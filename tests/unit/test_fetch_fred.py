"""Tester for FRED observations-fetcher."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from bedrock.fetch.fred import (
    FRED_OBSERVATIONS_URL,
    FredFetchError,
    build_fred_params,
    fetch_fred_series,
)


# ---------------------------------------------------------------------------
# Query-bygging
# ---------------------------------------------------------------------------


def test_build_params_includes_series_id_key_dates_filetype() -> None:
    params = build_fred_params("DGS10", "my_key", date(2020, 1, 1), date(2024, 12, 31))
    assert params["series_id"] == "DGS10"
    assert params["api_key"] == "my_key"
    assert params["file_type"] == "json"
    assert params["observation_start"] == "2020-01-01"
    assert params["observation_end"] == "2024-12-31"


def test_build_params_default_limit_is_max() -> None:
    params = build_fred_params("X", "K", date(2020, 1, 1), date(2020, 1, 2))
    assert int(params["limit"]) >= 100_000


# ---------------------------------------------------------------------------
# fetch_fred_series med mocked HTTP
# ---------------------------------------------------------------------------


SAMPLE_FRED_RESPONSE = {
    "realtime_start": "2024-01-01",
    "realtime_end": "2024-01-01",
    "observation_start": "2024-01-01",
    "observation_end": "2024-01-05",
    "count": 3,
    "observations": [
        {"realtime_start": "2024", "realtime_end": "2024", "date": "2024-01-02", "value": "3.95"},
        {"realtime_start": "2024", "realtime_end": "2024", "date": "2024-01-03", "value": "."},
        {"realtime_start": "2024", "realtime_end": "2024", "date": "2024-01-04", "value": "4.01"},
    ],
}


def _mock_response(payload, status: int = 200) -> Mock:
    m = Mock()
    m.status_code = status
    m.text = str(payload)[:500]
    m.json = Mock(return_value=payload)
    return m


def test_fetch_fred_returns_bedrock_schema() -> None:
    with patch(
        "bedrock.fetch.fred.http_get_with_retry",
        return_value=_mock_response(SAMPLE_FRED_RESPONSE),
    ):
        df = fetch_fred_series("DGS10", "my_key", date(2024, 1, 1), date(2024, 1, 5))

    assert list(df.columns) == ["series_id", "date", "value"]
    assert len(df) == 3
    assert df["series_id"].iloc[0] == "DGS10"
    assert df["date"].iloc[0] == "2024-01-02"


def test_fetch_fred_converts_dot_to_nan() -> None:
    """FRED's '.' marker for manglende observasjon → NaN i Bedrock."""
    with patch(
        "bedrock.fetch.fred.http_get_with_retry",
        return_value=_mock_response(SAMPLE_FRED_RESPONSE),
    ):
        df = fetch_fred_series("DGS10", "my_key", date(2024, 1, 1), date(2024, 1, 5))

    assert df["value"].iloc[0] == 3.95
    assert pd.isna(df["value"].iloc[1])  # "." → NaN
    assert df["value"].iloc[2] == 4.01


def test_fetch_fred_end_to_end_matches_datastore(tmp_path) -> None:
    """Fetcher-output skal passere direkte til DataStore.append_fundamentals."""
    from bedrock.data.store import DataStore

    with patch(
        "bedrock.fetch.fred.http_get_with_retry",
        return_value=_mock_response(SAMPLE_FRED_RESPONSE),
    ):
        df = fetch_fred_series("DGS10", "my_key", date(2024, 1, 1), date(2024, 1, 5))

    store = DataStore(tmp_path / "bedrock.db")
    store.append_fundamentals(df)

    out = store.get_fundamentals("DGS10")
    assert len(out) == 3
    assert out.iloc[0] == 3.95
    assert pd.isna(out.iloc[1])


def test_fetch_fred_empty_observations_returns_empty_df() -> None:
    empty = {"observations": []}
    with patch(
        "bedrock.fetch.fred.http_get_with_retry", return_value=_mock_response(empty)
    ):
        df = fetch_fred_series("X", "K", date(2024, 1, 1), date(2024, 1, 2))
    assert df.empty
    assert list(df.columns) == ["series_id", "date", "value"]


def test_fetch_fred_missing_observations_block_raises() -> None:
    bad = {"error_message": "something"}
    with patch(
        "bedrock.fetch.fred.http_get_with_retry", return_value=_mock_response(bad)
    ):
        with pytest.raises(FredFetchError, match="missing 'observations'"):
            fetch_fred_series("X", "K", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_fred_missing_date_or_value_in_row_raises() -> None:
    bad = {"observations": [{"realtime_start": "2024", "realtime_end": "2024"}]}
    with patch(
        "bedrock.fetch.fred.http_get_with_retry", return_value=_mock_response(bad)
    ):
        with pytest.raises(FredFetchError, match="missing 'date' or 'value'"):
            fetch_fred_series("X", "K", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_fred_http_error_includes_body_preview() -> None:
    err_body = '{"error_code":400,"error_message":"Bad Request. The value for variable api_key is not registered."}'
    m = Mock()
    m.status_code = 400
    m.text = err_body
    m.json = Mock(return_value={"error_message": "invalid key"})

    with patch("bedrock.fetch.fred.http_get_with_retry", return_value=m):
        with pytest.raises(FredFetchError, match="HTTP 400"):
            fetch_fred_series("X", "bad_key", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_fred_network_failure_wrapped() -> None:
    import requests

    with patch(
        "bedrock.fetch.fred.http_get_with_retry",
        side_effect=requests.ConnectionError("refused"),
    ):
        with pytest.raises(FredFetchError, match="Network failure"):
            fetch_fred_series("X", "K", date(2024, 1, 1), date(2024, 1, 2))


def test_fetch_fred_hits_correct_url() -> None:
    called = {}

    def capture(url, params=None, **kwargs):  # noqa: ARG001
        called["url"] = url
        return _mock_response(SAMPLE_FRED_RESPONSE)

    with patch("bedrock.fetch.fred.http_get_with_retry", side_effect=capture):
        fetch_fred_series("DGS10", "K", date(2024, 1, 1), date(2024, 1, 5))

    assert called["url"] == FRED_OBSERVATIONS_URL
    assert "stlouisfed.org" in called["url"]
