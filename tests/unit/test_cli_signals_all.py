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
    import pytest

    if not Path("data/bedrock.db").exists():
        pytest.skip("data/bedrock.db not backfilled — run `bedrock backfill ...` first")

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


def _mocked_generate_result(instrument: str):
    """Bygg en SimpleNamespace som mimicker GenerateResult med 6 entries
    (scalp/swing/makro × buy/sell). Hver entry har model_dump som returnerer
    dict m/ instrument, horizon, direction.
    """
    from types import SimpleNamespace

    entries = []
    for horizon in ("scalp", "swing", "makro"):
        for direction in ("buy", "sell"):
            entries.append(
                SimpleNamespace(
                    model_dump=lambda mode="json", h=horizon, d=direction, i=instrument: {
                        "instrument": i,
                        "horizon": h,
                        "direction": d,
                        "score": 1.0,
                        "published": True,
                    }
                )
            )
    return SimpleNamespace(entries=entries)


def test_signals_all_horizons_filter(tmp_path: Path, monkeypatch) -> None:
    """`--horizons scalp` filtrerer output til kun scalp-entries.

    Mocker generate_signals + DataStore + _read_asset_class for å unngå
    8-min full regen mens vi tester filter-logikken.
    """
    instruments_dir = tmp_path / "instruments"
    instruments_dir.mkdir()
    (instruments_dir / "gold.yaml").write_text("instrument: {id: Gold}")
    (instruments_dir / "silver.yaml").write_text("instrument: {id: Silver}")
    fake_db = tmp_path / "fake.db"
    fake_db.touch()

    import bedrock.cli.signals_all as mod

    monkeypatch.setattr(mod, "DataStore", lambda _path: object())
    monkeypatch.setattr(
        mod, "generate_signals", lambda inst, *a, **kw: _mocked_generate_result(inst)
    )
    monkeypatch.setattr(mod, "_read_asset_class", lambda _p: "metals")

    runner = CliRunner()
    output = tmp_path / "signals_scalp.json"
    result = runner.invoke(
        signals_all_cmd,
        [
            "--instruments-dir",
            str(instruments_dir),
            "--db",
            str(fake_db),
            "--output",
            str(output),
            "--no-split",
            "--horizons",
            "scalp",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    horizons = {str(e.get("horizon", "")).lower() for e in data}
    assert horizons == {"scalp"}
    # 2 instrumenter × 1 horisont × 2 retninger = 4 entries
    assert len(data) == 4


def test_signals_all_horizons_multiple(tmp_path: Path, monkeypatch) -> None:
    """`--horizons scalp --horizons swing` slipper begge gjennom, ikke makro."""
    instruments_dir = tmp_path / "instruments"
    instruments_dir.mkdir()
    (instruments_dir / "gold.yaml").write_text("instrument: {id: Gold}")
    fake_db = tmp_path / "fake.db"
    fake_db.touch()

    import bedrock.cli.signals_all as mod

    monkeypatch.setattr(mod, "DataStore", lambda _path: object())
    monkeypatch.setattr(
        mod, "generate_signals", lambda inst, *a, **kw: _mocked_generate_result(inst)
    )
    monkeypatch.setattr(mod, "_read_asset_class", lambda _p: "metals")

    runner = CliRunner()
    output = tmp_path / "signals_two.json"
    result = runner.invoke(
        signals_all_cmd,
        [
            "--instruments-dir",
            str(instruments_dir),
            "--db",
            str(fake_db),
            "--output",
            str(output),
            "--no-split",
            "--horizons",
            "scalp",
            "--horizons",
            "swing",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    horizons = {str(e.get("horizon", "")).lower() for e in data}
    assert horizons == {"scalp", "swing"}
    # 1 instrument × 2 horisonter × 2 retninger = 4 entries
    assert len(data) == 4


def test_signals_all_no_horizon_filter_keeps_all(tmp_path: Path, monkeypatch) -> None:
    """Uten --horizons skal alle 3 horisonter komme gjennom (status quo)."""
    instruments_dir = tmp_path / "instruments"
    instruments_dir.mkdir()
    (instruments_dir / "gold.yaml").write_text("instrument: {id: Gold}")
    fake_db = tmp_path / "fake.db"
    fake_db.touch()

    import bedrock.cli.signals_all as mod

    monkeypatch.setattr(mod, "DataStore", lambda _path: object())
    monkeypatch.setattr(
        mod, "generate_signals", lambda inst, *a, **kw: _mocked_generate_result(inst)
    )
    monkeypatch.setattr(mod, "_read_asset_class", lambda _p: "metals")

    runner = CliRunner()
    output = tmp_path / "signals_all.json"
    result = runner.invoke(
        signals_all_cmd,
        [
            "--instruments-dir",
            str(instruments_dir),
            "--db",
            str(fake_db),
            "--output",
            str(output),
            "--no-split",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    horizons = {str(e.get("horizon", "")).lower() for e in data}
    assert horizons == {"scalp", "swing", "makro"}
    assert len(data) == 6  # 1 inst × 3 hor × 2 dir


def test_signals_all_fails_on_empty_instruments_dir(tmp_path: Path) -> None:
    """Tom instruments-dir = UsageError. Ingen DB-avhengighet (sjekk
    rekkefølge: instruments-dir valideres før DB).
    """
    runner = CliRunner()
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    fake_db = tmp_path / "fake.db"
    fake_db.touch()  # eksisterer, så DB-check passerer
    result = runner.invoke(
        signals_all_cmd,
        [
            "--instruments-dir",
            str(empty_dir),
            "--db",
            str(fake_db),
        ],
    )
    assert result.exit_code != 0
    assert "Ingen instrumenter funnet" in result.output
