"""Tester for R4-horisont-modes på ``vix_regime``.

Sub-fase 12.7 R4 batch 5 (session 123). Tester at:
- Default (mode=None) er bit-identisk pre-R4 (regime-klassifikator).
- pct_12m/pct_36m monotonisitet på VIXCLS rå-serien.
- delta_5d_z/delta_20d_z regime-shift.
- invert-respekt (oversettes til bull_when=high/low).
- pct_36m fall-back, ukjent mode → default, missing series → 0.0.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.macro import vix_regime


def _build_series(values: list[float]) -> pd.Series:
    dates = pd.date_range(start="2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates)


class _MockStore:
    def __init__(self, series: pd.Series):
        self._series = series

    def get_fundamentals(self, series_id: str) -> pd.Series:
        return self._series


# ---------------------------------------------------------------------------
# Type A — bit-identisk default
# ---------------------------------------------------------------------------


def test_default_mode_returns_regime_score_low_vix():
    """VIX ≤ 15 ⇒ score = 1.0 (rolig marked, default-tolkning)."""
    store = _MockStore(_build_series([14.0]))
    score = vix_regime(store, "Test", {})
    assert score == 1.0


def test_default_mode_returns_regime_score_high_vix():
    """VIX > 35 ⇒ score = 0.0 (krise-regime)."""
    store = _MockStore(_build_series([40.0]))
    score = vix_regime(store, "Test", {})
    assert score == 0.0


def test_default_invert_safe_haven():
    """invert=True snur scoren (Gold-tolkning: høy VIX = bull)."""
    store = _MockStore(_build_series([14.0]))  # low VIX
    score = vix_regime(store, "Test", {"invert": True})
    # Inversjon: 1.0 → 0.0
    assert score == 0.0


def test_default_unchanged_with_horizon_param():
    store = _MockStore(_build_series([14.0]))
    no_horizon = vix_regime(store, "Test", {})
    with_swing = vix_regime(store, "Test", {"_horizon": "SWING"})
    with_makro = vix_regime(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# Type B — monotonisitet
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series():
    """pct_12m default invert=False ⇒ helper bull_when=low ⇒ lav rank = bull.

    Strigende VIX-serie ⇒ current er topp ⇒ rank ≈ 1.0 ⇒ score = 1 - rank = 0.0.
    Test motsatt invert=True ⇒ bull_when=high ⇒ score = rank.
    """
    n_days = 270
    values = [15.0 + i * 0.05 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(253, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = vix_regime(store, "Test", {"mode": "pct_12m", "invert": True})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    n_days = 770
    values = [15.0 + i * 0.05 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(757, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = vix_regime(store, "Test", {"mode": "pct_36m", "invert": True})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift():
    """invert=True ⇒ bull_when=high; VIX-spike er bull-of-Gold."""
    import random

    rng = random.Random(42)
    n_pre = 260
    base = 15.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.1))

    last = values[-1]
    post = list(values)
    for i in range(5):
        post.append(last + 1.5 * (i + 1))  # VIX hopper opp 1.5/dag

    pre_score = vix_regime(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_5d_z", "invert": True},
    )
    post_score = vix_regime(
        _MockStore(_build_series(post)),
        "Test",
        {"mode": "delta_5d_z", "invert": True},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 280
    base = 15.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.1))

    last = values[-1]
    post = list(values)
    for i in range(20):
        post.append(last + 0.5 * (i + 1))

    pre_score = vix_regime(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_20d_z", "invert": True},
    )
    post_score = vix_regime(
        _MockStore(_build_series(post)),
        "Test",
        {"mode": "delta_20d_z", "invert": True},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


# ---------------------------------------------------------------------------
# invert-respekt
# ---------------------------------------------------------------------------


def test_pct_12m_invert_respect():
    """invert=True (safe-haven) snur output på pct-mode."""
    n_days = 270
    values = [15.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))

    score_default = vix_regime(store, "Test", {"mode": "pct_12m"})  # invert=False
    score_invert = vix_regime(store, "Test", {"mode": "pct_12m", "invert": True})

    # Strigende serie → current er topp → rank ≈ 1.0
    # invert=False (lav VIX bull) → score = 1 - rank ≈ 0.0
    # invert=True (høy VIX bull) → score = rank ≈ 1.0
    assert score_default <= 0.05
    assert score_invert >= 0.95


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history():
    n_days = 270
    values = [15.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    score_36m = vix_regime(store, "Test", {"mode": "pct_36m", "invert": True})
    score_12m = vix_regime(store, "Test", {"mode": "pct_12m", "invert": True})
    assert score_36m == score_12m


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile():
    n_days = 270
    values = [15.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    flag = vix_regime(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    n_days = 270
    values = [15.0 + i * 0.05 for i in range(n_days - 1)]
    values.append(15.0 + (n_days // 2) * 0.05)
    store = _MockStore(_build_series(values))
    flag = vix_regime(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default():
    store = _MockStore(_build_series([14.0]))
    default = vix_regime(store, "Test", {})
    unknown = vix_regime(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# Manglende serie → 0.0
# ---------------------------------------------------------------------------


class _MockStoreMissing:
    def get_fundamentals(self, series_id: str):
        raise KeyError(series_id)


def test_missing_series_returns_zero():
    store = _MockStoreMissing()
    assert vix_regime(store, "Test", {}) == 0.0
    assert vix_regime(store, "Test", {"mode": "pct_12m"}) == 0.0
