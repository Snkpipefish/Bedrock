"""Trend-familie drivere.

Fase 1 session 4 — to første ekte drivere:

- `sma200_align`: posisjon relativt til 200-dag SMA på gitt TF
- `momentum_z`: z-score av nåpris vs rolling mean/std over et vindu

Begge returnerer 0.0..1.0 per driver-kontrakt (unidirectional bull-variant).
En dedikert bear-variant eller bi-direksjonal versjon kan legges til senere
når setup-generator ber om det.

Drivere er defensive: feil i data-oppslag eller for kort historikk gir 0.0
og logger (ikke unntak) — prinsipp fra driver-kontrakten i `drivers/__init__.py`.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# sma200_align
# ---------------------------------------------------------------------------

_SMA_WINDOW = 200


@register("sma200_align")
def sma200_align(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 for hvor komfortabelt over SMA200 prisen ligger.

    Terskler (empiriske, samme som PLAN § 4.4-eksemplet):
    - close > SMA × 1.01 -> 1.0 (klar trend-bekreftelse)
    - close > SMA        -> 0.6 (så vidt over, svak trend)
    - close > SMA × 0.99 -> 0.4 (innenfor ±1 %, tvetydig)
    - close <= SMA × 0.99 -> 0.0 (under, ingen bull-bekreftelse)

    Params:
        tf: timeframe for pris-oppslag (default "D1")

    Korte serier (< 200 bars) gir 0.0 — SMA er udefinert.
    """
    tf = params.get("tf", "D1")
    try:
        prices = store.get_prices(instrument, tf=tf, lookback=_SMA_WINDOW + 50)
    except Exception as exc:
        _log.warning(
            "sma200_align.prices_unavailable", instrument=instrument, tf=tf, error=str(exc)
        )
        return 0.0

    if len(prices) < _SMA_WINDOW:
        _log.debug(
            "sma200_align.short_history",
            instrument=instrument,
            tf=tf,
            bars=len(prices),
            required=_SMA_WINDOW,
        )
        return 0.0

    sma = prices.rolling(_SMA_WINDOW).mean().iloc[-1]
    close = prices.iloc[-1]

    if math.isnan(sma) or math.isnan(close):
        return 0.0

    if close > sma * 1.01:
        return 1.0
    if close > sma:
        return 0.6
    if close > sma * 0.99:
        return 0.4
    return 0.0


# ---------------------------------------------------------------------------
# momentum_z
# ---------------------------------------------------------------------------

_DEFAULT_WINDOW = 20


@register("momentum_z")
def momentum_z(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 basert på z-score av close vs rolling mean/std.

    z = (close - rolling_mean(window)) / rolling_std(window)

    Mapping (unidirectional bull):
    - z >= 2.0 -> 1.0 (klar outperformance vs baseline)
    - z >= 1.0 -> 0.75
    - z >= 0.5 -> 0.6
    - z >= 0.0 -> 0.5 (over gjennomsnitt)
    - z >= -0.5 -> 0.3
    - z < -0.5  -> 0.0 (under gjennomsnitt, ingen bull)

    Params:
        window: rolling-vindu for mean/std (default 20)
        tf: timeframe (default "D1")

    For kort historikk (< window + 1 bars) eller std == 0 gir 0.0.
    """
    window = int(params.get("window", _DEFAULT_WINDOW))
    tf = params.get("tf", "D1")

    try:
        prices = store.get_prices(instrument, tf=tf, lookback=window + 50)
    except Exception as exc:
        _log.warning("momentum_z.prices_unavailable", instrument=instrument, tf=tf, error=str(exc))
        return 0.0

    if len(prices) < window + 1:
        return 0.0

    rolling = prices.rolling(window)
    mean = rolling.mean().iloc[-1]
    std = rolling.std(ddof=0).iloc[-1]
    close = prices.iloc[-1]

    if math.isnan(mean) or math.isnan(std) or std == 0.0:
        return 0.0

    z = (close - mean) / std

    if z >= 2.0:
        return 1.0
    if z >= 1.0:
        return 0.75
    if z >= 0.5:
        return 0.6
    if z >= 0.0:
        return 0.5
    if z >= -0.5:
        return 0.3
    return 0.0
