"""`bedrock fetch` — kommandoer rundt config-drevet fetch-pipeline.

Fase 6 session 28 introduserer kun `status`-subkommandoen. Neste
session(er) legger til `run <fetcher>` og `run --all`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from bedrock.config.fetch import (
    DEFAULT_FETCH_CONFIG_PATH,
    FetchConfig,
    FetchConfigError,
    FetcherStatus,
    load_fetch_config,
    status_report,
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
            f"(DB finnes ikke: {db_path} — alle fetchere vil rapporteres "
            f"som NO_DATA)",
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
    header = (
        f"{'fetcher':<22} {'status':<9} {'last_obs':<26} "
        f"{'age_h':>8}  {'stale_h':>8}"
    )
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

        click.echo(
            f"{s.name:<22} {status_text:<9} {last_obs:<26} "
            f"{age:>8}  {s.stale_hours:>8.1f}"
        )


__all__ = ["fetch"]
