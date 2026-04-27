"""Tester for shipping_indices-tabell + DataStore-metoder + bdi-migrasjon
(sub-fase 12.5+ session 113).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import (
    SHIPPING_INDICES_COLS,
    TABLE_BDI,
    ShippingIndexRow,
)
from bedrock.data.store import DataStore

# Legacy DDL — gjenskapt lokalt fordi DDL_BDI ble fjernet i session 113-cleanup.
_LEGACY_DDL_BDI = f"""
CREATE TABLE IF NOT EXISTS {TABLE_BDI} (
    date   TEXT NOT NULL PRIMARY KEY,
    value  REAL NOT NULL,
    source TEXT NOT NULL
)
"""


def _ship_df(
    index_code: str = "BDI",
    dates: list[str] | None = None,
    base_value: float = 1500.0,
    source: str = "BDRY",
) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-04-20", "2026-04-21", "2026-04-22"]
    return pd.DataFrame(
        {
            "index_code": [index_code] * len(dates),
            "date": dates,
            "value": [base_value + i * 10 for i in range(len(dates))],
            "source": [source] * len(dates),
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Pydantic-validering
# ---------------------------------------------------------------------------


def test_shipping_index_row_accepts_known_codes() -> None:
    for code in ["BDI", "BCI", "BPI", "BSI"]:
        row = ShippingIndexRow(
            index_code=code,
            date=pd.Timestamp("2026-04-20").date(),
            value=1500.0,
            source="BDRY",
        )
        assert row.index_code == code


def test_shipping_index_row_uppercases_code() -> None:
    row = ShippingIndexRow(
        index_code="bdi",
        date=pd.Timestamp("2026-04-20").date(),
        value=1500.0,
        source="MANUAL",
    )
    assert row.index_code == "BDI"


def test_shipping_index_row_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="index_code"):
        ShippingIndexRow(
            index_code="XYZ",
            date=pd.Timestamp("2026-04-20").date(),
            value=1500.0,
            source="MANUAL",
        )


# ---------------------------------------------------------------------------
# append + get
# ---------------------------------------------------------------------------


def test_append_and_get_single_index(store: DataStore) -> None:
    store.append_shipping_indices(_ship_df("BDI"))
    series = store.get_shipping_index("BDI")
    assert len(series) == 3
    assert series.iloc[0] == 1500.0
    assert series.iloc[-1] == 1520.0


def test_append_multiple_indices(store: DataStore) -> None:
    store.append_shipping_indices(_ship_df("BDI", base_value=1500.0))
    store.append_shipping_indices(_ship_df("BPI", base_value=1200.0, source="STOOQ"))
    bdi = store.get_shipping_index("BDI")
    bpi = store.get_shipping_index("BPI")
    assert bdi.iloc[0] == 1500.0
    assert bpi.iloc[0] == 1200.0
    assert len(bdi) == 3
    assert len(bpi) == 3


def test_get_shipping_index_uppercase_lookup(store: DataStore) -> None:
    store.append_shipping_indices(_ship_df("BDI"))
    assert len(store.get_shipping_index("bdi")) == 3


def test_get_shipping_index_last_n(store: DataStore) -> None:
    store.append_shipping_indices(
        _ship_df("BDI", dates=["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23"])
    )
    series = store.get_shipping_index("BDI", last_n=2)
    assert len(series) == 2
    assert series.iloc[0] == 1520.0


def test_get_shipping_index_unknown_code_raises(store: DataStore) -> None:
    store.append_shipping_indices(_ship_df("BDI"))
    with pytest.raises(KeyError, match="BCI"):
        store.get_shipping_index("BCI")


def test_dedupe_on_index_date(store: DataStore) -> None:
    """Samme (index_code, date) skal overskrives — Yahoo kan revidere."""
    store.append_shipping_indices(_ship_df("BDI", dates=["2026-04-20"], base_value=1500.0))
    store.append_shipping_indices(_ship_df("BDI", dates=["2026-04-20"], base_value=9999.0))
    series = store.get_shipping_index("BDI")
    assert len(series) == 1
    assert series.iloc[0] == 9999.0


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"date": ["2026-04-20"], "value": [1500.0]})
    with pytest.raises(ValueError, match="mangler kolonner"):
        store.append_shipping_indices(bad)


def test_empty_df_returns_zero(store: DataStore) -> None:
    assert store.append_shipping_indices(pd.DataFrame(columns=list(SHIPPING_INDICES_COLS))) == 0


# ---------------------------------------------------------------------------
# has_shipping_index
# ---------------------------------------------------------------------------


def test_has_negative(store: DataStore) -> None:
    assert not store.has_shipping_index()
    assert not store.has_shipping_index("BDI")


def test_has_positive(store: DataStore) -> None:
    store.append_shipping_indices(_ship_df("BDI"))
    assert store.has_shipping_index()
    assert store.has_shipping_index("BDI")
    assert not store.has_shipping_index("BPI")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_shipping_indices(_ship_df("BDI"))
    series = DataStore(db).get_shipping_index("BDI")
    assert len(series) == 3


# ---------------------------------------------------------------------------
# Migration: bdi → shipping_indices
# ---------------------------------------------------------------------------


def _create_legacy_bdi_table(db: Path, rows: list[tuple[str, float, str]]) -> None:
    """Lag gammel `bdi`-tabell direkte med rad-data, før DataStore-init."""
    with sqlite3.connect(db) as conn:
        conn.execute(_LEGACY_DDL_BDI)
        conn.executemany(
            f"INSERT OR REPLACE INTO {TABLE_BDI} (date, value, source) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()


def test_migration_copies_bdi_rows_to_shipping_indices(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    _create_legacy_bdi_table(
        db,
        [
            ("2025-04-01", 1450.0, "BDRY"),
            ("2025-04-02", 1480.0, "BDRY"),
            ("2025-04-03", 1500.0, "BDRY"),
        ],
    )
    # Init DataStore — migrasjonen kjører automatisk
    store = DataStore(db)
    series = store.get_shipping_index("BDI")
    assert len(series) == 3
    assert series.iloc[0] == 1450.0
    assert series.iloc[-1] == 1500.0


def test_migration_drops_old_bdi_table(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    _create_legacy_bdi_table(db, [("2025-04-01", 1450.0, "BDRY")])
    DataStore(db)
    with sqlite3.connect(db) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_BDI,),
        )
        assert cursor.fetchone() is None


def test_migration_idempotent_on_re_init(tmp_path: Path) -> None:
    """Andre DataStore-init på samme DB skal ikke feile selv om gammel
    bdi-tabell allerede er borte."""
    db = tmp_path / "bedrock.db"
    _create_legacy_bdi_table(db, [("2025-04-01", 1450.0, "BDRY")])
    DataStore(db)
    DataStore(db)  # Skal være no-op (ikke kaste)
    series = DataStore(db).get_shipping_index("BDI")
    assert len(series) == 1


def test_migration_no_op_on_fresh_db(tmp_path: Path) -> None:
    """Fresh DB uten gammel bdi-tabell skal initialisere uten feil."""
    DataStore(tmp_path / "bedrock.db")  # Skal ikke kaste


# ---------------------------------------------------------------------------
# Legacy BDI-API er fjernet i C4 — bekreft at tilgang feiler
# ---------------------------------------------------------------------------


def test_legacy_append_bdi_no_longer_exists(store: DataStore) -> None:
    assert not hasattr(store, "append_bdi")


def test_legacy_get_bdi_no_longer_exists(store: DataStore) -> None:
    assert not hasattr(store, "get_bdi")
