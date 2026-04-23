"""Tester for aggregator-funksjoner."""

from __future__ import annotations

from bedrock.engine.aggregators import weighted_horizon


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
