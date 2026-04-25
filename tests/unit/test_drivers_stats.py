"""Tester for `bedrock.engine.drivers._stats`.

Port-tester av cot-explorers ``rank_percentile`` + ``rolling_z``.
Verifiserer at adferden er identisk med original-implementasjonen
(samme grenseverdier, samme None-håndtering, samme MAD-skalering).
"""

from __future__ import annotations

import math

from bedrock.engine.drivers._stats import (
    MIN_OBS_FOR_PCTILE,
    rank_percentile,
    rolling_z,
)

# ---------------------------------------------------------------------------
# rank_percentile
# ---------------------------------------------------------------------------


def test_rank_percentile_returns_50_at_median() -> None:
    history = list(range(0, 100))  # 0..99 (100 obs)
    # 49.5 ligger mellom 49 og 50 i sortert liste; ingen verdier <= 49.5 men over 49 unntatt 49 selv
    # Andelen ≤ 49.5 = 50/100 = 50%
    pct = rank_percentile(49.5, history)
    assert pct == 50.0


def test_rank_percentile_returns_100_at_max() -> None:
    history = [10.0, 20.0, 30.0] * 10  # 30 obs (over MIN)
    pct = rank_percentile(100.0, history)
    assert pct == 100.0


def test_rank_percentile_returns_0_at_min() -> None:
    history = list(range(10, 40))  # 30 obs
    pct = rank_percentile(-10.0, history)
    # Ingen verdier ≤ -10
    assert pct == 0.0


def test_rank_percentile_none_for_short_history() -> None:
    """Færre enn MIN_OBS_FOR_PCTILE → None."""
    history = [1.0] * (MIN_OBS_FOR_PCTILE - 1)
    assert rank_percentile(0.5, history) is None


def test_rank_percentile_filters_none_in_history() -> None:
    """None-verdier skal hoppes over."""
    history = [None] * 10 + list(range(0, 30))  # 30 valid obs
    pct = rank_percentile(15.0, history)
    assert pct is not None
    # 16 verdier ≤ 15 (0..15) av 30 = 53.3
    assert pct == 53.3


def test_rank_percentile_none_current_returns_none() -> None:
    history = list(range(0, 100))
    assert rank_percentile(None, history) is None


def test_rank_percentile_none_history_returns_none() -> None:
    assert rank_percentile(50.0, None) is None  # type: ignore[arg-type]


def test_rank_percentile_at_minimum_observations() -> None:
    """Akkurat MIN_OBS_FOR_PCTILE skal gi resultat."""
    history = list(range(0, MIN_OBS_FOR_PCTILE))
    pct = rank_percentile(13.0, history)
    assert pct is not None


# ---------------------------------------------------------------------------
# rolling_z
# ---------------------------------------------------------------------------


def test_rolling_z_zero_at_median() -> None:
    """``current`` = median → z = 0."""
    history = list(range(0, 100))  # median = 49.5
    z = rolling_z(49.5, history)
    assert z == 0.0


def test_rolling_z_positive_above_median() -> None:
    history = list(range(0, 100))
    z = rolling_z(75.0, history)
    assert z is not None
    assert z > 0


def test_rolling_z_negative_below_median() -> None:
    history = list(range(0, 100))
    z = rolling_z(20.0, history)
    assert z is not None
    assert z < 0


def test_rolling_z_none_when_mad_zero() -> None:
    """Konstant historikk → MAD = 0 → None."""
    history = [50.0] * 30
    assert rolling_z(60.0, history) is None


def test_rolling_z_none_for_short_history() -> None:
    history = [1.0] * (MIN_OBS_FOR_PCTILE - 1)
    assert rolling_z(0.5, history) is None


def test_rolling_z_robust_to_outliers() -> None:
    """En enkelt ekstrem outlier skal ikke ødelegge MAD-skalering.

    MAD bruker median(|x - median(x)|), så et ekstremt punkt påvirker
    bare én observasjon. Std/mean ville blitt mer påvirket.
    """
    history = [*list(range(0, 30)), 10000]  # 31 obs, en ekstremt outlier
    z_normal = rolling_z(15.0, history)
    # MAD-z bør være moderat (rundt 0) selv med outlier til stede
    assert z_normal is not None
    assert abs(z_normal) < 5.0  # ikke blåst opp av outlier


def test_rolling_z_filters_none_in_history() -> None:
    history = [None, None, *list(range(0, 30))]  # 30 valid obs
    z = rolling_z(15.0, history)
    assert z is not None


def test_rolling_z_returns_finite_values() -> None:
    """Z-score skal være finitt (ikke inf/nan) for vanlig input."""
    history = [1.0, 2.0, 3.0, 4.0, 5.0] * 6  # 30 obs
    z = rolling_z(3.5, history)
    assert z is not None
    assert math.isfinite(z)


def test_rolling_z_none_current_returns_none() -> None:
    history = list(range(0, 100))
    assert rolling_z(None, history) is None  # type: ignore[arg-type]


def test_rolling_z_at_minimum_observations() -> None:
    """Akkurat MIN_OBS_FOR_PCTILE skal gi resultat."""
    history = list(range(0, MIN_OBS_FOR_PCTILE))
    z = rolling_z(15.0, history)
    assert z is not None
