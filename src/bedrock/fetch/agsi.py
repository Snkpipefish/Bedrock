# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).
"""AGSI+ (GIE) EU gas storage fetcher (sub-fase 12.7 D1 A2, session 130).

Endepunkt:
    https://agsi.gie.eu/api?country={code}&date={YYYY-MM-DD}

Header:
    x-key: $AGSI_API_KEY

Krever API-nøkkel (gratis fra https://agsi.gie.eu/account). Nøkkel
lastes via ``bedrock.config.secrets`` (env-var eller
``~/.bedrock/secrets.env``, nøkkel ``AGSI_API_KEY``).

Tidligste data: 2011-01-01 (DE). EU-aggregat (`country=eu`) er primær
input til ``agsi_storage_pct``-driver i NaturalGas macro-familien
(low_bull = lavt fyllingsgrad ⇒ bull NG-pris).

API-returformat (per dag, per country):
- gasInStorage: gass i lager (TWh, float-as-string)
- workingGasVolume: maks-kapasitet (TWh)
- consumptionFull: % av maks-kapasitet (0..100, float-as-string)
- injection: daglig injection (TWh)
- withdrawal: daglig withdrawal (TWh)
- netWithdrawal: withdrawal - injection (TWh)
- gasDayStart: ISO YYYY-MM-DD

Per ADR-007 § 4: manuell CSV-fallback fra dag 1 finnes i
``data/manual/agsi_storage.csv`` (ikke obligatorisk for AGSI siden
endpointet er stabilt + token-basert auth).

Sekvensielle requests med 1.5s pacing-delay per
memory:`feedback_free_api_no_parallel.md` (gratis kilder krever
sekvensielle HTTP-kall).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import AGSI_STORAGE_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

AGSI_API_KEY_ENV = "AGSI_API_KEY"
AGSI_BASE_URL = "https://agsi.gie.eu/api"
DEFAULT_TIMEOUT = 30.0
REQUEST_PACING_SEC = 1.5

# Default countries to fetch. EU er primær for driver; per-land for
# fremtidig utvidelse + diagnostikk.
DEFAULT_COUNTRIES: tuple[str, ...] = ("eu", "de", "nl", "fr", "it")


class AgsiFetchError(RuntimeError):
    """AGSI-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def _to_float_or_none(v: Any) -> float | None:
    """Robust float-konvertering. AGSI returnerer numerikk som strings."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_record(rec: dict[str, Any], country: str) -> dict[str, Any] | None:
    """Konverter én AGSI-record til AGSI_STORAGE_COLS-format. None hvis ugyldig."""
    gas_day = rec.get("gasDayStart")
    if not gas_day:
        return None
    return {
        "country": country.lower(),
        "gas_day_start": str(gas_day),
        "gas_in_storage_twh": _to_float_or_none(rec.get("gasInStorage")),
        "working_gas_volume_twh": _to_float_or_none(rec.get("workingGasVolume")),
        "consumption_full_pct": _to_float_or_none(rec.get("full"))
        or _to_float_or_none(rec.get("consumptionFull")),
        "injection_twh": _to_float_or_none(rec.get("injection")),
        "withdrawal_twh": _to_float_or_none(rec.get("withdrawal")),
        "net_withdrawal_twh": _to_float_or_none(rec.get("netWithdrawal")),
    }


def fetch_agsi_country_range(
    country: str,
    api_key: str,
    *,
    from_date: date,
    to_date: date,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent AGSI-data for ett land over et dato-range.

    AGSI-API støtter ``from`` og ``to``-parametre — én request returnerer
    hele rangen som en liste i ``data``-feltet (paginated, page-param).

    Args:
        country: ISO-2 lowercase eller "eu".
        api_key: AGSI API-nøkkel.
        from_date / to_date: inkluderende dato-range.
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed JSON for testing. Hopper over HTTP.

    Returns:
        DataFrame med ``AGSI_STORAGE_COLS``. Tom hvis ingen rader.

    Raises:
        AgsiFetchError: ved HTTP-feil eller uventet payload-struktur.
    """
    if raw_response is None:
        # AGSI v2: per-land bruker `?country=<ISO2>`. EU-aggregat ligger under
        # `?type=eu` (verifisert mot live API 2026-04-29). Driveren benytter
        # samme storage-nøkkel "eu" for aggregat-radene.
        if country.lower() == "eu":
            params = {
                "type": "eu",
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "size": "300",
            }
        else:
            params = {
                "country": country,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "size": "300",  # AGSI default 30; 300 dekker ~10 mnd per page
            }
        try:
            response = http_get_with_retry(
                AGSI_BASE_URL,
                params=params,
                timeout=timeout,
                headers={"x-key": api_key},
            )
        except Exception as exc:
            raise AgsiFetchError(f"agsi.{country}: network failure: {exc}") from exc

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise AgsiFetchError(f"agsi.{country}: HTTP {response.status_code}: {body_preview!r}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AgsiFetchError(f"agsi.{country}: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, dict):
        raise AgsiFetchError(f"agsi.{country}: expected JSON object, got {type(payload).__name__}")

    raw_rows = payload.get("data", [])
    if not isinstance(raw_rows, list):
        raise AgsiFetchError(f"agsi.{country}: 'data' must be list, got {type(raw_rows).__name__}")

    rows: list[dict[str, Any]] = []
    for rec in raw_rows:
        if not isinstance(rec, dict):
            continue
        normalized = _normalize_record(rec, country)
        if normalized is not None:
            rows.append(normalized)

    df = pd.DataFrame(rows, columns=list(AGSI_STORAGE_COLS))
    _log.info("agsi.fetched country=%s rows=%d", country, len(df))
    return df


def fetch_agsi_storage(
    *,
    countries: Sequence[str] = DEFAULT_COUNTRIES,
    api_key: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    pacing_sec: float = REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent AGSI for alle gitte countries sekvensielt og kombinér.

    Default-vinduet er siste 30 dager hvis from/to ikke gitt — passer
    daglig fetcher-bruk. For backfill, bruk
    ``scripts/backfill/agsi.py`` med eksplisitte dato-grenser.

    Per memory:free-api-no-parallel-requests sender vi sekvensielt med
    ``pacing_sec`` mellom hver country-request.

    Returnerer kombinert DataFrame. Tom hvis ingen countries leverte
    data. Reiser ``AgsiFetchError`` hvis api_key mangler.
    """
    import time

    key = api_key or get_secret(AGSI_API_KEY_ENV)
    if not key:
        raise AgsiFetchError(
            f"AGSI api_key missing — set env-var {AGSI_API_KEY_ENV} "
            f"or ~/.bedrock/secrets.env entry."
        )

    today = date.today()
    end = to_date or today
    start = from_date or (today - timedelta(days=30))

    frames: list[pd.DataFrame] = []
    for i, country in enumerate(countries):
        if i > 0:
            time.sleep(pacing_sec)
        try:
            df = fetch_agsi_country_range(
                country, key, from_date=start, to_date=end, timeout=timeout
            )
        except AgsiFetchError as exc:
            _log.warning("agsi.country_failed country=%s error=%s", country, exc)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=list(AGSI_STORAGE_COLS))
    return pd.concat(frames, ignore_index=True)
