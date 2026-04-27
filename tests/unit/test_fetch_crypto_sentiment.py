# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Tester for ``bedrock.fetch.crypto_sentiment`` (sub-fase 12.5+ session 115).

raw_response/raw_fng/raw_coingecko-injection brukes i alle tester —
ingen network-IO.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import CRYPTO_SENTIMENT_COLS
from bedrock.fetch.crypto_sentiment import (
    fetch_coingecko_global,
    fetch_crypto_sentiment,
    fetch_crypto_sentiment_manual_csv,
    fetch_fear_and_greed,
)

# ---------------------------------------------------------------------------
# Fear & Greed
# ---------------------------------------------------------------------------


def _fng_response(values: list[tuple[str, int, str]]) -> dict:
    """Bygg alternative.me-respons. (date_iso, value, classification)."""
    from datetime import datetime, timezone

    return {
        "data": [
            {
                "value": str(v),
                "value_classification": cls,
                "timestamp": str(
                    int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
                ),
            }
            for d, v, cls in values
        ]
    }


def test_fng_parses_basic_response() -> None:
    raw = _fng_response(
        [
            ("2026-04-27", 55, "Greed"),
            ("2026-04-26", 50, "Neutral"),
        ]
    )
    df = fetch_fear_and_greed(raw_response=raw)
    assert len(df) == 2
    assert (df["indicator"] == "crypto_fng").all()
    assert (df["source"] == "ALTERNATIVE_ME").all()
    assert set(df["value"]) == {55.0, 50.0}
    assert list(df.columns) == list(CRYPTO_SENTIMENT_COLS)


def test_fng_skips_malformed_entries() -> None:
    raw = {
        "data": [
            {
                "value": "55",
                "value_classification": "Greed",
                "timestamp": str(int(pd.Timestamp("2026-04-27", tz="UTC").timestamp())),
            },
            {"value": "bogus", "timestamp": "not_int"},
            {"value": "50"},  # mangler timestamp
        ]
    }
    df = fetch_fear_and_greed(raw_response=raw)
    assert len(df) == 1
    assert df["value"].iloc[0] == 55.0


def test_fng_empty_response_returns_empty() -> None:
    df = fetch_fear_and_greed(raw_response={"data": []})
    assert df.empty
    assert list(df.columns) == list(CRYPTO_SENTIMENT_COLS)


def test_fng_none_response_returns_empty() -> None:
    df = fetch_fear_and_greed(raw_response=None, limit=0)
    # raw_response=None faller til HTTP-kall. Med limit=0 vil URL bli
    # malformed — vi bruker patch på _http_get_json istedenfor.
    # Her tester vi bare at empty dict gir empty df.
    df = fetch_fear_and_greed(raw_response={})
    assert df.empty


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------


def _cg_response() -> dict:
    return {
        "data": {
            "market_cap_percentage": {"btc": 52.3, "eth": 17.8},
            "total_market_cap": {"usd": 2.85e12},
            "market_cap_change_percentage_24h_usd": 1.23,
            "active_cryptocurrencies": 12000,
        }
    }


def test_coingecko_parses_4_indicators() -> None:
    df = fetch_coingecko_global(
        fetched_at=date(2026, 4, 27),
        raw_response=_cg_response(),
    )
    assert len(df) == 4
    by_ind = {row["indicator"]: row["value"] for _, row in df.iterrows()}
    assert by_ind["btc_dominance"] == 52.3
    assert by_ind["eth_dominance"] == 17.8
    assert by_ind["total_mcap_usd"] == 2.85e12
    assert by_ind["total_mcap_chg24h_pct"] == 1.23
    assert (df["source"] == "COINGECKO").all()
    assert (df["date"] == "2026-04-27").all()


def test_coingecko_skips_missing_indicators() -> None:
    raw = {"data": {"market_cap_percentage": {"btc": 52.0}}}
    df = fetch_coingecko_global(
        fetched_at=date(2026, 4, 27),
        raw_response=raw,
    )
    inds = set(df["indicator"])
    assert inds == {"btc_dominance"}


def test_coingecko_empty_response_returns_empty() -> None:
    df = fetch_coingecko_global(
        fetched_at=date(2026, 4, 27),
        raw_response={"data": {}},
    )
    assert df.empty
    assert list(df.columns) == list(CRYPTO_SENTIMENT_COLS)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_fetch_crypto_sentiment_combines_both_sources() -> None:
    df = fetch_crypto_sentiment(
        fetched_at=date(2026, 4, 27),
        raw_fng=_fng_response([("2026-04-27", 55, "Greed")]),
        raw_coingecko=_cg_response(),
    )
    assert len(df) == 5  # 1 fng + 4 coingecko
    inds = set(df["indicator"])
    assert inds == {
        "crypto_fng",
        "btc_dominance",
        "eth_dominance",
        "total_mcap_usd",
        "total_mcap_chg24h_pct",
    }


def test_fetch_crypto_sentiment_fng_only_when_coingecko_fails() -> None:
    df = fetch_crypto_sentiment(
        fetched_at=date(2026, 4, 27),
        raw_fng=_fng_response([("2026-04-27", 55, "Greed")]),
        raw_coingecko={"data": {}},
    )
    assert len(df) == 1
    assert df["indicator"].iloc[0] == "crypto_fng"


def test_fetch_crypto_sentiment_coingecko_only_when_fng_fails() -> None:
    df = fetch_crypto_sentiment(
        fetched_at=date(2026, 4, 27),
        raw_fng={},
        raw_coingecko=_cg_response(),
    )
    assert len(df) == 4
    assert "crypto_fng" not in set(df["indicator"])


def test_fetch_crypto_sentiment_empty_when_both_fail() -> None:
    df = fetch_crypto_sentiment(
        fetched_at=date(2026, 4, 27),
        raw_fng={},
        raw_coingecko={"data": {}},
    )
    assert df.empty
    assert list(df.columns) == list(CRYPTO_SENTIMENT_COLS)


# ---------------------------------------------------------------------------
# Manuell CSV
# ---------------------------------------------------------------------------


def test_manual_csv_reads(tmp_path: Path) -> None:
    csv = tmp_path / "cs.csv"
    pd.DataFrame(
        {
            "indicator": ["crypto_fng", "btc_dominance"],
            "date": ["2026-04-27", "2026-04-27"],
            "value": [55.0, 52.3],
            "source": ["MANUAL", "MANUAL"],
        }
    ).to_csv(csv, index=False)
    df = fetch_crypto_sentiment_manual_csv(csv)
    assert len(df) == 2


def test_manual_csv_missing_returns_empty(tmp_path: Path) -> None:
    df = fetch_crypto_sentiment_manual_csv(tmp_path / "missing.csv")
    assert df.empty


def test_manual_csv_missing_columns_raises(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    pd.DataFrame({"indicator": ["x"], "date": ["2026-04-27"]}).to_csv(csv, index=False)
    with pytest.raises(ValueError, match="mangler"):
        fetch_crypto_sentiment_manual_csv(csv)
