"""Tester for `bedrock backfill enso` (Fase 10 ADR-005)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.backfill import enso_cmd
from bedrock.data.store import DataStore
from bedrock.fetch.enso import NOAA_ONI_SERIES_ID


def test_enso_dry_run_no_db_no_http(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(enso_cmd, ["--db", str(db), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "NOAA_ONI" in result.output
    assert not db.exists()


def test_enso_writes_to_fundamentals(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Live-modus: monkey-patche fetch_noaa_oni → tre rader skrives til fundamentals."""
    db = tmp_path / "bedrock.db"

    fake_df = pd.DataFrame(
        {
            "series_id": [NOAA_ONI_SERIES_ID] * 3,
            "date": ["1999-01-01", "1999-02-01", "1999-03-01"],
            "value": [-1.7, -1.5, -1.2],
        }
    )

    monkeypatch.setattr(
        "bedrock.cli.backfill.fetch_noaa_oni",
        lambda: fake_df,
    )

    runner = CliRunner()
    result = runner.invoke(enso_cmd, ["--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "3 rader skrevet" in result.output

    store = DataStore(db)
    series = store.get_fundamentals(NOAA_ONI_SERIES_ID)
    assert len(series) == 3
    assert series.iloc[0] == pytest.approx(-1.7)


def test_enso_empty_response_handled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    monkeypatch.setattr(
        "bedrock.cli.backfill.fetch_noaa_oni",
        lambda: pd.DataFrame(columns=["series_id", "date", "value"]),
    )
    runner = CliRunner()
    result = runner.invoke(enso_cmd, ["--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "ingen rader" in result.output
