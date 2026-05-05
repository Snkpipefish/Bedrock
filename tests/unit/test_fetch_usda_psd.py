"""Tester for USDA FAS PSD fetcher."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from bedrock.fetch.usda_psd import (
    ATTR_EXPORTS,
    ATTR_PRODUCTION,
    UsdaPsdFetchError,
    fetch_india_sugar_history,
    fetch_psd_country_year,
)


def _mock_response(status: int = 200, payload=None, text: str = "") -> Mock:
    r = Mock()
    r.status_code = status
    r.json = Mock(return_value=payload or [])
    r.text = text
    return r


def test_fetch_year_returns_records() -> None:
    payload = [
        {"attributeId": ATTR_PRODUCTION, "value": 26574.0, "marketYear": "2010"},
        {"attributeId": ATTR_EXPORTS, "value": 1187.0, "marketYear": "2010"},
    ]
    with patch(
        "bedrock.fetch.usda_psd.http_get_with_retry",
        return_value=_mock_response(payload=payload),
    ), patch("bedrock.fetch.usda_psd._get_api_key", return_value="key"):
        records = fetch_psd_country_year("0612000", "IN", 2010)
    assert len(records) == 2
    assert records[0]["value"] == 26574.0


def test_fetch_year_http_error_raises() -> None:
    with patch(
        "bedrock.fetch.usda_psd.http_get_with_retry",
        return_value=_mock_response(status=500, text="error"),
    ), patch("bedrock.fetch.usda_psd._get_api_key", return_value="key"):
        with pytest.raises(UsdaPsdFetchError, match="HTTP 500"):
            fetch_psd_country_year("0612000", "IN", 2010)


def test_fetch_year_unexpected_shape_raises() -> None:
    with patch(
        "bedrock.fetch.usda_psd.http_get_with_retry",
        return_value=_mock_response(payload={"error": "x"}),
    ), patch("bedrock.fetch.usda_psd._get_api_key", return_value="key"):
        with pytest.raises(UsdaPsdFetchError, match="Unexpected response"):
            fetch_psd_country_year("0612000", "IN", 2010)


def test_india_history_aggregates_multiple_years() -> None:
    def _resp(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        year = int(url.rsplit("/", 1)[-1])
        return _mock_response(
            payload=[
                {
                    "attributeId": ATTR_PRODUCTION,
                    "value": 26000 + year,
                    "marketYear": str(year),
                },
                {
                    "attributeId": ATTR_EXPORTS,
                    "value": 1000 + year,
                    "marketYear": str(year),
                },
            ]
        )

    with patch("bedrock.fetch.usda_psd.http_get_with_retry", side_effect=_resp), patch(
        "bedrock.fetch.usda_psd._get_api_key", return_value="key"
    ), patch("time.sleep"):
        df = fetch_india_sugar_history(from_year=2020, to_year=2022)

    assert len(df) == 6  # 2 attrs × 3 years
    prod = df[df["series_id"] == "USDA_PSD_INDIA_SUGAR_PROD_KMT"]
    assert len(prod) == 3
    assert prod.iloc[0]["date"] == "2020-10-01"


def test_get_api_key_uses_env() -> None:
    with patch("bedrock.fetch.usda_psd.get_secret", return_value="env-key"):
        from bedrock.fetch.usda_psd import _get_api_key

        assert _get_api_key() == "env-key"


def test_get_api_key_raises_if_none() -> None:
    with patch("bedrock.fetch.usda_psd.get_secret", return_value=None):
        from bedrock.fetch.usda_psd import _get_api_key

        with pytest.raises(UsdaPsdFetchError, match="USDA API key not found"):
            _get_api_key()
