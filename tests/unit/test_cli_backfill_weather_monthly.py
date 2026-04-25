"""Tester for `bedrock backfill weather-monthly` (Fase 10 ADR-005).

Migrerer cot-explorer/data/agri_history/<region>.json til
weather_monthly-tabellen. Tester bruker fixture-JSON-filer i tmp_path
istedenfor reelle prod-filer for å unngå avhengighet av ~/cot-explorer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.backfill import (
    _load_agri_history_to_weather_monthly,
    weather_monthly_cmd,
)
from bedrock.data.store import DataStore


def _write_agri_json(path: Path, region: str, monthly: dict[str, dict]) -> None:
    payload = {
        "region_id": region,
        "name": region.replace("_", " ").title(),
        "lat": 41.8,
        "lon": -92.5,
        "updated": "2026-04-25T00:00:00+00:00",
        "monthly": monthly,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_monthly() -> dict[str, dict]:
    return {
        "2024-01": {
            "temp_mean": -8.5,
            "temp_max": 2.4,
            "precip_mm": 21.1,
            "et0_mm": 17.7,
            "hot_days": 0,
            "dry_days": 26,
            "wet_days": 0,
            "water_bal": 3.4,
            "days": 31,
        },
        "2024-02": {
            "temp_mean": -3.5,
            "temp_max": 8.1,
            "precip_mm": 35.2,
            "et0_mm": 22.0,
            "hot_days": 0,
            "dry_days": 18,
            "wet_days": 2,
            "water_bal": 13.2,
            "days": 29,
        },
    }


# ---------------------------------------------------------------------
# _load_agri_history_to_weather_monthly (loader-helper)
# ---------------------------------------------------------------------


def test_loader_drops_days_field(tmp_path: Path) -> None:
    """`days` (9. felt) skal ikke skrives — kan beregnes fra month-stringen."""
    p = tmp_path / "us_cornbelt.json"
    _write_agri_json(p, "us_cornbelt", _sample_monthly())
    df = _load_agri_history_to_weather_monthly(p)
    assert len(df) == 2
    assert "days" not in df.columns
    assert (df["region"] == "us_cornbelt").all()
    assert df["month"].tolist() == ["2024-01", "2024-02"]
    assert df["temp_mean"].iloc[0] == pytest.approx(-8.5)
    assert df["hot_days"].iloc[1] == 0


def test_loader_uses_region_id_field(tmp_path: Path) -> None:
    """Region kommer fra JSON `region_id`, ikke filnavn (slik at vi kan
    holde filnavn lik region_id som konvensjon, men ingen overraskelser
    om de divergerer)."""
    p = tmp_path / "filename_only.json"
    _write_agri_json(p, "actual_region_id", _sample_monthly())
    df = _load_agri_history_to_weather_monthly(p)
    assert (df["region"] == "actual_region_id").all()


def test_loader_falls_back_to_filename_if_region_id_missing(tmp_path: Path) -> None:
    p = tmp_path / "fallback_region.json"
    p.write_text(json.dumps({"monthly": _sample_monthly()}), encoding="utf-8")
    df = _load_agri_history_to_weather_monthly(p)
    assert (df["region"] == "fallback_region").all()


def test_loader_empty_monthly_returns_empty_frame(tmp_path: Path) -> None:
    p = tmp_path / "empty.json"
    _write_agri_json(p, "empty", {})
    df = _load_agri_history_to_weather_monthly(p)
    assert df.empty
    assert "region" in df.columns


def test_loader_handles_missing_field_per_month(tmp_path: Path) -> None:
    p = tmp_path / "partial.json"
    _write_agri_json(
        p,
        "partial",
        {
            "2024-01": {"temp_mean": 5.0},  # bare ett felt
        },
    )
    df = _load_agri_history_to_weather_monthly(p)
    assert df["temp_mean"].iloc[0] == 5.0
    assert pd.isna(df["temp_max"].iloc[0])


# ---------------------------------------------------------------------
# CLI-kommando
# ---------------------------------------------------------------------


def _setup_source(tmp_path: Path, regions: list[str]) -> Path:
    src = tmp_path / "agri_history"
    src.mkdir()
    for r in regions:
        _write_agri_json(src / f"{r}.json", r, _sample_monthly())
    return src


def test_cli_dry_run_lists_files(tmp_path: Path) -> None:
    src = _setup_source(tmp_path, ["us_cornbelt", "brazil_coffee"])
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(
        weather_monthly_cmd,
        ["--source-dir", str(src), "--db", str(db), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "us_cornbelt.json" in result.output
    assert "brazil_coffee.json" in result.output
    assert "Total: 2 regioner" in result.output
    assert not db.exists()


def test_cli_migrates_all_regions(tmp_path: Path) -> None:
    src = _setup_source(tmp_path, ["us_cornbelt", "brazil_coffee"])
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(weather_monthly_cmd, ["--source-dir", str(src), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "4 rader totalt" in result.output  # 2 regions × 2 months

    store = DataStore(db)
    a = store.get_weather_monthly("us_cornbelt")
    b = store.get_weather_monthly("brazil_coffee")
    assert len(a) == 2
    assert len(b) == 2


def test_cli_filter_by_region(tmp_path: Path) -> None:
    src = _setup_source(tmp_path, ["us_cornbelt", "brazil_coffee"])
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(
        weather_monthly_cmd,
        ["--source-dir", str(src), "--db", str(db), "--region", "us_cornbelt"],
    )
    assert result.exit_code == 0, result.output
    store = DataStore(db)
    assert store.has_weather_monthly("us_cornbelt") is True
    assert store.has_weather_monthly("brazil_coffee") is False


def test_cli_unknown_region_errors(tmp_path: Path) -> None:
    src = _setup_source(tmp_path, ["us_cornbelt"])
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    result = runner.invoke(
        weather_monthly_cmd,
        ["--source-dir", str(src), "--db", str(db), "--region", "missing"],
    )
    assert result.exit_code != 0
    assert "missing" in result.output.lower()


def test_cli_missing_source_dir_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        weather_monthly_cmd,
        ["--source-dir", str(tmp_path / "no_such_dir"), "--db", str(tmp_path / "x.db")],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_cli_idempotent(tmp_path: Path) -> None:
    src = _setup_source(tmp_path, ["us_cornbelt"])
    db = tmp_path / "bedrock.db"
    runner = CliRunner()
    runner.invoke(weather_monthly_cmd, ["--source-dir", str(src), "--db", str(db)])
    runner.invoke(weather_monthly_cmd, ["--source-dir", str(src), "--db", str(db)])
    store = DataStore(db)
    df = store.get_weather_monthly("us_cornbelt")
    assert len(df) == 2  # ikke 4 — INSERT OR REPLACE
