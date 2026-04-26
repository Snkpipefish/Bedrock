"""Tester for bedrock.parallel.compare (Fase 12 session 66).

Schema-håndtering: bedrock signals.json (list) vs cot-explorer
signals.json + agri_signals.json (envelope med ``signals``-felt).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bedrock.parallel.compare import (
    CompareReport,
    compare,
    format_compare_json,
    format_compare_markdown,
    load_bedrock_signals,
    load_old_signals,
    normalize_bedrock,
    normalize_old,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bedrock_entry(
    *,
    instrument: str = "Gold",
    direction: str = "buy",
    horizon: str = "makro",
    score: float = 5.0,
    max_score: float = 6.0,
    grade: str = "A",
    entry: float = 4500.0,
    sl: float = 4480.0,
) -> dict:
    return {
        "instrument": instrument,
        "direction": direction,
        "horizon": horizon,
        "score": score,
        "max_score": max_score,
        "grade": grade,
        "published": True,
        "setup": {"setup": {"entry": entry, "sl": sl, "tp": None, "rr": None}},
    }


def _old_entry(
    *,
    key: str = "Gold",
    action: str = "BUY",
    timeframe: str = "MAKRO",
    score: float = 15.0,
    max_score: float = 18.0,
    grade: str = "A",
    entry: float = 4500.0,
    sl: float = 4480.0,
) -> dict:
    return {
        "key": key,
        "name": key,
        "action": action,
        "timeframe": timeframe,
        "horizon": timeframe,
        "score": score,
        "max_score": max_score,
        "grade": grade,
        "entry": entry,
        "sl": sl,
        "t1": entry + 50,
        "t2": entry + 100,
    }


def _write_bedrock(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps(entries))
    return p


def _write_old(tmp_path: Path, name: str, entries: list[dict]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({"schema_version": "2.2", "signals": entries}))
    return p


# ---------------------------------------------------------------------------
# Normalisering
# ---------------------------------------------------------------------------


def test_normalize_bedrock_lowercases_keys() -> None:
    entry = _bedrock_entry(instrument="Gold", direction="BUY", horizon="MAKRO")
    norm = normalize_bedrock(entry)
    assert norm.instrument == "gold"
    assert norm.direction == "buy"
    assert norm.horizon == "makro"
    assert norm.entry == 4500.0
    assert norm.source == "bedrock"


def test_normalize_old_uses_action_for_direction() -> None:
    entry = _old_entry(action="SELL", timeframe="SWING")
    norms = normalize_old(entry)
    # Returnerer en NormalizedSignal per kandidat (key, name).
    assert len(norms) >= 1
    norm = norms[0]
    assert norm.direction == "sell"
    assert norm.horizon == "swing"


def test_normalize_old_handles_missing_max_score() -> None:
    entry = {"key": "X", "action": "BUY", "horizon": "MAKRO", "score": 10}
    norms = normalize_old(entry)
    assert len(norms) == 1
    norm = norms[0]
    assert norm.max_score == 0.0
    assert norm.score == 10.0


def test_normalize_old_returns_both_key_and_name_candidates() -> None:
    """Cot-explorer financial-signaler har key=ticker, name=display.
    Begge skal returneres som matchekandidater."""
    entry = {"key": "NAS100", "name": "Nasdaq", "action": "BUY", "horizon": "SWING"}
    norms = normalize_old(entry)
    instruments = {n.instrument for n in norms}
    assert instruments == {"nas100", "nasdaq"}


def test_normalize_bedrock_handles_missing_setup() -> None:
    entry = _bedrock_entry()
    entry.pop("setup")
    norm = normalize_bedrock(entry)
    assert norm.entry is None
    assert norm.sl is None


# ---------------------------------------------------------------------------
# Lasting
# ---------------------------------------------------------------------------


def test_load_bedrock_returns_empty_for_missing_file(tmp_path: Path) -> None:
    out = load_bedrock_signals(tmp_path / "ikke_eksisterer.json")
    assert out == []


def test_load_bedrock_rejects_dict(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"signals": []}))
    with pytest.raises(ValueError, match="forventet liste"):
        load_bedrock_signals(p)


def test_load_old_handles_envelope(tmp_path: Path) -> None:
    p = _write_old(tmp_path, "old.json", [_old_entry()])
    out = load_old_signals(p)
    assert len(out) == 1
    assert out[0].instrument == "gold"


def test_load_old_handles_bare_list(tmp_path: Path) -> None:
    p = tmp_path / "bare_list.json"
    p.write_text(json.dumps([_old_entry()]))
    out = load_old_signals(p)
    assert len(out) == 1


def test_load_old_returns_empty_for_missing(tmp_path: Path) -> None:
    out = load_old_signals(tmp_path / "ikke.json")
    assert out == []


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def test_compare_identical_grades_no_diff(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry()])
    old = _write_old(tmp_path, "old.json", [_old_entry()])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_common == 1
    assert report.n_only_old == 0
    assert report.n_only_new == 0
    assert report.n_changed == 0
    assert report.n_grade_diff == 0
    assert report.diff[0].kind == "unchanged"


def test_compare_grade_change_flagged(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry(grade="A+")])
    old = _write_old(tmp_path, "old.json", [_old_entry(grade="B")])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_changed == 1
    assert report.n_grade_diff == 1
    assert report.diff[0].kind == "changed"
    assert "grade" in report.diff[0].changed_fields


def test_compare_only_old_when_bedrock_missing_signal(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [])
    old = _write_old(tmp_path, "old.json", [_old_entry()])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_only_old == 1
    assert report.n_only_new == 0
    assert report.diff[0].kind == "only_old"


def test_compare_only_new_when_old_missing_signal(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry()])
    old = _write_old(tmp_path, "old.json", [])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_only_new == 1
    assert report.n_only_old == 0
    assert report.diff[0].kind == "only_new"


def test_compare_score_pct_within_tolerance_not_flagged(tmp_path: Path) -> None:
    # Bedrock 5.0/6.0 = 83.3%, old 15.0/18.0 = 83.3% — felles 0pp diff
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry(score=5.0, max_score=6.0)])
    old = _write_old(tmp_path, "old.json", [_old_entry(score=15.0, max_score=18.0)])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_changed == 0
    assert "score_pct" not in report.diff[0].changed_fields


def test_compare_score_pct_outside_tolerance_flagged(tmp_path: Path) -> None:
    # Bedrock 5.0/6.0 = 83.3%, old 9.0/18.0 = 50% — 33pp diff > 5pp toleranse
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry(score=5.0, max_score=6.0)])
    old = _write_old(tmp_path, "old.json", [_old_entry(score=9.0, max_score=18.0)])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert report.n_changed == 1
    assert "score_pct" in report.diff[0].changed_fields


def test_compare_entry_outside_tolerance_flagged(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry(entry=4500.0)])
    old = _write_old(tmp_path, "old.json", [_old_entry(entry=4600.0)])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    assert "entry" in report.diff[0].changed_fields


def test_compare_multiple_old_files_unioned(tmp_path: Path) -> None:
    bedrock = _write_bedrock(
        tmp_path,
        [
            _bedrock_entry(instrument="Gold", horizon="makro"),
            _bedrock_entry(instrument="Cotton", horizon="makro"),
        ],
    )
    old_a = _write_old(tmp_path, "a.json", [_old_entry(key="Gold")])
    old_b = _write_old(tmp_path, "b.json", [_old_entry(key="Cotton")])

    report = compare(bedrock_path=bedrock, old_paths=[old_a, old_b])

    assert report.n_common == 2
    assert report.n_only_old == 0
    assert report.n_only_new == 0


def test_compare_join_key_includes_direction(tmp_path: Path) -> None:
    """Buy og sell på samme instrument er to separate signaler."""
    bedrock = _write_bedrock(
        tmp_path,
        [
            _bedrock_entry(direction="buy"),
            _bedrock_entry(direction="sell"),
        ],
    )
    old = _write_old(tmp_path, "old.json", [_old_entry(action="BUY")])

    report = compare(bedrock_path=bedrock, old_paths=[old])

    # Felles kun for buy-versjonen
    assert report.n_common == 1
    assert report.n_only_new == 1
    assert report.n_only_old == 0


# ---------------------------------------------------------------------------
# Formatering
# ---------------------------------------------------------------------------


def test_format_markdown_includes_summary_table(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry(grade="A+")])
    old = _write_old(tmp_path, "old.json", [_old_entry(grade="B")])

    report = compare(bedrock_path=bedrock, old_paths=[old])
    md = format_compare_markdown(report)

    assert "Sammendrag" in md
    assert "Grade-endring" in md
    assert "| 1 |" in md  # n_grade_diff = 1
    assert "changed" in md


def test_format_markdown_max_rows_truncates(tmp_path: Path) -> None:
    # 5 endrede signaler, max_rows=2 → 3 utelatt
    bedrock_entries = [_bedrock_entry(instrument=f"X{i}", grade="A+") for i in range(5)]
    old_entries = [_old_entry(key=f"X{i}", grade="B") for i in range(5)]
    bedrock = _write_bedrock(tmp_path, bedrock_entries)
    old = _write_old(tmp_path, "old.json", old_entries)

    report = compare(bedrock_path=bedrock, old_paths=[old])
    md = format_compare_markdown(report, max_rows=2)

    assert "3 flere rader utelatt" in md


def test_format_markdown_no_changes_message(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry()])
    old = _write_old(tmp_path, "old.json", [_old_entry()])

    report = compare(bedrock_path=bedrock, old_paths=[old])
    md = format_compare_markdown(report)

    assert "ingen endringer" in md


def test_format_json_is_valid_json(tmp_path: Path) -> None:
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry()])
    old = _write_old(tmp_path, "old.json", [_old_entry(grade="C")])

    report = compare(bedrock_path=bedrock, old_paths=[old])
    out = format_compare_json(report)
    parsed = json.loads(out)

    assert parsed["n_common"] == 1
    assert parsed["n_grade_diff"] == 1
    assert isinstance(parsed["diff"], list)


def test_compare_report_pickleable_via_asdict(tmp_path: Path) -> None:
    """CompareReport skal kunne serialiseres til JSON via asdict."""
    bedrock = _write_bedrock(tmp_path, [_bedrock_entry()])
    old = _write_old(tmp_path, "old.json", [_old_entry()])

    report = compare(bedrock_path=bedrock, old_paths=[old])
    assert isinstance(report, CompareReport)
    # format_compare_json bruker asdict internt
    json.loads(format_compare_json(report))
