"""Tester for Yahoo Finance pris-fetcher (Fase 10 session 58).

Port av cot-explorers build_price_history.py — bruker statisk fixture
istedenfor ekte HTTP. Dekker:
- URL-bygging med epoch-konvertering
- parse_yahoo_chart: normalfall + kanteilfeller (None-close, mangelende
  felt, tom result, error-blokk)
- fetch_yahoo_prices: HTTP-mock + URLError-håndtering
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.fetch.yahoo import (
    YAHOO_CHART_URL,
    YahooFetchError,
    build_yahoo_url,
    fetch_yahoo_prices,
    parse_yahoo_chart,
)

# ---------------------------------------------------------------------
# build_yahoo_url
# ---------------------------------------------------------------------


def test_build_url_basic() -> None:
    url = build_yahoo_url("GC=F", date(2010, 1, 1), date(2010, 1, 31))
    assert url.startswith(YAHOO_CHART_URL)
    assert "GC%3DF" in url  # = encoded
    assert "interval=1d" in url
    assert "period1=" in url
    assert "period2=" in url


def test_build_url_includes_endpoint_inclusive() -> None:
    """to_date skal inkluderes (period2 = to_date + 86400)."""
    url = build_yahoo_url("GC=F", date(2010, 1, 1), date(2010, 1, 1))
    p1 = int(datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp())
    p2 = p1 + 86400
    assert f"period1={p1}" in url
    assert f"period2={p2}" in url


def test_build_url_weekly_interval() -> None:
    url = build_yahoo_url("GC=F", date(2010, 1, 1), date(2020, 1, 1), interval="1wk")
    assert "interval=1wk" in url


# ---------------------------------------------------------------------
# parse_yahoo_chart
# ---------------------------------------------------------------------


def _yahoo_response(
    timestamps: list[int],
    closes: list[float | None],
    opens: list[float | None] | None = None,
    volumes: list[int | None] | None = None,
) -> dict:
    n = len(timestamps)
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens or [None] * n,
                                "high": [None] * n,
                                "low": [None] * n,
                                "close": closes,
                                "volume": volumes or [None] * n,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_parse_basic() -> None:
    ts = [
        int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp()),
        int(datetime(2010, 1, 5, tzinfo=timezone.utc).timestamp()),
    ]
    data = _yahoo_response(ts, closes=[1100.5, 1102.0])
    df = parse_yahoo_chart(data, "GC=F")
    assert len(df) == 2
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["close"].iloc[0] == pytest.approx(1100.5)
    assert df["ts"].iloc[1] == pd.Timestamp("2010-01-05 00:00:00+0000")


def test_parse_drops_none_close() -> None:
    ts = [
        int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp()),
        int(datetime(2010, 1, 5, tzinfo=timezone.utc).timestamp()),
        int(datetime(2010, 1, 6, tzinfo=timezone.utc).timestamp()),
    ]
    data = _yahoo_response(ts, closes=[1100.0, None, 1105.0])
    df = parse_yahoo_chart(data, "GC=F")
    assert len(df) == 2
    assert df["close"].tolist() == [1100.0, 1105.0]


def test_parse_keeps_ohlcv() -> None:
    ts = [int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp())]
    data = _yahoo_response(
        ts,
        closes=[1100.0],
        opens=[1095.0],
        volumes=[12345],
    )
    df = parse_yahoo_chart(data, "GC=F")
    assert df["open"].iloc[0] == 1095.0
    assert df["volume"].iloc[0] == 12345


def test_parse_empty_result_returns_empty_frame() -> None:
    df = parse_yahoo_chart({"chart": {"result": [], "error": None}}, "GC=F")
    assert df.empty
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_parse_missing_chart_raises() -> None:
    with pytest.raises(YahooFetchError, match="missing 'chart'"):
        parse_yahoo_chart({}, "GC=F")


def test_parse_yahoo_error_raises() -> None:
    data = {"chart": {"result": None, "error": {"code": "Not Found", "description": "x"}}}
    with pytest.raises(YahooFetchError, match="error"):
        parse_yahoo_chart(data, "INVALID")


def test_parse_handles_missing_volume_field() -> None:
    """Yahoo returnerer noen ganger ingen volume-array (FX-pairs)."""
    ts = [int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp())]
    data = {
        "chart": {
            "result": [
                {
                    "timestamp": ts,
                    "indicators": {
                        "quote": [{"close": [1.5], "open": [1.4], "high": [1.6], "low": [1.3]}]
                    },
                }
            ],
            "error": None,
        }
    }
    df = parse_yahoo_chart(data, "EURUSD=X")
    assert len(df) == 1
    assert pd.isna(df["volume"].iloc[0])


# ---------------------------------------------------------------------
# fetch_yahoo_prices (HTTP-mock)
# ---------------------------------------------------------------------


def test_fetch_success() -> None:
    ts = [int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp())]
    payload = json.dumps(_yahoo_response(ts, closes=[1100.0])).encode()

    class FakeResp:
        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *a: object) -> None:
            pass

        def read(self) -> bytes:
            return payload

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        df = fetch_yahoo_prices("GC=F", date(2010, 1, 1), date(2010, 1, 31))
    assert len(df) == 1
    assert df["close"].iloc[0] == 1100.0


def test_fetch_url_error_raises() -> None:
    import urllib.error

    def boom(*args: object, **kwargs: object) -> object:
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", side_effect=boom):
        with pytest.raises(YahooFetchError, match="Network failure"):
            fetch_yahoo_prices("GC=F", date(2010, 1, 1), date(2010, 1, 31))


def test_fetch_invalid_json_raises() -> None:
    class FakeResp:
        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *a: object) -> None:
            pass

        def read(self) -> bytes:
            return b"<html>not json</html>"

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        with pytest.raises(YahooFetchError, match="parse Yahoo JSON"):
            fetch_yahoo_prices("GC=F", date(2010, 1, 1), date(2010, 1, 31))


def test_fetch_to_appendable_to_store(tmp_path) -> None:
    """Integrasjon: fetcher → DataStore.append_prices → get_prices."""
    from bedrock.data.store import DataStore

    ts = [
        int(datetime(2010, 1, 4, tzinfo=timezone.utc).timestamp()),
        int(datetime(2010, 1, 5, tzinfo=timezone.utc).timestamp()),
    ]
    payload = json.dumps(_yahoo_response(ts, closes=[1100.0, 1102.0])).encode()

    class FakeResp:
        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *a: object) -> None:
            pass

        def read(self) -> bytes:
            return payload

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        df = fetch_yahoo_prices("GC=F", date(2010, 1, 1), date(2010, 1, 31))

    store = DataStore(tmp_path / "bedrock.db")
    n = store.append_prices("Gold", "D1", df)
    assert n == 2
    series = store.get_prices("Gold", "D1")
    assert len(series) == 2
    assert series.iloc[0] == 1100.0
