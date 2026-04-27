"""Tester for COMEX-inventory-støtte i DataStore (sub-fase 12.5+ session 108)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _comex_df(
    metal: str = "gold",
    dates: list[str] | None = None,
    base_registered: float = 15_000_000.0,
    base_eligible: float = 13_000_000.0,
    units: str = "oz",
) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-05", "2024-01-08", "2024-01-09"]
    n = len(dates)
    return pd.DataFrame(
        {
            "metal": [metal] * n,
            "date": dates,
            "registered": [base_registered + 1000.0 * i for i in range(n)],
            "eligible": [base_eligible + 500.0 * i for i in range(n)],
            "total": [base_registered + base_eligible + 2000.0 * i for i in range(n)],
            "units": [units] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_append_and_get(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df())
    df = store.get_comex_inventory("gold")
    assert len(df) == 3
    assert list(df.columns) == [
        "metal",
        "date",
        "registered",
        "eligible",
        "total",
        "units",
    ]
    assert df["registered"].iloc[0] == 15_000_000.0
    assert df["units"].iloc[0] == "oz"


def test_last_n(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df())
    df = store.get_comex_inventory("gold", last_n=2)
    assert len(df) == 2
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-08")


def test_dedupe_on_metal_and_date(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df())
    replay = _comex_df(dates=["2024-01-05"], base_registered=99_999_999.0)
    store.append_comex_inventory(replay)
    df = store.get_comex_inventory("gold")
    assert len(df) == 3
    first = df[df["date"] == pd.Timestamp("2024-01-05")].iloc[0]
    assert first["registered"] == 99_999_999.0


def test_appends_new_dates(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df(dates=["2024-01-05", "2024-01-08"]))
    store.append_comex_inventory(_comex_df(dates=["2024-01-09", "2024-01-10"]))
    df = store.get_comex_inventory("gold")
    assert len(df) == 4


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"metal": ["gold"], "date": ["2024-01-05"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_comex_inventory(bad)


def test_get_unknown_metal_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No COMEX inventory data"):
        store.get_comex_inventory("plutonium")


def test_separate_metals_isolated(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df(metal="gold", base_registered=15_000_000))
    store.append_comex_inventory(_comex_df(metal="silver", base_registered=300_000_000))
    gold = store.get_comex_inventory("gold")
    silver = store.get_comex_inventory("silver")
    assert gold["registered"].iloc[0] == 15_000_000.0
    assert silver["registered"].iloc[0] == 300_000_000.0


def test_copper_no_eligible_split(store: DataStore) -> None:
    """Kobber: CME har fjernet reg/elig-skillet — eligible=0, total=registered."""
    df = pd.DataFrame(
        {
            "metal": ["copper", "copper"],
            "date": ["2024-01-05", "2024-01-08"],
            "registered": [50_000.0, 51_000.0],
            "eligible": [0.0, 0.0],
            "total": [50_000.0, 51_000.0],
            "units": ["st", "st"],
        }
    )
    store.append_comex_inventory(df)
    out = store.get_comex_inventory("copper")
    assert (out["eligible"] == 0.0).all()
    assert (out["total"] == out["registered"]).all()
    assert out["units"].iloc[0] == "st"


def test_units_can_be_null(store: DataStore) -> None:
    df = pd.DataFrame(
        {
            "metal": ["gold"],
            "date": ["2024-01-05"],
            "registered": [15_000_000.0],
            "eligible": [13_000_000.0],
            "total": [28_000_000.0],
            "units": [None],
        }
    )
    store.append_comex_inventory(df)
    out = store.get_comex_inventory("gold")
    assert pd.isna(out["units"].iloc[0])


# ---------------------------------------------------------------------------
# has_comex_inventory
# ---------------------------------------------------------------------------


def test_has_comex_inventory_negative(store: DataStore) -> None:
    assert not store.has_comex_inventory("gold")


def test_has_comex_inventory_positive(store: DataStore) -> None:
    store.append_comex_inventory(_comex_df(metal="gold"))
    assert store.has_comex_inventory("gold")
    assert not store.has_comex_inventory("silver")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_comex_inventory(_comex_df())
    df = DataStore(db).get_comex_inventory("gold")
    assert len(df) == 3
