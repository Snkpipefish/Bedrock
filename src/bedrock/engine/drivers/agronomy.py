"""Agronomy-drivere — bruker NASS Crop Progress + WASDE + events.

PLAN § 7.3 datakilder, session 83:

- ``crop_progress_stage``: Returnerer regime-score (0..1) basert på
  USDA NASS ukentlig crop-progress (% planted, silking, harvested,
  good/excellent condition).

- ``wasde_s2u_change``: Endring i stocks-to-use ratio fra forrige
  WASDE-rapport. Lavere S2U → tighter supply → bull.

- ``wasde_yield_change``: Endring i yield-prognose fra forrige
  rapport. Lavere yield → bull.

- ``export_event_active``: Returnerer 1.0 hvis eksport-policy event
  med høy severity er aktiv innen lookback-vinduet, 0.0 ellers.

- ``disease_pressure``: Returnerer score basert på disease/pest-
  alerts severity og yield-impact for commodity.

Alle drivere er asset-class-spesifikke for agri (commodity-mapping
fra instrument til USDA-commodity-kode).
"""

from __future__ import annotations

from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# Mapping fra bedrock instrument-id til USDA NASS commodity-kode.
# Brukes av crop_progress_stage og wasde_*-driverne.
_INSTRUMENT_TO_USDA: dict[str, str] = {
    "Corn": "CORN",
    "Soybean": "SOYBEANS",
    "Wheat": "WHEAT",
    "Cotton": "COTTON",
    # Ikke-USDA: Coffee, Sugar (Brazil-driven, ikke i NASS)
}


@register("crop_progress_stage")
def crop_progress_stage(store: Any, instrument: str, params: dict) -> float:
    """Score basert på siste NASS crop-progress good/excellent-prosent.

    Tolkning: Høy good/excellent-condition = bull (sterk crop forventes
    god yield → mer supply, men også reduserer rally-risiko fra
    yield-skuffelse). Per asymmetri-prinsippet: høy condition er svak
    bull (negative-tail-cut), lav condition er sterk bull (yield-
    risk).

    Bruker default `mode=low_is_bull` (yield-risk-drevet), eller
    `mode=high_is_bull` for trend-confirmation.

    Params:
        metric: "GOOD_EXCELLENT" (default), "PLANTED", "HARVESTED".
        mode: "low_is_bull" (default — yield-risk) eller "high_is_bull".
        state: "US TOTAL" (default).

    Returns:
        Score 0..1. 0.5 (nøytral) hvis instrument ikke har USDA-mapping
        eller hvis ingen rader finnes. 0.0 hvis crop-progress-data er
        helt utilgjengelig (defensive).
    """
    usda_commodity = _INSTRUMENT_TO_USDA.get(instrument)
    if usda_commodity is None:
        _log.debug("crop_progress.no_usda_mapping", instrument=instrument)
        return 0.5

    metric = str(params.get("metric", "GOOD_EXCELLENT"))
    mode = str(params.get("mode", "low_is_bull")).lower()
    state = str(params.get("state", "US TOTAL"))

    try:
        df = store.get_crop_progress(usda_commodity, state=state, metric=metric)
    except Exception as exc:
        _log.warning(
            "crop_progress.fetch_failed",
            instrument=instrument,
            commodity=usda_commodity,
            error=str(exc),
        )
        return 0.0

    if df.empty:
        _log.debug("crop_progress.no_rows", instrument=instrument, commodity=usda_commodity)
        return 0.5

    latest_pct = float(df["value_pct"].iloc[-1])

    # GOOD_EXCELLENT er typisk 50-80% under normale forhold; brukes
    # som percentile-rank for siste 10 års observasjoner.
    historical = df["value_pct"].astype("float64")
    if len(historical) < 10:
        # Fallback: lineær mapping 0-100 → 0-1
        raw = max(0.0, min(1.0, latest_pct / 100.0))
    else:
        rank = float((historical < latest_pct).sum()) / float(len(historical) - 1)
        raw = max(0.0, min(1.0, rank))

    if mode == "low_is_bull":
        return 1.0 - raw
    return raw


@register("wasde_s2u_change")
def wasde_s2u_change(store: Any, instrument: str, params: dict) -> float:
    """Score basert på endring i WASDE stocks-to-use ratio.

    Lavere S2U = tighter supply = bull. Driveren beregner siste
    rapport-S2U vs forrige rapport, mapper change til 0..1.

    Tolkning: -10% S2U-endring er ekstrem bullish; +10% er ekstrem bear.
    Mellom-verdier mappes lineært.

    Params:
        marketing_year: optional override (default = nyeste i data).
        region: "US" (default) eller "WORLD".

    Returns:
        Score 0..1. 0.5 (nøytral) hvis utilstrekkelig data.
    """
    usda_commodity = _INSTRUMENT_TO_USDA.get(instrument)
    if usda_commodity is None:
        return 0.5

    region = str(params.get("region", "US"))

    try:
        df = store.get_wasde(usda_commodity, "S2U", region=region)
    except Exception as exc:
        _log.warning("wasde_s2u.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if len(df) < 2:
        return 0.5

    # Filter til siste marketing year (typisk "Proj." for nåværende sesong).
    # Data sorted by report_date ASC, så vi henter siste rapport's MY-er
    # og bruker den for å sammenligne på tvers av rapporter.
    latest_report = df["report_date"].max()
    latest_my = df[df["report_date"] == latest_report]["marketing_year"].max()

    same_my = df[df["marketing_year"] == latest_my].sort_values("report_date")
    if len(same_my) < 2:
        return 0.5

    latest = float(same_my["value"].iloc[-1])
    prev = float(same_my["value"].iloc[-2])
    if prev == 0:
        return 0.5

    pct_change = (latest - prev) / prev * 100

    # Mapping: -10% = 1.0 (bull), 0% = 0.5, +10% = 0.0 (bear)
    if pct_change <= -10:
        return 1.0
    if pct_change <= -5:
        return 0.85
    if pct_change <= -1:
        return 0.65
    if pct_change <= 1:
        return 0.5
    if pct_change <= 5:
        return 0.35
    if pct_change <= 10:
        return 0.15
    return 0.0


@register("export_event_active")
def export_event_active(store: Any, instrument: str, params: dict) -> float:
    """Returner 0..1 basert på aktive eksport-policy events for commodity.

    Bruker manuell-curated `export_events`-tabell (PLAN § 7.3 Fase-5).

    Params:
        lookback_days: hvor lenge events teller (default 60).
        bull_bear: "BULL" (default) eller "BEAR" — hvilken retning
            som skal scores. Bull-events bidrar til bull-score, bear
            til bear-score.

    Returns:
        Score 0..1. 1.0 = severity-5 BULL-event innen vinduet.
        0.5 = ingen events (nøytral).
    """
    from datetime import date, timedelta

    lookback_days = int(params.get("lookback_days", 60))
    target_bull_bear = str(params.get("bull_bear", "BULL")).upper()

    # Hent commodity-mapping (samme USDA-koder som NASS, med ekstensjoner
    # for softs som ikke er i NASS).
    commodity_map = {
        "Corn": "CORN",
        "Soybean": "SOYBEANS",
        "Wheat": "WHEAT",
        "Cotton": "COTTON",
        "Sugar": "SUGAR",
        "Coffee": "COFFEE",
    }
    commodity = commodity_map.get(instrument)
    if commodity is None:
        return 0.5

    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()

    try:
        df = store.get_export_events(commodity=commodity, from_date=from_date)
    except Exception as exc:
        _log.warning("export_event.fetch_failed", instrument=instrument, error=str(exc))
        return 0.5

    if df.empty:
        return 0.5

    # Filter på bull_bear-retning og finn høyeste severity.
    matching = df[df["bull_bear"].str.upper() == target_bull_bear]
    if matching.empty:
        return 0.5

    max_severity = int(matching["severity"].max())
    # Severity 1-5 mapping:
    severity_score = {1: 0.55, 2: 0.65, 3: 0.75, 4: 0.85, 5: 1.0}
    return severity_score.get(max_severity, 0.5)


@register("disease_pressure")
def disease_pressure(store: Any, instrument: str, params: dict) -> float:
    """Score basert på disease/pest-alerts for commodity.

    Disease-pressure er typisk bull for prisen (yield-risk reduserer
    supply). Score 0.5 (nøytral) hvis ingen alerts; >0.5 ved aktive
    disease-events.

    Params:
        lookback_days: 90 default (epidemier varer typisk 1-3 mnd).

    Returns:
        Score 0..1.
    """
    from datetime import date, timedelta

    lookback_days = int(params.get("lookback_days", 90))
    commodity_map = {
        "Corn": "CORN",
        "Soybean": "SOYBEANS",
        "Wheat": "WHEAT",
        "Cotton": "COTTON",
        "Sugar": "SUGAR",
        "Coffee": "COFFEE",
    }
    commodity = commodity_map.get(instrument)
    if commodity is None:
        return 0.5

    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()

    try:
        df = store.get_disease_alerts(commodity=commodity, from_date=from_date)
    except Exception as exc:
        _log.warning("disease.fetch_failed", instrument=instrument, error=str(exc))
        return 0.5

    if df.empty:
        return 0.5

    # Severity 1-5 + optional yield_impact_pct gir kombinert pressure-score
    max_severity = int(df["severity"].max())
    impact_max = float(df["yield_impact_pct"].max()) if df["yield_impact_pct"].notna().any() else 0

    # Severity-basert + yield-impact bonus
    base = {1: 0.55, 2: 0.65, 3: 0.75, 4: 0.85, 5: 0.95}.get(max_severity, 0.5)
    if impact_max >= 10:
        base = min(1.0, base + 0.05)
    return base


@register("bdi_chg30d")
def bdi_chg30d(store: Any, instrument: str, params: dict) -> float:
    """Score basert på 30-dagers % endring i Baltic Dry Index.

    BDI er proxy for global shipping/freight cost. Høyt BDI = dyr
    eksport = bear for grain-eksportører. Default ``bull_when=negative``
    (BDI ned = bull eksport-flyt).

    Params:
        window_days: lookback (default 30).
        bull_when: "negative" (default) — BDI ned = bull.

    Returns:
        Score 0..1. 0.5 (nøytral) hvis utilstrekkelig data.
    """
    window_days = int(params.get("window_days", 30))
    bull_when = str(params.get("bull_when", "negative")).lower()

    try:
        series = store.get_bdi(last_n=window_days + 5)
    except KeyError:
        return 0.5
    except Exception as exc:
        _log.warning("bdi.fetch_failed", instrument=instrument, error=str(exc))
        return 0.5

    if len(series) < window_days + 1:
        return 0.5

    pct_change = (
        (series.iloc[-1] - series.iloc[-window_days - 1]) / series.iloc[-window_days - 1] * 100
    )

    if bull_when == "negative":
        # BDI ned = bull: -20% → 1.0, 0% → 0.5, +20% → 0.0
        if pct_change <= -20:
            return 1.0
        if pct_change <= -10:
            return 0.8
        if pct_change <= -3:
            return 0.65
        if pct_change <= 3:
            return 0.5
        if pct_change <= 10:
            return 0.35
        if pct_change <= 20:
            return 0.2
        return 0.0
    # bull_when=positive: BDI opp = bull (sjeldent i agri-context)
    if pct_change >= 20:
        return 1.0
    if pct_change >= 10:
        return 0.8
    if pct_change >= 3:
        return 0.65
    if pct_change >= -3:
        return 0.5
    if pct_change >= -10:
        return 0.35
    if pct_change >= -20:
        return 0.2
    return 0.0


@register("igc_stocks_change")
def igc_stocks_change(store: Any, instrument: str, params: dict) -> float:
    """Score basert på endring i IGC ending-stocks fra forrige rapport.

    Lavere ending-stocks = tighter global supply = bull. Driveren leser
    ``TABLE_IGC`` for relevant grain (Corn=MAIZE, Wheat=WHEAT).

    Returns:
        Score 0..1. 0.5 (nøytral) ved utilstrekkelig data.
    """
    igc_grain_map = {
        "Corn": "MAIZE",
        "Wheat": "WHEAT",
    }
    grain = igc_grain_map.get(instrument)
    if grain is None:
        return 0.5

    try:
        df = store.get_igc(grain, "ENDING_STOCKS")
    except Exception as exc:
        _log.warning("igc.fetch_failed", instrument=instrument, error=str(exc))
        return 0.5

    if len(df) < 2:
        return 0.5

    latest = float(df["value_mil_tons"].iloc[-1])
    prev = float(df["value_mil_tons"].iloc[-2])
    if prev == 0:
        return 0.5

    pct_change = (latest - prev) / prev * 100

    if pct_change <= -10:
        return 1.0
    if pct_change <= -5:
        return 0.85
    if pct_change <= -1:
        return 0.65
    if pct_change <= 1:
        return 0.5
    if pct_change <= 5:
        return 0.35
    if pct_change <= 10:
        return 0.15
    return 0.0


__all__ = [
    "bdi_chg30d",
    "crop_progress_stage",
    "disease_pressure",
    "export_event_active",
    "igc_stocks_change",
    "wasde_s2u_change",
]
