"""Tester for SQLite-backet `DataStore`."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _prices_df(n: int = 5, base: float = 100.0, start: str = "2024-01-01") -> pd.DataFrame:
    """Bygg en enkel OHLCV-DataFrame med n rader, 1 dag apart."""
    ts = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [base] * n,
            "high": [base + 1] * n,
            "low": [base - 1] * n,
            "close": [base + i for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_init_creates_sqlite_file(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    assert not db.exists()
    DataStore(db)
    assert db.exists()


def test_append_and_get_roundtrip(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=3))
    out = store.get_prices("Gold", "D1")
    assert len(out) == 3
    assert list(out) == [100.0, 101.0, 102.0]


def test_get_prices_returns_ts_indexed_series(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=3))
    out = store.get_prices("Gold", "D1")
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out.index[0] == pd.Timestamp("2024-01-01")


def test_lookback_returns_last_n(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=100))
    out = store.get_prices("Gold", "D1", lookback=10)
    assert len(out) == 10
    assert list(out) == [float(90 + 100 + i) for i in range(10)]  # closes 190..199


def test_lookback_larger_than_series_returns_full(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=3))
    out = store.get_prices("Gold", "D1", lookback=100)
    assert len(out) == 3


def test_get_prices_unknown_instrument_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No prices"):
        store.get_prices("Gold", "D1")


def test_append_prices_requires_ts_and_close(store: DataStore) -> None:
    bad = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "volume": [10.0]})
    with pytest.raises(ValueError, match="ts.*close"):
        store.append_prices("Gold", "D1", bad)


def test_append_dedupes_on_same_ts(store: DataStore) -> None:
    """INSERT OR REPLACE: samme (instrument, tf, ts) oppdateres, ikke dupliseres."""
    df = _prices_df(n=3)
    store.append_prices("Gold", "D1", df)

    # Samme ts-er, men nye close-verdier
    df2 = df.copy()
    df2["close"] = [999.0, 888.0, 777.0]
    store.append_prices("Gold", "D1", df2)

    out = store.get_prices("Gold", "D1")
    assert len(out) == 3
    assert list(out) == [999.0, 888.0, 777.0]


def test_append_appends_new_ts(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=3, start="2024-01-01"))
    store.append_prices("Gold", "D1", _prices_df(n=2, start="2024-01-04"))
    out = store.get_prices("Gold", "D1")
    assert len(out) == 5


def test_append_accepts_optional_ohlv_missing(store: DataStore) -> None:
    """Close-only input (ingen open/high/low/volume) skal funke."""
    df = pd.DataFrame(
        {"ts": pd.date_range("2024-01-01", periods=3, freq="D"), "close": [1.0, 2.0, 3.0]}
    )
    store.append_prices("Gold", "D1", df)
    out = store.get_prices("Gold", "D1")
    assert list(out) == [1.0, 2.0, 3.0]


def test_has_prices_negative(store: DataStore) -> None:
    assert not store.has_prices("Gold", "D1")


def test_has_prices_positive(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=1))
    assert store.has_prices("Gold", "D1")


def test_separate_instruments_do_not_interfere(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=3, base=100.0))
    store.append_prices("EURUSD", "D1", _prices_df(n=3, base=1.0))
    gold = store.get_prices("Gold", "D1")
    eur = store.get_prices("EURUSD", "D1")
    assert list(gold) == [100.0, 101.0, 102.0]
    assert list(eur) == [1.0, 2.0, 3.0]


def test_separate_tf_on_same_instrument(store: DataStore) -> None:
    store.append_prices("Gold", "D1", _prices_df(n=2, base=100.0))
    store.append_prices("Gold", "4H", _prices_df(n=2, base=200.0))
    assert list(store.get_prices("Gold", "D1")) == [100.0, 101.0]
    assert list(store.get_prices("Gold", "4H")) == [200.0, 201.0]


def test_store_survives_reopen(tmp_path: Path) -> None:
    """Data overlever at DataStore-instansen gjenopprettes mot samme fil."""
    db = tmp_path / "bedrock.db"
    DataStore(db).append_prices("Gold", "D1", _prices_df(n=3))

    store_b = DataStore(db)
    out = store_b.get_prices("Gold", "D1")
    assert len(out) == 3
