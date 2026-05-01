"""Felles helpers for horisont-bevisste R4-drivere.

Sub-fase 12.7 D1 (session 127). Samler de delte mode-helpers som ble
generalisert i sessions 123-125 fra real_yield-spesifikke til generiske
fundamentals-helpers. Tidligere lå de i ``macro.py`` med underscore-
prefiks og ble lazy-importert fra ``agronomy.py`` (shipping_pressure).

Modulen eksporterer publiske funksjoner uten underscore-prefiks (de er
nå modul-API, ikke private). Konstantene er fortsatt med ``_``-prefiks
for å markere at de er modul-interne defaults — drivere overstyrer via
egen lookback-param.

Brukere:
- ``macro.real_yield`` (R3)
- ``macro.dxy_chg5d`` (R4 session 123)
- ``macro.brl_chg5d`` (R4 session 123)
- ``macro.vix_regime`` (R4 session 123)
- ``macro.eia_stock_change`` (R4 session 124)
- ``agronomy.shipping_pressure`` (R4 session 125)

NB: ``positioning.py`` har sin egen ``_extreme_flag`` med identisk
implementasjon. Konsolidering av den til ``extreme_flag`` her er
utsatt — positioning's helpers er COT-ukentlig-spesifikke og krever
egen refactor-syklus.
"""

from __future__ import annotations

import logging

import pandas as pd

from bedrock.engine.drivers._stats import (
    MIN_OBS_FOR_PCTILE,
    rank_percentile,
    rolling_z,
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frekvens-spesifikke vinduer
# ---------------------------------------------------------------------------

# Daglige FRED-serier: 252 trading-days ≈ 12m, 756 ≈ 36m.
LOOKBACK_PCT_12M_DAILY = 252
LOOKBACK_PCT_36M_DAILY = 756
DELTA_5D_DAYS = 5
DELTA_20D_DAYS = 20
LOOKBACK_DELTA_DAILY = 252  # historikk-obs av diff-serien

# Ukentlige FRED/EIA-serier: 52 uker ≈ 12m, 156 uker ≈ 36m.
# delta_5d_z på ukentlig data tolkes som "1-rapport-delta" (~7d natural,
# samme presedens som positioning's COT-delta i positioning.py).
# delta_20d_z = "4-rapport-delta" (~28d natural).
LOOKBACK_PCT_12M_WEEKLY = 52
LOOKBACK_PCT_36M_WEEKLY = 156
DELTA_5D_WEEKS = 1
DELTA_20D_WEEKS = 4
LOOKBACK_DELTA_WEEKLY = 52


# ---------------------------------------------------------------------------
# Extreme-flag-tersklene (PLAN § 19.3 låst)
# ---------------------------------------------------------------------------

EXTREME_HARD_HI = 0.98
EXTREME_HARD_LO = 0.02
EXTREME_SOFT_HI = 0.95
EXTREME_SOFT_LO = 0.05


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def z_to_score_with_bull_when(z: float, bull_when: str) -> float:
    """Map z-score til [0..1] via momentum-trapp, bull_when-aware.

    bull_when="high": positiv z = bull-of-instrument ⇒ standard trapp.
    bull_when="low":  negativ z = bull-of-instrument ⇒ inverter z først.

    Trappen følger _DEFAULT_Z_THRESHOLDS-konvensjonen i positioning.py
    (z≥2→1.0, ...) for konsistens på tvers av drivere.
    """
    z_oriented = -z if bull_when == "low" else z
    if z_oriented >= 2.0:
        return 1.0
    if z_oriented >= 1.0:
        return 0.75
    if z_oriented >= 0.5:
        return 0.6
    if z_oriented >= 0.0:
        return 0.5
    if z_oriented >= -0.5:
        return 0.3
    return 0.0


def extreme_flag(pct_0_to_1: float, *, hard: bool) -> float:
    """Returner 1.0 hvis pct er ekstrem, ellers 0.0.

    Symmetrisk i begge ender — bull_when-agnostisk per pattern-doc § 1.1.

    hard=True: 0.98/0.02-tersklene (extreme_flag_hard).
    hard=False: 0.95/0.05-tersklene (extreme_flag_soft).
    """
    hi = EXTREME_HARD_HI if hard else EXTREME_SOFT_HI
    lo = EXTREME_HARD_LO if hard else EXTREME_SOFT_LO
    if pct_0_to_1 >= hi or pct_0_to_1 <= lo:
        return 1.0
    return 0.0


def normalize_bull_when_for_chg(bull_when: str) -> str:
    """Oversett dxy/brl chg-driver-konvensjon til generic helper-konvensjon.

    chg-drivere bruker ``bull_when="negative"`` (negativ endring = bull) og
    ``"positive"`` (positiv endring = bull). Helper-konvensjonen er
    ``"low"`` / ``"high"``.
    """
    if bull_when == "negative":
        return "low"
    if bull_when == "positive":
        return "high"
    return bull_when


def fundamentals_pct_score(
    series: pd.Series, bull_when: str, lookback: int, instrument: str
) -> float | None:
    """Rank-percentile av current mot siste `lookback` obs, bull_when-aware.

    Generisk helper for FRED/Yahoo/EIA-baserte tids-serier.

    bull_when="low":  score = 1 - rank/100 (lav rank ⇒ høy score)
    bull_when="high"/andre: score = rank/100. Caller normaliserer
        chg-driver-konvensjonen via ``normalize_bull_when_for_chg``.
    """
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        _log.debug(
            "fundamentals.short_history_for_pct",
            extra={"instrument": instrument, "n": len(series), "required": MIN_OBS_FOR_PCTILE + 1},
        )
        return None
    window = series.iloc[-(lookback + 1) :] if len(series) > lookback else series
    if len(window) < MIN_OBS_FOR_PCTILE + 1:
        return None
    current = float(window.iloc[-1])
    history = [float(v) for v in window.iloc[:-1]]
    pct = rank_percentile(current, history)
    if pct is None:
        return None
    pct_0_1 = pct / 100.0
    return 1.0 - pct_0_1 if bull_when == "low" else pct_0_1


def fundamentals_delta_score(
    series: pd.Series,
    bull_when: str,
    *,
    delta_days: int,
    lookback: int,
    instrument: str,
) -> float | None:
    """Z-score av N-trading-days-delta, bull_when-aware.

    Generisk helper for daglig + ukentlig FRED/EIA/Yahoo-data.
    delta_days=5 ⇒ "delta_5d_z" på daglig, eller "1-rapport-delta" (~7d
    natural) på ukentlig. delta_days=20 ⇒ "delta_20d_z".
    """
    required = delta_days + lookback + 1
    if len(series) < required:
        _log.debug(
            "fundamentals.short_history_for_delta",
            extra={
                "instrument": instrument,
                "delta_days": delta_days,
                "n": len(series),
                "required": required,
            },
        )
        return None

    diff_series = series.diff(periods=delta_days).dropna()
    if len(diff_series) < MIN_OBS_FOR_PCTILE + 1:
        return None

    _log.debug(
        "fundamentals.delta_z_natural_translation",
        extra={
            "instrument": instrument,
            "delta_days": delta_days,
            "natural_days": delta_days,
            "note": "delta interpreted as N-period-delta",
        },
    )

    current_diff = float(diff_series.iloc[-1])
    history_diff = [float(v) for v in diff_series.iloc[-(lookback + 1) : -1]]
    z = rolling_z(current_diff, history_diff)
    if z is None:
        return None
    return z_to_score_with_bull_when(z, bull_when)


def fundamentals_extreme_flag(
    series: pd.Series, *, hard: bool, lookback: int, instrument: str
) -> float | None:
    """Beregn extreme_flag på rank-percentile av current vs `lookback`-obs.

    Symmetrisk i begge ender — bull_when-agnostisk per § 1.1.
    Returnerer None hvis utilstrekkelig historikk slik at caller kan
    rapportere 0.0.
    """
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        return None
    window = series.iloc[-(lookback + 1) :] if len(series) > lookback else series
    if len(window) < MIN_OBS_FOR_PCTILE + 1:
        return None
    current = float(window.iloc[-1])
    history = [float(v) for v in window.iloc[:-1]]
    pct = rank_percentile(current, history)
    if pct is None:
        _log.debug("fundamentals.short_history_for_extreme", extra={"instrument": instrument})
        return None
    return extreme_flag(pct / 100.0, hard=hard)


__all__ = [
    "DELTA_5D_DAYS",
    "DELTA_5D_WEEKS",
    "DELTA_20D_DAYS",
    "DELTA_20D_WEEKS",
    "EXTREME_HARD_HI",
    "EXTREME_HARD_LO",
    "EXTREME_SOFT_HI",
    "EXTREME_SOFT_LO",
    "LOOKBACK_DELTA_DAILY",
    "LOOKBACK_DELTA_WEEKLY",
    "LOOKBACK_PCT_12M_DAILY",
    "LOOKBACK_PCT_12M_WEEKLY",
    "LOOKBACK_PCT_36M_DAILY",
    "LOOKBACK_PCT_36M_WEEKLY",
    "extreme_flag",
    "fundamentals_delta_score",
    "fundamentals_extreme_flag",
    "fundamentals_pct_score",
    "normalize_bull_when_for_chg",
    "z_to_score_with_bull_when",
]
