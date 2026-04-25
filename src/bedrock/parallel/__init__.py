"""Fase 12 parallell-drift — sammenligning og monitoring.

Eksponerer to kjerne-API-er:

- ``compare`` / ``CompareReport`` — daglig diff bedrock signals.json mot
  cot-explorers signals.json + agri_signals.json.
- ``run_monitor`` / ``MonitorReport`` — automatisk sjekk av PLAN § 12.3
  cutover-kriterier (fetcher-freshness, pipeline-log-feil, bot-log
  agri-TP-overrides, signal-diff).

Begge har tynne CLI-wrappers i ``scripts/`` (``compare_signals_daily.py``
og ``monitor_pipeline.py``).
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
    check_signal_diff,
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
    "check_signal_diff",
    "compare",
    "format_compare_json",
    "format_compare_markdown",
    "format_monitor_json",
    "format_monitor_text",
    "run_monitor",
]
