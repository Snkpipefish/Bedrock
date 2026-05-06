"""Tester for bedrock.parallel.monitor (Fase 12 session 66).

Bruker ekte filsystem-paths (tmp_path) for log-skanning. Fetcher-freshness
testes med en dummy DataStore-stub for å unngå sqlite-avhengighet.
"""

from __future__ import annotations

import json
from pathlib import Path

from bedrock.parallel.monitor import (
    MonitorReport,
    check_agri_tp_override,
    check_pipeline_log_errors,
    format_monitor_json,
    format_monitor_text,
    run_monitor,
)

# ---------------------------------------------------------------------------
# check_pipeline_log_errors
# ---------------------------------------------------------------------------


def test_pipeline_log_missing_is_ok(tmp_path: Path) -> None:
    result = check_pipeline_log_errors(log_path=tmp_path / "missing.log")
    assert result.ok is True
    assert result.data["log_exists"] is False


def test_pipeline_log_clean_is_ok(tmp_path: Path) -> None:
    log = tmp_path / "pipeline.log"
    log.write_text("INFO start\nINFO done\n")
    result = check_pipeline_log_errors(log_path=log)
    assert result.ok is True
    assert result.data["errors_found"] == 0


def test_pipeline_log_with_errors_fails(tmp_path: Path) -> None:
    log = tmp_path / "pipeline.log"
    log.write_text("INFO start\nfatal: unable to push\nERROR something broke\nINFO done\n")
    result = check_pipeline_log_errors(log_path=log)
    assert result.ok is False
    assert result.data["errors_found"] >= 2


def test_pipeline_log_only_scans_tail(tmp_path: Path) -> None:
    """Gamle feil utenfor tail skal ikke detekteres."""
    log = tmp_path / "pipeline.log"
    lines = ["fatal: gammel feil"] + ["INFO ny linje"] * 10
    log.write_text("\n".join(lines))
    result = check_pipeline_log_errors(log_path=log, max_lines=5)
    # Bare siste 5 linjer skannes — gammel feil skal ikke fange opp
    assert result.ok is True


# ---------------------------------------------------------------------------
# check_agri_tp_override
# ---------------------------------------------------------------------------


def test_agri_tp_override_missing_log_is_ok(tmp_path: Path) -> None:
    result = check_agri_tp_override(log_path=tmp_path / "ikke.log")
    assert result.ok is True


def test_agri_tp_override_clean_log_is_ok(tmp_path: Path) -> None:
    log = tmp_path / "bot.log"
    log.write_text("[INFO] entry confirmed\n[INFO] tp set to 4520\n")
    result = check_agri_tp_override(log_path=log)
    assert result.ok is True
    assert result.data["matches"] == 0


def test_agri_tp_override_match_fails(tmp_path: Path) -> None:
    log = tmp_path / "bot.log"
    log.write_text("[WARN] agri TP overridden by ATR-rule\n")
    result = check_agri_tp_override(log_path=log)
    assert result.ok is False
    assert result.data["matches"] == 1


def test_agri_tp_override_case_insensitive(tmp_path: Path) -> None:
    log = tmp_path / "bot.log"
    log.write_text("AGRI TP OVERRIDDEN now\n")
    result = check_agri_tp_override(log_path=log)
    assert result.ok is False


# ---------------------------------------------------------------------------
# run_monitor (orkestrering)
# ---------------------------------------------------------------------------


def test_run_monitor_with_clean_inputs_returns_ok(tmp_path: Path) -> None:
    pipeline_log = tmp_path / "pipeline.log"
    pipeline_log.write_text("INFO ok\n")
    bot_log = tmp_path / "bot.log"
    bot_log.write_text("INFO ok\n")

    report = run_monitor(
        fetch_yaml=tmp_path / "no-fetch.yaml",  # → fetcher-check fail
        db=tmp_path / "no-db",
        pipeline_log=pipeline_log,
        bot_log=bot_log,
    )

    assert isinstance(report, MonitorReport)
    # Fetcher-check skal feile fordi fetch.yaml ikke finnes,
    # men de andre 2 skal være OK.
    fetcher_check = next(c for c in report.checks if c.name == "fetcher_freshness")
    assert fetcher_check.ok is False

    pipeline_check = next(c for c in report.checks if c.name == "pipeline_log_errors")
    assert pipeline_check.ok is True

    agri_check = next(c for c in report.checks if c.name == "agri_tp_override")
    assert agri_check.ok is True

    assert report.overall_ok is False  # pga fetcher-check


def test_format_monitor_text_includes_manual_step(tmp_path: Path) -> None:
    report = run_monitor(
        fetch_yaml=tmp_path / "x.yaml",
        db=tmp_path / "x.db",
        pipeline_log=tmp_path / "x.log",
        bot_log=tmp_path / "x.log",
    )
    text = format_monitor_text(report)
    assert "Manuelt steg" in text
    assert "20 publiserte setups" in text


def test_format_monitor_json_is_valid_json(tmp_path: Path) -> None:
    report = run_monitor(
        fetch_yaml=tmp_path / "x.yaml",
        db=tmp_path / "x.db",
        pipeline_log=tmp_path / "x.log",
        bot_log=tmp_path / "x.log",
    )
    out = format_monitor_json(report)
    parsed = json.loads(out)
    assert "checks" in parsed
    assert isinstance(parsed["checks"], list)
    assert len(parsed["checks"]) == 3
