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

    Params:
        source: instrument-ID for cross-serien (påkrevd)
        lookback: antall bars tilbake for pct-beregning (default 30)
        tf: timeframe (default "D1")
        direction: "direct" (default) eller "invert". "invert" flipper
            fortegn — bruk når cross-retningen er motsatt av det
            instrumentet som scores trenger.

    Beregning: pct = (close_now - close_lookback_ago) / close_lookback_ago.
    Hvis `direction=invert`, bruk -pct i mapping.

    Mapping (unidirectional bull — høyere er bedre for scored instrument):
    - pct >= +10%  -> 1.0
    - pct >= +5%   -> 0.8
    - pct >= +2%   -> 0.65
    - pct >= 0%    -> 0.5   (flat)
    - pct >= -2%   -> 0.35
    - pct >= -5%   -> 0.2
    - pct < -5%    -> 0.0

    For kort historikk (< lookback + 1 bars) eller null pris gir 0.0.
    """
    source = params.get("source")
    if not source:
        _log.warning(
            "currency_cross_trend.missing_source",
            instrument=instrument,
        )
        return 0.0

    lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
    tf = params.get("tf", "D1")
    direction = params.get("direction", "direct")

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
