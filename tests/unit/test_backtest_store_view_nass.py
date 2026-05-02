"""Tester for AsOfDateStore-proxy for NASS yield + grain_stocks (sub-fase 12.10 follow-up Spor D, session 137)."""

# pyright: reportArgumentType=false

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore


@pytest.fixture
def store_with_nass(tmp_path: Path) -> DataStore:
    store = DataStore(tmp_path / "bedrock.db")

    # Yield: 4 år × 5 reference_periods (YEAR + AUG/SEP/OCT/NOV)
    yield_rows = []
    for year in (2020, 2021, 2022, 2023):
        # Forecasts publisert i hhv aug/sep/okt/nov same year
        for month, label in (
            (8, "YEAR - AUG FORECAST"),
            (9, "YEAR - SEP FORECAST"),
            (10, "YEAR - OCT FORECAST"),
            (11, "YEAR - NOV FORECAST"),
        ):
            yield_rows.append(
                {
                    "commodity": "CORN",
                    "year": year,
                    "reference_period": label,
                    "yield_value": 170.0 + (year - 2020) * 2.0,
                    "yield_units": "BU / ACRE",
                    "util_practice": "GRAIN",
                    "load_time": pd.Timestamp(f"{year}-{month:02d}-15 12:00:00"),
                }
            )
        # Final YEAR publisert i januar året etter
        yield_rows.append(
            {
                "commodity": "CORN",
                "year": year,
                "reference_period": "YEAR",
                "yield_value": 175.0 + (year - 2020) * 2.0,
                "yield_units": "BU / ACRE",
                "util_practice": "GRAIN",
                "load_time": pd.Timestamp(f"{year + 1}-01-12 12:00:00"),
            }
        )
    store.append_nass_yield(pd.DataFrame(yield_rows))

    # Grain stocks: 4 år × 4 quartals
    stocks_rows = []
    quarter_months = {
        "FIRST OF MAR": 3,
        "FIRST OF JUN": 6,
        "FIRST OF SEP": 9,
        "FIRST OF DEC": 12,
    }
    for year in (2020, 2021, 2022, 2023):
        for q, month in quarter_months.items():
            stocks_rows.append(
                {
                    "commodity": "CORN",
                    "year": year,
                    "reference_period": q,
                    "category": "TOTAL",
                    "stocks_bu": 7e9 - (year - 2020) * 1e8,
                    "load_time": pd.Timestamp(f"{year}-{month:02d}-30 12:00:00"),
                }
            )
    store.append_nass_grain_stocks(pd.DataFrame(stocks_rows))

    return store


# Yield clipping ---------------------------------------------------------


def test_yield_clipped_by_load_time(store_with_nass: DataStore) -> None:
    """as_of=2023-09-16: skal inkludere alle rader publisert ≤ den datoen."""
    view = AsOfDateStore(store_with_nass, date(2023, 9, 16))
    df = view.get_nass_yield("CORN")
    # 2020-2022 alle 5 rader hver = 15
    # 2023: AUG (8/15) og SEP (9/15) forecasts = 2
    assert len(df) == 17


def test_yield_clipped_excludes_unreleased(store_with_nass: DataStore) -> None:
    """as_of=2023-08-01: 2023-rader ikke ennå publisert."""
    view = AsOfDateStore(store_with_nass, date(2023, 8, 1))
    df = view.get_nass_yield("CORN")
    # 2020-2022: 5 hver = 15. 2023: ingen publisert ennå.
    assert len(df) == 15


def test_yield_clipped_to_empty(store_with_nass: DataStore) -> None:
    view = AsOfDateStore(store_with_nass, date(2019, 1, 1))
    df = view.get_nass_yield("CORN")
    assert df.empty


def test_yield_reference_period_filter_after_clip(store_with_nass: DataStore) -> None:
    view = AsOfDateStore(store_with_nass, date(2023, 9, 16))
    df = view.get_nass_yield("CORN", reference_period="YEAR")
    # YEAR-final for 2020-2022 er publisert (jan 2021/2022/2023)
    assert len(df) == 3


def test_has_nass_yield_after_clip(store_with_nass: DataStore) -> None:
    view_before = AsOfDateStore(store_with_nass, date(2019, 1, 1))
    assert not view_before.has_nass_yield("CORN")
    view_after = AsOfDateStore(store_with_nass, date(2023, 9, 16))
    assert view_after.has_nass_yield("CORN")


# Stocks clipping --------------------------------------------------------


def test_stocks_clipped_by_load_time(store_with_nass: DataStore) -> None:
    """as_of=2023-07-01: tar med alle Mar+Jun-rader t.o.m. 2023, ingen Sep/Dec 2023."""
    view = AsOfDateStore(store_with_nass, date(2023, 7, 1))
    df = view.get_nass_grain_stocks("CORN")
    # 2020-2022: 4 quartals × 3 år = 12
    # 2023: MAR (publisert 3/30) + JUN (publisert 6/30) = 2
    assert len(df) == 14


def test_stocks_clipped_excludes_unreleased(store_with_nass: DataStore) -> None:
    view = AsOfDateStore(store_with_nass, date(2023, 1, 1))
    df = view.get_nass_grain_stocks("CORN")
    # 2020-2022: 12 rader
    assert len(df) == 12


def test_has_nass_grain_stocks_after_clip(store_with_nass: DataStore) -> None:
    view_before = AsOfDateStore(store_with_nass, date(2019, 1, 1))
    assert not view_before.has_nass_grain_stocks("CORN")
    view_after = AsOfDateStore(store_with_nass, date(2023, 7, 1))
    assert view_after.has_nass_grain_stocks("CORN")
