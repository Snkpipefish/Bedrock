"""Integrasjons-tester for gates i Engine.score."""

from __future__ import annotations

import pytest

# Importer for side-effekt (registrer drivere + gates)
import bedrock.engine.drivers  # noqa: F401
import bedrock.engine.gates  # noqa: F401
from bedrock.engine.drivers import register
from bedrock.engine.engine import (
    AgriRules,
    DriverSpec,
    Engine,
    FinancialFamilySpec,
    FinancialRules,
    HorizonSpec,
)
from bedrock.engine.gates import GateSpec
from bedrock.engine.grade import (
    AgriGradeThreshold,
    AgriGradeThresholds,
    GradeThreshold,
    GradeThresholds,
)


# Registrer en dummy-driver én gang for disse testene
@register("always_one")
def _always_one(store, instrument, params):  # noqa: ANN001
    return 1.0


# ---------------------------------------------------------------------------
# Felles rules-byggere
# ---------------------------------------------------------------------------


def _financial_rules(gates: list[GateSpec] | None = None) -> FinancialRules:
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(
                family_weights={"trend": 1.0, "positioning": 1.0},
                max_score=2.0,
                min_score_publish=0.5,
            )
        },
        families={
            "trend": FinancialFamilySpec(
                drivers=[DriverSpec(name="always_one", weight=1.0)]
            ),
            "positioning": FinancialFamilySpec(
                drivers=[DriverSpec(name="always_one", weight=1.0)]
            ),
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=2),
            a=GradeThreshold(min_pct_of_max=0.55, min_families=2),
            b=GradeThreshold(min_pct_of_max=0.35, min_families=1),
        ),
        gates=gates or [],
    )


def _agri_rules_simple(gates: list[GateSpec] | None = None) -> AgriRules:
    from bedrock.engine.engine import AgriFamilySpec

    return AgriRules(
        aggregation="additive_sum",
        max_score=10.0,
        min_score_publish=3.0,
        families={
            "outlook": AgriFamilySpec(
                weight=5.0,
                drivers=[DriverSpec(name="always_one", weight=1.0)],
            )
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=8.0, min_families_active=1),
            a=AgriGradeThreshold(min_score=5.0, min_families_active=1),
            b=AgriGradeThreshold(min_score=3.0, min_families_active=1),
        ),
        gates=gates or [],
    )


# ---------------------------------------------------------------------------
# Financial + gates
# ---------------------------------------------------------------------------


def test_financial_score_without_gates() -> None:
    """Baseline: ingen gates → grade uforandret, gates_triggered tom."""
    result = Engine().score("Test", store=None, rules=_financial_rules(), horizon="SWING")
    # always_one × 2 families × weight 1.0 = 2.0 (= max_score). pct=1.0 → A+
    assert result.score == pytest.approx(2.0)
    assert result.grade == "A+"
    assert result.gates_triggered == []


def test_financial_triggered_gate_caps_grade() -> None:
    """Gate som utløses kapper grade fra A+ til A."""
    gates = [
        GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A")
    ]
    result = Engine().score(
        "Test", store=None, rules=_financial_rules(gates), horizon="SWING"
    )
    # Score fortsatt 2.0, men grade kappet
    assert result.score == pytest.approx(2.0)
    assert result.grade == "A"
    assert result.gates_triggered == ["min_active_families"]


def test_financial_untriggered_gate_no_cap() -> None:
    gates = [
        GateSpec(name="min_active_families", params={"min_count": 1}, cap_grade="B")
    ]
    result = Engine().score(
        "Test", store=None, rules=_financial_rules(gates), horizon="SWING"
    )
    assert result.grade == "A+"
    assert result.gates_triggered == []


def test_financial_multiple_gates_lowest_cap_wins() -> None:
    gates = [
        GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A"),
        GateSpec(name="score_below", params={"threshold": 100.0}, cap_grade="B"),
    ]
    result = Engine().score(
        "Test", store=None, rules=_financial_rules(gates), horizon="SWING"
    )
    assert result.grade == "B"
    assert result.gates_triggered == ["min_active_families", "score_below"]


def test_financial_cap_higher_than_grade_no_effect() -> None:
    """Gate med cap=A_plus på grade=A_plus endrer ingenting."""
    gates = [
        GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A+")
    ]
    result = Engine().score(
        "Test", store=None, rules=_financial_rules(gates), horizon="SWING"
    )
    assert result.grade == "A+"
    assert result.gates_triggered == ["min_active_families"]


# ---------------------------------------------------------------------------
# Agri + gates
# ---------------------------------------------------------------------------


def test_agri_score_without_gates() -> None:
    result = Engine().score("Test", store=None, rules=_agri_rules_simple())
    # additive_sum: family_score (1.0) × family_cap (5.0) = 5.0
    # → matches A-threshold (min_score=5.0)
    assert result.score == pytest.approx(5.0)
    assert result.grade == "A"
    assert result.gates_triggered == []


def test_agri_triggered_gate_caps() -> None:
    """Cap A-grade ned til B via score-below-gate."""
    gates = [
        GateSpec(name="score_below", params={"threshold": 10.0}, cap_grade="B")
    ]
    result = Engine().score("Test", store=None, rules=_agri_rules_simple(gates))
    assert result.score == pytest.approx(5.0)
    assert result.grade == "B"
    assert result.gates_triggered == ["score_below"]


# ---------------------------------------------------------------------------
# Explain-trace
# ---------------------------------------------------------------------------


def test_gates_triggered_populates_explain() -> None:
    """`GroupResult.gates_triggered` skal være sync med cap-beslutning."""
    gates = [
        GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A"),
    ]
    result = Engine().score(
        "Gold", store=None, rules=_financial_rules(gates), horizon="SWING"
    )
    assert "min_active_families" in result.gates_triggered
    assert result.grade == "A"
