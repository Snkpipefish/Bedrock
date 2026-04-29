# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).
"""USDA FAS Export Sales Reporting (ESR) fetcher (sub-fase 12.7 D2 A3, session 133).

Endepunkt:
    https://api.fas.usda.gov/api/esr/exports/commodityCode/{cc}/allCountries/marketYear/{my}
    https://api.fas.usda.gov/api/esr/exports/commodityCode/{cc}/countryCode/{ccode}/marketYear/{my}

Header:
    X-Api-Key: $FAS_API_KEY  (api.data.gov-konvensjon — universell key
        funker mot ESR/GATS/PSD og andre USDA/føderale endpoints).

Krever API-nøkkel (gratis fra https://api.data.gov/signup/). Nøkkel
lastes via ``bedrock.config.secrets`` (env-var eller
``~/.bedrock/secrets.env``, nøkkel ``FAS_API_KEY``). Samme key er typisk
duplisert som ``USDA_API_KEY`` + ``API_DATA_GOV_KEY`` for fleksibilitet.

Tidligste data: ESR har MY 2010 og fremover (verifisert via
``/datareleasedates``). Marketing year-konvensjon varierer per
commodity: Corn/Soybean/Cotton MY = Sep-Aug, Wheat MY = Jun-May.

API-returformat (per (commodity × country × MY × week)):
- weeklyExports, accumulatedExports, outstandingSales: kjernemetrikk
- grossNewSales, currentMYNetSales, currentMYTotalCommitment
- nextMYOutstandingSales, nextMYNetSales: rull-over til neste MY
- unitId: refererer til /unitsOfMeasure (typisk 1 = metric tonnes)
- weekEndingDate: ISO 8601 (T00:00:00 suffix; vi normaliserer til YYYY-MM-DD)

Sekvensielle requests med 1.5s pacing-delay per
memory:`feedback_free_api_no_parallel.md` (gratis kilder krever
sekvensielle HTTP-kall).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import FAS_ESR_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

FAS_API_KEY_ENV = "FAS_API_KEY"
FAS_BASE_URL = "https://api.fas.usda.gov/api"
DEFAULT_TIMEOUT = 30.0
REQUEST_PACING_SEC = 1.5

# Bedrock-relevante FAS commodity codes (verifisert mot /esr/commodities).
# Cotton er fragmentert i FAS — 1404 ("All Upland Cotton") er aggregat-koden
# (1401-1403 er bredde-grader; 1301 = American Pima er separat). Det vi ser i
# CBOT/CFD som "Cotton" er typisk Upland → 1404.
COMMODITY_CODES: dict[str, int] = {
    "corn": 401,
    "soybean": 801,
    "wheat": 107,  # All Wheat (aggregat)
    "cotton": 1404,  # All Upland Cotton (aggregat); 1301 = Pima er separat
}


class FasFetchError(RuntimeError):
    """FAS-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def _to_float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normalize_week_ending(v: Any) -> str | None:
    """Konverter 'YYYY-MM-DDTHH:MM:SS' eller dato til 'YYYY-MM-DD'."""
    if v is None:
        return None
    s = str(v)
    # Strip ISO-8601 T-suffix
    if "T" in s:
        s = s.split("T", 1)[0]
    return s[:10]


def _normalize_record(
    rec: dict[str, Any], commodity_code: int, market_year: int
) -> dict[str, Any] | None:
    week_ending = _normalize_week_ending(rec.get("weekEndingDate"))
    country_code = _to_int_or_none(rec.get("countryCode"))
    if week_ending is None or country_code is None:
        return None
    return {
        "commodity_code": commodity_code,
        "country_code": country_code,
        "market_year": market_year,
        "week_ending_date": week_ending,
        "weekly_exports": _to_float_or_none(rec.get("weeklyExports")),
        "accumulated_exports": _to_float_or_none(rec.get("accumulatedExports")),
        "outstanding_sales": _to_float_or_none(rec.get("outstandingSales")),
        "gross_new_sales": _to_float_or_none(rec.get("grossNewSales")),
        "current_my_net_sales": _to_float_or_none(rec.get("currentMYNetSales")),
        "current_my_total_commitment": _to_float_or_none(rec.get("currentMYTotalCommitment")),
        "next_my_outstanding_sales": _to_float_or_none(rec.get("nextMYOutstandingSales")),
        "next_my_net_sales": _to_float_or_none(rec.get("nextMYNetSales")),
        "unit_id": _to_int_or_none(rec.get("unitId")),
    }


def fetch_esr_exports(
    commodity_code: int,
    market_year: int,
    *,
    country_code: int | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent FAS ESR-eksport-data for én commodity × MY (× country, optional).

    Args:
        commodity_code: FAS commodityCode (Corn=401, Soybean=801, Wheat=107, Cotton=501).
        market_year: Marketing year (start-året, eks. 2024 = MY24/25).
        country_code: Hvis None, henter ``/allCountries`` (alle countries i én call).
            Hvis spesifisert, henter kun den country-en.
        api_key: FAS API-nøkkel. Default fra env/secrets.
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed JSON for testing. Hopper over HTTP.

    Returns:
        DataFrame med ``FAS_ESR_COLS``. Tom hvis ingen rader.

    Raises:
        FasFetchError: ved HTTP-feil eller uventet payload-struktur.
    """
    key = api_key or get_secret(FAS_API_KEY_ENV)
    if raw_response is None and not key:
        raise FasFetchError(
            f"FAS api_key missing — set env-var {FAS_API_KEY_ENV} or ~/.bedrock/secrets.env entry."
        )

    if raw_response is None:
        if country_code is None:
            url = f"{FAS_BASE_URL}/esr/exports/commodityCode/{commodity_code}/allCountries/marketYear/{market_year}"
        else:
            url = (
                f"{FAS_BASE_URL}/esr/exports/commodityCode/{commodity_code}"
                f"/countryCode/{country_code}/marketYear/{market_year}"
            )
        try:
            response = http_get_with_retry(
                url,
                params=None,
                timeout=timeout,
                headers={"X-Api-Key": key},
            )
        except Exception as exc:
            raise FasFetchError(
                f"fas_esr.{commodity_code}.{market_year}: network failure: {exc}"
            ) from exc

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise FasFetchError(
                f"fas_esr.{commodity_code}.{market_year}: "
                f"HTTP {response.status_code}: {body_preview!r}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FasFetchError(
                f"fas_esr.{commodity_code}.{market_year}: invalid JSON: {exc}"
            ) from exc
    else:
        payload = raw_response

    if not isinstance(payload, list):
        raise FasFetchError(
            f"fas_esr.{commodity_code}.{market_year}: expected JSON list, "
            f"got {type(payload).__name__}"
        )

    rows: list[dict[str, Any]] = []
    for rec in payload:
        if not isinstance(rec, dict):
            continue
        normalized = _normalize_record(rec, commodity_code, market_year)
        if normalized is not None:
            rows.append(normalized)

    df = pd.DataFrame(rows, columns=list(FAS_ESR_COLS))
    _log.info(
        "fas_esr.fetched commodity=%s my=%s country=%s rows=%d",
        commodity_code,
        market_year,
        country_code if country_code is not None else "ALL",
        len(df),
    )
    return df


def fetch_fas_esr_multi(
    commodities: Sequence[int],
    market_years: Sequence[int],
    *,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    pacing_sec: float = REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent FAS ESR for alle (commodity × MY)-par sekvensielt og kombinér.

    Per memory:free-api-no-parallel-requests sender vi sekvensielt med
    ``pacing_sec`` mellom hver request. Bruker ``/allCountries`` per call
    så én request dekker alle land for et gitt (commodity, MY).

    Returnerer kombinert DataFrame. Tom hvis ingen call leverte data.
    """
    import time

    key = api_key or get_secret(FAS_API_KEY_ENV)
    if not key:
        raise FasFetchError(
            f"FAS api_key missing — set env-var {FAS_API_KEY_ENV} or ~/.bedrock/secrets.env entry."
        )

    frames: list[pd.DataFrame] = []
    first = True
    for commodity_code in commodities:
        for market_year in market_years:
            if not first:
                time.sleep(pacing_sec)
            first = False
            try:
                df = fetch_esr_exports(
                    commodity_code,
                    market_year,
                    api_key=key,
                    timeout=timeout,
                )
            except FasFetchError as exc:
                _log.warning(
                    "fas_esr.call_failed commodity=%s my=%s error=%s",
                    commodity_code,
                    market_year,
                    exc,
                )
                continue
            if not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame(columns=list(FAS_ESR_COLS))
    return pd.concat(frames, ignore_index=True)
