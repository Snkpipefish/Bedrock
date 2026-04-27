# pyright: reportArgumentType=false
"""Tester for crypto_sentiment-tabell + DataStore (sub-fase 12.5+ session 115)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import CRYPTO_SENTIMENT_COLS, CryptoSentimentRow
from bedrock.data.store import DataStore


def _df(
    indicator: str = "crypto_fng",
    dates: list[str] | None = None,
    base: float = 50.0,
    source: str = "ALTERNATIVE_ME",
) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-04-25", "2026-04-26", "2026-04-27"]
    return pd.DataFrame(
        {
            "indicator": [indicator] * len(dates),
            "date": dates,
            "value": [base + i for i in range(len(dates))],
            "source": [source] * len(dates),
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------


def test_pydantic_lowercases_indicator() -> None:
    row = CryptoSentimentRow(
        indicator="CRYPTO_FNG",
        date=pd.Timestamp("2026-04-27").date(),
        value=55.0,
        source="ALTERNATIVE_ME",
    )
    assert row.indicator == "crypto_fng"


def test_pydantic_strips_whitespace() -> None:
    row = CryptoSentimentRow(
        indicator="  btc_dominance ",
        date=pd.Timestamp("2026-04-27").date(),
        value=51.5,
        source="COINGECKO",
    )
    assert row.indicator == "btc_dominance"


# ---------------------------------------------------------------------------
# append + get
# ---------------------------------------------------------------------------


def test_append_and_get(store: DataStore) -> None:
    store.append_crypto_sentiment(_df())
    series = store.get_crypto_sentiment("crypto_fng")
    assert len(series) == 3
    assert series.iloc[0] == 50.0
    assert series.iloc[-1] == 52.0


def test_multiple_indicators(store: DataStore) -> None:
    store.append_crypto_sentiment(_df("crypto_fng", base=55.0))
    store.append_crypto_sentiment(_df("btc_dominance", base=52.0, source="COINGECKO"))
    fng = store.get_crypto_sentiment("crypto_fng")
    btc = store.get_crypto_sentiment("btc_dominance")
    assert fng.iloc[0] == 55.0
    assert btc.iloc[0] == 52.0


def test_get_uppercase_lookup(store: DataStore) -> None:
    store.append_crypto_sentiment(_df("crypto_fng"))
    assert len(store.get_crypto_sentiment("CRYPTO_FNG")) == 3


def test_get_last_n(store: DataStore) -> None:
    store.append_crypto_sentiment(_df())
    assert len(store.get_crypto_sentiment("crypto_fng", last_n=1)) == 1


def test_get_unknown_raises(store: DataStore) -> None:
    store.append_crypto_sentiment(_df("crypto_fng"))
    with pytest.raises(KeyError, match="btc_dominance"):
        store.get_crypto_sentiment("btc_dominance")


def test_dedupe_overwrite(store: DataStore) -> None:
    """Samme (indicator, date) skal overskrives — CoinGecko kan revidere."""
    store.append_crypto_sentiment(_df("crypto_fng", dates=["2026-04-27"], base=50.0))
    store.append_crypto_sentiment(_df("crypto_fng", dates=["2026-04-27"], base=99.0))
    series = store.get_crypto_sentiment("crypto_fng")
    assert len(series) == 1
    assert series.iloc[0] == 99.0


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"date": ["2026-04-27"], "value": [50.0]})
    with pytest.raises(ValueError, match="mangler"):
        store.append_crypto_sentiment(bad)


def test_empty_returns_zero(store: DataStore) -> None:
    empty = pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))
    assert store.append_crypto_sentiment(empty) == 0


# ---------------------------------------------------------------------------
# has
# ---------------------------------------------------------------------------


def test_has_negative(store: DataStore) -> None:
    assert not store.has_crypto_sentiment()
    assert not store.has_crypto_sentiment("crypto_fng")


def test_has_positive(store: DataStore) -> None:
    store.append_crypto_sentiment(_df("crypto_fng"))
    assert store.has_crypto_sentiment()
    assert store.has_crypto_sentiment("crypto_fng")
    assert not store.has_crypto_sentiment("btc_dominance")


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_crypto_sentiment(_df())
    series = DataStore(db).get_crypto_sentiment("crypto_fng")
    assert len(series) == 3
