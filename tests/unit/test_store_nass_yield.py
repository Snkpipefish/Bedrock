"""Tester for nass_yield-støtte i DataStore (sub-fase 12.10 follow-up Spor D, session 137)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import NASS_YIELD_COLS, NassYieldRow
from bedrock.data.store import DataStore


def _yield_df(
    commodity: str = "CORN",
    years: list[int] | None = None,
    reference_periods: list[str] | None = None,
    base_yield: float = 170.0,
) -> pd.DataFrame:
    if years is None:
        years = [2022, 2023]
    if reference_periods is None:
        reference_periods = ["YEAR"]
    rows: list[dict] = []
    for i, y in enumerate(years):
        for rp in reference_periods:
            rows.append(
                {
                    "commodity": commodity,
                    "year": y,
                    "reference_period": rp,
                    "yield_value": base_yield + i * 5.0,
                    "yield_units": "BU / ACRE",
                    "util_practice": "GRAIN",
                    "load_time": pd.Timestamp(f"{y}-09-30 12:00:00"),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_nass_yield_cols_canonical_order() -> None:
    assert NASS_YIELD_COLS == (
        "commodity",
        "year",
        "reference_period",
        "yield_value",
        "yield_units",
        "util_practice",
        "load_time",
    )


def test_nass_yield_pydantic_uppercases_commodity() -> None:
    row = NassYieldRow(commodity="corn", year=2023, reference_period="YEAR")
    assert row.commodity == "CORN"


def test_nass_yield_pydantic_year_range() -> None:
    with pytest.raises(ValueError):
        NassYieldRow(commodity="CORN", year=1899, reference_period="YEAR")


def test_yield_append_and_get(store: DataStore) -> None:
    n = store.append_nass_yield(_yield_df())
    assert n == 2
    df = store.get_nass_yield("CORN")
    assert len(df) == 2
    assert df["yield_value"].iloc[0] == 170.0
    assert df["year"].iloc[0] == 2022


def test_yield_idempotent_replace(store: DataStore) -> None:
    """INSERT OR REPLACE på (commodity, year, reference_period)."""
    store.append_nass_yield(_yield_df())
    overwrite = _yield_df()
    overwrite.loc[0, "yield_value"] = 999.9
    store.append_nass_yield(overwrite)
    df = store.get_nass_yield("CORN")
    assert len(df) == 2
    assert df["yield_value"].iloc[0] == 999.9


def test_yield_commodity_isolation(store: DataStore) -> None:
    store.append_nass_yield(_yield_df(commodity="CORN", base_yield=170.0))
    store.append_nass_yield(_yield_df(commodity="SOYBEANS", base_yield=50.0))
    corn = store.get_nass_yield("CORN")
    soy = store.get_nass_yield("SOYBEANS")
    assert (corn["commodity"] == "CORN").all()
    assert (soy["commodity"] == "SOYBEANS").all()


def test_yield_reference_period_filter(store: DataStore) -> None:
    df = _yield_df(reference_periods=["YEAR", "YEAR - AUG FORECAST", "YEAR - NOV FORECAST"])
    store.append_nass_yield(df)
    final = store.get_nass_yield("CORN", reference_period="YEAR")
    assert len(final) == 2  # 2 år, kun YEAR
    assert (final["reference_period"] == "YEAR").all()


def test_yield_unknown_commodity_returns_empty(store: DataStore) -> None:
    df = store.get_nass_yield("RICE")
    assert df.empty


def test_yield_has(store: DataStore) -> None:
    assert not store.has_nass_yield("CORN")
    store.append_nass_yield(_yield_df())
    assert store.has_nass_yield("CORN")
    assert not store.has_nass_yield("RICE")


def test_yield_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"commodity": ["CORN"], "year": [2023]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_nass_yield(bad)


def test_yield_nullable_value(store: DataStore) -> None:
    df = _yield_df()
    df.loc[0, "yield_value"] = None
    store.append_nass_yield(df)
    out = store.get_nass_yield("CORN")
    assert pd.isna(out["yield_value"].iloc[0])
