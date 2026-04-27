# pyright: reportReturnType=false
# pandas-stubs typer pd.concat([...], axis=1).max(axis=1) som Union;
# i praksis Series.

"""Risk-familie drivere.

`vol_regime` (Block A polish, session 79):
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

`event_distance` (sub-fase 12.5+ session 105):
    Hvor "trygt" er det å åpne posisjon basert på avstand til neste
    high-impact-event på Forex Factory-kalenderen. 1.0 = ingen events
    innenfor `min_hours`; 0.0 = event akkurat nå. Linær mellom.

    Brukes som risk-gate i scoring: høy event-nærhet → lav score →
    redusert appetitt for nye posisjoner. Driver er retningsnøytral
    (samme score for BUY og SELL — events skaper toveis-volatilitet).

    Defensive: ingen kalender-data → 0.5 (neutral) i stedet for 0.0
    eller 1.0 — hverken false-safe eller false-block ved tom DB.
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
    except KeyError as exc:
        _log.debug(
            "vol_regime.prices_unavailable",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "vol_regime.prices_fetch_failed",
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


_DEFAULT_EVENT_MIN_HOURS = 4.0
_DEFAULT_EVENT_IMPACT_LEVELS = ("High",)
_DEFAULT_EVENT_COUNTRIES = ("USD",)
_DEFAULT_EVENT_NEUTRAL_ON_EMPTY = 0.5


@register("event_distance")
def event_distance(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 for tids-buffer til neste high-impact event.

    Score-logikk:
    - Ingen relevant event innenfor (now, now+lookahead_hours) → 1.0
    - Event akkurat nå (h2e=0) → 0.0
    - Event på h2e ∈ (0, min_hours) → linear h2e/min_hours
    - Event på h2e > min_hours → 1.0 (langt unna)

    Params:
        min_hours: tids-buffer der score ramper 0→1 (default 4.0)
        lookahead_hours: hvor langt fram driveren ser (default 24)
        impact_levels: list av impact-strenger som teller (default ["High"])
        countries: list av valuta-kodes som er relevante (default ["USD"])
        empty_score: score når ingen events i window (default 1.0; trygt)
        error_score: score ved exception/missing-data (default 0.5; neutral)

    Returns:
        Score 0..1. Retning-nøytral (samme verdi for BUY og SELL).
    """
    min_hours = float(params.get("min_hours", _DEFAULT_EVENT_MIN_HOURS))
    lookahead = float(params.get("lookahead_hours", 24.0))
    impact_levels = tuple(params.get("impact_levels", _DEFAULT_EVENT_IMPACT_LEVELS))
    countries = tuple(params.get("countries", _DEFAULT_EVENT_COUNTRIES))
    empty_score = float(params.get("empty_score", 1.0))
    error_score = float(params.get("error_score", _DEFAULT_EVENT_NEUTRAL_ON_EMPTY))

    if min_hours <= 0:
        _log.warning("event_distance.bad_min_hours", min_hours=min_hours)
        return error_score

    # Tillat injeksjon av "nå" for testing via params (ikke YAML-eksponert).
    now_ts = params.get("_now")
    if now_ts is None:
        from datetime import datetime, timezone

        now_ts = datetime.now(timezone.utc)
    elif isinstance(now_ts, str):
        now_ts = pd.to_datetime(now_ts, utc=True).to_pydatetime()

    # Store skriver event_ts som "%Y-%m-%dT%H:%M:%S" (SQLite TEXT, ingen TZ).
    # SQL-query må matche samme format for korrekt streng-sammenligning.
    from_ts_query = now_ts.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        df = store.get_econ_events(
            countries=list(countries),
            impact_levels=list(impact_levels),
            from_ts=from_ts_query,
        )
    except Exception as exc:
        _log.warning(
            "event_distance.store_unavailable",
            instrument=instrument,
            error=str(exc),
        )
        return error_score

    if df is None or df.empty:
        return empty_score

    # df["event_ts"] er tz-aware UTC. Nå er også UTC. Diff i timer.
    try:
        diffs = (df["event_ts"] - pd.Timestamp(now_ts)).dt.total_seconds() / 3600.0
    except Exception as exc:
        _log.warning(
            "event_distance.diff_failed",
            instrument=instrument,
            error=str(exc),
        )
        return error_score

    # Hold kun events som er framover i tid (>= 0 timer).
    forward = diffs[diffs >= 0.0]
    if forward.empty:
        return empty_score

    # Hold events innenfor lookahead-vinduet — events lenger fram enn
    # lookahead påvirker ikke score (trygt-default).
    in_window = forward[forward <= lookahead]
    if in_window.empty:
        return empty_score

    nearest_h2e = float(in_window.min())

    if nearest_h2e >= min_hours:
        return 1.0
    if nearest_h2e <= 0.0:
        return 0.0
    return max(0.0, min(1.0, nearest_h2e / min_hours))


__all__ = ["event_distance", "vol_regime"]
