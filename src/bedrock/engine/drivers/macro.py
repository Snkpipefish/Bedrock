"""Macro-familie drivere (Sub-fase 12.5 session 71).

Erstatter ``sma200_align``-placeholder i macro-familien for finansielle
instrumenter. Bruker FRED-fundamentals (DataStore.get_fundamentals) til
å beregne makro-miljøet rundt instrumentet.

Tre drivere implementert:

- ``real_yield``: 10-årig nominell yield − 10-årig inflation expectation
  (DGS10 − T10YIE). Mappet til 0..1 via konfigurerbar terskel-trapp.
  ``bull_when="low"`` (default for Gold/Silver — ikke-rentebærende
  metaller får støtte når real-yield faller). ``bull_when="high"``
  for USD-positive assets (USD, T-bonds).

- ``dxy_chg5d``: 5-dager rolling % endring i DTWEXBGS (broad dollar
  index). USD-styrke. Default ``bull_when="negative"`` (USD-svakhet
  støtter risk-on / metaller). ``"positive"`` for USD-relaterte longs.

- ``vix_regime``: VIXCLS klassifisert som lav/normal/høy regime.
  Mappet til 0..1 via params. Default tolket som risk-on score
  (lav VIX → høy score) — passer assets som blomstrer i lavt-vol-
  regime. ``invert=True`` for hedger-assets (Gold som safe-haven).

Alle drivere er asset-class-agnostic: dataen er felles, men
tolkningen drives av YAML-params. Defensive 0.0-fallbacks ved
manglende fundamentals-serie eller utilstrekkelig historikk.

Driver-funksjoner trenger ingen ``cot_contract`` — de leser FRED-
serier som er felles på tvers av instrumenter. ``instrument``-
parameteren brukes kun for logging.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# real_yield
# ---------------------------------------------------------------------------


# Default terskler for real yield (i prosentpoeng).
# Keys: terskel for real_yield-verdi, value: score 0..1.
# `bull_when="low"` (Gold-default): låg real yield → høy score.
_DEFAULT_REAL_YIELD_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    (-0.5, 1.0),  # negative real yield = sterk bull
    (0.5, 0.75),  # < 0.5 real yield = bull
    (1.5, 0.5),  # 0.5-1.5 = nøytral
    (2.5, 0.25),  # 1.5-2.5 = bear-ish
)

# Speilet for `bull_when="high"` (f.eks. USD-bonds): høy real yield → høy score.
_DEFAULT_REAL_YIELD_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    (2.5, 1.0),
    (1.5, 0.75),
    (0.5, 0.5),
    (-0.5, 0.25),
)


@register("real_yield")
def real_yield(store: Any, instrument: str, params: dict) -> float:
    """Real yield (DGS10 − T10YIE) mappet til 0..1.

    Params:
        nominal_series: FRED-serie for nominell yield (default ``DGS10``)
        inflation_series: FRED-serie for inflation expectation
            (default ``T10YIE``)
        bull_when: ``"low"`` (default) eller ``"high"`` — om låg eller høy
            real yield gir høyest score.
        thresholds: optional override-liste av ``[[level, score], ...]``
            som tolkes som "real_yield ≤ level → score". Sortert
            descending automatisk hvis ``bull_when="low"``, ascending
            for ``"high"``.

    Defensiv 0.0-retur ved manglende serier eller manglende overlapp.
    """
    nominal_id = params.get("nominal_series", "DGS10")
    inflation_id = params.get("inflation_series", "T10YIE")
    bull_when = params.get("bull_when", "low")

    try:
        nominal = store.get_fundamentals(nominal_id)
        inflation = store.get_fundamentals(inflation_id)
    except KeyError as exc:
        _log.debug(
            "real_yield.series_missing",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "real_yield.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    real = (nominal - inflation).dropna()
    if real.empty:
        _log.debug("real_yield.no_overlap", instrument=instrument)
        return 0.0

    current = float(real.iloc[-1])

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        if bull_when == "high":
            steps = _DEFAULT_REAL_YIELD_THRESHOLDS_HIGH
        else:
            steps = _DEFAULT_REAL_YIELD_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "high":
        # Høyere real_yield → høyere score: kjør thresholds i synkende
        # rekkefølge og treff på første som tilfredsstilles ovenfra.
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        # Default: lav real_yield → høy score. Tester nedover.
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)

    return 0.0


# ---------------------------------------------------------------------------
# dxy_chg5d
# ---------------------------------------------------------------------------


_DEFAULT_DXY_THRESHOLDS_NEGATIVE: tuple[tuple[float, float], ...] = (
    # USD-svakhet (negative endring) → høy score (default for Gold/risk-on)
    (-1.5, 1.0),  # < -1.5% = sterk USD-svakhet
    (-0.5, 0.75),
    (0.5, 0.5),  # ±0.5% = nøytral
    (1.5, 0.25),
)


_DEFAULT_DXY_THRESHOLDS_POSITIVE: tuple[tuple[float, float], ...] = (
    # USD-styrke (positive endring) → høy score (USD-relaterte longs)
    (1.5, 1.0),
    (0.5, 0.75),
    (-0.5, 0.5),
    (-1.5, 0.25),
)


@register("dxy_chg5d")
def dxy_chg5d(store: Any, instrument: str, params: dict) -> float:
    """5-dager % endring i broad dollar index (DTWEXBGS), mappet til 0..1.

    Params:
        series: FRED-serie (default ``DTWEXBGS``)
        window: rolling-vindu i dager (default 5). Signalvinduer >5
            gir mer stabilt signal men reagerer saktere.
        bull_when: ``"negative"`` (default — USD-svakhet er bull for
            risk-on / Gold) eller ``"positive"`` (USD-styrke er bull
            for USD-relaterte longs).
        thresholds: optional override.

    Defensiv 0.0-retur ved manglende DTWEXBGS-serie eller for kort
    historikk.
    """
    series_id = params.get("series", "DTWEXBGS")
    window = int(params.get("window", 5))
    bull_when = params.get("bull_when", "negative")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("dxy_chg5d.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("dxy_chg5d.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if len(series) < window + 1:
        _log.debug(
            "dxy_chg5d.short_history",
            instrument=instrument,
            n=len(series),
            window=window,
        )
        return 0.0

    pct_change = (series.iloc[-1] - series.iloc[-window - 1]) / series.iloc[-window - 1] * 100
    if pd.isna(pct_change):
        return 0.0
    current = float(pct_change)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        if bull_when == "positive":
            steps = _DEFAULT_DXY_THRESHOLDS_POSITIVE
        else:
            steps = _DEFAULT_DXY_THRESHOLDS_NEGATIVE
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "positive":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# brl_chg5d
# ---------------------------------------------------------------------------


# BRL er ~2x mer volatil enn DXY (5d stdev: BRL 2.06% vs DXY ~0.8%).
# Terskler skalert deretter, basert på empirisk percentil-fordeling
# 2010-2026: p90=+2.65%, p75=+1.28%, p25=-1.10%, p10=-2.28%.
_DEFAULT_BRL_THRESHOLDS_POSITIVE: tuple[tuple[float, float], ...] = (
    # USDBRL UP = BRL svakhet → bull for brasiliansk-eksport (sukker, kaffe)
    (2.5, 1.0),
    (1.0, 0.75),
    (-1.0, 0.5),  # ±1% = nøytral
    (-2.5, 0.25),
)


_DEFAULT_BRL_THRESHOLDS_NEGATIVE: tuple[tuple[float, float], ...] = (
    # USDBRL DOWN = BRL styrke → bull for BRL-positive assets
    (-2.5, 1.0),
    (-1.0, 0.75),
    (1.0, 0.5),
    (2.5, 0.25),
)


@register("brl_chg5d")
def brl_chg5d(store: Any, instrument: str, params: dict) -> float:
    """5-dager % endring i USD/BRL (DEXBZUS), mappet til 0..1.

    Sub-fase 12.5+ session 80: erstatter DXY-proxy for BRL-eksponerte
    softs (sukker, kaffe). DEXBZUS = "Brazilian Reals to One U.S.
    Dollar" — altså DEXBZUS UP = BRL svakhet.

    Params:
        series: FRED-serie (default ``DEXBZUS``)
        window: rolling-vindu i dager (default 5)
        bull_when: ``"positive"`` (default — USDBRL UP = BRL-svakhet
            = bull for brasiliansk-eksport: sukker, kaffe) eller
            ``"negative"`` (BRL-styrke er bull).
        thresholds: optional override.

    Defensiv 0.0-retur ved manglende serie eller for kort historikk.
    """
    series_id = params.get("series", "DEXBZUS")
    window = int(params.get("window", 5))
    bull_when = params.get("bull_when", "positive")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("brl_chg5d.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("brl_chg5d.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if len(series) < window + 1:
        _log.debug("brl_chg5d.short_history", instrument=instrument, n=len(series), window=window)
        return 0.0

    pct_change = (series.iloc[-1] - series.iloc[-window - 1]) / series.iloc[-window - 1] * 100
    if pd.isna(pct_change):
        return 0.0
    current = float(pct_change)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = (
            _DEFAULT_BRL_THRESHOLDS_POSITIVE
            if bull_when == "positive"
            else _DEFAULT_BRL_THRESHOLDS_NEGATIVE
        )
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "positive":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# vix_regime
# ---------------------------------------------------------------------------


# VIX-regimene. Kilder: VIX < 15 = lav vol, 15-25 = normal, > 25 = forhøyet.
_DEFAULT_VIX_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (15.0, 1.0),  # låg vol = risk-on bull (default; invert for safe-havens)
    (20.0, 0.75),
    (25.0, 0.5),
    (35.0, 0.25),
)


@register("vix_regime")
def vix_regime(store: Any, instrument: str, params: dict) -> float:
    """VIX-baseri regime-klassifikator, mappet til 0..1.

    Params:
        series: FRED-serie (default ``VIXCLS``)
        invert: ``False`` (default) — låg VIX = risk-on = høy score.
            ``True`` for safe-haven-assets (Gold, US-bonds) som
            blomstrer når VIX er forhøyet.
        thresholds: optional override.

    Default-terskler:
        VIX ≤ 15 → 1.0 (rolig marked)
        VIX ≤ 20 → 0.75
        VIX ≤ 25 → 0.5
        VIX ≤ 35 → 0.25
        VIX > 35 → 0.0 (krise-regime)
    """
    series_id = params.get("series", "VIXCLS")
    invert = bool(params.get("invert", False))

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("vix_regime.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("vix_regime.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if series.empty:
        return 0.0

    current = float(series.iloc[-1])

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_VIX_THRESHOLDS
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    # Default-mapping: lav VIX = høy score (test ascending).
    score = 0.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break

    if invert:
        # Safe-haven-tolkning: 1.0 ↔ 0.0, 0.75 ↔ 0.25, 0.5 stays.
        return round(1.0 - score, 4)
    return score


# ---------------------------------------------------------------------------
# eia_stock_change (sub-fase 12.5+ session 107)
# ---------------------------------------------------------------------------

# Default z-mapping for eia_stock_change. Speilet av cot_z_score-trappen:
# z ≥ +2 → 1.0 (sterk draw, bullish), z ≥ +1 → 0.75, ..., z < -0.5 → 0.0
# (sterk build, bearish). NB: z er allerede invertert (-z(WoW%)) hvis
# invert=True (default), så skalaen virker direkte bullish.
_DEFAULT_EIA_Z_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (2.0, 1.0),
    (1.0, 0.75),
    (0.5, 0.6),
    (0.0, 0.5),
    (-0.5, 0.3),
)


@register("eia_stock_change")
def eia_stock_change(store: Any, instrument: str, params: dict) -> float:
    """Z-score av week-over-week % endring i EIA-inventories, mappet til 0..1.

    Logikk for energi (CrudeOil/Brent/NaturalGas) — default-tolkningen:
    - Store builds (positiv WoW%, lager bygger seg) = bearish for prising
    - Store draws (negativ WoW%, lager tappes) = bullish for prising

    Driver inverterer derfor z-score-fortegnet før step-mapping. Lookback
    52 uker = 1 år rolling baseline.

    Params:
        series_id (REQUIRED): EIA-canonical (f.eks. ``"WCESTUS1"`` for crude,
            ``"WGTSTUS1"`` for gasoline, ``"NW2_EPG0_SWO_R48_BCF"`` for
            nat-gas). Kommer fra YAML-wiring.
        lookback_weeks: rolling-vindu (default 52).
        invert: ``True`` (default) — høy stock-build = bearish. Sett
            ``False`` hvis brukt for kontrarian-tolkning.
        z_thresholds: optional override av step-mapping.

    Returnerer:
    - 1.0 ved sterk uventet stock-draw (z ≥ +2 etter invertering)
    - 0.5 ved typisk WoW-endring
    - 0.0 ved sterk uventet stock-build

    Defensiv: alle feil → 0.0 + log.
    """
    from bedrock.engine.drivers._stats import MIN_OBS_FOR_PCTILE, rolling_z

    series_id = params.get("series_id")
    if not series_id:
        _log.warning("eia_stock_change.no_series_id", instrument=instrument)
        return 0.0

    lookback = int(params.get("lookback_weeks", 52))
    invert = bool(params.get("invert", True))

    try:
        df = store.get_eia_inventory(series_id, last_n=lookback + 2)
    except KeyError:
        _log.debug(
            "eia_stock_change.data_missing",
            instrument=instrument,
            series_id=series_id,
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "eia_stock_change.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    values = pd.Series(pd.to_numeric(df["value"], errors="coerce")).dropna()
    if len(values) < MIN_OBS_FOR_PCTILE + 2:
        _log.debug(
            "eia_stock_change.short_history",
            instrument=instrument,
            n=len(values),
            required=MIN_OBS_FOR_PCTILE + 2,
        )
        return 0.0

    # WoW % endring (første rad blir NaN → drop)
    wow_pct = values.pct_change().dropna() * 100.0
    if len(wow_pct) < MIN_OBS_FOR_PCTILE + 1:
        return 0.0

    current = float(wow_pct.iloc[-1])
    history = [float(v) for v in wow_pct.iloc[:-1]]

    z = rolling_z(current, history)
    if z is None:
        return 0.0

    if invert:
        z = -z

    user_thresholds = params.get("z_thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_EIA_Z_THRESHOLDS
    else:
        if isinstance(user_thresholds, dict):
            steps_list: list[tuple[float, float]] = []
            for k, v in user_thresholds.items():
                key_str = str(k).replace("+", "")
                steps_list.append((float(key_str), float(v)))
            steps = tuple(sorted(steps_list, key=lambda t: -t[0]))
        else:
            steps = tuple(user_thresholds)

    for threshold, score in steps:
        if z >= threshold:
            return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# comex_stress (sub-fase 12.5+ session 108)
# ---------------------------------------------------------------------------


@register("comex_stress")
def comex_stress(store: Any, instrument: str, params: dict) -> float:
    """COMEX warehouse-stress score (0..1) for metals.

    Port av cot-explorer's `fetch_comex.py` `stress()`-funksjon (skala
    konvertert fra 0..100 → 0..1).

    Logikk:
        coverage = registered / total
        base = (1 - coverage) * 0.80
        + 0.15  hvis WoW%-endring < -5%  (registered faller raskt = stress)
        + 0.05  hvis WoW%-endring < 0%
        - 0.05  hvis WoW%-endring > +5%

    Tolkning: høy stress = supply tight = bullish for prising
    (få oz klare til delivery vs futures-shorts → squeeze-risk).
    Low stress = supply rikelig = bearish.

    Params:
        metal (REQUIRED): "gold" | "silver" | "copper" — bedrock-canonical.
            Kommer fra YAML-wiring.
        wow_window: antall handelsdager som teller som "uke" for WoW-
            sammenligning (default 5).
        copper_handling: hvis ``"skip"`` (default) returner 0.5 (nøytral)
            for kobber siden CME har fjernet reg/elig-skillet og
            coverage-baseberegningen ikke gir mening. ``"trend_only"``
            ignorerer base, bruker bare WoW-bonusene.

    Returnerer:
        float i [0, 1]. 0.5 ved tomt history. Defensive 0.0 ved feil.
    """
    metal = params.get("metal")
    if not metal:
        _log.warning("comex_stress.no_metal_param", instrument=instrument)
        return 0.0

    wow_window = int(params.get("wow_window", 5))
    copper_handling = str(params.get("copper_handling", "skip"))

    try:
        df = store.get_comex_inventory(metal, last_n=wow_window + 5)
    except KeyError:
        _log.debug("comex_stress.data_missing", instrument=instrument, metal=metal)
        return 0.0
    except Exception as exc:
        _log.warning(
            "comex_stress.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    if len(df) == 0:
        return 0.5

    last = df.iloc[-1]
    registered = float(last["registered"])
    total = float(last["total"])

    is_copper = metal == "copper"

    # Kobber: CME har fjernet reg/elig-skillet → coverage-base meningsløs.
    if is_copper and copper_handling == "skip":
        score = 0.5  # nøytral start
    else:
        if total <= 0:
            return 0.5
        coverage = registered / total
        # Klamrer til [0, 1] for å håndtere edge-cases der reg > total
        coverage = max(0.0, min(1.0, coverage))
        score = (1.0 - coverage) * 0.80

    # WoW-bonus: hvis det finnes en rad ~wow_window dager tilbake.
    if len(df) > wow_window:
        prev_reg = float(df.iloc[-1 - wow_window]["registered"])
        if prev_reg > 0:
            chg_pct = (registered - prev_reg) / prev_reg
            if chg_pct < -0.05:
                score += 0.15
            elif chg_pct < 0:
                score += 0.05
            elif chg_pct > 0.05:
                score -= 0.05

    return max(0.0, min(1.0, round(score, 4)))


# ---------------------------------------------------------------------------
# mining_disruption (sub-fase 12.5+ session 109)
# ---------------------------------------------------------------------------

# Per-metall mapping fra mining-region-navn (cot-explorer-canonical) til
# global produksjonsandel. Vekt brukes til weighted score-aggregat:
# events i regioner med høyere produksjonsandel veier mer. Tall basert på
# 2024 USGS Mineral Commodity Summaries.
_REGION_WEIGHTS_BY_METAL: dict[str, dict[str, float]] = {
    "gold": {
        "Kina (Mongolia / Kina)": 0.10,
        "Mongolia / Kina": 0.10,
        "Australia": 0.10,
        "USA / Canada": 0.10,
        "Russland / Sibir": 0.09,
        "Sør-Afrika": 0.05,
        "Chile / Peru": 0.10,
        "Mexico / Mellom-Amerika": 0.04,
        "DRC / Zambia": 0.02,
        "Indonesia / Papua": 0.05,
        "Øst-Afrika": 0.06,  # Tanzania, Ghana etc.
    },
    "silver": {
        "Mexico / Mellom-Amerika": 0.23,
        "Chile / Peru": 0.18,
        "Mongolia / Kina": 0.13,
        "Russland / Sibir": 0.05,
        "Australia": 0.05,
        "USA / Canada": 0.06,
    },
    "copper": {
        "Chile / Peru": 0.40,  # Chile + Peru = ~40% global
        "DRC / Zambia": 0.15,
        "Mongolia / Kina": 0.10,
        "USA / Canada": 0.07,
        "Indonesia / Papua": 0.05,
        "Australia": 0.04,
        "Russland / Sibir": 0.04,
    },
    "platinum": {
        "Sør-Afrika": 0.70,  # Bushveld Complex — kritisk!
        "Russland / Sibir": 0.10,
        "USA / Canada": 0.04,
    },
}


@register("mining_disruption")
def mining_disruption(store: Any, instrument: str, params: dict) -> float:
    """Mining-disruption score (0..1) basert på USGS-events i mining-regioner.

    Logikk:
      For hver event i lookback-vinduet (default 7 dager) i en region som
      har vekt for `metal`:
        impact = max(0, magnitude - 4.5) / 3.0   # 4.5 → 0, 7.5 → 1
        weighted_impact = impact * region_weight

      score = clip(sum(weighted_impacts), 0, 1)

    Tolkning: høyere score = supply-disruption-risk = bullish for prising
    av det metallet (gruver kan stenge i flere uker etter alvorlige skjelv).

    Params:
        metal (REQUIRED): "gold" | "silver" | "copper" | "platinum".
            Bestemmer region-vektene.
        lookback_days: vindu i antall dager (default 7).
        min_magnitude: filtrer events under denne (default 4.5 — matcher
            USGS-feed-grense).
        regions: optional override av default region-vekter for metallet.

    Returnerer 0..1. Defensive 0.0 ved manglende metal/data/exception.
    """
    metal = params.get("metal")
    if not metal:
        _log.warning("mining_disruption.no_metal_param", instrument=instrument)
        return 0.0

    lookback_days = int(params.get("lookback_days", 7))
    min_magnitude = float(params.get("min_magnitude", 4.5))

    custom_regions = params.get("regions")
    if isinstance(custom_regions, dict):
        region_weights = {str(k): float(v) for k, v in custom_regions.items()}
    else:
        region_weights = _REGION_WEIGHTS_BY_METAL.get(str(metal).lower())
        if not region_weights:
            _log.warning("mining_disruption.unknown_metal", instrument=instrument, metal=metal)
            return 0.0

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    regions = list(region_weights.keys())

    try:
        df = store.get_seismic_events(regions=regions, from_ts=cutoff, min_magnitude=min_magnitude)
    except Exception as exc:
        _log.warning(
            "mining_disruption.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    if df.empty:
        return 0.0

    score = 0.0
    for _, row in df.iterrows():
        region = str(row["region"])
        weight = region_weights.get(region, 0.0)
        if weight <= 0:
            continue
        magnitude = float(row["magnitude"])
        # M4.5 → 0.0, M7.5 → 1.0 (lineært)
        impact = max(0.0, (magnitude - 4.5) / 3.0)
        score += impact * weight

    return max(0.0, min(1.0, round(score, 4)))


__all__ = [
    "comex_stress",
    "dxy_chg5d",
    "eia_stock_change",
    "mining_disruption",
    "real_yield",
    "vix_regime",
]
