"""`bedrock signals <instrument_id>` — kjør orchestrator fra CLI.

Eksempler:

    bedrock signals Gold --horizon SWING
    bedrock signals Corn
    bedrock signals Gold --snapshot data/setups/gold.json
    bedrock signals Gold --horizon SWING --json

Viser per (direction, horizon):
- score + grade + published-flag
- gates_triggered (hvis noen)
- setup entry/SL/TP/RR + setup_id (hvis funnet)
- skip_reason (hvis ingen setup funnet)

Formål: ende-til-ende CLI-demo av scoring + setup + hysterese uten
web-UI. Brukes til manuell verifikasjon og debugging.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from bedrock.cli._instrument_lookup import (
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_INSTRUMENTS_DIR,
)
from bedrock.data.store import DataStore
from bedrock.orchestrator import generate_signals
from bedrock.orchestrator.score import OrchestratorError
from bedrock.setups.generator import Direction

DEFAULT_DB_PATH = Path("data/bedrock.db")


@click.command()
@click.argument("instrument_id")
@click.option(
    "--horizon",
    "horizons",
    multiple=True,
    help=(
        "Begrens til denne horisonten (kan gjentas). Default: alle "
        "horisonter fra YAML (financial) eller SCALP+SWING+MAKRO (agri)."
    ),
)
@click.option(
    "--direction",
    "directions",
    type=click.Choice(["BUY", "SELL"], case_sensitive=False),
    multiple=True,
    help="Begrens til retning (kan gjentas). Default: begge.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path til SQLite-databasen med prisdata.",
)
@click.option(
    "--instruments-dir",
    "instruments_dir",
    default=DEFAULT_INSTRUMENTS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--defaults-dir",
    "defaults_dir",
    default=DEFAULT_DEFAULTS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--snapshot",
    "snapshot_path",
    default=None,
    type=click.Path(path_type=Path),
    help="Path til snapshot-fil for hysterese (leses + skrives).",
)
@click.option(
    "--price-tf",
    default="D1",
    show_default=True,
    help="Timeframe for pris-oppslag.",
)
@click.option(
    "--price-lookback",
    default=250,
    show_default=True,
    type=int,
    help="Antall barer å hente.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Skriv ut maskinlesbar JSON istedenfor human-readable tabell.",
)
@click.option(
    "--no-snapshot-write",
    is_flag=True,
    help="Ikke skriv ny snapshot-fil (kun les forrige).",
)
def signals_cmd(
    instrument_id: str,
    horizons: tuple[str, ...],
    directions: tuple[str, ...],
    db_path: Path,
    instruments_dir: Path,
    defaults_dir: Path,
    snapshot_path: Path | None,
    price_tf: str,
    price_lookback: int,
    as_json: bool,
    no_snapshot_write: bool,
) -> None:
    """Kjør scoring + setup-generering for INSTRUMENT_ID.

    Eksempel:

        bedrock signals Gold --horizon SWING

    Leser prisdata fra SQLite (`--db`), laster YAML-config fra
    `--instruments-dir`, og kjører full orchestrator-pipeline.
    """
    if not db_path.exists():
        raise click.UsageError(
            f"DB-fil finnes ikke: {db_path}. Kjør `bedrock backfill prices` "
            f"først, eller oppgi --db."
        )

    store = DataStore(db_path)
    # Direction-enum har lowercase values; CLI-argumenter normaliseres
    direction_list = (
        [Direction(d.lower()) for d in directions] if directions else None
    )
    horizon_list = list(horizons) if horizons else None

    try:
        result = generate_signals(
            instrument_id,
            store,
            horizons=horizon_list,
            directions=direction_list,
            instruments_dir=instruments_dir,
            defaults_dir=defaults_dir,
            snapshot_path=snapshot_path,
            write_snapshot=not no_snapshot_write,
            now=datetime.now(timezone.utc),
            price_tf=price_tf,
            price_lookback=price_lookback,
        )
    except OrchestratorError as exc:
        raise click.UsageError(str(exc)) from exc

    if as_json:
        _print_json(result)
    else:
        _print_table(result)


def _print_json(result) -> None:  # noqa: ANN001
    """Full JSON-dump for programatisk forbruk."""
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


def _print_table(result) -> None:  # noqa: ANN001
    """Menneskelesbar oversikt per entry."""
    click.echo(f"Instrument: {result.instrument}")
    click.echo(f"Run: {result.run_ts.isoformat()}")
    if result.snapshot_written:
        click.echo(f"Snapshot written: {result.snapshot_written}")
    click.echo("")

    for entry in result.entries:
        _print_entry(entry)
        click.echo("")


def _print_entry(entry) -> None:  # noqa: ANN001
    marker = "PUBLISH" if entry.published else "       "
    setup_status = "SETUP" if entry.setup is not None else "-----"
    click.echo(
        f"[{marker}] {setup_status} {entry.direction.value.upper():4s} "
        f"{entry.horizon.value.upper():6s}  score={entry.score:6.3f}/"
        f"{entry.max_score:<5.1f}  grade={entry.grade}"
    )
    if entry.gates_triggered:
        click.echo(
            f"         gates_triggered: {', '.join(entry.gates_triggered)}"
        )
    if entry.setup is not None:
        s = entry.setup.setup
        rr_str = f"{s.rr:.2f}" if s.rr is not None else "trailing"
        tp_str = f"{s.tp:.4f}" if s.tp is not None else "trailing"
        click.echo(
            f"         id={entry.setup.setup_id}  "
            f"entry={s.entry:.4f}  sl={s.sl:.4f}  tp={tp_str}  rr={rr_str}"
        )
        click.echo(
            f"         first_seen={entry.setup.first_seen.isoformat()}  "
            f"last={entry.setup.last_updated.isoformat()}"
        )
    elif entry.skip_reason:
        click.echo(f"         skip: {entry.skip_reason}")

    # Publisering-gulv
    click.echo(f"         min_score_publish={entry.min_score_publish:.2f}")


def main() -> None:
    signals_cmd(standalone_mode=True)
    sys.exit(0)


__all__ = ["signals_cmd"]
