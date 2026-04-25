"""Daglig signal-diff bedrock vs cot-explorer.

Tynn CLI-wrapper. All logikk i `bedrock.parallel.compare`.

Eksempel:

    PYTHONPATH=src python scripts/compare_signals_daily.py
    PYTHONPATH=src python scripts/compare_signals_daily.py \\
        --output data/_meta/compare_$(date +%F).md

Default: leser bedrock data/signals.json og cot-explorer
~/cot-explorer/data/signals.json + ~/cot-explorer/data/agri_signals.json,
skriver markdown til stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bedrock.parallel.compare import (
    compare,
    format_compare_json,
    format_compare_markdown,
)

DEFAULT_BEDROCK_SIGNALS = Path("data/signals.json")
DEFAULT_OLD_SIGNALS = [
    Path.home() / "cot-explorer" / "data" / "signals.json",
    Path.home() / "cot-explorer" / "data" / "agri_signals.json",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bedrock",
        type=Path,
        default=DEFAULT_BEDROCK_SIGNALS,
        help=f"Sti til bedrock signals.json. Default: {DEFAULT_BEDROCK_SIGNALS}",
    )
    parser.add_argument(
        "--old",
        type=Path,
        action="append",
        default=None,
        help=(
            "Sti til gammel signals-fil. Kan gis flere ganger. "
            f"Default: {DEFAULT_OLD_SIGNALS[0]} + {DEFAULT_OLD_SIGNALS[1]}"
        ),
    )
    parser.add_argument(
        "--report",
        choices=("markdown", "json"),
        default="markdown",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=100,
        help="Maks antall diff-rader i markdown. Default 100.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Skriv rapport til fil i stedet for stdout.",
    )
    args = parser.parse_args(argv)

    old_paths = args.old if args.old else DEFAULT_OLD_SIGNALS
    report = compare(bedrock_path=args.bedrock, old_paths=old_paths)

    if args.report == "json":
        text = format_compare_json(report)
    else:
        text = format_compare_markdown(report, max_rows=args.max_rows)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
