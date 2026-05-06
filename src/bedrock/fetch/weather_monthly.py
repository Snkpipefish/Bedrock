# pyright: reportArgumentType=false, reportReturnType=false

"""Månedlig vær-fetcher mot Open-Meteo Archive.

Henter daglig observasjon (tmax, tmin, precip, et0) og aggregerer til
månedlig WeatherMonthlyRow-format som matcher eksisterende
`weather_monthly`-tabell migrert fra cot-explorer.

Aggregerings-terskler er kalibrert mot eksisterende regioner (sjekket
mot brazil_coffee 2011-2026): hot_days = tmax > 32°C, dry_days =
precip < 1 mm, wet_days = precip ≥ 10 mm.

Brukes når en ny region (f.eks. brazil_centro_sul for sukker) skal
backfilles uten cot-explorer pre-aggregert JSON.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"

HOT_DAY_TMAX_C = 32.0
DRY_DAY_PRECIP_MM = 1.0
WET_DAY_PRECIP_MM = 10.0


class WeatherMonthlyFetchError(RuntimeError):
    """Månedlig vær-fetch feilet permanent."""


def _build_params(
    latitude: float,
    longitude: float,
    from_date: date,
    to_date: date,
    timezone: str = "UTC",
) -> dict[str, str]:
    return {
        "latitude": str(latitude),
        "longitude": str(longitude),
        "start_date": from_date.isoformat(),
        "end_date": to_date.isoformat(),
        "daily": _DAILY_VARS,
        "timezone": timezone,
    }


def fetch_weather_monthly(
    region: str,
    latitude: float,
    longitude: float,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent og aggregér månedlig vær fra Open-Meteo Archive.

    Returnerer DataFrame med kolonner som matcher
    ``WEATHER_MONTHLY_COLS``. Ufullstendige sluttmåneder (mindre enn
    25 dager med data) droppes for å unngå skjeve aggregat.
    """
    params = _build_params(latitude, longitude, from_date, to_date)
    _log.info(
        "fetch_weather_monthly region=%s lat=%s lon=%s from=%s to=%s",
        region,
        latitude,
        longitude,
        from_date,
        to_date,
    )

    try:
        response = http_get_with_retry(OPEN_METEO_ARCHIVE_URL, params=params)
    except Exception as exc:
        raise WeatherMonthlyFetchError(
            f"Network failure fetching monthly weather for {region}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise WeatherMonthlyFetchError(
            f"Open-Meteo returned HTTP {response.status_code} for {region}: {response.text[:200]!r}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise WeatherMonthlyFetchError(
            f"Failed to parse Open-Meteo JSON for {region}: {exc}"
        ) from exc

    return aggregate_to_monthly(payload, region)


def aggregate_to_monthly(payload: dict, region: str) -> pd.DataFrame:
    """Aggregér Open-Meteo daglig respons til månedlige rader."""
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherMonthlyFetchError(
            f"Open-Meteo response for {region} missing 'daily' block. "
            f"Keys: {sorted(payload.keys())}"
        )

    required = [
        "time",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
    ]
    missing = [k for k in required if k not in daily]
    if missing:
        raise WeatherMonthlyFetchError(
            f"Open-Meteo response for {region} missing daily fields: {missing}"
        )

    n = len(daily["time"])
    if n == 0:
        return _empty_monthly_df()

    daily_df = pd.DataFrame(
        {
            "date": pd.to_datetime(daily["time"]),
            "tmax": daily["temperature_2m_max"],
            "tmin": daily["temperature_2m_min"],
            "precip": daily["precipitation_sum"],
            "et0": daily["et0_fao_evapotranspiration"],
        }
    )

    daily_df["temp_mean_daily"] = (daily_df["tmax"] + daily_df["tmin"]) / 2.0
    daily_df["month"] = daily_df["date"].dt.strftime("%Y-%m")

    grouped = daily_df.groupby("month", as_index=False).agg(
        days=("date", "count"),
        temp_mean=("temp_mean_daily", "mean"),
        temp_max=("tmax", "max"),
        precip_mm=("precip", "sum"),
        et0_mm=("et0", "sum"),
        hot_days=("tmax", lambda s: int((s > HOT_DAY_TMAX_C).sum())),
        dry_days=("precip", lambda s: int((s < DRY_DAY_PRECIP_MM).sum())),
        wet_days=("precip", lambda s: int((s >= WET_DAY_PRECIP_MM).sum())),
    )

    # Drop måneder med < 25 dager data (delvis siste-måned).
    grouped = grouped[grouped["days"] >= 25].copy()
    if grouped.empty:
        return _empty_monthly_df()

    grouped["region"] = region
    grouped["water_bal"] = grouped["precip_mm"] - grouped["et0_mm"]

    grouped["temp_mean"] = grouped["temp_mean"].round(2)
    grouped["temp_max"] = grouped["temp_max"].round(2)
    grouped["precip_mm"] = grouped["precip_mm"].round(1)
    grouped["et0_mm"] = grouped["et0_mm"].round(1)
    grouped["water_bal"] = grouped["water_bal"].round(1)
    grouped["hot_days"] = grouped["hot_days"].astype(int)
    grouped["dry_days"] = grouped["dry_days"].astype(int)
    grouped["wet_days"] = grouped["wet_days"].astype(int)

    cols = [
        "region",
        "month",
        "temp_mean",
        "temp_max",
        "precip_mm",
        "et0_mm",
        "hot_days",
        "dry_days",
        "wet_days",
        "water_bal",
    ]
    return grouped[cols].reset_index(drop=True)


def _empty_monthly_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "region",
            "month",
            "temp_mean",
            "temp_max",
            "precip_mm",
            "et0_mm",
            "hot_days",
            "dry_days",
            "wet_days",
            "water_bal",
        ]
    )
