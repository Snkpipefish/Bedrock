"""Tester for bedrock.parallel.monitor (Fase 12 session 66).

Bruker ekte filsystem-paths (tmp_path) for log-skanning + dummy
bedrock/old signal-filer for signal-diff-sjekken. Fetcher-freshness
testes med en dummy DataStore-stub for å unngå sqlite-avhengighet.
"""

from __future__ import annotations

import json
from pathlib import Path

from bedrock.parallel.monitor import (
    MonitorReport,
    check_agri_tp_override,
    check_pipeline_log_errors,
    check_signal_diff,
    format_monitor_json,
    format_monitor_text,
    run_monitor,
)

# ---------------------------------------------------------------------------
# Hjelpere
# ---------------------------------------------------------------------------


def _write_bedrock_signals(path: Path, *, grade: str = "A") -> Path:
    path.write_text(
        json.dumps(
            [
                {
                    "instrument": "Gold",
                    "direction": "buy",
                    "horizon": "makro",
                    "score": 5.0,
                    "max_score": 6.0,
                    "grade": grade,
                    "published": True,
                    "setup": {"setup": {"entry": 4500.0, "sl": 4480.0}},
                }
            ]
        )
    )
    return path


def _write_old_signals(path: Path, *, grade: str = "A") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.2",
                "signals": [
                    {
                        "key": "Gold",
                        "name": "Gold",
                        "action": "BUY",
                        "timeframe": "MAKRO",
                        "horizon": "MAKRO",
                        "score": 15.0,
                        "max_score": 18.0,
                        "grade": grade,
                        "entry": 4500.0,
                        "sl": 4480.0,
                    }
                ],
            }
        )
    )
    return path


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
# check_signal_diff
# ---------------------------------------------------------------------------


def test_signal_diff_bedrock_missing_fails(tmp_path: Path) -> None:
    old = _write_old_signals(tmp_path / "old.json")
    result = check_signal_diff(
        bedrock_signals=tmp_path / "bedrock_missing.json",
        old_signals=(old,),
    )
    assert result.ok is False
    assert "mangler" in result.detail


def test_signal_diff_no_old_files_fails(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json")
    result = check_signal_diff(
        bedrock_signals=bedrock,
        old_signals=(tmp_path / "missing1.json", tmp_path / "missing2.json"),
    )
    assert result.ok is False
    assert "ingen gamle signal-filer" in result.detail


def test_signal_diff_identical_is_ok(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json", grade="A")
    old = _write_old_signals(tmp_path / "old.json", grade="A")
    result = check_signal_diff(bedrock_signals=bedrock, old_signals=(old,))
    assert result.ok is True
    assert result.data["n_common"] == 1
    assert result.data["n_grade_diff"] == 0


def test_signal_diff_one_grade_change_within_threshold_is_ok(tmp_path: Path) -> None:
    """Singel signal med grade-endring → ratio = 1.0 > 0.5 default → fail.

    Med høy threshold (1.0) skal det være OK.
    """
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json", grade="A+")
    old = _write_old_signals(tmp_path / "old.json", grade="B")
    result = check_signal_diff(
        bedrock_signals=bedrock,
        old_signals=(old,),
        grade_diff_ratio_fail=1.5,  # tillat alt
    )
    assert result.ok is True


def test_signal_diff_above_threshold_fails(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json", grade="A+")
    old = _write_old_signals(tmp_path / "old.json", grade="B")
    result = check_signal_diff(
        bedrock_signals=bedrock,
        old_signals=(old,),
        grade_diff_ratio_fail=0.5,
    )
    # 1/1 = 100 % grade-endring → over 50 % terskel → fail
    assert result.ok is False
    assert result.data["n_grade_diff"] == 1


# ---------------------------------------------------------------------------
# run_monitor (orkestrering)
# ---------------------------------------------------------------------------


def test_run_monitor_with_clean_inputs_returns_ok(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json", grade="A")
    old = _write_old_signals(tmp_path / "old.json", grade="A")
    pipeline_log = tmp_path / "pipeline.log"
    pipeline_log.write_text("INFO ok\n")
    bot_log = tmp_path / "bot.log"
    bot_log.write_text("INFO ok\n")

    report = run_monitor(
        fetch_yaml=tmp_path / "no-fetch.yaml",  # → fetcher-check fail
        db=tmp_path / "no-db",
        pipeline_log=pipeline_log,
        bot_log=bot_log,
        bedrock_signals=bedrock,
        old_signals=(old,),
    )

    assert isinstance(report, MonitorReport)
    # Fetcher-check skal feile fordi fetch.yaml ikke finnes,
    # men de andre 3 skal være OK.
    fetcher_check = next(c for c in report.checks if c.name == "fetcher_freshness")
    assert fetcher_check.ok is False

    pipeline_check = next(c for c in report.checks if c.name == "pipeline_log_errors")
    assert pipeline_check.ok is True

    agri_check = next(c for c in report.checks if c.name == "agri_tp_override")
    assert agri_check.ok is True

    signal_check = next(c for c in report.checks if c.name == "signal_diff")
    assert signal_check.ok is True

    assert report.overall_ok is False  # pga fetcher-check


def test_format_monitor_text_includes_manual_step(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json")
    old = _write_old_signals(tmp_path / "old.json")
    report = run_monitor(
        fetch_yaml=tmp_path / "x.yaml",
        db=tmp_path / "x.db",
        pipeline_log=tmp_path / "x.log",
        bot_log=tmp_path / "x.log",
        bedrock_signals=bedrock,
        old_signals=(old,),
    )
    text = format_monitor_text(report)
    assert "Manuelt steg" in text
    assert "20 publiserte setups" in text


def test_format_monitor_json_is_valid_json(tmp_path: Path) -> None:
    bedrock = _write_bedrock_signals(tmp_path / "bedrock.json")
    old = _write_old_signals(tmp_path / "old.json")
    report = run_monitor(
        fetch_yaml=tmp_path / "x.yaml",
        db=tmp_path / "x.db",
        pipeline_log=tmp_path / "x.log",
        bot_log=tmp_path / "x.log",
        bedrock_signals=bedrock,
        old_signals=(old,),
    )
    out = format_monitor_json(report)
    parsed = json.loads(out)
    assert "checks" in parsed
    assert isinstance(parsed["checks"], list)
    assert len(parsed["checks"]) == 4
