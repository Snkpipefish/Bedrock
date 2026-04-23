"""Tester for `bedrock backfill cot-disaggregated` CLI."""

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


def _sample_cot_df(n: int = 2) -> pd.DataFrame:
    dates = ["2024-01-02", "2024-01-09"][:n]
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": ["GOLD - COMMODITY EXCHANGE INC."] * n,
            "mm_long": [150000 + i * 1000 for i in range(n)],
            "mm_short": [60000] * n,
            "other_long": [30000] * n,
            "other_short": [25000] * n,
            "comm_long": [200000] * n,
            "comm_short": [300000] * n,
            "nonrep_long": [8000] * n,
            "nonrep_short": [3000] * n,
            "open_interest": [500000] * n,
        }
    )


def test_backfill_cot_writes_to_db(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch(
        "bedrock.cli.backfill.fetch_cot_disaggregated", return_value=_sample_cot_df(2)
    ):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-disaggregated",
                "--contract",
                "GOLD - COMMODITY EXCHANGE INC.",
                "--from",
                "2024-01-01",
                "--to",
                "2024-01-15",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Wrote 2" in result.output

    store = DataStore(db)
    out = store.get_cot("GOLD - COMMODITY EXCHANGE INC.")
    assert len(out) == 2


def test_backfill_cot_empty_result_is_not_error(runner: CliRunner, tmp_path: Path) -> None:
    """Tom respons fra Socrata (kontrakten har ikke data i perioden) er OK."""
    db = tmp_path / "bedrock.db"
    with patch(
        "bedrock.cli.backfill.fetch_cot_disaggregated",
        return_value=pd.DataFrame(
            columns=[
                "report_date",
                "contract",
                "mm_long",
                "mm_short",
                "other_long",
                "other_short",
                "comm_long",
                "comm_short",
                "nonrep_long",
                "nonrep_short",
                "open_interest",
            ]
        ),
    ):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-disaggregated",
                "--contract",
                "UNKNOWN",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "No rows to write" in result.output
    # DB-fila blir ikke opprettet når det ikke er noe å skrive
    assert not db.exists()


def test_backfill_cot_dry_run_shows_url_and_soql(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_cot_disaggregated") as mock_fetch:
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-disaggregated",
                "--contract",
                "GOLD - COMMODITY EXCHANGE INC.",
                "--from",
                "2024-01-01",
                "--to",
                "2024-01-15",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "publicreporting.cftc.gov" in result.output
    assert "GOLD - COMMODITY EXCHANGE INC." in result.output
    assert "2024-01-01" in result.output
    assert "2024-01-15" in result.output
    # Ingen fetch-kall, ingen DB-opprettelse
    mock_fetch.assert_not_called()
    assert not db.exists()


def test_backfill_cot_requires_contract(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        ["backfill", "cot-disaggregated", "--from", "2024-01-01"],
    )
    assert result.exit_code != 0
    assert "contract" in result.output.lower()


def test_backfill_cot_requires_from_date(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        ["backfill", "cot-disaggregated", "--contract", "X"],
    )
    assert result.exit_code != 0


def test_backfill_cot_help_visible_from_parent(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "cot-disaggregated" in result.output
