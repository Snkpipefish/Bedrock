"""Tester for Stooq pris-fetcher.

Bruker `unittest.mock.patch` til å stubbe HTTP-kall — ingen live network.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from bedrock.fetch.prices import (
    PriceFetchError,
    build_stooq_url_params,
    fetch_prices,
)

# ---------------------------------------------------------------------------
# URL-bygging
# ---------------------------------------------------------------------------


def test_build_url_params_lowercases_ticker() -> None:
    params = build_stooq_url_params("XAUUSD", date(2024, 1, 2), date(2024, 1, 10))
    assert params["s"] == "xauusd"


def test_build_url_params_formats_dates_as_yyyymmdd() -> None:
    params = build_stooq_url_params("xauusd", date(2024, 1, 2), date(2024, 3, 15))
    assert params["d1"] == "20240102"
    assert params["d2"] == "20240315"


def test_build_url_params_default_interval_is_daily() -> None:
    params = build_stooq_url_params("xauusd", date(2024, 1, 1), date(2024, 1, 2))
    assert params["i"] == "d"


# ---------------------------------------------------------------------------
# fetch_prices med mocked HTTP
# ---------------------------------------------------------------------------


SAMPLE_CSV = """Date,Open,High,Low,Close,Volume
2024-01-02,2060.0,2075.5,2058.0,2072.1,12500
2024-01-03,2072.0,2080.0,2065.0,2068.5,13200
2024-01-04,2068.0,2079.0,2067.2,2077.8,12800
"""


def _mock_response(text: str, status: int = 200) -> Mock:
    m = Mock()
    m.status_code = status
    m.text = text
    return m


def test_fetch_prices_returns_bedrock_shaped_dataframe() -> None:
    with patch("bedrock.fetch.prices.http_get_with_retry", return_value=_mock_response(SAMPLE_CSV)):
        df = fetch_prices("xauusd", date(2024, 1, 2), date(2024, 1, 4))

    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["ts"].iloc[0] == pd.Timestamp("2024-01-02")
    assert df["close"].iloc[0] == 2072.1
    assert df["volume"].iloc[2] == 12800.0


def test_fetch_prices_ts_column_is_datetime() -> None:
    with patch("bedrock.fetch.prices.http_get_with_retry", return_value=_mock_response(SAMPLE_CSV)):
        df = fetch_prices("xauusd", date(2024, 1, 2), date(2024, 1, 4))

    assert pd.api.types.is_datetime64_any_dtype(df["ts"])


def test_fetch_prices_fx_without_volume_column() -> None:
    """Stooq mangler noen ganger Volume for FX — skal gi NaN."""
    csv_no_volume = """Date,Open,High,Low,Close
2024-01-02,1.0950,1.0970,1.0935,1.0962
"""
    with patch(
        "bedrock.fetch.prices.http_get_with_retry",
        return_value=_mock_response(csv_no_volume),
    ):
        df = fetch_prices("eurusd", date(2024, 1, 2), date(2024, 1, 2))

    assert pd.isna(df["volume"].iloc[0])


def test_fetch_prices_empty_response_raises() -> None:
    with patch("bedrock.fetch.prices.http_get_with_retry", return_value=_mock_response("")):
        with pytest.raises(PriceFetchError, match="no data"):
            fetch_prices("badticker", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_prices_no_data_response_raises() -> None:
    with patch("bedrock.fetch.prices.http_get_with_retry", return_value=_mock_response("No data")):
        with pytest.raises(PriceFetchError, match="no data"):
            fetch_prices("badticker", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_prices_http_error_status_raises() -> None:
    with (
        patch(
            "bedrock.fetch.prices.http_get_with_retry",
            return_value=_mock_response("Server error", status=500),
        ),
        pytest.raises(PriceFetchError, match="HTTP 500"),
    ):
        fetch_prices("xauusd", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_prices_malformed_csv_raises() -> None:
    malformed = "not,a,csv\nmissing,columns"
    with (
        patch(
            "bedrock.fetch.prices.http_get_with_retry",
            return_value=_mock_response(malformed),
        ),
        pytest.raises(PriceFetchError, match="missing columns"),
    ):
        fetch_prices("xauusd", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_prices_network_exception_wrapped() -> None:
    import requests

    with (
        patch(
            "bedrock.fetch.prices.http_get_with_retry",
            side_effect=requests.ConnectionError("connection refused"),
        ),
        pytest.raises(PriceFetchError, match="Network failure"),
    ):
        fetch_prices("xauusd", date(2024, 1, 1), date(2024, 1, 2))
