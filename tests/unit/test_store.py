"""Tester for `InMemoryStore` (Fase 1-stub)."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.data.store import InMemoryStore


def test_add_and_get_prices_roundtrip() -> None:
    store = InMemoryStore()
    store.add_prices("Gold", "D1", pd.Series([100.0, 101.0, 102.0]))

    out = store.get_prices("Gold", tf="D1")
    assert len(out) == 3
    assert list(out) == [100.0, 101.0, 102.0]


def test_add_prices_accepts_list() -> None:
    store = InMemoryStore()
    store.add_prices("Gold", "D1", [1.0, 2.0, 3.0])

    assert store.has_prices("Gold", "D1")
    assert list(store.get_prices("Gold")) == [1.0, 2.0, 3.0]


def test_get_prices_lookback_returns_last_n() -> None:
    store = InMemoryStore()
    store.add_prices("Gold", "D1", list(range(100)))

    out = store.get_prices("Gold", tf="D1", lookback=10)
    assert len(out) == 10
    assert list(out) == list(range(90, 100))


def test_get_prices_lookback_larger_than_series_returns_full() -> None:
    store = InMemoryStore()
    store.add_prices("Gold", "D1", [1.0, 2.0, 3.0])
    out = store.get_prices("Gold", tf="D1", lookback=100)
    assert list(out) == [1.0, 2.0, 3.0]


def test_get_prices_unknown_instrument_raises() -> None:
    store = InMemoryStore()
    with pytest.raises(KeyError, match="No prices"):
        store.get_prices("Gold", tf="D1")


def test_add_prices_overwrites_existing_key() -> None:
    store = InMemoryStore()
    store.add_prices("Gold", "D1", [1.0, 2.0])
    store.add_prices("Gold", "D1", [9.0])
    assert list(store.get_prices("Gold", "D1")) == [9.0]


def test_has_prices_negative() -> None:
    store = InMemoryStore()
    assert not store.has_prices("Gold", "D1")
