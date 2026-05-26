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
DEFAULT_AGRI_OUTPUT_PATH = Path("data/agri_signals.json")
DEFAULT_WHITELIST_PATH = Path("config/bot_whitelist.yaml")

# Asset-classes som UI klassifiserer som "agri" (vs "financial").
# Matcher signal_server/endpoints/ui.py's split: /api/ui/setups/agri
# leser agri_signals_path, /api/ui/setups/financial leser signals_path.
_AGRI_ASSET_CLASSES = frozenset({"grains", "softs"})

# Felter som bumpes hver kjøring uavhengig av faktisk innholds-endring.
# Strippes bort før equality-sjekk i `_write_if_changed` slik at intra-day
# regen-runs som produserer identisk decision-state ikke gir unødig
# disk-IO eller bot-poll-trigger.
_VOLATILE_SETUP_FIELDS = frozenset({"first_seen", "last_updated"})


def _strip_volatile(entries: list[dict]) -> list[dict]:
    """Returnerer en kopi av entries med volatile timestamp-felter fjernet."""
    out = []
    for e in entries:
        copy = dict(e)
        setup = copy.get("setup")
        if isinstance(setup, dict):
            copy["setup"] = {k: v for k, v in setup.items() if k not in _VOLATILE_SETUP_FIELDS}
        out.append(copy)
    return out


def _write_if_changed(path: Path, entries: list[dict]) -> bool:
    """Skriv `entries` som JSON til `path`. Hopper over skriving hvis filen
    allerede inneholder identiske decision-relevante felter (volatile
    timestamps strippes før sammenligning).

    Returnerer True hvis filen ble skrevet, False hvis den ble hoppet over.
    Ved skip bevares filens mtime — UI-er og bot som leser mtime for å
    detektere fersk-data trigges ikke unødig.
    """
    new_payload = json.dumps(entries, indent=2, default=str)
    if path.exists():
        try:
            existing_entries = json.loads(path.read_text())
            if isinstance(existing_entries, list) and _strip_volatile(
                existing_entries
            ) == _strip_volatile(entries):
                return False
        except (json.JSONDecodeError, OSError):
            pass
    path.write_text(new_payload)
    return True


def _read_asset_class(yaml_path: Path) -> str | None:
    """Hent asset_class fra en instrument-YAML. Returnerer None ved feil."""
    try:
        data = yaml.safe_load(yaml_path.read_text())
        if not isinstance(data, dict):
            return None
        instrument = data.get("instrument", {})
        if not isinstance(instrument, dict):
            return None
        ac = instrument.get("asset_class")
        return str(ac) if ac else None
    except (OSError, yaml.YAMLError):
        return None


# ─────────────────────────────────────────────────────────────
# Permanent-disabled-guard (session 2026-05-26)
# ─────────────────────────────────────────────────────────────
# Hardkodet kill-switch for instrumenter som ALDRI skal pushes til
# boten — uavhengig av YAML-config eller per-instrument bot_whitelist.
# Brukes for instrumenter som er strukturelt ulønnsomme (negativ swap
# i begge retninger, etc.) eller har dårlig kapital-effektivitet.
#
# Ved et uhell-reaktiverings-forsøk: selv om noen legger til linjer i
# bot_whitelist.yaml eller rename'r en _disabled_xxx.yaml tilbake, vil
# disse fortsatt filtreres bort fra bot-feeden. For å faktisk reaktivere
# må man fjerne navnet fra dette settet (eksplisitt kode-endring,
# pull-request-synlig).
#
# Tilsvarende guard finnes i src/bedrock/bot/entry.py som siste-line-
# of-defense på selve bot-siden.
PERMANENTLY_DISABLED: frozenset[str] = frozenset(
    {
        "Platinum",  # negativ swap begge veier + tap-historikk
        "BTC",  # 35% av margin, lav PnL-bidrag
        "ETH",  # 1.5% spread + lav PnL-bidrag
    }
)


def _load_bot_whitelist(path: Path) -> dict[str, str]:
    """Last bot-whitelist + navne-mapping fra YAML.

    Returns mapping bedrock-id → bot-name. Kaster ClickException hvis
    filen mangler eller ikke har 'mapping'-key. Filtrerer alltid bort
    instrumenter i ``PERMANENTLY_DISABLED`` — også hvis de skulle ha
    sneket seg tilbake inn i YAML-en.
    """
    if not path.exists():
        raise click.ClickException(
            f"Bot-whitelist mangler: {path}. Forventet YAML med 'mapping:' key."
        )
    data = yaml.safe_load(path.read_text())
    mapping = data.get("mapping") if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        raise click.ClickException(f"{path}: mangler 'mapping:' dict.")
    result: dict[str, str] = {}
    for k, v in mapping.items():
        if k in PERMANENTLY_DISABLED:
            _log.warning(
                "bot_whitelist.permanently_disabled_blocked",
                instrument=k,
                note="fjern fra PERMANENTLY_DISABLED i signals_all.py for å reaktivere",
            )
            continue
        result[str(k)] = str(v)
    return result


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
@click.option(
    "--agri-output",
    "agri_output_path",
    default=DEFAULT_AGRI_OUTPUT_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path for agri-signals (grains/softs). Hvis --no-split eller --bot-only, ignoreres.",
)
@click.option(
    "--split/--no-split",
    "split_assets",
    default=True,
    show_default=True,
    help="Skriv financial → signals.json + agri → agri_signals.json. "
    "Default på, men deaktivert ved --bot-only.",
)
@click.option(
    "--horizons",
    "horizons_filter",
    multiple=True,
    type=click.Choice(["scalp", "swing", "makro"], case_sensitive=False),
    help="Filtrer output til kun gitte horisonter (kan gjentas). "
    "Default: alle 3. Brukes av per-horisont-cadence-timere; "
    "engine kjører fortsatt full beregning per instrument, kun "
    "skriving filtreres.",
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
    agri_output_path: Path,
    split_assets: bool,
    horizons_filter: tuple[str, ...],
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

            # Tag asset_class for split-skriving + UI-bruk
            yaml_path = instruments_dir / f"{instrument_id.lower()}.yaml"
            asset_class = _read_asset_class(yaml_path) if yaml_path.exists() else None

            horizons_lower = {h.lower() for h in horizons_filter} if horizons_filter else None
            kept = 0
            for entry in result.entries:
                e_dict = entry.model_dump(mode="json")
                if horizons_lower is not None:
                    if str(e_dict.get("horizon", "")).lower() not in horizons_lower:
                        continue
                if bot_name is not None:
                    e_dict["instrument"] = bot_name
                if asset_class is not None:
                    e_dict["asset_class"] = asset_class
                all_entries.append(e_dict)
                kept += 1
            if horizons_lower is not None:
                click.echo(
                    f"  {instrument_id}: {kept}/{len(result.entries)} entries (horisont-filter)"
                )
            else:
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

    # Splitt financial/agri hvis split_assets er på OG vi ikke er i bot-only.
    # Bot-only writes always to a single output file (signals_bot.json) since
    # bot ikke skiller mellom financial og agri.
    if split_assets and not bot_only:
        agri_entries = [e for e in all_entries if e.get("asset_class") in _AGRI_ASSET_CLASSES]
        financial_entries = [
            e for e in all_entries if e.get("asset_class") not in _AGRI_ASSET_CLASSES
        ]
        fin_written = _write_if_changed(output_path, financial_entries)
        agri_output_path.parent.mkdir(parents=True, exist_ok=True)
        agri_written = _write_if_changed(agri_output_path, agri_entries)
        click.echo("")
        fin_tag = "Wrote" if fin_written else "Unchanged (skipped)"
        agri_tag = "Wrote" if agri_written else "Unchanged (skipped)"
        click.echo(f"{fin_tag} {len(financial_entries)} financial entries to {output_path}")
        click.echo(f"{agri_tag} {len(agri_entries)} agri entries to {agri_output_path}")
    else:
        written = _write_if_changed(output_path, all_entries)
        click.echo("")
        tag = "Wrote" if written else "Unchanged (skipped)"
        click.echo(
            f"{tag} {len(all_entries)} entries from "
            f"{len(instruments) - len(failures)}/{len(instruments)} instruments "
            f"to {output_path}"
        )
    if failures:
        click.echo(f"Failures: {len(failures)}", err=True)
        for inst, err in failures:
            click.echo(f"  - {inst}: {err}", err=True)
        sys.exit(1 if not continue_on_error else 0)
