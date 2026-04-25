"""Tester for run_orchestrator_replay + per-grade-breakdown
(Fase 11 session 63).

Krever ekte instrument-YAML siden orchestrator slår opp config. Bruker
samme tmp_path-pattern som test_analog_drivers.py — minimal Gold-YAML
med analog-familie + dummy trend-driver.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestSignal,
    format_markdown,
    run_orchestrator_replay,
    summary_stats,
)
from bedrock.data.store import DataStore


@pytest.fixture
def gold_yaml_dir(tmp_path: Path) -> Path:
    """Minimal Gold-YAML med analog-familie og enkel scoring-struktur."""
    inst_dir = tmp_path / "instruments"
    inst_dir.mkdir()
    (inst_dir / "gold.yaml").write_text(
        """\
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  cot_contract: "GOLD - COMMODITY EXCHANGE INC."
  cot_report: disaggregated
aggregation: weighted_horizon
horizons:
  SCALP:
    family_weights: {trend: 1.0, analog: 0.5}
    max_score: 1.5
    min_score_publish: 0.5
families:
  trend:
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
  analog:
    drivers:
      - name: analog_hit_rate
        weight: 1.0
        params:
          asset_class: metals
          k: 5
          horizon_days: 30
          outcome_threshold_pct: 3.0
          min_history_days: 0
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A: {min_pct_of_max: 0.55, min_families: 1}
  B: {min_pct_of_max: 0.35, min_families: 1}
""",
        encoding="utf-8",
    )
    return inst_dir


@pytest.fixture
def replay_store(tmp_path: Path) -> DataStore:
    """Seed nok prises + DTWEXBGS + outcomes til at orchestrator-replay
    kan kjøre over et lite vindu."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 600
    dates = pd.date_range("2022-01-01", periods=n, freq="D")

    # Prices: nok lookback for sma200 (200 + 50)
    store.append_prices(
        "Gold",
        "D1",
        pd.DataFrame(
            {
                "ts": dates,
                "open": [1800.0 + i * 0.5 for i in range(n)],
                "high": [1810.0 + i * 0.5 for i in range(n)],
                "low": [1790.0 + i * 0.5 for i in range(n)],
                "close": [1800.0 + i * 0.5 for i in range(n)],
                "volume": [1000.0] * n,
            }
        ),
    )

    # DTWEXBGS for analog dxy_chg5d
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DTWEXBGS"] * n,
                "date": dates,
                "value": [100.0 + i * 0.05 for i in range(n)],
            }
        )
    )

    # Outcomes
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


# ---------------------------------------------------------------------
# run_orchestrator_replay
# ---------------------------------------------------------------------


def test_orchestrator_replay_populates_score_and_grade(
    replay_store: DataStore, gold_yaml_dir: Path
) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 15),
    )
    result = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        step_days=5,
    )
    assert len(result.signals) >= 1
    for s in result.signals:
        assert s.score is not None
        assert s.grade in {"A+", "A", "B", "C", "D", None}  # None bør ikke skje med vår yaml
        assert s.published is not None
        # forward_return + hit kommer fra outcomes-tabellen
        assert s.forward_return_pct in {5.0, -1.0}
        assert s.hit == (s.forward_return_pct >= cfg.outcome_threshold_pct)


def test_orchestrator_replay_step_days(replay_store: DataStore, gold_yaml_dir: Path) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 31),
    )
    daily = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        step_days=1,
    )
    weekly = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        step_days=7,
    )
    # daily skal ha flere signaler enn weekly
    assert len(daily.signals) > len(weekly.signals)


def test_orchestrator_replay_max_iterations(replay_store: DataStore, gold_yaml_dir: Path) -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        step_days=1,
        max_iterations=3,
    )
    assert len(result.signals) <= 3


def test_orchestrator_replay_buy_vs_sell(replay_store: DataStore, gold_yaml_dir: Path) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 15),
    )
    buy = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        direction="buy",
        step_days=5,
    )
    sell = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
        direction="sell",
        step_days=5,
    )
    assert len(buy.signals) >= 1
    assert len(sell.signals) >= 1


def test_orchestrator_replay_no_outcomes_returns_empty(tmp_path: Path, gold_yaml_dir: Path) -> None:
    store = DataStore(tmp_path / "empty.db")
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = run_orchestrator_replay(
        store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
    )
    assert result.signals == []


def test_orchestrator_replay_outside_window_returns_empty(
    replay_store: DataStore, gold_yaml_dir: Path
) -> None:
    cfg = BacktestConfig(
        instrument="Gold",
        horizon_days=30,
        from_date=date(2030, 1, 1),
        to_date=date(2030, 12, 31),
    )
    result = run_orchestrator_replay(
        replay_store,
        cfg,
        instruments_dir=str(gold_yaml_dir),
    )
    assert result.signals == []


# ---------------------------------------------------------------------
# Per-grade-breakdown i summary_stats
# ---------------------------------------------------------------------


def test_summary_stats_includes_per_grade_when_grades_present() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=5.0,
                hit=True,
                grade="A+",
                score=4.5,
                published=True,
            ),
            BacktestSignal(
                ref_date=date(2024, 1, 2),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=2.0,
                hit=False,
                grade="A+",
                score=4.5,
                published=True,
            ),
            BacktestSignal(
                ref_date=date(2024, 1, 3),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=-1.0,
                hit=False,
                grade="B",
                score=2.0,
                published=True,
            ),
        ],
    )
    report = summary_stats(result)
    assert "A+" in report.by_grade
    assert "B" in report.by_grade
    assert report.by_grade["A+"]["n_signals"] == 2.0
    assert report.by_grade["A+"]["hit_rate_pct"] == 50.0
    assert report.by_grade["B"]["n_signals"] == 1.0
    assert report.by_grade["B"]["hit_rate_pct"] == 0.0
    # Grade-rangering: A+ før B
    assert list(report.by_grade.keys()) == ["A+", "B"]


def test_summary_stats_n_published_populated_when_orchestrator_data() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=1.0,
                hit=False,
                grade="A",
                score=3.0,
                published=True,
            ),
            BacktestSignal(
                ref_date=date(2024, 1, 2),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=2.0,
                hit=False,
                grade="B",
                score=1.5,
                published=False,
            ),
        ],
    )
    report = summary_stats(result)
    assert report.n_published == 1


def test_summary_stats_no_grades_means_empty_breakdown() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = BacktestResult(
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
    report = summary_stats(result)
    assert report.by_grade == {}
    assert report.n_published is None


def test_format_markdown_includes_per_grade_section() -> None:
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = BacktestResult(
        config=cfg,
        signals=[
            BacktestSignal(
                ref_date=date(2024, 1, 1),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=5.0,
                hit=True,
                grade="A+",
                score=4.5,
                published=True,
            ),
            BacktestSignal(
                ref_date=date(2024, 1, 2),
                instrument="Gold",
                horizon_days=30,
                forward_return_pct=-1.0,
                hit=False,
                grade="B",
                score=2.0,
                published=True,
            ),
        ],
    )
    report = summary_stats(result)
    md = format_markdown(result, report)
    assert "## Per grade" in md
    assert "| A+ | 1 |" in md
    assert "| B | 1 |" in md


def test_format_markdown_no_per_grade_when_outcome_replay_only() -> None:
    """Outcome-replay (uten grade) skal ikke vise tom ## Per grade-tabell."""
    cfg = BacktestConfig(instrument="Gold", horizon_days=30)
    result = BacktestResult(
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
    report = summary_stats(result)
    md = format_markdown(result, report)
    assert "## Per grade" not in md
