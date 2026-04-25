"""`bedrock backtest` — CLI for backtest-rammeverket (Fase 11 session 62).

Session 62 leverer kun `bedrock backtest run` med outcome-replay.
Senere subkommandoer (compare, replay-with-orchestrator, etc.) legges
til når orchestrator-replay er implementert.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click

from bedrock.backtest import (
    BacktestConfig,
    BacktestResult,
    compare_signals,
    format_compare_json,
    format_compare_markdown,
    format_json,
    format_markdown,
    run_orchestrator_replay,
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
@click.option(
    "--mode",
    type=click.Choice(["outcome", "orchestrator"], case_sensitive=False),
    default="outcome",
    show_default=True,
    help=(
        "Replay-modus. outcome=kun analog_outcomes-tabell (raskt). "
        "orchestrator=full Engine-kjøring as-of-date per ref_date "
        "(populerer score/grade, men tregt — sekunder per iterasjon)."
    ),
)
@click.option(
    "--step-days",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Steg mellom ref_dates (kun orchestrator-mode). 1=daglig, "
        "5=ukentlig, 21=månedlig. Default 1."
    ),
)
@click.option(
    "--direction",
    type=click.Choice(["buy", "sell"], case_sensitive=False),
    default="buy",
    show_default=True,
    help="Direction å rapportere (kun orchestrator-mode).",
)
@click.option(
    "--instruments-dir",
    type=click.Path(path_type=Path),
    default=Path("config/instruments"),
    show_default=True,
    help="Sti til instrument-YAML-katalog (kun orchestrator-mode).",
)
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="Hard cap på antall iterasjoner (kun orchestrator-mode). Ingen default.",
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
    mode: str,
    step_days: int,
    direction: str,
    instruments_dir: Path,
    max_iterations: int | None,
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
    if mode.lower() == "orchestrator":
        result = run_orchestrator_replay(
            store,
            cfg,
            instruments_dir=str(instruments_dir),
            direction=direction.lower(),
            step_days=step_days,
            max_iterations=max_iterations,
        )
    else:
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


@backtest.command("compare")
@click.option(
    "--v1",
    "v1_path",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Sti til v1-BacktestResult JSON (fra `backtest run --report json`).",
)
@click.option(
    "--v2",
    "v2_path",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Sti til v2-BacktestResult JSON.",
)
@click.option(
    "--label-v1",
    default="v1",
    show_default=True,
    help="Etikett for v1 i rapporten.",
)
@click.option(
    "--label-v2",
    default="v2",
    show_default=True,
    help="Etikett for v2 i rapporten.",
)
@click.option(
    "--report",
    "report_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Skriv compare-rapport til fil. Default: stdout.",
)
@click.option(
    "--max-rows",
    type=int,
    default=50,
    show_default=True,
    help="Max diff-rader i markdown (kun markdown-format).",
)
def compare_cmd(
    v1_path: Path,
    v2_path: Path,
    label_v1: str,
    label_v2: str,
    report_format: str,
    output: Path | None,
    max_rows: int,
) -> None:
    """Diff to BacktestResult-JSON-filer (regelsett-impact-tester per § 11.5).

    Eksempel:

        bedrock backtest run --instrument Gold --horizon-days 30 \\
            --mode orchestrator --report json --output v1.json
        # ... rediger gold.yaml ...
        bedrock backtest run --instrument Gold --horizon-days 30 \\
            --mode orchestrator --report json --output v2.json
        bedrock backtest compare --v1 v1.json --v2 v2.json \\
            --label-v1 baseline --label-v2 nye-vekter
    """
    v1 = _load_result_from_json(v1_path)
    v2 = _load_result_from_json(v2_path)
    report = compare_signals(v1, v2, label_v1=label_v1, label_v2=label_v2)
    if report_format.lower() == "json":
        text = format_compare_json(report)
    else:
        text = format_compare_markdown(report, max_rows=max_rows)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        click.echo(
            f"Wrote compare-rapport til {output} "
            f"(Δ={report.signal_count_delta}, n_changed={report.n_changed})"
        )
    else:
        click.echo(text)


def _load_result_from_json(path: Path) -> BacktestResult:
    """Les BacktestResult fra JSON-fil produsert av `format_json`.

    JSON-en har topnivå `config`, `report` (ignoreres her — vi
    re-aggregerer ved behov) og `signals`. Pydantic parser config og
    signals automatisk.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BacktestResult.model_validate(
        {"config": payload["config"], "signals": payload.get("signals", [])}
    )


def main() -> None:
    """Eksponert slik at `python -m bedrock.cli.backtest run ...` også funker."""
    backtest(standalone_mode=True)
    sys.exit(0)


if __name__ == "__main__":
    main()


__all__ = ["backtest"]
