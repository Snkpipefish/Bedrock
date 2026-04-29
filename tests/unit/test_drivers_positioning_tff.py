"""Tester for TFF-baserte positioning-drivere (D1 A4 session 128).

Sub-fase 12.7 D1 A4. Verifiserer at:

- ``positioning_lev_funds_pct`` og ``positioning_asset_mgr_pct``
  produserer rank-percentile / 100 fra TFF-data.
- Default (mode=None) er bit-identisk pattern til positioning_mm_pct.
- pct_12m monotonisitet på syntetisk strigende serie (Type B).
- delta_5d_z regime-shift (Type C).
- pct_36m fall-back ved utilstrekkelig historikk.
- extreme_flag_hard/soft modes.
- _horizon-param leses uten output-effekt (ADR-010 R4-kontrakt).
- Ukjent mode → fall-back til default.

Mock-store-mønster matcher
``test_drivers_positioning_horizon_modes.py``-presedensen.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from bedrock.engine.drivers.positioning import (
    positioning_asset_mgr_pct,
    positioning_lev_funds_pct,
)


def _build_tff_df(
    *,
    n_weeks: int,
    lev_funds_long_values: list[float] | None = None,
    asset_mgr_long_values: list[float] | None = None,
    lev_funds_long_start: float = 100_000,
    lev_funds_long_step: float = 1_000,
    lev_funds_short: float = 50_000,
    asset_mgr_long_start: float = 200_000,
    asset_mgr_long_step: float = 500,
    asset_mgr_short: float = 100_000,
    open_interest: float = 1_000_000,
) -> pd.DataFrame:
    """Bygger TFF-historikk. Default lager strigende lev_funds + asset_mgr."""
    base = date(2022, 1, 5)
    rows = []
    if lev_funds_long_values is None:
        lev_funds_long_values = [
            lev_funds_long_start + lev_funds_long_step * i for i in range(n_weeks)
        ]
    if asset_mgr_long_values is None:
        asset_mgr_long_values = [
            asset_mgr_long_start + asset_mgr_long_step * i for i in range(n_weeks)
        ]
    assert len(lev_funds_long_values) == n_weeks
    assert len(asset_mgr_long_values) == n_weeks
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "TEST",
                "dealer_long": 50_000,
                "dealer_short": 50_000,
                "asset_mgr_long": asset_mgr_long_values[i],
                "asset_mgr_short": asset_mgr_short,
                "lev_funds_long": lev_funds_long_values[i],
                "lev_funds_short": lev_funds_short,
                "other_long": 10_000,
                "other_short": 10_000,
                "nonrep_long": 5_000,
                "nonrep_short": 5_000,
                "open_interest": open_interest,
            }
        )
    return pd.DataFrame(rows)


class _MockTffStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_cot_tff(self, contract: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


@pytest.fixture
def mock_instrument(monkeypatch):
    class _Meta:
        cot_contract = "TEST"
        cot_report = "legacy"  # ignoreres av TFF-loader

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )


# ---------------------------------------------------------------------------
# Type A — bit-identisk default (mode=None)
# ---------------------------------------------------------------------------


def test_lev_funds_default_returns_top_percentile(mock_instrument):
    """Strigende lev_funds_long → siste obs er topp → pct ≈ 1.0."""
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    score = positioning_lev_funds_pct(store, "Test", {})
    assert score >= 0.95
    assert score <= 1.0


def test_asset_mgr_default_returns_top_percentile(mock_instrument):
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    score = positioning_asset_mgr_pct(store, "Test", {})
    assert score >= 0.95


def test_lev_funds_horizon_param_does_not_change_output(mock_instrument):
    """R4-kontrakt: _horizon LESES men brukes ikke i default-output."""
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    no_horizon = positioning_lev_funds_pct(store, "Test", {})
    with_swing = positioning_lev_funds_pct(store, "Test", {"_horizon": "SWING"})
    with_makro = positioning_lev_funds_pct(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_12m
# ---------------------------------------------------------------------------


def test_lev_funds_pct_12m_monotonic_on_strictly_increasing_series(mock_instrument):
    full_df = _build_tff_df(n_weeks=80)
    prev = -1.0
    for n in range(53, 81):
        store = _MockTffStore(full_df.head(n))
        score = positioning_lev_funds_pct(store, "Test", {"mode": "pct_12m"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at n={n}"
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta_5d_z
# ---------------------------------------------------------------------------


def test_lev_funds_delta_5d_z_reacts_to_regime_shift(mock_instrument):
    """delta_5d_z på Lev Funds-net fanger ekstrem 1-rapport-hopp."""
    import random

    rng = random.Random(42)
    n_pre = 60
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    series = [*values, values[-1] + 5000.0]
    df = _build_tff_df(n_weeks=len(series), lev_funds_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = positioning_lev_funds_pct(_MockTffStore(pre_df), "Test", {"mode": "delta_5d_z"})
    post_score = positioning_lev_funds_pct(_MockTffStore(df), "Test", {"mode": "delta_5d_z"})
    assert post_score >= 0.75
    assert post_score > pre_score


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_lev_funds_pct_36m_fallback_to_12m_on_short_history(mock_instrument):
    df = _build_tff_df(n_weeks=80)  # < 156 obs
    store = _MockTffStore(df)
    score_36m = positioning_lev_funds_pct(store, "Test", {"mode": "pct_36m"})
    score_12m = positioning_lev_funds_pct(store, "Test", {"mode": "pct_12m"})
    assert score_36m == score_12m


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_lev_funds_extreme_flag_hard_at_top_percentile(mock_instrument):
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    flag = positioning_lev_funds_pct(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_asset_mgr_extreme_flag_hard_at_top_percentile(mock_instrument):
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    flag = positioning_asset_mgr_pct(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_lev_funds_extreme_flag_soft_at_least_as_lenient(mock_instrument):
    """Soft (5/95) trigger minst like ofte som hard (2/98)."""
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + 51 * 100]
    df = _build_tff_df(n_weeks=n, lev_funds_long_values=values)
    store = _MockTffStore(df)
    soft = positioning_lev_funds_pct(store, "Test", {"mode": "extreme_flag_soft"})
    hard = positioning_lev_funds_pct(store, "Test", {"mode": "extreme_flag_hard"})
    assert soft >= hard


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_lev_funds_unknown_mode_falls_back_to_default(mock_instrument):
    df = _build_tff_df(n_weeks=60)
    store = _MockTffStore(df)
    default = positioning_lev_funds_pct(store, "Test", {})
    unknown = positioning_lev_funds_pct(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# Asset Manager-spesifikk: differensiering fra Lev Funds
# ---------------------------------------------------------------------------


def test_asset_mgr_uses_different_field_than_lev_funds(mock_instrument):
    """Asset Manager-driver leser asset_mgr_long, ikke lev_funds_long.

    Bygger en serie der lev_funds er ekstrem (siste topp) men asset_mgr
    er median. Asset_mgr-driver skal IKKE returnere 1.0.
    """
    n = 60
    # Lev funds: monotont stigende (siste = topp)
    lev = [100_000.0 + i * 1_000 for i in range(n)]
    # Asset mgr: midtflat (siste obs er median)
    asset = [200_000.0 + i * 100 for i in range(n - 1)] + [200_000.0 + (n // 2) * 100]
    df = _build_tff_df(
        n_weeks=n,
        lev_funds_long_values=lev,
        asset_mgr_long_values=asset,
    )
    store = _MockTffStore(df)

    lev_score = positioning_lev_funds_pct(store, "Test", {})
    asset_score = positioning_asset_mgr_pct(store, "Test", {})

    assert lev_score >= 0.95, "lev_funds-driver burde se topp-percentile"
    assert asset_score < 0.6, f"asset_mgr-driver burde se midtflat, fikk {asset_score}"
