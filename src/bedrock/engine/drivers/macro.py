"""Macro-familie drivere (Sub-fase 12.5 session 71 + 12.7 R3).

Erstatter ``sma200_align``-placeholder i macro-familien for finansielle
instrumenter. Bruker FRED-fundamentals (DataStore.get_fundamentals) til
å beregne makro-miljøet rundt instrumentet.

Tre drivere implementert:

- ``real_yield``: 10-årig nominell yield − 10-årig inflation expectation
  (DGS10 − T10YIE). Mappet til 0..1 via konfigurerbar terskel-trapp.
  ``bull_when="low"`` (default for Gold/Silver — ikke-rentebærende
  metaller får støtte når real-yield faller). ``bull_when="high"``
  for USD-positive assets (USD, T-bonds). **R3 (sub-fase 12.7)**:
  utvidet med horisont-bevisste modes via ``params["mode"]``. Default-
  output (mode=None) er bit-identisk pre-R3.

- ``dxy_chg5d``: 5-dager rolling % endring i DTWEXBGS (broad dollar
  index). USD-styrke. Default ``bull_when="negative"`` (USD-svakhet
  støtter risk-on / metaller). ``"positive"`` for USD-relaterte longs.

- ``vix_regime``: VIXCLS klassifisert som lav/normal/høy regime.
  Mappet til 0..1 via params. Default tolket som risk-on score
  (lav VIX → høy score) — passer assets som blomstrer i lavt-vol-
  regime. ``invert=True`` for hedger-assets (Gold som safe-haven).

Alle drivere er asset-class-agnostic: dataen er felles, men
tolkningen drives av YAML-params. Defensive 0.0-fallbacks ved
manglende fundamentals-serie eller utilstrekkelig historikk.

Driver-funksjoner trenger ingen ``cot_contract`` — de leser FRED-
serier som er felles på tvers av instrumenter. ``instrument``-
parameteren brukes kun for logging.

real_yield-spesifikk (R3):
- ``mode``: feature-velger. ``None``/utelatt (default) = dagens
  terskel-trapp på absolutt real-yield-nivå (bit-identisk pre-R3).
  ``"pct_12m"`` = rank-percentile over 252 trading-days, bull_when-
  invertert. ``"pct_36m"`` = 756 trading-days, fall-back til pct_12m
  ved utilstrekkelig historikk. ``"delta_5d_z"`` = z-score av 5d
  trading-days-delta over 252-obs-vindu, mappet via momentum-trapp
  med bull_when-respekt. ``"delta_20d_z"`` = 20d-delta. ``"extreme_
  flag_hard"`` / ``"extreme_flag_soft"`` = 1.0 ved 2/98- eller
  5/95-percentile-tersklene (bull_when-agnostisk — ekstremitet er
  symmetrisk).
- ``_horizon``: engine-injisert per ADR-010. Lest men ikke brukt for
  output-endring i R3.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register
from bedrock.engine.drivers._stats import (
    MIN_OBS_FOR_PCTILE,
    rank_percentile,
    rolling_z,
)

# R3 mode-helpers — konsolidert til horizon_helpers.py i D1 (session 127).
# Re-eksporteres under gamle navn (med _-prefiks) for bakoverkompatibilitet
# med eksisterende lazy-import-referanser fra agronomy.py + currency.py.
from bedrock.engine.drivers.horizon_helpers import (
    DELTA_5D_DAYS as _DELTA_5D_DAYS,
)
from bedrock.engine.drivers.horizon_helpers import (
    DELTA_5D_WEEKS as _DELTA_5D_WEEKS,
)
from bedrock.engine.drivers.horizon_helpers import (
    DELTA_20D_DAYS as _DELTA_20D_DAYS,
)
from bedrock.engine.drivers.horizon_helpers import (
    DELTA_20D_WEEKS as _DELTA_20D_WEEKS,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_DELTA_DAILY as _LOOKBACK_DELTA_DAILY,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_DELTA_WEEKLY as _LOOKBACK_DELTA_WEEKLY,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_PCT_12M_DAILY as _LOOKBACK_PCT_12M_DAILY,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_PCT_12M_WEEKLY as _LOOKBACK_PCT_12M_WEEKLY,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_PCT_36M_DAILY as _LOOKBACK_PCT_36M_DAILY,
)
from bedrock.engine.drivers.horizon_helpers import (
    LOOKBACK_PCT_36M_WEEKLY as _LOOKBACK_PCT_36M_WEEKLY,
)
from bedrock.engine.drivers.horizon_helpers import (
    extreme_flag as _extreme_flag,
)
from bedrock.engine.drivers.horizon_helpers import (
    fundamentals_delta_score as _fundamentals_delta_score,
)
from bedrock.engine.drivers.horizon_helpers import (
    fundamentals_extreme_flag as _fundamentals_extreme_flag,
)
from bedrock.engine.drivers.horizon_helpers import (
    fundamentals_pct_score as _fundamentals_pct_score,
)
from bedrock.engine.drivers.horizon_helpers import (
    normalize_bull_when_for_chg as _normalize_bull_when_for_chg,
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# real_yield
# ---------------------------------------------------------------------------


# Default terskler for real yield (i prosentpoeng).
# Keys: terskel for real_yield-verdi, value: score 0..1.
# `bull_when="low"` (Gold-default): låg real yield → høy score.
_DEFAULT_REAL_YIELD_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    (-0.5, 1.0),  # negative real yield = sterk bull
    (0.5, 0.75),  # < 0.5 real yield = bull
    (1.5, 0.5),  # 0.5-1.5 = nøytral
    (2.5, 0.25),  # 1.5-2.5 = bear-ish
)

# Speilet for `bull_when="high"` (f.eks. USD-bonds): høy real yield → høy score.
_DEFAULT_REAL_YIELD_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    (2.5, 1.0),
    (1.5, 0.75),
    (0.5, 0.5),
    (-0.5, 0.25),
)


def _compute_real_yield_series(store: Any, instrument: str, params: dict) -> pd.Series | None:
    """Bygg real-yield-serie (DGS10 − T10YIE), eller None ved feil.

    Felles loader for default-mode og R3-modes for å unngå duplisering
    av FRED-fetch-logikken.
    """
    nominal_id = params.get("nominal_series", "DGS10")
    inflation_id = params.get("inflation_series", "T10YIE")

    try:
        nominal = store.get_fundamentals(nominal_id)
        inflation = store.get_fundamentals(inflation_id)
    except KeyError as exc:
        _log.debug("real_yield.series_missing", instrument=instrument, error=str(exc))
        return None
    except Exception as exc:
        _log.warning("real_yield.fetch_failed", instrument=instrument, error=str(exc))
        return None

    real = (nominal - inflation).dropna()
    if real.empty:
        _log.debug("real_yield.no_overlap", instrument=instrument)
        return None
    return real


def _real_yield_default_score(current: float, bull_when: str, params: dict) -> float:
    """Pre-R3 default-output: terskel-trapp på absolutt real_yield-nivå.

    Bit-identisk med pre-R3-implementasjonen — ekstrahert til egen
    funksjon kun for å holde mode-dispatcheren lesbar.
    """
    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        if bull_when == "high":
            steps = _DEFAULT_REAL_YIELD_THRESHOLDS_HIGH
        else:
            steps = _DEFAULT_REAL_YIELD_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "high":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


@register("real_yield")
def real_yield(store: Any, instrument: str, params: dict) -> float:
    """Real yield (DGS10 − T10YIE) mappet til 0..1.

    Default (mode=None): konfigurerbar terskel-trapp på absolutt real-
    yield-nivå (bit-identisk med pre-R3).

    R3 (sub-fase 12.7): horisont-bevisst via ``params["mode"]``. Se
    docstring øverst i modulen for full mode-tabell. ``bull_when``
    respekteres på ALLE modes (pct_*, delta_*_z); extreme_flag-modes
    er bull_when-agnostiske per § 1.1.

    Params:
        nominal_series: FRED-serie for nominell yield (default ``DGS10``)
        inflation_series: FRED-serie for inflation expectation
            (default ``T10YIE``)
        bull_when: ``"low"`` (default) eller ``"high"``.
        thresholds: optional override for default-mode-trapp.
        mode: R3 feature-velger (None for default).

    Defensiv 0.0-retur ved manglende serier eller manglende overlapp.
    """
    horizon = params.get("_horizon")  # noqa: F841 — bevisst lest for ADR-010
    bull_when = params.get("bull_when", "low")
    mode = params.get("mode")

    real = _compute_real_yield_series(store, instrument, params)
    if real is None:
        return 0.0

    current = float(real.iloc[-1])

    if mode is None:
        return _real_yield_default_score(current, bull_when, params)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(real, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(real, bull_when, _LOOKBACK_PCT_36M_DAILY, instrument)
        if result is None:
            _log.info(
                "real_yield.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(real),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(real, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            real,
            bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            real,
            bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        # Beregn rå rank (uten bull_when-inversjon) — extreme_flag er
        # symmetrisk per § 1.1.
        if len(real) < MIN_OBS_FOR_PCTILE + 1:
            return 0.0
        window = (
            real.iloc[-(_LOOKBACK_PCT_12M_DAILY + 1) :]
            if len(real) > _LOOKBACK_PCT_12M_DAILY
            else real
        )
        if len(window) < MIN_OBS_FOR_PCTILE + 1:
            return 0.0
        history = [float(v) for v in window.iloc[:-1]]
        pct = rank_percentile(current, history)
        if pct is None:
            return 0.0
        return _extreme_flag(pct / 100.0, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "real_yield.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _real_yield_default_score(current, bull_when, params)


# ---------------------------------------------------------------------------
# dxy_chg5d
# ---------------------------------------------------------------------------


_DEFAULT_DXY_THRESHOLDS_NEGATIVE: tuple[tuple[float, float], ...] = (
    # USD-svakhet (negative endring) → høy score (default for Gold/risk-on)
    (-1.5, 1.0),  # < -1.5% = sterk USD-svakhet
    (-0.5, 0.75),
    (0.5, 0.5),  # ±0.5% = nøytral
    (1.5, 0.25),
)


_DEFAULT_DXY_THRESHOLDS_POSITIVE: tuple[tuple[float, float], ...] = (
    # USD-styrke (positive endring) → høy score (USD-relaterte longs)
    (1.5, 1.0),
    (0.5, 0.75),
    (-0.5, 0.5),
    (-1.5, 0.25),
)


# _normalize_bull_when_for_chg konsolidert til horizon_helpers.py i D1
# (session 127). Re-eksportert fra macro-modulen via top-level import for
# bakoverkompatibilitet.


@register("dxy_chg5d")
def dxy_chg5d(store: Any, instrument: str, params: dict) -> float:
    """5-dager % endring i ICE Dollar Index (`DX-Y.NYB`), mappet til 0..1.

    **D1 B3 (sub-fase 12.7, session 128):** kilde byttet fra FRED
    ``DTWEXBGS`` (Federal Reserve broad dollar, 26 valutaer) til Yahoo
    ``DX-Y.NYB`` (ICE Dollar Index, 6-valuta basket: EUR/JPY/GBP/CAD/SEK/CHF).
    ICE-DXY er markedsstandard og det handlere faktisk handler på.
    Fundamentals-tabellen lagrer Yahoo-close som pseudo-FRED-serie med
    series_id=``DX-Y.NYB``. Backfill-script:
    ``scripts/backfill/dxy_yahoo.py``. ``DTWEXBGS`` beholdes i fundamentals
    som sekundær (eksisterende FRED-fetcher henter den fortsatt) — bruk
    ``params={"series": "DTWEXBGS"}`` for å bytte tilbake.

    Params:
        series: kilde-serie i fundamentals-tabellen. Default ``DX-Y.NYB``
            (Yahoo ICE-DXY). Sekundær: ``DTWEXBGS`` (FRED broad dollar).
        window: rolling-vindu i dager (default 5). Signalvinduer >5
            gir mer stabilt signal men reagerer saktere.
        bull_when: ``"negative"`` (default — USD-svakhet er bull for
            risk-on / Gold) eller ``"positive"`` (USD-styrke er bull
            for USD-relaterte longs).
        thresholds: optional override.
        mode: R4 feature-velger per ADR-010. ``None``/utelatt (default) =
            dagens 5d-pct-change-trapp (bit-identisk pre-R4). Modes
            opererer på den underliggende DTWEXBGS-rå-serien
            (ikke pct-change-output): ``"pct_12m"``/``"pct_36m"``/
            ``"delta_5d_z"``/``"delta_20d_z"``/``"extreme_flag_*"`` per
            § 1.1. ``bull_when="negative"`` på rå-serien tolkes som
            "low" (lav DXY = USD-svakhet = bull). delta_5d_z på rå-
            serien er IKKE samme som default 5d-pct-change — modes er
            parallelle aggregeringer, ikke "delta av default-output".
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Defensiv 0.0-retur ved manglende DTWEXBGS-serie eller for kort
    historikk.
    """
    # ADR-010: les _horizon for fremtidig bruk. R4-kontrakt: ikke endre
    # default-output basert på _horizon.
    _horizon = params.get("_horizon")
    # D1 B3 (session 128): default byttet fra FRED DTWEXBGS til Yahoo
    # ICE Dollar Index (DX-Y.NYB). Lagret i fundamentals via
    # scripts/backfill/dxy_yahoo.py.
    series_id = params.get("series", "DX-Y.NYB")
    bull_when = params.get("bull_when", "negative")
    mode = params.get("mode")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("dxy_chg5d.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("dxy_chg5d.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if mode is None:
        return _dxy_chg5d_default(series, bull_when, params, instrument)

    # Mode-banen opererer på rå-serien; bull_when normaliseres til
    # helper-konvensjonen (negative→low, positive→high).
    helper_bull_when = _normalize_bull_when_for_chg(bull_when)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_36M_DAILY, instrument
        )
        if result is None:
            _log.info(
                "dxy_chg5d.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(
                series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "dxy_chg5d.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _dxy_chg5d_default(series, bull_when, params, instrument)


def _dxy_chg5d_default(series: pd.Series, bull_when: str, params: dict, instrument: str) -> float:
    """Pre-R4-default-bane for dxy_chg5d: 5d-pct-change-trapp.

    Isolert i egen helper for å garantere bit-identisk pre-R4-output
    uavhengig av om mode-dispatcher rammer fall-back-grenen.
    """
    window = int(params.get("window", 5))

    if len(series) < window + 1:
        _log.debug(
            "dxy_chg5d.short_history",
            instrument=instrument,
            n=len(series),
            window=window,
        )
        return 0.0

    pct_change = (series.iloc[-1] - series.iloc[-window - 1]) / series.iloc[-window - 1] * 100
    if pd.isna(pct_change):
        return 0.0
    current = float(pct_change)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        if bull_when == "positive":
            steps = _DEFAULT_DXY_THRESHOLDS_POSITIVE
        else:
            steps = _DEFAULT_DXY_THRESHOLDS_NEGATIVE
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "positive":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# brl_chg5d
# ---------------------------------------------------------------------------


# BRL er ~2x mer volatil enn DXY (5d stdev: BRL 2.06% vs DXY ~0.8%).
# Terskler skalert deretter, basert på empirisk percentil-fordeling
# 2010-2026: p90=+2.65%, p75=+1.28%, p25=-1.10%, p10=-2.28%.
_DEFAULT_BRL_THRESHOLDS_POSITIVE: tuple[tuple[float, float], ...] = (
    # USDBRL UP = BRL svakhet → bull for brasiliansk-eksport (sukker, kaffe)
    (2.5, 1.0),
    (1.0, 0.75),
    (-1.0, 0.5),  # ±1% = nøytral
    (-2.5, 0.25),
)


_DEFAULT_BRL_THRESHOLDS_NEGATIVE: tuple[tuple[float, float], ...] = (
    # USDBRL DOWN = BRL styrke → bull for BRL-positive assets
    (-2.5, 1.0),
    (-1.0, 0.75),
    (1.0, 0.5),
    (2.5, 0.25),
)


@register("brl_chg5d")
def brl_chg5d(store: Any, instrument: str, params: dict) -> float:
    """5-dager % endring i USD/BRL (DEXBZUS), mappet til 0..1.

    Sub-fase 12.5+ session 80: erstatter DXY-proxy for BRL-eksponerte
    softs (sukker, kaffe). DEXBZUS = "Brazilian Reals to One U.S.
    Dollar" — altså DEXBZUS UP = BRL svakhet.

    Params:
        series: FRED-serie (default ``DEXBZUS``)
        window: rolling-vindu i dager (default 5)
        bull_when: ``"positive"`` (default — USDBRL UP = BRL-svakhet
            = bull for brasiliansk-eksport: sukker, kaffe) eller
            ``"negative"`` (BRL-styrke er bull).
        thresholds: optional override.
        mode: R4 feature-velger per ADR-010. ``None``/utelatt (default) =
            dagens 5d-pct-change-trapp. Modes opererer på underliggende
            DEXBZUS rå-serien (samme pattern som dxy_chg5d).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Defensiv 0.0-retur ved manglende serie eller for kort historikk.
    """
    # ADR-010: les _horizon for fremtidig bruk.
    _horizon = params.get("_horizon")
    series_id = params.get("series", "DEXBZUS")
    bull_when = params.get("bull_when", "positive")
    mode = params.get("mode")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("brl_chg5d.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("brl_chg5d.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if mode is None:
        return _brl_chg5d_default(series, bull_when, params, instrument)

    helper_bull_when = _normalize_bull_when_for_chg(bull_when)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_36M_DAILY, instrument
        )
        if result is None:
            _log.info(
                "brl_chg5d.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(
                series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "brl_chg5d.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _brl_chg5d_default(series, bull_when, params, instrument)


def _brl_chg5d_default(series: pd.Series, bull_when: str, params: dict, instrument: str) -> float:
    """Pre-R4-default-bane for brl_chg5d: 5d-pct-change-trapp på DEXBZUS."""
    window = int(params.get("window", 5))

    if len(series) < window + 1:
        _log.debug("brl_chg5d.short_history", instrument=instrument, n=len(series), window=window)
        return 0.0

    pct_change = (series.iloc[-1] - series.iloc[-window - 1]) / series.iloc[-window - 1] * 100
    if pd.isna(pct_change):
        return 0.0
    current = float(pct_change)

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = (
            _DEFAULT_BRL_THRESHOLDS_POSITIVE
            if bull_when == "positive"
            else _DEFAULT_BRL_THRESHOLDS_NEGATIVE
        )
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "positive":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# vix_regime
# ---------------------------------------------------------------------------


# VIX-regimene. Kilder: VIX < 15 = lav vol, 15-25 = normal, > 25 = forhøyet.
_DEFAULT_VIX_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (15.0, 1.0),  # låg vol = risk-on bull (default; invert for safe-havens)
    (20.0, 0.75),
    (25.0, 0.5),
    (35.0, 0.25),
)


@register("vix_regime")
def vix_regime(store: Any, instrument: str, params: dict) -> float:
    """VIX-baseri regime-klassifikator, mappet til 0..1.

    Params:
        series: FRED-serie (default ``VIXCLS``)
        invert: ``False`` (default) — låg VIX = risk-on = høy score.
            ``True`` for safe-haven-assets (Gold, US-bonds) som
            blomstrer når VIX er forhøyet.
        thresholds: optional override.
        mode: R4 feature-velger per ADR-010. ``None``/utelatt (default) =
            dagens regime-klassifikator basert på siste VIX-verdi
            (bit-identisk pre-R4). Modes opererer på rolling VIX-serien:
            ``"pct_12m"`` = "hvor høy VIX er relativt til 12m historikk",
            ``"delta_5d_z"`` = "z-score av 5d VIX-endring", osv.
            ``invert``-param oversettes til bull_when via
            _normalize_invert_to_bull_when (invert=False ⇒ "low" siden
            lav VIX = bull; invert=True ⇒ "high" siden høy VIX = bull
            for safe-havens). delta_*_z-modes på en VIX-serie tolker
            "økning i VIX-z-score" — typisk bearish for risk-on, bullish
            for hedger.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Default-terskler:
        VIX ≤ 15 → 1.0 (rolig marked)
        VIX ≤ 20 → 0.75
        VIX ≤ 25 → 0.5
        VIX ≤ 35 → 0.25
        VIX > 35 → 0.0 (krise-regime)
    """
    # ADR-010: les _horizon for fremtidig bruk.
    _horizon = params.get("_horizon")
    series_id = params.get("series", "VIXCLS")
    invert = bool(params.get("invert", False))
    mode = params.get("mode")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("vix_regime.series_missing", instrument=instrument, series=series_id)
        return 0.0
    except Exception as exc:
        _log.warning("vix_regime.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if series.empty:
        return 0.0

    if mode is None:
        return _vix_regime_default(series, invert, params)

    # invert=False: lav VIX = bull (risk-on default) ⇒ helper bull_when="low"
    # invert=True: høy VIX = bull (safe-haven) ⇒ helper bull_when="high"
    helper_bull_when = "high" if invert else "low"

    if mode == "pct_12m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(
            series, helper_bull_when, _LOOKBACK_PCT_36M_DAILY, instrument
        )
        if result is None:
            _log.info(
                "vix_regime.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M_DAILY + 1,
            )
            result = _fundamentals_pct_score(
                series, helper_bull_when, _LOOKBACK_PCT_12M_DAILY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            helper_bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "vix_regime.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _vix_regime_default(series, invert, params)


def _vix_regime_default(series: pd.Series, invert: bool, params: dict) -> float:
    """Pre-R4-default-bane for vix_regime: regime-klassifikator på siste VIX."""
    current = float(series.iloc[-1])

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_VIX_THRESHOLDS
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    # Default-mapping: lav VIX = høy score (test ascending).
    score = 0.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break

    if invert:
        # Safe-haven-tolkning: 1.0 ↔ 0.0, 0.75 ↔ 0.25, 0.5 stays.
        return round(1.0 - score, 4)
    return score


# ---------------------------------------------------------------------------
# B1 D1 (sub-fase 12.7, session 129)
#
# Fire macro-drivere som leser FRED-fundamentals utvidet med 10 nye serier:
#   - foreign 10Y (DE/GB/JP/AU) for yield-diff
#   - AAA10Y / BAA10Y for credit-spread (V2-substitusjon for HY/IG OAS som
#     kun ga 3 år gratis-API-historikk; AAA10Y/BAA10Y har 30+ år)
#   - WALCL / RRPONTSYD / WTREGEN for NetFedLiq
#   - NFCI for Chicago Fed Financial Conditions Index
#
# Frekvens-noter:
#   - DGS10/AAA10Y/BAA10Y: daglig
#   - IRLTLT01<XX>M156N: månedlig — yield-diff-serien (DGS10 - foreign)
#     blir effektivt månedlig etter dropna
#   - WALCL/RRPONTSYD/WTREGEN: ukentlig (ons)
#   - NFCI: ukentlig (fre)
#
# Per ADR-010: alle fire eksponerer R4-modes (pct_*/delta_*_z/extreme_*)
# men yield_diff_10y har færre obs → kun pct_36m + extreme støttes.
# ---------------------------------------------------------------------------

# yield_diff_10y default-trapper. bull_when="low" = lav diff (foreign yield
# nær eller over US) er bull for foreign-currency. EURUSD/GBPUSD/AUDUSD er
# default; USDJPY bruker "high".
_DEFAULT_YIELD_DIFF_10Y_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    (-0.5, 1.0),  # foreign yield > US +0.5 = sterk bull foreign-CCY
    (0.5, 0.75),  # nær paritet = mild bull
    (1.5, 0.5),  # ±1.5 = nøytral
    (2.5, 0.25),  # US tydelig høyere = bear foreign
)

_DEFAULT_YIELD_DIFF_10Y_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    # Speilet for USDJPY-style: høy diff = USD strong = bull pair
    (2.5, 1.0),
    (1.5, 0.75),
    (0.5, 0.5),
    (-0.5, 0.25),
)

# Yield-diff-serien er månedlig; 36-obs tilsvarer 3 år.
_LOOKBACK_PCT_36M_MONTHLY = 36
_LOOKBACK_PCT_12M_MONTHLY = 12  # kun 12 obs — under MIN_OBS_FOR_PCTILE; brukes ikke i pct_12m.


@register("yield_diff_10y")
def yield_diff_10y(store: Any, instrument: str, params: dict) -> float:
    """US 10Y minus foreign 10Y yield-differensial, mappet til 0..1.

    B1 D1 (sub-fase 12.7, session 129). Påvirker FX-instrumenter (EURUSD,
    GBPUSD, USDJPY, AUDUSD) i macro-familien. Yield-diff er primær FX-
    fundamental: høy US-yield-diff trekker kapital til USD, lav diff
    presser USD ned vs foreign.

    Frekvens-noter:
        - DGS10 er daglig, IRLTLT01<XX>M156N er månedlig (FRED-OECD-feed).
        - Etter (us - foreign).dropna() blir serien effektivt månedlig.
        - pct_12m gir for få obs (12 < MIN_OBS_FOR_PCTILE=20) → faller
          tilbake til pct_36m.
        - delta_*_z støttes ikke (månedlig data); fall-back til default.

    Params:
        foreign_series (REQUIRED): FRED-serie for foreign 10Y. F.eks.
            ``IRLTLT01DEM156N`` (Tyskland), ``IRLTLT01GBM156N`` (UK),
            ``IRLTLT01JPM156N`` (Japan), ``IRLTLT01AUM156N`` (Australia).
        us_series: US 10Y (default ``DGS10``).
        bull_when: ``"low"`` (default — lav diff = bull foreign vs USD;
            EURUSD/GBPUSD/AUDUSD-tolkning) eller ``"high"`` (USDJPY:
            høy diff = USD strong = bull pair).
        thresholds: optional liste av (terskel, score)-par.
        mode: R4 feature-velger. ``None`` (default) = terskel-trapp.
            Støttede modes: ``"pct_36m"``, ``"extreme_flag_hard"``,
            ``"extreme_flag_soft"``. ``"pct_12m"`` faller til pct_36m.
            ``"delta_5d_z"``/``"delta_20d_z"`` fall-back til default.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Defensive 0.0 ved manglende serier eller ingen overlapp.
    """
    _horizon = params.get("_horizon")
    foreign_series = params.get("foreign_series")
    if not foreign_series:
        _log.warning("yield_diff_10y.no_foreign_series", instrument=instrument)
        return 0.0
    us_series = params.get("us_series", "DGS10")
    bull_when = params.get("bull_when", "low")
    mode = params.get("mode")

    try:
        us = store.get_fundamentals(us_series).dropna()
        foreign = store.get_fundamentals(foreign_series).dropna()
    except KeyError as exc:
        _log.debug("yield_diff_10y.series_missing", instrument=instrument, error=str(exc))
        return 0.0
    except Exception as exc:
        _log.warning("yield_diff_10y.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    diff = (us - foreign).dropna()
    if diff.empty:
        _log.debug("yield_diff_10y.no_overlap", instrument=instrument)
        return 0.0

    current = float(diff.iloc[-1])

    if mode is None:
        return _yield_diff_10y_default_score(current, bull_when, params)

    if mode in ("pct_12m", "pct_36m"):
        # Begge bruker 36-obs-vindu for å sikre nok obs (12 obs er under
        # MIN_OBS_FOR_PCTILE). pct_12m logges som fall-back.
        if mode == "pct_12m":
            _log.info(
                "yield_diff_10y.pct_12m_fallback_to_36m",
                instrument=instrument,
                reason="monthly_data_insufficient_for_12m_window",
            )
        result = _fundamentals_pct_score(diff, bull_when, _LOOKBACK_PCT_36M_MONTHLY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            diff,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_36M_MONTHLY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # delta_*_z er ikke meningsfullt for månedlig data; fall-back.
    _log.warning(
        "yield_diff_10y.unsupported_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _yield_diff_10y_default_score(current, bull_when, params)


def _yield_diff_10y_default_score(current: float, bull_when: str, params: dict) -> float:
    """Default-trapp på diff-verdi i prosentpoeng."""
    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = (
            _DEFAULT_YIELD_DIFF_10Y_THRESHOLDS_HIGH
            if bull_when == "high"
            else _DEFAULT_YIELD_DIFF_10Y_THRESHOLDS_LOW
        )
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    if bull_when == "high":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if current >= threshold:
                return float(score)
    else:
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if current <= threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# credit_spread_change (B1 D1)
# ---------------------------------------------------------------------------

# Step-mapping for spread-delta z-score. Sterk negativ delta (spreads
# komprimerer) = risk-on = bull risk-on-assets. Tilsvarer positioning-
# trappen i andre delta-baserte drivere.
_DEFAULT_CREDIT_DELTA_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    # bull_when="low": lav spread-delta (komprimering) = bull
    (-2.0, 1.0),  # sterk komprimering = sterk bull
    (-1.0, 0.75),
    (-0.5, 0.6),
    (0.0, 0.5),
    (0.5, 0.3),
)

# Default-trapp på SPREAD-NIVÅ (BAA10Y - AAA10Y) i prosentpoeng.
# Lav spread = lav credit-stress = bull risk-on. Historisk normalrange
# 0.6-1.2 pp; kriser 2.5-4.0 pp.
_DEFAULT_CREDIT_LEVEL_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    (0.6, 1.0),  # svært komprimert = sterk risk-on
    (0.9, 0.75),
    (1.2, 0.5),  # normal-range = nøytral
    (1.8, 0.25),
)


@register("credit_spread_change")
def credit_spread_change(store: Any, instrument: str, params: dict) -> float:
    """BAA10Y − AAA10Y kreditt-spread, mappet til 0..1.

    B1 D1 (sub-fase 12.7, session 129). V2-substitusjon for HY/IG OAS
    (BAMLH0A0HYM2/BAMLC0A0CM ga kun 3 år gratis FRED-API-historikk;
    Moody's AAA10Y/BAA10Y har 30+ år).

    Spread = BAA10Y − AAA10Y representerer credit-stress (BAA-IG-junior
    over AAA-IG-senior). Komprimerer i risk-on-regimer, ekspanderer i
    risk-off / kreditt-kriser.

    Default-tolkning (bull_when="low"): lav spread = lav credit-stress =
    bull for risk-on-aktiva (Nasdaq, SP500, BTC, ETH). bull_when="high"
    for safe-haven (Gold) der bredere spread = flight-to-quality.

    Begge serier er daglige, så delta_5d_z/delta_20d_z er meningsfulle
    her (motsetning yield_diff_10y som er månedlig).

    Params:
        baa_series: BAA-serie (default ``BAA10Y``).
        aaa_series: AAA-serie (default ``AAA10Y``).
        bull_when: ``"low"`` (default — risk-on) eller ``"high"`` (safe-
            haven). Hard-coded ``"low"`` om mode er delta_*_z og bruker
            ikke spesifiserer (default delta-mapping er negativ-delta-
            bull).
        thresholds: override default-trapp (kun for default mode).
        mode: feature-velger per ADR-010. Modes: ``"pct_12m"``,
            ``"pct_36m"``, ``"delta_5d_z"``, ``"delta_20d_z"``,
            ``"extreme_flag_hard"``, ``"extreme_flag_soft"``.
        _horizon: engine-injisert. Lest, ikke brukt i R4.

    Defensive 0.0 ved manglende serier eller ingen overlapp.
    """
    _horizon = params.get("_horizon")
    baa_id = params.get("baa_series", "BAA10Y")
    aaa_id = params.get("aaa_series", "AAA10Y")
    bull_when = params.get("bull_when", "low")
    mode = params.get("mode")

    try:
        baa = store.get_fundamentals(baa_id).dropna()
        aaa = store.get_fundamentals(aaa_id).dropna()
    except KeyError as exc:
        _log.debug("credit_spread_change.series_missing", instrument=instrument, error=str(exc))
        return 0.0
    except Exception as exc:
        _log.warning("credit_spread_change.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    spread = (baa - aaa).dropna()
    if spread.empty:
        _log.debug("credit_spread_change.no_overlap", instrument=instrument)
        return 0.0

    current = float(spread.iloc[-1])

    if mode is None:
        return _credit_spread_change_default(current, bull_when, params)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(spread, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(spread, bull_when, _LOOKBACK_PCT_36M_DAILY, instrument)
        if result is None:
            result = _fundamentals_pct_score(spread, bull_when, _LOOKBACK_PCT_12M_DAILY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            spread,
            bull_when,
            delta_days=_DELTA_5D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            spread,
            bull_when,
            delta_days=_DELTA_20D_DAYS,
            lookback=_LOOKBACK_DELTA_DAILY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            spread,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_DAILY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "credit_spread_change.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _credit_spread_change_default(current, bull_when, params)


def _credit_spread_change_default(current: float, bull_when: str, params: dict) -> float:
    """Default-trapp på spread-NIVÅ (ikke delta — det fanges av delta-modes).

    Lav spread = lav credit-stress = høy score for bull_when="low".
    """
    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_CREDIT_LEVEL_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    # Trappen er definert ascending (lav spread → høy score for "low").
    score = 0.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break

    if bull_when == "high":
        # Speil for safe-haven: høy spread = bull → invertér.
        return round(1.0 - score, 4)
    return score


# ---------------------------------------------------------------------------
# nfci_change (B1 D1) — Chicago Fed National Financial Conditions Index
# ---------------------------------------------------------------------------

# NFCI default level-trapp. NFCI=0 = average financial conditions; positiv =
# tighter, negativ = looser. Lav NFCI = looser conditions = bull risk-on.
_DEFAULT_NFCI_LEVEL_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    (-1.0, 1.0),  # mye løsere enn snitt = sterk bull risk-on
    (-0.5, 0.75),
    (0.0, 0.5),  # gjennomsnitt = nøytral
    (0.5, 0.25),
    (1.0, 0.1),  # tighter = bear risk-on
)


@register("nfci_change")
def nfci_change(store: Any, instrument: str, params: dict) -> float:
    """Chicago Fed NFCI (National Financial Conditions Index), 0..1.

    B1 D1 (sub-fase 12.7, session 129). NFCI er en sammensatt indeks over
    risiko, kreditt og leverage i USA: 0 = gjennomsnitt over 1971-, positiv
    = tighter (mer stress), negativ = looser. Ukentlig (fre) FRED-rapport.

    Default-tolkning (bull_when="low"): lav NFCI = looser conditions =
    bull for risk-on-aktiva. bull_when="high" for hedge-aktiva (Gold).

    NFCI er ukentlig — bruker WEEKLY-vinduer (LOOKBACK_PCT_12M_WEEKLY=52,
    DELTA_5D_WEEKS=1).

    Params:
        series: FRED-serie (default ``NFCI``).
        bull_when: ``"low"`` (default) eller ``"high"``.
        thresholds: optional override.
        mode: per ADR-010. Modes: ``"pct_12m"``, ``"pct_36m"``,
            ``"delta_5d_z"`` (1-rapport-delta), ``"delta_20d_z"``
            (4-rapport-delta), ``"extreme_flag_hard"``,
            ``"extreme_flag_soft"``.
        _horizon: engine-injisert.

    Defensive 0.0 ved manglende serie.
    """
    _horizon = params.get("_horizon")
    series_id = params.get("series", "NFCI")
    bull_when = params.get("bull_when", "low")
    mode = params.get("mode")

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.debug("nfci_change.series_missing", instrument=instrument)
        return 0.0
    except Exception as exc:
        _log.warning("nfci_change.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if series.empty:
        return 0.0

    current = float(series.iloc[-1])

    if mode is None:
        return _nfci_change_default(current, bull_when, params)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(series, bull_when, _LOOKBACK_PCT_36M_WEEKLY, instrument)
        if result is None:
            result = _fundamentals_pct_score(
                series, bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_5D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            series,
            bull_when,
            delta_days=_DELTA_20D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            series,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_WEEKLY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "nfci_change.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _nfci_change_default(current, bull_when, params)


def _nfci_change_default(current: float, bull_when: str, params: dict) -> float:
    """Default-trapp på NFCI-NIVÅ. Lav NFCI = bull for bull_when='low'."""
    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_NFCI_LEVEL_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = 0.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break
    else:
        score = 0.0  # ingen terskel matchet → høyere enn alle = bear

    if bull_when == "high":
        return round(1.0 - score, 4)
    return score


# ---------------------------------------------------------------------------
# net_fed_liq_change (B1 D1)
# ---------------------------------------------------------------------------

# Default-trapp på NetFedLiq-NIVÅ-pct-endring (year-over-year fungerer ikke
# her siden alle 3 inputs har høy autokorrelasjon — vi bruker 4-uke pct-
# endring som er mer responsiv). bull_when="high" = liquidity-vekst er bull.
_DEFAULT_NETFEDLIQ_PCT_THRESHOLDS_HIGH: tuple[tuple[float, float], ...] = (
    # bull_when="high": positiv pct-endring = liquidity-injeksjon = bull
    (2.0, 1.0),  # > 2% 4w-vekst = sterk QE
    (1.0, 0.75),
    (0.0, 0.5),  # flat = nøytral
    (-1.0, 0.25),
    (-2.0, 0.1),  # < -2% = sterk QT = bear
)


@register("net_fed_liq_change")
def net_fed_liq_change(store: Any, instrument: str, params: dict) -> float:
    """Net Federal Reserve Liquidity = WALCL − RRPONTSYD − WTREGEN, 0..1.

    B1 D1 (sub-fase 12.7, session 129). NetFedLiq tracker den effektive
    likviditeten i markedet etter at Fed's balance sheet (WALCL) er
    justert for cash som sitter i RRP-fasiliteten (RRPONTSYD) og Treasury
    General Account (WTREGEN). Stigende NetFedLiq = liquidity-flow inn
    i risk-aktiva.

    Tre input-serier alle ukentlige (ons). Default-mode bruker 4-uke pct-
    endring som signal (mer responsiv enn level — selve nivået er trended
    over tid og lav-informativt).

    Tolkning (bull_when="high"): vekst i NetFedLiq = bull risk-on.
    bull_when="low" for kontrære posisjoner.

    Params:
        walcl_series: default ``WALCL``.
        rrp_series: default ``RRPONTSYD``.
        tga_series: default ``WTREGEN``.
        bull_when: ``"high"`` (default — risk-on) eller ``"low"``.
        chg_window_weeks: 4-uke endring (default 4 — månedlig kadens).
        thresholds: optional override.
        mode: ``"pct_12m"``, ``"pct_36m"``, ``"delta_5d_z"``,
            ``"delta_20d_z"``, ``"extreme_flag_hard"``,
            ``"extreme_flag_soft"``. Modes opererer på NetFedLiq-rå-
            serien (ikke pct-change-output) per dxy_chg5d-presedens.
        _horizon: engine-injisert.

    Defensive 0.0 ved manglende serier.
    """
    _horizon = params.get("_horizon")
    walcl_id = params.get("walcl_series", "WALCL")
    rrp_id = params.get("rrp_series", "RRPONTSYD")
    tga_id = params.get("tga_series", "WTREGEN")
    bull_when = params.get("bull_when", "high")
    mode = params.get("mode")

    try:
        walcl = store.get_fundamentals(walcl_id).dropna()
        rrp = store.get_fundamentals(rrp_id).dropna()
        tga = store.get_fundamentals(tga_id).dropna()
    except KeyError as exc:
        _log.debug("net_fed_liq_change.series_missing", instrument=instrument, error=str(exc))
        return 0.0
    except Exception as exc:
        _log.warning("net_fed_liq_change.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    # WALCL er i USD millions; RRP og TGA i USD millions (FRED units
    # matcher). Linje-by-linje subtraksjon på felles datoer (alle ukentlig
    # ons → bør allerede være justert).
    aligned = pd.concat([walcl, rrp, tga], axis=1, join="inner")
    if aligned.empty:
        _log.debug("net_fed_liq_change.no_overlap", instrument=instrument)
        return 0.0

    aligned.columns = ["walcl", "rrp", "tga"]
    net_liq = (aligned["walcl"] - aligned["rrp"] - aligned["tga"]).dropna()
    if net_liq.empty:
        return 0.0

    if mode is None:
        return _net_fed_liq_change_default(net_liq, bull_when, params)

    if mode == "pct_12m":
        result = _fundamentals_pct_score(net_liq, bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        result = _fundamentals_pct_score(net_liq, bull_when, _LOOKBACK_PCT_36M_WEEKLY, instrument)
        if result is None:
            result = _fundamentals_pct_score(
                net_liq, bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        result = _fundamentals_delta_score(
            net_liq,
            bull_when,
            delta_days=_DELTA_5D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        result = _fundamentals_delta_score(
            net_liq,
            bull_when,
            delta_days=_DELTA_20D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        result = _fundamentals_extreme_flag(
            net_liq,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_WEEKLY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    _log.warning(
        "net_fed_liq_change.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _net_fed_liq_change_default(net_liq, bull_when, params)


def _net_fed_liq_change_default(net_liq: pd.Series, bull_when: str, params: dict) -> float:
    """Default-bane: 4-uke pct-endring i NetFedLiq, mappet via terskel-trapp."""
    chg_window = int(params.get("chg_window_weeks", 4))
    if len(net_liq) <= chg_window:
        return 0.0

    current = float(net_liq.iloc[-1])
    prev = float(net_liq.iloc[-1 - chg_window])
    if prev == 0:
        return 0.0

    pct_chg = ((current - prev) / abs(prev)) * 100.0

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_NETFEDLIQ_PCT_THRESHOLDS_HIGH
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    # Default-trappen er definert som "high"-aware (positiv = bull).
    if bull_when == "high":
        for threshold, score in sorted(steps, key=lambda t: -t[0]):
            if pct_chg >= threshold:
                return float(score)
    else:
        # bull_when="low": speil — negativ pct-endring = bull (kontrært)
        for threshold, score in sorted(steps, key=lambda t: t[0]):
            if pct_chg <= -threshold:
                return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# eia_stock_change (sub-fase 12.5+ session 107)
# ---------------------------------------------------------------------------

# Default z-mapping for eia_stock_change. Speilet av cot_z_score-trappen:
# z ≥ +2 → 1.0 (sterk draw, bullish), z ≥ +1 → 0.75, ..., z < -0.5 → 0.0
# (sterk build, bearish). NB: z er allerede invertert (-z(WoW%)) hvis
# invert=True (default), så skalaen virker direkte bullish.
_DEFAULT_EIA_Z_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (2.0, 1.0),
    (1.0, 0.75),
    (0.5, 0.6),
    (0.0, 0.5),
    (-0.5, 0.3),
)


def _load_eia_inventory_series(
    store: Any, instrument: str, series_id: str, *, n_obs: int
) -> pd.Series | None:
    """Hent EIA-inventory-serie (rå-verdier) som pd.Series.

    Felles loader for default-bane og R4-modes. Returnerer
    chronologisk sortert serie (siste obs sist) eller None ved feil.
    """
    try:
        df = store.get_eia_inventory(series_id, last_n=n_obs)
    except KeyError:
        _log.debug(
            "eia_stock_change.data_missing",
            instrument=instrument,
            series_id=series_id,
        )
        return None
    except Exception as exc:
        _log.warning(
            "eia_stock_change.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return None

    values = pd.Series(pd.to_numeric(df["value"], errors="coerce")).dropna()
    if values.empty:
        return None
    return values


def _load_eia_pct_change_series(
    store: Any, instrument: str, series_id: str, *, n_obs: int
) -> pd.Series | None:
    """Hent WoW%-serien for EIA-inventory.

    Bygges som ``values.pct_change().dropna() * 100``. R4-modes kan
    deretter beregne pct-percentile / delta-z på pct-serien. Default-
    bane bruker også denne serien direkte (siste obs = current WoW%).

    Returnerer pd.Series med pct-change-verdier eller None ved feil/tom.
    """
    values = _load_eia_inventory_series(store, instrument, series_id, n_obs=n_obs + 1)
    if values is None:
        return None
    wow_pct = values.pct_change().dropna() * 100.0
    if wow_pct.empty:
        return None
    return wow_pct


@register("eia_stock_change")
def eia_stock_change(store: Any, instrument: str, params: dict) -> float:
    """Z-score av week-over-week % endring i EIA-inventories, mappet til 0..1.

    Logikk for energi (CrudeOil/Brent/NaturalGas) — default-tolkningen:
    - Store builds (positiv WoW%, lager bygger seg) = bearish for prising
    - Store draws (negativ WoW%, lager tappes) = bullish for prising

    Driver inverterer derfor z-score-fortegnet før step-mapping. Lookback
    52 uker = 1 år rolling baseline.

    R4 (sub-fase 12.7): horisont-bevisst via ``params["mode"]`` per
    ADR-010. Default-output (mode=None) er bit-identisk pre-R4 — kontraktuelt
    krav per § 5.3 (R4 = disiplin B, YAML uendret, score uendret).

    Mode-tabell (modes opererer på underliggende WoW%-serien — samme
    rådata default bruker):
    - ``None`` (default): z-score-trapp av siste WoW% vs 52-uke historikk,
      med invert (høy build = bearish per default). Bit-identisk pre-R4.
    - ``"pct_12m"``: rank-percentile av siste WoW% over 52-uke vindu,
      bull_when-aware via invert-flagget (invert=True ⇒ helper "low"
      siden lav WoW% = stock-draw = bullish).
    - ``"pct_36m"``: 156-uke vindu, fall-back til pct_12m + log.
    - ``"delta_5d_z"``: z-score av 1-rapport-delta i WoW%-serien
      (~7d natural). NB: dette er "endring i WoW%-distribusjon",
      ikke "endring i EIA-stock-nivå" — parallel aggregering, ikke
      "delta av default-output". Bull_when-aware.
    - ``"delta_20d_z"``: 4-rapport-delta (~28d natural).
    - ``"extreme_flag_hard"``: 1.0 ved WoW% pct ≥ 0.98 eller ≤ 0.02.
    - ``"extreme_flag_soft"``: 1.0 ved WoW% pct ≥ 0.95 eller ≤ 0.05.

    Params:
        series_id (REQUIRED): EIA-canonical (f.eks. ``"WCESTUS1"`` for crude,
            ``"WGTSTUS1"`` for gasoline, ``"NW2_EPG0_SWO_R48_BCF"`` for
            nat-gas). Kommer fra YAML-wiring.
        lookback_weeks: rolling-vindu for default (default 52). Modes
            overstyrer dette med _LOOKBACK_PCT_*_WEEKLY-konstanter.
        invert: ``True`` (default) — høy stock-build = bearish. Sett
            ``False`` hvis brukt for kontrarian-tolkning.
        z_thresholds: optional override av default-step-mapping.
        mode: R4 feature-velger per ADR-010 (se mode-tabell over).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt i R4.

    Returnerer:
    - 1.0 ved sterk uventet stock-draw (z ≥ +2 etter invertering)
    - 0.5 ved typisk WoW-endring
    - 0.0 ved sterk uventet stock-build

    Defensiv: alle feil → 0.0 + log.
    """
    # ADR-010: les _horizon for fremtidig bruk.
    _horizon = params.get("_horizon")
    series_id = params.get("series_id")
    if not series_id:
        _log.warning("eia_stock_change.no_series_id", instrument=instrument)
        return 0.0

    invert = bool(params.get("invert", True))
    mode = params.get("mode")

    if mode is None:
        return _eia_stock_change_default(store, instrument, series_id, invert, params)

    # Mode-banen opererer på WoW%-serien.
    # invert=True: høy WoW% (build) = bearish ⇒ helper bull_when="low"
    # invert=False: høy WoW% = bullish ⇒ helper bull_when="high"
    helper_bull_when = "low" if invert else "high"

    if mode == "pct_12m":
        wow_pct = _load_eia_pct_change_series(
            store, instrument, str(series_id), n_obs=_LOOKBACK_PCT_12M_WEEKLY + 1
        )
        if wow_pct is None:
            return 0.0
        result = _fundamentals_pct_score(
            wow_pct, helper_bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        wow_pct = _load_eia_pct_change_series(
            store, instrument, str(series_id), n_obs=_LOOKBACK_PCT_36M_WEEKLY + 1
        )
        if wow_pct is None:
            return 0.0
        result = _fundamentals_pct_score(
            wow_pct, helper_bull_when, _LOOKBACK_PCT_36M_WEEKLY, instrument
        )
        if result is None:
            _log.info(
                "eia_stock_change.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(wow_pct),
                required=_LOOKBACK_PCT_36M_WEEKLY + 1,
            )
            result = _fundamentals_pct_score(
                wow_pct, helper_bull_when, _LOOKBACK_PCT_12M_WEEKLY, instrument
            )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        wow_pct = _load_eia_pct_change_series(
            store,
            instrument,
            str(series_id),
            n_obs=_DELTA_5D_WEEKS + _LOOKBACK_DELTA_WEEKLY + 1,
        )
        if wow_pct is None:
            return 0.0
        result = _fundamentals_delta_score(
            wow_pct,
            helper_bull_when,
            delta_days=_DELTA_5D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        wow_pct = _load_eia_pct_change_series(
            store,
            instrument,
            str(series_id),
            n_obs=_DELTA_20D_WEEKS + _LOOKBACK_DELTA_WEEKLY + 1,
        )
        if wow_pct is None:
            return 0.0
        result = _fundamentals_delta_score(
            wow_pct,
            helper_bull_when,
            delta_days=_DELTA_20D_WEEKS,
            lookback=_LOOKBACK_DELTA_WEEKLY,
            instrument=instrument,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        wow_pct = _load_eia_pct_change_series(
            store, instrument, str(series_id), n_obs=_LOOKBACK_PCT_12M_WEEKLY + 1
        )
        if wow_pct is None:
            return 0.0
        result = _fundamentals_extreme_flag(
            wow_pct,
            hard=(mode == "extreme_flag_hard"),
            lookback=_LOOKBACK_PCT_12M_WEEKLY,
            instrument=instrument,
        )
        return result if result is not None else 0.0

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "eia_stock_change.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _eia_stock_change_default(store, instrument, series_id, invert, params)


def _eia_stock_change_default(
    store: Any, instrument: str, series_id: str, invert: bool, params: dict
) -> float:
    """Pre-R4-default-bane: z-score-trapp av siste WoW% vs 52-uke historikk."""
    from bedrock.engine.drivers._stats import MIN_OBS_FOR_PCTILE

    lookback = int(params.get("lookback_weeks", 52))

    values = _load_eia_inventory_series(store, instrument, str(series_id), n_obs=lookback + 2)
    if values is None:
        return 0.0

    if len(values) < MIN_OBS_FOR_PCTILE + 2:
        _log.debug(
            "eia_stock_change.short_history",
            instrument=instrument,
            n=len(values),
            required=MIN_OBS_FOR_PCTILE + 2,
        )
        return 0.0

    wow_pct = values.pct_change().dropna() * 100.0
    if len(wow_pct) < MIN_OBS_FOR_PCTILE + 1:
        return 0.0

    current = float(wow_pct.iloc[-1])
    history = [float(v) for v in wow_pct.iloc[:-1]]

    z = rolling_z(current, history)
    if z is None:
        return 0.0

    if invert:
        z = -z

    user_thresholds = params.get("z_thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_EIA_Z_THRESHOLDS
    else:
        if isinstance(user_thresholds, dict):
            steps_list: list[tuple[float, float]] = []
            for k, v in user_thresholds.items():
                key_str = str(k).replace("+", "")
                steps_list.append((float(key_str), float(v)))
            steps = tuple(sorted(steps_list, key=lambda t: -t[0]))
        else:
            steps = tuple(user_thresholds)

    for threshold, score in steps:
        if z >= threshold:
            return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# comex_stress (sub-fase 12.5+ session 108)
# ---------------------------------------------------------------------------


@register("comex_stress")
def comex_stress(store: Any, instrument: str, params: dict) -> float:
    """COMEX warehouse-stress score (0..1) for metals.

    Port av cot-explorer's `fetch_comex.py` `stress()`-funksjon (skala
    konvertert fra 0..100 → 0..1).

    Logikk:
        coverage = registered / total
        base = (1 - coverage) * 0.80
        + 0.15  hvis WoW%-endring < -5%  (registered faller raskt = stress)
        + 0.05  hvis WoW%-endring < 0%
        - 0.05  hvis WoW%-endring > +5%

    Tolkning: høy stress = supply tight = bullish for prising
    (få oz klare til delivery vs futures-shorts → squeeze-risk).
    Low stress = supply rikelig = bearish.

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren er domene-spesifikk
    (warehouse coverage + WoW-bonus); rolling-percentile på "stress-score"
    ville ødelegge den fysiske tolkningen. Per crop_progress-presedens:
    kun `_horizon`-lesing, ingen pct_*/delta_*-modes.

    Params:
        metal (REQUIRED): "gold" | "silver" | "copper" — bedrock-canonical.
            Kommer fra YAML-wiring.
        wow_window: antall handelsdager som teller som "uke" for WoW-
            sammenligning (default 5).
        copper_handling: hvis ``"skip"`` (default) returner 0.5 (nøytral)
            for kobber siden CME har fjernet reg/elig-skillet og
            coverage-baseberegningen ikke gir mening. ``"trend_only"``
            ignorerer base, bruker bare WoW-bonusene.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returnerer:
        float i [0, 1]. 0.5 ved tomt history. Defensive 0.0 ved feil.
    """
    # ADR-010: les _horizon for å oppfylle horisont-bevisst-konvensjonen.
    # Lest men ikke brukt — comex_stress er domene-spesifikk (warehouse
    # coverage). Per § 5.3 (R4-kontrakt for rank-baserte/domene-spesifikke
    # drivere): output uendret med eller uten _horizon.
    _horizon = params.get("_horizon")
    metal = params.get("metal")
    if not metal:
        _log.warning("comex_stress.no_metal_param", instrument=instrument)
        return 0.0

    wow_window = int(params.get("wow_window", 5))
    copper_handling = str(params.get("copper_handling", "skip"))

    try:
        df = store.get_comex_inventory(metal, last_n=wow_window + 5)
    except KeyError:
        _log.debug("comex_stress.data_missing", instrument=instrument, metal=metal)
        return 0.0
    except Exception as exc:
        _log.warning(
            "comex_stress.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    if len(df) == 0:
        return 0.5

    last = df.iloc[-1]
    registered = float(last["registered"])
    total = float(last["total"])

    is_copper = metal == "copper"

    # Kobber: CME har fjernet reg/elig-skillet → coverage-base meningsløs.
    if is_copper and copper_handling == "skip":
        score = 0.5  # nøytral start
    else:
        if total <= 0:
            return 0.5
        coverage = registered / total
        # Klamrer til [0, 1] for å håndtere edge-cases der reg > total
        coverage = max(0.0, min(1.0, coverage))
        score = (1.0 - coverage) * 0.80

    # WoW-bonus: hvis det finnes en rad ~wow_window dager tilbake.
    if len(df) > wow_window:
        prev_reg = float(df.iloc[-1 - wow_window]["registered"])
        if prev_reg > 0:
            chg_pct = (registered - prev_reg) / prev_reg
            if chg_pct < -0.05:
                score += 0.15
            elif chg_pct < 0:
                score += 0.05
            elif chg_pct > 0.05:
                score -= 0.05

    return max(0.0, min(1.0, round(score, 4)))


# ---------------------------------------------------------------------------
# mining_disruption (sub-fase 12.5+ session 109)
# ---------------------------------------------------------------------------

# Per-metall mapping fra mining-region-navn (cot-explorer-canonical) til
# global produksjonsandel. Vekt brukes til weighted score-aggregat:
# events i regioner med høyere produksjonsandel veier mer. Tall basert på
# 2024 USGS Mineral Commodity Summaries.
_REGION_WEIGHTS_BY_METAL: dict[str, dict[str, float]] = {
    "gold": {
        "Kina (Mongolia / Kina)": 0.10,
        "Mongolia / Kina": 0.10,
        "Australia": 0.10,
        "USA / Canada": 0.10,
        "Russland / Sibir": 0.09,
        "Sør-Afrika": 0.05,
        "Chile / Peru": 0.10,
        "Mexico / Mellom-Amerika": 0.04,
        "DRC / Zambia": 0.02,
        "Indonesia / Papua": 0.05,
        "Øst-Afrika": 0.06,  # Tanzania, Ghana etc.
    },
    "silver": {
        "Mexico / Mellom-Amerika": 0.23,
        "Chile / Peru": 0.18,
        "Mongolia / Kina": 0.13,
        "Russland / Sibir": 0.05,
        "Australia": 0.05,
        "USA / Canada": 0.06,
    },
    "copper": {
        "Chile / Peru": 0.40,  # Chile + Peru = ~40% global
        "DRC / Zambia": 0.15,
        "Mongolia / Kina": 0.10,
        "USA / Canada": 0.07,
        "Indonesia / Papua": 0.05,
        "Australia": 0.04,
        "Russland / Sibir": 0.04,
    },
    "platinum": {
        "Sør-Afrika": 0.70,  # Bushveld Complex — kritisk!
        "Russland / Sibir": 0.10,
        "USA / Canada": 0.04,
    },
}


@register("mining_disruption")
def mining_disruption(store: Any, instrument: str, params: dict) -> float:
    """Mining-disruption score (0..1) basert på USGS-events i mining-regioner.

    Logikk:
      For hver event i lookback-vinduet (default 7 dager) i en region som
      har vekt for `metal`:
        impact = max(0, magnitude - 4.5) / 3.0   # 4.5 → 0, 7.5 → 1
        weighted_impact = impact * region_weight

      score = clip(sum(weighted_impacts), 0, 1)

    Tolkning: høyere score = supply-disruption-risk = bullish for prising
    av det metallet (gruver kan stenge i flere uker etter alvorlige skjelv).

    **R4 (sub-fase 12.7):** ``params["_horizon"]`` LESES per ADR-010 men
    brukes ikke til å endre output. Driveren er event-basert (seismic +
    region-vekter), ikke en rolling tids-serie. Per event_distance-
    presedens: kun `_horizon`-lesing, ingen pct_*/delta_*-modes.

    Params:
        metal (REQUIRED): "gold" | "silver" | "copper" | "platinum".
            Bestemmer region-vektene.
        lookback_days: vindu i antall dager (default 7).
        min_magnitude: filtrer events under denne (default 4.5 — matcher
            USGS-feed-grense).
        regions: optional override av default region-vekter for metallet.
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Returnerer 0..1. Defensive 0.0 ved manglende metal/data/exception.
    """
    # ADR-010: les _horizon. Event-basert driver — output uendret med
    # eller uten _horizon (event-distance-presedens for R4 disiplin B).
    _horizon = params.get("_horizon")
    metal = params.get("metal")
    if not metal:
        _log.warning("mining_disruption.no_metal_param", instrument=instrument)
        return 0.0

    lookback_days = int(params.get("lookback_days", 7))
    min_magnitude = float(params.get("min_magnitude", 4.5))

    custom_regions = params.get("regions")
    if isinstance(custom_regions, dict):
        region_weights = {str(k): float(v) for k, v in custom_regions.items()}
    else:
        region_weights = _REGION_WEIGHTS_BY_METAL.get(str(metal).lower())
        if not region_weights:
            _log.warning("mining_disruption.unknown_metal", instrument=instrument, metal=metal)
            return 0.0

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    regions = list(region_weights.keys())

    try:
        df = store.get_seismic_events(regions=regions, from_ts=cutoff, min_magnitude=min_magnitude)
    except Exception as exc:
        _log.warning(
            "mining_disruption.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    if df.empty:
        return 0.0

    score = 0.0
    for _, row in df.iterrows():
        region = str(row["region"])
        weight = region_weights.get(region, 0.0)
        if weight <= 0:
            continue
        magnitude = float(row["magnitude"])
        # M4.5 → 0.0, M7.5 → 1.0 (lineært)
        impact = max(0.0, (magnitude - 4.5) / 3.0)
        score += impact * weight

    return max(0.0, min(1.0, round(score, 4)))


__all__ = [
    "comex_stress",
    "credit_spread_change",
    "dxy_chg5d",
    "eia_stock_change",
    "mining_disruption",
    "net_fed_liq_change",
    "nfci_change",
    "real_yield",
    "vix_regime",
    "yield_diff_10y",
]
