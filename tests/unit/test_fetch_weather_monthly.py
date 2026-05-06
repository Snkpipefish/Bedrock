"""Tester for Open-Meteo månedlig vær-fetcher (Brazil Centro-Sul backfill)."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from bedrock.fetch.weather_monthly import (
    WeatherMonthlyFetchError,
    aggregate_to_monthly,
    fetch_weather_monthly,
)


def _make_payload(days: int, *, tmax_const: float = 30.0, precip_const: float = 5.0) -> dict:
    """Bygg syntetisk Open-Meteo-respons for `days` etterfølgende dager fra 2024-01-01."""
    times = [f"2024-01-{d:02d}" for d in range(1, days + 1)]
    return {
        "daily": {
            "time": times,
            "temperature_2m_max": [tmax_const] * days,
            "temperature_2m_min": [tmax_const - 10.0] * days,
            "precipitation_sum": [precip_const] * days,
            "et0_fao_evapotranspiration": [3.0] * days,
        }
    }


# ---------------------------------------------------------------------------
# Aggregering
# ---------------------------------------------------------------------------


def test_aggregate_full_month_yields_one_row() -> None:
    df = aggregate_to_monthly(_make_payload(31), "test_region")
    assert len(df) == 1
    assert df.iloc[0]["region"] == "test_region"
    assert df.iloc[0]["month"] == "2024-01"


def test_aggregate_partial_month_dropped() -> None:
    df = aggregate_to_monthly(_make_payload(20), "test_region")
    assert df.empty


def test_aggregate_temp_mean_max_correct() -> None:
    payload = _make_payload(31, tmax_const=30.0)
    df = aggregate_to_monthly(payload, "r")
    row = df.iloc[0]
    assert row["temp_mean"] == pytest.approx(25.0, abs=0.01)  # (30+20)/2
    assert row["temp_max"] == 30.0


def test_aggregate_precip_sum_and_water_bal() -> None:
    payload = _make_payload(31, precip_const=2.0)
    df = aggregate_to_monthly(payload, "r")
    row = df.iloc[0]
    assert row["precip_mm"] == pytest.approx(62.0)
    assert row["et0_mm"] == pytest.approx(93.0)  # 31 * 3.0
    assert row["water_bal"] == pytest.approx(-31.0)


def test_aggregate_hot_dry_wet_day_thresholds() -> None:
    # tmax=33 → hot. precip=5 → not dry, not wet (mellom 1 og 10).
    payload = _make_payload(31, tmax_const=33.0, precip_const=5.0)
    df = aggregate_to_monthly(payload, "r")
    row = df.iloc[0]
    assert row["hot_days"] == 31
    assert row["dry_days"] == 0
    assert row["wet_days"] == 0


def test_aggregate_dry_days_when_below_1mm() -> None:
    payload = _make_payload(31, precip_const=0.5)
    df = aggregate_to_monthly(payload, "r")
    assert df.iloc[0]["dry_days"] == 31


def test_aggregate_wet_days_when_at_or_above_10mm() -> None:
    payload = _make_payload(31, precip_const=10.0)
    df = aggregate_to_monthly(payload, "r")
    assert df.iloc[0]["wet_days"] == 31


def test_aggregate_missing_daily_block_raises() -> None:
    with pytest.raises(WeatherMonthlyFetchError, match="missing 'daily'"):
        aggregate_to_monthly({"hourly": {}}, "r")


def test_aggregate_missing_required_field_raises() -> None:
    bad = {"daily": {"time": [], "temperature_2m_max": []}}
    with pytest.raises(WeatherMonthlyFetchError, match="missing daily fields"):
        aggregate_to_monthly(bad, "r")


def test_aggregate_empty_time_returns_empty_df() -> None:
    payload = {
        "daily": {
            "time": [],
            "temperature_2m_max": [],
            "temperature_2m_min": [],
            "precipitation_sum": [],
            "et0_fao_evapotranspiration": [],
        }
    }
    df = aggregate_to_monthly(payload, "r")
    assert df.empty


# ---------------------------------------------------------------------------
# fetch_weather_monthly med mocked HTTP
# ---------------------------------------------------------------------------


def test_fetch_returns_aggregated_dataframe() -> None:
    from datetime import date

    response = Mock()
    response.status_code = 200
    response.json = Mock(return_value=_make_payload(31))

    with patch("bedrock.fetch.weather_monthly.http_get_with_retry", return_value=response):
        df = fetch_weather_monthly(
            "brazil_centro_sul", -21.18, -47.81, date(2024, 1, 1), date(2024, 1, 31)
        )

    assert len(df) == 1
    assert df.iloc[0]["region"] == "brazil_centro_sul"


def test_fetch_http_error_raises() -> None:
    from datetime import date

    response = Mock()
    response.status_code = 500
    response.text = "internal error"

    with patch("bedrock.fetch.weather_monthly.http_get_with_retry", return_value=response):
        with pytest.raises(WeatherMonthlyFetchError, match="HTTP 500"):
            fetch_weather_monthly("r", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 31))


def test_fetch_network_failure_raises() -> None:
    from datetime import date

    with patch(
        "bedrock.fetch.weather_monthly.http_get_with_retry",
        side_effect=RuntimeError("connection refused"),
    ):
        with pytest.raises(WeatherMonthlyFetchError, match="Network failure"):
            fetch_weather_monthly("r", 0.0, 0.0, date(2024, 1, 1), date(2024, 1, 31))
