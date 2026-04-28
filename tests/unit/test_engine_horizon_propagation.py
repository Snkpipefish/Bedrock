"""Tester for ADR-010 (sub-fase 12.7 R1) — horisont-propagering.

Verifiserer at:

A. Engine setter ``_horizon`` korrekt i driver-params:
   - For FinancialRules: streng (``"SCALP"``/``"SWING"``/``"MAKRO"``)
     matchende horizon-arg.
   - For AgriRules: ``None``.

B. Eksisterende driver er bit-identisk uavhengig av om ``_horizon``
   er satt eller ikke. Dette er den faktiske bakoverkompatibilitet-
   garantien for R1: drivere som ignorerer ``_horizon``-key-en gir
   samme score som før engine-patchen.

Mønsteret følger ``test_engine_direction_polarity.py`` (ADR-006).
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
from bedrock.setups.generator import Direction


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Ringfence registry-mutasjoner per test."""
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _financial_rules() -> FinancialRules:
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SCALP": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "SWING": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
            "MAKRO": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
        },
        families={
            "f1": FinancialFamilySpec(drivers=[DriverSpec(name="probe_horizon", weight=1.0)])
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.85, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.70, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.50, min_families=1),
        ),
    )


def _agri_rules() -> AgriRules:
    return AgriRules(
        aggregation="additive_sum",
        max_score=1.0,
        families={
            "f1": AgriFamilySpec(
                weight=1.0,
                drivers=[DriverSpec(name="probe_horizon", weight=1.0)],
            )
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=0.85, min_families_active=1),
            a=AgriGradeThreshold(min_score=0.70, min_families_active=1),
            b=AgriGradeThreshold(min_score=0.50, min_families_active=1),
        ),
    )


# ---------------------------------------------------------------------------
# Test A — Engine setter `_horizon` korrekt
# ---------------------------------------------------------------------------


def test_engine_propagates_horizon_string_for_financial() -> None:
    """For FinancialRules skal driver se `_horizon` = horizon-arg-strengen."""
    seen: dict[str, object] = {}

    @drivers.register("probe_horizon")
    def _probe(store: object, instrument: str, params: dict) -> float:
        seen["_horizon"] = params.get("_horizon")
        return 0.5

    rules = _financial_rules()
    Engine().score("Gold", store=object(), rules=rules, horizon="SWING")

    assert seen["_horizon"] == "SWING"


def test_engine_propagates_horizon_for_each_horizon_value() -> None:
    """Verifiser alle tre horisont-strenger propageres riktig."""
    seen: list[object] = []

    @drivers.register("probe_horizon")
    def _probe(store: object, instrument: str, params: dict) -> float:
        seen.append(params.get("_horizon"))
        return 0.5

    rules = _financial_rules()
    eng = Engine()
    for h in ("SCALP", "SWING", "MAKRO"):
        eng.score("Gold", store=object(), rules=rules, horizon=h)

    assert seen == ["SCALP", "SWING", "MAKRO"]


def test_engine_propagates_none_horizon_for_agri() -> None:
    """For AgriRules skal driver se `_horizon` = None."""
    seen: dict[str, object] = {"_horizon": "sentinel"}

    @drivers.register("probe_horizon")
    def _probe(store: object, instrument: str, params: dict) -> float:
        seen["_horizon"] = params.get("_horizon", "missing-key")
        return 0.5

    rules = _agri_rules()
    Engine().score("Corn", store=object(), rules=rules)

    assert seen["_horizon"] is None


# ---------------------------------------------------------------------------
# Test B — Bakoverkompatibilitet (eksisterende driver er bit-identisk)
# ---------------------------------------------------------------------------


def test_horizon_unaware_driver_is_bit_identical() -> None:
    """En driver som ignorerer `_horizon`-key skal gi nøyaktig samme score
    uansett hvilken horisont engine propagerer. Dette er score-uendret-
    garantien (PLAN § 19.1) i sin minste form.
    """

    @drivers.register("probe_horizon")
    def _probe(store: object, instrument: str, params: dict) -> float:
        # Driver ser ikke på _horizon. Returnerer en konstant.
        return 0.4242

    rules = _financial_rules()
    eng = Engine()
    scores = [
        eng.score("Gold", store=object(), rules=rules, horizon=h).score
        for h in ("SCALP", "SWING", "MAKRO")
    ]

    # Tre identiske scores; ingen drift fra horizon-arg fordi driveren
    # ikke leser _horizon.
    assert scores[0] == scores[1] == scores[2] == pytest.approx(0.4242)


def test_horizon_unaware_driver_with_buy_and_sell() -> None:
    """Bit-identitet skal også holde i kombinasjon med direction=SELL.
    Med polarity=directional flippes scoren til 1-value, men det er
    direction-flip — uavhengig av `_horizon`. Verifiser at horisont-
    varianten ikke introduserer drift."""

    @drivers.register("probe_horizon")
    def _probe(store: object, instrument: str, params: dict) -> float:
        return 0.3

    rules = _financial_rules()
    eng = Engine()
    buy_scores = [
        eng.score("Gold", object(), rules, horizon=h, direction=Direction.BUY).score
        for h in ("SCALP", "SWING", "MAKRO")
    ]
    sell_scores = [
        eng.score("Gold", object(), rules, horizon=h, direction=Direction.SELL).score
        for h in ("SCALP", "SWING", "MAKRO")
    ]

    assert buy_scores[0] == buy_scores[1] == buy_scores[2] == pytest.approx(0.3)
    # SELL flipper: 1 - 0.3 = 0.7 (familien er default polarity=directional)
    assert sell_scores[0] == sell_scores[1] == sell_scores[2] == pytest.approx(0.7)
