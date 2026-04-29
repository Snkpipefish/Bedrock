"""Valutakryss-drivere.

Fase 6 session 31 — `currency_cross_trend`.

Cross-driver leser en ANNEN instrument (valutakrysset) fra store i
stedet for instrumentet som scorene. Hovedbruk: softs (sukker, kaffe)
scoret på brasiliansk eksportør-økonomi via BRL-styrke.

Mønster: `instrument`-argumentet ignoreres; driveren bruker
`params["source"]` som prisserie-ID. Dette lar samme driver brukes
for flere cross (BRL/USD for softs, CNY/USD for metaller etc.) uten
at vi trenger én driver per valutapar.

**Retning**: driveren er unidirectional bull — høyere score betyr
"bullish for instrumentet som scores". Caller MÅ velge cross med
riktig fortegn:

- For softs: bruk `BRLUSD` (BRL sterkt = high cross = bullish softs)
- Hvis kun `USDBRL` finnes: bruk `direction: invert` (flipper fortegn)

Feil i data-oppslag gir 0.0 + logg per driver-kontrakten.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)

_DEFAULT_LOOKBACK = 30


@register("currency_cross_trend")
def currency_cross_trend(store: Any, instrument: str, params: dict) -> float:
    """Score basert på prosentvis endring i en valuta-cross over lookback-vindu.

    Signatur følger standard driver-kontrakten. `instrument`-argumentet
    ignoreres — caller spesifiserer kilden via `params["source"]`.

    **R4 (sub-fase 12.7):** horisont-bevisst via ``params["mode"]`` per
    ADR-010. Default-output (mode=None) er bit-identisk pre-R4. Modes
    opererer på underliggende cross-rå-serien (ikke pct-change) —
    parallel til dxy_chg5d/brl_chg5d-pattern. Gjenbruker
    ``_fundamentals_*``-helpers fra macro.py.

    Params:
        source: instrument-ID for cross-serien (påkrevd)
        lookback: antall bars tilbake for default pct-beregning (default
            30). Modes overstyrer med _LOOKBACK_PCT_*_DAILY-konstanter.
        tf: timeframe (default "D1")
        direction: "direct" (default) eller "invert". "invert" flipper
            fortegn i default-banen. Oversettes til helper bull_when i
            mode-banen ("direct"→"high" siden høy cross = bull;
            "invert"→"low").
        mode: R4 feature-velger per ADR-010 (None/pct_12m/pct_36m/
            delta_5d_z/delta_20d_z/extreme_flag_*).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Beregning (default): pct = (close_now - close_lookback_ago) / close_lookback_ago.
    Hvis `direction=invert`, bruk -pct i mapping.

    Default-mapping (unidirectional bull):
    - pct >= +10% → 1.0; +5% → 0.8; +2% → 0.65; 0 → 0.5;
      -2% → 0.35; -5% → 0.2; < -5% → 0.0

    For kort historikk eller null pris gir 0.0.
    """
    # ADR-010: les _horizon for fremtidig bruk.
    _horizon = params.get("_horizon")
    source = params.get("source")
    if not source:
        _log.warning(
            "currency_cross_trend.missing_source",
            instrument=instrument,
        )
        return 0.0

    direction = params.get("direction", "direct")
    mode = params.get("mode")

    if mode is None:
        return _currency_cross_trend_default(store, instrument, str(source), direction, params)

    if direction not in ("direct", "invert"):
        _log.warning(
            "currency_cross_trend.unknown_direction",
            direction=direction,
            source=source,
        )
        return 0.0

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

    helper_bull_when = "low" if direction == "invert" else "high"
    tf = params.get("tf", "D1")

    try:
        prices = store.get_prices(source, tf=tf, lookback=_LOOKBACK_PCT_36M_DAILY + 10)
    except Exception as exc:
        _log.warning(
            "currency_cross_trend.prices_unavailable",
            source=source,
            tf=tf,
            error=str(exc),
        )
        return 0.0

    if mode == "pct_12m":
        result = _fundamentals_pct_score(
            prices, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, str(source)
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(
            prices, helper_bull_when, _LOOKBACK_PCT_36M_DAILY, str(source)
        )
        if result is None:
            _log.info(
                "currency_cross_trend.pct_36m_fallback_to_12m",
                source=source,
                available_obs=len(prices),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(
                prices, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, str(source)
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            prices,
            helper_bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=str(source),
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            prices,
            helper_bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=str(source),
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            prices,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=str(source),
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "currency_cross_trend.unknown_mode_falling_back_to_default",
        source=source,
        mode=mode,
    )
    return _currency_cross_trend_default(store, instrument, str(source), direction, params)


def _currency_cross_trend_default(
    store: Any, instrument: str, source: str, direction: str, params: dict
) -> float:
    """Pre-R4-default-bane: pct-change-trapp på cross-prices."""
    lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
    tf = params.get("tf", "D1")

    try:
        prices = store.get_prices(source, tf=tf, lookback=lookback + 50)
    except Exception as exc:
        _log.warning(
            "currency_cross_trend.prices_unavailable",
            source=source,
            tf=tf,
            error=str(exc),
        )
        return 0.0

    if len(prices) < lookback + 1:
        _log.debug(
            "currency_cross_trend.short_history",
            source=source,
            tf=tf,
            bars=len(prices),
            required=lookback + 1,
        )
        return 0.0

    close_now = prices.iloc[-1]
    close_then = prices.iloc[-(lookback + 1)]

    if math.isnan(close_now) or math.isnan(close_then) or close_then == 0.0:
        return 0.0

    pct = (close_now - close_then) / close_then
    if direction == "invert":
        pct = -pct
    elif direction != "direct":
        _log.warning(
            "currency_cross_trend.unknown_direction",
            direction=direction,
            source=source,
        )
        return 0.0

    if pct >= 0.10:
        return 1.0
    if pct >= 0.05:
        return 0.8
    if pct >= 0.02:
        return 0.65
    if pct >= 0.0:
        return 0.5
    if pct >= -0.02:
        return 0.35
    if pct >= -0.05:
        return 0.2
    return 0.0
