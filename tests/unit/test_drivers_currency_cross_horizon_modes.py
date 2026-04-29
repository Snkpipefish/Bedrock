"""Tester for R4-horisont-modes på ``currency_cross_trend``.

Sub-fase 12.7 R4 batch 7 (session 125). Tester at default er bit-
identisk pre-R4 + monotonisitet + regime-shift på rå cross-prises.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.currency import currency_cross_trend


def _build_series(values: list[float]) -> pd.Series:
    dates = pd.date_range(start="2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates)


class _MockStore:
    def __init__(self, series: pd.Series):
        self._series = series

    def get_prices(self, source: str, tf: str = "D1", lookback: int | None = None):
        if lookback is None:
            return self._series
        return self._series.tail(lookback)


_PARAMS = {"source": "BRLUSD"}


def test_default_mode_returns_chg_trap():
    """Default: 30d-pct-change-trapp på cross-serien (direction=direct).

    Float precision: (0.22-0.20)/0.20 kan gi 0.0999... < 0.10 ⇒ 0.8-grein.
    Bruker større endring (+15%) for klar 1.0-trigger.
    """
    values = [0.20] * 30 + [0.23]
    score = currency_cross_trend(_MockStore(_build_series(values)), "Sugar", _PARAMS)
    assert score == 1.0


def test_default_unchanged_with_horizon_param():
    values = [0.20 + i * 0.0001 for i in range(35)]
    store = _MockStore(_build_series(values))
    no_horizon = currency_cross_trend(store, "Sugar", _PARAMS)
    with_swing = currency_cross_trend(store, "Sugar", {**_PARAMS, "_horizon": "SWING"})
    with_makro = currency_cross_trend(store, "Sugar", {**_PARAMS, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


def test_pct_12m_monotonic_on_strictly_increasing_series():
    """pct_12m m/ direction=direct ⇒ helper bull_when=high ⇒ rank ≈ 1.0."""
    n_days = 270
    values = [0.20 + i * 0.0001 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(253, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "pct_12m"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    n_days = 770
    values = [0.20 + i * 0.0001 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(757, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "pct_36m"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 260
    values = [0.20]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.0001))

    last = values[-1]
    post = list(values)
    for i in range(5):
        post.append(last + 0.005 * (i + 1))

    pre_score = currency_cross_trend(
        _MockStore(_build_series(values)),
        "Sugar",
        {**_PARAMS, "mode": "delta_5d_z"},
    )
    post_score = currency_cross_trend(
        _MockStore(_build_series(post)),
        "Sugar",
        {**_PARAMS, "mode": "delta_5d_z"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 280
    values = [0.20]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.0001))

    last = values[-1]
    post = list(values)
    for i in range(20):
        post.append(last + 0.0015 * (i + 1))

    pre_score = currency_cross_trend(
        _MockStore(_build_series(values)),
        "Sugar",
        {**_PARAMS, "mode": "delta_20d_z"},
    )
    post_score = currency_cross_trend(
        _MockStore(_build_series(post)),
        "Sugar",
        {**_PARAMS, "mode": "delta_20d_z"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_pct_12m_direction_inversion():
    """direction=invert (BRL-styrkning er bull for noen contexts) snur output."""
    n_days = 270
    values = [0.20 + i * 0.0001 for i in range(n_days)]
    store = _MockStore(_build_series(values))

    score_direct = currency_cross_trend(
        store, "Sugar", {**_PARAMS, "mode": "pct_12m", "direction": "direct"}
    )
    score_invert = currency_cross_trend(
        store, "Sugar", {**_PARAMS, "mode": "pct_12m", "direction": "invert"}
    )

    # direct ⇒ helper "high" ⇒ rank ≈ 1.0
    # invert ⇒ helper "low" ⇒ score = 1 - rank ≈ 0.0
    assert score_direct >= 0.95
    assert score_invert <= 0.05


def test_pct_36m_fallback_to_12m_on_short_history():
    n_days = 270
    values = [0.20 + i * 0.0001 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    score_36m = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "pct_36m"})
    score_12m = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "pct_12m"})
    assert score_36m == score_12m


def test_extreme_flag_hard_at_top_percentile():
    n_days = 270
    values = [0.20 + i * 0.0001 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    flag = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_unknown_mode_falls_back_to_default():
    values = [0.20] * 30 + [0.22]
    store = _MockStore(_build_series(values))
    default = currency_cross_trend(store, "Sugar", _PARAMS)
    unknown = currency_cross_trend(store, "Sugar", {**_PARAMS, "mode": "not_a_real_mode"})
    assert default == unknown


def test_missing_source_returns_zero():
    store = _MockStore(_build_series([0.20] * 35))
    assert currency_cross_trend(store, "Sugar", {}) == 0.0
    assert currency_cross_trend(store, "Sugar", {"mode": "pct_12m"}) == 0.0
