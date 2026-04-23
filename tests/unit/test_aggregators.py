"""Tester for aggregator-funksjoner."""

from __future__ import annotations

import pytest

from bedrock.engine.aggregators import additive_sum, weighted_horizon


def test_weighted_horizon_sum_with_unit_weights() -> None:
    scores = {"trend": 0.5, "positioning": 0.8}
    weights = {"trend": 1.0, "positioning": 1.0}
    assert weighted_horizon(scores, weights) == 1.3


def test_weighted_horizon_applies_per_family_weights() -> None:
    scores = {"trend": 0.5, "positioning": 0.8}
    weights = {"trend": 2.0, "positioning": 0.5}
    # 0.5 * 2.0 + 0.8 * 0.5 = 1.4
    assert weighted_horizon(scores, weights) == 1.4


def test_weighted_horizon_missing_score_treated_as_zero() -> None:
    """Familier i vekter men ikke scores -> 0-bidrag (familie produserte
    ingen score, men horisonten forventet den)."""
    scores = {"trend": 0.5}
    weights = {"trend": 1.0, "macro": 1.0}
    assert weighted_horizon(scores, weights) == 0.5


def test_weighted_horizon_ignores_unweighted_families() -> None:
    """Familier i scores men ikke vekter ignoreres — bruker har ikke gitt
    dem vekt for denne horisonten."""
    scores = {"trend": 0.5, "unwanted": 99.0}
    weights = {"trend": 1.0}
    assert weighted_horizon(scores, weights) == 0.5


def test_weighted_horizon_empty_weights_yields_zero() -> None:
    assert weighted_horizon({"trend": 0.5}, {}) == 0.0


def test_weighted_horizon_all_missing_yields_zero() -> None:
    assert weighted_horizon({}, {"trend": 1.0, "macro": 1.0}) == 0.0


# ---------------------------------------------------------------------------
# additive_sum (agri)
# ---------------------------------------------------------------------------


def test_additive_sum_multiplies_family_score_by_cap() -> None:
    """outlook=1.0 * cap 5.0 + yield=1.0 * cap 3.0 = 8.0."""
    scores = {"outlook": 1.0, "yield": 1.0}
    caps = {"outlook": 5.0, "yield": 3.0}
    assert additive_sum(scores, caps) == 8.0


def test_additive_sum_partial_family_scores() -> None:
    """outlook=0.5 * 5 + yield=0.8 * 3 = 2.5 + 2.4 = 4.9."""
    scores = {"outlook": 0.5, "yield": 0.8}
    caps = {"outlook": 5.0, "yield": 3.0}
    assert additive_sum(scores, caps) == pytest.approx(4.9)


def test_additive_sum_missing_family_scored_as_zero() -> None:
    scores = {"outlook": 1.0}
    caps = {"outlook": 5.0, "yield": 3.0}
    assert additive_sum(scores, caps) == 5.0


def test_additive_sum_ignores_families_without_cap() -> None:
    scores = {"outlook": 1.0, "unknown": 99.0}
    caps = {"outlook": 5.0}
    assert additive_sum(scores, caps) == 5.0


def test_additive_sum_empty_caps_yields_zero() -> None:
    assert additive_sum({"outlook": 1.0}, {}) == 0.0
