"""Tester for ADR-006 (session 95b) — direction-asymmetric scoring.

Verifiserer at:
1. Default oppførsel (uten direction) er bakoverkompatibel: BUY-resultat.
2. `direction=Direction.SELL` flipper drivere på familier med
   ``polarity="directional"``.
3. Familier med ``polarity="neutral"`` har identisk score for BUY og SELL.
4. AgriRules respekterer direction.
5. Default `polarity` på FamilySpec er ``"directional"``.
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
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


@pytest.fixture
def _register_test_drivers() -> None:
    @drivers.register("mock_high")
    def _high(store: object, instrument: str, params: dict) -> float:
        return 0.8

    @drivers.register("mock_mid")
    def _mid(store: object, instrument: str, params: dict) -> float:
        return 0.5


# ---------------------------------------------------------------------------
# Schema-defaults
# ---------------------------------------------------------------------------


def test_financial_family_spec_default_polarity_is_directional() -> None:
    spec = FinancialFamilySpec(drivers=[])
    assert spec.polarity == "directional"


def test_agri_family_spec_default_polarity_is_directional() -> None:
    spec = AgriFamilySpec(weight=1.0, drivers=[])
    assert spec.polarity == "directional"


def test_polarity_field_accepts_neutral() -> None:
    spec = FinancialFamilySpec(drivers=[], polarity="neutral")
    assert spec.polarity == "neutral"


def test_polarity_field_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        FinancialFamilySpec(drivers=[], polarity="invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Engine.score med direction
# ---------------------------------------------------------------------------


def _make_rules(
    polarity_trend: str = "directional",
    polarity_macro: str = "directional",
) -> FinancialRules:
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(
                family_weights={"trend": 1.0, "macro": 1.0},
                max_score=6.0,
                min_score_publish=2.5,
            ),
        },
        families={
            "trend": FinancialFamilySpec(
                drivers=[DriverSpec(name="mock_high", weight=1.0)],
                polarity=polarity_trend,  # type: ignore[arg-type]
            ),
            "macro": FinancialFamilySpec(
                drivers=[DriverSpec(name="mock_mid", weight=1.0)],
                polarity=polarity_macro,  # type: ignore[arg-type]
            ),
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=2),
            a=GradeThreshold(min_pct_of_max=0.55, min_families=2),
            b=GradeThreshold(min_pct_of_max=0.35, min_families=1),
        ),
    )


def test_default_direction_is_buy_backwards_compat(_register_test_drivers: None) -> None:
    """Engine.score() uten direction-arg skal oppføre seg som BUY."""
    rules = _make_rules()
    no_arg = Engine().score("X", store=None, rules=rules, horizon="SWING")
    explicit_buy = Engine().score(
        "X", store=None, rules=rules, horizon="SWING", direction=Direction.BUY
    )
    assert no_arg.score == pytest.approx(explicit_buy.score)
    assert no_arg.families["trend"].drivers[0].value == pytest.approx(0.8)


def test_sell_flips_directional_family(_register_test_drivers: None) -> None:
    """SELL skal invertere driver-verdien på directional-familier."""
    rules = _make_rules()
    buy = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.BUY)
    sell = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.SELL)
    # mock_high returnerer 0.8 → BUY value 0.8, SELL value 0.2
    assert buy.families["trend"].drivers[0].value == pytest.approx(0.8)
    assert sell.families["trend"].drivers[0].value == pytest.approx(0.2)
    # mock_mid returnerer 0.5 → flip gir 0.5 (samme verdi men logisk flippet)
    assert buy.families["macro"].drivers[0].value == pytest.approx(0.5)
    assert sell.families["macro"].drivers[0].value == pytest.approx(0.5)
    # Aggregert: BUY 1.3 vs SELL 0.7
    assert buy.score == pytest.approx(1.3)
    assert sell.score == pytest.approx(0.7)


def test_neutral_family_unchanged_for_sell(_register_test_drivers: None) -> None:
    """Familier med polarity=neutral skal være identiske for BUY og SELL."""
    rules = _make_rules(polarity_trend="neutral", polarity_macro="neutral")
    buy = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.BUY)
    sell = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.SELL)
    assert buy.score == pytest.approx(sell.score)
    assert buy.families["trend"].drivers[0].value == pytest.approx(0.8)
    assert sell.families["trend"].drivers[0].value == pytest.approx(0.8)


def test_mixed_polarity(_register_test_drivers: None) -> None:
    """Mix av directional + neutral: kun directional flippes."""
    rules = _make_rules(polarity_trend="directional", polarity_macro="neutral")
    buy = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.BUY)
    sell = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.SELL)
    # trend flipper (0.8 → 0.2), macro uendret (0.5)
    assert sell.families["trend"].drivers[0].value == pytest.approx(0.2)
    assert sell.families["macro"].drivers[0].value == pytest.approx(0.5)
    # BUY: 0.8 + 0.5 = 1.3 ; SELL: 0.2 + 0.5 = 0.7
    assert buy.score == pytest.approx(1.3)
    assert sell.score == pytest.approx(0.7)


def test_contribution_recomputed_after_flip(_register_test_drivers: None) -> None:
    """`contribution` må reflektere den flippede verdien × weight."""
    rules = _make_rules()
    sell = Engine().score("X", store=None, rules=rules, horizon="SWING", direction=Direction.SELL)
    trend_drv = sell.families["trend"].drivers[0]
    assert trend_drv.value == pytest.approx(0.2)
    assert trend_drv.contribution == pytest.approx(0.2 * 1.0)


def test_agri_rules_respect_direction(_register_test_drivers: None) -> None:
    """AgriRules må også flippe drivere ved SELL på directional-familier."""
    rules = AgriRules(
        aggregation="additive_sum",
        max_score=4.0,
        min_score_publish=1.5,
        families={
            "weather": AgriFamilySpec(
                weight=2.0,
                drivers=[DriverSpec(name="mock_high", weight=1.0)],
                polarity="directional",
            ),
            "context": AgriFamilySpec(
                weight=2.0,
                drivers=[DriverSpec(name="mock_mid", weight=1.0)],
                polarity="neutral",
            ),
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=2.5, min_families_active=2),
            a=AgriGradeThreshold(min_score=1.5, min_families_active=2),
            b=AgriGradeThreshold(min_score=0.5, min_families_active=1),
        ),
    )
    buy = Engine().score("Corn", store=None, rules=rules, direction=Direction.BUY)
    sell = Engine().score("Corn", store=None, rules=rules, direction=Direction.SELL)
    # weather: driver 0.8 BUY, 0.2 SELL ; context: 0.5 begge
    assert buy.families["weather"].drivers[0].value == pytest.approx(0.8)
    assert sell.families["weather"].drivers[0].value == pytest.approx(0.2)
    assert buy.families["context"].drivers[0].value == pytest.approx(0.5)
    assert sell.families["context"].drivers[0].value == pytest.approx(0.5)
    # additive_sum multipliserer family_score med family_cap (=spec.weight=2.0).
    # BUY  weather=0.8*2.0 + context=0.5*2.0 = 1.6 + 1.0 = 2.6
    # SELL weather=0.2*2.0 + context=0.5*2.0 = 0.4 + 1.0 = 1.4
    assert buy.score == pytest.approx(2.6)
    assert sell.score == pytest.approx(1.4)
