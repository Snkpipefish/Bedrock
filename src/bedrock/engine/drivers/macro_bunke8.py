"""Sub-fase 12.10 Bunke 8 — Treasury + USGS + sluttspill.

Per § 22.2 #27-#29.

#27 Treasury auctions: DEFERRED (Treasury bid-to-cover, indirect-pct,
    quarterly refunding krever ny Treasury-auction-fetcher; ingen data
    p.t. i bedrock.db).

#28 USGS seismic (2 av 2):
- seismic_m6_global_24h: count av M≥6 events globalt siste 24h
- seismic_chile_peru_copper: M≥5.5 events i Chile/Peru-regioner

#29 crypto_sentiment_extreme: DEFERRED per spec ("vent til 100+ rader,
    ~juli 2026"). P.t. 39 rader; re-vurderes etter mer akkumulering.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# #28 USGS seismic
# ---------------------------------------------------------------------------


@register("seismic_m6_global_24h")
def seismic_m6_global_24h(store: Any, instrument: str, params: dict) -> float:
    """Count av M ≥ 6 jordskjelv globalt siste N timer (default 24).

    Tolkning: en M≥6 globalt utløser typisk safe-haven-flow til gull /
    treasury-rally. Default bull_when='high' = mer M6-events = bull
    (for safe-haven-instrumenter). Override for risk-on-instrumenter.

    Score:
    - 0 events → 0.0 (ingen safe-haven-trigger)
    - 1 event → 0.5 (mild safe-haven)
    - ≥ 2 events → 1.0 (clustering, tydelig haven-bid)
    """
    _ = params.get("_horizon")
    from datetime import datetime, timedelta, timezone

    bull_when = str(params.get("bull_when", "high")).lower()
    lookback_hours = float(params.get("lookback_hours", 24.0))
    min_magnitude = float(params.get("min_magnitude", 6.0))

    now_ts = params.get("_now")
    if now_ts is None:
        now_ts = datetime.now(timezone.utc)
    elif isinstance(now_ts, str):
        now_ts = pd.to_datetime(now_ts, utc=True).to_pydatetime()

    from_ts_dt = now_ts - timedelta(hours=lookback_hours)

    try:
        df = store.get_seismic_events(from_ts=from_ts_dt, min_magnitude=min_magnitude)
    except Exception as exc:
        _log.warning("seismic_m6.fetch_failed", instrument=instrument, error=str(exc))
        return 0.5

    if df is None or df.empty:
        score = 0.0
    else:
        n = len(df)
        if n >= 2:
            score = 1.0
        elif n == 1:
            score = 0.5
        else:
            score = 0.0

    return score if bull_when == "high" else 1.0 - score


@register("seismic_chile_peru_copper")
def seismic_chile_peru_copper(store: Any, instrument: str, params: dict) -> float:
    """Count av M ≥ 5.5 jordskjelv i Chile/Peru-regioner siste N dager (default 7).

    Spesifisert for Copper (Chile/Peru ~40% global produksjon). Mining-
    disruption fra større skjelv → supply-stress → bull copper-prising.
    Default bull_when='high'.

    Score:
    - 0 events → 0.5 (baseline)
    - 1 event → 0.75
    - ≥ 2 events → 1.0
    """
    _ = params.get("_horizon")
    from datetime import datetime, timedelta, timezone

    bull_when = str(params.get("bull_when", "high")).lower()
    lookback_days = float(params.get("lookback_days", 7.0))
    min_magnitude = float(params.get("min_magnitude", 5.5))

    now_ts = params.get("_now")
    if now_ts is None:
        now_ts = datetime.now(timezone.utc)
    elif isinstance(now_ts, str):
        now_ts = pd.to_datetime(now_ts, utc=True).to_pydatetime()

    from_ts_dt = now_ts - timedelta(days=lookback_days)

    try:
        df = store.get_seismic_events(
            from_ts=from_ts_dt,
            min_magnitude=min_magnitude,
            region="Chile / Peru",
        )
    except Exception as exc:
        _log.warning(
            "seismic_chile_peru.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.5

    if df is None or df.empty:
        score = 0.5
    else:
        n = len(df)
        if n >= 2:
            score = 1.0
        elif n == 1:
            score = 0.75
        else:
            score = 0.5

    return score if bull_when == "high" else 1.0 - score


__all__ = [
    "seismic_chile_peru_copper",
    "seismic_m6_global_24h",
]
