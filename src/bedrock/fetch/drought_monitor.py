# pyright: reportArgumentType=false, reportReturnType=false
"""US Drought Monitor (USDM) fetcher (sub-fase 12.7 D2 A9, session 133).

Endepunkt:
    https://usdmdataservices.unl.edu/api/USStatistics/
        GetDroughtSeverityStatisticsByAreaPercent?
        aoi={aoi}&startdate={M/D/Y}&enddate={M/D/Y}&statisticsType=1

Format: CSV uten BOM (header + rader).
Tidligste data: 2000-01-04 (USDM lansert jan-2000).
Frekvens: ukentlig (gjeldende fra hver torsdag, basert på tirsdags-data).

Vi bruker statisticsType=1 (cumulative) — D0=% i D0+, D1=% i D1+, etc.
D2+ er primær driver-input (severe+).

Per ADR-007: gratis, ingen auth, men sekvensielle calls per
memory:`feedback_free_api_no_parallel.md` (1.5s pacing). USDM-API har
en chunk-grense (~365 dager per call); skriptet håndterer dette ved å
chunke per 1-års-vinduer.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Any

import pandas as pd

from bedrock.data.schemas import DROUGHT_MONITOR_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

USDM_BASE_URL = (
    "https://usdmdataservices.unl.edu/api/USStatistics/GetDroughtSeverityStatisticsByAreaPercent"
)
USDM_STATE_URL = (
    "https://usdmdataservices.unl.edu/api/StateStatistics/GetDroughtSeverityStatisticsByAreaPercent"
)
DEFAULT_TIMEOUT = 30.0
REQUEST_PACING_SEC = 1.5

# State-abbrev → FIPS-kode (StateStatistics-endpoint krever FIPS, ikke abbrev).
# Sub-fase 12.10 Bunke 5 #19. Kun de 5 statene som driverne wires til —
# kan utvides ved behov.
_STATE_ABBREV_TO_FIPS: dict[str, str] = {
    "ia": "19",  # Iowa
    "tx": "48",  # Texas
    "ca": "06",  # California
    "ks": "20",  # Kansas
    "nd": "38",  # North Dakota
}


class DroughtMonitorFetchError(RuntimeError):
    """USDM-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def _to_float_or_none(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _format_date_us(d: date) -> str:
    """USDM API forventer M/D/YYYY (ikke ISO)."""
    return f"{d.month}/{d.day}/{d.year}"


def _yyyymmdd_to_iso(s: str) -> str | None:
    """Konverter '20241231' til '2024-12-31'."""
    if not s or len(s) < 8:
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _parse_csv_payload(text: str, aoi: str) -> list[dict[str, Any]]:
    """Parse USDM CSV til rader matching DROUGHT_MONITOR_COLS-skjema."""
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if not raw:
            continue
        map_date = _yyyymmdd_to_iso(raw.get("MapDate", ""))
        if map_date is None:
            continue
        rows.append(
            {
                "map_date": map_date,
                "aoi": aoi,
                "none_pct": _to_float_or_none(raw.get("None")),
                "d0_pct": _to_float_or_none(raw.get("D0")),
                "d1_pct": _to_float_or_none(raw.get("D1")),
                "d2_pct": _to_float_or_none(raw.get("D2")),
                "d3_pct": _to_float_or_none(raw.get("D3")),
                "d4_pct": _to_float_or_none(raw.get("D4")),
                "valid_start": raw.get("ValidStart") or None,
                "valid_end": raw.get("ValidEnd") or None,
            }
        )
    return rows


def fetch_drought_monitor(
    *,
    aoi: str = "us",
    start_date: date,
    end_date: date,
    statistics_type: int = 1,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent USDM-data for ett AOI × dato-range.

    Args:
        aoi: AOI-kode. ``"us"`` = CONUS-aggregat (default). Også state-koder
            som ``"IA"``, ``"IL"``, etc.
        start_date / end_date: inkluderende dato-range.
        statistics_type: 1 = cumulative (D0=% i D0+; D1=% i D1+; ...).
            2 = categorical (D0=% kun i D0; D1=% kun i D1; ...). Bedrock
            bruker 1.
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed CSV-streng for testing. Hopper over HTTP.

    Returns:
        DataFrame med ``DROUGHT_MONITOR_COLS``. Tom hvis ingen rader.
    """
    if raw_response is None:
        # Sub-fase 12.10 Bunke 5 #19: konvertér state-abbrev til FIPS-kode
        # (StateStatistics-endpoint krever FIPS).
        api_aoi = aoi
        if aoi.lower() in _STATE_ABBREV_TO_FIPS:
            api_aoi = _STATE_ABBREV_TO_FIPS[aoi.lower()]
        params = {
            "aoi": api_aoi,
            "startdate": _format_date_us(start_date),
            "enddate": _format_date_us(end_date),
            "statisticsType": str(statistics_type),
        }
        # state-aoi (≤2 chars eller numerisk FIPS) routes til StateStatistics-
        # endpoint. CONUS aggregat ('us') bruker default.
        is_state = aoi.lower() != "us" and (len(aoi) <= 2 or aoi.isdigit())
        url = USDM_STATE_URL if is_state else USDM_BASE_URL
        try:
            response = http_get_with_retry(url, params=params, timeout=timeout)
        except Exception as exc:
            raise DroughtMonitorFetchError(f"usdm.{aoi}: network failure: {exc}") from exc

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise DroughtMonitorFetchError(
                f"usdm.{aoi}: HTTP {response.status_code}: {body_preview!r}"
            )
        payload = response.text
    else:
        payload = raw_response

    if not isinstance(payload, str):
        raise DroughtMonitorFetchError(
            f"usdm.{aoi}: expected CSV-string, got {type(payload).__name__}"
        )

    rows = _parse_csv_payload(payload, aoi=aoi.lower())
    df = pd.DataFrame(rows, columns=list(DROUGHT_MONITOR_COLS))
    _log.info(
        "usdm.fetched aoi=%s rows=%d range=%s..%s",
        aoi,
        len(df),
        start_date,
        end_date,
    )
    return df
