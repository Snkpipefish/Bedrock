"""Tester for fundamentals-støtte (FRED-stil serier) i DataStore."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _fred_df(
    series_id: str = "DGS10",
    dates: list[str] | None = None,
    values: list[float | None] | None = None,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    if values is None:
        values = [3.95, 3.97, 4.01]
    return pd.DataFrame(
        {
            "series_id": [series_id] * len(dates),
            "date": dates,
            "value": values,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_fundamentals_append_and_get(store: DataStore) -> None:
    store.append_fundamentals(_fred_df())
    out = store.get_fundamentals("DGS10")
    assert len(out) == 3
    assert list(out) == [3.95, 3.97, 4.01]
    assert isinstance(out.index, pd.DatetimeIndex)


def test_fundamentals_get_last_n(store: DataStore) -> None:
    store.append_fundamentals(_fred_df())
    out = store.get_fundamentals("DGS10", last_n=2)
    assert len(out) == 2
    assert list(out) == [3.97, 4.01]


def test_fundamentals_dedupe_on_same_date(store: DataStore) -> None:
    store.append_fundamentals(_fred_df())
    # Re-append med samme datoer, nye verdier
    replay = _fred_df(values=[9.0, 9.0, 9.0])
    store.append_fundamentals(replay)
    out = store.get_fundamentals("DGS10")
    assert len(out) == 3
    assert list(out) == [9.0, 9.0, 9.0]


def test_fundamentals_nullable_value(store: DataStore) -> None:
    """FRED rapporterer ofte missing (helgedager). NULL lagres, kommer ut
    som NaN."""
    store.append_fundamentals(_fred_df(values=[3.95, None, 4.01]))
    out = store.get_fundamentals("DGS10")
    assert out.iloc[0] == 3.95
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == 4.01


def test_fundamentals_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"series_id": ["X"], "value": [1.0]})  # mangler date
    with pytest.raises(ValueError, match="missing columns"):
        store.append_fundamentals(bad)


def test_fundamentals_unknown_series_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No fundamentals"):
        store.get_fundamentals("NOT_A_SERIES")


def test_fundamentals_separate_series_do_not_interfere(store: DataStore) -> None:
    store.append_fundamentals(_fred_df(series_id="DGS10", values=[3.95, 3.97, 4.01]))
    store.append_fundamentals(_fred_df(series_id="DGS2", values=[4.5, 4.6, 4.7]))
    assert list(store.get_fundamentals("DGS10")) == [3.95, 3.97, 4.01]
    assert list(store.get_fundamentals("DGS2")) == [4.5, 4.6, 4.7]


def test_has_fundamentals(store: DataStore) -> None:
    assert not store.has_fundamentals("DGS10")
    store.append_fundamentals(_fred_df())
    assert store.has_fundamentals("DGS10")
    assert not store.has_fundamentals("DGS2")


def test_fundamentals_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_fundamentals(_fred_df())
    assert list(DataStore(db).get_fundamentals("DGS10")) == [3.95, 3.97, 4.01]
