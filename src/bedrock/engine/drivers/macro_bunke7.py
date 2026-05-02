"""Sub-fase 12.10 Bunke 7 — GIE-utvidelse + COT-disaggregated.

Per § 22.2 #23-#26.

#23 AGSI per-land (5 drivere):
- agsi_germany_pct (DE), agsi_netherlands_pct (NL), agsi_italy_pct (IT) —
  thin wrappers rundt eksisterende agsi_storage_pct.
- agsi_withdrawal_rate, agsi_injection_rate — nye drivere som leser
  withdrawal_twh / injection_twh-kolonnene direkte.

#24 ALSI: DEFERRED (krever ny GIE-API-route + skjema).
#25 IIP REMIT: DEFERRED (krever ny IIP-API-route + skjema).

#26 COT-disaggregated utvidelser (2 av 4):
- cot_oi_change: open_interest WoW-change z-score
- cot_commercial_extreme: Commercial-positioning ekstrem (kontrært)
- cot_concentration_top4: DEFERRED (Conc_Net-kolonner ikke i schema)
- cot_swap_dealer_skew: DEFERRED (Swap Dealer kun i TFF, ikke disaggregated)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import get, register
from bedrock.engine.drivers.macro_bunke3 import _compute_z, _step

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# #23 AGSI per-land (thin wrappers)
# ---------------------------------------------------------------------------


def _agsi_country_wrapper(store: Any, instrument: str, params: dict, *, country: str) -> float:
    base_fn = get("agsi_storage_pct")
    sub_params = dict(params)
    sub_params["country"] = country
    return base_fn(store, instrument, sub_params)


@register("agsi_germany_pct")
def agsi_germany_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Germany gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="de")


@register("agsi_netherlands_pct")
def agsi_netherlands_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Netherlands gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="nl")


@register("agsi_italy_pct")
def agsi_italy_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Italy gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="it")


# ---------------------------------------------------------------------------
# AGSI withdrawal/injection rates
# ---------------------------------------------------------------------------


def _agsi_rate_driver(store: Any, instrument: str, params: dict, *, column: str) -> float:
    """Felles helper for withdrawal/injection-rate-drivere."""
    _ = params.get("_horizon")
    country = str(params.get("country", "eu")).lower()
    bull_when = str(params.get("bull_when", "high")).lower()
    lookback_days = int(params.get("lookback_days", 252))
    min_samples = int(params.get("min_samples", 30))

    try:
        df = store.get_agsi_storage(country)
    except Exception:
        return 0.0

    if df is None or df.empty or column not in df.columns:
        return 0.0

    series = pd.Series(
        df[column].astype("float64").values,
        index=pd.to_datetime(df["gas_day_start"]),
    ).dropna()

    if len(series) < min_samples:
        return 0.5

    z = _compute_z(series, lookback=lookback_days)
    if z is None:
        return 0.5

    z_oriented = z if bull_when == "high" else -z
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


@register("agsi_withdrawal_rate")
def agsi_withdrawal_rate(store: Any, instrument: str, params: dict) -> float:
    """AGSI withdrawal-rate (TWh/dag) z-score. Default bull_when='high' (høyt
    uttak = stress på supply = bull NG). Override via YAML."""
    return _agsi_rate_driver(store, instrument, params, column="withdrawal_twh")


@register("agsi_injection_rate")
def agsi_injection_rate(store: Any, instrument: str, params: dict) -> float:
    """AGSI injection-rate (TWh/dag) z-score. Default bull_when='low' (lav
    injeksjon = trang supply = bull NG)."""
    # Override default bull_when til 'low' for injection
    p = dict(params)
    p.setdefault("bull_when", "low")
    return _agsi_rate_driver(store, instrument, p, column="injection_twh")


# ---------------------------------------------------------------------------
# #26 COT utvidelser (2 av 4)
# ---------------------------------------------------------------------------


_OI_CHANGE_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-2.0, 0.0),  # store OI-fall = bear/risk-off
    (-1.0, 0.25),
    (0.0, 0.5),
    (1.0, 0.75),
    (float("inf"), 1.0),
)


@register("cot_oi_change")
def cot_oi_change(store: Any, instrument: str, params: dict) -> float:
    """COT open_interest WoW-change z-score.

    Tolkning: økning i OI = nye penger inn = trend-følger-momentum
    (bull-of-trend); fall i OI = posisjon-lukking = mean-revert-signal.
    Default bull_when='high'.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 52))
    min_samples = int(params.get("min_samples", 30))

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or "open_interest" not in df.columns:
        return 0.0

    series = pd.Series(
        df["open_interest"].astype("float64").values,
        index=pd.to_datetime(df["report_date"]),
    ).dropna()

    if len(series) < min_samples:
        return 0.5

    # WoW = pct change: (current - prev) / prev
    if len(series) < 2:
        return 0.5
    chg_series = series.pct_change().dropna() * 100.0
    if len(chg_series) < min_samples:
        return 0.5

    z = _compute_z(chg_series, lookback=lookback_weeks)
    if z is None:
        return 0.5

    z_oriented = z if bull_when == "high" else -z
    score = _step(z_oriented, _OI_CHANGE_THRESHOLDS_BULL_HIGH)
    return score


@register("cot_commercial_extreme")
def cot_commercial_extreme(store: Any, instrument: str, params: dict) -> float:
    """Commercial-positioning ekstrem-flag (kontrært-signal).

    Commercials er typisk hedgers (produsenter/forbrukere) som tar motsatt
    posisjon av spekulanter. Ekstrem long = bull-of-prising; ekstrem short
    = bear-of-prising. Default bull_when='high' = commercial long ekstrem
    er bullish.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 156))  # 3 år
    min_samples = int(params.get("min_samples", 52))

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or "comm_long" not in df.columns:
        return 0.0

    long_s = df["comm_long"].astype("float64")
    short_s = df["comm_short"].astype("float64")
    oi = df["open_interest"].astype("float64").replace(0, float("nan"))
    net_pct = ((long_s - short_s) / oi).dropna() * 100.0

    if len(net_pct) < min_samples:
        return 0.5

    # Rolling-percentile av siste obs
    window = net_pct.tail(lookback_weeks + 1).dropna()
    if len(window) < 10:
        return 0.5
    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    rank = float((history < current).sum()) / float(len(history))

    # Map rank til kontrært score: høy commercial-long = bullish (bull_when='high')
    score = rank if bull_when == "high" else 1.0 - rank
    return max(0.0, min(1.0, score))


__all__ = [
    "agsi_germany_pct",
    "agsi_injection_rate",
    "agsi_italy_pct",
    "agsi_netherlands_pct",
    "agsi_withdrawal_rate",
    "cot_commercial_extreme",
    "cot_oi_change",
]
