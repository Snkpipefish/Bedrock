"""Tester for ISMA India sugar production fetcher."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from bedrock.fetch.isma_india import (
    SERIES_ID,
    IsmaFetchError,
    fetch_isma_india,
    parse_production_values,
)


def test_parse_extracts_lakh_tonnes() -> None:
    items = [
        {"title": "India sugar production 274.8 lakh tons in 2025-26", "date": "2026-04-17"},
    ]
    df = parse_production_values(items)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 274.8
    assert df.iloc[0]["series_id"] == SERIES_ID
    assert df.iloc[0]["date"] == "2026-04-17"


def test_parse_converts_million_to_lakh() -> None:
    items = [
        {"title": "Sugar output 27.5 million tonnes this season", "date": "2026-03-01"},
    ]
    df = parse_production_values(items)
    assert df.iloc[0]["value"] == pytest.approx(275.0)


def test_parse_filters_unrealistic_values() -> None:
    items = [
        {"title": "Sugar imports 5 lakh tons", "date": "2026-01-01"},  # < 50
        {"title": "Worldwide sugar 999 lakh tons", "date": "2026-01-02"},  # > 500
        {"title": "India 274 lakh tons", "date": "2026-01-03"},  # OK
    ]
    df = parse_production_values(items)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 274.0


def test_parse_dedupes_same_date_with_median() -> None:
    items = [
        {"title": "274.8 lakh tons", "date": "2026-04-17"},
        {"title": "275 lakh tons", "date": "2026-04-17"},
        {"title": "275.2 lakh tons", "date": "2026-04-17"},
    ]
    df = parse_production_values(items)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 275.0  # median


def test_parse_skips_items_without_match() -> None:
    items = [
        {"title": "Ethanol blending update", "date": "2026-01-01"},
        {"title": "Government policy review", "date": "2026-01-02"},
    ]
    df = parse_production_values(items)
    assert df.empty


def test_parse_handles_missing_date() -> None:
    items = [
        {"title": "274.8 lakh tons"},  # no date
        {"title": "100 lakh tons", "date": "2026-04-17"},
    ]
    df = parse_production_values(items)
    assert len(df) == 1


def test_fetch_http_error_raises() -> None:
    response = Mock()
    response.status_code = 500
    response.text = "internal error"
    with patch("bedrock.fetch.isma_india.http_get_with_retry", return_value=response):
        with pytest.raises(IsmaFetchError, match="HTTP 500"):
            fetch_isma_india()


def test_fetch_returns_dataframe_on_success() -> None:
    response = Mock()
    response.status_code = 200
    response.json = Mock(
        return_value={
            "data": [
                {"title": "Sugar 274.8 lakh tons in 2025-26", "date": "2026-04-17"},
            ]
        }
    )
    with patch("bedrock.fetch.isma_india.http_get_with_retry", return_value=response):
        df = fetch_isma_india()
    assert len(df) == 1
    assert df.iloc[0]["value"] == 274.8
