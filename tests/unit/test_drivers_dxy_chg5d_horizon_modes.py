"""Tester for R4-horisont-modes på ``dxy_chg5d``.

Sub-fase 12.7 R4 batch 5 (session 123). Tester at:
- Default (mode=None) er bit-identisk pre-R4 (5d-pct-change-trapp).
- pct_12m/pct_36m monotonisitet (Type B) på DTWEXBGS rå-serien.
- delta_5d_z/delta_20d_z regime-shift (Type C) på rå-serien.
- extreme_flag_*-modes sanity.
- bull_when-respekt: pct_12m snur output ved bull_when=positive vs negative.
- pct_36m fall-back til pct_12m ved utilstrekkelig historikk.
- _horizon-param leses uten output-effekt.
- Ukjent mode → fall-back til default.

Bruker mock-store-mønster matching macro.py-tester.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.macro import dxy_chg5d


def _build_series(values: list[float]) -> pd.Series:
    """Build daily FRED-style series med deterministiske datoer."""
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


def test_default_mode_returns_chg5d_trap():
    """Default skal returnere 5d-pct-change-trapp på rå DTWEXBGS-data."""
    # 100 → 100.5 over 5 dager: pct_change = +0.5%, mellom -0.5 og +0.5 →
    # bull_when="negative" trappe-grein "(0.5, 0.5)" treffer.
    values = [100.0] * 5 + [100.5]
    store = _MockStore(_build_series(values))
    score = dxy_chg5d(store, "Test", {})
    # +0.5% er på terskelen for "0.5 → 0.5" (≤ 0.5 i bull_when=negative)
    assert score == 0.5


def test_default_unchanged_with_horizon_param():
    """R4-kontrakt: _horizon LESES men brukes ikke i default-output."""
    values = [100.0 + i * 0.1 for i in range(10)]
    store = _MockStore(_build_series(values))
    no_horizon = dxy_chg5d(store, "Test", {})
    with_swing = dxy_chg5d(store, "Test", {"_horizon": "SWING"})
    with_makro = dxy_chg5d(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# Type B — monotonisitet
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series():
    """Type B: pct_12m på strigende DXY-serie + bull_when=high → monotont
    stigende output (caller normaliserer "positive" → "high")."""
    n_days = 270
    values = [100.0 + i * 0.05 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(253, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = dxy_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    n_days = 770
    values = [100.0 + i * 0.05 for i in range(n_days)]
    full_series = _build_series(values)
    prev = -1.0
    for n in range(757, n_days + 1):
        store = _MockStore(full_series.iloc[:n])
        score = dxy_chg5d(store, "Test", {"mode": "pct_36m", "bull_when": "positive"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift():
    """Type C: delta_5d_z fanger 5d hopp i DXY rå-serien."""
    import random

    rng = random.Random(42)
    n_pre = 260
    base = 100.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.1))

    # Hopp på 5% (50× std) over 5 dager
    last = values[-1]
    post = list(values)
    for i in range(5):
        post.append(last + 1.0 * (i + 1))

    pre_score = dxy_chg5d(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_5d_z", "bull_when": "positive"},
    )
    post_score = dxy_chg5d(
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
    base = 100.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.1))

    last = values[-1]
    post = list(values)
    for i in range(20):
        post.append(last + 0.3 * (i + 1))

    pre_score = dxy_chg5d(
        _MockStore(_build_series(values)),
        "Test",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    post_score = dxy_chg5d(
        _MockStore(_build_series(post)),
        "Test",
        {"mode": "delta_20d_z", "bull_when": "positive"},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


# ---------------------------------------------------------------------------
# bull_when-respekt
# ---------------------------------------------------------------------------


def test_pct_12m_bull_when_inversion():
    """pct_12m skal respektere bull_when ved å snu output.

    bull_when=positive: høy DXY = bull → høy score.
    bull_when=negative: høy DXY = bear → lav score.
    """
    n_days = 270
    values = [100.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))

    score_pos = dxy_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
    score_neg = dxy_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "negative"})

    # Pct ≈ 1.0 (current er høyeste). bull_when=positive: score ≈ 1.0.
    # bull_when=negative: score ≈ 0.0.
    assert score_pos >= 0.95
    assert score_neg <= 0.05


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history():
    n_days = 270  # < 757 obs
    values = [100.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    score_36m = dxy_chg5d(store, "Test", {"mode": "pct_36m", "bull_when": "positive"})
    score_12m = dxy_chg5d(store, "Test", {"mode": "pct_12m", "bull_when": "positive"})
    assert score_36m == score_12m


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile():
    """Strigende serie med current = topp → flag = 1.0."""
    n_days = 270
    values = [100.0 + i * 0.05 for i in range(n_days)]
    store = _MockStore(_build_series(values))
    flag = dxy_chg5d(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    n_days = 270
    values = [100.0 + i * 0.05 for i in range(n_days - 1)]
    # Median-aktig current
    values.append(100.0 + (n_days // 2) * 0.05)
    store = _MockStore(_build_series(values))
    flag = dxy_chg5d(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default():
    values = [100.0] * 5 + [100.5]
    store = _MockStore(_build_series(values))
    default = dxy_chg5d(store, "Test", {})
    unknown = dxy_chg5d(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# Manglende serie → 0.0
# ---------------------------------------------------------------------------


class _MockStoreMissing:
    def get_fundamentals(self, series_id: str):
        raise KeyError(series_id)


def test_missing_series_returns_zero():
    store = _MockStoreMissing()
    assert dxy_chg5d(store, "Test", {}) == 0.0
    assert dxy_chg5d(store, "Test", {"mode": "pct_12m"}) == 0.0
