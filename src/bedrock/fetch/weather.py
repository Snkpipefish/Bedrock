"""Weather-fetcher mot Open-Meteo Archive API.

Ingen auth, ingen API-nøkkel. Dekker 1940-present (ERA5 reanalysis) for
vilkårlig (lat, lon).

Endepunkt:
    https://archive-api.open-meteo.com/v1/archive

Vi henter daglige variabler:
    temperature_2m_max → tmax (°C)
    temperature_2m_min → tmin (°C)
    precipitation_sum  → precip (mm)

`gdd` (growing-degree-days) beregnes IKKE i fetcher-en — base-temperaturen
er crop-spesifikk (10°C for mais, 8°C for hvete, etc.) og hører i en driver
som kjenner context. Kolonnen skrives som NULL og fylles evt. senere.

Region-navnet (f.eks. `us_cornbelt`, `brazil_mato_grosso`) er et
Bedrock-internt tag som bruker henvender seg til; (lat, lon) er
faktisk-query-parametre til Open-Meteo. Region→koordinat-mapping hører
til Fase 5 instrument-config.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum"


class WeatherFetchError(RuntimeError):
    """Weather-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def build_open_meteo_params(
    latitude: float,
    longitude: float,
    from_date: date,
    to_date: date,
    timezone: str = "UTC",
) -> dict[str, str]:
    """Bygg URL-parametre for Open-Meteo Archive. Eksponert for `--dry-run`."""
    return {
        "latitude": f"{latitude}",
        "longitude": f"{longitude}",
        "start_date": from_date.isoformat(),
        "end_date": to_date.isoformat(),
        "daily": _DAILY_VARS,
        "timezone": timezone,
    }


def fetch_weather(
    region: str,
    latitude: float,
    longitude: float,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent daglige vær-observasjoner fra Open-Meteo Archive.

    Returnerer DataFrame som matcher `DataStore.append_weather`
    (kolonner: region, date, tmax, tmin, precip, gdd). `gdd` er NULL.

    `region` er tagg som lagres; (lat, lon) bestemmer faktisk sted.

    Kaster `WeatherFetchError` ved HTTP-feil eller malformert JSON.
    """
    params = build_open_meteo_params(latitude, longitude, from_date, to_date)
    _log.info(
        "fetch_weather region=%s lat=%s lon=%s from=%s to=%s",
        region,
        latitude,
        longitude,
        from_date,
        to_date,
    )

    try:
        response = http_get_with_retry(OPEN_METEO_ARCHIVE_URL, params=params)
    except Exception as exc:
        raise WeatherFetchError(
            f"Network failure fetching weather for {region}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise WeatherFetchError(
            f"Open-Meteo returned HTTP {response.status_code} for {region}: "
            f"{response.text[:200]!r}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise WeatherFetchError(f"Failed to parse Open-Meteo JSON for {region}: {exc}") from exc

    return _normalize_open_meteo(data, region)


def _normalize_open_meteo(payload: dict, region: str) -> pd.DataFrame:
    """Konverter Open-Meteo `{daily: {time: [...], var: [...]}}` til Bedrock-schema."""
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherFetchError(
            f"Open-Meteo response for {region} missing 'daily' block. "
            f"Keys: {sorted(payload.keys())}"
        )

    required = ["time", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
    missing = [k for k in required if k not in daily]
    if missing:
        raise WeatherFetchError(
            f"Open-Meteo response for {region} missing daily fields: {missing}"
        )

    times = daily["time"]
    n = len(times)

    # Tom respons (0 rader) er teoretisk ikke lovlig for gyldige datoer, men vi
    # behandler det som tom DataFrame heller enn error.
    if n == 0:
        return pd.DataFrame(columns=["region", "date", "tmax", "tmin", "precip", "gdd"])

    df = pd.DataFrame(
        {
            "region": [region] * n,
            "date": times,
            "tmax": daily["temperature_2m_max"],
            "tmin": daily["temperature_2m_min"],
            "precip": daily["precipitation_sum"],
            "gdd": [None] * n,  # beregnes i driver med crop-spesifikk base-temp
        }
    )
    return df
