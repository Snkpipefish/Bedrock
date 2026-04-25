"""`bedrock signals-all` — regenerer signals.json for alle instrumenter.

Brukes av systemd-timer (`bedrock-signals-all.timer`) for å holde
``data/signals.json`` ferskt slik at compare-script (`scripts/
compare_signals_daily.py`) kan sammenligne mot cot-explorer's
output.

Eksempel:

    bedrock signals-all
    bedrock signals-all --output data/signals.json
    bedrock signals-all --skip Gold  # generer alt unntatt Gold
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import structlog

from bedrock.cli._instrument_lookup import (
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_INSTRUMENTS_DIR,
)
from bedrock.data.store import DataStore
from bedrock.orchestrator import generate_signals
from bedrock.orchestrator.score import OrchestratorError

DEFAULT_DB_PATH = Path("data/bedrock.db")
DEFAULT_OUTPUT_PATH = Path("data/signals.json")

_log = structlog.get_logger(__name__)


def _discover_instrument_ids(instruments_dir: Path) -> list[str]:
    """Returner instrument_id fra hver `*.yaml` i ``instruments_dir``.

    Bruker filnavnet (uten ``.yaml``) capitalize-d som default. Dette
    matcher prosjektets konvensjon (`gold.yaml` → ``Gold``,
    `cotton.yaml` → ``Cotton``). Skipper filer som starter med ``_``
    eller heter ``family_*``-templates.
    """
    if not instruments_dir.exists():
        return []
    ids: list[str] = []
    for path in sorted(instruments_dir.glob("*.yaml")):
        stem = path.stem
        if stem.startswith("_") or stem.startswith("family_"):
            continue
        ids.append(stem.capitalize())
    return ids


@click.command(name="signals-all")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path til SQLite-databasen.",
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
    "--output",
    "output_path",
    default=DEFAULT_OUTPUT_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path hvor signals.json skrives.",
)
@click.option(
    "--skip",
    "skip_instruments",
    multiple=True,
    help="Hopp over disse instrumentene (kan gjentas).",
)
@click.option(
    "--continue-on-error",
    is_flag=True,
    default=True,
    help="Fortsett selv om ett instrument feiler (default: på).",
)
def signals_all_cmd(
    db_path: Path,
    instruments_dir: Path,
    defaults_dir: Path,
    output_path: Path,
    skip_instruments: tuple[str, ...],
    continue_on_error: bool,
) -> None:
    """Regenerer signals.json for alle instrumenter i ``instruments_dir``.

    Iterer over hver `*.yaml`-fil, kjør orchestrator, samle alle entries
    til en flat liste, og skriv til ``output_path``. Brukes av systemd-
    timer for daglig regenerering.
    """
    # Sjekk instruments-dir først (rask, ingen avhengighet) før DB.
    instruments = _discover_instrument_ids(instruments_dir)
    if not instruments:
        raise click.UsageError(
            f"Ingen instrumenter funnet i {instruments_dir}. Forventer *.yaml-filer."
        )

    if not db_path.exists():
        raise click.UsageError(
            f"DB-fil finnes ikke: {db_path}. Kjør `bedrock backfill prices` først."
        )

    skip_lower = {s.lower() for s in skip_instruments}
    instruments = [i for i in instruments if i.lower() not in skip_lower]

    store = DataStore(db_path)
    now = datetime.now(timezone.utc)
    all_entries: list[dict] = []
    failures: list[tuple[str, str]] = []

    for instrument_id in instruments:
        try:
            result = generate_signals(
                instrument_id,
                store,
                instruments_dir=instruments_dir,
                defaults_dir=defaults_dir,
                snapshot_path=None,
                write_snapshot=False,
                now=now,
            )
            for entry in result.entries:
                all_entries.append(entry.model_dump(mode="json"))
            click.echo(f"  {instrument_id}: {len(result.entries)} entries")
        except (OrchestratorError, Exception) as exc:
            failures.append((instrument_id, str(exc)))
            _log.warning(
                "signals_all.instrument_failed",
                instrument=instrument_id,
                error=str(exc),
            )
            click.echo(f"  {instrument_id}: FAILED ({exc})", err=True)
            if not continue_on_error:
                raise click.ClickException(
                    f"{instrument_id} feilet og --continue-on-error er av: {exc}"
                ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(all_entries, indent=2, default=str))

    click.echo("")
    click.echo(
        f"Wrote {len(all_entries)} entries from "
        f"{len(instruments) - len(failures)}/{len(instruments)} instruments "
        f"to {output_path}"
    )
    if failures:
        click.echo(f"Failures: {len(failures)}", err=True)
        for inst, err in failures:
            click.echo(f"  - {inst}: {err}", err=True)
        sys.exit(1 if not continue_on_error else 0)
