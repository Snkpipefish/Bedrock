# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

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
import pandas as pd

from bedrock.cli._instrument_lookup import DEFAULT_INSTRUMENTS_DIR, find_instrument
from bedrock.cli._iteration import run_with_summary
from bedrock.config.secrets import get_secret
from bedrock.data.schemas import WEATHER_MONTHLY_COLS
from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import (
    CFTC_DISAGGREGATED_URL,
    CFTC_LEGACY_URL,
    build_socrata_query,
    fetch_cot_disaggregated,
    fetch_cot_legacy,
)
from bedrock.fetch.enso import NOAA_ONI_URL, fetch_noaa_oni
from bedrock.fetch.fred import (
    FRED_OBSERVATIONS_URL,
    build_fred_params,
    fetch_fred_series,
)
from bedrock.fetch.weather import (
    OPEN_METEO_ARCHIVE_URL,
    build_open_meteo_params,
    fetch_weather,
)
from bedrock.fetch.yahoo import build_yahoo_url, fetch_yahoo_prices

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
        "Yahoo Finance-ticker (f.eks. GC=F). Hvis utelatt, brukes instrumentets "
        "`yahoo_ticker` (eller `ticker`) fra YAML."
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
    "--interval",
    type=click.Choice(["1d", "1wk", "1mo"], case_sensitive=False),
    default="1d",
    show_default=True,
    help="Yahoo-intervall.",
)
@click.option(
    "--tf",
    default="D1",
    show_default=True,
    help="Timeframe-tag lagret i DB (info, ikke fetch-param).",
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
    interval: str,
    tf: str,
    db_path: Path,
    instruments_dir: Path,
    dry_run: bool,
) -> None:
    """Backfill prisbarer fra Yahoo Finance til SQLite.

    Eksempel:

        bedrock backfill prices --instrument Gold --from 2010-01-01
        bedrock backfill prices --instrument Corn --from 2010-01-01 --interval 1wk

    `--dry-run` bygger og viser URL uten å gjøre HTTP-kall eller skrive til DB.

    Per session 69 (Fase 12): Yahoo er eneste pris-kilde. Stooq-fallback
    fjernet — krevde API-nøkkel etter april 2026 og ble blocker. Yahoo-
    port (session 58) er verifisert mot 15 års historikk fra
    cot-explorer.
    """
    if instrument is None:
        raise click.UsageError("--instrument er påkrevd.")

    resolved_instrument, resolved_ticker = _resolve_prices(instrument, ticker, instruments_dir)

    _from: date = from_date.date()
    _to: date = to_date.date() if to_date is not None else date.today()

    if dry_run:
        url = build_yahoo_url(resolved_ticker, _from, _to, interval=interval.lower())  # type: ignore[arg-type]
        click.echo(f"DRY-RUN  URL: {url}")
        click.echo(
            f"DRY-RUN  Would write to: {db_path} (instrument={resolved_instrument}, tf={tf})"
        )
        return

    click.echo(
        f"Fetching {resolved_instrument} ({resolved_ticker}) "
        f"from {_from} to {_to} via Yahoo interval={interval}..."
    )
    df = fetch_yahoo_prices(resolved_ticker, _from, _to, interval=interval.lower())  # type: ignore[arg-type]
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
    """Returner (DB-instrument-tag, ticker) etter --instrument + YAML-oppslag.

    Regler:

    - Eksplisitt `--ticker` vinner: (instrument_arg, ticker_arg). YAML røres
      ikke — lar brukere kjøre mot DB uten å skrive YAML først.
    - Uten `--ticker`: slå opp YAML, bruk `yahoo_ticker or ticker`.
    """
    if ticker_arg is not None:
        return instrument_arg, ticker_arg

    cfg = find_instrument(instrument_arg, instruments_dir)
    meta = cfg.instrument
    resolved_ticker = meta.yahoo_ticker or meta.ticker
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
# enso (Fase 10 ADR-005) — NOAA ONI til fundamentals-tabellen
# ---------------------------------------------------------------------------


@backfill.command("enso")
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
def enso_cmd(db_path: Path, dry_run: bool) -> None:
    """Backfill NOAA ONI ENSO-indeks til SQLite (`fundamentals`-tabellen).

    Per ADR-005 lagres ONI som `series_id="NOAA_ONI"` i den eksisterende
    `fundamentals`-tabellen — ikke i en egen tabell. Dette gjenbruker
    (key, date, value)-skjemaet og krever ingen ny DataStore-getter.

    Eksempel:

        bedrock backfill enso

    Endepunktet er åpent (ingen API-nøkkel). NOAA publiserer historikk
    fra 1950 og oppdaterer månedlig (~10. i måneden). Idempotent via
    INSERT OR REPLACE på (series_id, date).
    """
    from bedrock.fetch.enso import NOAA_ONI_SERIES_ID

    if dry_run:
        click.echo(f"DRY-RUN  URL: {NOAA_ONI_URL}")
        click.echo(f"DRY-RUN  Would write to: {db_path} (series_id={NOAA_ONI_SERIES_ID})")
        return

    df = fetch_noaa_oni()
    if df.empty:
        click.echo("noaa_oni: ingen rader returnert (uventet)")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    n = store.append_fundamentals(df)
    click.echo(
        f"noaa_oni: {n} rader skrevet  (range: {df['date'].iloc[0]} .. {df['date'].iloc[-1]})"
    )


# ---------------------------------------------------------------------------
# weather-monthly (Fase 10 ADR-005) — migrere ~/cot-explorer/agri_history/
# ---------------------------------------------------------------------------


_DEFAULT_AGRI_HISTORY_DIR = Path.home() / "cot-explorer" / "data" / "agri_history"
"""Default-kilde for migrering av månedlig vær-aggregat."""

_AGRI_HISTORY_FIELD_MAP: dict[str, str] = {
    "temp_mean": "temp_mean",
    "temp_max": "temp_max",
    "precip_mm": "precip_mm",
    "et0_mm": "et0_mm",
    "hot_days": "hot_days",
    "dry_days": "dry_days",
    "wet_days": "wet_days",
    "water_bal": "water_bal",
}
"""Mapping fra agri_history-JSON-felt til WeatherMonthlyRow-kolonne.

Det 9. JSON-feltet (`days`, antall dager i måneden) droppes per
session 58-beslutning — kan beregnes trivielt fra `month`-stringen
ved behov og er ikke i § 6.5.
"""


@backfill.command("weather-monthly")
@click.option(
    "--source-dir",
    default=_DEFAULT_AGRI_HISTORY_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Kilde-katalog med <region>.json-filer fra cot-explorer/data/agri_history/.",
)
@click.option(
    "--region",
    default=None,
    help="Filtrer til én region (matches mot filnavn uten .json). Default: alle.",
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
    help="Vis hvilke filer som ville blitt migrert. Ingen DB-skriving.",
)
def weather_monthly_cmd(
    source_dir: Path,
    region: str | None,
    db_path: Path,
    dry_run: bool,
) -> None:
    """Migrere pre-aggregert månedlig vær fra cot-explorer til Bedrock.

    Per ADR-005 B2: cot-explorer/data/agri_history/<region>.json har 14
    regioner med 184+ måneder ferdig pre-aggregert (temp_mean, hot_days,
    water_bal, etc.). Dette migreres til ny `weather_monthly`-tabell.
    9. felt `days` droppes (kan beregnes fra `month`).

    Eksempel:

        bedrock backfill weather-monthly
        bedrock backfill weather-monthly --region us_cornbelt

    Idempotent via INSERT OR REPLACE på (region, month).
    """
    if not source_dir.exists():
        raise click.UsageError(f"Source dir not found: {source_dir}")

    files = sorted(source_dir.glob("*.json"))
    if region is not None:
        files = [f for f in files if f.stem == region]
        if not files:
            raise click.UsageError(f"Region {region!r} not found in {source_dir}")

    if dry_run:
        for f in files:
            click.echo(f"DRY-RUN  Would migrate: {f.name}")
        click.echo(f"DRY-RUN  Total: {len(files)} regioner → {db_path}")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DataStore(db_path)
    total = 0
    for f in files:
        df = _load_agri_history_to_weather_monthly(f)
        if df.empty:
            click.echo(f"{f.stem}: 0 rader (skipped)")
            continue
        n = store.append_weather_monthly(df)
        total += n
        click.echo(
            f"{f.stem}: {n} rader skrevet  ({df['month'].iloc[0]} .. {df['month'].iloc[-1]})"
        )

    click.echo(f"weather-monthly: {total} rader totalt fra {len(files)} regioner")


def _load_agri_history_to_weather_monthly(path: Path) -> pd.DataFrame:
    """Les én agri_history JSON-fil og returner WeatherMonthlyRow-DataFrame.

    JSON-format:
        {"region_id": "us_cornbelt", "monthly": {"2011-01": {"temp_mean": ..., ...}}}

    Tom `monthly` → tom DataFrame med riktig kolonne-sett.
    """
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    region = raw.get("region_id") or path.stem
    monthly = raw.get("monthly") or {}

    cols = list(WEATHER_MONTHLY_COLS)
    if not monthly:
        return pd.DataFrame(columns=cols)

    rows: list[dict[str, object]] = []
    for month_key in sorted(monthly.keys()):
        obs = monthly[month_key] or {}
        row: dict[str, object] = {"region": region, "month": month_key}
        for json_field, schema_field in _AGRI_HISTORY_FIELD_MAP.items():
            row[schema_field] = obs.get(json_field)
        rows.append(row)

    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# outcomes (Fase 10 ADR-005) — beregne forward_return + max_drawdown
# ---------------------------------------------------------------------------


@backfill.command("outcomes")
@click.option(
    "--instrument",
    "instruments",
    multiple=True,
    required=True,
    help="Bedrock-instrument-ID. Kan gjentas: --instrument Gold --instrument Corn.",
)
@click.option(
    "--horizons",
    default="30,90",
    show_default=True,
    help="Komma-separert liste av forward-horisonter i dager.",
)
@click.option(
    "--tf",
    default="D1",
    show_default=True,
    help="Pris-timeframe å lese fra `prices`-tabellen.",
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
    help="Vis hva som ville blitt beregnet. Ingen DB-skriving.",
)
def outcomes_cmd(
    instruments: tuple[str, ...],
    horizons: str,
    tf: str,
    db_path: Path,
    dry_run: bool,
) -> None:
    """Beregne forward-return + max-drawdown for analog-matching.

    Per ADR-005 B3: for hver dato i `prices`-tabellen, beregn
    forward_return_pct (close_t+H / close_t - 1) * 100 og
    max_drawdown_pct (min(close_t..t+H) / close_t - 1) * 100 for hver
    horisont H i `--horizons`. Skrives til `analog_outcomes`-tabellen.

    Datoer som ikke har full forward-vindu (siste H dager før i dag)
    får ikke rad for den horisonten — caller (K-NN) trenger ikke
    håndtere "missing future".

    Eksempel:

        bedrock backfill outcomes --instrument Gold --instrument Corn
        bedrock backfill outcomes --instrument Gold --horizons 30,60,90,180

    Idempotent via INSERT OR REPLACE på (instrument, ref_date, horizon_days).
    Re-kjør etter at `prices` er oppdatert for å få nye outcomes.
    """
    horizon_list = _parse_horizons(horizons)

    if dry_run:
        for inst in instruments:
            for h in horizon_list:
                click.echo(
                    f"DRY-RUN  Would compute outcomes: instrument={inst} "
                    f"horizon_days={h} tf={tf} db={db_path}"
                )
        return

    if not db_path.exists():
        raise click.UsageError(f"DB not found: {db_path}. Kjør `bedrock backfill prices` først.")

    store = DataStore(db_path)
    grand_total = 0
    for inst in instruments:
        try:
            prices = store.get_prices(inst, tf=tf)
        except KeyError:
            click.echo(f"{inst}: ingen prises-data (skipped)")
            continue
        if prices.empty:
            click.echo(f"{inst}: tom pris-serie (skipped)")
            continue
        for h in horizon_list:
            df = _compute_outcomes(inst, prices, h)
            if df.empty:
                click.echo(f"{inst} h={h}d: 0 outcomes (kort historikk)")
                continue
            n = store.append_outcomes(df)
            grand_total += n
            click.echo(
                f"{inst} h={h}d: {n} outcomes skrevet  "
                f"({df['ref_date'].iloc[0]} .. {df['ref_date'].iloc[-1]})"
            )

    click.echo(f"outcomes: {grand_total} rader totalt")


def _parse_horizons(raw: str) -> list[int]:
    """Parse '30,60,90' → [30, 60, 90]. Avviser tomme/0/negative."""
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = int(part)
        except ValueError as exc:
            raise click.UsageError(f"Ugyldig horizon: {part!r}") from exc
        if v <= 0:
            raise click.UsageError(f"Horizon må være positiv, fikk: {v}")
        out.append(v)
    if not out:
        raise click.UsageError("Minst én horisont må gis i --horizons.")
    return out


def _compute_outcomes(
    instrument: str,
    prices: pd.Series,
    horizon_days: int,
) -> pd.DataFrame:
    """Beregn forward_return + max_drawdown for hver dato i pris-serien.

    `prices` er pd.Series indeksert på datetime (close-priser). Vi bruker
    enkel posisjons-basert offset (rolling window) — slik at horizon_days
    er antall bars, ikke kalender-dager. For D1-data er forskjellen
    helger og helligdager (~5/7 av kalender-dager). Dette matcher
    intuitiv "30 trading-days forward".

    Returnerer DataFrame matching ANALOG_OUTCOMES_COLS. Datoer uten
    full forward-vindu (siste horizon_days bars) er ekskludert.
    """
    if len(prices) < horizon_days + 1:
        return pd.DataFrame(
            columns=[
                "instrument",
                "ref_date",
                "horizon_days",
                "forward_return_pct",
                "max_drawdown_pct",
            ]
        )

    # Sortér defensiv (DataStore.get_prices returnerer ASC, men sikrer)
    series = prices.sort_index()
    n = len(series)

    rows: list[dict[str, object]] = []
    values = series.values
    index = series.index

    for i in range(n - horizon_days):
        close_t = float(values[i])
        if close_t <= 0.0:
            continue
        window_end = i + horizon_days + 1  # inkluder t+H
        window = values[i:window_end]
        close_t_plus_h = float(window[-1])
        min_in_window = float(window.min())

        forward_return_pct = (close_t_plus_h / close_t - 1.0) * 100.0
        max_drawdown_pct = (min_in_window / close_t - 1.0) * 100.0

        rows.append(
            {
                "instrument": instrument,
                "ref_date": index[i],
                "horizon_days": horizon_days,
                "forward_return_pct": forward_return_pct,
                "max_drawdown_pct": max_drawdown_pct,
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Eksponert slik at `python -m bedrock.cli.backfill prices ...` også funker."""
    backfill(standalone_mode=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
