"""Tester for R4-horisont-modes på ``shipping_pressure``.

Sub-fase 12.7 R4 batch 6 finish (session 125). Tester at default er
bit-identisk pre-R4 + monotonisitet + regime-shift på rå Baltic-serien.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.agronomy import shipping_pressure


def _build_series(values: list[float]) -> pd.Series:
    dates = pd.date_range(start="2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates)


class _MockStore:
    def __init__(self, series: pd.Series):
        self._series = series

    def get_shipping_index(self, index_code: str, last_n: int | None = None):
        if last_n is None:
            return self._series
        return self._series.tail(last_n)


def test_default_mode_returns_chg_trap():
    """Default: 30d-pct-change-trapp på BDI-serien (bull_when=negative)."""
    # 1500 → 1200 over 30 dager: -20% ⇒ trappen 1.0
    values = [1500.0] * 30 + [1200.0]
    score = shipping_pressure(_MockStore(_build_series(values)), "Corn", {})
    assert score == 1.0


def test_default_unchanged_with_horizon_param():
    values = [1500.0 + i for i in range(35)]
    store = _MockStore(_build_series(values))
    no_horizon = shipping_pressure(store, "Corn", {})
    with_swing = shipping_pressure(store, "Corn", {"_horizon": "SWING"})
    with_makro = shipping_pressure(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


def test_pct_12m_monotonic_on_strictly_increasing_series():
    """pct_12m m/ bull_when=positive ⇒ helper bull_when=high ⇒
    strigende serie + current = topp ⇒ rank ≈ 1.0."""
    n_days = 270
    values = [1500.0 + i * 0.5 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(253, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = shipping_pressure(store, "Corn", {"mode": "pct_12m", "bull_when": "positive"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    n_days = 770
    values = [1500.0 + i * 0.5 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(757, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = shipping_pressure(store, "Corn", {"mode": "pct_36m", "bull_when": "positive"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 260
    values = [1500.0]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 5))

    last = values[-1]
    post = list(values)
    for i in range(5):
        post.append(last + 50 * (i + 1))

    pre_score = shipping_pressure(
        _MockStore(_build_series(values)),
        "Corn",
        {"mode": "delta_5d_z", "bull_when": "positive"},
    )
    post_score = shipping_pressure(
        _MockStore(_build_series(post)),
        "Corn",
        {"mode": "delta_5d_z", "bull_when": "positive"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 280
    values = [1500.0]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 5))

    last = values[-1]
    post = list(values)
    for i in range(20):
        post.append(last + 15 * (i + 1))

    pre_score = shipping_pressure(
        _MockStore(_build_series(values)),
        "Corn",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    post_score = shipping_pressure(
        _MockStore(_build_series(post)),
        "Corn",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_pct_12m_bull_when_inversion():
    """bull_when=negative (default — rate ned = bull) snur output."""
    n_days = 270
    values = [1500.0 + i * 0.5 for i in range(n_days)]
    store = _MockStore(_build_series(values))

    score_neg = shipping_pressure(store, "Corn", {"mode": "pct_12m", "bull_when": "negative"})
    score_pos = shipping_pressure(store, "Corn", {"mode": "pct_12m", "bull_when": "positive"})

    # Strigende serie ⇒ current = topp ⇒ rank ≈ 1.0
    # bull_when=negative ⇒ helper "low" ⇒ score = 1 - rank ≈ 0
    # bull_when=positive ⇒ helper "high" ⇒ score = rank ≈ 1
    assert score_neg <= 0.05
    assert score_pos >= 0.95


def test_pct_36m_fallback_to_12m_on_short_history():
    n_days = 270
    values = [1500.0 + i * 0.5 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    score_36m = shipping_pressure(store, "Corn", {"mode": "pct_36m", "bull_when": "positive"})
    score_12m = shipping_pressure(store, "Corn", {"mode": "pct_12m", "bull_when": "positive"})
    assert score_36m == score_12m


def test_extreme_flag_hard_at_top_percentile():
    n_days = 270
    values = [1500.0 + i * 0.5 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    flag = shipping_pressure(store, "Corn", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_unknown_mode_falls_back_to_default():
    values = [1500.0] * 30 + [1200.0]
    store = _MockStore(_build_series(values))
    default = shipping_pressure(store, "Corn", {})
    unknown = shipping_pressure(store, "Corn", {"mode": "not_a_real_mode"})
    assert default == unknown


class _MockStoreMissing:
    def get_shipping_index(self, index_code: str, last_n: int | None = None):
        raise KeyError(index_code)


def test_missing_data_returns_neutral_default_zero_mode():
    """Default returnerer 0.5 (nøytral), mode returnerer 0.0 ved manglende data."""
    store = _MockStoreMissing()
    assert shipping_pressure(store, "Corn", {}) == 0.5
    assert shipping_pressure(store, "Corn", {"mode": "pct_12m"}) == 0.0
