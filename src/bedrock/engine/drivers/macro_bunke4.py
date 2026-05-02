# pyright: reportReturnType=false
# pandas-stubs typer pd.concat([...], axis=1).max(axis=1) som Union;
# i praksis Series. Same pattern som risk.py.

"""Sub-fase 12.10 Bunke 4 — Yahoo + CBOE + NOAA-drivere.

Levert per § 22.2 #15-#18:

#15 Yahoo vol-indekser (z-score-baserte):
- move_index_z: ICE BofA US Treasury MOVE Index (2003+)
- vvix_z: VIX of VIX (2007+)
- gvz_z: CBOE Gold ETF VIX (2008+)
- ovx_z: CBOE Crude Oil VIX (2007+)

#16 CBOE indekser:
- cboe_skew_z: CBOE SKEW Index (z-score over 252-d). Levert.
- cboe_pcr_total_extreme: DEFERRED (krever CBOE direkte; Yahoo har ikke)
- cboe_pcr_equity_only: DEFERRED (samme)
- cboe_vix_term_curve: DEFERRED (overlapper med vix_term_ratio)

#17 NOAA ENSO/PDO:
- noaa_oni_index: ONI level (erstatter `enso_regime`-mapping)
- noaa_enso_forecast_3mo: IRI ENSO Plumes 3-mnd-forward (Spor F4 2026-05-02 —
  manuell CSV-fallback per ADR-007 § 4, series_id=IRI_ENSO_FCST_3MO)
- noaa_pdo_index: PDO level (multi-decade ocean-pattern)

#18 intraday:
- intraday_atr_h1: ATR(14) på H1-bars som kortsiktig vol-gate
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register
from bedrock.engine.drivers.macro_bunke3 import _compute_z, _get_series, _step

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Felles helper for vol-indeks z-score-drivere
# ---------------------------------------------------------------------------


def _vol_index_z_driver(store: Any, instrument: str, params: dict, *, series_id: str) -> float:
    """Generic z-score-driver for vol-indekser. Default bull_when='low' (lav
    vol = bull risk-on). Returnerer 0..1 score.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    lookback = int(params.get("lookback_days", 252))
    min_samples = int(params.get("min_samples", 60))

    s = _get_series(store, series_id)
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    z = _compute_z(s, lookback=lookback)
    if z is None:
        return 0.5

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


# ---------------------------------------------------------------------------
# #15 Yahoo vol-indekser
# ---------------------------------------------------------------------------


@register("move_index_z")
def move_index_z(store: Any, instrument: str, params: dict) -> float:
    """ICE BofA US Treasury MOVE Index z-score. Lav = bull-of-rates-stability."""
    return _vol_index_z_driver(store, instrument, params, series_id="MOVE")


@register("vvix_z")
def vvix_z(store: Any, instrument: str, params: dict) -> float:
    """VVIX (VIX of VIX) z-score. Bull-when=low default (lav VVIX = vol-vol-
    stability = risk-on)."""
    return _vol_index_z_driver(store, instrument, params, series_id="VVIX")


@register("gvz_z")
def gvz_z(store: Any, instrument: str, params: dict) -> float:
    """CBOE Gold-ETF VIX (GVZ) z-score. For Gold/Silver: lav GVZ = bull (fearless
    accumulation)."""
    return _vol_index_z_driver(store, instrument, params, series_id="GVZ")


@register("ovx_z")
def ovx_z(store: Any, instrument: str, params: dict) -> float:
    """CBOE Crude Oil VIX (OVX) z-score. For CrudeOil/Brent: lav OVX = bull
    risk-on."""
    return _vol_index_z_driver(store, instrument, params, series_id="OVX")


# ---------------------------------------------------------------------------
# #16 CBOE
# ---------------------------------------------------------------------------


@register("cboe_skew_z")
def cboe_skew_z(store: Any, instrument: str, params: dict) -> float:
    """CBOE SKEW Index z-score. Høy SKEW = tail-risk-priced-in (etterlengtet
    av options-flow). Default bull_when='low' (lav SKEW = lite halerisk-
    bekymring = risk-on)."""
    return _vol_index_z_driver(store, instrument, params, series_id="SKEW")


# ---------------------------------------------------------------------------
# #17 NOAA ENSO/PDO
# ---------------------------------------------------------------------------


_ONI_THRESHOLDS_DEFAULT: tuple[tuple[float, float], ...] = (
    # Default: bull_when='low' kontekst er Cocoa/Coffee-positiv.
    # ONI ≤ -0.5 = La Niña (kontekst-spesifikk effekt; default neutral)
    # |ONI| < 0.5 = neutral
    # ONI ≥ +0.5 = El Niño (kontekst-spesifikk)
    # Driveren returnerer rå-fortolkning som 0..1; YAML-config bestemmer
    # hvilken retning som er bullish via bull_when.
    (-1.5, 1.0),  # sterk La Niña
    (-0.5, 0.75),  # mild La Niña
    (0.5, 0.5),  # neutral
    (1.5, 0.25),  # mild El Niño
    (float("inf"), 0.0),  # sterk El Niño
)


@register("noaa_oni_index")
def noaa_oni_index(store: Any, instrument: str, params: dict) -> float:
    """NOAA Oceanic Niño Index level. Erstatter ``enso_regime`` med direkte
    NOAA-data (i stedet for proxy-tabell). Returnerer 0..1 basert på siste
    tilgjengelige verdi.

    Default tolkning er agnostisk: bull_when='low' antar La Niña er bullish
    (typisk for grain-instrumenter pga US-tørke). Override via YAML for
    instrumenter som har omvendt sensitivitet.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 12))

    s = _get_series(store, "ONI")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    current = float(s.iloc[-1])
    score = _step(current, _ONI_THRESHOLDS_DEFAULT)
    return score if bull_when == "low" else 1.0 - score


_PDO_THRESHOLDS_DEFAULT: tuple[tuple[float, float], ...] = (
    # PDO-fase: positiv = warm phase (vest-Pacific cool, øst-Pacific warm),
    # negativ = cool phase. Multi-decade-pattern. Effekt på agri/commodity
    # er kontekst-spesifikk; default neutral-mapping.
    (-1.5, 1.0),
    (-0.5, 0.75),
    (0.5, 0.5),
    (1.5, 0.25),
    (float("inf"), 0.0),
)


@register("noaa_enso_forecast_3mo")
def noaa_enso_forecast_3mo(store: Any, instrument: str, params: dict) -> float:
    """IRI ENSO Plumes 3-mnd-forward Niño 3.4 ensemble-mean (Spor F4).

    Reads ``IRI_ENSO_FCST_3MO`` fra fundamentals (manuell CSV-loader per
    ADR-007 § 4). Mapper med samme step-tabell som ``noaa_oni_index``
    siden begge representerer Niño 3.4 SST-anomali-nivå (forward vs
    realisert). Default ``bull_when='low'`` antar La Niña-forecast er
    bullish for grain/agri (drought-bias i Brazil/W.Afrika).

    Override via YAML hvis instrumentet har omvendt sensitivitet
    (f.eks. tropisk asia-rice som er våtere under La Niña).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 3))
    series_id = str(params.get("series_id", "IRI_ENSO_FCST_3MO"))

    s = _get_series(store, series_id)
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    current = float(s.iloc[-1])
    score = _step(current, _ONI_THRESHOLDS_DEFAULT)
    return score if bull_when == "low" else 1.0 - score


@register("noaa_pdo_index")
def noaa_pdo_index(store: Any, instrument: str, params: dict) -> float:
    """NOAA PDO Index level. Multi-decade ocean-pattern."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 12))

    s = _get_series(store, "PDO")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    current = float(s.iloc[-1])
    score = _step(current, _PDO_THRESHOLDS_DEFAULT)
    return score if bull_when == "low" else 1.0 - score


# ---------------------------------------------------------------------------
# #18 intraday
# ---------------------------------------------------------------------------


def _wilder_atr(ohlc: pd.DataFrame, period: int) -> pd.Series:
    """Wilder-style ATR (kopiert fra risk.py for å unngå krys-modul-import)."""
    high = ohlc["high"].astype("float64")
    low = ohlc["low"].astype("float64")
    close = ohlc["close"].astype("float64")
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


@register("intraday_atr_h1")
def intraday_atr_h1(store: Any, instrument: str, params: dict) -> float:
    """ATR(14) på H1-bars som kortsiktig vol-percentil-driver.

    For SCALP/SWING: høy intraday-vol = høyere stop-buffer-behov, men også
    raskere mean-revert-muligheter. Default bull_when='high' (mean-revert-
    tolkning); override via YAML.

    Krever H1-prices via ``store.get_prices_ohlc(instrument, tf='H1')``.
    Returnerer 0.5 hvis H1-data mangler eller historikk er kort.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    period = int(params.get("period", 14))
    lookback = int(params.get("lookback", 252 * 24))  # ~1 år H1-bars
    tf = str(params.get("tf", "H1"))
    min_samples = int(params.get("min_samples", period + 24))

    try:
        ohlc = store.get_prices_ohlc(instrument, tf=tf, lookback=lookback + period + 10)
    except Exception:
        return 0.5

    if ohlc is None or len(ohlc) < min_samples:
        return 0.5

    atr_series = _wilder_atr(ohlc, period)
    if atr_series.empty or atr_series.dropna().empty:
        return 0.5

    window_len = min(lookback, len(atr_series))
    window = atr_series.tail(window_len).dropna()
    if len(window) < 2:
        return 0.5

    current = float(window.iloc[-1])
    rank = float((window < current).sum()) / float(len(window) - 1)
    rank = max(0.0, min(1.0, rank))
    return rank if bull_when == "high" else 1.0 - rank


__all__ = [
    "cboe_skew_z",
    "gvz_z",
    "intraday_atr_h1",
    "move_index_z",
    "noaa_enso_forecast_3mo",
    "noaa_oni_index",
    "noaa_pdo_index",
    "ovx_z",
    "vvix_z",
]
