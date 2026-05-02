"""Sub-fase 12.10 Bunke 3 FRED-drivere.

Levert i Bunke 3 (PLAN § 22.2 #7-#14):

- yields:    t10y3m, t_bill_3mo_yield
- credit:    hy_oas_change
- labor:     initial_claims_z, continuing_claims_z
- growth:    industrial_production_yoy, cfnai_3mma, umich_sentiment_z,
             jolts_openings_yoy, ism_pmi_level
             (ism_pmi_level levert Spor F1 2026-05-02 — manuell CSV-fallback
             via scripts/backfill/ism_pmi.py, series_id ISM_PMI)
- liquidity: anfci_z, m2_yoy
- vol:       vix9d_vix_ratio
- fx:        dollar_index_breadth
- calendar:  fomc_decision_distance

Alle drivere følger pattern fra macro.py:
1. Param-parsing + min_samples-guard
2. fetch via store.get_fundamentals(series_id)
3. Mode-dispatch: default / pct_12m / pct_36m / delta_5d_z / delta_20d_z
4. Step-mapping på raw value eller computed metric for default-mode

ism_pmi_level åpnet Spor F1 2026-05-02 via manuell CSV-fallback per
ADR-007 § 4. Operatør laster av månedlig ISM Report on Business
headline-PMI til ``data/manual/ism_pmi.csv`` (FRED NAPMPMI fortsatt
404 — ISM trakk gratis-feeden).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

from bedrock.engine.drivers import register
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_DELTA_DAILY,
    LOOKBACK_DELTA_WEEKLY,
    LOOKBACK_PCT_12M_DAILY,
    LOOKBACK_PCT_12M_WEEKLY,
    LOOKBACK_PCT_36M_DAILY,
    LOOKBACK_PCT_36M_WEEKLY,
    fundamentals_delta_score,
    fundamentals_extreme_flag,
    fundamentals_pct_score,
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Felles helpers
# ---------------------------------------------------------------------------


def _step(value: float, thresholds: tuple[tuple[float, float], ...]) -> float:
    """Apply step-mapping: returnér første score hvor value ≤ threshold.

    thresholds er sortert ASC på terskel. Siste tuple kan ha None-threshold
    som catch-all (representert som inf).
    """
    for thresh, score in thresholds:
        if value <= thresh:
            return score
    return thresholds[-1][1]


def _get_series(store: Any, series_id: str) -> pd.Series | None:
    """Returnér FRED-serie sortert ASC, eller None ved feil."""
    try:
        s = store.get_fundamentals(series_id)
    except Exception:
        return None
    if s is None or len(s) == 0:
        return None
    return s


def _resolve_mode(
    params: dict, series: pd.Series, *, weekly: bool, instrument: str
) -> float | None:
    """Mode-dispatch via fundamentals_*-helpere. Returnerer None hvis mode er
    'default' eller 'raw' (caller håndterer).
    """
    mode = str(params.get("mode", "default")).lower()
    bull_when = str(params.get("bull_when", "low")).lower()
    if mode in ("default", "raw"):
        return None
    if mode == "pct_12m":
        lookback = LOOKBACK_PCT_12M_WEEKLY if weekly else LOOKBACK_PCT_12M_DAILY
        return fundamentals_pct_score(series, bull_when, lookback, instrument)
    if mode == "pct_36m":
        lookback = LOOKBACK_PCT_36M_WEEKLY if weekly else LOOKBACK_PCT_36M_DAILY
        return fundamentals_pct_score(series, bull_when, lookback, instrument)
    if mode == "delta_5d_z":
        delta_days = 1 if weekly else 5
        lookback = LOOKBACK_DELTA_WEEKLY if weekly else LOOKBACK_DELTA_DAILY
        return fundamentals_delta_score(
            series, bull_when, delta_days=delta_days, lookback=lookback, instrument=instrument
        )
    if mode == "delta_20d_z":
        delta_days = 4 if weekly else 20
        lookback = LOOKBACK_DELTA_WEEKLY if weekly else LOOKBACK_DELTA_DAILY
        return fundamentals_delta_score(
            series, bull_when, delta_days=delta_days, lookback=lookback, instrument=instrument
        )
    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        lookback = LOOKBACK_PCT_12M_WEEKLY if weekly else LOOKBACK_PCT_12M_DAILY
        hard = mode.endswith("_hard")
        return fundamentals_extreme_flag(
            series, hard=hard, lookback=lookback, instrument=instrument
        )
    return None


# ---------------------------------------------------------------------------
# #7 yields: t10y3m, t_bill_3mo_yield
# ---------------------------------------------------------------------------


_T10Y3M_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-0.5, 0.0),  # ≤ -0.5% inverted = recession-signal = bear
    (0.0, 0.25),
    (0.5, 0.5),
    (1.0, 0.75),
    (float("inf"), 1.0),
)


@register("t10y3m")
def t10y3m(store: Any, instrument: str, params: dict) -> float:
    """Yield-curve spread = DGS10 - DGS3MO. Bear ved invert; bull ved steep.

    Bull-when: ``high`` (steep curve = expansion-mode = bull risk-on);
    omvendt for instrumenter som drar nytte av invert (gull, treasuries).

    Modes per ADR-010 (default + pct_12m + pct_36m + delta_5d_z + delta_20d_z
    + extreme_flag_hard/soft).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 30))

    s10 = _get_series(store, "DGS10")
    s3 = _get_series(store, "DGS3MO")
    if s10 is None or s3 is None:
        return 0.0
    if len(s10) < min_samples or len(s3) < min_samples:
        return 0.5

    spread = (s10 - s3).dropna()
    if len(spread) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, spread, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    current = float(spread.iloc[-1])
    score = _step(current, _T10Y3M_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


_TBILL_THRESHOLDS_BULL_LOW: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),  # T-bill < 1% = ZIRP-equivalent = bull risk-on
    (2.5, 0.75),
    (4.0, 0.5),
    (5.5, 0.25),
    (float("inf"), 0.0),
)


@register("t_bill_3mo_yield")
def t_bill_3mo_yield(store: Any, instrument: str, params: dict) -> float:
    """3-Month Treasury Bill rate (TB3MS). Lav rate = bull risk-on.

    Default bull_when='low'. Modes per ADR-010.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 24))

    s = _get_series(store, "TB3MS")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    current = float(s.iloc[-1])
    score = _step(current, _TBILL_THRESHOLDS_BULL_LOW)
    return score if bull_when == "low" else 1.0 - score


# ---------------------------------------------------------------------------
# #8 credit: hy_oas_change
# ---------------------------------------------------------------------------


_HY_CHG_THRESHOLDS_BULL_LOW: tuple[tuple[float, float], ...] = (
    # Negativ chg = spread narrowing = risk-on = bull
    (-0.5, 1.0),
    (-0.2, 0.85),
    (0.0, 0.65),
    (0.2, 0.5),
    (0.5, 0.25),
    (float("inf"), 0.0),
)


@register("hy_oas_change")
def hy_oas_change(store: Any, instrument: str, params: dict) -> float:
    """5d %-pt change i ICE BofA US High Yield OAS (BAMLH0A0HYM2).

    Default bull_when='low' (negative chg = spread narrowing = risk-on).
    Modes per ADR-010.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 60))

    s = _get_series(store, "BAMLH0A0HYM2")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    if len(s) < 6:
        return 0.5
    chg = float(s.iloc[-1]) - float(s.iloc[-6])
    score = _step(chg, _HY_CHG_THRESHOLDS_BULL_LOW)
    return score if bull_when == "low" else 1.0 - score


# ---------------------------------------------------------------------------
# #9 labor: initial_claims_z, continuing_claims_z
# ---------------------------------------------------------------------------


def _z_score_to_step(z: float, *, bull_when: str) -> float:
    """Map z-score til 0..1 via momentum-trapp.

    bull_when='low' (default for claims): negativ z = bull (claims falling
    relative to history). bull_when='high': positiv z = bull.
    """
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


def _compute_z(series: pd.Series, lookback: int = 52) -> float | None:
    """Z-score av siste obs vs `lookback` foregående obs."""
    window = series.tail(lookback + 1).dropna()
    if len(window) < 5:
        return None
    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    mean = float(history.mean())
    std = float(history.std(ddof=1))
    if std <= 0:
        return None
    return (current - mean) / std


def _claims_driver(store: Any, series_id: str, instrument: str, params: dict) -> float:
    """Felles claims z-score driver."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    lookback = int(params.get("lookback_weeks", 52))
    min_samples = int(params.get("min_samples", 26))

    s = _get_series(store, series_id)
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=True, instrument=instrument)
    if mode_score is not None:
        return mode_score

    z = _compute_z(s, lookback=lookback)
    if z is None:
        return 0.5
    return _z_score_to_step(z, bull_when=bull_when)


@register("initial_claims_z")
def initial_claims_z(store: Any, instrument: str, params: dict) -> float:
    """Initial Jobless Claims (ICSA) z-score. Bull when low (= jobs holding)."""
    return _claims_driver(store, "ICSA", instrument, params)


@register("continuing_claims_z")
def continuing_claims_z(store: Any, instrument: str, params: dict) -> float:
    """Continued Jobless Claims (CCSA) z-score. Bull when low."""
    return _claims_driver(store, "CCSA", instrument, params)


# ---------------------------------------------------------------------------
# #10 growth: industrial_production_yoy, cfnai_3mma, umich_sentiment_z,
#             jolts_openings_yoy, ism_pmi_level (Spor F1 2026-05-02).
# ---------------------------------------------------------------------------


def _yoy_change(series: pd.Series, periods: int = 12) -> float | None:
    """YoY %-change for monthly series. periods=12 → 12 mnd YoY."""
    if len(series) < periods + 1:
        return None
    cur = float(series.iloc[-1])
    yoy_back = float(series.iloc[-(periods + 1)])
    if yoy_back == 0:
        return None
    return (cur - yoy_back) / yoy_back * 100.0


_INDPRO_YOY_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-3.0, 0.0),
    (-1.0, 0.25),
    (0.0, 0.5),
    (2.0, 0.75),
    (float("inf"), 1.0),
)


@register("industrial_production_yoy")
def industrial_production_yoy(store: Any, instrument: str, params: dict) -> float:
    """INDPRO 12m YoY %-change. Bull when expanding (high)."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 24))

    s = _get_series(store, "INDPRO")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    yoy = _yoy_change(s, periods=12)
    if yoy is None:
        return 0.5
    score = _step(yoy, _INDPRO_YOY_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


_CFNAI_3MMA_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-1.0, 0.0),
    (-0.5, 0.25),
    (0.0, 0.5),
    (0.3, 0.75),
    (float("inf"), 1.0),
)


@register("cfnai_3mma")
def cfnai_3mma(store: Any, instrument: str, params: dict) -> float:
    """CFNAI 3-month moving average. Above 0 = above-trend growth."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 12))

    s = _get_series(store, "CFNAI")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    if len(s) < 3:
        return 0.5
    mma3 = float(s.tail(3).mean())
    score = _step(mma3, _CFNAI_3MMA_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


_ISM_PMI_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # ISM Manufacturing PMI: 50-line cross. <45 = recession, 50 = neutral,
    # >55 = solid expansion. Step-mapping forsterker terskler rundt 50-linjen.
    (45.0, 0.0),
    (48.0, 0.25),
    (50.0, 0.5),
    (52.0, 0.6),
    (55.0, 0.75),
    (float("inf"), 1.0),
)


@register("ism_pmi_level")
def ism_pmi_level(store: Any, instrument: str, params: dict) -> float:
    """ISM Manufacturing PMI headline-level (Spor F1 — manuell CSV-fallback).

    Reads ``ISM_PMI`` fra fundamentals (manuell CSV-loader per ADR-007 § 4 —
    ISM trakk gratis FRED-feeden NAPMPMI som returnerer 404). Default
    ``bull_when='high'``: PMI > 50 = manufacturing-ekspansjon = bullish
    equity. Override via YAML for instrumenter med omvendt sensitivitet.

    Step-mapping forsterker terskler rundt 50-linjen (markedet diskonterer
    cross-overs aggressivt). Standard ISM-fortolkning:
    - < 45  → deep contraction / recession-territory (bear)
    - 45-48 → contraction
    - 48-50 → soft contraction (skeptisk neutral)
    - 50-52 → mild expansion
    - 52-55 → solid expansion
    - > 55  → strong expansion (bull)

    Optional ``series_id``-override hvis flere ISM-PMI-varianter skulle
    legges inn i fundamentals (Services/Composite mfl).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 6))
    series_id = str(params.get("series_id", "ISM_PMI"))

    s = _get_series(store, series_id)
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    current = float(s.iloc[-1])
    score = _step(current, _ISM_PMI_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


_TREASURY_BTC_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # Trapper kalibrert for bull_when='high' (høy demand = høy score).
    # Z-score av bid_to_cover_ratio mot lookback-vindu.
    (-2.0, 0.0),  # ekstrem svak Treasury-demand
    (-1.0, 0.25),
    (-0.5, 0.4),
    (0.0, 0.5),
    (0.5, 0.6),
    (1.0, 0.75),
    (float("inf"), 1.0),  # ekstrem sterk Treasury-demand
)


@register("treasury_auction_demand")
def treasury_auction_demand(store: Any, instrument: str, params: dict) -> float:
    """US Treasury auction bid-to-cover-ratio z-score (Spor F6).

    Reads TreasuryDirect-auction-historikk for valgt (security_type,
    security_term)-par og z-score'r siste bid_to_cover-ratio mot
    rolling-historikk. Default ``security_type='Note'`` /
    ``security_term='10-Year'`` — den mest-fulgte auksjonen for
    safe-haven-demand-signal.

    Tolkning for equity-instrumenter:
    - Høy bid-to-cover (z > 0) = sterk Treasury-demand = risk-off-bias
      = bearish equity → bruk ``bull_when='low'`` for å invertere.
    - Svak bid-to-cover (z < 0) = svak demand = risk-on-bias = bullish
      equity.

    Default ``bull_when='low'`` (equity-tilpasset). Override 'high' for
    bond ETFs hvor sterk Treasury-demand er positivt for pris.

    Params:
        security_type: Bill/Note/Bond/TIPS/FRN. Default ``"Note"``.
        security_term: f.eks. ``"10-Year"``, ``"2-Year"``, ``"13-Week"``.
            Default ``"10-Year"``.
        lookback_months: rolling-vindu for z-score (default 24).
        bull_when: ``"low"`` (default, equity-tolkning) eller ``"high"``.
        min_samples: minimum auksjoner i historikken (default 12).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    security_type = str(params.get("security_type", "Note"))
    security_term = str(params.get("security_term", "10-Year"))
    lookback_months = int(params.get("lookback_months", 24))
    min_samples = int(params.get("min_samples", 12))

    try:
        df = store.get_treasury_auctions(security_type=security_type, security_term=security_term)
    except Exception:
        return 0.0

    if df is None or df.empty or "bid_to_cover_ratio" not in df.columns:
        return 0.0

    s = pd.Series(pd.to_numeric(df["bid_to_cover_ratio"], errors="coerce")).dropna()
    if len(s) < min_samples:
        return 0.5

    # 24-mnd ≈ 24 auksjoner for monthly Notes; for Bills (ukentlig) ~104.
    # Bruker ren tail-window (ikke kalender-måneder) for cadence-agnostikk.
    window = s.tail(lookback_months + 1)
    if len(window) < 4:
        return 0.5

    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    mean = float(history.mean())
    std = float(history.std(ddof=0))
    if std == 0 or pd.isna(std):
        return 0.5

    z = (current - mean) / std
    score = _step(z, _TREASURY_BTC_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


@register("umich_sentiment_z")
def umich_sentiment_z(store: Any, instrument: str, params: dict) -> float:
    """Univ Michigan Consumer Sentiment (UMCSENT) z-score. Bull when high."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    lookback = int(params.get("lookback_months", 60))
    min_samples = int(params.get("min_samples", 24))

    s = _get_series(store, "UMCSENT")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    z = _compute_z(s, lookback=lookback)
    if z is None:
        return 0.5
    return _z_score_to_step(z, bull_when=bull_when)


_JOLTS_YOY_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-15.0, 0.0),
    (-5.0, 0.25),
    (0.0, 0.5),
    (5.0, 0.75),
    (float("inf"), 1.0),
)


@register("jolts_openings_yoy")
def jolts_openings_yoy(store: Any, instrument: str, params: dict) -> float:
    """JOLTS Job Openings (JTSJOL) 12m YoY %-change. Bull when growing."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 24))

    s = _get_series(store, "JTSJOL")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    yoy = _yoy_change(s, periods=12)
    if yoy is None:
        return 0.5
    score = _step(yoy, _JOLTS_YOY_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


# ---------------------------------------------------------------------------
# #11 liquidity: anfci_z, m2_yoy
# ---------------------------------------------------------------------------


@register("anfci_z")
def anfci_z(store: Any, instrument: str, params: dict) -> float:
    """Adjusted NFCI (ANFCI) z-score. Bull when low (= loose conditions).

    Replaces nfci_change i § 22.2 #11. NFCI er en absolutt level-indeks
    sentrert om 0; ANFCI er adjusted for credit/leverage. Z-score gir
    relativ posisjonering.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    lookback = int(params.get("lookback_weeks", 156))  # ~3 år
    min_samples = int(params.get("min_samples", 52))

    s = _get_series(store, "ANFCI")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=True, instrument=instrument)
    if mode_score is not None:
        return mode_score

    z = _compute_z(s, lookback=lookback)
    if z is None:
        return 0.5
    return _z_score_to_step(z, bull_when=bull_when)


_M2_YOY_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),  # ≤ 0 % YoY = krimping = bear (dollar-likviditet faller)
    (3.0, 0.3),
    (5.0, 0.5),
    (8.0, 0.75),
    (float("inf"), 1.0),
)


@register("m2_yoy")
def m2_yoy(store: Any, instrument: str, params: dict) -> float:
    """M2 Money Supply (M2SL) 12m YoY %-change. Bull when growing."""
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    min_samples = int(params.get("min_samples", 24))

    s = _get_series(store, "M2SL")
    if s is None:
        return 0.0
    if len(s) < min_samples:
        return 0.5

    mode_score = _resolve_mode(params, s, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    yoy = _yoy_change(s, periods=12)
    if yoy is None:
        return 0.5
    score = _step(yoy, _M2_YOY_THRESHOLDS_BULL_HIGH)
    return score if bull_when == "high" else 1.0 - score


# ---------------------------------------------------------------------------
# #12 vol: vix9d_vix_ratio
# ---------------------------------------------------------------------------


_VIX9D_VIX_RATIO_THRESHOLDS: tuple[tuple[float, float], ...] = (
    # Bull-of-equity (default bull_when='low'): low ratio = backwardation OK,
    # high ratio (>1.0) = short-term-fear-spike (mean-revert opportunity for
    # equities).
    (0.85, 1.0),  # ekstrem complacency
    (0.95, 0.8),
    (1.0, 0.6),
    (1.10, 0.5),  # mild backwardation
    (1.25, 0.3),  # tydelig fear-spike
    (float("inf"), 0.0),
)


@register("vix9d_vix_ratio")
def vix9d_vix_ratio(store: Any, instrument: str, params: dict) -> float:
    """VIX9D / VIX(CLS) ratio. Default bull_when='low'.

    < 1.0 = backwardation (stable expectations); > 1.0 = short-term fear
    spike. Mean-revert: high ratio = bull risk-on next 5-10d (per
    studied vol-term-structure presedens).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 30))

    vix9d = _get_series(store, "VIX9D")
    vix = _get_series(store, "VIXCLS")
    if vix9d is None or vix is None:
        return 0.0
    if len(vix9d) < min_samples or len(vix) < min_samples:
        return 0.5

    # Align on common index
    df = pd.concat([vix9d.rename("vix9d"), vix.rename("vix")], axis=1, join="inner").dropna()
    if df.empty:
        return 0.5
    ratio = (df["vix9d"] / df["vix"]).dropna()
    if len(ratio) == 0:
        return 0.5

    mode_score = _resolve_mode(params, ratio, weekly=False, instrument=instrument)
    if mode_score is not None:
        return mode_score

    current = float(ratio.iloc[-1])
    score = _step(current, _VIX9D_VIX_RATIO_THRESHOLDS)
    return score if bull_when == "low" else 1.0 - score


# ---------------------------------------------------------------------------
# #13 fx: dollar_index_breadth
# ---------------------------------------------------------------------------


# DEX-serier orientering: hver serie er enten "USD/X" (USD pr enhet av X) eller
# "X/USD" (X pr USD). For "USD strength", USD/X opp = USD strong, X/USD opp =
# X strong = USD weak.
#
# FRED-konvensjoner:
#   DEXJPUS = JPY/USD     → opp = JPY weak vs USD = USD STRONG
#   DEXCAUS = CAD/USD     → opp = CAD weak = USD STRONG
#   DEXSDUS = SEK/USD     → opp = SEK weak = USD STRONG
#   DEXSZUS = CHF/USD     → opp = CHF weak = USD STRONG
#   DEXUSEU = USD/EUR     → opp = USD strong = USD STRONG  (per FRED, dollar/euro)
#   DEXUSUK = USD/GBP     → opp = USD strong = USD STRONG
#   DEXUSAL = USD/AUD     → opp = USD strong = USD STRONG
#   DEXUSNZ = USD/NZD     → opp = USD strong = USD STRONG
#
# Alle 8 serier: stigning ⇒ USD STRONG. Breadth = andel av 8 som er opp over
# `window`-dager.
_DEX_SERIES: tuple[str, ...] = (
    "DEXJPUS",
    "DEXCAUS",
    "DEXSDUS",
    "DEXSZUS",
    "DEXUSEU",
    "DEXUSUK",
    "DEXUSAL",
    "DEXUSNZ",
)


@register("dollar_index_breadth")
def dollar_index_breadth(store: Any, instrument: str, params: dict) -> float:
    """Andel av 8 DEX-pairs som viser USD-styrke over window-dager.

    1.0 = alle 8 pairs viser USD opp; 0.0 = ingen. Default bull_when='low'
    (USD-styrke = bear FX/commodities; bull USDJPY).

    Returns 0.5 hvis < 4 av 8 pairs er tilgjengelige.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    window = int(params.get("window", 5))
    min_pairs = int(params.get("min_pairs", 4))

    up_count = 0
    available_count = 0
    for series_id in _DEX_SERIES:
        s = _get_series(store, series_id)
        if s is None or len(s) < window + 1:
            continue
        available_count += 1
        recent = s.tail(window + 1).dropna()
        if len(recent) < 2:
            continue
        if float(recent.iloc[-1]) > float(recent.iloc[0]):
            up_count += 1

    if available_count < min_pairs:
        return 0.5

    breadth = up_count / float(available_count)  # 0..1, høy = USD strong
    return breadth if bull_when == "high" else 1.0 - breadth


# ---------------------------------------------------------------------------
# #14 calendar: fomc_decision_distance
# ---------------------------------------------------------------------------


_FOMC_TITLE_PATTERNS: tuple[str, ...] = (
    "FOMC Statement",
    "Federal Funds Rate",
    "Fed Chair",
    "FOMC Press Conference",
    "FOMC Meeting Minutes",
)


@register("fomc_decision_distance")
def fomc_decision_distance(store: Any, instrument: str, params: dict) -> float:
    """Tids-buffer til neste FOMC-rate-decision (ramper 0 → 1).

    Variant av event_distance med hardkodet filter på FOMC-relaterte
    title-patterns (FOMC Statement / Federal Funds Rate / Fed Chair).
    Brukes på alle FX/equity/metal-instrumenter siden Fed-events
    flytter alle USD-priced markeder.
    """
    _ = params.get("_horizon")
    from datetime import datetime, timezone

    min_hours = float(params.get("min_hours", 8.0))
    lookahead = float(params.get("lookahead_hours", 168.0))  # 1 uke
    empty_score = float(params.get("empty_score", 1.0))
    error_score = float(params.get("error_score", 0.5))

    now_ts = params.get("_now")
    if now_ts is None:
        now_ts = datetime.now(timezone.utc)
    elif isinstance(now_ts, str):
        now_ts = pd.to_datetime(now_ts, utc=True).to_pydatetime()

    from_ts_query = now_ts.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        df = store.get_econ_events(
            countries=["USD"],
            impact_levels=["High"],
            from_ts=from_ts_query,
        )
    except Exception as exc:
        _log.warning(
            "fomc_decision_distance.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return error_score

    if df is None or df.empty:
        return empty_score

    # Filtrer til FOMC-relaterte titler
    pattern = "|".join(_FOMC_TITLE_PATTERNS)
    fomc_df = df[df["title"].str.contains(pattern, case=False, na=False, regex=True)]
    if fomc_df.empty:
        return empty_score

    diffs = (fomc_df["event_ts"] - pd.Timestamp(now_ts)).dt.total_seconds() / 3600.0
    forward = diffs[diffs >= 0.0]
    if forward.empty:
        return empty_score
    in_window = forward[forward <= lookahead]
    if in_window.empty:
        return empty_score

    nearest = float(in_window.min())
    if nearest >= min_hours:
        return 1.0
    if nearest <= 0:
        return 0.0
    return max(0.0, min(1.0, nearest / min_hours))


# ---------------------------------------------------------------------------
# Suppress unused-import warning
# ---------------------------------------------------------------------------
_ = np  # numpy reservert for fremtidige drivere som krever vektorisering


__all__ = [
    "anfci_z",
    "cfnai_3mma",
    "continuing_claims_z",
    "dollar_index_breadth",
    "fomc_decision_distance",
    "hy_oas_change",
    "industrial_production_yoy",
    "initial_claims_z",
    "jolts_openings_yoy",
    "m2_yoy",
    "t10y3m",
    "t_bill_3mo_yield",
    "umich_sentiment_z",
    "vix9d_vix_ratio",
]
