"""Tester for R4-horisont-modes på ``cot_euronext_mm_pct``.

Sub-fase 12.7 R4 batch 4 (session 123). Parallell til
``test_drivers_cot_ice_horizon_modes.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers.positioning import cot_euronext_mm_pct


def _build_euronext_cot_df(
    *,
    n_weeks: int,
    mm_long_values: list[float] | None = None,
    mm_long_start: float = 100_000,
    mm_long_step: float = 1_000,
    mm_short: float = 50_000,
    open_interest: float = 300_000,
) -> pd.DataFrame:
    base = date(2022, 1, 5)
    rows = []
    if mm_long_values is None:
        mm_long_values = [mm_long_start + mm_long_step * i for i in range(n_weeks)]
    assert len(mm_long_values) == n_weeks
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "euronext milling wheat",
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


class _MockEuronextStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_cot_euronext(self, contract: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


_PARAMS = {"contract": "euronext milling wheat"}


def test_default_mode_returns_rank_percentile():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    score = cot_euronext_mm_pct(store, "Test", _PARAMS)
    assert score >= 0.95
    assert score <= 1.0


def test_default_unchanged_with_horizon_param():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    no_horizon = cot_euronext_mm_pct(store, "Test", _PARAMS)
    with_swing = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "_horizon": "SWING"})
    with_makro = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


def test_pct_12m_equals_default_for_same_lookback():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    default = cot_euronext_mm_pct(store, "Test", _PARAMS)
    explicit = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
    assert default == explicit


def test_pct_12m_monotonic_on_strictly_increasing_series():
    full_df = _build_euronext_cot_df(n_weeks=80)
    prev = -1.0
    for n in range(53, 81):
        store = _MockEuronextStore(full_df.head(n))
        score = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_series():
    full_df = _build_euronext_cot_df(n_weeks=180)
    prev = -1.0
    for n in range(157, 181):
        store = _MockEuronextStore(full_df.head(n))
        score = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_36m"})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    series = [*values, values[-1] + 5000.0]
    df = _build_euronext_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_euronext_mm_pct(
        _MockEuronextStore(pre_df), "Test", {**_PARAMS, "mode": "delta_5d_z"}
    )
    post_score = cot_euronext_mm_pct(
        _MockEuronextStore(df), "Test", {**_PARAMS, "mode": "delta_5d_z"}
    )

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
    df = _build_euronext_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_euronext_mm_pct(
        _MockEuronextStore(pre_df), "Test", {**_PARAMS, "mode": "delta_20d_z"}
    )
    post_score = cot_euronext_mm_pct(
        _MockEuronextStore(df), "Test", {**_PARAMS, "mode": "delta_20d_z"}
    )

    assert post_score >= 0.75
    assert post_score > pre_score


def test_pct_36m_fallback_to_12m_on_short_history():
    df = _build_euronext_cot_df(n_weeks=80)
    store = _MockEuronextStore(df)
    score_36m = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_36m"})
    score_12m = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "pct_12m"})
    assert score_36m == score_12m


def test_extreme_flag_hard_at_top_percentile():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    flag = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + (n // 2) * 100]
    df = _build_euronext_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockEuronextStore(df)
    flag = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 0.0


def test_extreme_flag_soft_threshold():
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + 51 * 100]
    df = _build_euronext_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockEuronextStore(df)
    soft = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_soft"})
    hard = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert soft >= hard


def test_unknown_mode_falls_back_to_default():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    default = cot_euronext_mm_pct(store, "Test", _PARAMS)
    unknown = cot_euronext_mm_pct(store, "Test", {**_PARAMS, "mode": "not_a_real_mode"})
    assert default == unknown


def test_missing_contract_returns_zero():
    df = _build_euronext_cot_df(n_weeks=60)
    store = _MockEuronextStore(df)
    assert cot_euronext_mm_pct(store, "Test", {}) == 0.0
    assert cot_euronext_mm_pct(store, "Test", {"mode": "pct_12m"}) == 0.0
