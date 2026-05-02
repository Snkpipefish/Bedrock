"""Tester for alsi_storage-støtte i DataStore (sub-fase 12.10 follow-up Spor C, session 136)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import ALSI_STORAGE_COLS, AlsiStorageRow
from bedrock.data.store import DataStore


def _alsi_df(country: str = "eu", dates: list[str] | None = None) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-04-28", "2026-04-29", "2026-04-30"]
    n = len(dates)
    return pd.DataFrame(
        {
            "country": [country] * n,
            "gas_day_start": dates,
            "inventory_twh": [32.0 + 0.5 * i for i in range(n)],
            "dtmi_twh": [62.0] * n,
            "full_pct": [(32.0 + 0.5 * i) / 62.0 * 100 for i in range(n)],
            "send_out_twh": [4.0 + 0.1 * i for i in range(n)],
            "dtrs_twh": [7.9] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_alsi_cols_canonical_order() -> None:
    assert ALSI_STORAGE_COLS == (
        "country",
        "gas_day_start",
        "inventory_twh",
        "dtmi_twh",
        "full_pct",
        "send_out_twh",
        "dtrs_twh",
    )


def test_alsi_pydantic_lowercase_country() -> None:
    row = AlsiStorageRow(country="EU", gas_day_start=dt.date(2026, 4, 30))
    assert row.country == "eu"


def test_alsi_append_and_get(store: DataStore) -> None:
    n = store.append_alsi_storage(_alsi_df())
    assert n == 3
    df = store.get_alsi_storage("eu")
    assert len(df) == 3
    assert df["inventory_twh"].iloc[0] == 32.0
    assert df["gas_day_start"].iloc[0] == pd.Timestamp("2026-04-28")


def test_alsi_idempotent_replace(store: DataStore) -> None:
    """INSERT OR REPLACE på (country, gas_day_start) — re-append overskriver."""
    store.append_alsi_storage(_alsi_df())
    overwrite = _alsi_df()
    overwrite.loc[0, "inventory_twh"] = 99.9
    store.append_alsi_storage(overwrite)
    df = store.get_alsi_storage("eu")
    assert len(df) == 3
    assert df["inventory_twh"].iloc[0] == 99.9


def test_alsi_country_isolation(store: DataStore) -> None:
    store.append_alsi_storage(_alsi_df(country="eu"))
    store.append_alsi_storage(_alsi_df(country="de"))
    eu = store.get_alsi_storage("eu")
    de = store.get_alsi_storage("de")
    assert len(eu) == 3
    assert len(de) == 3
    assert (eu["country"] == "eu").all()
    assert (de["country"] == "de").all()


def test_alsi_get_unknown_country_raises(store: DataStore) -> None:
    with pytest.raises(KeyError):
        store.get_alsi_storage("xx")


def test_alsi_has(store: DataStore) -> None:
    assert not store.has_alsi_storage("eu")
    store.append_alsi_storage(_alsi_df())
    assert store.has_alsi_storage("eu")
    assert not store.has_alsi_storage("xx")


def test_alsi_last_n(store: DataStore) -> None:
    store.append_alsi_storage(_alsi_df(dates=[f"2026-04-{d:02d}" for d in range(1, 11)]))
    df = store.get_alsi_storage("eu", last_n=3)
    assert len(df) == 3
    assert df["gas_day_start"].iloc[-1] == pd.Timestamp("2026-04-10")


def test_alsi_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"country": ["eu"], "gas_day_start": ["2026-04-30"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_alsi_storage(bad)


def test_alsi_nullable_fields(store: DataStore) -> None:
    """Alle numeriske felt unntatt PK kan være null (delvis API-respons)."""
    df = pd.DataFrame(
        {
            "country": ["eu"],
            "gas_day_start": ["2026-04-30"],
            "inventory_twh": [32.0],
            "dtmi_twh": [None],
            "full_pct": [None],
            "send_out_twh": [None],
            "dtrs_twh": [None],
        }
    )
    store.append_alsi_storage(df)
    out = store.get_alsi_storage("eu")
    assert len(out) == 1
    assert out["inventory_twh"].iloc[0] == 32.0
    assert pd.isna(out["dtmi_twh"].iloc[0])
