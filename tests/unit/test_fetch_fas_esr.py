"""Tester for FAS ESR-fetcher (sub-fase 12.7 D2 A3, session 133)."""

from __future__ import annotations

from typing import Any

import pytest

from bedrock.data.schemas import FAS_ESR_COLS
from bedrock.fetch.fas_esr import (
    FasFetchError,
    _normalize_record,
    _normalize_week_ending,
    fetch_esr_exports,
)


def _sample_record(**overrides: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "commodityCode": 401,
        "countryCode": 1220,
        "weeklyExports": 34818,
        "accumulatedExports": 34818,
        "outstandingSales": 712440,
        "grossNewSales": 52762,
        "currentMYNetSales": 52762,
        "currentMYTotalCommitment": 747258,
        "nextMYOutstandingSales": 0,
        "nextMYNetSales": 0,
        "unitId": 1,
        "weekEndingDate": "2023-09-07T00:00:00",
    }
    rec.update(overrides)
    return rec


def test_normalize_week_ending_strips_iso_t_suffix() -> None:
    assert _normalize_week_ending("2023-09-07T00:00:00") == "2023-09-07"
    assert _normalize_week_ending("2024-01-15") == "2024-01-15"
    assert _normalize_week_ending(None) is None


def test_normalize_record_maps_camelcase_to_snake() -> None:
    rec = _sample_record()
    norm = _normalize_record(rec, commodity_code=401, market_year=2024)
    assert norm is not None
    assert norm["country_code"] == 1220
    assert norm["weekly_exports"] == 34818.0
    assert norm["current_my_total_commitment"] == 747258.0
    assert norm["next_my_outstanding_sales"] == 0.0
    assert norm["unit_id"] == 1
    assert norm["week_ending_date"] == "2023-09-07"


def test_normalize_record_missing_week_returns_none() -> None:
    rec = _sample_record()
    rec.pop("weekEndingDate")
    assert _normalize_record(rec, commodity_code=401, market_year=2024) is None


def test_normalize_record_missing_country_returns_none() -> None:
    rec = _sample_record()
    rec.pop("countryCode")
    assert _normalize_record(rec, commodity_code=401, market_year=2024) is None


def test_fetch_esr_exports_with_raw_payload() -> None:
    payload = [
        _sample_record(),
        _sample_record(countryCode=2010, weeklyExports=245758),
    ]
    df = fetch_esr_exports(401, 2024, raw_response=payload)
    assert len(df) == 2
    assert list(df.columns) == list(FAS_ESR_COLS)
    assert df["country_code"].tolist() == [1220, 2010]
    assert df["commodity_code"].iloc[0] == 401
    assert df["market_year"].iloc[0] == 2024


def test_fetch_esr_exports_handles_invalid_records() -> None:
    """Records uten weekEndingDate hoppes over uten å feile."""
    payload: list[Any] = [
        _sample_record(),
        {"weeklyExports": 100},  # mangler week + country
        "not-a-dict",
        _sample_record(countryCode=2010),
    ]
    df = fetch_esr_exports(401, 2024, raw_response=payload)
    assert len(df) == 2


def test_fetch_esr_exports_non_list_payload_raises() -> None:
    with pytest.raises(FasFetchError, match="expected JSON list"):
        fetch_esr_exports(401, 2024, raw_response={"data": []})


def test_fetch_esr_exports_empty_payload_returns_empty_df() -> None:
    df = fetch_esr_exports(401, 2024, raw_response=[])
    assert df.empty
    assert list(df.columns) == list(FAS_ESR_COLS)
