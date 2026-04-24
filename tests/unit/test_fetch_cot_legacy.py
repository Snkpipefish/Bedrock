"""Tester for CFTC Legacy COT-fetcher.

Disaggregated-fetcher er testet i test_fetch_cot_cftc.py. Her fokuserer vi
på det som er spesifikt for legacy-rapporten: andre Socrata-feltnavn, annet
URL, og at Bedrock-schema får legacy-kolonner (noncomm_* i stedet for
mm_*/other_*).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from bedrock.fetch.cot_cftc import CFTC_LEGACY_URL, CotFetchError, fetch_cot_legacy


SAMPLE_LEGACY_ROWS = [
    {
        "report_date_as_yyyy_mm_dd": "2020-01-07T00:00:00.000",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "noncomm_positions_long_all": "180000",
        "noncomm_positions_short_all": "65000",
        "comm_positions_long_all": "200000",
        "comm_positions_short_all": "300000",
        "nonrept_positions_long_all": "9000",
        "nonrept_positions_short_all": "4000",
        "open_interest_all": "520000",
    },
    {
        "report_date_as_yyyy_mm_dd": "2020-01-14T00:00:00.000",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "noncomm_positions_long_all": "182000",
        "noncomm_positions_short_all": "66000",
        "comm_positions_long_all": "201000",
        "comm_positions_short_all": "302000",
        "nonrept_positions_long_all": "9100",
        "nonrept_positions_short_all": "4050",
        "open_interest_all": "530000",
    },
]


def _mock_response(payload, status: int = 200) -> Mock:
    m = Mock()
    m.status_code = status
    m.text = str(payload)[:500]
    m.json = Mock(return_value=payload)
    return m


def test_fetch_cot_legacy_returns_legacy_schema() -> None:
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_LEGACY_ROWS),
    ):
        df = fetch_cot_legacy(
            "GOLD - COMMODITY EXCHANGE INC.", date(2020, 1, 1), date(2020, 1, 31)
        )

    # Legacy har noncomm_*, ikke mm_*/other_*
    assert list(df.columns) == [
        "report_date",
        "contract",
        "noncomm_long",
        "noncomm_short",
        "comm_long",
        "comm_short",
        "nonrep_long",
        "nonrep_short",
        "open_interest",
    ]
    assert len(df) == 2
    assert df["noncomm_long"].iloc[0] == 180000


def test_fetch_cot_legacy_uses_legacy_url() -> None:
    """Verifiser at fetcher treffer legacy-datasettet, ikke disaggregated."""
    called_url = {}

    def capture(url, params=None, **kwargs):  # noqa: ARG001
        called_url["url"] = url
        return _mock_response(SAMPLE_LEGACY_ROWS)

    with patch("bedrock.fetch.cot_cftc.http_get_with_retry", side_effect=capture):
        fetch_cot_legacy("x", date(2020, 1, 1), date(2020, 1, 15))

    assert called_url["url"] == CFTC_LEGACY_URL
    assert "6dca-aqww" in called_url["url"]


def test_fetch_cot_legacy_end_to_end_matches_datastore(tmp_path) -> None:
    """Fetcher-output skal passere direkte til DataStore.append_cot_legacy."""
    from bedrock.data.store import DataStore

    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_LEGACY_ROWS),
    ):
        df = fetch_cot_legacy(
            "GOLD - COMMODITY EXCHANGE INC.", date(2020, 1, 1), date(2020, 1, 31)
        )

    store = DataStore(tmp_path / "bedrock.db")
    written = store.append_cot_legacy(df)
    assert written == 2

    out = store.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="legacy")
    assert len(out) == 2
    assert out["noncomm_long"].iloc[0] == 180000
    # Disaggregated-tabellen skal fortsatt være tom
    assert not store.has_cot("GOLD - COMMODITY EXCHANGE INC.", report="disaggregated")


def test_fetch_cot_legacy_empty_response() -> None:
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry", return_value=_mock_response([])
    ):
        df = fetch_cot_legacy("UNKNOWN", date(2020, 1, 1), date(2020, 1, 15))
    assert df.empty
    # Kolonner er legacy-sett, ikke disaggregated
    assert "noncomm_long" in df.columns
    assert "mm_long" not in df.columns


def test_fetch_cot_legacy_missing_fields_raises() -> None:
    """Hvis legacy-respons mangler legacy-felter (f.eks. får disagg-felter)."""
    bad = [
        {
            "report_date_as_yyyy_mm_dd": "2020-01-07",
            "market_and_exchange_names": "x",
            "m_money_positions_long": "100",  # disagg-felt, ikke legacy
        }
    ]
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry", return_value=_mock_response(bad)
    ):
        with pytest.raises(CotFetchError, match="missing fields"):
            fetch_cot_legacy("x", date(2020, 1, 1), date(2020, 1, 15))


def test_fetch_cot_legacy_string_numbers_converted_to_int() -> None:
    with patch(
        "bedrock.fetch.cot_cftc.http_get_with_retry",
        return_value=_mock_response(SAMPLE_LEGACY_ROWS),
    ):
        df = fetch_cot_legacy("x", date(2020, 1, 1), date(2020, 1, 15))

    assert df["noncomm_long"].dtype == "int64"
    assert df["comm_short"].dtype == "int64"
