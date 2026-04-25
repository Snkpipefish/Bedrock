"""`bedrock backfill` — kommandoer for å fylle SQLite-databasen med historikk.

Fase 3: 5 subkommandoer (prices, cot-disaggregated, cot-legacy, weather,
fundamentals).

Fase 5 session 22 la til:

- `--instrument <id>`-flagg på hver subkommando. Når satt, leses
  sentrale felter (ticker, contract, lat/lon, series-ID-er) fra
  `config/instruments/<id>.yaml`. Eksplisitte args overstyrer fortsatt.
- Per-item resiliens for `fundamentals` (og generelt: hvis `--instrument`
  gir liste med flere items): én feil aborterer ikke, summary + retry-
  kommandoer på slutten.
- Felles `--instruments-dir`-overstyring (for testing og alternative config-
  sett).
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path

import click

from bedrock.cli._instrument_lookup import DEFAULT_INSTRUMENTS_DIR, find_instrument
from bedrock.cli._iteration import run_with_summary
from bedrock.config.secrets import get_secret
from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import (
    CFTC_DISAGGREGATED_URL,
    CFTC_LEGACY_URL,
    build_socrata_query,
    fetch_cot_disaggregated,
    fetch_cot_legacy,
)
from bedrock.fetch.fred import (
    FRED_OBSERVATIONS_URL,
    build_fred_params,
    fetch_fred_series,
)
from bedrock.fetch.prices import STOOQ_CSV_URL, build_stooq_url_params, fetch_prices
from bedrock.fetch.weather import (
    OPEN_METEO_ARCHIVE_URL,
    build_open_meteo_params,
    fetch_weather,
)

_FRED_API_KEY_ENV = "FRED_API_KEY"
_MASKED_API_KEY = "***"

_log = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/bedrock.db")


# ---------------------------------------------------------------------------
# Felles CLI-options
# ---------------------------------------------------------------------------


def _instruments_dir_option(f):
    return click.option(
        "--instruments-dir",
        "instruments_dir",
        default=DEFAULT_INSTRUMENTS_DIR,
        show_default=True,
        type=click.Path(path_type=Path),
        help="Katalog med instrument-YAML-er (brukt av --instrument).",
    )(f)


# ---------------------------------------------------------------------------
# Gruppe
# ---------------------------------------------------------------------------


@click.group()
def backfill() -> None:
    """Fyll SQLite-databasen med historikk fra eksterne kilder."""


# ---------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------


@backfill.command("prices")
@click.option(
    "--instrument",
    default=None,
    help=(
        "Bedrock-instrumentnavn. Hvis --ticker ikke er gitt, slås ticker "
        "opp i config/instruments/<id>.yaml. Påkrevd (blir DB-tag)."
    ),
)
@click.option(
    "--ticker",
    default=None,
    help=(
        "Stooq-ticker (f.eks. xauusd). Hvis utelatt, brukes instrumentets "
        "`stooq_ticker` (eller `ticker`) fra YAML."
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
@_instruments_dir_option
@click.option(
    "--dry-run",
    is_flag=True,
    help="Vis URL som ville blitt hentet. Ingen HTTP-kall, ingen skriving.",
)
def prices_cmd(
    instrument: str | None,
    ticker: str | None,
    from_date: datetime,
    to_date: datetime | None,
    tf: str,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill prisbarer fra Stooq til SQLite.

    Eksempel:

        bedrock backfill prices --instrument Gold --ticker xauusd --from 2016-01-01
        bedrock backfill prices --instrument Gold --from 2016-01-01  # ticker fra YAML

    `--dry-run` bygger og viser URL uten å gjøre HTTP-kall eller skrive til DB.
    """
    if instrument is None:
        raise click.UsageError("--instrument er påkrevd.")

    resolved_instrument, resolved_ticker = _resolve_prices(instrument, ticker, instruments_dir)

    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_stooq_url_params(resolved_ticker, _from, _to)
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        click.echo(f"DRY-RUN  URL: {STOOQ_CSV_URL}?{param_str}")
        click.echo(
            f"DRY-RUN  Would write to: {db_path} (instrument={resolved_instrument}, tf={tf})"
        )
        return

    click.echo(f"Fetching {resolved_instrument} ({resolved_ticker}) from {_from} to {_to}...")
    df = fetch_prices(resolved_ticker, _from, _to)
    click.echo(f"Fetched {len(df)} bars.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_prices(resolved_instrument, tf, df)
    click.echo(f"Wrote {written} bars to {db_path} (instrument={resolved_instrument}, tf={tf}).")


def _resolve_prices(
    instrument_arg: str,
    ticker_arg: str | None,
    instruments_dir: Path,
) -> tuple[str, str]:
    """Returner (DB-instrument-tag, stooq-ticker) etter --instrument + YAML-
    oppslag.

    Regler:

    - Eksplisitt `--ticker` vinner: (instrument_arg, ticker_arg). YAML røres
      ikke — lar brukere kjøre mot DB uten å skrive YAML først.
    - Uten `--ticker`: slå opp YAML ved `--instrument`. Bruk
      `instrument.id` (kanonisk casing) som DB-tag og
      `stooq_ticker or ticker` som fetch-arg.
    """
    if ticker_arg is not None:
        return instrument_arg, ticker_arg

    cfg = find_instrument(instrument_arg, instruments_dir)
    meta = cfg.instrument
    resolved_ticker = meta.stooq_ticker or meta.ticker
    return meta.id, resolved_ticker


# ---------------------------------------------------------------------------
# cot-disaggregated
# ---------------------------------------------------------------------------


@backfill.command("cot-disaggregated")
@click.option(
    "--instrument",
    default=None,
    help=(
        "Bedrock-instrumentnavn. Hvis --contract ikke er gitt, slås `cot_contract` opp fra YAML."
    ),
)
@click.option(
    "--contract",
    default=None,
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
@_instruments_dir_option
@click.option(
    "--dry-run",
    is_flag=True,
    help="Vis URL og SoQL-parametre. Ingen HTTP-kall, ingen DB-skriving.",
)
def cot_disaggregated_cmd(
    instrument: str | None,
    contract: str | None,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill CFTC disaggregated COT-rapporter til SQLite.

    Eksempel:

        bedrock backfill cot-disaggregated --contract "GOLD - ..." --from 2010-01-01
        bedrock backfill cot-disaggregated --instrument Gold --from 2010-01-01
    """
    resolved_contract = _resolve_cot_contract(instrument, contract, instruments_dir)
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_socrata_query(resolved_contract, _from, _to)
        click.echo(f"DRY-RUN  URL: {CFTC_DISAGGREGATED_URL}")
        click.echo(f"DRY-RUN  $where: {params['$where']}")
        click.echo(f"DRY-RUN  $order: {params['$order']}")
        click.echo(f"DRY-RUN  $limit: {params['$limit']}")
        click.echo(f"DRY-RUN  Would write to: {db_path}")
        return

    click.echo(f"Fetching COT disaggregated for {resolved_contract!r} from {_from} to {_to}...")
    df = fetch_cot_disaggregated(resolved_contract, _from, _to)
    click.echo(f"Fetched {len(df)} report(s).")

    if df.empty:
        click.echo("No rows to write.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_cot_disaggregated(df)
    click.echo(f"Wrote {written} report(s) to {db_path}.")


# ---------------------------------------------------------------------------
# cot-legacy
# ---------------------------------------------------------------------------


@backfill.command("cot-legacy")
@click.option(
    "--instrument",
    default=None,
    help=(
        "Bedrock-instrumentnavn. Hvis --contract ikke er gitt, slås `cot_contract` opp fra YAML."
    ),
)
@click.option(
    "--contract",
    default=None,
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
@_instruments_dir_option
@click.option(
    "--dry-run",
    is_flag=True,
    help="Vis URL og SoQL-parametre. Ingen HTTP-kall, ingen DB-skriving.",
)
def cot_legacy_cmd(
    instrument: str | None,
    contract: str | None,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill CFTC legacy COT-rapporter til SQLite.

    Brukes for kontrakter uten disaggregated-rapport, og for historikk
    før 2010.

    Eksempel:

        bedrock backfill cot-legacy --contract "GOLD - ..." --from 2006-01-01
        bedrock backfill cot-legacy --instrument Gold --from 2006-01-01
    """
    resolved_contract = _resolve_cot_contract(instrument, contract, instruments_dir)
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_socrata_query(resolved_contract, _from, _to)
        click.echo(f"DRY-RUN  URL: {CFTC_LEGACY_URL}")
        click.echo(f"DRY-RUN  $where: {params['$where']}")
        click.echo(f"DRY-RUN  $order: {params['$order']}")
        click.echo(f"DRY-RUN  $limit: {params['$limit']}")
        click.echo(f"DRY-RUN  Would write to: {db_path}")
        return

    click.echo(f"Fetching COT legacy for {resolved_contract!r} from {_from} to {_to}...")
    df = fetch_cot_legacy(resolved_contract, _from, _to)
    click.echo(f"Fetched {len(df)} report(s).")

    if df.empty:
        click.echo("No rows to write.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_cot_legacy(df)
    click.echo(f"Wrote {written} report(s) to {db_path}.")


def _resolve_cot_contract(
    instrument_arg: str | None,
    contract_arg: str | None,
    instruments_dir: Path,
) -> str:
    """Returner kontrakt-navn etter --instrument + YAML-oppslag.

    Regler:

    - Eksplisitt `--contract` vinner (uavhengig av `--instrument`).
    - Uten `--contract`, krever `--instrument` med `cot_contract` satt.
    - Begge mangler → `click.UsageError`.
    """
    if contract_arg is not None:
        return contract_arg
    if instrument_arg is None:
        raise click.UsageError("Enten --contract eller --instrument må gis.")
    cfg = find_instrument(instrument_arg, instruments_dir)
    if cfg.instrument.cot_contract is None:
        raise click.UsageError(
            f"Instrument {instrument_arg!r} har ikke `cot_contract` i YAML. "
            f"Legg til feltet, eller oppgi --contract eksplisitt."
        )
    return cfg.instrument.cot_contract


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------


@backfill.command("weather")
@click.option(
    "--instrument",
    default=None,
    help=(
        "Bedrock-instrumentnavn. Hvis --region/--lat/--lon ikke er gitt, "
        "slås weather-metadata opp fra YAML."
    ),
)
@click.option(
    "--region",
    default=None,
    help="Region-tag som lagres i DB (f.eks. us_cornbelt, brazil_mato_grosso).",
)
@click.option(
    "--lat",
    "latitude",
    default=None,
    type=float,
    help="Breddegrad (decimal degrees).",
)
@click.option(
    "--lon",
    "longitude",
    default=None,
    type=float,
    help="Lengdegrad (decimal degrees).",
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
@_instruments_dir_option
@click.option(
    "--dry-run",
    is_flag=True,
    help="Vis URL og parametre. Ingen HTTP-kall, ingen DB-skriving.",
)
def weather_cmd(
    instrument: str | None,
    region: str | None,
    latitude: float | None,
    longitude: float | None,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill daglige vær-observasjoner fra Open-Meteo Archive til SQLite.

    Eksempel:

        bedrock backfill weather --region us_cornbelt --lat 40.75 --lon -96.75 --from 2016-01-01
        bedrock backfill weather --instrument Corn --from 2016-01-01

    `gdd` lagres som NULL — beregnes senere i driver med crop-spesifikk
    base-temperatur.
    """
    resolved_region, resolved_lat, resolved_lon = _resolve_weather(
        instrument, region, latitude, longitude, instruments_dir
    )
    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        params = build_open_meteo_params(resolved_lat, resolved_lon, _from, _to)
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        click.echo(f"DRY-RUN  URL: {OPEN_METEO_ARCHIVE_URL}?{param_str}")
        click.echo(f"DRY-RUN  Would write to: {db_path} (region={resolved_region})")
        return

    click.echo(
        f"Fetching weather for region={resolved_region!r} lat={resolved_lat} "
        f"lon={resolved_lon} from {_from} to {_to}..."
    )
    df = fetch_weather(resolved_region, resolved_lat, resolved_lon, _from, _to)
    click.echo(f"Fetched {len(df)} daily observation(s).")

    if df.empty:
        click.echo("No rows to write.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    written = store.append_weather(df)
    click.echo(f"Wrote {written} observation(s) to {db_path}.")


def _resolve_weather(
    instrument_arg: str | None,
    region_arg: str | None,
    lat_arg: float | None,
    lon_arg: float | None,
    instruments_dir: Path,
) -> tuple[str, float, float]:
    """Returner (region, lat, lon) etter --instrument + YAML-oppslag.

    Hvis alle tre eksplisitte args er satt → bruk dem. Ellers krev
    `--instrument` og bruk YAML. Delvise kombinasjoner gir tydelig feil.
    """
    explicit = [region_arg, lat_arg, lon_arg]
    explicit_set = sum(1 for x in explicit if x is not None)

    if explicit_set == 3:
        assert region_arg is not None
        assert lat_arg is not None
        assert lon_arg is not None
        return region_arg, lat_arg, lon_arg

    if explicit_set > 0 and instrument_arg is None:
        raise click.UsageError(
            "--region, --lat og --lon må oppgis sammen (eller bruk --instrument)."
        )

    if instrument_arg is None:
        raise click.UsageError("Oppgi enten alle av --region/--lat/--lon eller --instrument.")

    cfg = find_instrument(instrument_arg, instruments_dir)
    meta = cfg.instrument
    if meta.weather_region is None or meta.weather_lat is None or meta.weather_lon is None:
        raise click.UsageError(
            f"Instrument {instrument_arg!r} har ikke komplett weather-metadata "
            f"i YAML (region/lat/lon). Legg til felter, eller oppgi "
            f"--region/--lat/--lon eksplisitt."
        )
    # Eksplisitte args overstyrer per-felt når både instrument og delvis
    # eksplisitt arg er gitt.
    return (
        region_arg if region_arg is not None else meta.weather_region,
        lat_arg if lat_arg is not None else meta.weather_lat,
        lon_arg if lon_arg is not None else meta.weather_lon,
    )


# ---------------------------------------------------------------------------
# fundamentals (FRED)
# ---------------------------------------------------------------------------


@backfill.command("fundamentals")
@click.option(
    "--instrument",
    default=None,
    help=(
        "Bedrock-instrumentnavn. Uten --series-id: iterer over alle "
        "`fred_series_ids` i YAML med per-serie progress + retry-oppsummering."
    ),
)
@click.option(
    "--series-id",
    default=None,
    help=(
        "FRED-serie-ID (f.eks. DGS10, DXY, UNRATE). Overstyrer til én "
        "enkelt serie — brukbart for retry eller testing."
    ),
)
@click.option(
    "--api-key",
    default=None,
    help=(
        f"FRED API-nøkkel. Hvis utelatt, leses fra env-var {_FRED_API_KEY_ENV} "
        f"eller ~/.bedrock/secrets.env."
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
@_instruments_dir_option
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Vis URL og parametre (API-nøkkel maskes). Ingen HTTP-kall, "
        "ingen DB-skriving. Fungerer uten å ha FRED-nøkkel satt."
    ),
)
def fundamentals_cmd(
    instrument: str | None,
    series_id: str | None,
    api_key: str | None,
    from_date: datetime,
    to_date: datetime | None,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill FRED-serier til SQLite.

    Eksempel:

        bedrock backfill fundamentals --series-id DGS10 --from 2016-01-01
        bedrock backfill fundamentals --instrument Gold --from 2016-01-01
        bedrock backfill fundamentals --instrument Gold --series-id DGS10 --from 2016-01-01

    Med kun `--instrument` itereres alle serier instrumentet har i YAML;
    én feil aborterer ikke resten, og på slutten printes retry-kommandoer
    for de feilede.

    API-nøkkel: CLI-arg > env-var FRED_API_KEY > ~/.bedrock/secrets.env.
    """
    series_ids = _resolve_fred_series(instrument, series_id, instruments_dir)

    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    # Resolve api-key én gang
    if api_key is None:
        api_key = get_secret(_FRED_API_KEY_ENV)

    if dry_run:
        _fundamentals_dry_run(series_ids, api_key, _from, _to, db_path)
        return

    if api_key is None:
        raise click.UsageError(
            f"FRED API-nøkkel ikke funnet. Sett env-var {_FRED_API_KEY_ENV}, "
            f"legg til i ~/.bedrock/secrets.env, eller bruk --api-key. "
            f"Nøkkel hentes gratis fra https://fred.stlouisfed.org/docs/api/api_key.html"
        )

    # DataStore opprettes lat — unngår å lage tom DB-fil hvis alle
    # serier returnerer empty.
    _store_ref: list[DataStore] = []

    def _get_store() -> DataStore:
        if not _store_ref:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _store_ref.append(DataStore(db_path))
        return _store_ref[0]

    def _fetch_one(sid: str) -> int:
        df = fetch_fred_series(sid, api_key, _from, _to)
        if df.empty:
            return 0
        return _get_store().append_fundamentals(df)

    def _retry_cmd(sid: str) -> str:
        return (
            f"bedrock backfill fundamentals --series-id {sid} "
            f"--from {_from} --to {_to} --db {db_path}"
        )

    run_with_summary(
        items=series_ids,
        process_fn=_fetch_one,
        retry_command=_retry_cmd,
        label="series-id",
    )


def _resolve_fred_series(
    instrument_arg: str | None,
    series_id_arg: str | None,
    instruments_dir: Path,
) -> list[str]:
    """Returner liste av serie-IDer å hente.

    - `--series-id` satt: én-liste, uavhengig av `--instrument`.
    - Kun `--instrument`: iterer over `fred_series_ids` fra YAML.
    - Ingen av delene: feil.
    """
    if series_id_arg is not None:
        return [series_id_arg]
    if instrument_arg is None:
        raise click.UsageError("Enten --series-id eller --instrument må gis.")
    cfg = find_instrument(instrument_arg, instruments_dir)
    ids = list(cfg.instrument.fred_series_ids)
    if not ids:
        raise click.UsageError(
            f"Instrument {instrument_arg!r} har ingen `fred_series_ids` i YAML. "
            f"Legg til feltet, eller oppgi --series-id."
        )
    return ids


def _fundamentals_dry_run(
    series_ids: list[str],
    api_key: str | None,
    _from: date,
    _to: date,
    db_path: Path,
) -> None:
    """Print dry-run-output for hver serie uten HTTP/DB."""
    for sid in series_ids:
        params = build_fred_params(sid, _MASKED_API_KEY, _from, _to)
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        click.echo(f"DRY-RUN  URL: {FRED_OBSERVATIONS_URL}?{param_str}")
        click.echo(f"DRY-RUN  Would write to: {db_path} (series_id={sid})")
    key_state = "resolved" if api_key else "MISSING (live run vil feile)"
    click.echo(f"DRY-RUN  API-key: {key_state}")


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Eksponert slik at `python -m bedrock.cli.backfill prices ...` også funker."""
    backfill(standalone_mode=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
