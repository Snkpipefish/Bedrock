"""Backtest-rammeverk for Bedrock (Fase 11, session 62 scaffold).

Per PLAN § 11.5: rapport over signal-performance på historikk.

Session 62 leverer kun **outcome-replay**: leser pre-beregnet
`analog_outcomes`-tabell og rapporterer aggregert forward_return +
hit-rate per (instrument, horizon_days) i et dato-vindu. Dette gir
oss en baseline rapport-format og CLI-skall.

Senere sessions vil legge til:

- `run_orchestrator_replay` — re-kjøre orchestrator as-of-date for
  hver dato i vinduet og fange faktisk signal-output (score, grade,
  published, gates_triggered) per (direction, horizon)
- Per-grade-breakdown (krever orchestrator-output)
- `compare_signals(v1, v2)` for regelsett-impact-tester
- UI-integrering (ny "Backtest"-fane?)

Per ADR-005 + § 6.5: outcomes-tabellen er pre-beregnet (forward_return
+ max_drawdown), så outcome-replay er en ren DB-query + aggregat.
Ingen HTTP, ingen orchestrator-kjøring i session 62.
"""

from __future__ import annotations

from bedrock.backtest.compare import (
    CompareReport,
    DiffRow,
    compare_signals,
    format_compare_json,
    format_compare_markdown,
)
from bedrock.backtest.config import BacktestConfig
from bedrock.backtest.report import (
    BacktestReport,
    format_json,
    format_markdown,
    summary_stats,
)
from bedrock.backtest.result import BacktestResult, BacktestSignal
from bedrock.backtest.runner import run_orchestrator_replay, run_outcome_replay
from bedrock.backtest.store_view import AsOfDateStore

__all__ = [
    "AsOfDateStore",
    "BacktestConfig",
    "BacktestReport",
    "BacktestResult",
    "BacktestSignal",
    "CompareReport",
    "DiffRow",
    "compare_signals",
    "format_compare_json",
    "format_compare_markdown",
    "format_json",
    "format_markdown",
    "run_orchestrator_replay",
    "run_outcome_replay",
    "summary_stats",
]
