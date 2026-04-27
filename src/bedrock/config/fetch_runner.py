"""Fetch-runner: dispatcher fra FetcherSpec til faktisk fetch-kjøring.

Session 29: hver kjent fetcher-navn mapper til en run-funksjon som
itererer over instrumenter i `config/instruments/`, filtrerer på
relevant metadata (stooq_ticker, cot_contract, weather_region,
fred_series_ids), henter data, skriver til DataStore.

Resiliens: per-item feil aborterer ikke hele kjøringen. Mønsteret er
identisk med `bedrock.cli._iteration.run_with_summary` fra session 22.

Struktur:

    @register_runner("prices")
    def run_prices(spec, store, from_date, to_date, instruments): ...

    run_fetcher_by_name(name, store, spec, *, from_date, to_date,
                       instruments_dir, defaults_dir) -> FetchRunResult
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bedrock.config.fetch import FetcherSpec
from bedrock.config.instruments import InstrumentConfig, load_all_instruments
from bedrock.config.secrets import get_secret

_log = logging.getLogger(__name__)

_FRED_API_KEY_ENV = "FRED_API_KEY"
_NASS_API_KEY_ENV = "BEDROCK_NASS_API_KEY"


# ---------------------------------------------------------------------------
# Result-modeller
# ---------------------------------------------------------------------------


@dataclass
class ItemOutcome:
    """Resultat for ett fetched-item (én instrument, én serie, etc.)."""

    item_id: str
    ok: bool
    rows_written: int = 0
    error: str | None = None


@dataclass
class FetchRunResult:
    """Samlet resultat for én fetcher-kjøring."""

    fetcher_name: str
    items: list[ItemOutcome] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(i.rows_written for i in self.items if i.ok)

    @property
    def ok_count(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def fail_count(self) -> int:
        return sum(1 for i in self.items if not i.ok)


# ---------------------------------------------------------------------------
# Runner-registry
# ---------------------------------------------------------------------------


RunnerFn = Callable[..., FetchRunResult]
_RUNNERS: dict[str, RunnerFn] = {}


def register_runner(name: str) -> Callable[[RunnerFn], RunnerFn]:
    def decorator(fn: RunnerFn) -> RunnerFn:
        if name in _RUNNERS:
            raise ValueError(f"Runner {name!r} already registered")
        _RUNNERS[name] = fn
        return fn

    return decorator


def get_runner(name: str) -> RunnerFn:
    if name not in _RUNNERS:
        known = ", ".join(sorted(_RUNNERS)) or "<none>"
        raise KeyError(f"No runner for fetcher {name!r}. Known: {known}")
    return _RUNNERS[name]


def all_runner_names() -> list[str]:
    return sorted(_RUNNERS)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def run_fetcher_by_name(
    name: str,
    store: Any,
    spec: FetcherSpec,
    *,
    from_date: date,
    to_date: date | None = None,
    instruments_dir: Path | str,
    defaults_dir: Path | str | None = None,
    instrument_filter: str | None = None,
) -> FetchRunResult:
    """Kjør fetcher-navn mot store, iterer instrumenter som trenger dataen.

    `instrument_filter` begrenser til én instrument (case-insensitive ID-
    match) — brukes for target-retry eller manuell testing.
    """
    runner = get_runner(name)
    configs = load_all_instruments(instruments_dir, defaults_dir=defaults_dir)

    if instrument_filter is not None:
        filtered_key = _find_instrument_key(configs, instrument_filter)
        configs = {filtered_key: configs[filtered_key]}

    effective_to = to_date or datetime.now(timezone.utc).date()

    return runner(
        spec=spec,
        store=store,
        from_date=from_date,
        to_date=effective_to,
        instruments=configs.values(),
    )


def _find_instrument_key(configs: dict[str, InstrumentConfig], target: str) -> str:
    if target in configs:
        return target
    lower = target.lower()
    for key in configs:
        if key.lower() == lower:
            return key
    raise KeyError(f"Instrument {target!r} not found. Available: {sorted(configs)}")


# ---------------------------------------------------------------------------
# Runner-implementasjoner
# ---------------------------------------------------------------------------


def _safe_run(
    items: Iterable[tuple[str, Callable[[], int]]],
    result: FetchRunResult,
) -> None:
    """Kjør hver item-closure, fang exceptions per item."""
    for item_id, fn in items:
        try:
            written = fn()
            result.items.append(ItemOutcome(item_id=item_id, ok=True, rows_written=written))
        except Exception as exc:
            result.items.append(ItemOutcome(item_id=item_id, ok=False, error=str(exc)))


@register_runner("prices")
def run_prices(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    from bedrock.fetch.prices import fetch_prices

    result = FetchRunResult(fetcher_name="prices")

    def _items():
        for cfg in instruments:
            meta = cfg.instrument
            ticker = meta.yahoo_ticker or meta.ticker
            if not ticker:
                continue
            item_id = meta.id

            def _do(ticker=ticker, inst_id=meta.id):
                df = fetch_prices(ticker, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_prices(inst_id, "D1", df)

            yield item_id, _do

    _safe_run(_items(), result)
    return result


@register_runner("cot_disaggregated")
def run_cot_disaggregated(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    from bedrock.fetch.cot_cftc import fetch_cot_disaggregated

    result = FetchRunResult(fetcher_name="cot_disaggregated")

    def _items():
        for cfg in instruments:
            contract = cfg.instrument.cot_contract
            if not contract or cfg.instrument.cot_report != "disaggregated":
                continue

            def _do(contract=contract):
                df = fetch_cot_disaggregated(contract, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_cot_disaggregated(df)

            yield cfg.instrument.id, _do

    _safe_run(_items(), result)
    return result


@register_runner("cot_legacy")
def run_cot_legacy(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    from bedrock.fetch.cot_cftc import fetch_cot_legacy

    result = FetchRunResult(fetcher_name="cot_legacy")

    def _items():
        for cfg in instruments:
            contract = cfg.instrument.cot_contract
            if not contract or cfg.instrument.cot_report != "legacy":
                continue

            def _do(contract=contract):
                df = fetch_cot_legacy(contract, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_cot_legacy(df)

            yield cfg.instrument.id, _do

    _safe_run(_items(), result)
    return result


@register_runner("weather")
def run_weather(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    from bedrock.fetch.weather import fetch_weather

    result = FetchRunResult(fetcher_name="weather")

    def _items():
        for cfg in instruments:
            meta = cfg.instrument
            if not meta.weather_region or meta.weather_lat is None or meta.weather_lon is None:
                continue

            def _do(
                region=meta.weather_region,
                lat=meta.weather_lat,
                lon=meta.weather_lon,
            ):
                df = fetch_weather(region, lat, lon, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_weather(df)

            # item_id er region — ikke instrument (samme region kan
            # brukes av flere agri)
            yield meta.weather_region, _do

    _safe_run(_items(), result)
    return result


@register_runner("fundamentals")
def run_fundamentals(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    from bedrock.fetch.fred import fetch_fred_series

    result = FetchRunResult(fetcher_name="fundamentals")

    api_key = get_secret(_FRED_API_KEY_ENV)
    if api_key is None:
        # Rapporter som feil per serie — mer informativt enn å raise
        for cfg in instruments:
            for series_id in cfg.instrument.fred_series_ids:
                result.items.append(
                    ItemOutcome(
                        item_id=f"{cfg.instrument.id}:{series_id}",
                        ok=False,
                        error=("Mangler FRED_API_KEY — sett env-var eller ~/.bedrock/secrets.env"),
                    )
                )
        return result

    def _items():
        seen: set[str] = set()
        for cfg in instruments:
            for series_id in cfg.instrument.fred_series_ids:
                if series_id in seen:
                    continue  # unngå dobbelt-henting når flere
                    # instrumenter deler samme serie
                seen.add(series_id)

                def _do(sid=series_id):
                    df = fetch_fred_series(sid, api_key, from_date, to_date)
                    if df.empty:
                        return 0
                    return store.append_fundamentals(df)

                yield series_id, _do

    _safe_run(_items(), result)
    return result


@register_runner("enso")
def run_enso(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """NOAA ONI (ENSO-indeks). Ikke-instrument-spesifikk; én global serie.

    Skriver til `fundamentals`-tabellen som ``series_id="NOAA_ONI"`` per
    ADR-005. Kjørt månedlig (12. UTC) etter NOAAs ~10. publisering.
    """
    from bedrock.fetch.enso import fetch_noaa_oni

    result = FetchRunResult(fetcher_name="enso")

    def _do() -> int:
        df = fetch_noaa_oni()
        if df.empty:
            return 0
        return store.append_fundamentals(df)

    _safe_run([("NOAA_ONI", _do)], result)
    return result


@register_runner("wasde")
def run_wasde(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """USDA WASDE-rapport. Månedlig (~10.); fetcher har egen XML→CSV-fallback."""
    from bedrock.fetch.wasde import fetch_wasde

    result = FetchRunResult(fetcher_name="wasde")

    def _do() -> int:
        df = fetch_wasde()
        if df.empty:
            return 0
        return store.append_wasde(df)

    _safe_run([("WASDE", _do)], result)
    return result


@register_runner("crop_progress")
def run_crop_progress(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """USDA NASS Crop Progress. Ukentlig (mandager) under vekstsesong.

    Krever ``BEDROCK_NASS_API_KEY`` (env eller secrets.env). Mangler
    nøkkelen, faller fetcheren tilbake til manuell CSV — vi rapporterer
    likevel item som ok hvis dataframe er ikke-tom.
    """
    from bedrock.fetch.nass import fetch_crop_progress

    result = FetchRunResult(fetcher_name="crop_progress")
    api_key = get_secret(_NASS_API_KEY_ENV)

    def _do() -> int:
        df = fetch_crop_progress(api_key=api_key)
        if df.empty:
            return 0
        return store.append_crop_progress(df)

    _safe_run([("crop_progress", _do)], result)
    return result


@register_runner("bdi")
def run_bdi(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Baltic Dry Index via BDRY ETF (Yahoo). Daglig Mon-Fri etter US close."""
    from bedrock.fetch.manual_events import fetch_bdi_via_bdry

    result = FetchRunResult(fetcher_name="bdi")

    def _do() -> int:
        df = fetch_bdi_via_bdry(
            start_date=from_date.isoformat(),
            end_date=to_date.isoformat(),
        )
        if df.empty:
            return 0
        return store.append_bdi(df)

    _safe_run([("BDRY", _do)], result)
    return result


def _previous_tuesday(now: datetime | None = None) -> date:
    """ICE-COT rapporteres for tirsdag-snapshot, publisert fredag.

    Returnerer siste tirsdag på eller før ``now`` (UTC). Brukes av
    ``run_cot_ice`` til smart-skip: hvis DB allerede har rad for denne
    tirsdagen, hopper vi over HTTP-kallet (sparer trafikk mot gratis-
    kilden).
    """
    n = now or datetime.now(timezone.utc)
    today = n.date()
    # Mandag=0 ... Søndag=6. Vi vil til siste tirsdag (=1) på eller før i dag.
    delta = (today.weekday() - 1) % 7
    return today - timedelta(days=delta)


@register_runner("cot_ice")
def run_cot_ice(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """ICE Futures Europe COT (sub-fase 12.5+ session 106).

    Henter ukentlig CSV (én fil per år) og skriver til ``cot_ice``-
    tabellen. Ikke instrument-spesifikk; én global fetch dekker alle
    ICE-listede markeder (Brent, Gasoil, TTF Gas).

    Smart-skip: ICE rapporterer for forrige tirsdag-snapshot (publisert
    fredag). Hvis DB allerede har rad med ``report_date >=
    previous_tuesday(now)``, hopper vi over HTTP-kallet — gratis-API-
    etiquette per memory feedback_free_api_no_parallel.
    """
    from bedrock.data.schemas import TABLE_COT_ICE
    from bedrock.fetch.cot_ice import fetch_cot_ice

    result = FetchRunResult(fetcher_name="cot_ice")

    # Smart-skip-sjekk
    target_tuesday = _previous_tuesday()
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_COT_ICE, "report_date")
    except Exception as exc:
        _log.warning("cot_ice.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= target_tuesday:
                _log.info(
                    "cot_ice.up_to_date latest=%s target=%s — skipping HTTP",
                    latest_date,
                    target_tuesday,
                )
                result.items.append(ItemOutcome(item_id="ice_cot", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("cot_ice.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_cot_ice()
        if df.empty:
            return 0
        return store.append_cot_ice(df)

    _safe_run([("ice_cot", _do)], result)
    return result


def _previous_wednesday(now: datetime | None = None) -> date:
    """EIA weekly petroleum-rapporter publiseres typisk onsdag 10:30 ET
    (~16:30 Oslo) for forrige fredag-snapshot. Naturgass-storage onsdag/
    torsdag avhengig av kalender.

    Returnerer siste onsdag på eller før ``now`` (UTC). Brukes av
    ``run_eia_inventories`` til smart-skip.
    """
    n = now or datetime.now(timezone.utc)
    today = n.date()
    # Mandag=0 ... Søndag=6. Onsdag=2.
    delta = (today.weekday() - 2) % 7
    return today - timedelta(days=delta)


@register_runner("eia_inventories")
def run_eia_inventories(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """EIA Open Data weekly inventories (sub-fase 12.5+ session 107).

    Henter US Crude Oil Stocks, Total Gasoline Stocks, og Lower 48 Natural
    Gas Storage. Ikke instrument-spesifikk; én global fetch dekker alle
    energy-relaterte instrumenter (CrudeOil, Brent, NaturalGas).

    Smart-skip: EIA petroleum publiserer typisk onsdag, naturgass onsdag/
    torsdag. Hvis DB allerede har rader med ``date >= forrige onsdag``,
    hopper runneren over HTTP-kallet.
    """
    from bedrock.data.schemas import TABLE_EIA_INVENTORY
    from bedrock.fetch.eia_inventories import fetch_eia

    result = FetchRunResult(fetcher_name="eia_inventories")

    # Smart-skip
    target_wednesday = _previous_wednesday()
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_EIA_INVENTORY, "date")
    except Exception as exc:
        _log.warning("eia.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= target_wednesday:
                _log.info(
                    "eia.up_to_date latest=%s target=%s — skipping HTTP",
                    latest_date,
                    target_wednesday,
                )
                result.items.append(ItemOutcome(item_id="eia_inventories", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("eia.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_eia()
        if df.empty:
            return 0
        return store.append_eia_inventory(df)

    _safe_run([("eia_inventories", _do)], result)
    return result


def _previous_business_day(now: datetime | None = None) -> date:
    """COMEX rapporterer T-1: man-fre publiseres data for forrige børsdag.

    Returnerer siste mandag-fredag på eller før gårsdagen (UTC). Brukt av
    ``run_comex`` til smart-skip.
    """
    n = now or datetime.now(timezone.utc)
    today = n.date()
    target = today - timedelta(days=1)
    while target.weekday() >= 5:
        target = target - timedelta(days=1)
    return target


@register_runner("comex")
def run_comex(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """COMEX warehouse-inventories (sub-fase 12.5+ session 108).

    Henter daglige stocks for gull/sølv/kobber fra metalcharts.org.
    Ikke instrument-spesifikk; én global fetch dekker alle metals-
    instrumenter.

    Smart-skip: COMEX rapporterer T-1 daglig (man-fre). Hvis DB
    allerede har rader med ``date >= forrige børsdag``, hopper
    runneren over HTTP-kallet.
    """
    from bedrock.data.schemas import TABLE_COMEX_INVENTORY
    from bedrock.fetch.comex import fetch_comex

    result = FetchRunResult(fetcher_name="comex")

    target = _previous_business_day()
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_COMEX_INVENTORY, "date")
    except Exception as exc:
        _log.warning("comex.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= target:
                _log.info(
                    "comex.up_to_date latest=%s target=%s — skipping HTTP",
                    latest_date,
                    target,
                )
                result.items.append(ItemOutcome(item_id="comex", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("comex.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_comex()
        if df.empty:
            return 0
        return store.append_comex_inventory(df)

    _safe_run([("comex", _do)], result)
    return result


@register_runner("seismic")
def run_seismic(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """USGS seismic events M≥4.5 siste 7 dager (sub-fase 12.5+ session 109).

    Henter globale events og lagrer alle (med region=None for events
    utenfor mining-regions). Drivere filtrerer per metall.

    Idempotent på event_id — daglig kjøring oppdaterer event-properties
    hvis USGS reviderer (vanlig de første 24 timene etter et skjelv).
    Ingen smart-skip nødvendig: USGS-feeden er liten (~100 events/uke)
    og refresh-cost er trivialt.
    """
    from bedrock.fetch.seismic import fetch_seismic

    result = FetchRunResult(fetcher_name="seismic")

    def _do() -> int:
        df = fetch_seismic()
        if df.empty:
            return 0
        return store.append_seismic_events(df)

    _safe_run([("seismic", _do)], result)
    return result


@register_runner("calendar_ff")
def run_calendar_ff(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Forex Factory økonomisk kalender (sub-fase 12.5+ session 105).

    Henter denne uke's high/medium-impact events og skriver til
    ``econ_events``-tabellen. Ikke instrument-spesifikk; én global
    fetch per kjøring. Cadence (ADR-008): ``15 6,18 * * *`` Oslo —
    daglig 2× for å fange forecast/previous-oppdateringer 1-2 timer
    før release.
    """
    from bedrock.fetch.calendar_ff import fetch_calendar_events

    result = FetchRunResult(fetcher_name="calendar_ff")

    def _do() -> int:
        df = fetch_calendar_events()
        if df.empty:
            return 0
        return store.append_econ_events(df)

    _safe_run([("forex_factory", _do)], result)
    return result


# ---------------------------------------------------------------------------
# Convenience: default from_date basert på stale_hours
# ---------------------------------------------------------------------------


def default_from_date(
    spec: FetcherSpec,
    now: datetime | None = None,
    buffer_multiplier: float = 2.0,
) -> date:
    """Foreslå start-dato som dekker `stale_hours × buffer_multiplier`.

    For daglige fetchere (stale_hours=24-30) gir dette 2-3 dager bak,
    nok til å fange gap ved forsinket kjøring uten å hente unødvendig
    langt bak.
    """
    resolved_now = now or datetime.now(timezone.utc)
    hours = spec.stale_hours * buffer_multiplier
    return (resolved_now - timedelta(hours=hours)).date()


__all__ = [
    "FetchRunResult",
    "ItemOutcome",
    "all_runner_names",
    "default_from_date",
    "get_runner",
    "register_runner",
    "run_fetcher_by_name",
]
