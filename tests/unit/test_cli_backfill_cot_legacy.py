"""Tester for `bedrock backfill cot-legacy` CLI."""

from __future__ import annotations

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


def _sample_legacy_df(n: int = 2) -> pd.DataFrame:
    dates = ["2020-01-07", "2020-01-14"][:n]
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": ["GOLD - COMMODITY EXCHANGE INC."] * n,
            "noncomm_long": [180000 + i * 1000 for i in range(n)],
            "noncomm_short": [65000] * n,
            "comm_long": [200000] * n,
            "comm_short": [300000] * n,
            "nonrep_long": [9000] * n,
            "nonrep_short": [4000] * n,
            "open_interest": [520000] * n,
        }
    )


def test_backfill_cot_legacy_writes_to_db(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch(
        "bedrock.cli.backfill.fetch_cot_legacy", return_value=_sample_legacy_df(2)
    ):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-legacy",
                "--contract",
                "GOLD - COMMODITY EXCHANGE INC.",
                "--from",
                "2020-01-01",
                "--to",
                "2020-01-31",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Wrote 2" in result.output

    store = DataStore(db)
    out = store.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="legacy")
    assert len(out) == 2
    # Må IKKE havne i disaggregated-tabellen
    assert not store.has_cot("GOLD - COMMODITY EXCHANGE INC.", report="disaggregated")


def test_backfill_cot_legacy_dry_run_shows_legacy_url(
    runner: CliRunner, tmp_path: Path
) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_cot_legacy") as mock_fetch:
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-legacy",
                "--contract",
                "GOLD - COMMODITY EXCHANGE INC.",
                "--from",
                "2020-01-01",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "6dca-aqww" in result.output  # legacy datasett-ID
    assert "72hh-3qpy" not in result.output  # ikke disagg
    mock_fetch.assert_not_called()
    assert not db.exists()


def test_backfill_cot_legacy_empty_result_is_not_error(
    runner: CliRunner, tmp_path: Path
) -> None:
    db = tmp_path / "bedrock.db"
    with patch(
        "bedrock.cli.backfill.fetch_cot_legacy",
        return_value=pd.DataFrame(columns=_sample_legacy_df(1).columns),
    ):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-legacy",
                "--contract",
                "UNKNOWN",
                "--from",
                "2020-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "No rows to write" in result.output
    assert not db.exists()


def test_backfill_cot_legacy_requires_contract(runner: CliRunner) -> None:
    result = runner.invoke(
        cli, ["backfill", "cot-legacy", "--from", "2020-01-01"]
    )
    assert result.exit_code != 0


def test_backfill_cot_legacy_help_shows_in_parent(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "cot-legacy" in result.output
    assert "cot-disaggregated" in result.output
