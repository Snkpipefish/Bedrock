"""Tester for `bedrock signals` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

# Registrer drivere
import bedrock.engine.drivers  # noqa: F401
from bedrock.cli.__main__ import cli
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _wavy_prices(n: int = 300, base: float = 100.0) -> np.ndarray:
    t = np.arange(n)
    return base + t * 0.3 + 20.0 * np.sin(t / 8.0)


@pytest.fixture
def db_with_prices(tmp_path: Path) -> Path:
    db = tmp_path / "bedrock.db"
    store = DataStore(db)
    n = 300
    ts = pd.date_range("2020-01-01", periods=n, freq="D")
    close = _wavy_prices(n)
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": [1000.0] * n,
        }
    )
    store.append_prices("Gold", "D1", df)
    return db


@pytest.fixture
def configs_dir(tmp_path: Path) -> tuple[Path, Path]:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "family_financial.yaml").write_text(
        dedent(
            """\
            aggregation: weighted_horizon
            horizons:
              SWING:
                family_weights: {trend: 1.0}
                max_score: 5.0
                min_score_publish: 0.5
            families:
              trend:
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.75, min_families: 1}
              A:      {min_pct_of_max: 0.55, min_families: 1}
              B:      {min_pct_of_max: 0.35, min_families: 1}
            """
        )
    )
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "gold.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
            """
        )
    )
    return defaults, insts


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------


def test_signals_human_readable_output(
    runner: CliRunner, db_with_prices: Path, configs_dir
) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Instrument: Gold" in result.output
    assert "BUY" in result.output
    assert "SELL" in result.output
    assert "SWING" in result.output
    assert "score=" in result.output
    assert "grade=" in result.output


def test_signals_json_output(runner: CliRunner, db_with_prices: Path, configs_dir) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["instrument"] == "Gold"
    assert "entries" in payload
    assert len(payload["entries"]) >= 2


def test_signals_filters_horizon(runner: CliRunner, db_with_prices: Path, configs_dir) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--horizon",
            "SWING",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert all(e["horizon"] == "swing" for e in payload["entries"])


def test_signals_filters_direction(runner: CliRunner, db_with_prices: Path, configs_dir) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--direction",
            "BUY",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # JSON-utgang bruker enum-value (lowercase)
    assert all(e["direction"] == "buy" for e in payload["entries"])


def test_signals_missing_db_errors(runner: CliRunner, tmp_path: Path, configs_dir) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--db",
            str(tmp_path / "nope.db"),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )
    assert result.exit_code != 0
    assert "DB-fil finnes ikke" in result.output


def test_signals_unknown_instrument_errors(
    runner: CliRunner, db_with_prices: Path, configs_dir
) -> None:
    defaults, insts = configs_dir
    result = runner.invoke(
        cli,
        [
            "signals",
            "Platinum",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )
    assert result.exit_code != 0
    assert "Platinum" in result.output or "no YAML" in result.output


def test_signals_snapshot_written(
    runner: CliRunner, db_with_prices: Path, configs_dir, tmp_path: Path
) -> None:
    defaults, insts = configs_dir
    snap = tmp_path / "gold_snap.json"
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--snapshot",
            str(snap),
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )
    assert result.exit_code == 0, result.output
    assert snap.exists()
    assert "Snapshot written" in result.output


def test_signals_no_snapshot_write_flag(
    runner: CliRunner, db_with_prices: Path, configs_dir, tmp_path: Path
) -> None:
    defaults, insts = configs_dir
    snap = tmp_path / "should_not_exist.json"
    result = runner.invoke(
        cli,
        [
            "signals",
            "Gold",
            "--snapshot",
            str(snap),
            "--no-snapshot-write",
            "--db",
            str(db_with_prices),
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )
    assert result.exit_code == 0, result.output
    assert not snap.exists()


def test_signals_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["signals", "--help"])
    assert result.exit_code == 0
    assert "INSTRUMENT_ID" in result.output
    assert "--horizon" in result.output
    assert "--json" in result.output
