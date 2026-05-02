"""Tester for nass_grain_stocks-støtte i DataStore (sub-fase 12.10 follow-up Spor D, session 137)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import NASS_GRAIN_STOCKS_COLS, NassGrainStocksRow
from bedrock.data.store import DataStore


def _stocks_df(
    commodity: str = "CORN",
    years: list[int] | None = None,
    reference_periods: list[str] | None = None,
    categories: list[str] | None = None,
    base_stocks: float = 7e9,
) -> pd.DataFrame:
    if years is None:
        years = [2022, 2023]
    if reference_periods is None:
        reference_periods = ["FIRST OF MAR", "FIRST OF JUN"]
    if categories is None:
        categories = ["TOTAL"]
    rows: list[dict] = []
    for y in years:
        for rp in reference_periods:
            for cat in categories:
                rows.append(
                    {
                        "commodity": commodity,
                        "year": y,
                        "reference_period": rp,
                        "category": cat,
                        "stocks_bu": base_stocks,
                        "load_time": pd.Timestamp(f"{y}-04-01 12:00:00"),
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_stocks_cols_canonical_order() -> None:
    assert NASS_GRAIN_STOCKS_COLS == (
        "commodity",
        "year",
        "reference_period",
        "category",
        "stocks_bu",
        "load_time",
    )


def test_stocks_pydantic_uppercases_commodity_and_category() -> None:
    row = NassGrainStocksRow(
        commodity="corn",
        year=2023,
        reference_period="FIRST OF MAR",
        category="on farm",
    )
    assert row.commodity == "CORN"
    assert row.category == "ON FARM"


def test_stocks_append_and_get(store: DataStore) -> None:
    n = store.append_nass_grain_stocks(_stocks_df())
    assert n == 4  # 2 år × 2 quartals × 1 category
    df = store.get_nass_grain_stocks("CORN")
    assert len(df) == 4
    assert (df["category"] == "TOTAL").all()


def test_stocks_idempotent_replace(store: DataStore) -> None:
    store.append_nass_grain_stocks(_stocks_df())
    overwrite = _stocks_df()
    overwrite.loc[0, "stocks_bu"] = 999.0  # (2022, FIRST OF MAR)
    store.append_nass_grain_stocks(overwrite)
    df = store.get_nass_grain_stocks("CORN")
    # SQL ORDER BY year, reference_period: alphabetisk "FIRST OF JUN" < "FIRST OF MAR"
    # → row 1 = (2022, MAR) hvor overwriten skjedde
    assert (
        df[(df["year"] == 2022) & (df["reference_period"] == "FIRST OF MAR")]["stocks_bu"].iloc[0]
        == 999.0
    )


def test_stocks_category_isolation(store: DataStore) -> None:
    """ON FARM vs OFF FARM vs TOTAL er separate rader (PK inkluderer category)."""
    df = _stocks_df(categories=["TOTAL", "ON FARM", "OFF FARM"])
    store.append_nass_grain_stocks(df)
    total = store.get_nass_grain_stocks("CORN", category="TOTAL")
    on_farm = store.get_nass_grain_stocks("CORN", category="ON FARM")
    off_farm = store.get_nass_grain_stocks("CORN", category="OFF FARM")
    assert len(total) == 4
    assert len(on_farm) == 4
    assert len(off_farm) == 4


def test_stocks_default_category_total(store: DataStore) -> None:
    df = _stocks_df(categories=["TOTAL", "ON FARM"])
    store.append_nass_grain_stocks(df)
    out = store.get_nass_grain_stocks("CORN")
    assert (out["category"] == "TOTAL").all()


def test_stocks_unknown_commodity_returns_empty(store: DataStore) -> None:
    df = store.get_nass_grain_stocks("RICE")
    assert df.empty


def test_stocks_has(store: DataStore) -> None:
    assert not store.has_nass_grain_stocks("CORN")
    store.append_nass_grain_stocks(_stocks_df())
    assert store.has_nass_grain_stocks("CORN")
    assert not store.has_nass_grain_stocks("RICE")


def test_stocks_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"commodity": ["CORN"], "year": [2023]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_nass_grain_stocks(bad)


def test_stocks_nullable_value(store: DataStore) -> None:
    df = _stocks_df()
    df.loc[0, "stocks_bu"] = None  # (2022, FIRST OF MAR)
    store.append_nass_grain_stocks(df)
    out = store.get_nass_grain_stocks("CORN")
    null_row = out[(out["year"] == 2022) & (out["reference_period"] == "FIRST OF MAR")]
    assert pd.isna(null_row["stocks_bu"].iloc[0])
