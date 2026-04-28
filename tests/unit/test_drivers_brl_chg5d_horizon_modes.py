"""Tester for R4-horisont-modes på ``brl_chg5d``.

Sub-fase 12.7 R4 batch 5 (session 123). Parallell til
``test_drivers_dxy_chg5d_horizon_modes.py`` men driver leser DEXBZUS.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.macro import brl_chg5d


def _build_series(values: list[float]) -> pd.Series:
    dates = pd.date_range(start="2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates)


class _MockStore:
    def __init__(self, series: pd.Series):
        self._series = series

    def get_fundamentals(self, series_id: str) -> pd.Series:
        return self._series


def test_default_mode_returns_chg5d_trap():
    """Default skal returnere 5d-pct-change-trapp.

    bull_when=positive default. BRL-trappe (sortert ascending +): (-2.5, 0.25),
    (-1.0, 0.5), (1.0, 0.75), (2.5, 1.0). 5.0 → 5.06 = +1.2% ⇒ ≥1.0-grein → 0.75.
    """
    values = [5.0] * 5 + [5.06]
    store = _MockStore(_build_series(values))
    score = brl_chg5d(store, "Test", {})
    assert score == 0.75


def test_default_unchanged_with_horizon_param():
    values = [5.0 + i * 0.01 for i in range(10)]
    store = _MockStore(_build_series(values))
    no_horizon = brl_chg5d(store, "Test", {})
    with_swing = brl_chg5d(store, "Test", {"_horizon": "SWING"})
    with_makro = brl_chg5d(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


def test_pct_12m_monotonic_on_strictly_increasing_series():
    """bull_when=positive: høy DEXBZUS = USD-BRL UP = bull for kaffe/sukker."""
    n_days = 270
    values = [5.0 + i * 0.001 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(253, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = brl_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    n_days = 770
    values = [5.0 + i * 0.001 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(757, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = brl_chg5d(store, "Test", {"mode": "pct_36m", "bull_when": "positive"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 260
    base = 5.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.005))

    last = values[-1]
    post = list(values)
    for i in range(5):
        post.append(last + 0.05 * (i + 1))

    pre_score = brl_chg5d(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_5d_z", "bull_when": "positive"},
    )
    post_score = brl_chg5d(
        _MockStore(_build_series(post)),
        "Test",
        {"mode": "delta_5d_z", "bull_when": "positive"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 280
    base = 5.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.005))

    last = values[-1]
    post = list(values)
    for i in range(20):
        post.append(last + 0.015 * (i + 1))

    pre_score = brl_chg5d(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    post_score = brl_chg5d(
        _MockStore(_build_series(post)),
        "Test",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_pct_12m_bull_when_inversion():
    """bull_when=negative skal snu output."""
    n_days = 270
    values = [5.0 + i * 0.001 for i in range(n_days)]
    store = _MockStore(_build_series(values))

    score_pos = brl_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
    score_neg = brl_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "negative"})

    assert score_pos >= 0.95
    assert score_neg <= 0.05


def test_pct_36m_fallback_to_12m_on_short_history():
    n_days = 270
    values = [5.0 + i * 0.001 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    score_36m = brl_chg5d(store, "Test", {"mode": "pct_36m", "bull_when": "positive"})
    score_12m = brl_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
    assert score_36m == score_12m


def test_extreme_flag_hard_at_top_percentile():
    n_days = 270
    values = [5.0 + i * 0.001 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    flag = brl_chg5d(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    n_days = 270
    values = [5.0 + i * 0.001 for i in range(n_days - 1)]
    values.append(5.0 + (n_days // 2) * 0.001)
    store = _MockStore(_build_series(values))
    flag = brl_chg5d(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


def test_unknown_mode_falls_back_to_default():
    values = [5.0] * 5 + [5.05]
    store = _MockStore(_build_series(values))
    default = brl_chg5d(store, "Test", {})
    unknown = brl_chg5d(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown


class _MockStoreMissing:
    def get_fundamentals(self, series_id: str):
        raise KeyError(series_id)


def test_missing_series_returns_zero():
    store = _MockStoreMissing()
    assert brl_chg5d(store, "Test", {}) == 0.0
    assert brl_chg5d(store, "Test", {"mode": "pct_12m"}) == 0.0
