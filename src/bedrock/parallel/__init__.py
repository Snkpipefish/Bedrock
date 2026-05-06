"""Fase 12 parallell-drift — sammenligning og monitoring.

Eksponerer to kjerne-API-er:

- ``compare`` / ``CompareReport`` — ad-hoc diff bedrock signals.json mot
  cot-explorers signals.json + agri_signals.json (manuell bruk via
  ``scripts/compare_signals_daily.py``).
- ``run_monitor`` / ``MonitorReport`` — automatisk sjekk av PLAN § 12.3
  cutover-kriterier (fetcher-freshness, pipeline-log-feil, bot-log
  agri-TP-overrides). Signal-diff fjernet i 12.9 follow-up.
"""

from bedrock.parallel.compare import (
    CompareReport,
    DiffEntry,
    NormalizedSignal,
    compare,
    format_compare_json,
    format_compare_markdown,
)
from bedrock.parallel.monitor import (
    CheckResult,
    MonitorReport,
    check_agri_tp_override,
    check_fetcher_freshness,
    check_pipeline_log_errors,
    format_monitor_json,
    format_monitor_text,
    run_monitor,
)

__all__ = [
    "CheckResult",
    "CompareReport",
    "DiffEntry",
    "MonitorReport",
    "NormalizedSignal",
    "check_agri_tp_override",
    "check_fetcher_freshness",
    "check_pipeline_log_errors",
    "compare",
    "format_compare_json",
    "format_compare_markdown",
    "format_monitor_json",
    "format_monitor_text",
    "run_monitor",
]
