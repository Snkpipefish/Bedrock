# pyright: reportReturnType=false
# pandas-stubs typer pd.concat([...], axis=1).max(axis=1) som Union;
# i praksis Series.

"""Risk-familie drivere (Block A polish, session 79).

Erstatter ``sma200_align``-placeholder i Gold risk-familien.

`vol_regime`:
    Volatilitets-regime basert på ATR(14)-percentil over et lengre
    lookback-vindu (default 252 dager = ~1 år handelsdager). Lav
    score = lav vol = "compressed" / breakout-setup; høy score =
    høy vol = "trade-friendly" miljø for risiko-bevisst posisjons-
    størrelse.

    Tolkning er asymmetri-relevant:
    - For trend-followers: høy vol = bull (lett å entre/ta gevinst)
    - For mean-reverters: lav vol = bull (kompresjon før eksplosjon)

    Default `mode=high_is_bull` (trend-tolkning). Bytte med
    `mode=low_is_bull` for mean-reversion-tolkning.

ATR (Wilder-style EMA av true range) er finansbransjens standard
for volatilitet på OHLCV-data. Krever high/low/close — bruker
``store.get_prices_ohlc``.

Defensive: kort historikk gir 0.0.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)

_DEFAULT_ATR_PERIOD = 14
_DEFAULT_LOOKBACK = 252


def _wilder_atr(ohlc: pd.DataFrame, period: int) -> pd.Series:
    """Wilder-style ATR (EMA av True Range med alpha=1/period).

    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    Wilder smoothing er ekvivalent med EMA med alpha = 1/period.
    """
    high = ohlc["high"].astype("float64")
    low = ohlc["low"].astype("float64")
    close = ohlc["close"].astype("float64")
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


@register("vol_regime")
def vol_regime(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 basert på ATR-percentil over lookback-vindu.

    Params:
        period: ATR-perioden (default 14).
        lookback: antall bars i percentil-vinduet (default 252).
        tf: timeframe (default "D1").
        mode: "high_is_bull" (default) eller "low_is_bull".
            high_is_bull: høy vol-percentil → høy score (trend-følger).
            low_is_bull: lav vol-percentil → høy score (mean-revert).

    Returns:
        Score 0..1. 0.0 ved kort historikk eller udefinert ATR.
    """
    period = int(params.get("period", _DEFAULT_ATR_PERIOD))
    lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
    tf = params.get("tf", "D1")
    mode = str(params.get("mode", "high_is_bull")).lower()

    try:
        ohlc = store.get_prices_ohlc(instrument, tf=tf, lookback=lookback + period + 10)
    except Exception as exc:
        _log.warning(
            "vol_regime.prices_unavailable",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return 0.0

    if len(ohlc) < period + 1:
        _log.debug(
            "vol_regime.short_history",
            instrument=instrument,
            bars=len(ohlc),
            required=period + 1,
        )
        return 0.0

    atr_series = _wilder_atr(ohlc, period)
    if atr_series.empty or atr_series.dropna().empty:
        return 0.0

    # Percentil-vindu: bruk siste min(lookback, len)-elementer.
    window_len = min(lookback, len(atr_series))
    window = atr_series.tail(window_len).dropna()
    if len(window) < 2:
        return 0.0

    current = float(window.iloc[-1])
    rank = float((window < current).sum()) / float(len(window) - 1)
    rank = max(0.0, min(1.0, rank))

    if mode == "low_is_bull":
        return 1.0 - rank
    return rank


__all__ = ["vol_regime"]
