"""Tester for R4-horisont-modes på ``cot_ice_mm_pct``.

Sub-fase 12.7 R4 batch 4 (session 123). Parallell til
``test_drivers_cot_z_score_horizon_modes.py`` men driver leser fra
``store.get_cot_ice`` istedenfor ``store.get_cot``.

Verifiserer at:
- Default (mode=None) er bit-identisk med pre-R4 (rank-percentile / 100).
- pct_12m/pct_36m monotonisitet (Type B).
- delta_5d_z/delta_20d_z regime-shift (Type C).
- extreme_flag_hard/soft sanity.
- _horizon-param leses uten output-effekt.
- Ukjent mode → fall-back til default.
- pct_36m fall-back til pct_12m ved utilstrekkelig historikk.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers.positioning import cot_ice_mm_pct


def _build_ice_cot_df(
    *,
    n_weeks: int,
    mm_long_values: list[float] | None = None,
    mm_long_start: float = 100_000,
    mm_long_step: float = 1_000,
    mm_short: float = 50_000,
    open_interest: float = 300_000,
) -> pd.DataFrame:
    """Bygger ICE-COT-historikk parallell til CFTC-versjonen."""
    base = date(2022, 1, 5)
    rows = []
    if mm_long_values is None:
        mm_long_values = [mm_long_start + mm_long_step * i for i in range(n_weeks)]
    assert len(mm_long_values) == n_weeks
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "ice brent crude",
                "mm_long": mm_long_values[i],
                "mm_short": mm_short,
                "other_long": 0,
                "other_short": 0,
                "comm_long": 0,
                "comm_short": 0,
                "nonrep_long": 0,
                "nonrep_short": 0,
                "open_interest": open_interest,
            }
        )
    return pd.DataFrame(rows)


class _MockIceStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_cot_ice(self, contract: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


_PARAMS = {"contract": "ice brent crude"}


# ---------------------------------------------------------------------------
# Type A — bit-identisk default
# ---------------------------------------------------------------------------


def test_default_mode_returns_rank_percentile():
    """Default skal returnere rank-percentile / 100 (pre-R4-output)."""
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    score = cot_ice_mm_pct(store, "Test", _PARAMS)
    # current er det høyeste i 52-vinduet → pct ≈ 1.0
    assert score >= 0.95
    assert score <= 1.0


def test_default_unchanged_with_horizon_param():
    """R4-kontrakt: _horizon LESES men brukes ikke i default-output."""
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    no_horizon = cot_ice_mm_pct(store, "Test", _PARAMS)
    with_swing = cot_ice_mm_pct(store, "Test", {**_PARAMS, "_horizon": "SWING"})
    with_makro = cot_ice_mm_pct(store, "Test", {**_PARAMS, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


def test_pct_12m_equals_default_for_same_lookback():
    """mode='pct_12m' skal gi samme verdi som default ved lookback=52."""
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    default = cot_ice_mm_pct(store, "Test", _PARAMS)
    explicit = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
    assert default == explicit


# ---------------------------------------------------------------------------
# Type B — monotonisitet
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series():
    full_df = _build_ice_cot_df(n_weeks=80)
    prev = -1.0
    for n in range(53, 81):
        store = _MockIceStore(full_df.head(n))
        score = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    """Type B på pct_36m: krever ≥157 obs."""
    full_df = _build_ice_cot_df(n_weeks=180)
    prev = -1.0
    for n in range(157, 181):
        store = _MockIceStore(full_df.head(n))
        score = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_36m"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    series = [*values, values[-1] + 5000.0]
    df = _build_ice_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_ice_mm_pct(_MockIceStore(pre_df), "Test", {**_PARAMS, "mode": "delta_5d_z"})
    post_score = cot_ice_mm_pct(_MockIceStore(df), "Test", {**_PARAMS, "mode": "delta_5d_z"})

    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    series = list(values)
    last = values[-1]
    for _ in range(4):
        last = last + 1500.0
        series.append(last)
    df = _build_ice_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_ice_mm_pct(_MockIceStore(pre_df), "Test", {**_PARAMS, "mode": "delta_20d_z"})
    post_score = cot_ice_mm_pct(_MockIceStore(df), "Test", {**_PARAMS, "mode": "delta_20d_z"})

    assert post_score >= 0.75
    assert post_score > pre_score


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history():
    df = _build_ice_cot_df(n_weeks=80)
    store = _MockIceStore(df)
    score_36m = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_36m"})
    score_12m = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
    assert score_36m == score_12m


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile():
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    flag = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + (n // 2) * 100]
    df = _build_ice_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockIceStore(df)
    flag = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 0.0


def test_extreme_flag_soft_threshold():
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + 51 * 100]
    df = _build_ice_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockIceStore(df)
    soft = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_soft"})
    hard = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert soft >= hard


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default():
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    default = cot_ice_mm_pct(store, "Test", _PARAMS)
    unknown = cot_ice_mm_pct(store, "Test", {**_PARAMS, "mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# Manglende contract-param → 0.0 (defensive)
# ---------------------------------------------------------------------------


def test_missing_contract_returns_zero():
    df = _build_ice_cot_df(n_weeks=60)
    store = _MockIceStore(df)
    # Default uten contract
    assert cot_ice_mm_pct(store, "Test", {}) == 0.0
    # Mode uten contract
    assert cot_ice_mm_pct(store, "Test", {"mode": "pct_12m"}) == 0.0
