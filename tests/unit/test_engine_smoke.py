"""Smoke-tester for Engine.score() med mock-drivere.

Dette er ikke logiske scoring-scenarier (de kommer i `tests/logical/` når
ekte drivere + DataStore finnes). Her verifiseres kun at Engine wire-er
registry -> aggregator -> grade korrekt sammen.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bedrock.engine import drivers
from bedrock.engine.engine import (
    DriverSpec,
    Engine,
    FamilySpec,
    HorizonSpec,
    Rules,
)
from bedrock.engine.grade import GradeThreshold, GradeThresholds


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


@pytest.fixture
def minimal_rules() -> Rules:
    """To familier (trend, macro), én driver per, weighted_horizon."""
    return Rules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(
                family_weights={"trend": 1.0, "macro": 1.0},
                max_score=6.0,
                min_score_publish=2.5,
            ),
        },
        families={
            "trend": FamilySpec(drivers=[DriverSpec(name="mock_full", weight=1.0)]),
            "macro": FamilySpec(drivers=[DriverSpec(name="mock_half", weight=1.0)]),
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=2),
            a=GradeThreshold(min_pct_of_max=0.55, min_families=2),
            b=GradeThreshold(min_pct_of_max=0.35, min_families=1),
        ),
    )


def test_engine_scores_with_mock_drivers(minimal_rules: Rules) -> None:
    @drivers.register("mock_full")
    def _full(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("mock_half")
    def _half(store: object, instrument: str, params: dict) -> float:
        return 0.5

    result = Engine().score("Gold", store=None, rules=minimal_rules, horizon="SWING")

    # trend = 1.0 * weight 1.0 = 1.0 ; macro = 0.5 * weight 1.0 = 0.5
    # weighted_horizon: 1.0 * 1.0 + 0.5 * 1.0 = 1.5
    assert result.instrument == "Gold"
    assert result.horizon == "SWING"
    assert result.aggregation == "weighted_horizon"
    assert result.score == pytest.approx(1.5)
    assert result.max_score == 6.0
    assert result.families["trend"].score == pytest.approx(1.0)
    assert result.families["macro"].score == pytest.approx(0.5)
    assert result.active_families == 2


def test_engine_driver_trace_records_contributions(minimal_rules: Rules) -> None:
    @drivers.register("mock_full")
    def _full(store: object, instrument: str, params: dict) -> float:
        return 0.8

    @drivers.register("mock_half")
    def _half(store: object, instrument: str, params: dict) -> float:
        return 0.4

    result = Engine().score("Gold", store=None, rules=minimal_rules, horizon="SWING")

    trend_driver = result.families["trend"].drivers[0]
    assert trend_driver.name == "mock_full"
    assert trend_driver.value == pytest.approx(0.8)
    assert trend_driver.weight == 1.0
    assert trend_driver.contribution == pytest.approx(0.8)


def test_engine_passes_params_to_driver(minimal_rules: Rules) -> None:
    """Params fra YAML skal videresendes uendret til driver-funksjonen."""
    received: dict[str, dict] = {}

    @drivers.register("mock_full")
    def _full(store: object, instrument: str, params: dict) -> float:
        received["full"] = params
        return 1.0

    @drivers.register("mock_half")
    def _half(store: object, instrument: str, params: dict) -> float:
        return 0.5

    rules = minimal_rules.model_copy()
    rules.families["trend"].drivers[0] = DriverSpec(
        name="mock_full",
        weight=1.0,
        params={"tf": "D1", "lookback": 200},
    )

    Engine().score("Gold", None, rules, "SWING")
    assert received["full"] == {"tf": "D1", "lookback": 200}


def test_engine_unknown_horizon_raises_keyerror(minimal_rules: Rules) -> None:
    @drivers.register("mock_full")
    def _f(store: object, instrument: str, params: dict) -> float:
        return 0.0

    @drivers.register("mock_half")
    def _h(store: object, instrument: str, params: dict) -> float:
        return 0.0

    with pytest.raises(KeyError, match="Horizon 'MAKRO'"):
        Engine().score("Gold", None, minimal_rules, horizon="MAKRO")


def test_engine_additive_sum_not_implemented_yet(minimal_rules: Rules) -> None:
    rules = minimal_rules.model_copy(update={"aggregation": "additive_sum"})
    with pytest.raises(NotImplementedError, match="additive_sum"):
        Engine().score("Gold", None, rules, horizon="SWING")


def test_engine_active_families_excludes_zero_scored_families(
    minimal_rules: Rules,
) -> None:
    @drivers.register("mock_full")
    def _full(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("mock_half")
    def _zero(store: object, instrument: str, params: dict) -> float:
        return 0.0  # macro-familien får score 0 -> ikke aktiv

    result = Engine().score("Gold", None, minimal_rules, "SWING")
    assert result.active_families == 1
    assert result.families["macro"].score == 0.0
