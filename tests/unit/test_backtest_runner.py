"""Tester for backtest-rammeverket (Fase 11 session 62 scaffold).

Dekker:
- BacktestConfig validering (dato-vindu, terskel)
- run_outcome_replay mot fixture-DB (full window, filter, hit-flag)
- summary_stats (aggregat-beregning, tomt)
- format_markdown + format_json (roundtrip)
- BacktestSignal/Result Pydantic-roundtrip
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from bedrock.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestSignal,
    format_json,
    format_markdown,
    run_outcome_replay,
    summary_stats,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------
# BacktestConfig
# ---------------------------------------------------------------------


def test_config_minimal() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    assert cfg.from_date is None
    assert cfg.to_date is None
    assert cfg.outcome_threshold_pct == 3.0
    assert cfg.report_format == "markdown"


def test_config_horizon_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        BacktestConfig(instrument="Gold", horizon_days=0)
    with pytest.raises(ValidationError):
        BacktestConfig(instrument="Gold", horizon_days=-30)


def test_config_window_validation() -> None:
    with pytest.raises(ValidationError, match="from_date"):
        BacktestConfig(
            instrument="Gold",
            horizon_days=30,
            from_date=date(2025, 1, 1),
            to_date=date(2024, 1, 1),
        )


def test_config_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        BacktestConfig(instrument="Gold", horizon_days=30, surprise=1)


def test_config_report_format_choices() -> None:
    BacktestConfig(instrument="Gold", horizon_days=30, report_format="json")
    BacktestConfig(instrument="Gold", horizon_days=30, report_format="markdown")
    with pytest.raises(ValidationError):
        BacktestConfig(instrument="Gold", horizon_days=30, report_format="xml")  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Pydantic-modeller (BacktestSignal/Result)
# ---------------------------------------------------------------------


def test_signal_minimal() -> None:
    s = BacktestSignal(
        ref_date=date(2024, 1, 15),
        instrument="Gold",
        horizon_days=30,
        forward_return_pct=2.5,
        hit=False,
    )
    assert s.score is None
    assert s.grade is None
    assert s.published is None


def test_result_roundtrip() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    r = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 15),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=4.0,
                max_drawdown_pct=-1.5,
                hit=True,
            ),
        ],
    )
    j = r.model_dump_json()
    r2 = BacktestResult.model_validate_json(j)
    assert r2 == r


# ---------------------------------------------------------------------
# run_outcome_replay
# ---------------------------------------------------------------------


@pytest.fixture
def seeded_store(tmp_path: Path) -> DataStore:
    store = DataStore(tmp_path / "bedrock.db")
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                "forward_return_pct": [5.0 if i % 3 == 0 else -1.0 for i in range(n)],
                "max_drawdown_pct": [-2.0] * n,
            }
        )
    )
    return store


def test_replay_full_window(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_outcome_replay(seeded_store, cfg)
    assert len(result.signals) == 100
    # 1/3 hits (i % 3 == 0 → forward_return = 5%)
    n_hits = sum(1 for s in result.signals if s.hit)
    assert 30 < n_hits < 40


def test_replay_window_filter(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2024, 1, 15),
        to_date=date(2024, 1, 31),
    )
    result = run_outcome_replay(seeded_store, cfg)
    assert len(result.signals) == 17  # jan 15..31 inkl. = 17 dager
    for s in result.signals:
        assert date(2024, 1, 15) <= s.ref_date <= date(2024, 1, 31)


def test_replay_threshold_changes_hit_count(seeded_store: DataStore) -> None:
    """Samme outcomes-data, ulik terskel → ulik hit-rate."""
    low = run_outcome_replay(
        seeded_store, BacktestConfig(instrument="Gold", horizon_days=30, outcome_threshold_pct=0.0)
    )
    high = run_outcome_replay(
        seeded_store,
        BacktestConfig(instrument="Gold", horizon_days=30, outcome_threshold_pct=10.0),
    )
    n_low = sum(1 for s in low.signals if s.hit)
    n_high = sum(1 for s in high.signals if s.hit)
    assert n_low > n_high
    assert n_high == 0  # ingen 10%-hits i fixture


def test_replay_unknown_instrument_returns_empty(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Silver", horizon_days=30)
    result = run_outcome_replay(seeded_store, cfg)
    assert result.signals == []


def test_replay_unknown_horizon_returns_empty(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=90)  # ikke seedet
    result = run_outcome_replay(seeded_store, cfg)
    assert result.signals == []


def test_replay_window_outside_data_returns_empty(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2030, 1, 1),
        to_date=date(2030, 12, 31),
    )
    result = run_outcome_replay(seeded_store, cfg)
    assert result.signals == []


def test_replay_signals_sorted_by_date(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_outcome_replay(seeded_store, cfg)
    dates = [s.ref_date for s in result.signals]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------
# summary_stats
# ---------------------------------------------------------------------


def test_summary_stats_empty() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    r = BacktestResult(config=cfg, signals=[])
    report = summary_stats(r)
    assert report.n_signals == 0
    assert report.n_hits == 0
    assert report.hit_rate_pct == 0.0
    assert report.avg_drawdown_pct is None


def test_summary_stats_basic(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_outcome_replay(seeded_store, cfg)
    report = summary_stats(result)
    assert report.n_signals == 100
    assert 30 < report.n_hits < 40
    assert report.best_return_pct == 5.0
    assert report.worst_return_pct == -1.0
    assert report.avg_drawdown_pct == -2.0
    assert report.worst_drawdown_pct == -2.0


def test_summary_stats_n_published_none_when_no_score_data() -> None:
    """Outcome-replay mangler published — n_published skal være None."""
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    r = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=1.0,
                hit=False,
            ),
        ],
    )
    report = summary_stats(r)
    assert report.n_published is None


# ---------------------------------------------------------------------
# format_markdown / format_json
# ---------------------------------------------------------------------


def test_format_markdown_includes_metrics(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
    )
    result = run_outcome_replay(seeded_store, cfg)
    report = summary_stats(result)
    md = format_markdown(result, report)
    assert "# Backtest: Gold · h=30d" in md
    assert "**Vindu:** 2024-01-01 .. 2024-12-31" in md
    assert "**Antall signaler:** 100" in md
    assert "Hit-rate" in md
    assert "Avg drawdown" in md


def test_format_markdown_empty_data_message(tmp_path: Path) -> None:
    cfg = BacktestConfig(instrument="DoesNotExist", horizon_days=30)
    empty_store = DataStore(tmp_path / "empty.db")
    result = run_outcome_replay(empty_store, cfg)
    report = summary_stats(result)
    md = format_markdown(result, report)
    assert "Ingen outcomes funnet" in md


def test_format_json_roundtrip(seeded_store: DataStore) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_outcome_replay(seeded_store, cfg)
    report = summary_stats(result)
    text = format_json(result, report)
    parsed = json.loads(text)
    assert "config" in parsed
    assert "report" in parsed
    assert "signals" in parsed
    assert parsed["config"]["instrument"] == "Gold"
    assert parsed["report"]["n_signals"] == 100
    assert len(parsed["signals"]) == 100


def test_format_markdown_signed_returns() -> None:
    """+/− prefiks på return-verdier."""
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    r = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=2.5,
                hit=False,
            ),
            BacktestSignal(
                ref_date=date(2024, 1, 2),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=-1.5,
                hit=False,
            ),
        ],
    )
    report = summary_stats(r)
    md = format_markdown(r, report)
    assert "+2.50%" in md or "+0.50%" in md  # avg er +0.50
    assert "-1.50%" in md  # worst
