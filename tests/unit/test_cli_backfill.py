"""Tester for `bedrock backfill prices` CLI.

Bruker click's CliRunner. Fetcher er mocket — ingen live network.
Databasen skrives til pytest-tmp, isolert pr test.
"""

from __future__ import annotations

from datetime import date
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


def _sample_bars(n: int = 3) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02", periods=n, freq="D")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


# ---------------------------------------------------------------------------
# Normal flow
# ---------------------------------------------------------------------------


def test_backfill_prices_writes_to_db(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_prices", return_value=_sample_bars(3)):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--source",
                "stooq",
                "--instrument",
                "Gold",
                "--ticker",
                "xauusd",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Wrote 3 bars" in result.output

    # Verifiser faktisk skrevet til DB
    store = DataStore(db)
    out = store.get_prices("Gold", "D1")
    assert len(out) == 3


def test_backfill_creates_parent_dir_for_db(runner: CliRunner, tmp_path: Path) -> None:
    """--db path med ikke-eksisterende forelder skal få katalog opprettet."""
    db = tmp_path / "nested" / "subdir" / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_prices", return_value=_sample_bars(1)):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--source",
                "stooq",
                "--instrument",
                "Gold",
                "--ticker",
                "xauusd",
                "--from",
                "2024-01-02",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert db.exists()


def test_backfill_defaults_to_today_when_to_missing(runner: CliRunner, tmp_path: Path) -> None:
    """Uten --to skal default være i dag."""
    db = tmp_path / "bedrock.db"
    called_with: dict = {}

    def fake_fetch(ticker: str, from_date: date, to_date: date, interval: str = "d"):
        called_with["from"] = from_date
        called_with["to"] = to_date
        return _sample_bars(1)

    with patch("bedrock.cli.backfill.fetch_prices", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--source",
                "stooq",
                "--instrument",
                "Gold",
                "--ticker",
                "xauusd",
                "--from",
                "2024-01-02",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert called_with["to"] == date.today()


def test_backfill_respects_tf_option(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_prices", return_value=_sample_bars(1)):
        runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--source",
                "stooq",
                "--instrument",
                "Gold",
                "--ticker",
                "xauusd",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-02",
                "--tf",
                "4H",
                "--db",
                str(db),
            ],
        )

    store = DataStore(db)
    assert store.has_prices("Gold", "4H")
    assert not store.has_prices("Gold", "D1")


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_shows_url_without_http_call(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_prices") as mock_fetch:
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--source",
                "stooq",
                "--instrument",
                "Gold",
                "--ticker",
                "xauusd",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "stooq.com" in result.output
    assert "s=xauusd" in result.output
    assert "d1=20240102" in result.output
    assert "d2=20240104" in result.output

    # Fetch skal ikke være kalt
    mock_fetch.assert_not_called()

    # DB skal ikke være opprettet
    assert not db.exists()


def test_dry_run_shows_destination_db_path(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "somewhere" / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "prices",
            "--source",
            "stooq",
            "--instrument",
            "EURUSD",
            "--ticker",
            "eurusd",
            "--from",
            "2024-01-02",
            "--db",
            str(db),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "EURUSD" in result.output
    assert str(db) in result.output
    # Dir skal heller ikke opprettes under dry-run
    assert not db.parent.exists()


# ---------------------------------------------------------------------------
# Argument-validering
# ---------------------------------------------------------------------------


def test_missing_instrument_errors(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        ["backfill", "prices", "--ticker", "xauusd", "--from", "2024-01-02"],
    )
    assert result.exit_code != 0
    assert "instrument" in result.output.lower()


def test_missing_from_date_errors(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        ["backfill", "prices", "--instrument", "Gold", "--ticker", "xauusd"],
    )
    assert result.exit_code != 0


def test_invalid_date_format_errors(runner: CliRunner) -> None:
    result = runner.invoke(
        cli,
        [
            "backfill",
            "prices",
            "--source",
            "stooq",
            "--instrument",
            "Gold",
            "--ticker",
            "xauusd",
            "--from",
            "not-a-date",
        ],
    )
    assert result.exit_code != 0


def test_cli_help_mentions_backfill(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "backfill" in result.output
