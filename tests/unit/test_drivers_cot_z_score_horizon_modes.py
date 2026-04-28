"""Tester for R4-horisont-modes på ``cot_z_score``.

Sub-fase 12.7 R4 batch 4 (session 123). Verifiserer at:

- Default (mode=None) er bit-identisk med pre-R4 (z-score MAD-trapp).
- ``mode="pct_12m"`` produserer monotont stigende output på syntetisk
  strigende serie (Type B per ``docs/driver_horizon_pattern.md`` § 2.2).
- ``mode="pct_36m"`` har monotonisitet på lengre fixture og fall-backer
  til pct_12m ved utilstrekkelig historikk (per § 1.1).
- ``mode="delta_5d_z"`` reagerer på regime-shift (Type C per § 2.3).
- ``mode="delta_20d_z"`` reagerer på regime-shift med 4-rapport-delta.
- ``mode="extreme_flag_*"`` returnerer 1.0 ved 2/98- og 5/95-tersklene.
- ``_horizon``-param leses uten å påvirke default-output.
- Ukjent mode fall-backer til default.

Bruker samme in-memory mock-store-mønster som
``test_drivers_positioning_horizon_modes.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from bedrock.engine.drivers.positioning import cot_z_score


def _build_cot_df(
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
                "contract": "TEST",
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


class _MockStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_cot(self, contract: str, report: str = "disaggregated", last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


@pytest.fixture
def mock_instrument(monkeypatch):
    class _Meta:
        cot_contract = "TEST"
        cot_report = "disaggregated"

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )


# ---------------------------------------------------------------------------
# Type A — bit-identisk default (mode=None)
# ---------------------------------------------------------------------------


def test_default_mode_returns_z_score_trap(mock_instrument):
    """Default skal returnere z-score-trapp på rå MM net.

    Med strigende mm_long er current det høyeste. MAD-basert z-score
    på en jevn lineær serie gir z ≈ 1.35 (median er midten, MAD
    proporsjonal med half-spread, 1.4826-skaleringen normaliserer mot
    σ-ekvivalent). Det treffer trappens z≥1.0-grein → 0.75.
    """
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    score = cot_z_score(store, "Test", {})
    # Z ≈ 1.35 → 0.75 (z ≥ 1.0-grein i default-trappen)
    assert score == 0.75


def test_default_unchanged_with_horizon_param(mock_instrument):
    """R4-kontrakt: _horizon LESES men brukes ikke i default-output."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    no_horizon = cot_z_score(store, "Test", {})
    with_swing = cot_z_score(store, "Test", {"_horizon": "SWING"})
    with_makro = cot_z_score(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_12m
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series(mock_instrument):
    """Type B (§ 2.2): pct_12m på strigende serie → monotont stigende."""
    full_df = _build_cot_df(n_weeks=80)
    prev = -1.0
    for n in range(53, 81):
        store = _MockStore(full_df.head(n))
        score = cot_z_score(store, "Test", {"mode": "pct_12m"})
        assert score >= prev, (
            f"pct_12m fell from {prev} to {score} at n={n} på strengt stigende serie"
        )
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_36m (lengre fixture)
# ---------------------------------------------------------------------------


def test_pct_36m_monotonic_on_strictly_increasing_series(mock_instrument):
    """Type B på pct_36m: krever ≥157 obs for å aktivere 156-vinduet."""
    full_df = _build_cot_df(n_weeks=180)
    prev = -1.0
    for n in range(157, 181):
        store = _MockStore(full_df.head(n))
        score = cot_z_score(store, "Test", {"mode": "pct_36m"})
        assert score >= prev, (
            f"pct_36m fell from {prev} to {score} at n={n} på strengt stigende serie"
        )
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta_5d_z
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift(mock_instrument):
    """Type C (§ 2.3): delta_5d_z fanger stort hopp i underliggende serie."""
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    series = [*values, values[-1] + 5000.0]
    df = _build_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_z_score(_MockStore(pre_df), "Test", {"mode": "delta_5d_z"})
    post_score = cot_z_score(_MockStore(df), "Test", {"mode": "delta_5d_z"})

    assert post_score >= 0.75, f"delta_5d_z post-hopp = {post_score}, forventet ≥ 0.75 (z ≥ 1)"
    assert post_score > pre_score, (
        f"delta_5d_z post-hopp ({post_score}) skulle være > pre ({pre_score})"
    )


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta_20d_z (4-rapport-delta)
# ---------------------------------------------------------------------------


def test_delta_20d_z_reacts_to_regime_shift(mock_instrument):
    """Type C: delta_20d_z fanger gradvis trend over 4 rapporter (~28d)."""
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    # Gradvis 4-rapport-trend som akkumulerer til stort delta
    series = list(values)
    last = values[-1]
    for _ in range(4):
        last = last + 1500.0
        series.append(last)
    df = _build_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = cot_z_score(_MockStore(pre_df), "Test", {"mode": "delta_20d_z"})
    post_score = cot_z_score(_MockStore(df), "Test", {"mode": "delta_20d_z"})

    assert post_score >= 0.75, f"delta_20d_z post-trend = {post_score}, forventet ≥ 0.75 (z ≥ 1)"
    assert post_score > pre_score, (
        f"delta_20d_z post-trend ({post_score}) skulle være > pre ({pre_score})"
    )


# ---------------------------------------------------------------------------
# pct_36m fall-back ved utilstrekkelig historikk
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history(mock_instrument):
    """Ved <156 obs skal pct_36m logge info og fall-back til pct_12m.

    Per § 1.1: ikke 0.0, ikke krasj — graceful fall-back.
    """
    df = _build_cot_df(n_weeks=80)  # 80 < 156 obs
    store = _MockStore(df)

    score_36m = cot_z_score(store, "Test", {"mode": "pct_36m"})
    score_12m = cot_z_score(store, "Test", {"mode": "pct_12m"})
    assert score_36m == score_12m, (
        f"pct_36m fall-back skulle gi samme som pct_12m, fikk {score_36m} vs {score_12m}"
    )


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile(mock_instrument):
    """Når current er det høyeste i 52-historikken: pct ≈ 1.0 ⇒ flag = 1.0."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    flag = cot_z_score(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median(mock_instrument):
    """Når current ligger nær median: flag = 0.0."""
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + (n // 2) * 100]
    df = _build_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockStore(df)
    flag = cot_z_score(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


def test_extreme_flag_soft_threshold(mock_instrument):
    """Soft (5/95) skal trigge minst like ofte som hard (2/98)."""
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + 51 * 100]
    df = _build_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockStore(df)
    soft = cot_z_score(store, "Test", {"mode": "extreme_flag_soft"})
    hard = cot_z_score(store, "Test", {"mode": "extreme_flag_hard"})
    assert soft >= hard


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default(mock_instrument):
    """Ukjent mode-verdi skal logge warning og returnere default-output."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    default = cot_z_score(store, "Test", {})
    unknown = cot_z_score(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown
