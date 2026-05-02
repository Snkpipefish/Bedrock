"""Sub-fase 12.10 Bunke 1 Bug-1 trinn 3/3:
Schema-migrasjon + auto-populer av `released_at` for COT- og AAII-tabellene.

Verifiserer at:
1. Eksisterende DBer uten `released_at`-kolonnen får den lagt til
   automatisk + backfilles via SQLite datetime-aritmetikk på reopen.
2. Auto-populering på append fungerer både med og uten eksplisitt
   ``released_at``-kolonne i input-df.
3. Round-trip av eksplisitt ``released_at`` bevarer verdien.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from bedrock.data.release_calendar import aaii_released_at_iso, cot_released_at_iso
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------------
# Schema-migrasjon: legacy DB uten kolonnen
# ---------------------------------------------------------------------------


def test_migration_adds_released_at_column_to_cot_disaggregated(tmp_path: Path) -> None:
    """En DB lagd uten `released_at` skal få kolonnen via _init_schema."""
    db_path = tmp_path / "legacy.db"

    # Lag legacy-DB manuelt — uten released_at
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE cot_disaggregated (
                report_date TEXT NOT NULL,
                contract TEXT NOT NULL,
                mm_long INTEGER NOT NULL,
                mm_short INTEGER NOT NULL,
                other_long INTEGER NOT NULL,
                other_short INTEGER NOT NULL,
                comm_long INTEGER NOT NULL,
                comm_short INTEGER NOT NULL,
                nonrep_long INTEGER NOT NULL,
                nonrep_short INTEGER NOT NULL,
                open_interest INTEGER NOT NULL,
                PRIMARY KEY (report_date, contract)
            )
        """)
        conn.execute(
            "INSERT INTO cot_disaggregated VALUES "
            "('2024-04-30', 'GOLD', 100, 50, 10, 10, 10, 10, 5, 5, 200)"
        )
        conn.commit()

    # Init via DataStore — skal kjøre migrasjon
    store = DataStore(db_path)

    # Verifiser at kolonnen finnes + er backfylt
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("PRAGMA table_info(cot_disaggregated)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "released_at" in columns

        cursor = conn.execute("SELECT released_at FROM cot_disaggregated")
        released_at_value = cursor.fetchone()[0]
        # 2024-04-30 (tirsdag) + 3 dager @ 21:00 UTC = 2024-05-03 21:00:00
        assert released_at_value == "2024-05-03 21:00:00"

    # Sanity: store kan lese raden
    df = store.get_cot("GOLD", report="disaggregated")
    assert len(df) == 1
    assert "released_at" in df.columns


def test_migration_idempotent(tmp_path: Path) -> None:
    """Re-init av en DB hvor kolonnen finnes skal være no-op."""
    db_path = tmp_path / "bedrock.db"
    store = DataStore(db_path)

    # Append en rad
    store.append_cot_disaggregated(
        pd.DataFrame(
            {
                "report_date": [pd.Timestamp("2024-04-30")],
                "contract": ["GOLD"],
                "mm_long": [100],
                "mm_short": [50],
                "other_long": [10],
                "other_short": [10],
                "comm_long": [10],
                "comm_short": [10],
                "nonrep_long": [5],
                "nonrep_short": [5],
                "open_interest": [200],
            }
        )
    )

    # Re-init samme DB
    store2 = DataStore(db_path)
    df = store2.get_cot("GOLD", report="disaggregated")
    assert len(df) == 1
    assert df["released_at"].iloc[0] == "2024-05-03 21:00:00"


def test_migration_aaii_adds_released_at(tmp_path: Path) -> None:
    """AAII-migrasjon: kolonnen + backfill via 1d @ 14:00 UTC."""
    db_path = tmp_path / "legacy.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE aaii_sentiment (
                date TEXT NOT NULL PRIMARY KEY,
                bullish_pct REAL,
                neutral_pct REAL,
                bearish_pct REAL,
                bull_bear_spread REAL
            )
        """)
        conn.execute("INSERT INTO aaii_sentiment VALUES ('2024-05-01', 40.0, 30.0, 30.0, 10.0)")
        conn.commit()

    DataStore(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT released_at FROM aaii_sentiment")
        # 2024-05-01 (onsdag) + 1 dag @ 14:00 = 2024-05-02 14:00:00
        assert cursor.fetchone()[0] == "2024-05-02 14:00:00"


# ---------------------------------------------------------------------------
# Auto-populer på append
# ---------------------------------------------------------------------------


def test_append_cot_disaggregated_auto_populates_released_at(tmp_path: Path) -> None:
    """append uten released_at-kolonne skal beregne den selv."""
    store = DataStore(tmp_path / "bedrock.db")
    store.append_cot_disaggregated(
        pd.DataFrame(
            {
                "report_date": [pd.Timestamp("2024-04-30")],  # tirsdag
                "contract": ["GOLD"],
                "mm_long": [100],
                "mm_short": [50],
                "other_long": [10],
                "other_short": [10],
                "comm_long": [10],
                "comm_short": [10],
                "nonrep_long": [5],
                "nonrep_short": [5],
                "open_interest": [200],
            }
        )
    )

    df = store.get_cot("GOLD", report="disaggregated")
    assert df["released_at"].iloc[0] == cot_released_at_iso(pd.Timestamp("2024-04-30"))


def test_append_cot_euronext_auto_populates_released_at(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    store.append_cot_euronext(
        pd.DataFrame(
            {
                "report_date": [pd.Timestamp("2024-04-30")],
                "contract": ["euronext milling wheat"],
                "mm_long": [100],
                "mm_short": [50],
                "open_interest": [200],
            }
        )
    )
    df = store.get_cot_euronext("euronext milling wheat")
    assert df["released_at"].iloc[0] == cot_released_at_iso(pd.Timestamp("2024-04-30"))


def test_append_aaii_auto_populates_released_at(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    store.append_aaii_sentiment(
        pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-05-01")],  # onsdag
                "bullish_pct": [40.0],
                "neutral_pct": [30.0],
                "bearish_pct": [30.0],
                "bull_bear_spread": [10.0],
            }
        )
    )
    df = store.get_aaii_sentiment()
    assert df["released_at"].iloc[0] == aaii_released_at_iso(pd.Timestamp("2024-05-01"))


# ---------------------------------------------------------------------------
# Eksplisitt released_at bevares
# ---------------------------------------------------------------------------


def test_append_cot_with_explicit_released_at_round_trip(tmp_path: Path) -> None:
    """Hvis caller leverer released_at eksplisitt, skal den bevares."""
    store = DataStore(tmp_path / "bedrock.db")
    explicit = "2024-05-03 18:30:00"  # Egendefinert override
    store.append_cot_disaggregated(
        pd.DataFrame(
            {
                "report_date": [pd.Timestamp("2024-04-30")],
                "contract": ["GOLD"],
                "mm_long": [100],
                "mm_short": [50],
                "other_long": [10],
                "other_short": [10],
                "comm_long": [10],
                "comm_short": [10],
                "nonrep_long": [5],
                "nonrep_short": [5],
                "open_interest": [200],
                "released_at": [explicit],
            }
        )
    )
    df = store.get_cot("GOLD", report="disaggregated")
    assert df["released_at"].iloc[0] == explicit
