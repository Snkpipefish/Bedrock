"""*_surprise-drivere (sub-fase 12.10 follow-up Spor B, session 138).

Per ADR-014 cross-source data-arkitektur. Drivere leser ``econ_events``-
tabellen (Forex Factory + FRED-cross-source) og beregner surprise =
(actual - forecast) for siste event innen lookback-vindu, mappet til
0..1 score.

4 drivere:
- ``nfp_surprise``: Non-Farm Payrolls (PAYEMS MoM Δ tusen jobs)
- ``cpi_surprise``: CPI m/m (CPIAUCSL MoM %)
- ``gdp_surprise``: GDP q/q (GDP QoQ-annualisert %)
- ``pce_surprise``: Core PCE Price Index m/m (PCEPI MoM %)

Markedsreaksjon avhenger av asset (per § 22.2 #5):
- SP500/Nasdaq: NFP↑/GDP↑ = bull; CPI↑/PCE↑ = bear (Fed hawkish)
- USDJPY: alle↑ = bull (USD styrker seg)
- EURUSD: alle↑ = bear (USDEUR-svekking)

Driveren leser ``bull_when`` per (instrument, driver) for å sette
orientering.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# Step-trapp per metric_kind. Surprise-akse er (actual - forecast) i
# samme units som forecast.
_NFP_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # Surprise i tusen jobs. Typisk -200 til +200K.
    (-100.0, 0.0),
    (-50.0, 0.25),
    (0.0, 0.5),
    (50.0, 0.75),
    (float("inf"), 1.0),
)

_PCT_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # Surprise i prosent-punkter (CPI/PCE/GDP). Typisk -0.3 til +0.3 for
    # CPI/PCE; -2 til +2 for GDP.
    (-0.3, 0.0),
    (-0.1, 0.25),
    (0.0, 0.5),
    (0.1, 0.75),
    (float("inf"), 1.0),
)

_GDP_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # GDP-surprise i prosent-punkter (annualisert). Typisk -2 til +2.
    (-1.5, 0.0),
    (-0.5, 0.25),
    (0.0, 0.5),
    (0.5, 0.75),
    (float("inf"), 1.0),
)


_VALUE_RE = re.compile(r"^([+-]?\d+\.?\d*)\s*([%KMB]?)\s*$")


def _parse_value(s: object) -> float | None:
    """Parse FF-formatted verdi til numerisk. Returner None ved feil.

    Eksempler:
        "115K" → 115.0 (jobs in thousands)
        "+108K" → 108.0
        "-48K" → -48.0
        "0.2%" → 0.2 (% points)
        "3.0%" → 3.0
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s_str = str(s).strip()
    if not s_str:
        return None
    m = _VALUE_RE.match(s_str)
    if m is None:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    suffix = m.group(2).upper()
    # K/M/B for jobs er allerede i tusen — vi beholder verdien som-er
    # (forecast og actual er begge "115K"-formatert; surprise er
    # (actual - forecast) i samme units, så skalering er konsistent).
    if suffix == "M":
        v *= 1000.0
    elif suffix == "B":
        v *= 1_000_000.0
    return v


def _step(value: float, thresholds: tuple[tuple[float, float], ...]) -> float:
    for thresh, score in thresholds:
        if value <= thresh:
            return score
    return thresholds[-1][1]


def _econ_surprise_score(
    store: Any,
    instrument: str,
    params: dict,
    *,
    metric_kind: str,
) -> float:
    """Felles helper for surprise-drivere.

    Params:
        title_pattern (REQUIRED): SQL LIKE-pattern (med %% wildcards).
        country: default 'USD'.
        bull_when: 'high' (default) eller 'low' — flipper orientering.
        lookback_days: events publisert i siste N dager. Default 30 for
            monthly metrics, 100 for GDP (quarterly).
        thresholds: optional override.

    Defensive 0.5 (nøytral) ved manglende data — ingen surprise = ingen
    informasjon = ikke et bull/bear-signal.
    """
    _ = params.get("_horizon")
    title_pattern = params.get("title_pattern")
    if not title_pattern:
        _log.warning("econ_surprise.no_title_pattern", instrument=instrument)
        return 0.5
    country = str(params.get("country", "USD")).upper()
    bull_when = str(params.get("bull_when", "high")).lower()
    default_lookback = 100 if metric_kind == "gdp" else 30
    lookback_days = int(params.get("lookback_days", default_lookback))

    try:
        df = store.get_econ_events(
            countries=[country],
            title_pattern=str(title_pattern),
        )
    except Exception:
        return 0.5

    if df is None or df.empty:
        return 0.5

    # Filtrér på actual NOT NULL og forecast NOT NULL
    df = df[df["actual"].notna() & df["forecast"].notna()]
    if df.empty:
        return 0.5

    # Filtrér på lookback-vindu fra siste event_ts (as_of-prinsipp:
    # AsOfDateStore har allerede clipped, så df["event_ts"].max() er
    # latest-known)
    if df["event_ts"].dt.tz is None:
        latest = df["event_ts"].max()
    else:
        latest = df["event_ts"].max()
    cutoff = latest - pd.Timedelta(days=lookback_days)
    df = df[df["event_ts"] >= cutoff]
    if df.empty:
        return 0.5

    # Sorter desc, ta nyeste rad
    df = df.sort_values("event_ts", ascending=False)
    last = df.iloc[0]

    actual = _parse_value(last["actual"])
    forecast = _parse_value(last["forecast"])
    if actual is None or forecast is None:
        return 0.5

    surprise = actual - forecast

    user_thresholds = params.get("thresholds")
    if user_thresholds is not None:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)
    elif metric_kind == "nfp":
        steps = _NFP_THRESHOLDS_BULL_HIGH
    elif metric_kind == "gdp":
        steps = _GDP_THRESHOLDS_BULL_HIGH
    else:  # cpi, pce — pct-points
        steps = _PCT_THRESHOLDS_BULL_HIGH

    score = _step(surprise, steps)
    if bull_when == "low":
        return round(1.0 - score, 4)
    return round(score, 4)


@register("nfp_surprise")
def nfp_surprise(store: Any, instrument: str, params: dict) -> float:
    """Non-Farm Payrolls actual vs forecast → 0..1.

    Default title_pattern='Non-Farm Employment Change'.
    """
    p = dict(params)
    p.setdefault("title_pattern", "Non-Farm Employment Change")
    return _econ_surprise_score(store, instrument, p, metric_kind="nfp")


@register("cpi_surprise")
def cpi_surprise(store: Any, instrument: str, params: dict) -> float:
    """CPI m/m actual vs forecast → 0..1.

    Default title_pattern='CPI m/m'. (Bruk 'Core CPI m/m' for kjerne.)
    """
    p = dict(params)
    p.setdefault("title_pattern", "CPI m/m")
    return _econ_surprise_score(store, instrument, p, metric_kind="cpi")


@register("gdp_surprise")
def gdp_surprise(store: Any, instrument: str, params: dict) -> float:
    """GDP q/q actual vs forecast → 0..1.

    Default title_pattern='Advance GDP q/q' (første rapport, mest market-
    moving). 'Prelim/Final GDP q/q' kan brukes for revisjon-effekter.
    """
    p = dict(params)
    p.setdefault("title_pattern", "Advance GDP q/q")
    return _econ_surprise_score(store, instrument, p, metric_kind="gdp")


@register("pce_surprise")
def pce_surprise(store: Any, instrument: str, params: dict) -> float:
    """Core PCE Price Index m/m actual vs forecast → 0..1.

    Default title_pattern='Core PCE Price Index m/m'.
    """
    p = dict(params)
    p.setdefault("title_pattern", "Core PCE Price Index m/m")
    return _econ_surprise_score(store, instrument, p, metric_kind="pce")


__all__ = [
    "cpi_surprise",
    "gdp_surprise",
    "nfp_surprise",
    "pce_surprise",
]
