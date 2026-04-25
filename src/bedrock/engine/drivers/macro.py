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
        _log.warning(
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
        _log.warning("dxy_chg5d.series_missing", instrument=instrument, series=series_id)
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
        _log.warning("vix_regime.series_missing", instrument=instrument, series=series_id)
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


__all__ = ["dxy_chg5d", "real_yield", "vix_regime"]
