"""Smoke-tester for Engine.score() med AgriRules + additive_sum."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bedrock.engine import drivers
from bedrock.engine.engine import (
    AgriFamilySpec,
    AgriRules,
    DriverSpec,
    Engine,
)
from bedrock.engine.grade import AgriGradeThreshold, AgriGradeThresholds


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


@pytest.fixture
def corn_rules() -> AgriRules:
    """Forenklet Corn-lignende regel fra PLAN § 4.3. Tre familier for å
    holde testen beviselig, ikke alle 6 som i den faktiske YAML-en."""
    return AgriRules(
        aggregation="additive_sum",
        max_score=10.0,
        min_score_publish=4.0,
        families={
            "outlook": AgriFamilySpec(
                weight=5.0,
                drivers=[DriverSpec(name="agri_outlook_mock", weight=1.0)],
            ),
            "yield": AgriFamilySpec(
                weight=3.0,
                drivers=[DriverSpec(name="agri_yield_mock", weight=1.0)],
            ),
            "weather": AgriFamilySpec(
                weight=2.0,
                drivers=[DriverSpec(name="agri_weather_mock", weight=1.0)],
            ),
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=8.0, min_families_active=3),
            a=AgriGradeThreshold(min_score=6.0, min_families_active=2),
            b=AgriGradeThreshold(min_score=3.0, min_families_active=2),
        ),
    )


def test_engine_agri_scores_additive_sum(corn_rules: AgriRules) -> None:
    """outlook=1.0 * 5 + yield=1.0 * 3 + weather=1.0 * 2 = 10.0."""

    @drivers.register("agri_outlook_mock")
    def _o(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("agri_yield_mock")
    def _y(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("agri_weather_mock")
    def _w(store: object, instrument: str, params: dict) -> float:
        return 1.0

    result = Engine().score("Corn", store=None, rules=corn_rules)

    assert result.instrument == "Corn"
    assert result.horizon is None  # agri: horizon kommer fra setup-generator (Fase 4)
    assert result.aggregation == "additive_sum"
    assert result.score == pytest.approx(10.0)
    assert result.max_score == 10.0
    assert result.grade == "A+"
    assert result.active_families == 3


def test_engine_agri_partial_scores_scale_by_family_cap(corn_rules: AgriRules) -> None:
    """outlook=0.5 * 5 + yield=0.0 * 3 + weather=1.0 * 2 = 2.5 + 0 + 2.0 = 4.5."""

    @drivers.register("agri_outlook_mock")
    def _o(store: object, instrument: str, params: dict) -> float:
        return 0.5

    @drivers.register("agri_yield_mock")
    def _y(store: object, instrument: str, params: dict) -> float:
        return 0.0

    @drivers.register("agri_weather_mock")
    def _w(store: object, instrument: str, params: dict) -> float:
        return 1.0

    result = Engine().score("Corn", None, corn_rules)

    assert result.score == pytest.approx(4.5)
    assert result.active_families == 2  # yield er 0 -> inaktiv
    # 4.5 >= 3.0 (B-min) og 2 aktive, men 4.5 < 6.0 (A-min) -> B
    assert result.grade == "B"


def test_engine_agri_horizon_argument_ignored(corn_rules: AgriRules) -> None:
    """AgriRules skal ignorere `horizon`-argumentet (ingen feil heller)."""

    @drivers.register("agri_outlook_mock")
    def _o(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("agri_yield_mock")
    def _y(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("agri_weather_mock")
    def _w(store: object, instrument: str, params: dict) -> float:
        return 1.0

    # Skal ikke kaste selv om horizon settes.
    result = Engine().score("Corn", None, corn_rules, horizon="SWING")
    assert result.horizon is None


def test_engine_agri_explain_trace_has_per_driver_contributions(
    corn_rules: AgriRules,
) -> None:
    @drivers.register("agri_outlook_mock")
    def _o(store: object, instrument: str, params: dict) -> float:
        return 0.8

    @drivers.register("agri_yield_mock")
    def _y(store: object, instrument: str, params: dict) -> float:
        return 0.6

    @drivers.register("agri_weather_mock")
    def _w(store: object, instrument: str, params: dict) -> float:
        return 0.3

    result = Engine().score("Corn", None, corn_rules)

    # Familie-score er driver-vektet sum (før familie-cap anvendes i aggregator).
    assert result.families["outlook"].score == pytest.approx(0.8)
    assert result.families["outlook"].drivers[0].contribution == pytest.approx(0.8)


def test_agri_rules_yaml_alias_parse() -> None:
    """Sikrer at YAML-style nøkler (`A_plus`, `A`, `B`) parses korrekt."""
    yaml_like = {
        "aggregation": "additive_sum",
        "max_score": 18,
        "min_score_publish": 7,
        "families": {
            "outlook": {
                "weight": 5,
                "drivers": [{"name": "x", "weight": 1.0}],
            },
        },
        "grade_thresholds": {
            "A_plus": {"min_score": 14, "min_families_active": 4},
            "A": {"min_score": 10, "min_families_active": 3},
            "B": {"min_score": 7, "min_families_active": 2},
        },
    }
    rules = AgriRules.model_validate(yaml_like)
    assert rules.max_score == 18
    assert rules.grade_thresholds.a_plus.min_score == 14
    assert rules.families["outlook"].weight == 5
