"""Tester for Open-Meteo vær-fetcher."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from bedrock.fetch.weather import (
    OPEN_METEO_ARCHIVE_URL,
    WeatherFetchError,
    build_open_meteo_params,
    fetch_weather,
)

# ---------------------------------------------------------------------------
# Query-bygging
# ---------------------------------------------------------------------------


def test_build_params_includes_lat_lon_dates_daily() -> None:
    params = build_open_meteo_params(40.75, -96.75, date(2024, 1, 2), date(2024, 1, 5))
    assert params["latitude"] == "40.75"
    assert params["longitude"] == "-96.75"
    assert params["start_date"] == "2024-01-02"
    assert params["end_date"] == "2024-01-05"
    assert "temperature_2m_max" in params["daily"]
    assert "temperature_2m_min" in params["daily"]
    assert "precipitation_sum" in params["daily"]


def test_build_params_default_timezone_utc() -> None:
    params = build_open_meteo_params(0.0, 0.0, date(2024, 1, 1), date(2024, 1, 2))
    assert params["timezone"] == "UTC"


# ---------------------------------------------------------------------------
# fetch_weather med mocked HTTP
# ---------------------------------------------------------------------------


SAMPLE_RESPONSE = {
    "latitude": 40.75,
    "longitude": -96.75,
    "daily": {
        "time": ["2024-07-01", "2024-07-02", "2024-07-03"],
        "temperature_2m_max": [30.1, 31.5, 29.8],
        "temperature_2m_min": [18.2, 19.4, 17.9],
        "precipitation_sum": [0.0, 2.5, 0.2],
    },
}


def _mock_response(payload, status: int = 200) -> Mock:
    m = Mock()
    m.status_code = status
    m.text = str(payload)[:500]
    m.json = Mock(return_value=payload)
    return m


def test_fetch_weather_returns_bedrock_schema() -> None:
    with patch(
        "bedrock.fetch.weather.http_get_with_retry",
        return_value=_mock_response(SAMPLE_RESPONSE),
    ):
        df = fetch_weather("us_cornbelt", 40.75, -96.75, date(2024, 7, 1), date(2024, 7, 3))

    assert list(df.columns) == ["region", "date", "tmax", "tmin", "precip", "gdd"]
    assert len(df) == 3
    assert df["region"].iloc[0] == "us_cornbelt"
    assert df["tmax"].iloc[0] == 30.1
    assert df["precip"].iloc[1] == 2.5


def test_fetch_weather_gdd_is_null() -> None:
    """gdd lagres som NULL — beregnes senere i driver med crop-spesifikk base."""
    with patch(
        "bedrock.fetch.weather.http_get_with_retry",
        return_value=_mock_response(SAMPLE_RESPONSE),
    ):
        df = fetch_weather("us_cornbelt", 40.75, -96.75, date(2024, 7, 1), date(2024, 7, 3))

    assert df["gdd"].isna().all()


def test_fetch_weather_end_to_end_matches_datastore(tmp_path) -> None:
    """Fetcher-output skal gå direkte inn i DataStore.append_weather."""
    from bedrock.data.store import DataStore

    with patch(
        "bedrock.fetch.weather.http_get_with_retry",
        return_value=_mock_response(SAMPLE_RESPONSE),
    ):
        df = fetch_weather("us_cornbelt", 40.75, -96.75, date(2024, 7, 1), date(2024, 7, 3))

    store = DataStore(tmp_path / "bedrock.db")
    written = store.append_weather(df)
    assert written == 3

    out = store.get_weather("us_cornbelt")
    assert len(out) == 3
    assert out["tmax"].iloc[0] == 30.1
    # gdd forblir NULL i DB
    assert pd.isna(out["gdd"]).all()


def test_fetch_weather_empty_time_array_returns_empty_df() -> None:
    payload = {
        "daily": {
            "time": [],
            "temperature_2m_max": [],
            "temperature_2m_min": [],
            "precipitation_sum": [],
        }
    }
    with patch(
        "bedrock.fetch.weather.http_get_with_retry",
        return_value=_mock_response(payload),
    ):
        df = fetch_weather("x", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty
    assert list(df.columns) == ["region", "date", "tmax", "tmin", "precip", "gdd"]


def test_fetch_weather_missing_daily_block_raises() -> None:
    with (
        patch(
            "bedrock.fetch.weather.http_get_with_retry",
            return_value=_mock_response({"latitude": 0}),
        ),
        pytest.raises(WeatherFetchError, match="missing 'daily'"),
    ):
        fetch_weather("x", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_weather_missing_daily_field_raises() -> None:
    """Hvis Open-Meteo skulle returnere daily uten temperature_2m_max."""
    payload = {
        "daily": {
            "time": ["2024-01-01"],
            "temperature_2m_min": [10.0],
            # temperature_2m_max og precipitation_sum mangler
        }
    }
    with (
        patch(
            "bedrock.fetch.weather.http_get_with_retry",
            return_value=_mock_response(payload),
        ),
        pytest.raises(WeatherFetchError, match="missing daily fields"),
    ):
        fetch_weather("x", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 1))


def test_fetch_weather_http_error_raises() -> None:
    with (
        patch(
            "bedrock.fetch.weather.http_get_with_retry",
            return_value=_mock_response({}, status=400),
        ),
        pytest.raises(WeatherFetchError, match="HTTP 400"),
    ):
        fetch_weather("x", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_weather_network_failure_wrapped() -> None:
    import requests

    with (
        patch(
            "bedrock.fetch.weather.http_get_with_retry",
            side_effect=requests.ConnectionError("refused"),
        ),
        pytest.raises(WeatherFetchError, match="Network failure"),
    ):
        fetch_weather("x", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_weather_hits_correct_url() -> None:
    called = {}

    def capture(url, params=None, **kw):
        called["url"] = url
        return _mock_response(SAMPLE_RESPONSE)

    with patch("bedrock.fetch.weather.http_get_with_retry", side_effect=capture):
        fetch_weather("us", 0.0, 0.0, date(2024, 7, 1), date(2024, 7, 3))

    assert called["url"] == OPEN_METEO_ARCHIVE_URL
    assert "archive-api.open-meteo.com" in called["url"]
