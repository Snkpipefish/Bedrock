"""Tester for CFTC COT Socrata-fetcher."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from bedrock.fetch.cot_cftc import (
    CotFetchError,
    build_socrata_query,
    fetch_cot_disaggregated,
)


# ---------------------------------------------------------------------------
# Query-bygging
# ---------------------------------------------------------------------------


def test_build_query_has_where_order_limit() -> None:
    params = build_socrata_query(
        "GOLD - COMMODITY EXCHANGE INC.", date(2020, 1, 1), date(2024, 12, 31)
    )
    assert "$where" in params
    assert "$order" in params
    assert "$limit" in params


def test_build_query_contract_and_dates_in_where_clause() -> None:
    params = build_socrata_query(
        "GOLD - COMMODITY EXCHANGE INC.", date(2020, 1, 1), date(2024, 12, 31)
    )
    where = params["$where"]
    assert "GOLD - COMMODITY EXCHANGE INC." in where
    assert "2020-01-01" in where
    assert "2024-12-31" in where


def test_build_query_order_ascending_by_report_date() -> None:
    params = build_socrata_query("X", date(2020, 1, 1), date(2020, 1, 2))
    assert "ASC" in params["$order"].upper()
    assert "report_date_as_yyyy_mm_dd" in params["$order"]


# ---------------------------------------------------------------------------
# fetch_cot_disaggregated med mocked HTTP
# ---------------------------------------------------------------------------


SAMPLE_SOCRATA_ROWS = [
    {
        "report_date_as_yyyy_mm_dd": "2024-01-02T00:00:00.000",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "m_money_positions_long": "150000",
        "m_money_positions_short": "60000",
        "other_rept_positions_long": "30000",
        "other_rept_positions_short": "25000",
        "prod_merc_positions_long": "200000",
        "prod_merc_positions_short": "300000",
        "nonrept_positions_long_all": "8000",
        "nonrept_positions_short_all": "3000",
        "open_interest_all": "500000",
    },
    {
        "report_date_as_yyyy_mm_dd": "2024-01-09T00:00:00.000",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "m_money_positions_long": "152000",
        "m_money_positions_short": "61000",
        "other_rept_positions_long": "30500",
        "other_rept_positions_short": "25500",
        "prod_merc_positions_long": "201000",
        "prod_merc_positions_short": "302000",
        "nonrept_positions_long_all": "8100",
        "nonrept_positions_short_all": "3050",
        "open_interest_all": "510000",
    },
]


def _mock_response(payload, status: int = 200) -> Mock:
    m = Mock()
    m.status_code = status
    m.text = str(payload)[:500]
    m.json = Mock(return_value=payload)
    return m


def test_fetch_cot_disaggregated_returns_bedrock_schema(tmp_path) -> None:  # noqa: ARG001
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_SOCRATA_ROWS),
    ):
        df = fetch_cot_disaggregated(
            "GOLD - COMMODITY EXCHANGE INC.", date(2024, 1, 1), date(2024, 1, 15)
        )

    assert list(df.columns) == [
        "report_date",
        "contract",
        "mm_long",
        "mm_short",
        "other_long",
        "other_short",
        "comm_long",
        "comm_short",
        "nonrep_long",
        "nonrep_short",
        "open_interest",
    ]
    assert len(df) == 2
    assert df["report_date"].iloc[0] == "2024-01-02"
    assert df["mm_long"].iloc[0] == 150000
    assert df["open_interest"].iloc[1] == 510000


def test_fetch_cot_disaggregated_matches_datastore_schema(tmp_path) -> None:
    """End-to-end: fetch -> DataStore.append_cot_disaggregated uten manipulering."""
    from bedrock.data.store import DataStore

    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_SOCRATA_ROWS),
    ):
        df = fetch_cot_disaggregated(
            "GOLD - COMMODITY EXCHANGE INC.", date(2024, 1, 1), date(2024, 1, 15)
        )

    store = DataStore(tmp_path / "bedrock.db")
    written = store.append_cot_disaggregated(df)
    assert written == 2

    out = store.get_cot("GOLD - COMMODITY EXCHANGE INC.")
    assert len(out) == 2
    assert out["mm_long"].iloc[0] == 150000


def test_fetch_cot_converts_string_numbers_to_int() -> None:
    """Socrata returnerer ofte alle tall som streng. Bedrock-schema krever int."""
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_SOCRATA_ROWS),
    ):
        df = fetch_cot_disaggregated("x", date(2024, 1, 1), date(2024, 1, 15))

    assert df["mm_long"].dtype == "int64"
    assert df["open_interest"].dtype == "int64"


def test_fetch_cot_empty_response_returns_empty_frame() -> None:
    """Tom Socrata-liste = tom DataFrame med riktig skjema. Ingen exception."""
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry", return_value=_mock_response([])
    ):
        df = fetch_cot_disaggregated("UNKNOWN", date(2024, 1, 1), date(2024, 1, 15))
    assert df.empty
    assert "mm_long" in df.columns


def test_fetch_cot_missing_fields_raises() -> None:
    """Hvis Socrata-respons mangler forventede felter, kast CotFetchError."""
    bad_rows = [{"report_date_as_yyyy_mm_dd": "2024-01-02", "market_and_exchange_names": "X"}]
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry", return_value=_mock_response(bad_rows)
    ):
        with pytest.raises(CotFetchError, match="missing fields"):
            fetch_cot_disaggregated("X", date(2024, 1, 1), date(2024, 1, 15))


def test_fetch_cot_http_error_raises() -> None:
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response([], status=503),
    ):
        with pytest.raises(CotFetchError, match="HTTP 503"):
            fetch_cot_disaggregated("X", date(2024, 1, 1), date(2024, 1, 15))


def test_fetch_cot_non_list_json_raises() -> None:
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response({"error": "server down"}),
    ):
        with pytest.raises(CotFetchError, match="non-list"):
            fetch_cot_disaggregated("X", date(2024, 1, 1), date(2024, 1, 15))


def test_fetch_cot_network_failure_wrapped() -> None:
    import requests

    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        side_effect=requests.Timeout("timeout"),
    ):
        with pytest.raises(CotFetchError, match="Network failure"):
            fetch_cot_disaggregated("X", date(2024, 1, 1), date(2024, 1, 15))


def test_fetch_cot_trims_iso_timestamp_to_date() -> None:
    """Socrata gir `2024-01-02T00:00:00.000` — vi lagrer bare dato-delen."""
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_SOCRATA_ROWS),
    ):
        df = fetch_cot_disaggregated("x", date(2024, 1, 1), date(2024, 1, 15))

    # Ingen T-tidsdel etter normalisering
    assert "T" not in df["report_date"].iloc[0]
    assert df["report_date"].iloc[0] == "2024-01-02"
