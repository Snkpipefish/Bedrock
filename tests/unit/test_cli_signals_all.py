"""Tester for ``bedrock.cli.signals_all``.

Bruker click.testing.CliRunner mot ``signals_all_cmd`` mot fixture-
DB + fixture-instruments-dir. Verifiserer:
- Discovery av instrumenter via *.yaml-iterasjon
- --skip-flag fungerer
- --output-flag styrer write-path
- Failures rapporteres uten å stoppe loopen (default --continue-on-error)
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from bedrock.cli.signals_all import _discover_instrument_ids, signals_all_cmd

# ---------------------------------------------------------------------------
# _discover_instrument_ids
# ---------------------------------------------------------------------------


def test_discover_capitalize_filenames(tmp_path: Path) -> None:
    """`gold.yaml` → `Gold`, `cotton.yaml` → `Cotton`."""
    (tmp_path / "gold.yaml").write_text("instrument: {id: Gold}")
    (tmp_path / "cotton.yaml").write_text("instrument: {id: Cotton}")
    ids = _discover_instrument_ids(tmp_path)
    assert ids == ["Cotton", "Gold"]  # sortert alfabetisk


def test_discover_skips_underscore_and_family_files(tmp_path: Path) -> None:
    """`_template.yaml` og `family_agri.yaml` skal hoppes over."""
    (tmp_path / "gold.yaml").write_text("x")
    (tmp_path / "_template.yaml").write_text("x")
    (tmp_path / "family_agri.yaml").write_text("x")
    ids = _discover_instrument_ids(tmp_path)
    assert ids == ["Gold"]


def test_discover_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    ids = _discover_instrument_ids(tmp_path / "does-not-exist")
    assert ids == []


def test_discover_returns_empty_for_empty_dir(tmp_path: Path) -> None:
    ids = _discover_instrument_ids(tmp_path)
    assert ids == []


# ---------------------------------------------------------------------------
# signals_all_cmd integration (via CliRunner)
# ---------------------------------------------------------------------------


def test_signals_all_writes_output(tmp_path: Path) -> None:
    """End-to-end: kjør mot real prosjekt-DB + config-dir, sjekk JSON."""
    runner = CliRunner()
    output = tmp_path / "signals.json"
    result = runner.invoke(
        signals_all_cmd,
        ["--output", str(output), "--skip", "Coffee", "--skip", "Sugar"],
    )
    # Ikke alle instrumenter trenger å lykkes (analog kan skip), men
    # exit-koden skal være 0 og output-filen skal eksistere.
    assert result.exit_code == 0, result.output
    assert output.exists()
    data = json.loads(output.read_text())
    assert isinstance(data, list)
    assert len(data) > 0
    # Sjekk at skip-flag fungerte
    instruments = {entry["instrument"] for entry in data}
    assert "Coffee" not in instruments
    assert "Sugar" not in instruments


def test_signals_all_fails_on_missing_db(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        signals_all_cmd,
        ["--db", str(tmp_path / "nonexistent.db")],
    )
    assert result.exit_code != 0
    assert "DB-fil finnes ikke" in result.output


def test_signals_all_fails_on_empty_instruments_dir(tmp_path: Path) -> None:
    """Tom instruments-dir = UsageError."""
    runner = CliRunner()
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = runner.invoke(
        signals_all_cmd,
        [
            "--instruments-dir",
            str(empty_dir),
        ],
    )
    assert result.exit_code != 0
    assert "Ingen instrumenter funnet" in result.output
