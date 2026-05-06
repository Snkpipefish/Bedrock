"""USDA FAS PSD (Production, Supply, Distribution) fetcher.

Henter årlig sukker-PSD-data per land via FAS API. Erstatter ISMA-
parsing (som ga kun 18 mnd) med autoritative offisielle data tilbake
til 2010 og bakover.

API: https://api.fas.usda.gov/api/psd/commodity/{code}/country/{iso}/year/{year}
Auth: X-Api-Key header

Sub-fase 12.11+ analytiker D.5 — supplementer ISMA med USDA PSD for å
få 16+ års historikk for India sugar production/exports/imports/stocks.

Initial bruk: India sugar (commodity 0612000, country IN). Senere
utvidbar til Thailand (TH), Brasil (BR), EU (E1), etc.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

API_BASE = "https://api.fas.usda.gov/api/psd"

# PSD attribute IDs (per USDA PSD reference)
ATTR_PRODUCTION = 28
ATTR_EXPORTS = 89
ATTR_IMPORTS = 30
ATTR_ENDING_STOCKS = 86
ATTR_BEGIN_STOCKS = 20

# Commodity codes
COMMODITY_SUGAR_CENTRIFUGAL = "0612000"


class UsdaPsdFetchError(RuntimeError):
    """USDA PSD-fetch feilet."""


def _get_api_key(api_key: str | None = None) -> str:
    if api_key:
        return api_key
    for env in ("USDA_API_KEY", "FAS_API_KEY", "API_DATA_GOV_KEY"):
        v = get_secret(env)
        if v:
            return v
    raise UsdaPsdFetchError(
        "USDA API key not found. Set USDA_API_KEY in env or ~/.bedrock/secrets.env"
    )


def fetch_psd_country_year(
    commodity_code: str,
    country_iso: str,
    year: int,
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Returner råe PSD-records for ett (commodity, country, year)."""
    key = _get_api_key(api_key)
    url = f"{API_BASE}/commodity/{commodity_code}/country/{country_iso}/year/{year}"
    try:
        response = http_get_with_retry(url, headers={"X-Api-Key": key}, timeout=timeout)
    except Exception as exc:
        raise UsdaPsdFetchError(
            f"Network failure for {commodity_code}/{country_iso}/{year}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise UsdaPsdFetchError(
            f"USDA PSD HTTP {response.status_code} for "
            f"{commodity_code}/{country_iso}/{year}: {response.text[:200]!r}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise UsdaPsdFetchError(f"Failed to parse USDA PSD JSON: {exc}") from exc

    if not isinstance(data, list):
        raise UsdaPsdFetchError(f"Unexpected response shape: {type(data)}")

    return data


def fetch_india_sugar_history(
    from_year: int = 2010,
    to_year: int | None = None,
    *,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Hent India sugar PSD-historikk som fundamentals-DataFrame.

    Returnerer rader for 4 series_id:
    - USDA_PSD_INDIA_SUGAR_PROD_KMT
    - USDA_PSD_INDIA_SUGAR_EXPORTS_KMT
    - USDA_PSD_INDIA_SUGAR_IMPORTS_KMT
    - USDA_PSD_INDIA_SUGAR_ENDSTOCKS_KMT

    Date-stempel: marketing-year start (oct-1 av MY).
    """
    import time
    from datetime import date

    if to_year is None:
        to_year = date.today().year

    rows: list[dict[str, Any]] = []
    for year in range(from_year, to_year + 1):
        try:
            records = fetch_psd_country_year(
                COMMODITY_SUGAR_CENTRIFUGAL, "IN", year, api_key=api_key
            )
        except UsdaPsdFetchError as exc:
            _log.warning("usda_psd.year_failed year=%s error=%s", year, exc)
            continue

        if not records:
            continue

        my = int(records[0].get("marketYear", year))
        date_str = f"{my}-10-01"

        attr_to_series = {
            ATTR_PRODUCTION: "USDA_PSD_INDIA_SUGAR_PROD_KMT",
            ATTR_EXPORTS: "USDA_PSD_INDIA_SUGAR_EXPORTS_KMT",
            ATTR_IMPORTS: "USDA_PSD_INDIA_SUGAR_IMPORTS_KMT",
            ATTR_ENDING_STOCKS: "USDA_PSD_INDIA_SUGAR_ENDSTOCKS_KMT",
        }
        for rec in records:
            attr_id = rec.get("attributeId")
            sid = attr_to_series.get(attr_id)
            if sid is None:
                continue
            rows.append(
                {
                    "series_id": sid,
                    "date": date_str,
                    "value": float(rec["value"]),
                }
            )
        time.sleep(0.3)  # gratis-API-sparing

    if not rows:
        return pd.DataFrame(columns=["series_id", "date", "value"])

    df = pd.DataFrame(rows)
    # Dedup (series_id, date) — siste vinner
    df = df.drop_duplicates(subset=["series_id", "date"], keep="last")
    return df.sort_values(["series_id", "date"]).reset_index(drop=True)
