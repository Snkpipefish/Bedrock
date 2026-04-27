# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""EIA Open Data v2 weekly-inventory fetcher (sub-fase 12.5+ session 107).

Henter US weekly petroleum stocks (Crude, Gasoline) og natural gas
storage fra EIA's Open Data API v2 (https://www.eia.gov/developer/).
Cot-explorer's `fetch_oilgas.py` hadde ingen EIA-implementasjon (kun
Google News), så dette er en fresh port mot v2-API-strukturen.

API-mønster (v2):
    GET https://api.eia.gov/v2/{route}/data/
        ?api_key=KEY
        &frequency=weekly
        &data[0]=value
        &facets[series][]=SERIES_ID
        &sort[0][column]=period
        &sort[0][direction]=desc
        &length=N

Default series (per ADR-008 + session 107-design):
- ``WCESTUS1``: US Ending Stocks excluding SPR of Crude Oil (MBBL)
- ``WGTSTUS1``: US Total Gasoline Stocks (MBBL)
- ``NW2_EPG0_SWO_R48_BCF``: US Working Natural Gas in Storage Lower 48 (BCF)

Petroleum-stocks publiseres typisk onsdag 10:30 ET (= 16:30 Oslo +
buffer); natural gas storage typisk torsdag 10:30 ET. Per ADR-008
fyrer fetcheren onsdag 17:30 Oslo (`30 17 * * 3`) — gass kommer da
også med på torsdag-fyringen via stale-detect, eller manuelt
re-kjøres torsdag.

Sekvensielle HTTP-requests per memory-feedback (gratis-API → ingen
parallell). Manuell CSV-fallback (per ADR-007 § 4) i
``data/manual/eia_inventory.csv``.

API-key oppslag (samme mønster som FRED + NASS):
1. CLI-arg / `api_key`-param
2. Env-var ``BEDROCK_EIA_API_KEY``
3. ``~/.bedrock/secrets.env``

Registrer gratis nøkkel på https://www.eia.gov/opendata/register.php
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import EIA_INVENTORY_COLS
from bedrock.fetch.base import http_get_with_retry

EIA_API_KEY_ENV = "BEDROCK_EIA_API_KEY"

_log = logging.getLogger(__name__)

_EIA_BASE = "https://api.eia.gov/v2"
_DEFAULT_TIMEOUT = 60.0
_REQUEST_PACING_SEC = 1.5  # mellom sekvensielle requests for å være snill mot gratis-API
_MANUAL_CSV = Path("data/manual/eia_inventory.csv")


# ---------------------------------------------------------------------------
# Series-katalog
# ---------------------------------------------------------------------------


# Hver default-serie har et route-prefix slik at v2-API kan velge riktig
# data-endpoint. ``frequency`` lagres slik at vi senere kan utvide til
# månedlige STEO-serier uten arkitektur-endring.
class _SeriesSpec:
    __slots__ = ("frequency", "label", "route", "series_id")

    def __init__(self, series_id: str, route: str, frequency: str, label: str):
        self.series_id = series_id
        self.route = route
        self.frequency = frequency
        self.label = label


DEFAULT_SERIES: tuple[_SeriesSpec, ...] = (
    _SeriesSpec(
        "WCESTUS1",
        "petroleum/stoc/wstk",
        "weekly",
        "US Crude Oil Ending Stocks excl. SPR (MBBL)",
    ),
    _SeriesSpec(
        "WGTSTUS1",
        "petroleum/stoc/wstk",
        "weekly",
        "US Total Gasoline Stocks (MBBL)",
    ),
    _SeriesSpec(
        "NW2_EPG0_SWO_R48_BCF",
        "natural-gas/stor/wkly",
        "weekly",
        "US Working Natural Gas in Storage Lower 48 (BCF)",
    ),
)


# ---------------------------------------------------------------------------
# Remote fetch (sekvensiell)
# ---------------------------------------------------------------------------


def fetch_eia_series(
    series_spec: _SeriesSpec,
    api_key: str,
    *,
    length: int = 5_000,
    timeout: float = _DEFAULT_TIMEOUT,
    raw_response: Any = None,  # injection-point for testing
) -> pd.DataFrame:
    """Hent én EIA-serie. Returnerer DataFrame med ``EIA_INVENTORY_COLS``.

    Args:
        series_spec: hvilken serie + route som skal hentes.
        api_key: EIA Open Data API-nøkkel.
        length: maks rader API-en skal returnere (5000 dekker >90 år
            ukentlig, EIA tillater max 5000 per call).
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed JSON-dict for testing. Hopper over HTTP.

    Returns:
        DataFrame med (series_id, date, value, units). Tom hvis API
        returnerer 0 rader.

    Raises:
        ValueError: ved HTTP-feil eller uventet response-struktur.
    """
    if raw_response is None:
        url = f"{_EIA_BASE}/{series_spec.route}/data/"
        params = {
            "api_key": api_key,
            "frequency": series_spec.frequency,
            "data[0]": "value",
            "facets[series][]": series_spec.series_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": str(length),
        }
        response = http_get_with_retry(url, params=params, timeout=timeout)
        if response.status_code != 200:
            raise ValueError(f"eia.{series_spec.series_id}: HTTP {response.status_code} from {url}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"eia.{series_spec.series_id}: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, dict):
        raise ValueError(
            f"eia.{series_spec.series_id}: expected JSON object, got {type(payload).__name__}"
        )

    response_section = payload.get("response")
    if not isinstance(response_section, dict):
        raise ValueError(f"eia.{series_spec.series_id}: missing 'response' key")

    raw_rows = response_section.get("data", [])
    rows: list[dict[str, Any]] = []
    for entry in raw_rows:
        if not isinstance(entry, dict):
            continue
        period = entry.get("period")
        value = entry.get("value")
        units = entry.get("units")
        if period is None or value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            _log.debug(
                "eia.skipping_non_numeric series=%s period=%s value=%r",
                series_spec.series_id,
                period,
                value,
            )
            continue
        rows.append(
            {
                "series_id": series_spec.series_id,
                "date": str(period),
                "value": numeric_value,
                "units": str(units) if units else None,
            }
        )

    df = pd.DataFrame(rows, columns=list(EIA_INVENTORY_COLS))
    _log.info("eia.fetched series=%s rows=%d", series_spec.series_id, len(df))
    return df


def fetch_eia_inventories(
    *,
    series: Sequence[_SeriesSpec] = DEFAULT_SERIES,
    api_key: str | None = None,
    length: int = 5_000,
    timeout: float = _DEFAULT_TIMEOUT,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent alle default-series sekvensielt og konkateneres.

    Mellom hver request settes et lite pacing-delay (default 1.5 s)
    for å være snill mot gratis-API-en.

    Returnerer kombinert DataFrame med alle serier. Tom DataFrame
    (med riktig kolonnesett) hvis ingen serier ga rader. Reiser
    ``ValueError`` hvis api_key mangler.
    """
    key = api_key or get_secret(EIA_API_KEY_ENV)
    if not key:
        raise ValueError(
            f"eia: mangler API-nøkkel — sett env-var {EIA_API_KEY_ENV} eller "
            f"~/.bedrock/secrets.env. Registrer gratis på "
            f"https://www.eia.gov/opendata/register.php"
        )

    frames: list[pd.DataFrame] = []
    for i, spec in enumerate(series):
        if i > 0:
            time.sleep(pacing_sec)
        try:
            df = fetch_eia_series(spec, key, length=length, timeout=timeout)
        except Exception as exc:
            _log.warning("eia.series_failed series=%s error=%s", spec.series_id, exc)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=list(EIA_INVENTORY_COLS))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Manuell CSV-fallback
# ---------------------------------------------------------------------------


def fetch_eia_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert CSV fra ``data/manual/eia_inventory.csv``.

    CSV må ha kolonnene i ``EIA_INVENTORY_COLS``. Returnerer tom
    DataFrame hvis filen mangler.

    Raises:
        ValueError: hvis filen finnes men mangler påkrevde kolonner.
    """
    if not csv_path.exists():
        _log.info("eia.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(EIA_INVENTORY_COLS))

    df = pd.read_csv(csv_path)
    missing = [c for c in EIA_INVENTORY_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"eia_inventory manual CSV mangler kolonner: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[list(EIA_INVENTORY_COLS)].copy()


# ---------------------------------------------------------------------------
# Combined: API + fallback (ingen exceptions oppover)
# ---------------------------------------------------------------------------


def fetch_eia(
    *,
    api_key: str | None = None,
    csv_path: Path = _MANUAL_CSV,
    series: Sequence[_SeriesSpec] = DEFAULT_SERIES,
) -> pd.DataFrame:
    """Hent EIA — prøv API først, så manuell CSV-fallback.

    Returnerer alltid en DataFrame; tom hvis både API og manuell mangler.
    Ingen exceptions propageres (caller sjekker df.empty).
    """
    try:
        df = fetch_eia_inventories(series=series, api_key=api_key)
        if not df.empty:
            return df
    except Exception as exc:
        _log.warning("eia.api_failed_fallback_to_csv error=%s", exc)

    try:
        return fetch_eia_manual(csv_path)
    except Exception as exc:
        _log.warning("eia.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(EIA_INVENTORY_COLS))


__all__ = [
    "DEFAULT_SERIES",
    "EIA_API_KEY_ENV",
    "_SeriesSpec",
    "fetch_eia",
    "fetch_eia_inventories",
    "fetch_eia_manual",
    "fetch_eia_series",
]
