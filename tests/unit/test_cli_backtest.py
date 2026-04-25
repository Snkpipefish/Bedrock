"""Tester for `bedrock backtest run` CLI (Fase 11 session 62)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.backtest import backtest
from bedrock.data.store import DataStore


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    store = DataStore(tmp_path / "bedrock.db")
    n = 50
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                "forward_return_pct": [3.5 if i % 2 == 0 else -1.0 for i in range(n)],
                "max_drawdown_pct": [-2.0] * n,
            }
        )
    )
    return tmp_path / "bedrock.db"


def test_run_markdown_to_stdout(seeded_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        ["run", "--instrument", "Gold", "--horizon-days", "30", "--db", str(seeded_db)],
    )
    assert result.exit_code == 0, result.output
    assert "# Backtest: Gold · h=30d" in result.output
    assert "Antall signaler:** 50" in result.output


def test_run_json_to_stdout(seeded_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Gold",
            "--horizon-days",
            "30",
            "--db",
            str(seeded_db),
            "--report",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["config"]["instrument"] == "Gold"
    assert parsed["report"]["n_signals"] == 50


def test_run_to_file(seeded_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "reports" / "gold-30d.md"
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Gold",
            "--horizon-days",
            "30",
            "--db",
            str(seeded_db),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Antall signaler:** 50" in content


def test_run_missing_db(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Gold",
            "--horizon-days",
            "30",
            "--db",
            str(tmp_path / "nope.db"),
        ],
    )
    assert result.exit_code != 0
    assert "DB ikke funnet" in result.output


def test_run_window_filter(seeded_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Gold",
            "--horizon-days",
            "30",
            "--from",
            "2024-01-10",
            "--to",
            "2024-01-20",
            "--db",
            str(seeded_db),
        ],
    )
    assert result.exit_code == 0, result.output
    # Jan 10..20 inkl = 11 dager
    assert "Antall signaler:** 11" in result.output


def test_run_threshold_pct(seeded_db: Path) -> None:
    runner = CliRunner()
    # Med terskel 100 → 0 hits (3.5% er ikke nok)
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Gold",
            "--horizon-days",
            "30",
            "--threshold-pct",
            "100",
            "--db",
            str(seeded_db),
            "--report",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["report"]["n_hits"] == 0


def test_run_unknown_instrument_empty_message(seeded_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        backtest,
        [
            "run",
            "--instrument",
            "Silver",
            "--horizon-days",
            "30",
            "--db",
            str(seeded_db),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Ingen outcomes funnet" in result.output
