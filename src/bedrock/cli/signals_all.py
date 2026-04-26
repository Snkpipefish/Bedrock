"""`bedrock signals-all` — regenerer signals.json for alle instrumenter.

Brukes av systemd-timer (`bedrock-signals-all.timer`) for å holde
``data/signals.json`` ferskt slik at compare-script (`scripts/
compare_signals_daily.py`) kan sammenligne mot cot-explorer's
output.

Bot-whitelist: ``--bot-only`` filtrerer til kun instrumenter som
står i ``config/bot_whitelist.yaml`` og transformerer instrument-id
til bot-navn (f.eks. "Gold" → "GOLD"). Brukes ved push til scalp-
edge-bot for å unngå at eksperimentelle instrumenter (Copper,
NaturalGas, BTC etc.) sendes.

Eksempel:

    bedrock signals-all
    bedrock signals-all --output data/signals.json
    bedrock signals-all --skip Gold  # generer alt unntatt Gold
    bedrock signals-all --bot-only --output data/signals_bot.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import structlog
import yaml

from bedrock.cli._instrument_lookup import (
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_INSTRUMENTS_DIR,
)
from bedrock.data.store import DataStore
from bedrock.orchestrator import generate_signals
from bedrock.orchestrator.score import OrchestratorError

DEFAULT_DB_PATH = Path("data/bedrock.db")
DEFAULT_OUTPUT_PATH = Path("data/signals.json")
DEFAULT_WHITELIST_PATH = Path("config/bot_whitelist.yaml")


def _load_bot_whitelist(path: Path) -> dict[str, str]:
    """Last bot-whitelist + navne-mapping fra YAML.

    Returns mapping bedrock-id → bot-name. Kaster ClickException hvis
    filen mangler eller ikke har 'mapping'-key.
    """
    if not path.exists():
        raise click.ClickException(
            f"Bot-whitelist mangler: {path}. Forventet YAML med 'mapping:' key."
        )
    data = yaml.safe_load(path.read_text())
    mapping = data.get("mapping") if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        raise click.ClickException(f"{path}: mangler 'mapping:' dict.")
    return {str(k): str(v) for k, v in mapping.items()}


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
@click.option(
    "--bot-only",
    is_flag=True,
    default=False,
    help="Filtrer til kun whitelist-instrumenter + transformer instrument-id "
    "til bot-navn. Brukes ved push til scalp-edge-bot.",
)
@click.option(
    "--whitelist",
    "whitelist_path",
    default=DEFAULT_WHITELIST_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path til bot-whitelist YAML (kun relevant med --bot-only).",
)
def signals_all_cmd(
    db_path: Path,
    instruments_dir: Path,
    defaults_dir: Path,
    output_path: Path,
    skip_instruments: tuple[str, ...],
    continue_on_error: bool,
    bot_only: bool,
    whitelist_path: Path,
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

    # Last whitelist hvis --bot-only er på
    whitelist_mapping: dict[str, str] | None = None
    if bot_only:
        whitelist_mapping = _load_bot_whitelist(whitelist_path)
        # Filtrer instrumenter til de som er i whitelist (case-insensitive)
        wl_lower = {k.lower() for k in whitelist_mapping}
        instruments = [i for i in instruments if i.lower() in wl_lower]
        if not instruments:
            raise click.UsageError(
                f"Ingen av instrumentene i {instruments_dir} matcher whitelist i {whitelist_path}."
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
            # Bot-only: transformer instrument-id til bot-navn
            bot_name: str | None = None
            if whitelist_mapping is not None:
                # Match case-insensitivt mot mapping (key er bedrock-id)
                for bedrock_id, mapped in whitelist_mapping.items():
                    if bedrock_id.lower() == instrument_id.lower():
                        bot_name = mapped
                        break
            for entry in result.entries:
                e_dict = entry.model_dump(mode="json")
                if bot_name is not None:
                    e_dict["instrument"] = bot_name
                all_entries.append(e_dict)
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
