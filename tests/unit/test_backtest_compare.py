"""Tester for compare_signals + CompareReport (Fase 11 session 65)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from click.testing import CliRunner

from bedrock.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestSignal,
    compare_signals,
    format_compare_json,
    format_compare_markdown,
)
from bedrock.cli.backtest import backtest as backtest_cli

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _sig(
    day: int,
    *,
    score: float | None = None,
    grade: str | None = None,
    pub: bool | None = None,
    fwd: float = 1.0,
    hit: bool = False,
) -> BacktestSignal:
    return BacktestSignal(
        ref_date=date(2024, 1, day),
        instrument="Gold",
        horizon_days=30,
        forward_return_pct=fwd,
        max_drawdown_pct=-1.0,
        hit=hit,
        score=score,
        grade=grade,
        published=pub,
    )


def _result(*signals: BacktestSignal) -> BacktestResult:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    return BacktestResult(config=cfg, signals=list(signals))


# ---------------------------------------------------------------------
# Identical inputs
# ---------------------------------------------------------------------


def test_identical_results_zero_changes() -> None:
    a = _sig(1, score=4.0, grade="A+", pub=True, hit=True)
    b = _sig(2, score=2.0, grade="B", pub=False, hit=False)
    r = compare_signals(_result(a, b), _result(a, b))
    assert r.n_signals_v1 == 2
    assert r.n_signals_v2 == 2
    assert r.n_only_v1 == 0
    assert r.n_only_v2 == 0
    assert r.n_changed == 0
    assert r.n_score_changed == 0
    assert r.n_grade_changed == 0
    assert r.signal_count_delta == 0
    assert r.diff_rows == []


# ---------------------------------------------------------------------
# Score-only change
# ---------------------------------------------------------------------


def test_score_change_alone() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=True))
    v2 = _result(_sig(1, score=2.5, grade="B", pub=True))
    r = compare_signals(v1, v2)
    assert r.n_changed == 1
    assert r.n_score_changed == 1
    assert r.n_grade_changed == 0
    assert r.n_grade_promoted == 0
    assert r.n_grade_demoted == 0


def test_tiny_float_diff_ignored() -> None:
    """Numerisk støy < 1e-9 skal ikke regnes som endring."""
    v1 = _result(_sig(1, score=2.0, grade="B", pub=True))
    v2 = _result(_sig(1, score=2.0 + 1e-12, grade="B", pub=True))
    r = compare_signals(v1, v2)
    assert r.n_changed == 0


# ---------------------------------------------------------------------
# Grade overgang
# ---------------------------------------------------------------------


def test_grade_promoted() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=True))
    v2 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    r = compare_signals(v1, v2)
    assert r.n_grade_changed == 1
    assert r.n_grade_promoted == 1
    assert r.n_grade_demoted == 0


def test_grade_demoted() -> None:
    v1 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    v2 = _result(_sig(1, score=2.0, grade="C", pub=False))
    r = compare_signals(v1, v2)
    assert r.n_grade_changed == 1
    assert r.n_grade_promoted == 0
    assert r.n_grade_demoted == 1


def test_grade_unknown_treated_as_lowest_rank() -> None:
    """Ukjent grade-streng rangeres som verste (rank 99)."""
    v1 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    v2 = _result(_sig(1, score=2.0, grade="UNKNOWN", pub=True))
    r = compare_signals(v1, v2)
    assert r.n_grade_demoted == 1


# ---------------------------------------------------------------------
# Published-overgang
# ---------------------------------------------------------------------


def test_published_added() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=False))
    v2 = _result(_sig(1, score=3.5, grade="A", pub=True))
    r = compare_signals(v1, v2)
    assert r.n_published_added == 1
    assert r.n_published_removed == 0


def test_published_removed() -> None:
    v1 = _result(_sig(1, score=3.5, grade="A", pub=True))
    v2 = _result(_sig(1, score=1.0, grade="C", pub=False))
    r = compare_signals(v1, v2)
    assert r.n_published_added == 0
    assert r.n_published_removed == 1


# ---------------------------------------------------------------------
# Hit-overgang (uvanlig — krever endret hit-flag på samme ref_date)
# ---------------------------------------------------------------------


def test_hit_changed() -> None:
    v1 = _result(_sig(1, fwd=2.0, hit=False))
    v2 = _result(_sig(1, fwd=2.0, hit=True))  # samme fwd, annet hit
    r = compare_signals(v1, v2)
    assert r.n_hit_changed == 1
    assert r.n_changed == 1


# ---------------------------------------------------------------------
# Only-in-v1 / only-in-v2
# ---------------------------------------------------------------------


def test_only_in_v1() -> None:
    v1 = _result(_sig(1), _sig(2))
    v2 = _result(_sig(1))
    r = compare_signals(v1, v2)
    assert r.n_only_v1 == 1
    assert r.n_only_v2 == 0
    assert r.signal_count_delta == 1


def test_only_in_v2() -> None:
    v1 = _result(_sig(1))
    v2 = _result(_sig(1), _sig(2), _sig(3))
    r = compare_signals(v1, v2)
    assert r.n_only_v1 == 0
    assert r.n_only_v2 == 2
    assert r.signal_count_delta == 2


def test_disjoint_ref_dates() -> None:
    v1 = _result(_sig(1), _sig(2))
    v2 = _result(_sig(3), _sig(4))
    r = compare_signals(v1, v2)
    assert r.n_only_v1 == 2
    assert r.n_only_v2 == 2
    assert r.n_common == 0
    assert r.n_changed == 0


# ---------------------------------------------------------------------
# DiffRow rekkefølge + innhold
# ---------------------------------------------------------------------


def test_diff_rows_contain_old_and_new_values() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=False))
    v2 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    r = compare_signals(v1, v2)
    assert len(r.diff_rows) == 1
    row = r.diff_rows[0]
    assert row.kind == "changed"
    assert row.score_v1 == 2.0
    assert row.score_v2 == 4.0
    assert row.grade_v1 == "B"
    assert row.grade_v2 == "A+"
    assert row.published_v1 is False
    assert row.published_v2 is True


def test_only_v1_row_has_no_v2_data() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=True))
    v2 = _result()
    r = compare_signals(v1, v2)
    row = r.diff_rows[0]
    assert row.kind == "only_v1"
    assert row.score_v1 == 2.0
    assert row.score_v2 is None
    assert row.grade_v2 is None


# ---------------------------------------------------------------------
# § 11.5 use case — assertion-mønsteret
# ---------------------------------------------------------------------


def test_signal_count_delta_threshold_pattern() -> None:
    """Per § 11.5: assert diff.signal_count_delta < 0.10 * len(v1_signals)."""
    v1 = _result(*[_sig(d) for d in range(1, 21)])  # 20 sigs
    v2 = _result(*[_sig(d) for d in range(1, 22)])  # 21 sigs
    r = compare_signals(v1, v2)
    assert r.signal_count_delta < 0.10 * len(v1.signals) + 1  # 2.0


# ---------------------------------------------------------------------
# Mismatch-warnings (instrument + horizon)
# ---------------------------------------------------------------------


def test_instrument_mismatch_warns_but_completes() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B"))
    cfg2 = BacktestConfig(instrument="Corn", horizon_days=30)
    v2 = BacktestResult(
        config=cfg2,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Corn",
                horizon_days=30,
                forward_return_pct=1.0,
                hit=False,
                score=2.0,
                grade="B",
            )
        ],
    )
    r = compare_signals(v1, v2)
    # Skal ikke kaste — bare logge advarsel
    assert r.n_common == 1


# ---------------------------------------------------------------------
# Markdown- + JSON-rendering
# ---------------------------------------------------------------------


def test_format_markdown_empty_diff() -> None:
    a = _sig(1, score=4.0, grade="A+", pub=True)
    r = compare_signals(_result(a), _result(a))
    md = format_compare_markdown(r)
    assert "Ingen forskjeller å rapportere" in md


def test_format_markdown_with_diffs() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=False))
    v2 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    r = compare_signals(v1, v2, label_v1="baseline", label_v2="ny")
    md = format_compare_markdown(r)
    assert "Compare: baseline → ny" in md
    assert "Score endret" in md
    assert "B → A+" in md
    assert "✗ → ✓" in md  # pub-overgang


def test_format_markdown_max_rows_truncates() -> None:
    sigs1 = [_sig(d, score=1.0, grade="C") for d in range(1, 11)]
    sigs2 = [_sig(d, score=2.0, grade="B") for d in range(1, 11)]
    r = compare_signals(_result(*sigs1), _result(*sigs2))
    md = format_compare_markdown(r, max_rows=3)
    # 10 changed-rader, men vi ber om max 3
    assert "7 flere rader utelatt" in md


def test_format_compare_json_roundtrip() -> None:
    v1 = _result(_sig(1, score=2.0, grade="B"))
    v2 = _result(_sig(1, score=4.0, grade="A+"))
    r = compare_signals(v1, v2)
    text = format_compare_json(r)
    parsed = json.loads(text)
    assert parsed["n_changed"] == 1
    assert parsed["label_v1"] == "v1"
    assert len(parsed["diff_rows"]) == 1


# ---------------------------------------------------------------------
# CLI: bedrock backtest compare
# ---------------------------------------------------------------------


def test_cli_compare_writes_markdown(tmp_path: Path) -> None:
    v1 = _result(_sig(1, score=2.0, grade="B", pub=False))
    v2 = _result(_sig(1, score=4.0, grade="A+", pub=True))
    p1 = tmp_path / "v1.json"
    p2 = tmp_path / "v2.json"
    p1.write_text(
        json.dumps(
            {
                "config": v1.config.model_dump(mode="json"),
                "signals": [s.model_dump(mode="json") for s in v1.signals],
            }
        )
    )
    p2.write_text(
        json.dumps(
            {
                "config": v2.config.model_dump(mode="json"),
                "signals": [s.model_dump(mode="json") for s in v2.signals],
            }
        )
    )
    out = tmp_path / "diff.md"
    runner = CliRunner()
    result = runner.invoke(
        backtest_cli,
        [
            "compare",
            "--v1",
            str(p1),
            "--v2",
            str(p2),
            "--label-v1",
            "before",
            "--label-v2",
            "after",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    md = out.read_text()
    assert "Compare: before → after" in md
    assert "B → A+" in md


def test_cli_compare_emits_json(tmp_path: Path) -> None:
    v1 = _result(_sig(1, score=2.0, grade="B"))
    v2 = _result(_sig(1, score=4.0, grade="A+"))
    p1 = tmp_path / "v1.json"
    p2 = tmp_path / "v2.json"
    for path, res in [(p1, v1), (p2, v2)]:
        path.write_text(
            json.dumps(
                {
                    "config": res.config.model_dump(mode="json"),
                    "signals": [s.model_dump(mode="json") for s in res.signals],
                }
            )
        )
    runner = CliRunner()
    result = runner.invoke(
        backtest_cli,
        [
            "compare",
            "--v1",
            str(p1),
            "--v2",
            str(p2),
            "--report",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["n_changed"] == 1
