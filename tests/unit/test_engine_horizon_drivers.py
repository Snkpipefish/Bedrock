"""Tester for sub-fase 12.9 Fase 3 — per-horisont-drivere.

Verifiserer at:

A. `DriverSpec.horizons` filtrerer drivere per horisont.
B. Filtrerte drivere får ikke kjørt sin score-funksjon (ikke fn(store, ..)).
C. Family-vekter re-normaliseres slik at sum=1.0 (financial) bevares.
D. Tom familie etter filter → score=0.0, ingen drivere kjørt.
E. None horizon (agri) → ingen filtrering, status quo.

Mønster fra test_engine_horizon_propagation.py + test_engine_direction_polarity.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bedrock.engine import drivers
from bedrock.engine.engine import (
    AgriFamilySpec,
    AgriRules,
    DriverSpec,
    Engine,
    FinancialFamilySpec,
    FinancialRules,
    HorizonSpec,
)
from bedrock.engine.grade import (
    AgriGradeThreshold,
    AgriGradeThresholds,
    GradeThreshold,
    GradeThresholds,
)


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


def _financial_rules_two_drivers() -> FinancialRules:
    """Familie med 2 drivere: 'always' + 'scalp_only'.

    always: vekt 0.6, alle horisonter
    scalp_only: vekt 0.4, kun SCALP
    """
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SCALP": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "SWING": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "MAKRO": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
        },
        families={
            "f1": FinancialFamilySpec(
                drivers=[
                    DriverSpec(name="always", weight=0.6),
                    DriverSpec(name="scalp_only", weight=0.4, horizons=["SCALP"]),
                ]
            )
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.85, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.70, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.50, min_families=1),
        ),
    )


def test_horizons_filter_skips_non_matching_drivers() -> None:
    """SWING-score skal ikke kjøre 'scalp_only'-driveren."""
    calls: list[str] = []

    @drivers.register("always")
    def _always(store: object, instrument: str, params: dict) -> float:
        calls.append("always")
        return 1.0

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        calls.append("scalp_only")
        return 1.0

    rules = _financial_rules_two_drivers()
    Engine().score("X", store=object(), rules=rules, horizon="SWING")

    assert "always" in calls
    assert "scalp_only" not in calls


def test_horizons_filter_includes_matching_drivers() -> None:
    """SCALP-score skal kjøre BÅDE 'always' og 'scalp_only'."""
    calls: list[str] = []

    @drivers.register("always")
    def _always(store: object, instrument: str, params: dict) -> float:
        calls.append("always")
        return 1.0

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        calls.append("scalp_only")
        return 1.0

    rules = _financial_rules_two_drivers()
    Engine().score("X", store=object(), rules=rules, horizon="SCALP")

    assert calls.count("always") == 1
    assert calls.count("scalp_only") == 1


def test_renormalization_preserves_family_score() -> None:
    """Når 'scalp_only' filtreres ut, skaleres 'always' fra 0.6 til 1.0
    slik at family-score med begge drivere = 1.0 == family-score med kun
    'always' (re-normalisert).

    Setup: begge drivere returnerer 1.0.
    SCALP: family_score = 1.0*0.6 + 1.0*0.4 = 1.0
    SWING: 'scalp_only' filtrert. Renorm: 0.6/0.6 = 1.0. 1.0*1.0 = 1.0
    """

    @drivers.register("always")
    def _always(store: object, instrument: str, params: dict) -> float:
        return 1.0

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        return 1.0

    rules = _financial_rules_two_drivers()
    eng = Engine()

    res_scalp = eng.score("X", store=object(), rules=rules, horizon="SCALP")
    res_swing = eng.score("X", store=object(), rules=rules, horizon="SWING")

    f1_scalp = res_scalp.families["f1"].score
    f1_swing = res_swing.families["f1"].score
    assert abs(f1_scalp - 1.0) < 1e-9
    assert abs(f1_swing - 1.0) < 1e-9


def test_renormalization_with_partial_values() -> None:
    """Drivere returnerer ulike verdier — renorm må bevare proporsjonen."""

    @drivers.register("always")
    def _always(store: object, instrument: str, params: dict) -> float:
        return 0.5

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        return 1.0

    rules = _financial_rules_two_drivers()
    eng = Engine()

    res_scalp = eng.score("X", store=object(), rules=rules, horizon="SCALP")
    res_swing = eng.score("X", store=object(), rules=rules, horizon="SWING")

    # SCALP: 0.5*0.6 + 1.0*0.4 = 0.3 + 0.4 = 0.7
    assert abs(res_scalp.families["f1"].score - 0.7) < 1e-9
    # SWING: 'scalp_only' filtrert. always-vekt 0.6 renormalisert til 1.0.
    # family_score = 0.5 * 1.0 = 0.5
    assert abs(res_swing.families["f1"].score - 0.5) < 1e-9


def test_empty_family_after_filter_scores_zero() -> None:
    """Familie med kun ScalpOnly-drivere på MAKRO → 0.0, ingen kjøring."""
    calls: list[str] = []

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        calls.append("scalp_only")
        return 1.0

    rules = FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "MAKRO": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
        },
        families={
            "f1": FinancialFamilySpec(
                drivers=[
                    DriverSpec(name="scalp_only", weight=1.0, horizons=["SCALP"]),
                ]
            )
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.85, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.70, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.50, min_families=1),
        ),
    )

    res = Engine().score("X", store=object(), rules=rules, horizon="MAKRO")
    assert res.families["f1"].score == 0.0
    assert res.families["f1"].drivers == []
    assert "scalp_only" not in calls


def test_agri_no_horizon_no_filter() -> None:
    """Agri kaller score uten horizon — ingen filter, alle drivere kjører
    selv om de har horizons-felt satt.
    """
    calls: list[str] = []

    @drivers.register("scalp_only")
    def _scalp(store: object, instrument: str, params: dict) -> float:
        calls.append("scalp_only")
        return 0.5

    rules = AgriRules(
        aggregation="additive_sum",
        max_score=1.0,
        families={
            "f1": AgriFamilySpec(
                weight=1.0,
                drivers=[
                    DriverSpec(name="scalp_only", weight=1.0, horizons=["SCALP"]),
                ],
            )
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=0.85, min_families_active=1),
            a=AgriGradeThreshold(min_score=0.70, min_families_active=1),
            b=AgriGradeThreshold(min_score=0.50, min_families_active=1),
        ),
    )

    Engine().score("Corn", store=object(), rules=rules)
    assert "scalp_only" in calls


def test_no_horizons_field_unchanged_behavior() -> None:
    """DriverSpec uten `horizons`-felt skal være bit-identisk med pre-Fase-3.

    Setup: 1 driver uten horizons-felt, 3 horisont-kall. Hver kall skal kjøre
    driveren én gang og gi samme score.
    """

    @drivers.register("always")
    def _always(store: object, instrument: str, params: dict) -> float:
        return 0.42

    rules = FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SCALP": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "SWING": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "MAKRO": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
        },
        families={"f1": FinancialFamilySpec(drivers=[DriverSpec(name="always", weight=1.0)])},
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.85, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.70, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.50, min_families=1),
        ),
    )

    eng = Engine()
    for h in ("SCALP", "SWING", "MAKRO"):
        res = eng.score("X", store=object(), rules=rules, horizon=h)
        assert abs(res.families["f1"].score - 0.42) < 1e-9
