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

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bedrock.config.fetch import FetcherSpec
from bedrock.config.instruments import InstrumentConfig, load_all_instruments
from bedrock.config.secrets import get_secret

_FRED_API_KEY_ENV = "FRED_API_KEY"


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
            ticker = meta.stooq_ticker or meta.ticker
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
