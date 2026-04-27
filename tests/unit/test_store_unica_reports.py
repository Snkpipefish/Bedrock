"""Tester for unica_reports-støtte i DataStore (sub-fase 12.5+ session 112)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _unica_df(
    dates: list[str] | None = None,
    base_mix_sugar: float = 50.0,
    base_crush: float = 600_000.0,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-04-15", "2026-04-30", "2026-05-15"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "position_date": [f"{d[8:10]}/{d[5:7]}/{d[:4]}" for d in dates],
            "period": [f"quinzena {i}" for i in range(n)],
            "crop_year": ["2025/2026"] * n,
            "mix_sugar_pct": [base_mix_sugar + i for i in range(n)],
            "mix_sugar_pct_prev": [base_mix_sugar - 2 + i for i in range(n)],
            "mix_ethanol_pct": [100.0 - (base_mix_sugar + i) for i in range(n)],
            "mix_ethanol_pct_prev": [100.0 - (base_mix_sugar - 2 + i) for i in range(n)],
            "crush_kt": [base_crush + 1000 * i for i in range(n)],
            "crush_kt_prev": [base_crush - 5000 + 1000 * i for i in range(n)],
            "crush_yoy_pct": [-2.21 + 0.1 * i for i in range(n)],
            "sugar_production_kt": [50_000.0 + 100 * i for i in range(n)],
            "sugar_production_kt_prev": [49_500.0 + 100 * i for i in range(n)],
            "sugar_production_yoy_pct": [1.0 + 0.1 * i for i in range(n)],
            "ethanol_total_ml": [25_000.0 + 100 * i for i in range(n)],
            "ethanol_total_ml_prev": [24_800.0 + 100 * i for i in range(n)],
            "ethanol_total_yoy_pct": [0.8 + 0.1 * i for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_append_and_get(store: DataStore) -> None:
    store.append_unica_reports(_unica_df())
    df = store.get_unica_reports()
    assert len(df) == 3
    assert df["mix_sugar_pct"].iloc[0] == 50.0
    assert df["crop_year"].iloc[0] == "2025/2026"


def test_last_n(store: DataStore) -> None:
    store.append_unica_reports(_unica_df())
    df = store.get_unica_reports(last_n=2)
    assert len(df) == 2
    assert df["report_date"].iloc[0] == pd.Timestamp("2026-04-30")


def test_dedupe_on_report_date(store: DataStore) -> None:
    """Samme report_date overskrives — UNICA kan revidere."""
    store.append_unica_reports(_unica_df())
    revision = _unica_df(dates=["2026-04-15"], base_mix_sugar=99.99)
    store.append_unica_reports(revision)
    df = store.get_unica_reports()
    assert len(df) == 3
    first = df[df["report_date"] == pd.Timestamp("2026-04-15")].iloc[0]
    assert first["mix_sugar_pct"] == 99.99


def test_returns_empty_when_no_rows(store: DataStore) -> None:
    df = store.get_unica_reports()
    assert df.empty


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"report_date": ["2026-04-15"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_unica_reports(bad)


def test_nullable_fields_preserved(store: DataStore) -> None:
    """Alle felter etter report_date kan være None (PDF-parsing kan
    feile på enkeltsegmenter)."""
    df = pd.DataFrame(
        {
            "report_date": ["2026-04-15"],
            "position_date": [None],
            "period": [None],
            "crop_year": [None],
            "mix_sugar_pct": [None],
            "mix_sugar_pct_prev": [None],
            "mix_ethanol_pct": [None],
            "mix_ethanol_pct_prev": [None],
            "crush_kt": [None],
            "crush_kt_prev": [None],
            "crush_yoy_pct": [None],
            "sugar_production_kt": [None],
            "sugar_production_kt_prev": [None],
            "sugar_production_yoy_pct": [None],
            "ethanol_total_ml": [None],
            "ethanol_total_ml_prev": [None],
            "ethanol_total_yoy_pct": [None],
        }
    )
    store.append_unica_reports(df)
    out = store.get_unica_reports()
    assert len(out) == 1
    assert pd.isna(out["mix_sugar_pct"].iloc[0])


def test_appends_new_dates(store: DataStore) -> None:
    store.append_unica_reports(_unica_df(dates=["2026-04-15", "2026-04-30"]))
    store.append_unica_reports(_unica_df(dates=["2026-05-15", "2026-05-30"]))
    df = store.get_unica_reports()
    assert len(df) == 4


# ---------------------------------------------------------------------------
# has_unica_reports
# ---------------------------------------------------------------------------


def test_has_negative(store: DataStore) -> None:
    assert not store.has_unica_reports()


def test_has_positive(store: DataStore) -> None:
    store.append_unica_reports(_unica_df())
    assert store.has_unica_reports()


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_unica_reports(_unica_df())
    df = DataStore(db).get_unica_reports()
    assert len(df) == 3
