"""Tester for EIA-inventory-støtte i DataStore (sub-fase 12.5+ session 107)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _eia_df(
    series_id: str = "WCESTUS1",
    dates: list[str] | None = None,
    base_value: float = 460_000.0,
    units: str = "MBBL",
) -> pd.DataFrame:
    """Bygger en DataFrame med n EIA-stock-rader."""
    if dates is None:
        dates = ["2024-01-05", "2024-01-12", "2024-01-19"]
    n = len(dates)
    return pd.DataFrame(
        {
            "series_id": [series_id] * n,
            "date": dates,
            "value": [base_value + 1000.0 * i for i in range(n)],
            "units": [units] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_eia_append_and_get(store: DataStore) -> None:
    store.append_eia_inventory(_eia_df())
    df = store.get_eia_inventory("WCESTUS1")
    assert len(df) == 3
    assert list(df.columns) == ["series_id", "date", "value", "units"]
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-05")
    assert df["value"].iloc[0] == 460_000.0
    assert df["units"].iloc[0] == "MBBL"


def test_eia_last_n(store: DataStore) -> None:
    store.append_eia_inventory(_eia_df())
    df = store.get_eia_inventory("WCESTUS1", last_n=2)
    assert len(df) == 2
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-12")
    assert df["date"].iloc[1] == pd.Timestamp("2024-01-19")


def test_eia_dedupe_on_same_series_and_date(store: DataStore) -> None:
    """Samme (series_id, date) overskrives, ikke dupliseres."""
    store.append_eia_inventory(_eia_df())
    replay = _eia_df(dates=["2024-01-05"], base_value=999_999.0)
    store.append_eia_inventory(replay)

    df = store.get_eia_inventory("WCESTUS1")
    assert len(df) == 3
    first = df[df["date"] == pd.Timestamp("2024-01-05")].iloc[0]
    assert first["value"] == 999_999.0


def test_eia_append_appends_new_dates(store: DataStore) -> None:
    store.append_eia_inventory(_eia_df(dates=["2024-01-05", "2024-01-12"]))
    store.append_eia_inventory(_eia_df(dates=["2024-01-19", "2024-01-26"]))
    df = store.get_eia_inventory("WCESTUS1")
    assert len(df) == 4


def test_eia_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"series_id": ["WCESTUS1"], "date": ["2024-01-05"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_eia_inventory(bad)


def test_eia_get_unknown_series_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No EIA inventory data"):
        store.get_eia_inventory("NONEXISTENT")


def test_eia_separate_series_do_not_interfere(store: DataStore) -> None:
    """Crude og Gasoline lagres uavhengig selv om datoer overlapper."""
    store.append_eia_inventory(_eia_df(series_id="WCESTUS1", base_value=460_000.0, units="MBBL"))
    store.append_eia_inventory(_eia_df(series_id="WGTSTUS1", base_value=230_000.0, units="MBBL"))

    crude = store.get_eia_inventory("WCESTUS1")
    gasoline = store.get_eia_inventory("WGTSTUS1")
    assert crude["value"].iloc[0] == 460_000.0
    assert gasoline["value"].iloc[0] == 230_000.0


def test_eia_handles_different_units(store: DataStore) -> None:
    """Crude (MBBL) og NatGas (BCF) får forskjellige units lagret."""
    store.append_eia_inventory(_eia_df(series_id="WCESTUS1", base_value=460_000.0, units="MBBL"))
    store.append_eia_inventory(
        _eia_df(series_id="NW2_EPG0_SWO_R48_BCF", base_value=2000.0, units="BCF")
    )

    crude = store.get_eia_inventory("WCESTUS1")
    natgas = store.get_eia_inventory("NW2_EPG0_SWO_R48_BCF")
    assert crude["units"].iloc[0] == "MBBL"
    assert natgas["units"].iloc[0] == "BCF"


def test_eia_units_can_be_null(store: DataStore) -> None:
    """Manuell CSV uten units-kolonne — None-fallback håndteres."""
    df = pd.DataFrame(
        {
            "series_id": ["WCESTUS1"],
            "date": ["2024-01-05"],
            "value": [460_000.0],
            "units": [None],
        }
    )
    store.append_eia_inventory(df)
    out = store.get_eia_inventory("WCESTUS1")
    assert pd.isna(out["units"].iloc[0])


# ---------------------------------------------------------------------------
# has_eia_inventory
# ---------------------------------------------------------------------------


def test_has_eia_inventory_negative(store: DataStore) -> None:
    assert not store.has_eia_inventory("WCESTUS1")


def test_has_eia_inventory_positive(store: DataStore) -> None:
    store.append_eia_inventory(_eia_df(series_id="WCESTUS1"))
    assert store.has_eia_inventory("WCESTUS1")
    assert not store.has_eia_inventory("WGTSTUS1")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_eia_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_eia_inventory(_eia_df())

    store_b = DataStore(db)
    df = store_b.get_eia_inventory("WCESTUS1")
    assert len(df) == 3
