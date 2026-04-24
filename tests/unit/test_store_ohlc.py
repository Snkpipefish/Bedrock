"""Tester for `DataStore.get_prices_ohlc` — full OHLCV-lesing."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _ohlcv(n: int = 5, base: float = 100.0) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [base + i for i in range(n)],
            "high": [base + i + 0.5 for i in range(n)],
            "low": [base + i - 0.5 for i in range(n)],
            "close": [base + i + 0.25 for i in range(n)],
            "volume": [1000.0 * (i + 1) for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    s = DataStore(tmp_path / "bedrock.db")
    s.append_prices("Gold", "D1", _ohlcv(n=5))
    return s


def test_ohlc_returns_datetime_indexed_dataframe(store: DataStore) -> None:
    df = store.get_prices_ohlc("Gold", "D1")
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "ts"


def test_ohlc_returns_all_columns(store: DataStore) -> None:
    df = store.get_prices_ohlc("Gold", "D1")
    assert set(df.columns) == {"open", "high", "low", "close", "volume"}


def test_ohlc_column_dtypes_are_float64(store: DataStore) -> None:
    df = store.get_prices_ohlc("Gold", "D1")
    for col in ("open", "high", "low", "close", "volume"):
        assert df[col].dtype == "float64"


def test_ohlc_ascending_sort(store: DataStore) -> None:
    df = store.get_prices_ohlc("Gold", "D1")
    assert df.index[0] < df.index[-1]


def test_ohlc_lookback_returns_last_n(store: DataStore) -> None:
    df = store.get_prices_ohlc("Gold", "D1", lookback=3)
    assert len(df) == 3
    assert df["high"].iloc[0] == pytest.approx(102.5)  # bar 2 (0-indexed)


def test_ohlc_unknown_instrument_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No prices"):
        store.get_prices_ohlc("Silver", "D1")


def test_ohlc_null_volume_comes_out_as_nan(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    close_only = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [1.0, 2.0],
        }
    )
    store.append_prices("EURUSD", "D1", close_only)
    df = store.get_prices_ohlc("EURUSD", "D1")
    assert pd.isna(df["open"].iloc[0])
    assert pd.isna(df["volume"].iloc[0])
    assert df["close"].iloc[0] == 1.0
