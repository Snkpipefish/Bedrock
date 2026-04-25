"""`bedrock backtest` — CLI for backtest-rammeverket (Fase 11 session 62).

Session 62 leverer kun `bedrock backtest run` med outcome-replay.
Senere subkommandoer (compare, replay-with-orchestrator, etc.) legges
til når orchestrator-replay er implementert.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click

from bedrock.backtest import (
    BacktestConfig,
    format_json,
    format_markdown,
    run_outcome_replay,
    summary_stats,
)
from bedrock.data.store import DataStore

DEFAULT_DB_PATH = Path("data/bedrock.db")


@click.group()
def backtest() -> None:
    """Backtest-rammeverk — kjør historisk replay og rapporter performance."""


@backtest.command("run")
@click.option(
    "--instrument",
    required=True,
    help="Bedrock-instrument-ID (f.eks. Gold, Corn).",
)
@click.option(
    "--horizon-days",
    type=int,
    default=30,
    show_default=True,
    help="Forward-vindu i dager. Må matche en horizon i analog_outcomes.",
)
@click.option(
    "--from",
    "from_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Start-dato (YYYY-MM-DD). Default: hele tilgjengelige historikken.",
)
@click.option(
    "--to",
    "to_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Slutt-dato (YYYY-MM-DD). Default: alt fram til siste outcome.",
)
@click.option(
    "--threshold-pct",
    type=float,
    default=3.0,
    show_default=True,
    help="Hit-terskel i %. Forward_return ≥ threshold = hit.",
)
@click.option(
    "--report",
    "report_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output-format.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Skriv rapport til fil. Default: stdout.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path til SQLite-databasen.",
)
def run_cmd(
    instrument: str,
    horizon_days: int,
    from_date: datetime | None,
    to_date: datetime | None,
    threshold_pct: float,
    report_format: str,
    output: Path | None,
    db_path: Path,
) -> None:
    """Kjør outcome-replay backtest mot analog_outcomes-tabellen.

    Eksempel:

        bedrock backtest run --instrument Gold --horizon-days 30 \\
            --from 2024-01-01 --to 2024-12-31

        bedrock backtest run --instrument Corn --horizon-days 90 \\
            --report json --output reports/corn-90d.json

    Per session 62: leser pre-beregnet `analog_outcomes` for
    (instrument, horizon_days). Score/grade/published-felter er
    ikke populert (kommer i orchestrator-replay senere session).
    """
    if not db_path.exists():
        raise click.UsageError(
            f"DB ikke funnet: {db_path}. Kjør `bedrock backfill outcomes` først."
        )

    cfg = BacktestConfig(
        instrument=instrument,
        horizon_days=horizon_days,
        from_date=from_date.date() if from_date is not None else None,
        to_date=to_date.date() if to_date is not None else None,
        outcome_threshold_pct=threshold_pct,
        report_format=report_format.lower(),  # type: ignore[arg-type]
    )

    store = DataStore(db_path)
    result = run_outcome_replay(store, cfg)
    report = summary_stats(result)

    if cfg.report_format == "json":
        text = format_json(result, report)
    else:
        text = format_markdown(result, report)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        click.echo(f"Wrote backtest report to {output} ({report.n_signals} signals)")
    else:
        click.echo(text)


def main() -> None:
    """Eksponert slik at `python -m bedrock.cli.backtest run ...` også funker."""
    backtest(standalone_mode=True)
    sys.exit(0)


if __name__ == "__main__":
    main()


__all__ = ["backtest"]
