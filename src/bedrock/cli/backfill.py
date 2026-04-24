"""`bedrock backfill` — kommandoer for å fylle SQLite-databasen med historikk.

Fase 3 session 10: kun `prices` subkommando (Stooq CSV).

Senere sessions:
- `backfill cot` (CFTC disaggregated + legacy)
- `backfill fundamentals` (FRED)
- `backfill weather` (ERA5 eller lignende)
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path

import click

from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import (
    CFTC_DISAGGREGATED_URL,
    CFTC_LEGACY_URL,
    build_socrata_query,
    fetch_cot_disaggregated,
    fetch_cot_legacy,
)
from bedrock.fetch.prices import STOOQ_CSV_URL, build_stooq_url_params, fetch_prices

_log = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/bedrock.db")


@click.group()
def backfill() -> None:
    """Fyll SQLite-databasen med historikk fra eksterne kilder."""


@backfill.command("prices")
@click.option(
    "--instrument",
    required=True,
    help="Bedrock-instrumentnavn (f.eks. Gold, EURUSD).",
)
@click.option(
    "--ticker",
    required=True,
    help="Stooq-ticker (f.eks. xauusd, eurusd). Case-insensitive.",
)
@click.option(
    "--from",
    "from_date",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Start-dato (YYYY-MM-DD) inklusiv.",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Slutt-dato (YYYY-MM-DD) inklusiv. Default: i dag.",
)
@click.option(
    "--tf",
    default="D1",
    show_default=True,
    help="Timeframe-tag lagret i DB (info, ikke Stooq-param).",
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
    "--dry-run",
    is_flag=True,
    help="Vis URL som ville blitt hentet. Ingen HTTP-kall, ingen skriving.",
)
def prices_cmd(
    instrument: str,
    ticker: str,
    from_date: datetime,
    to_date: datetime | None,
    tf: str,
    db_path: Path,
    dry_run: bool,
) -> None:
    """Backfill prisbarer fra Stooq til SQLite.

    Eksempel:

        bedrock backfill prices --instrument Gold --ticker xauusd --from 2016-01-01

    `--dry-run` bygger og viser URL uten å gjøre HTTP-kall eller skrive til DB.
    """
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_stooq_url_params(ticker, _from, _to)
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        click.echo(f"DRY-RUN  URL: {STOOQ_CSV_URL}?{param_str}")
        click.echo(f"DRY-RUN  Would write to: {db_path} (instrument={instrument}, tf={tf})")
        return

    click.echo(f"Fetching {instrument} ({ticker}) from {_from} to {_to}...")
    df = fetch_prices(ticker, _from, _to)
    click.echo(f"Fetched {len(df)} bars.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_prices(instrument, tf, df)
    click.echo(f"Wrote {written} bars to {db_path} (instrument={instrument}, tf={tf}).")


@backfill.command("cot-disaggregated")
@click.option(
    "--contract",
    required=True,
    help=(
        "CFTC kontrakt-navn, eksakt match mot "
        "`market_and_exchange_names`. F.eks. "
        "'GOLD - COMMODITY EXCHANGE INC.'"
    ),
)
@click.option(
    "--from",
    "from_date",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Start-dato (YYYY-MM-DD) inklusiv.",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Slutt-dato (YYYY-MM-DD) inklusiv. Default: i dag.",
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
    "--dry-run",
    is_flag=True,
    help="Vis URL og SoQL-parametre. Ingen HTTP-kall, ingen DB-skriving.",
)
def cot_disaggregated_cmd(
    contract: str,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    dry_run: bool,
) -> None:
    """Backfill CFTC disaggregated COT-rapporter til SQLite.

    Eksempel:

        bedrock backfill cot-disaggregated --contract "GOLD - COMMODITY EXCHANGE INC." --from 2010-01-01
    """
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_socrata_query(contract, _from, _to)
        click.echo(f"DRY-RUN  URL: {CFTC_DISAGGREGATED_URL}")
        click.echo(f"DRY-RUN  $where: {params['$where']}")
        click.echo(f"DRY-RUN  $order: {params['$order']}")
        click.echo(f"DRY-RUN  $limit: {params['$limit']}")
        click.echo(f"DRY-RUN  Would write to: {db_path}")
        return

    click.echo(f"Fetching COT disaggregated for {contract!r} from {_from} to {_to}...")
    df = fetch_cot_disaggregated(contract, _from, _to)
    click.echo(f"Fetched {len(df)} report(s).")

    if df.empty:
        click.echo("No rows to write.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_cot_disaggregated(df)
    click.echo(f"Wrote {written} report(s) to {db_path}.")


@backfill.command("cot-legacy")
@click.option(
    "--contract",
    required=True,
    help=(
        "CFTC kontrakt-navn, eksakt match mot "
        "`market_and_exchange_names`. F.eks. "
        "'GOLD - COMMODITY EXCHANGE INC.'"
    ),
)
@click.option(
    "--from",
    "from_date",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Start-dato (YYYY-MM-DD) inklusiv.",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Slutt-dato (YYYY-MM-DD) inklusiv. Default: i dag.",
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
    "--dry-run",
    is_flag=True,
    help="Vis URL og SoQL-parametre. Ingen HTTP-kall, ingen DB-skriving.",
)
def cot_legacy_cmd(
    contract: str,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    dry_run: bool,
) -> None:
    """Backfill CFTC legacy COT-rapporter til SQLite.

    Brukes for kontrakter uten disaggregated-rapport, og for historikk
    før 2010.

    Eksempel:

        bedrock backfill cot-legacy --contract "GOLD - COMMODITY EXCHANGE INC." --from 2006-01-01
    """
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_socrata_query(contract, _from, _to)
        click.echo(f"DRY-RUN  URL: {CFTC_LEGACY_URL}")
        click.echo(f"DRY-RUN  $where: {params['$where']}")
        click.echo(f"DRY-RUN  $order: {params['$order']}")
        click.echo(f"DRY-RUN  $limit: {params['$limit']}")
        click.echo(f"DRY-RUN  Would write to: {db_path}")
        return

    click.echo(f"Fetching COT legacy for {contract!r} from {_from} to {_to}...")
    df = fetch_cot_legacy(contract, _from, _to)
    click.echo(f"Fetched {len(df)} report(s).")

    if df.empty:
        click.echo("No rows to write.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_cot_legacy(df)
    click.echo(f"Wrote {written} report(s) to {db_path}.")


def main() -> None:
    """Eksponert slik at `python -m bedrock.cli.backfill prices ...` også funker."""
    backfill(standalone_mode=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
