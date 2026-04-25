"""`bedrock fetch` — kommandoer rundt config-drevet fetch-pipeline.

Fase 6 session 28 introduserer kun `status`-subkommandoen. Neste
session(er) legger til `run <fetcher>` og `run --all`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from bedrock.cli._instrument_lookup import (
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_INSTRUMENTS_DIR,
)
from bedrock.config.fetch import (
    DEFAULT_FETCH_CONFIG_PATH,
    FetchConfig,
    FetchConfigError,
    FetcherStatus,
    check_staleness,
    load_fetch_config,
    status_report,
)
from bedrock.config.fetch_runner import (
    FetchRunResult,
    default_from_date,
    run_fetcher_by_name,
)
from bedrock.data.store import DataStore

DEFAULT_DB_PATH = Path("data/bedrock.db")


@click.group()
def fetch() -> None:
    """Config-drevet fetch-orkestrering (PLAN § 7.2)."""


@fetch.command("status")
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_FETCH_CONFIG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path til fetch-config YAML.",
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
    "--json",
    "as_json",
    is_flag=True,
    help="Skriv ut maskinlesbar JSON.",
)
def status_cmd(
    config_path: Path,
    db_path: Path,
    as_json: bool,
) -> None:
    """Vis staleness-status per fetcher.

    For hver fetcher i `fetch.yaml`: viser siste observasjon i DB,
    alder i timer, og fresh/STALE/NO_DATA-flag.
    """
    try:
        config = load_fetch_config(config_path)
    except FileNotFoundError as exc:
        raise click.UsageError(str(exc)) from exc
    except FetchConfigError as exc:
        raise click.UsageError(f"Kunne ikke laste fetch-config: {exc}") from exc

    if not db_path.exists() and not as_json:
        # OK — alle fetchere vil rapporteres som NO_DATA. Stille i
        # --json-modus for å bevare rent JSON-output.
        click.echo(
            f"(DB finnes ikke: {db_path} — alle fetchere vil rapporteres som NO_DATA)",
            err=True,
        )

    store = DataStore(db_path) if db_path.exists() else _DummyStore()
    now = datetime.now(timezone.utc)

    report = status_report(config, store, now=now)

    if as_json:
        payload = [_to_json(s) for s in report]
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        _print_table(config, report, now)


class _DummyStore:
    """Minimal stand-in for DataStore når DB ikke eksisterer.

    Returnerer None for alle tabeller — alle fetchere rapporteres som
    NO_DATA. Gir brukeren en nyttig første-gangs-status uten at vi
    trenger å instansiere en ekte DataStore (som ville opprettet filen).
    """

    def latest_observation_ts(self, table: str, ts_column: str = "ts") -> str | None:
        return None


def _to_json(status: FetcherStatus) -> dict:
    return status.model_dump(mode="json")


def _print_table(config: FetchConfig, report: list[FetcherStatus], now: datetime) -> None:
    click.echo(f"Fetch status  (now: {now.isoformat()})")
    click.echo("")
    header = f"{'fetcher':<22} {'status':<9} {'last_obs':<26} {'age_h':>8}  {'stale_h':>8}"
    click.echo(header)
    click.echo("-" * len(header))

    for s in report:
        if not s.has_data:
            status_text = "NO_DATA"
            last_obs = "(empty)"
            age = "-"
        elif s.is_stale:
            status_text = "STALE"
            last_obs = s.latest_observation.isoformat()
            age = f"{s.age_hours:.1f}"
        else:
            status_text = "fresh"
            last_obs = s.latest_observation.isoformat()
            age = f"{s.age_hours:.1f}"

        click.echo(f"{s.name:<22} {status_text:<9} {last_obs:<26} {age:>8}  {s.stale_hours:>8.1f}")


@fetch.command("run")
@click.argument("fetcher_name", required=False)
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_FETCH_CONFIG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
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
    "--from",
    "from_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Start-dato (YYYY-MM-DD). Default: stale_hours × 2 bak nå.",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Slutt-dato. Default: i dag.",
)
@click.option(
    "--stale-only",
    is_flag=True,
    help="Kjør kun fetchere som er stale.",
)
@click.option(
    "--instrument",
    "instrument_filter",
    default=None,
    help="Begrens til én instrument-id (case-insensitive).",
)
def run_cmd(
    fetcher_name: str | None,
    config_path: Path,
    db_path: Path,
    instruments_dir: Path,
    defaults_dir: Path,
    from_date: datetime | None,
    to_date: datetime | None,
    stale_only: bool,
    instrument_filter: str | None,
) -> None:
    """Kjør én eller alle fetchere basert på config.

    Eksempler:

        bedrock fetch run                   # alle fetchere
        bedrock fetch run prices            # kun prices
        bedrock fetch run --stale-only      # kun de som er stale
        bedrock fetch run weather --instrument Corn  # filtrer instrument
    """
    try:
        config = load_fetch_config(config_path)
    except FileNotFoundError as exc:
        raise click.UsageError(str(exc)) from exc

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    now = datetime.now(timezone.utc)

    # Bestem hvilke fetchere å kjøre
    if fetcher_name is not None:
        if fetcher_name not in config.fetchers:
            raise click.UsageError(
                f"Ukjent fetcher {fetcher_name!r}. Tilgjengelige: {sorted(config.fetchers.keys())}"
            )
        targets = [fetcher_name]
    else:
        targets = sorted(config.fetchers.keys())

    if stale_only:
        targets = [
            name
            for name in targets
            if check_staleness(name, config.fetchers[name], store, now=now).is_stale
        ]
        if not targets:
            click.echo("Ingen stale fetchere — alt er fresh.")
            return

    to_resolved = to_date.date() if to_date is not None else now.date()

    any_failures = False
    for name in targets:
        spec = config.fetchers[name]
        from_resolved = (
            from_date.date() if from_date is not None else default_from_date(spec, now=now)
        )

        click.echo(f"=== Running {name} ({spec.module}) from {from_resolved} to {to_resolved} ===")

        try:
            result = run_fetcher_by_name(
                name,
                store,
                spec,
                from_date=from_resolved,
                to_date=to_resolved,
                instruments_dir=instruments_dir,
                defaults_dir=defaults_dir,
                instrument_filter=instrument_filter,
            )
        except (KeyError, FileNotFoundError) as exc:
            click.echo(f"  FAIL: {exc}", err=True)
            any_failures = True
            continue

        _print_run_result(result)
        if result.fail_count > 0:
            any_failures = True

    if any_failures:
        click.get_current_context().exit(1)


def _print_run_result(result: FetchRunResult) -> None:
    for item in result.items:
        if item.ok:
            click.echo(f"  OK   {item.item_id} → {item.rows_written} row(s)")
        else:
            click.echo(f"  FAIL {item.item_id}: {item.error}", err=True)
    click.echo(
        f"  Summary: {result.ok_count}/{len(result.items)} ok, "
        f"{result.fail_count} failed, {result.total_rows} total rows"
    )


__all__ = ["fetch"]
