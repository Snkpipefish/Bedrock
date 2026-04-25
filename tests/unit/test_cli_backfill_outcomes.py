"""Tester for `bedrock backfill outcomes` (Fase 10 ADR-005)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.backfill import (
    _compute_outcomes,
    _parse_horizons,
    outcomes_cmd,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------
# _parse_horizons
# ---------------------------------------------------------------------


def test_parse_horizons_basic() -> None:
    assert _parse_horizons("30,90") == [30, 90]


def test_parse_horizons_with_whitespace() -> None:
    assert _parse_horizons(" 30 , 60 , 90 ") == [30, 60, 90]


def test_parse_horizons_single() -> None:
    assert _parse_horizons("30") == [30]


def test_parse_horizons_empty_raises() -> None:
    import click

    with pytest.raises(click.UsageError):
        _parse_horizons("")


def test_parse_horizons_negative_raises() -> None:
    import click

    with pytest.raises(click.UsageError, match="positiv"):
        _parse_horizons("30,-1")


def test_parse_horizons_zero_raises() -> None:
    import click

    with pytest.raises(click.UsageError, match="positiv"):
        _parse_horizons("0,30")


def test_parse_horizons_non_int_raises() -> None:
    import click

    with pytest.raises(click.UsageError, match="Ugyldig"):
        _parse_horizons("30,abc")


# ---------------------------------------------------------------------
# _compute_outcomes
# ---------------------------------------------------------------------


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, name="close")


def test_compute_outcomes_basic_30d() -> None:
    # 100 → 110 over 30 bars; min underveis = 95
    values = [100.0] + [95.0] * 5 + [105.0] * 24 + [110.0]
    df = _compute_outcomes("Gold", _series(values), horizon_days=30)
    assert len(df) == 1  # bare ref_date=t=0 har full 30-day window
    assert df["forward_return_pct"].iloc[0] == pytest.approx(10.0)
    assert df["max_drawdown_pct"].iloc[0] == pytest.approx(-5.0)


def test_compute_outcomes_negative_return() -> None:
    values = [100.0] + [99.0] * 29 + [80.0]
    df = _compute_outcomes("Gold", _series(values), horizon_days=30)
    assert df["forward_return_pct"].iloc[0] == pytest.approx(-20.0)
    assert df["max_drawdown_pct"].iloc[0] == pytest.approx(-20.0)


def test_compute_outcomes_drops_short_history() -> None:
    df = _compute_outcomes("Gold", _series([100.0, 101.0]), horizon_days=30)
    assert df.empty


def test_compute_outcomes_excludes_incomplete_window() -> None:
    """Series på 100 bars med horizon 30 → 70 outcomes (siste 30 bars
    har ikke full forward-vindu)."""
    values = [100.0 + i for i in range(100)]
    df = _compute_outcomes("Gold", _series(values), horizon_days=30)
    assert len(df) == 70


def test_compute_outcomes_skips_zero_close() -> None:
    """close_t = 0 ville gitt division-by-zero — skipper slike rader."""
    values = [100.0, 0.0, 100.0] + [102.0] * 30
    df = _compute_outcomes("Gold", _series(values), horizon_days=30)
    # ref_date=t=0 OK (close=100), ref_date=t=1 skip (close=0), ref_date=t=2 OK
    assert len(df) == 2
    # Etter t=2 har vi bare 30 bars, dvs. t+30 = bar 32. n=33. n-h = 3, så range(3) = [0,1,2]
    # Bar 1 hoppes over → 2 rader.


def test_compute_outcomes_columns() -> None:
    values = [100.0] * 32
    df = _compute_outcomes("Gold", _series(values), horizon_days=30)
    assert list(df.columns) == [
        "instrument",
        "ref_date",
        "horizon_days",
        "forward_return_pct",
        "max_drawdown_pct",
    ]
    assert (df["instrument"] == "Gold").all()
    assert (df["horizon_days"] == 30).all()


def test_compute_outcomes_flat_series_zero_return() -> None:
    df = _compute_outcomes("Gold", _series([100.0] * 35), horizon_days=30)
    assert (df["forward_return_pct"] == 0.0).all()
    assert (df["max_drawdown_pct"] == 0.0).all()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def _seed_prices(db: Path, instrument: str, n: int = 200) -> None:
    """Lag DB med n daglige priser stigende fra 100 til 100+n."""
    db.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db)
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=n, freq="D"),
            "close": [100.0 + i for i in range(n)],
        }
    )
    store.append_prices(instrument, "D1", df)


def test_cli_dry_run(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(
        outcomes_cmd,
        [
            "--instrument",
            "Gold",
            "--horizons",
            "30,90",
            "--db",
            str(db),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "horizon_days=30" in result.output
    assert "horizon_days=90" in result.output


def test_cli_writes_outcomes(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    _seed_prices(db, "Gold", n=200)
    runner = CliRunner()
    result = runner.invoke(
        outcomes_cmd,
        [
            "--instrument",
            "Gold",
            "--horizons",
            "30,90",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    store = DataStore(db)
    df30 = store.get_outcomes("Gold", horizon_days=30)
    df90 = store.get_outcomes("Gold", horizon_days=90)
    assert len(df30) == 170  # 200 - 30
    assert len(df90) == 110  # 200 - 90


def test_cli_missing_db_errors(tmp_path: Path) -> None:
    db = tmp_path / "no_such.db"
    runner = CliRunner()
    result = runner.invoke(
        outcomes_cmd,
        ["--instrument", "Gold", "--db", str(db)],
    )
    assert result.exit_code != 0
    assert "DB not found" in result.output


def test_cli_missing_instrument_skips(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    _seed_prices(db, "Gold", n=200)
    runner = CliRunner()
    result = runner.invoke(
        outcomes_cmd,
        [
            "--instrument",
            "Silver",  # ikke seedet
            "--db",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output.lower() or "ingen prises-data" in result.output


def test_cli_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    _seed_prices(db, "Gold", n=200)
    runner = CliRunner()
    runner.invoke(outcomes_cmd, ["--instrument", "Gold", "--db", str(db)])
    runner.invoke(outcomes_cmd, ["--instrument", "Gold", "--db", str(db)])
    store = DataStore(db)
    df = store.get_outcomes("Gold", horizon_days=30)
    assert len(df) == 170  # ikke 340
