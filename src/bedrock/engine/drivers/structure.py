"""Structure-familie drivere (Block A polish, session 79).

Erstatter ``sma200_align``-placeholder i Gold structure-familien
(og kan brukes for andre instrumenter senere).

`range_position`:
    Hvor i siste N-dagers high/low-range befinner prisen seg?
    Score 0..1 = (close - low_n) / (high_n - low_n).

    Tolkning (unidirectional bull):
    - 1.0 (på/nær top): trend-fortsettelse opp, breakout-potensial
    - 0.5 (midt-i): tvetydig — venter på retning
    - 0.0 (på/nær bunn): mean-reversion-potensial OPP, men kan
      også være trend-fortsettelse ned. Per asymmetri-prinsippet
      tolkes lav range_position som lav bull-confidence.

    Med `mode=mean_revert`-param flippes tolkningen: lav score blir
    bullish (kjøpsignal nær bunn av range). Default er
    `mode=continuation` — høy score er bull.

Defensive: kort historikk eller flatt range (high == low) gir 0.0.
"""

from __future__ import annotations

from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)

_DEFAULT_WINDOW = 20


@register("range_position")
def range_position(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 basert på prisens posisjon i N-dagers high/low-range.

    Params:
        window: antall bars i lookback (default 20).
        tf: timeframe (default "D1").
        mode: "continuation" (default) eller "mean_revert".
            continuation: høy score = nær top = bull (trend-fortsettelse).
            mean_revert: høy score = nær bunn = bull (oversold-bounce).

    Returns:
        Score 0..1. 0.0 ved kort historikk eller flatt range.
    """
    window = int(params.get("window", _DEFAULT_WINDOW))
    tf = params.get("tf", "D1")
    mode = str(params.get("mode", "continuation")).lower()

    try:
        ohlc = store.get_prices_ohlc(instrument, tf=tf, lookback=window + 5)
    except KeyError as exc:
        _log.debug(
            "range_position.prices_unavailable",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "range_position.prices_fetch_failed",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return 0.0

    if len(ohlc) < window:
        _log.debug(
            "range_position.short_history",
            instrument=instrument,
            bars=len(ohlc),
            required=window,
        )
        return 0.0

    tail = ohlc.tail(window)
    high_n = float(tail["high"].max())
    low_n = float(tail["low"].min())
    close = float(ohlc["close"].iloc[-1])

    if high_n <= low_n:
        return 0.0

    raw = (close - low_n) / (high_n - low_n)
    raw = max(0.0, min(1.0, raw))

    if mode == "mean_revert":
        return 1.0 - raw
    return raw


__all__ = ["range_position"]
