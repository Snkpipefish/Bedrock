"""Tester for `bedrock backfill crop-progress` (PLAN § 7.3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.backfill import crop_progress_cmd
from bedrock.data.store import DataStore


def test_dry_run_default_args_no_db_no_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "bedrock.db"
    # Sørg for ren env (ingen utilsiktet key fra utvikler-shell).
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    # Pek get_secret til en tom secrets-fil så ~/.bedrock/secrets.env ikke leses.
    empty_secrets = tmp_path / "secrets.env"
    empty_secrets.write_text("")
    monkeypatch.setattr("bedrock.config.secrets.DEFAULT_SECRETS_PATH", empty_secrets)

    runner = CliRunner()
    result = runner.invoke(crop_progress_cmd, ["--db", str(db), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    # Default-commodities + 5 år (4 bakover + nåværende)
    assert "CORN" in result.output and "WHEAT" in result.output
    assert "(MISSING)" in result.output
    assert not db.exists()


def test_dry_run_with_env_key_masks_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "bedrock.db"
    monkeypatch.setenv("BEDROCK_NASS_API_KEY", "secret-test-key")
    runner = CliRunner()
    result = runner.invoke(crop_progress_cmd, ["--db", str(db), "--dry-run", "--year", "2026"])
    assert result.exit_code == 0, result.output
    assert "***" in result.output
    assert "secret-test-key" not in result.output
    assert "[2026]" in result.output


def test_dry_run_custom_commodity_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "bedrock.db"
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    empty = tmp_path / "secrets.env"
    empty.write_text("")
    monkeypatch.setattr("bedrock.config.secrets.DEFAULT_SECRETS_PATH", empty)
    runner = CliRunner()
    result = runner.invoke(
        crop_progress_cmd,
        ["--db", str(db), "--dry-run", "--commodity", "CORN", "--year", "2024", "--year", "2025"],
    )
    assert result.exit_code == 0, result.output
    assert "CORN" in result.output
    assert "WHEAT" not in result.output
    assert "[2024, 2025]" in result.output


def test_live_run_writes_to_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Monkey-patcher fetch_crop_progress_api → rader skrives til SQLite."""
    db = tmp_path / "bedrock.db"

    fake_df = pd.DataFrame(
        {
            "week_ending": ["2026-04-13", "2026-04-20", "2026-04-27"],
            "commodity": ["CORN", "CORN", "CORN"],
            "state": ["US", "US", "US"],
            "metric": ["PLANTED", "PLANTED", "PLANTED"],
            "value_pct": [12.0, 24.0, 38.0],
        }
    )

    monkeypatch.setenv("BEDROCK_NASS_API_KEY", "test-key")
    monkeypatch.setattr(
        "bedrock.fetch.nass.fetch_crop_progress_api",
        lambda **kwargs: fake_df,
    )

    runner = CliRunner()
    result = runner.invoke(
        crop_progress_cmd,
        ["--db", str(db), "--commodity", "CORN", "--year", "2026"],
    )
    assert result.exit_code == 0, result.output
    assert "3 rader skrevet" in result.output

    store = DataStore(db)
    rows = store.get_crop_progress("CORN", state="US", metric="PLANTED")
    assert len(rows) == 3
    assert rows.iloc[-1]["value_pct"] == pytest.approx(38.0)


def test_missing_key_errors_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Live-kall uten key: brukerfeil med tydelig beskjed."""
    db = tmp_path / "bedrock.db"
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    empty = tmp_path / "secrets.env"
    empty.write_text("")
    monkeypatch.setattr("bedrock.config.secrets.DEFAULT_SECRETS_PATH", empty)
    runner = CliRunner()
    result = runner.invoke(crop_progress_cmd, ["--db", str(db), "--year", "2026"])
    assert result.exit_code != 0
    assert "ikke funnet" in result.output or "BEDROCK_NASS_API_KEY" in result.output


def test_empty_api_response_handled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    monkeypatch.setenv("BEDROCK_NASS_API_KEY", "test-key")
    monkeypatch.setattr(
        "bedrock.fetch.nass.fetch_crop_progress_api",
        lambda **kwargs: pd.DataFrame(
            columns=["week_ending", "commodity", "state", "metric", "value_pct"]
        ),
    )
    runner = CliRunner()
    result = runner.invoke(crop_progress_cmd, ["--db", str(db), "--year", "2026"])
    assert result.exit_code == 0, result.output
    assert "ingen rader" in result.output


def test_default_years_includes_current_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "bedrock.db"
    monkeypatch.delenv("BEDROCK_NASS_API_KEY", raising=False)
    empty = tmp_path / "secrets.env"
    empty.write_text("")
    monkeypatch.setattr("bedrock.config.secrets.DEFAULT_SECRETS_PATH", empty)
    runner = CliRunner()
    result = runner.invoke(crop_progress_cmd, ["--db", str(db), "--dry-run"])
    assert result.exit_code == 0, result.output
    current = date.today().year
    assert str(current) in result.output
    assert str(current - 4) in result.output
