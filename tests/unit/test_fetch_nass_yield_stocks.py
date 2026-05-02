# pyright: reportArgumentType=false
"""Tester for NASS yield + grain_stocks fetchers (sub-fase 12.10 follow-up Spor D, session 137)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bedrock.data.schemas import NASS_GRAIN_STOCKS_COLS, NASS_YIELD_COLS
from bedrock.fetch.nass import (
    _parse_stocks_category,
    fetch_nass_grain_stocks_api,
    fetch_nass_yield_api,
)

# ---------------------------------------------------------------------------
# _parse_stocks_category
# ---------------------------------------------------------------------------


def test_parse_stocks_total() -> None:
    assert _parse_stocks_category("CORN, GRAIN - STOCKS, MEASURED IN BU") == "TOTAL"


def test_parse_stocks_on_farm() -> None:
    assert _parse_stocks_category("CORN, ON FARM, GRAIN - STOCKS, MEASURED IN BU") == "ON FARM"


def test_parse_stocks_off_farm() -> None:
    assert _parse_stocks_category("CORN, OFF FARM, GRAIN - STOCKS, MEASURED IN BU") == "OFF FARM"


def test_parse_stocks_default_total_for_unknown() -> None:
    assert _parse_stocks_category("WHEAT, ALL CLASSES, GRAIN - STOCKS") == "TOTAL"


# ---------------------------------------------------------------------------
# fetch_nass_yield_api
# ---------------------------------------------------------------------------


def _yield_response_payload(commodity: str, year: int) -> dict:
    """Minimal mock-payload modellert etter live NASS-respons."""
    return {
        "data": [
            {
                "commodity_desc": commodity,
                "year": year,
                "reference_period_desc": "YEAR",
                "Value": "175.5",
                "unit_desc": "BU / ACRE",
                "util_practice_desc": "GRAIN",
                "load_time": f"{year + 1}-01-12 12:00:00.000",
            },
            {
                "commodity_desc": commodity,
                "year": year,
                "reference_period_desc": "YEAR - AUG FORECAST",
                "Value": "172.0",
                "unit_desc": "BU / ACRE",
                "util_practice_desc": "GRAIN",
                "load_time": f"{year}-08-12 12:00:00.000",
            },
        ]
    }


def test_yield_api_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    monkeypatch.setattr("bedrock.fetch.nass.get_secret", lambda _: None)
    with pytest.raises(ValueError, match="BEDROCK_NASS_API_KEY"):
        fetch_nass_yield_api(commodities=["CORN"], years=[2023])


def test_yield_api_skips_unknown_commodity() -> None:
    """RICE har ingen unit_desc-mapping → skippes med warning, ikke raise."""
    df = fetch_nass_yield_api(commodities=["RICE"], years=[2023], api_key="fake")
    assert df.empty
    assert list(df.columns) == list(NASS_YIELD_COLS)


def test_yield_api_parses_response() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _yield_response_payload("CORN", 2023)
    mock_resp.raise_for_status = MagicMock()

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_yield_api(commodities=["CORN"], years=[2023], api_key="fake")

    assert len(df) == 2
    assert list(df.columns) == list(NASS_YIELD_COLS)
    assert (df["commodity"] == "CORN").all()
    final_row = df[df["reference_period"] == "YEAR"]
    assert len(final_row) == 1
    assert final_row["yield_value"].iloc[0] == 175.5


def test_yield_api_skips_invalid_value() -> None:
    payload = {
        "data": [
            {
                "year": 2023,
                "reference_period_desc": "YEAR",
                "Value": "(NA)",
                "unit_desc": "BU / ACRE",
            },
            {
                "year": 2023,
                "reference_period_desc": "YEAR - SEP FORECAST",
                "Value": "abc",
                "unit_desc": "BU / ACRE",
            },
            {
                "year": 2023,
                "reference_period_desc": "YEAR - OCT FORECAST",
                "Value": "173.5",
                "unit_desc": "BU / ACRE",
                "util_practice_desc": "GRAIN",
                "load_time": "2023-10-12 12:00:00.000",
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_yield_api(commodities=["CORN"], years=[2023], api_key="fake")

    # Bare den gyldige raden går igjennom.
    assert len(df) == 1
    assert df["yield_value"].iloc[0] == 173.5


def test_yield_api_handles_http_error() -> None:
    """En HTTP-error skal logges og hoppes over, ikke raises."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_yield_api(commodities=["CORN"], years=[2023], api_key="fake")
    assert df.empty


def test_yield_api_cotton_uses_lb_per_acre() -> None:
    captured: dict = {}

    def _capture(*args, **kw):
        captured["params"] = kw.get("params")
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"data": []}
        mock.raise_for_status = MagicMock()
        return mock

    with patch("bedrock.fetch.nass.requests.get", side_effect=_capture):
        fetch_nass_yield_api(commodities=["COTTON"], years=[2023], api_key="fake")

    assert captured["params"]["unit_desc"] == "LB / ACRE"


# ---------------------------------------------------------------------------
# fetch_nass_grain_stocks_api
# ---------------------------------------------------------------------------


def _stocks_response_payload(commodity: str, year: int) -> dict:
    return {
        "data": [
            {
                "year": year,
                "reference_period_desc": "FIRST OF MAR",
                "short_desc": f"{commodity}, GRAIN - STOCKS, MEASURED IN BU",
                "Value": "7,000,000,000",
                "load_time": f"{year}-04-01 12:00:00.000",
            },
            {
                "year": year,
                "reference_period_desc": "FIRST OF MAR",
                "short_desc": f"{commodity}, ON FARM, GRAIN - STOCKS, MEASURED IN BU",
                "Value": "3,000,000,000",
                "load_time": f"{year}-04-01 12:00:00.000",
            },
            {
                "year": year,
                "reference_period_desc": "FIRST OF MAR",
                "short_desc": f"{commodity}, OFF FARM, GRAIN - STOCKS, MEASURED IN BU",
                "Value": "4,000,000,000",
                "load_time": f"{year}-04-01 12:00:00.000",
            },
        ]
    }


def test_stocks_api_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    monkeypatch.setattr("bedrock.fetch.nass.get_secret", lambda _: None)
    with pytest.raises(ValueError, match="BEDROCK_NASS_API_KEY"):
        fetch_nass_grain_stocks_api(commodities=["CORN"], years=[2023])


def test_stocks_api_skips_unsupported_commodity() -> None:
    df = fetch_nass_grain_stocks_api(commodities=["COTTON"], years=[2023], api_key="fake")
    assert df.empty
    assert list(df.columns) == list(NASS_GRAIN_STOCKS_COLS)


def test_stocks_api_parses_response() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _stocks_response_payload("CORN", 2023)
    mock_resp.raise_for_status = MagicMock()

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_grain_stocks_api(commodities=["CORN"], years=[2023], api_key="fake")

    assert len(df) == 3
    cats = sorted(df["category"].tolist())
    assert cats == ["OFF FARM", "ON FARM", "TOTAL"]
    total_row = df[df["category"] == "TOTAL"]
    assert total_row["stocks_bu"].iloc[0] == 7_000_000_000.0


def test_stocks_api_filters_non_quarterly_periods() -> None:
    """Annual/MARKETING YEAR-rader skal hoppes over (kun FIRST OF *)."""
    payload = {
        "data": [
            {
                "year": 2023,
                "reference_period_desc": "MARKETING YEAR",
                "short_desc": "CORN, GRAIN - STOCKS, MEASURED IN BU",
                "Value": "1,000",
                "load_time": "2023-01-01 12:00:00.000",
            },
            {
                "year": 2023,
                "reference_period_desc": "FIRST OF JUN",
                "short_desc": "CORN, GRAIN - STOCKS, MEASURED IN BU",
                "Value": "5,000,000,000",
                "load_time": "2023-06-30 12:00:00.000",
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_grain_stocks_api(commodities=["CORN"], years=[2023], api_key="fake")

    assert len(df) == 1
    assert df["reference_period"].iloc[0] == "FIRST OF JUN"


def test_stocks_api_handles_http_error() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

    with patch("bedrock.fetch.nass.requests.get", return_value=mock_resp):
        df = fetch_nass_grain_stocks_api(commodities=["CORN"], years=[2023], api_key="fake")
    assert df.empty
