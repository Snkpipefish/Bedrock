"""Tester for analog_outcomes-støtte i DataStore (Fase 10 ADR-005).

Dekker:
- Pydantic-skjema for AnalogOutcomeRow (forward_return påkrevd, drawdown valgfri)
- append_outcomes + get_outcomes (round-trip, all/filter/batch-lookup)
- Idempotens via PRIMARY KEY (instrument, ref_date, horizon_days)
- has_outcomes med valgfri horizon_days-filter
- Tom DataFrame returneres ved misstreff, ikke exception
- Empty ref_dates returnerer empty frame uten DB-hit
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from bedrock.data.schemas import (
    ANALOG_OUTCOMES_COLS,
    DDL_ANALOG_OUTCOMES,
    TABLE_ANALOG_OUTCOMES,
    AnalogOutcomeRow,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------
# Pydantic-schema
# ---------------------------------------------------------------------


def test_outcome_row_minimal() -> None:
    row = AnalogOutcomeRow(
        instrument="Gold",
        ref_date=date(2024, 1, 15),
        horizon_days=30,
        forward_return_pct=2.7,
    )
    assert row.max_drawdown_pct is None


def test_outcome_row_full() -> None:
    row = AnalogOutcomeRow(
        instrument="Corn",
        ref_date=date(2023, 5, 1),
        horizon_days=90,
        forward_return_pct=-1.2,
        max_drawdown_pct=-4.8,
    )
    assert row.max_drawdown_pct == pytest.approx(-4.8)


def test_outcome_row_rejects_zero_horizon() -> None:
    with pytest.raises(ValidationError):
        AnalogOutcomeRow(
            instrument="Gold",
            ref_date=date(2024, 1, 1),
            horizon_days=0,
            forward_return_pct=0.0,
        )


def test_outcome_row_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        AnalogOutcomeRow(
            instrument="Gold",
            ref_date=date(2024, 1, 1),
            horizon_days=30,
            forward_return_pct=1.0,
            extra=1,
        )


# ---------------------------------------------------------------------
# DataStore round-trip
# ---------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def _df(
    instrument: str = "Gold",
    horizon: int = 30,
    dates: list[str] | None = None,
    returns: list[float] | None = None,
    drawdowns: list[float | None] | None = None,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-15", "2024-02-12", "2024-03-04"]
    n = len(dates)
    if returns is None:
        returns = [1.5, -0.4, 3.2]
    if drawdowns is None:
        drawdowns = [-0.8, -2.1, -0.3]
    return pd.DataFrame(
        {
            "instrument": [instrument] * n,
            "ref_date": dates,
            "horizon_days": [horizon] * n,
            "forward_return_pct": returns,
            "max_drawdown_pct": drawdowns,
        }
    )


def test_init_creates_outcomes_table(store: DataStore) -> None:
    import sqlite3

    conn = sqlite3.connect(store._db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_ANALOG_OUTCOMES,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "analog_outcomes" in DDL_ANALOG_OUTCOMES


def test_append_and_get_all(store: DataStore) -> None:
    n = store.append_outcomes(_df())
    assert n == 3

    df = store.get_outcomes("Gold")
    assert len(df) == 3
    assert list(df.columns) == list(ANALOG_OUTCOMES_COLS)
    assert df["ref_date"].iloc[0] == pd.Timestamp("2024-01-15")
    assert df["forward_return_pct"].iloc[2] == pytest.approx(3.2)
    assert df["max_drawdown_pct"].iloc[1] == pytest.approx(-2.1)


def test_append_idempotent(store: DataStore) -> None:
    store.append_outcomes(_df())
    df2 = _df(returns=[99.0, 99.0, 99.0])
    store.append_outcomes(df2)
    out = store.get_outcomes("Gold")
    assert len(out) == 3
    assert (out["forward_return_pct"] == 99.0).all()


def test_get_with_horizon_filter(store: DataStore) -> None:
    store.append_outcomes(_df(horizon=30))
    store.append_outcomes(_df(horizon=90, returns=[5.0, 5.0, 5.0]))

    df30 = store.get_outcomes("Gold", horizon_days=30)
    df90 = store.get_outcomes("Gold", horizon_days=90)

    assert len(df30) == 3
    assert len(df90) == 3
    assert (df30["horizon_days"] == 30).all()
    assert (df90["forward_return_pct"] == 5.0).all()


def test_get_with_ref_dates_batch(store: DataStore) -> None:
    store.append_outcomes(_df())
    # Spør om to av tre datoer + én som ikke finnes
    out = store.get_outcomes(
        "Gold",
        ref_dates=["2024-01-15", "2024-03-04", "2030-01-01"],
    )
    assert len(out) == 2
    dates = out["ref_date"].dt.strftime("%Y-%m-%d").tolist()
    assert "2024-01-15" in dates
    assert "2024-03-04" in dates


def test_get_empty_ref_dates_short_circuits(store: DataStore) -> None:
    store.append_outcomes(_df())
    out = store.get_outcomes("Gold", ref_dates=[])
    assert out.empty
    assert list(out.columns) == list(ANALOG_OUTCOMES_COLS)


def test_get_no_match_returns_empty(store: DataStore) -> None:
    store.append_outcomes(_df())
    out = store.get_outcomes("Silver")  # ikke skrevet
    assert out.empty


def test_get_outcomes_accepts_timestamp_in_ref_dates(store: DataStore) -> None:
    store.append_outcomes(_df())
    out = store.get_outcomes(
        "Gold",
        ref_dates=[pd.Timestamp("2024-01-15"), pd.Timestamp("2024-02-12")],
    )
    assert len(out) == 2


def test_max_drawdown_optional(store: DataStore) -> None:
    df = _df(drawdowns=[None, None, None])
    store.append_outcomes(df)
    out = store.get_outcomes("Gold")
    assert out["max_drawdown_pct"].isna().all()


def test_has_outcomes(store: DataStore) -> None:
    assert store.has_outcomes("Gold") is False
    store.append_outcomes(_df(horizon=30))
    assert store.has_outcomes("Gold") is True
    assert store.has_outcomes("Gold", horizon_days=30) is True
    assert store.has_outcomes("Gold", horizon_days=90) is False


def test_append_missing_required_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame(
        {
            "instrument": ["Gold"],
            "ref_date": ["2024-01-15"],
            # mangler horizon_days, forward_return_pct
        }
    )
    with pytest.raises(ValueError, match="missing"):
        store.append_outcomes(bad)


def test_isolation_per_instrument(store: DataStore) -> None:
    store.append_outcomes(_df(instrument="Gold"))
    store.append_outcomes(_df(instrument="Corn", returns=[10.0, 10.0, 10.0]))
    g = store.get_outcomes("Gold")
    c = store.get_outcomes("Corn")
    assert (g["instrument"] == "Gold").all()
    assert (c["forward_return_pct"] == 10.0).all()


def test_pk_includes_horizon(store: DataStore) -> None:
    """Same (instrument, ref_date) MED ulik horizon skal gi separate rader."""
    store.append_outcomes(_df(horizon=30))
    store.append_outcomes(_df(horizon=90))
    out = store.get_outcomes("Gold")
    assert len(out) == 6
    assert sorted(out["horizon_days"].unique()) == [30, 90]
