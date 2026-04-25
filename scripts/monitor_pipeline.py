"""Bedrock parallell-drift pipeline-monitor (PLAN § 12.3).

Tynn CLI-wrapper. All logikk i `bedrock.parallel.monitor`.

Eksempel:

    PYTHONPATH=src python scripts/monitor_pipeline.py
    PYTHONPATH=src python scripts/monitor_pipeline.py --report json \\
        --output data/_meta/monitor_$(date +%F).json

Returnerer exit-code 0 hvis alle delsjekker er OK, ellers 1.
Egnet som systemd-timer-payload som varsler ved fail.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bedrock.parallel.monitor import (
    DEFAULT_BEDROCK_SIGNALS,
    DEFAULT_BOT_LOG,
    DEFAULT_DB,
    DEFAULT_FETCH_YAML,
    DEFAULT_OLD_SIGNALS,
    DEFAULT_PIPELINE_LOG,
    format_monitor_json,
    format_monitor_text,
    run_monitor,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-yaml", type=Path, default=DEFAULT_FETCH_YAML)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--pipeline-log", type=Path, default=DEFAULT_PIPELINE_LOG)
    parser.add_argument("--bot-log", type=Path, default=DEFAULT_BOT_LOG)
    parser.add_argument("--bedrock-signals", type=Path, default=DEFAULT_BEDROCK_SIGNALS)
    parser.add_argument(
        "--old-signals",
        type=Path,
        action="append",
        default=None,
        help="Sti til gammel signal-fil; kan gis flere ganger.",
    )
    parser.add_argument("--report", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    old_signals = args.old_signals if args.old_signals else list(DEFAULT_OLD_SIGNALS)

    report = run_monitor(
        fetch_yaml=args.fetch_yaml,
        db=args.db,
        pipeline_log=args.pipeline_log,
        bot_log=args.bot_log,
        bedrock_signals=args.bedrock_signals,
        old_signals=old_signals,
    )

    text = format_monitor_json(report) if args.report == "json" else format_monitor_text(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if report.overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
