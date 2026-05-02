"""Trend-familie drivere.

Fase 1 session 4 — to første ekte drivere:

- ``sma200_align``: posisjon relativt til 200-dag SMA på gitt TF
- ``momentum_z``: z-score av nåpris vs rolling mean/std over et vindu

Begge returnerer 0.0..1.0 per driver-kontrakt (unidirectional bull-variant).

R4 (sub-fase 12.7): begge drivere er nå horisont-bevisste via ``params["mode"]``
per ADR-010 og ``docs/driver_horizon_pattern.md`` § 1.1. ``params["_horizon"]``
leses (lest, ikke brukt for å påvirke default-output) per ADR-010 og R3-
presedens (commits ``c95d8fc``, ``dc0a98c``).

**Default-mode (mode=None) er bit-identisk med pre-R4** — terskel-trapp på
``close vs SMA200`` for ``sma200_align``, terskel-trapp på rolling z-score
for ``momentum_z``. R4-kontrakt: YAML uendret, score uendret.

Mode-tabell (begge drivere, virker på driver-egen tids-serie):

==================  =============================================
Mode                 Tolkning
==================  =============================================
None (default)       Eksisterende terskel-trapp (bit-identisk)
``pct_12m``          12m rolling percentile av feature-serien
``pct_36m``          36m rolling percentile (fall-back til 12m)
``delta_5d_z``       z-score av 5d-delta i feature-serien
``delta_20d_z``      z-score av 20d-delta i feature-serien
``extreme_flag_hard`` 1.0 ved 2/98-percentile, ellers 0.0
``extreme_flag_soft`` 1.0 ved 5/95-percentile, ellers 0.0
==================  =============================================

For ``sma200_align`` virker modes på ``(close - SMA200) / SMA200``-serien.
For ``momentum_z`` virker modes på rolling-z-score-serien (``delta_*``-modes
representerer akselerasjon av momentum, ikke endring i underliggende pris).

bull_when=high implisitt (positiv distance / positiv z = bullish).

Drivere er defensive: feil i data-oppslag eller for kort historikk gir 0.0
og logger (ikke unntak) — prinsipp fra driver-kontrakten i ``drivers/__init__.py``.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register
from bedrock.engine.drivers._stats import rank_percentile, rolling_z

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Konstanter (delt mellom begge drivere)
# ---------------------------------------------------------------------------

# 12m / 36m i trading-dager (252 = ~kalender-12m, 756 = ~36m).
# Per PLAN § 19.3 og driver_horizon_pattern.md § 1.1.
_LOOKBACK_PCT_12M = 252
_LOOKBACK_PCT_36M = 756

# Historikk-vindu for delta-z-distribusjon (~12m daglig).
_LOOKBACK_DELTA = 252

# Delta-vinduer i trading-dager.
_DELTA_5D = 5
_DELTA_20D = 20

# Ekstrem-terskler per § 19.3-låsen.
_EXTREME_HARD_HI = 0.98
_EXTREME_HARD_LO = 0.02
_EXTREME_SOFT_HI = 0.95
_EXTREME_SOFT_LO = 0.05


def _z_to_score_positive(z: float) -> float:
    """Map z-score til [0..1] (bull_when=high konvensjon).

    Speiler ``positioning._z_to_score_positive`` for konsistent skalering
    på tvers av z-baserte drivere (R3-presedens).
    """
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


def _extreme_flag(pct_0_to_1: float, *, hard: bool) -> float:
    """1.0 hvis pct er ekstrem, ellers 0.0. Per § 19.3-låsen."""
    hi = _EXTREME_HARD_HI if hard else _EXTREME_SOFT_HI
    lo = _EXTREME_HARD_LO if hard else _EXTREME_SOFT_LO
    if pct_0_to_1 >= hi or pct_0_to_1 <= lo:
        return 1.0
    return 0.0


def _mode_pct_from_series(
    series: pd.Series, instrument: str, lookback: int, *, driver: str
) -> float | None:
    """Rank-percentile (0..1) av siste verdi vs ``lookback`` historikk.

    Returnerer ``None`` ved utilstrekkelig historikk.
    """
    clean = series.dropna()
    if len(clean) < lookback + 1:
        _log.debug(
            f"{driver}.short_history_for_pct",
            instrument=instrument,
            available=len(clean),
            required=lookback + 1,
        )
        return None
    history = clean.iloc[-(lookback + 1) : -1].tolist()
    current = float(clean.iloc[-1])
    pct = rank_percentile(current, history)
    if pct is None:
        return None
    return round(pct / 100.0, 4)


def _mode_delta_z_from_series(
    series: pd.Series,
    instrument: str,
    *,
    delta_days: int,
    lookback: int,
    driver: str,
) -> float | None:
    """Rolling-z av N-day delta i ``series``, mappet til [0..1].

    Returnerer ``None`` ved utilstrekkelig historikk eller flat
    delta-distribusjon (MAD=0).
    """
    clean = series.dropna()
    if len(clean) < delta_days + lookback + 1:
        _log.debug(
            f"{driver}.short_history_for_delta_z",
            instrument=instrument,
            available=len(clean),
            required=delta_days + lookback + 1,
        )
        return None
    delta = clean.diff(delta_days).dropna()
    if len(delta) < lookback + 1:
        return None
    history = delta.iloc[-(lookback + 1) : -1].tolist()
    current = float(delta.iloc[-1])
    z = rolling_z(current, history)
    if z is None:
        return None
    return round(_z_to_score_positive(z), 4)


# ---------------------------------------------------------------------------
# sma200_align
# ---------------------------------------------------------------------------

_SMA_WINDOW = 200


def _load_sma_distance_series(store: Any, instrument: str, tf: str, n_obs: int) -> pd.Series | None:
    """Bygg ``(close - SMA200) / SMA200``-serien for mode-bruk.

    ``n_obs`` er minimum antall ikke-NaN distance-verdier som trengs
    (driveren legger til SMA-vindu og buffer på toppen).
    """
    try:
        prices = store.get_prices(instrument, tf=tf, lookback=n_obs + _SMA_WINDOW + 50)
    except KeyError as exc:
        _log.debug(
            "sma200_align.prices_unavailable",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return None
    except Exception as exc:
        _log.warning(
            "sma200_align.prices_fetch_failed",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return None
    if len(prices) < _SMA_WINDOW + 1:
        return None
    sma = prices.rolling(_SMA_WINDOW).mean()
    distance = (prices - sma) / sma
    return distance.dropna()


def _sma200_align_default(store: Any, instrument: str, params: dict) -> float:
    """Bit-identisk pre-R4 terskel-trapp på close vs SMA200."""
    tf = params.get("tf", "D1")
    try:
        prices = store.get_prices(instrument, tf=tf, lookback=_SMA_WINDOW + 50)
    except KeyError as exc:
        _log.debug("sma200_align.prices_unavailable", instrument=instrument, tf=tf, error=str(exc))
        return 0.0
    except Exception as exc:
        _log.warning(
            "sma200_align.prices_fetch_failed", instrument=instrument, tf=tf, error=str(exc)
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


@register("sma200_align")
def sma200_align(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 for hvor komfortabelt over SMA200 prisen ligger.

    Default (``mode=None``) — bit-identisk pre-R4:
    - close > SMA × 1.01 -> 1.0 (klar trend-bekreftelse)
    - close > SMA        -> 0.6 (så vidt over, svak trend)
    - close > SMA × 0.99 -> 0.4 (innenfor ±1 %, tvetydig)
    - close <= SMA × 0.99 -> 0.0 (under, ingen bull-bekreftelse)

    Modes (R4-utvidelse, virker på ``(close - SMA200) / SMA200``-serien;
    bull_when=high implisitt — positiv distance = pris over SMA = bullish):
    - ``pct_12m`` / ``pct_36m`` / ``delta_5d_z`` / ``delta_20d_z`` /
      ``extreme_flag_hard`` / ``extreme_flag_soft``

    Params:
        tf: timeframe for pris-oppslag (default ``D1``)
        mode: feature-velger (default ``None`` = pre-R4-terskel-trapp)

    ``params["_horizon"]`` leses per ADR-010 men brukes ikke for default;
    YAML-sidens horisont-valg styrer i fremtidig D-fase hvilken mode som
    aktiveres per familie-kontekst.

    Korte serier (< 200 bars) gir 0.0 — SMA er udefinert.
    """
    # ADR-010: les _horizon for fremtidig bruk. R4-kontrakt: ikke endre
    # default-output basert på _horizon.
    _horizon = params.get("_horizon")
    mode = params.get("mode")
    tf = params.get("tf", "D1")

    if mode is None:
        return _sma200_align_default(store, instrument, params)

    if mode == "pct_12m":
        series = _load_sma_distance_series(store, instrument, tf, _LOOKBACK_PCT_12M)
        if series is None:
            return 0.0
        result = _mode_pct_from_series(series, instrument, _LOOKBACK_PCT_12M, driver="sma200_align")
        return result if result is not None else 0.0

    if mode == "pct_36m":
        series = _load_sma_distance_series(store, instrument, tf, _LOOKBACK_PCT_36M)
        if series is None:
            return 0.0
        result = _mode_pct_from_series(series, instrument, _LOOKBACK_PCT_36M, driver="sma200_align")
        if result is None:
            _log.info(
                "sma200_align.pct_36m_fallback_to_12m",
                instrument=instrument,
                available=len(series),
                required=_LOOKBACK_PCT_36M + 1,
            )
            result = _mode_pct_from_series(
                series, instrument, _LOOKBACK_PCT_12M, driver="sma200_align"
            )
        return result if result is not None else 0.0

    if mode == "delta_5d_z":
        series = _load_sma_distance_series(store, instrument, tf, _DELTA_5D + _LOOKBACK_DELTA)
        if series is None:
            return 0.0
        result = _mode_delta_z_from_series(
            series,
            instrument,
            delta_days=_DELTA_5D,
            lookback=_LOOKBACK_DELTA,
            driver="sma200_align",
        )
        return result if result is not None else 0.0

    if mode == "delta_20d_z":
        series = _load_sma_distance_series(store, instrument, tf, _DELTA_20D + _LOOKBACK_DELTA)
        if series is None:
            return 0.0
        result = _mode_delta_z_from_series(
            series,
            instrument,
            delta_days=_DELTA_20D,
            lookback=_LOOKBACK_DELTA,
            driver="sma200_align",
        )
        return result if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        series = _load_sma_distance_series(store, instrument, tf, _LOOKBACK_PCT_12M)
        if series is None:
            return 0.0
        pct = _mode_pct_from_series(series, instrument, _LOOKBACK_PCT_12M, driver="sma200_align")
        if pct is None:
            return 0.0
        return _extreme_flag(pct, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "sma200_align.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _sma200_align_default(store, instrument, params)


# ---------------------------------------------------------------------------
# momentum_z
# ---------------------------------------------------------------------------

_DEFAULT_WINDOW = 20


def _load_momentum_z_series(
    store: Any, instrument: str, tf: str, window: int, n_obs: int
) -> pd.Series | None:
    """Bygg rolling-z-score-serien for mode-bruk.

    z_t = (close_t - rolling_mean_window) / rolling_std_window.

    ``n_obs`` er minimum antall ikke-NaN z-verdier som trengs.
    """
    try:
        prices = store.get_prices(instrument, tf=tf, lookback=n_obs + window + 50)
    except KeyError as exc:
        _log.debug(
            "momentum_z.prices_unavailable",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return None
    except Exception as exc:
        _log.warning(
            "momentum_z.prices_fetch_failed",
            instrument=instrument,
            tf=tf,
            error=str(exc),
        )
        return None
    if len(prices) < window + 1:
        return None
    rolling = prices.rolling(window)
    mean = rolling.mean()
    std = rolling.std(ddof=0)
    z = (prices - mean) / std.where(std != 0.0)
    return z.dropna()


def _momentum_z_default(store: Any, instrument: str, params: dict) -> float:
    """Bit-identisk pre-R4 terskel-trapp på rolling-z-score."""
    window = int(params.get("window", _DEFAULT_WINDOW))
    tf = params.get("tf", "D1")

    try:
        prices = store.get_prices(instrument, tf=tf, lookback=window + 50)
    except KeyError as exc:
        _log.debug("momentum_z.prices_unavailable", instrument=instrument, tf=tf, error=str(exc))
        return 0.0
    except Exception as exc:
        _log.warning("momentum_z.prices_fetch_failed", instrument=instrument, tf=tf, error=str(exc))
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


@register("momentum_z")
def momentum_z(store: Any, instrument: str, params: dict) -> float:
    """Returnerer 0..1 basert på z-score av close vs rolling mean/std.

    Default (``mode=None``) — bit-identisk pre-R4 z-score-terskel-trapp:
        z >= 2.0 -> 1.0
        z >= 1.0 -> 0.75
        z >= 0.5 -> 0.6
        z >= 0.0 -> 0.5
        z >= -0.5 -> 0.3
        z < -0.5  -> 0.0

    Modes (R4-utvidelse, virker på rolling-z-score-serien — merk at
    ``delta_*_z``-modes representerer **akselerasjon av momentum** over
    5d/20d, ikke endring i underliggende pris):
    - ``pct_12m`` / ``pct_36m`` / ``delta_5d_z`` / ``delta_20d_z`` /
      ``extreme_flag_hard`` / ``extreme_flag_soft``

    Tolkning av ``delta_5d_z``-mode på en z-score-serie: "z-score av delta
    av z-score-distribusjon over 5d" — dvs. positiv verdi = momentum-
    z-score er økende, dvs. trend-akselererer. Dette er konseptuelt et
    lag dypere enn ``delta_5d_z`` på en rå-serie (positioning_mm_pct,
    real_yield) hvor det måler endring i underliggende metrikk.

    Params:
        window: rolling-vindu for mean/std (default 20)
        tf: timeframe (default ``D1``)
        mode: feature-velger (default ``None`` = pre-R4-terskel-trapp)
        instrument: valgfri override — les prices for et annet instrument
            enn det som scores. Brukstilfelle (sub-fase 12.11): Sugar
            scorer mot CrudeOil-momentum (Brasil ethanol-mix-katalysator)
            uten å trenge en ny dedikert oljedriver. Default = scored
            instrument.

    ``params["_horizon"]`` leses per ADR-010 men brukes ikke for default.

    For kort historikk (< window + 1 bars) eller std == 0 gir 0.0.
    """
    _horizon = params.get("_horizon")
    mode = params.get("mode")
    window = int(params.get("window", _DEFAULT_WINDOW))
    tf = params.get("tf", "D1")
    target_instrument = params.get("instrument", instrument)

    if mode is None:
        return _momentum_z_default(store, target_instrument, params)

    if mode == "pct_12m":
        series = _load_momentum_z_series(store, target_instrument, tf, window, _LOOKBACK_PCT_12M)
        if series is None:
            return 0.0
        result = _mode_pct_from_series(
            series, target_instrument, _LOOKBACK_PCT_12M, driver="momentum_z"
        )
        return result if result is not None else 0.0

    if mode == "pct_36m":
        series = _load_momentum_z_series(store, target_instrument, tf, window, _LOOKBACK_PCT_36M)
        if series is None:
            return 0.0
        result = _mode_pct_from_series(
            series, target_instrument, _LOOKBACK_PCT_36M, driver="momentum_z"
        )
        if result is None:
            _log.info(
                "momentum_z.pct_36m_fallback_to_12m",
                instrument=instrument,
                available=len(series),
                required=_LOOKBACK_PCT_36M + 1,
            )
            result = _mode_pct_from_series(
                series, instrument, _LOOKBACK_PCT_12M, driver="momentum_z"
            )
        return result if result is not None else 0.0

    if mode == "delta_5d_z":
        # delta_5d_z på momentum_z = endring i momentum-z-score-distribusjon
        # over 5d. Tolkning: "akselerasjon av momentum" snarere enn "endring
        # i underliggende prisserie".
        series = _load_momentum_z_series(
            store, target_instrument, tf, window, _DELTA_5D + _LOOKBACK_DELTA
        )
        if series is None:
            return 0.0
        result = _mode_delta_z_from_series(
            series,
            instrument,
            delta_days=_DELTA_5D,
            lookback=_LOOKBACK_DELTA,
            driver="momentum_z",
        )
        return result if result is not None else 0.0

    if mode == "delta_20d_z":
        # delta_20d_z på momentum_z: 20d-akselerasjon av momentum.
        series = _load_momentum_z_series(
            store, target_instrument, tf, window, _DELTA_20D + _LOOKBACK_DELTA
        )
        if series is None:
            return 0.0
        result = _mode_delta_z_from_series(
            series,
            instrument,
            delta_days=_DELTA_20D,
            lookback=_LOOKBACK_DELTA,
            driver="momentum_z",
        )
        return result if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        series = _load_momentum_z_series(store, target_instrument, tf, window, _LOOKBACK_PCT_12M)
        if series is None:
            return 0.0
        pct = _mode_pct_from_series(
            series, target_instrument, _LOOKBACK_PCT_12M, driver="momentum_z"
        )
        if pct is None:
            return 0.0
        return _extreme_flag(pct, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "momentum_z.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _momentum_z_default(store, instrument, params)
