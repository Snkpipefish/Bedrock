"""Tester for `bedrock backfill fundamentals` CLI."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli
from bedrock.data.store import DataStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _clean_fred_env():
    saved = os.environ.pop("FRED_API_KEY", None)
    yield
    if saved is not None:
        os.environ["FRED_API_KEY"] = saved


def _sample_fred_df(series_id: str = "DGS10", n: int = 3) -> pd.DataFrame:
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"][:n]
    return pd.DataFrame(
        {
            "series_id": [series_id] * n,
            "date": dates,
            "value": [3.95, 3.97, 4.01][:n],
        }
    )


# ---------------------------------------------------------------------------
# Normal flow with explicit --api-key
# ---------------------------------------------------------------------------


def test_backfill_fundamentals_with_cli_api_key(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_fred_series", return_value=_sample_fred_df(n=3)):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--api-key",
                "my_key_from_cli",
                "--from",
                "2024-01-01",
                "--to",
                "2024-01-05",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "DGS10" in result.output
    assert "3 row" in result.output

    store = DataStore(db)
    out = store.get_fundamentals("DGS10")
    assert len(out) == 3


def test_backfill_fundamentals_with_env_var(runner: CliRunner, tmp_path: Path) -> None:
    """Uten --api-key skal FRED_API_KEY env-var brukes."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "env_key_abc"

    called = {}

    def capture(series_id, api_key, from_date, to_date):
        called["api_key"] = api_key
        return _sample_fred_df(n=1)

    with patch("bedrock.cli.backfill.fetch_fred_series", side_effect=capture):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert called["api_key"] == "env_key_abc"


def test_backfill_fundamentals_no_key_no_dry_run_errors(runner: CliRunner, tmp_path: Path) -> None:
    """Uten noen nøkkel OG uten --dry-run skal CLI feile tydelig."""
    db = tmp_path / "bedrock.db"
    # Sørg for at heller ikke secrets-fila har nøkkel
    with patch("bedrock.cli.backfill.get_secret", return_value=None):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code != 0
    assert "FRED API-n\u00f8kkel ikke funnet" in result.output
    assert not db.exists()


def test_backfill_fundamentals_cli_key_overrides_env(runner: CliRunner, tmp_path: Path) -> None:
    """CLI-arg vinner over env-var."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "env_loses"

    called = {}

    def capture(series_id, api_key, from_date, to_date):
        called["api_key"] = api_key
        return _sample_fred_df(n=1)

    with patch("bedrock.cli.backfill.fetch_fred_series", side_effect=capture):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--api-key",
                "cli_wins",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert called["api_key"] == "cli_wins"


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_masks_api_key_in_output(runner: CliRunner, tmp_path: Path) -> None:
    """--dry-run viser URL men aldri en ekte api_key-verdi."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "SECRET_KEY_DO_NOT_LEAK"

    with patch("bedrock.cli.backfill.fetch_fred_series") as mock_fetch:
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--from",
                "2024-01-01",
                "--to",
                "2024-01-05",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "stlouisfed.org" in result.output
    assert "api_key=***" in result.output
    # Aller viktigst: den ekte nøkkelen skal IKKE vises
    assert "SECRET_KEY_DO_NOT_LEAK" not in result.output
    mock_fetch.assert_not_called()
    assert not db.exists()


def test_dry_run_works_without_api_key(runner: CliRunner, tmp_path: Path) -> None:
    """--dry-run skal virke selv uten nøkkel satt."""
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.get_secret", return_value=None):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "DGS10",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "MISSING" in result.output


def test_dry_run_reports_key_resolved_when_present(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "ok_key"

    result = runner.invoke(
        cli,
        [
            "backfill",
            "fundamentals",
            "--series-id",
            "DGS10",
            "--from",
            "2024-01-01",
            "--db",
            str(db),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "API-key: resolved" in result.output


# ---------------------------------------------------------------------------
# Argument-validering
# ---------------------------------------------------------------------------


def test_backfill_fundamentals_empty_result_ok(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    empty = pd.DataFrame(columns=["series_id", "date", "value"])
    with patch("bedrock.cli.backfill.fetch_fred_series", return_value=empty):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--series-id",
                "UNKNOWN",
                "--api-key",
                "k",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    # Tom fetch → OK med 0 rader, ingen DB-fil opprettes (lat DataStore)
    assert "0 row" in result.output
    assert not db.exists()


def test_backfill_fundamentals_requires_series_id(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        ["backfill", "fundamentals", "--from", "2024-01-01", "--api-key", "k"],
    )
    assert result.exit_code != 0


def test_backfill_fundamentals_help_shows_in_parent(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "fundamentals" in result.output
