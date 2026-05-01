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

    **R3 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010
    men brukes ikke til å endre output. Driveren er rank-basert
    allerede (vs siste 10 års observasjoner) og rolling-percentile-
    overlay ville ødelegge domene-logikken. Per § 5.3-kontrakt og
    audit-flagg fra R2: kun Type A snapshot for denne driveren —
    ingen pct_*/delta_*-modes pålegges. ``params["mode"]`` beholder
    sin eksisterende ``low_is_bull``/``high_is_bull``-semantikk;
    R3-feature-modes (pct_12m osv.) er ikke gyldige her og vil
    bare bli tolket som ``low_is_bull`` per default.

    Params:
        metric: "GOOD_EXCELLENT" (default), "PLANTED", "HARVESTED".
        mode: "low_is_bull" (default — yield-risk) eller "high_is_bull".
            **NB:** ikke å forveksle med R3-feature-modes (pct_*, delta_*).
            Crop_progress_stage's mode er agronomi-spesifikk
            tolknings-orientering, ikke en standard horisont-feature.
        state: "US TOTAL" (default).

    Returns:
        Score 0..1. 0.5 (nøytral) hvis instrument ikke har USDA-mapping
        eller hvis ingen rader finnes. 0.0 hvis crop-progress-data er
        helt utilgjengelig (defensive).
    """
    # ADR-010: les _horizon for å oppfylle horisont-bevisst-konvensjonen.
    # Lest men ikke brukt — crop_progress_stage er kalender-aware via
    # NASS-rapport-tidspunktet, ikke horisont-aware. Per § 5.3 (R3-
    # kontrakt): output uendret med eller uten _horizon.
    _horizon = params.get("_horizon")

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

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren er domene-spesifikk
    (rapport-til-rapport pct-change i månedlig WASDE), ikke en rolling
    tids-serie. Per crop_progress-presedens: kun `_horizon`-lesing.

    Params:
        marketing_year: optional override (default = nyeste i data).
        region: "US" (default) eller "WORLD".
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returns:
        Score 0..1. 0.5 (nøytral) hvis utilstrekkelig data.
    """
    # ADR-010: les _horizon. Månedlig rapport-til-rapport endring,
    # domene-spesifikk step-mapping — output uendret med eller uten
    # _horizon (R4 disiplin B).
    _horizon = params.get("_horizon")
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

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren er event-basert (severity 1-5
    fra DB-tabell), ikke en rolling tids-serie. Per event_distance-
    presedens: kun `_horizon`-lesing.

    Params:
        lookback_days: hvor lenge events teller (default 60).
        bull_bear: "BULL" (default) eller "BEAR" — hvilken retning
            som skal scores. Bull-events bidrar til bull-score, bear
            til bear-score.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returns:
        Score 0..1. 1.0 = severity-5 BULL-event innen vinduet.
        0.5 = ingen events (nøytral).
    """
    # ADR-010: les _horizon. Event-basert driver — output uendret
    # (R4 disiplin B).
    _horizon = params.get("_horizon")
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

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren er event-basert (severity
    + yield_impact fra DB-tabell), ikke en rolling tids-serie. Per
    event_distance-presedens: kun `_horizon`-lesing.

    Params:
        lookback_days: 90 default (epidemier varer typisk 1-3 mnd).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returns:
        Score 0..1.
    """
    # ADR-010: les _horizon. Event-basert driver — output uendret.
    _horizon = params.get("_horizon")
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


@register("shipping_pressure")
def shipping_pressure(store: Any, instrument: str, params: dict) -> float:
    """Score basert på % endring i en Baltic-shipping-indeks over et vindu.

    Erstatter ``bdi_chg30d`` (sub-fase 12.5+ session 113). Fungerer for
    hele Baltic-suiten — velg indeks via ``index``-param:

    - ``BDI`` (default for bakoverkompatibilitet): composite tørrbulk
    - ``BCI``: Capesize (kull/jernmalm)
    - ``BPI``: Panamax — primær for grain-eksport
    - ``BSI``: Supramax (korn/stål/fosfat)

    Tolkning: høy shipping-rate = dyr eksport = bear for eksportør-priser.
    Default ``bull_when=negative`` (rate ned = bull eksport-flyt).

    **R4 (sub-fase 12.7):** horisont-bevisst via ``params["mode"]`` per
    ADR-010. Default-output (mode=None) er bit-identisk pre-R4. Modes
    opererer på underliggende Baltic-rå-serien (ikke pct-change) —
    parallel til dxy_chg5d/brl_chg5d-pattern. Gjenbruker
    ``_fundamentals_*``-helpers fra macro.py.

    Params:
        index: 'BDI' (default) | 'BCI' | 'BPI' | 'BSI'.
        window_days: lookback for default (default 30). Modes overstyrer
            med _LOOKBACK_PCT_*_DAILY-konstanter (252/756).
        bull_when: "negative" (default — rate ned = bull). Oversettes til
            helper bull_when ("negative"→"low"; "positive"→"high").
        mode: R4 feature-velger per ADR-010 (None/pct_12m/pct_36m/
            delta_5d_z/delta_20d_z/extreme_flag_*).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Returns:
        Score 0..1. 0.5 (nøytral) i default ved utilstrekkelig data;
        0.0 i mode-banen ved utilstrekkelig historikk.
    """
    # ADR-010: les _horizon for fremtidig bruk.
    _horizon = params.get("_horizon")
    index_code = str(params.get("index", "BDI")).upper()
    bull_when = str(params.get("bull_when", "negative")).lower()
    mode = params.get("mode")

    if mode is None:
        return _shipping_pressure_default(store, instrument, index_code, bull_when, params)

    # Mode-banen: hent rå-serien og deleger til _fundamentals_*-helpers.
    # D1 (session 127): direkte top-level import fra horizon_helpers
    # (tidligere lazy-import fra macro for å unngå sirkulær).
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_5D_DAYS as _DELTA_5D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_20D_DAYS as _DELTA_20D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_DELTA_DAILY as _LOOKBACK_DELTA_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_12M_DAILY as _LOOKBACK_PCT_12M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_36M_DAILY as _LOOKBACK_PCT_36M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_delta_score as _fundamentals_delta_score,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_extreme_flag as _fundamentals_extreme_flag,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_pct_score as _fundamentals_pct_score,
    )

    helper_bull_when = "low" if bull_when == "negative" else "high"

    try:
        series = store.get_shipping_index(index_code, last_n=_LOOKBACK_PCT_36M_DAILY + 10)
    except KeyError:
        return 0.0
    except Exception as exc:
        _log.warning(
            "shipping.fetch_failed",
            instrument=instrument,
            index=index_code,
            error=str(exc),
        )
        return 0.0

    if mode == "pct_12m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_36M_DAILY, instrument
        )
        if result is None:
            _log.info(
                "shipping.pct_36m_fallback_to_12m",
                instrument=instrument,
                index=index_code,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(
                series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "shipping.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _shipping_pressure_default(store, instrument, index_code, bull_when, params)


def _shipping_pressure_default(
    store: Any, instrument: str, index_code: str, bull_when: str, params: dict
) -> float:
    """Pre-R4-default-bane: pct-change-trapp på Baltic-indeks."""
    window_days = int(params.get("window_days", 30))

    try:
        series = store.get_shipping_index(index_code, last_n=window_days + 5)
    except KeyError:
        return 0.5
    except Exception as exc:
        _log.warning(
            "shipping.fetch_failed",
            instrument=instrument,
            index=index_code,
            error=str(exc),
        )
        return 0.5

    if len(series) < window_days + 1:
        return 0.5

    pct_change = (
        (series.iloc[-1] - series.iloc[-window_days - 1]) / series.iloc[-window_days - 1] * 100
    )

    if bull_when == "negative":
        # Shipping ned = bull: -20% → 1.0, 0% → 0.5, +20% → 0.0
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
    # bull_when=positive: shipping opp = bull (sjeldent i agri-context)
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


# ---------------------------------------------------------------------------
# conab_yoy (sub-fase 12.5+ session 111)
# ---------------------------------------------------------------------------


@register("conab_yoy")
def conab_yoy(store: Any, instrument: str, params: dict) -> float:
    """Conab YoY-endring i produksjon, mappet til 0..1 score.

    Leser siste rapport for `commodity` og bruker `yoy_change_pct`-
    feltet (vs forrige safra).

    Tolkning: lavere produksjon (negativ YoY) = supply tight =
    bullish for prising → høy score. Høyere produksjon (positiv YoY)
    = bearish → lav score.

    Step-mapping (default):
        yoy ≤ -10% → 1.00   (sterk supply-shortfall)
        yoy ≤  -5% → 0.85
        yoy ≤  -2% → 0.65
        yoy ≤   0% → 0.50   (flat)
        yoy ≤  +5% → 0.35
        yoy >  +5% → 0.15

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren bruker årlig YoY-metric
    fra månedlig CONAB-rapport — pct_12m/delta_*_z gir lite mening på
    årlig-frekvens-output. Kun `_horizon`-lesing.

    Params:
        commodity (REQUIRED): bedrock-canonical Conab-id ('soja',
            'milho', 'cafe_total', etc.).
        thresholds: optional override.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returnerer 0..1. Defensiv 0.0 ved manglende commodity/data/feil.
    """
    # ADR-010: les _horizon. Månedlig CONAB-rapport med årlig YoY-metric.
    _horizon = params.get("_horizon")
    import pandas as pd

    commodity = params.get("commodity")
    if not commodity:
        _log.warning("conab_yoy.no_commodity_param", instrument=instrument)
        return 0.0

    try:
        df = store.get_conab_estimates(str(commodity), last_n=1)
    except KeyError:
        _log.debug("conab_yoy.data_missing", instrument=instrument, commodity=commodity)
        return 0.0
    except Exception as exc:
        _log.warning("conab_yoy.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if df.empty:
        return 0.0

    yoy_pct = df["yoy_change_pct"].iloc[0]
    if yoy_pct is None or pd.isna(yoy_pct):
        return 0.5  # ingen YoY-data → nøytral

    yoy_pct = float(yoy_pct)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps: tuple[tuple[float, float], ...] = (
            (-10.0, 1.00),
            (-5.0, 0.85),
            (-2.0, 0.65),
            (0.0, 0.50),
            (5.0, 0.35),
        )
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    for threshold, score in steps:
        if yoy_pct <= threshold:
            return float(score)
    return 0.15


# ---------------------------------------------------------------------------
# unica_change (sub-fase 12.5+ session 112)
# ---------------------------------------------------------------------------


@register("unica_change")
def unica_change(store: Any, instrument: str, params: dict) -> float:
    """UNICA Brazil sukker-supply-shift, mappet til 0..1 score.

    Leser siste UNICA quinzena-rapport og evaluerer en av flere metrikker:

    Params:
        metric: hvilket UNICA-felt skal brukes som signal:
            - ``"sugar_production_yoy"`` (default): YoY-endring i akkumulert
              sukker-produksjon. Lav (negativ) = supply tight = bullish.
            - ``"crush_yoy"``: YoY-endring i akkumulert sukkerrør-crush.
              Lav crush = mindre råvare = bullish.
            - ``"mix_sugar_pct"``: aktuell akkumulert sukker-mix-prosent
              (Centro-Sul). Lav (etanol-tilt) = mindre sukker-supply =
              bullish.
            - ``"mix_sugar_change"``: differanse current vs prev_year
              (mix_sugar_pct - mix_sugar_pct_prev). Negativ = mindre
              sukker enn ifjor = bullish.
        thresholds: optional override liste av (max_value, score)-tupler.

    Default step-mapping for YoY-metrikker (sugar_production_yoy /
    crush_yoy):
        ≤ -10% → 1.00 (sterk shortfall)
        ≤  -5% → 0.85
        ≤  -2% → 0.65
        ≤   0% → 0.50 (flat)
        ≤  +5% → 0.35
        >  +5% → 0.15 (klart over forrige safra)

    Default for mix_sugar_pct (absolutt-verdi):
        ≤ 45% → 1.00 (sterk etanol-tilt)
        ≤ 47% → 0.80
        ≤ 49% → 0.65
        ≤ 51% → 0.50 (balanse)
        ≤ 53% → 0.35
        >  53% → 0.15 (sterk sukker-tilt)

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Multi-metric driver med step-mapping
    på siste rapport — kun `_horizon`-lesing.

    Returnerer 0..1. Defensiv 0.0 ved manglende data/feil. NULL-felter
    → 0.5 (nøytral).
    """
    # ADR-010: les _horizon. ~Halv-månedlig multi-metric driver.
    _horizon = params.get("_horizon")
    import pandas as pd

    metric = str(params.get("metric", "sugar_production_yoy"))

    try:
        df = store.get_unica_reports(last_n=1)
    except Exception as exc:
        _log.warning("unica_change.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if df.empty:
        _log.debug("unica_change.no_data", instrument=instrument)
        return 0.0

    last = df.iloc[0]

    # Map metric → DataFrame-kolonne + bruk-modus
    metric_to_col = {
        "sugar_production_yoy": ("sugar_production_yoy_pct", "yoy"),
        "crush_yoy": ("crush_yoy_pct", "yoy"),
        "mix_sugar_pct": ("mix_sugar_pct", "abs_mix"),
        "mix_sugar_change": (None, "mix_change"),
    }
    if metric not in metric_to_col:
        _log.warning("unica_change.unknown_metric", instrument=instrument, metric=metric)
        return 0.0

    col, mode = metric_to_col[metric]
    if mode == "mix_change":
        cur = last["mix_sugar_pct"]
        prev = last["mix_sugar_pct_prev"]
        if cur is None or prev is None or pd.isna(cur) or pd.isna(prev):
            return 0.5
        value = float(cur) - float(prev)
    else:
        raw = last[col] if col else None
        if raw is None or pd.isna(raw):
            return 0.5
        value = float(raw)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        if mode == "abs_mix":
            steps: tuple[tuple[float, float], ...] = (
                (45.0, 1.00),
                (47.0, 0.80),
                (49.0, 0.65),
                (51.0, 0.50),
                (53.0, 0.35),
            )
        else:
            # yoy + mix_change deler samme step-mapping (yoy-stil)
            steps = (
                (-10.0, 1.00),
                (-5.0, 0.85),
                (-2.0, 0.65),
                (0.0, 0.50),
                (5.0, 0.35),
            )
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    for threshold, score in steps:
        if value <= threshold:
            return float(score)
    return 0.15


# ---------------------------------------------------------------------------
# fas_exports (sub-fase 12.7 D2 A3, session 133)
# ---------------------------------------------------------------------------
#
# USDA FAS Export Sales Reporting (ESR) — ukentlig us-eksport-status per
# commodity × destination country × marketing year. Driver-laget
# aggregerer på tvers av countries (sum) og scorer WoW-endring i
# weekly_exports som primær cross-familie-input.
#
# Tolkning: høy export demand (positivt WoW) = bull for grain price
# (USA er den marginal-tilbudet for verden; sterk demand fra utlandet
# trekker domestic-S2U ned). bull_when=high (default).
#
# WoW-skjær ignorerer country-mix-endringer (sum-aggregat). Mode-banen
# (pct_12m/pct_36m/delta_5d_z osv.) bruker ukentlig sum-tids-serie
# direkte via fundamentals_*-helpers. ESR er ukentlig, ikke daglig:
# bruker DAILY-konstantene som approximation (252 ≈ 1y med ukentlig
# data trumfer 1y kalenderis kontekst, men gir et
# rolling-rangeringsvindu på 252 rader = ~5 år ukentlig data).

# FAS commodity codes — speil mot bedrock instrument-id. Cotton 1404 =
# "All Upland Cotton" (aggregat; 1301 = American Pima er separat).
_INSTRUMENT_TO_FAS: dict[str, int] = {
    "Corn": 401,
    "Soybean": 801,
    "Wheat": 107,  # All Wheat (aggregat)
    "Cotton": 1404,  # All Upland Cotton
}

_DEFAULT_FAS_WOW_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    # bull_when="high": positiv WoW = bull (sterk export demand).
    # Steps på WoW %-endring i sum(weekly_exports) på tvers av countries.
    (-25.0, 0.0),  # ≤ -25% WoW = sterk outflow = bear
    (-10.0, 0.25),
    (0.0, 0.5),  # flat WoW = nøytral
    (10.0, 0.75),
    (25.0, 1.0),  # ≥ +25% WoW = sterk inflow = bull
)


@register("fas_exports")
def fas_exports(store: Any, instrument: str, params: dict) -> float:
    """USDA FAS ukentlig us-eksport WoW-endring mappet til 0..1.

    Sub-fase 12.7 D2 A3 (session 133). Grain/softs cross-familie-input.

    Default (mode=None): WoW (uke-til-uke) %-endring i sum(weekly_exports)
    på tvers av alle destination-countries for primary commodity. Steps
    via terskel-trapp (-25 → 0; +25 → 1.0).

    Modes per ADR-010 (pct_12m/pct_36m/delta_5d_z/delta_20d_z/
    extreme_flag_*) opererer på ukentlig sum-tids-serie. Ukentlig data
    + DAILY-lookback-konstanter gir rolling-vindu på 252 rader = ~5 år
    ukentlig (godt nok for percentile-rangering); pct_36m faller tilbake
    til pct_12m hvis utilstrekkelig historikk.

    Tolkning:
        bull_when="high" (default): økte exports = bull for grain price
            (USA er marginal-tilbud for verden).
        bull_when="low": invertert.

    Params:
        commodity_code: optional override — default mappes via instrument.
        bull_when: "high" (default) eller "low".
        thresholds: optional override for default-trapp.
        mode: feature-velger per ADR-010.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    NB: Aggregat over alle countries — country-mix-endringer fanges ikke.
    Dette er per design (sum-WoW er en bredere demand-indikator enn
    enkelt-country-shift). Bruk per-country-driver i fremtiden hvis
    nødvendig.

    Defensive 0.0 ved manglende data eller ukjent instrument.
    """
    _horizon = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    mode = params.get("mode")

    # Bestem commodity_code: explicit param trumfer instrument-mapping.
    commodity_code_param = params.get("commodity_code")
    if commodity_code_param is not None:
        commodity_code = int(commodity_code_param)
    else:
        commodity_code = _INSTRUMENT_TO_FAS.get(instrument, 0)
        if commodity_code == 0:
            return 0.0

    try:
        df = store.get_fas_esr(commodity_code)
    except KeyError:
        _log.debug("fas_exports.no_data", instrument=instrument, commodity_code=commodity_code)
        return 0.0
    except Exception as exc:
        _log.warning(
            "fas_exports.fetch_failed",
            instrument=instrument,
            commodity_code=commodity_code,
            error=str(exc),
        )
        return 0.0

    if df.empty or "weekly_exports" not in df.columns:
        return 0.0

    # Bygg pd.Series indeksert på week_ending_date (sortert ASC, allerede
    # aggregat-summert SQL-side hvis country_code=None i get_fas_esr).
    import pandas as pd

    series = pd.Series(
        df["weekly_exports"].values,
        index=pd.to_datetime(df["week_ending_date"]),
    ).dropna()

    if series.empty:
        return 0.0

    if mode is None:
        return _fas_exports_default(series, bull_when, params)

    # Mode-banen — gjenbruker fundamentals_*-helpere fra horizon_helpers.
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_5D_DAYS as _DELTA_5D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_20D_DAYS as _DELTA_20D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_DELTA_DAILY as _LOOKBACK_DELTA_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_12M_DAILY as _LOOKBACK_PCT_12M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_36M_DAILY as _LOOKBACK_PCT_36M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_delta_score as _fundamentals_delta_score,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_extreme_flag as _fundamentals_extreme_flag,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_pct_score as _fundamentals_pct_score,
    )

    if mode == "pct_12m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_36M_DAILY, instrument)
        if result is None:
            result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "fas_exports.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _fas_exports_default(series, bull_when, params)


def _fas_exports_default(series: Any, bull_when: str, params: dict) -> float:
    """Default-trapp på WoW %-endring i sum(weekly_exports)."""
    if len(series) < 2:
        return 0.5

    current = float(series.iloc[-1])
    prev = float(series.iloc[-2])

    if prev == 0:
        # Edge: forrige uke 0 export — ingen meningsfull WoW. Returnér
        # nøytral. Skjer typisk i MY-overgang når historikken ennå ikke
        # har bygd opp.
        return 0.5

    pct_change = (current - prev) / abs(prev) * 100.0

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_FAS_WOW_THRESHOLDS_HIGH
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = 1.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if pct_change <= threshold:
            score = float(s)
            break

    if bull_when == "low":
        return round(1.0 - score, 4)
    return round(score, 4)


# ---------------------------------------------------------------------------
# drought_monitor (sub-fase 12.7 D2 A9, session 133)
# ---------------------------------------------------------------------------
#
# US Drought Monitor — ukentlig CONUS-aggregat fra USDM (cumulative %-areal
# per drought-severity-bucket). Brukes av grain/softs weather-familier som
# co-driver med weather_stress.
#
# Default-input er ``d2_pct`` (% i D2+ severe+) for siste observasjon.
# Tolkning: høy drought-andel = bull for grain price (yield-risk reduserer
# supply). bull_when=high (default).
#
# Mode-banen bruker d2_pct-tids-serien direkte via fundamentals_*-helpers.
# USDM er ukentlig — DAILY-lookback-konstanter approximerer rolling-window
# (252 ukentlige rader = ~5 år).

_DEFAULT_DROUGHT_PCT_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    # bull_when="high": høy D2+ andel = bull. Steps på rå d2_pct (0..100).
    (5.0, 0.0),  # ≤ 5% i D2+ = ingen reell drought = bear
    (15.0, 0.25),  # ~normal varians
    (25.0, 0.5),  # nøytral — moderat drought
    (40.0, 0.75),  # høy drought-bekymring
    (100.0, 1.0),  # ≥ 40% i D2+ = sterk drought = sterk bull
)


@register("drought_monitor")
def drought_monitor(store: Any, instrument: str, params: dict) -> float:
    """USDM drought-severity mappet til 0..1 for grain/softs weather.

    Sub-fase 12.7 D2 A9 (session 133). Co-driver med weather_stress i
    Corn/Soybean/Wheat/Cotton weather-familien.

    Default (mode=None): terskel-trapp på rå ``d2_pct`` (% i D2+ severe+)
    fra siste USDM-observasjon. R4-modes bruker d2_pct-tids-serien via
    fundamentals_*-helpere.

    Frekvens: USDM publiserer ukentlig (torsdag, basert på tirsdags-data).
    Bruker DAILY-lookback-konstantene som approximation.

    Tolkning:
        bull_when="high" (default): høy drought-andel = bull (yield-risk
            reduserer supply).
        bull_when="low": invertert.

    Params:
        aoi: USDM-AOI-kode. Default ``"us"`` (CONUS-aggregat). Per-state
            tilgjengelig: ``"IA"``, ``"IL"``, etc.
        metric: hvilken D-bucket skal brukes (``"d2_pct"`` default). Kan
            være ``d0_pct``/``d1_pct``/``d3_pct``/``d4_pct``.
        bull_when: "high" (default) eller "low".
        thresholds: optional override for default-trapp.
        mode: feature-velger per ADR-010.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Defensive 0.0 ved manglende data.
    """
    _horizon = params.get("_horizon")
    aoi = str(params.get("aoi", "us")).lower()
    metric = str(params.get("metric", "d2_pct"))
    bull_when = str(params.get("bull_when", "high")).lower()
    mode = params.get("mode")

    try:
        df = store.get_drought_monitor(aoi)
    except KeyError:
        _log.debug("drought_monitor.no_data", instrument=instrument, aoi=aoi)
        return 0.0
    except Exception as exc:
        _log.warning(
            "drought_monitor.fetch_failed",
            instrument=instrument,
            aoi=aoi,
            error=str(exc),
        )
        return 0.0

    if df.empty or metric not in df.columns:
        return 0.0

    import pandas as pd

    series = pd.Series(
        df[metric].values,
        index=pd.to_datetime(df["map_date"]),
    ).dropna()

    if series.empty:
        return 0.0

    current = float(series.iloc[-1])

    if mode is None:
        return _drought_monitor_default(current, bull_when, params)

    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_5D_DAYS as _DELTA_5D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_20D_DAYS as _DELTA_20D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_DELTA_DAILY as _LOOKBACK_DELTA_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_12M_DAILY as _LOOKBACK_PCT_12M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_36M_DAILY as _LOOKBACK_PCT_36M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_delta_score as _fundamentals_delta_score,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_extreme_flag as _fundamentals_extreme_flag,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_pct_score as _fundamentals_pct_score,
    )

    if mode == "pct_12m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_36M_DAILY, instrument)
        if result is None:
            result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "drought_monitor.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _drought_monitor_default(current, bull_when, params)


def _drought_monitor_default(current: float, bull_when: str, params: dict) -> float:
    """Default-trapp på rå d2_pct (0..100)."""
    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_DROUGHT_PCT_THRESHOLDS_HIGH
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = 1.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break

    if bull_when == "low":
        return round(1.0 - score, 4)
    return round(score, 4)


# ---------------------------------------------------------------------------
# cecafe_export_change (sub-fase 12.7 D3 A10, session 135)
# ---------------------------------------------------------------------------
#
# Cecafé månedlig brasiliansk kaffe-eksport — proxy for global supply-stress.
# Brasil står for ~40 % av global kaffeproduksjon og er klart største
# eksportør av arabica. Lave eksport-volumer = supply-stress = bullish for
# kaffe-pris (KC). bull_when="low" default per § 19.5 Del A A10.
#
# Default-trapp på MoM %-endring i ``volume_60kg_bags`` for
# ``coffee_type='sum'``. NB: Brasiliansk kaffe har sterk sesongmessig
# variasjon (lav-eksport jan-mar, høy-eksport apr-aug), så MoM-volatilitet
# er stor. Wider thresholds enn FAS weekly. R4-modes (pct_12m/pct_36m)
# opererer på full serie og gir bedre signal — bruk dem hvis tilgjengelig.

_DEFAULT_CECAFE_MOM_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    # bull_when="high": positiv MoM = bull (sterk export demand).
    # Etter flip ved bull_when="low" (kaffe default): lavt MoM-volume =
    # bull (supply tight). Steps på MoM %-endring i sum(volume_60kg_bags).
    # Wider intervaller enn weekly-drivere pga månedlig sesongvariasjon.
    (-40.0, 0.0),  # ≤ -40% MoM = sterk drop = bear i "high"-konvensjon
    (-15.0, 0.25),
    (0.0, 0.5),  # flat MoM = nøytral
    (15.0, 0.75),
    (40.0, 1.0),  # ≥ +40% MoM = sterk increase = bull i "high"-konvensjon
)


@register("cecafe_export_change")
def cecafe_export_change(store: Any, instrument: str, params: dict) -> float:
    """Cecafé månedlig kaffe-eksport-endring mappet til 0..1 for Coffee.

    Sub-fase 12.7 D3 A10 (session 135). Brukes i Coffee conab-familien
    sammen med ``conab_yoy`` (Brazil-produksjons-anslag).

    Default (mode=None): MoM (måned-til-måned) %-endring i
    ``volume_60kg_bags`` for ``coffee_type='sum'``. Steps via terskel-
    trapp (-40 → 0; +40 → 1.0; bredere enn weekly pga sesongvariasjon).

    Modes per ADR-010 (pct_12m/pct_36m/delta_5d_z/delta_20d_z/
    extreme_flag_*) opererer på månedlig sum-tids-serie. Månedlig data
    + DAILY-lookback-konstanter gir rolling-vindu på 252 rader = ~21 år
    månedlig (godt nok for percentile-rangering); pct_36m faller tilbake
    til pct_12m hvis utilstrekkelig historikk.

    Tolkning:
        bull_when="low" (default): lavt eksportvolum = supply-issue =
            bull for kaffe-pris (Brasil ~40 % av global supply).
        bull_when="high": invertert.

    Params:
        coffee_type: hvilken type skal brukes (default ``"sum"``). Andre:
            ``"arabica"`` (KC primær), ``"robusta"``, ``"industrialized"``.
        bull_when: "low" (default) eller "high".
        thresholds: optional override for default-trapp.
        mode: feature-velger per ADR-010.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Defensive 0.0 ved manglende data.
    """
    _horizon = params.get("_horizon")
    coffee_type = str(params.get("coffee_type", "sum")).lower()
    bull_when = str(params.get("bull_when", "low")).lower()
    mode = params.get("mode")

    try:
        df = store.get_cecafe_exports(coffee_type)
    except KeyError:
        _log.debug("cecafe_export_change.no_data", instrument=instrument, coffee_type=coffee_type)
        return 0.0
    except Exception as exc:
        _log.warning(
            "cecafe_export_change.fetch_failed",
            instrument=instrument,
            coffee_type=coffee_type,
            error=str(exc),
        )
        return 0.0

    if df.empty or "volume_60kg_bags" not in df.columns:
        return 0.0

    import pandas as pd

    series = pd.Series(
        df["volume_60kg_bags"].values,
        index=pd.to_datetime(df["month"]),
    ).dropna()

    if series.empty:
        return 0.0

    if mode is None:
        return _cecafe_export_change_default(series, bull_when, params)

    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_5D_DAYS as _DELTA_5D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        DELTA_20D_DAYS as _DELTA_20D_DAYS,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_DELTA_DAILY as _LOOKBACK_DELTA_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_12M_DAILY as _LOOKBACK_PCT_12M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        LOOKBACK_PCT_36M_DAILY as _LOOKBACK_PCT_36M_DAILY,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_delta_score as _fundamentals_delta_score,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_extreme_flag as _fundamentals_extreme_flag,
    )
    from bedrock.engine.drivers.horizon_helpers import (
        fundamentals_pct_score as _fundamentals_pct_score,
    )

    if mode == "pct_12m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_36M_DAILY, instrument)
        if result is None:
            result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "cecafe_export_change.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _cecafe_export_change_default(series, bull_when, params)


def _cecafe_export_change_default(series: Any, bull_when: str, params: dict) -> float:
    """Default-trapp på MoM %-endring i sum(volume_60kg_bags)."""
    if len(series) < 2:
        return 0.5

    current = float(series.iloc[-1])
    prev = float(series.iloc[-2])

    if prev == 0:
        return 0.5

    pct_change = (current - prev) / abs(prev) * 100.0

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_CECAFE_MOM_THRESHOLDS_HIGH
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = 1.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if pct_change <= threshold:
            score = float(s)
            break

    if bull_when == "low":
        return round(1.0 - score, 4)
    return round(score, 4)


__all__ = [
    "cecafe_export_change",
    "conab_yoy",
    "crop_progress_stage",
    "disease_pressure",
    "drought_monitor",
    "export_event_active",
    "fas_exports",
    "shipping_pressure",
    "unica_change",
    "wasde_s2u_change",
]
