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


# Hardkodet liste av TFF-kontrakter som holdes ferske. Bruker
# eksisterende DB-historikk som "kanonisk liste" (8 kontrakter
# backfillet i session 128). Disse er CFTC's Financial-futures-segment
# (FX, indices, crypto) som har TFF-rapport tilgjengelig — ikke alle
# CFTC-kontrakter har det (råvarer bruker disaggregated).
#
# Ingen instrument-rule har cot_report: tff i config/instruments/* per
# 2026-05-26, men positioning_tff-driveren kan aktiveres når som helst
# uten backfill-stub fordi denne fetcheren holder data fersk ukentlig.
_TFF_CONTRACTS: tuple[str, ...] = (
    "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
    "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE",
    "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
)


@register_runner("cot_tff")
def run_cot_tff(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Traders in Financial Futures-rapporter (FX/indices/crypto).

    Itererer over hardkodet ``_TFF_CONTRACTS``-liste i stedet for
    instrument-config (per session 2026-05-26 har ingen rule
    ``cot_report: tff``; alle FX bruker ``legacy``). Holder tabellen
    fersk så ``positioning_tff``-driveren kan wires senere uten
    backfill-stub. ``instruments``-parameter ignoreres bevisst.
    """
    from bedrock.fetch.cot_cftc import fetch_cot_tff

    result = FetchRunResult(fetcher_name="cot_tff")

    def _items():
        for contract in _TFF_CONTRACTS:

            def _do(contract=contract):
                df = fetch_cot_tff(contract, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_cot_tff(df)

            yield contract, _do

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


@register_runner("anp_ethanol")
def run_anp_ethanol(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """ANP Brasil etanol pumpe-pris (sub-fase 12.11+ analytiker D.2).

    Henter månedlige CSV/XLSX fra ANP "dados abertos" og aggregerer
    ETANOL hydrous-pris til daglig eksport-impact-vektet snitt for
    Centro-Sul-states. Skriver til fundamentals.
    """
    from bedrock.fetch.anp_ethanol import fetch_anp_ethanol

    result = FetchRunResult(fetcher_name="anp_ethanol")

    def _items():
        def _do():
            df = fetch_anp_ethanol(from_year=from_date.year, to_year=to_date.year)
            if df.empty:
                return 0
            return store.append_fundamentals(df)

        yield "anp_ethanol", _do

    _safe_run(_items(), result)
    return result


@register_runner("usda_psd_india_sugar")
def run_usda_psd_india_sugar(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """USDA FAS PSD India sugar (sub-fase 12.11+ analytiker D.5).

    Henter offisiell PSD-data (production/exports/imports/end-stocks)
    for India sugar via USDA FAS API. 16+ års historikk (2010+).
    Skriver til fundamentals.
    """
    from bedrock.fetch.usda_psd import fetch_india_sugar_history

    result = FetchRunResult(fetcher_name="usda_psd_india_sugar")

    def _items():
        def _do():
            df = fetch_india_sugar_history(from_year=from_date.year, to_year=to_date.year)
            if df.empty:
                return 0
            return store.append_fundamentals(df)

        yield "usda_psd_india_sugar", _do

    _safe_run(_items(), result)
    return result


@register_runner("isma_india")
def run_isma_india(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """ISMA India sugar production fetcher (sub-fase 12.11+ analytiker D.5).

    Henter siste sukker-prod-tall fra ISMA's offentlige API og skriver
    til fundamentals med series_id=ISMA_INDIA_SUGAR_PROD_LAKH_TONS.
    Instrument-uavhengig — kjører én gang per fetch-runde.
    """
    from bedrock.fetch.isma_india import fetch_isma_india

    result = FetchRunResult(fetcher_name="isma_india")

    def _items():
        def _do():
            df = fetch_isma_india()
            if df.empty:
                return 0
            mask = (df["date"] >= from_date.isoformat()) & (df["date"] <= to_date.isoformat())
            windowed = df[mask]
            if windowed.empty:
                return 0
            return store.append_fundamentals(windowed)

        yield "isma_india", _do

    _safe_run(_items(), result)
    return result


@register_runner("comtrade_india_sugar")
def run_comtrade_india_sugar(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """UN Comtrade månedlig India sugar exports (sub-fase 12.11+ session 154).

    Henter månedlig eksport-data via Comtrade public preview-endpoint
    (ingen API-key, ~500 records/call gratis tier). Aggregerer alle
    1701-HS-koder (raw + refined cane sugar). Skriver til fundamentals
    som COMTRADE_INDIA_SUGAR_EXPORTS_USD/KG_MONTHLY. Adresserer USDA
    PSD årlig-lag (~6 mnd) for India policy-events (eksportforbud).
    """
    from bedrock.fetch.comtrade import fetch_india_sugar_exports

    result = FetchRunResult(fetcher_name="comtrade_india_sugar")

    def _items():
        def _do():
            df = fetch_india_sugar_exports(from_year=from_date.year, to_year=to_date.year)
            if df.empty:
                return 0
            return store.append_fundamentals(df)

        yield "comtrade_india_sugar", _do

    _safe_run(_items(), result)
    return result


@register_runner("weather_monthly")
def run_weather_monthly(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Månedlig weather-aggregat per instrument-region.

    Henter daglig fra Open-Meteo Archive og aggregerer til
    weather_monthly-tabellen. Brukes for regioner som ikke har
    cot-explorer pre-aggregert JSON (sub-fase 12.11+: brazil_centro_sul
    for sukker). Idempotent via INSERT OR REPLACE på (region, month).
    """
    from bedrock.fetch.weather_monthly import fetch_weather_monthly

    result = FetchRunResult(fetcher_name="weather_monthly")

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
                df = fetch_weather_monthly(region, lat, lon, from_date, to_date)
                if df.empty:
                    return 0
                return store.append_weather_monthly(df)

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

    # Sub-fase 12.10 follow-up post-Spor-F (2026-05-02): pacing 250ms mellom
    # serier. Vi henter ~14 unike serier; FRED's gratis-limit er 120 req/min
    # (2/sek) — vi er godt innenfor, men pacing matcher pattern fra
    # eia_inventories.py og memory-feedback `free-api-no-parallel-requests`.
    # Total ekstra runtime: 14 × 0.25s ≈ 3.5 sek per dag-fyring.
    import time as _time

    pacing_sec = 0.25

    def _items():
        seen: set[str] = set()
        first = True
        for cfg in instruments:
            for series_id in cfg.instrument.fred_series_ids:
                if series_id in seen:
                    continue  # unngå dobbelt-henting når flere
                    # instrumenter deler samme serie
                seen.add(series_id)

                def _do(sid=series_id, _is_first=first):
                    if not _is_first:
                        _time.sleep(pacing_sec)
                    df = fetch_fred_series(sid, api_key, from_date, to_date)
                    if df.empty:
                        return 0
                    return store.append_fundamentals(df)

                first = False
                yield series_id, _do

    _safe_run(_items(), result)
    return result


@register_runner("agsi")
def run_agsi(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """GIE AGSI+ EU gas storage (daglig D+1).

    Sub-fase 12.10 follow-up post-Spor-F (2026-05-02): NaturalGas macro
    har 5 AGSI-drivere wired (`agsi_storage_pct`, `agsi_germany_pct`,
    `agsi_netherlands_pct`, `agsi_italy_pct`, `agsi_withdrawal_rate`,
    `agsi_injection_rate`). Frem til denne runner-registreringen ble
    data oppdatert kun manuelt via `scripts/backfill/agsi.py` —
    risiko for stale signal uten advarsel.

    Standard-vinduet (siste 30 dager) per `fetch_agsi_storage`-default
    er passende for daglig påfyll.
    """
    from bedrock.fetch.agsi import fetch_agsi_storage

    result = FetchRunResult(fetcher_name="agsi")

    def _do() -> int:
        df = fetch_agsi_storage()
        if df.empty:
            return 0
        return store.append_agsi_storage(df)

    _safe_run([("agsi", _do)], result)
    return result


@register_runner("alsi")
def run_alsi(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """GIE ALSI EU LNG-terminal storage (daglig D+1).

    Sub-fase 12.10 follow-up post-Spor-F (2026-05-02): NaturalGas macro
    har 2 ALSI-drivere wired (`alsi_eu_pct`, `alsi_storage_change`).
    Tidligere kun manuell backfill — nå daglig timer.
    """
    from bedrock.fetch.alsi import fetch_alsi_storage

    result = FetchRunResult(fetcher_name="alsi")

    def _do() -> int:
        df = fetch_alsi_storage()
        if df.empty:
            return 0
        return store.append_alsi_storage(df)

    _safe_run([("alsi", _do)], result)
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


@register_runner("shipping")
def run_shipping(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Baltic-suite (BDI/BCI/BPI/BSI). BDI auto via BDRY ETF (Yahoo);
    BCI/BPI/BSI fra manuell CSV-fallback. Daglig Mon-Fri etter US close.

    Erstatter den gamle ``bdi``-runneren (sub-fase 12.5+ session 113).
    """
    from bedrock.fetch.shipping import fetch_shipping_indices

    result = FetchRunResult(fetcher_name="shipping")

    def _do() -> int:
        df = fetch_shipping_indices(
            start_date=from_date.isoformat(),
            end_date=to_date.isoformat(),
        )
        if df.empty:
            return 0
        return store.append_shipping_indices(df)

    _safe_run([("shipping_indices", _do)], result)
    return result


@register_runner("news_intel")
def run_news_intel(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Google News RSS per bedrock-kategori. Sub-fase 12.5+ session 114.

    UI-only foreløpig per ADR-008 § 114; scoring-driver vurderes etter
    ≥1 mnds empirisk data-akkumulering. Ingen API-key; sekvensielt med
    2s pacing per memory-feedback.
    """
    from bedrock.fetch.news_intel import fetch_news_intel

    result = FetchRunResult(fetcher_name="news_intel")

    def _do() -> int:
        df = fetch_news_intel()
        if df.empty:
            return 0
        return store.append_news_intel(df)

    _safe_run([("rss_categories", _do)], result)
    return result


@register_runner("crypto_sentiment")
def run_crypto_sentiment(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Alternative.me Fear & Greed + CoinGecko global market data.
    Sub-fase 12.5+ session 115.

    UI-only foreløpig per ADR-008 § 115; scoring-driver vurderes etter
    ≥1 mnds empirisk data. Sekvensielle HTTP-kall mellom de to gratis-
    API-ene (gratis-kilde-etiquette per memory-feedback).
    """
    from bedrock.fetch.crypto_sentiment import fetch_crypto_sentiment

    result = FetchRunResult(fetcher_name="crypto_sentiment")

    def _do() -> int:
        df = fetch_crypto_sentiment()
        if df.empty:
            return 0
        return store.append_crypto_sentiment(df)

    _safe_run([("fng_coingecko", _do)], result)
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


@register_runner("unica")
def run_unica(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """UNICA Brazil sugar/ethanol halvmånedlige rapporter (session 112).

    Henter siste quinzenal-rapport via PDF (poppler-utils primær,
    pypdf fallback gjenbrukt fra session 111). Idempotent på
    report_date — hvis dagens dato allerede er lagret hopper vi over.
    Smart-skip: UNICA publiserer 2× per måned (ca 1. og 16.); hvis
    siste rad er innen 13 dager, hopp over.
    """
    from datetime import timedelta

    from bedrock.data.schemas import TABLE_UNICA_REPORTS
    from bedrock.fetch.unica import fetch_unica

    result = FetchRunResult(fetcher_name="unica")

    today = datetime.now(timezone.utc).date()
    skip_threshold = today - timedelta(days=13)
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_UNICA_REPORTS, "report_date")
    except Exception as exc:
        _log.warning("unica.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= skip_threshold:
                _log.info(
                    "unica.up_to_date latest=%s threshold=%s — skipping PDF",
                    latest_date,
                    skip_threshold,
                )
                result.items.append(ItemOutcome(item_id="unica", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("unica.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_unica()
        if df.empty:
            return 0
        return store.append_unica_reports(df)

    _safe_run([("unica", _do)], result)
    return result


@register_runner("conab")
def run_conab(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Conab Brazil monthly crop estimates (sub-fase 12.5+ session 111).

    Henter grains + kaffe-rapporter via PDF (pdftotext primær,
    pypdf fallback). Ikke instrument-spesifikk; én global fetch
    dekker alle Brazil-relaterte instrumenter (Soybean, Corn,
    Coffee).

    Smart-skip: Conab publiserer en gang per måned. Hvis DB allerede
    har rader fra inneværende måned, hopper runneren over PDF-
    nedlasting (PDF-er er store, unngå sløsing).
    """
    from bedrock.data.schemas import TABLE_CONAB_ESTIMATES
    from bedrock.fetch.conab import fetch_conab

    result = FetchRunResult(fetcher_name="conab")

    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_CONAB_ESTIMATES, "report_date")
    except Exception as exc:
        _log.warning("conab.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= month_start:
                _log.info(
                    "conab.up_to_date latest=%s month_start=%s — skipping PDF",
                    latest_date,
                    month_start,
                )
                result.items.append(ItemOutcome(item_id="conab", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("conab.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_conab()
        if df.empty:
            return 0
        return store.append_conab_estimates(df)

    _safe_run([("conab", _do)], result)
    return result


@register_runner("cot_euronext")
def run_cot_euronext(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult:
    """Euronext MiFID II COT (sub-fase 12.5+ session 110).

    Henter ukentlige rapporter for Milling Wheat (EBM), Corn (EMA), og
    Canola (ECO). Ikke instrument-spesifikk; én global fetch per kjøring.

    Smart-skip: Euronext rapporterer onsdager. Hvis DB allerede har rader
    med ``report_date >= forrige onsdag``, hopper runneren over HTTP.
    """
    from bedrock.data.schemas import TABLE_COT_EURONEXT
    from bedrock.fetch.cot_euronext import fetch_cot_euronext

    result = FetchRunResult(fetcher_name="cot_euronext")

    # Smart-skip: gjenbruker _previous_wednesday() fra session 107
    target = _previous_wednesday()
    latest = None
    try:
        latest = store.latest_observation_ts(TABLE_COT_EURONEXT, "report_date")
    except Exception as exc:
        _log.warning("euronext.smart_skip_lookup_failed error=%s", exc)

    if latest is not None:
        try:
            latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d").date()
            if latest_date >= target:
                _log.info(
                    "euronext.up_to_date latest=%s target=%s — skipping HTTP",
                    latest_date,
                    target,
                )
                result.items.append(ItemOutcome(item_id="cot_euronext", ok=True, rows_written=0))
                return result
        except ValueError:
            _log.warning("euronext.smart_skip_bad_date raw=%r", latest)

    def _do() -> int:
        df = fetch_cot_euronext()
        if df.empty:
            return 0
        return store.append_cot_euronext(df)

    _safe_run([("cot_euronext", _do)], result)
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
