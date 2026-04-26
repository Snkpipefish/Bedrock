"""Tester for asymmetrisk publish-floor (session 101).

Etter direction-aware scoring (session 95b/100) er instrumenter med
strukturell direction-bias (SP500, Nasdaq, Gold) i stand til å ha
ulik publish-floor for BUY vs SELL. YAML-format:

    min_score_publish:
        buy: 3.0
        sell: 4.5

Eldre format (felles float) er fortsatt støttet:

    min_score_publish: 3.5
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bedrock.engine import drivers
from bedrock.engine.engine import (
    AgriFamilySpec,
    AgriRules,
    DriverSpec,
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


# ---------------------------------------------------------------------------
# HorizonSpec.get_publish_floor
# ---------------------------------------------------------------------------


def test_horizon_spec_float_form_is_symmetric() -> None:
    """Eldre float-form gir samme floor for begge retninger."""
    spec = HorizonSpec(
        family_weights={"a": 1.0},
        max_score=5.0,
        min_score_publish=2.5,
    )
    assert spec.get_publish_floor("buy") == 2.5
    assert spec.get_publish_floor("sell") == 2.5
    assert spec.get_publish_floor("BUY") == 2.5  # case-insensitive


def test_horizon_spec_dict_form_per_direction() -> None:
    """Dict-form med buy/sell-keys gir per-direction-floor."""
    spec = HorizonSpec(
        family_weights={"a": 1.0},
        max_score=5.0,
        min_score_publish={"buy": 3.0, "sell": 4.5},
    )
    assert spec.get_publish_floor("buy") == 3.0
    assert spec.get_publish_floor("sell") == 4.5
    # Case-insensitive lookup
    assert spec.get_publish_floor("BUY") == 3.0
    assert spec.get_publish_floor("Sell") == 4.5


def test_horizon_spec_dict_unknown_direction_returns_strictest() -> None:
    """Ukjent retning faller tilbake til strengeste floor (defensiv)."""
    spec = HorizonSpec(
        family_weights={"a": 1.0},
        max_score=5.0,
        min_score_publish={"buy": 2.0, "sell": 4.0},
    )
    assert spec.get_publish_floor("unknown") == 4.0  # max av (2.0, 4.0)


def test_horizon_spec_dict_partial_only_buy() -> None:
    """Dict med bare buy-key: SELL faller tilbake til strengeste."""
    spec = HorizonSpec(
        family_weights={"a": 1.0},
        max_score=5.0,
        min_score_publish={"buy": 2.0},
    )
    assert spec.get_publish_floor("buy") == 2.0
    assert spec.get_publish_floor("sell") == 2.0  # max av kun-buy


def test_horizon_spec_default_zero_when_omitted() -> None:
    """Default min_score_publish=0.0 når ikke spesifisert."""
    spec = HorizonSpec(family_weights={"a": 1.0}, max_score=5.0)
    assert spec.get_publish_floor("buy") == 0.0
    assert spec.get_publish_floor("sell") == 0.0


# ---------------------------------------------------------------------------
# Integrasjon: Financial-rules respekterer asymmetrisk floor
# ---------------------------------------------------------------------------


def _make_rules(min_score_publish: float | dict[str, float]) -> FinancialRules:
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(
                family_weights={"trend": 1.0},
                max_score=5.0,
                min_score_publish=min_score_publish,
            ),
        },
        families={
            "trend": FinancialFamilySpec(
                drivers=[DriverSpec(name="mock_full", weight=1.0)],
                polarity="neutral",  # Ikke flip — driver returnerer fast verdi
            ),
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.55, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.35, min_families=1),
        ),
    )


def test_financial_rules_load_dict_form() -> None:
    """Pydantic skal akseptere dict-form for min_score_publish."""
    rules = _make_rules({"buy": 1.5, "sell": 3.0})
    spec = rules.horizons["SWING"]
    assert isinstance(spec.min_score_publish, dict)
    assert spec.get_publish_floor("buy") == 1.5
    assert spec.get_publish_floor("sell") == 3.0


def test_financial_rules_load_float_form() -> None:
    """Float-form fortsatt aksepteres (bakoverkompatibilitet)."""
    rules = _make_rules(2.0)
    spec = rules.horizons["SWING"]
    assert spec.min_score_publish == 2.0
    assert spec.get_publish_floor("buy") == 2.0
    assert spec.get_publish_floor("sell") == 2.0


# ---------------------------------------------------------------------------
# Agri-rules
# ---------------------------------------------------------------------------


def test_agri_rules_accept_dict_form() -> None:
    """AgriRules.min_score_publish skal støtte dict-form."""
    rules = AgriRules(
        aggregation="additive_sum",
        max_score=10.0,
        min_score_publish={"buy": 4.0, "sell": 6.0},
        families={
            "weather": AgriFamilySpec(
                weight=2.0,
                drivers=[DriverSpec(name="mock_full", weight=1.0)],
            ),
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=8.0, min_families_active=1),
            a=AgriGradeThreshold(min_score=6.0, min_families_active=1),
            b=AgriGradeThreshold(min_score=4.0, min_families_active=1),
        ),
    )
    assert isinstance(rules.min_score_publish, dict)
    assert rules.min_score_publish["buy"] == 4.0
    assert rules.min_score_publish["sell"] == 6.0


def test_agri_rules_inverted_asymmetry_for_sell_bias() -> None:
    """Sugar-mønster: SELL-bias instrument får BUY-floor høyere enn SELL.

    Bekrefter at `_get_min_score_publish` slår opp riktig retning når
    asymmetrien er invertert (SELL ≤ BUY istedenfor BUY ≤ SELL).
    """
    from bedrock.config.instruments import InstrumentConfig, InstrumentMetadata
    from bedrock.orchestrator.signals import _get_min_score_publish
    from bedrock.setups.generator import Horizon

    rules = AgriRules(
        aggregation="additive_sum",
        max_score=16.0,
        min_score_publish={"buy": 7.0, "sell": 5.0},  # invertert
        families={
            "weather": AgriFamilySpec(
                weight=2.0,
                drivers=[DriverSpec(name="mock_full", weight=1.0)],
            ),
        },
        grade_thresholds=AgriGradeThresholds(
            a_plus=AgriGradeThreshold(min_score=12.0, min_families_active=1),
            a=AgriGradeThreshold(min_score=10.0, min_families_active=1),
            b=AgriGradeThreshold(min_score=6.0, min_families_active=1),
        ),
    )
    cfg = InstrumentConfig(
        instrument=InstrumentMetadata(
            id="SugarTest",
            asset_class="softs",
            ticker="SB",
        ),
        rules=rules,
    )
    # Agri har ingen horizon-skille — samme floor for SCALP/SWING/MAKRO
    for horizon in (Horizon.SCALP, Horizon.SWING, Horizon.MAKRO):
        assert _get_min_score_publish(cfg, horizon, Direction.BUY) == 7.0
        assert _get_min_score_publish(cfg, horizon, Direction.SELL) == 5.0


# ---------------------------------------------------------------------------
# End-to-end: published-flag respekterer asymmetrisk floor
# ---------------------------------------------------------------------------


def test_get_min_score_publish_uses_direction_specific_floor() -> None:
    """`_get_min_score_publish` skal slå opp per direction når dict-form."""
    from bedrock.config.instruments import InstrumentConfig, InstrumentMetadata
    from bedrock.orchestrator.signals import _get_min_score_publish
    from bedrock.setups.generator import Horizon

    rules = _make_rules({"buy": 1.5, "sell": 2.5})
    cfg = InstrumentConfig(
        instrument=InstrumentMetadata(
            id="TestInst",
            asset_class="metals",
            ticker="XYZ",
        ),
        rules=rules,
    )

    buy_floor = _get_min_score_publish(cfg, Horizon.SWING, Direction.BUY)
    sell_floor = _get_min_score_publish(cfg, Horizon.SWING, Direction.SELL)
    assert buy_floor == 1.5
    assert sell_floor == 2.5


def test_get_min_score_publish_float_form_returns_same_for_both() -> None:
    """Float-form: BUY og SELL får samme floor."""
    from bedrock.config.instruments import InstrumentConfig, InstrumentMetadata
    from bedrock.orchestrator.signals import _get_min_score_publish
    from bedrock.setups.generator import Horizon

    rules = _make_rules(2.0)
    cfg = InstrumentConfig(
        instrument=InstrumentMetadata(
            id="TestInst",
            asset_class="metals",
            ticker="XYZ",
        ),
        rules=rules,
    )

    assert _get_min_score_publish(cfg, Horizon.SWING, Direction.BUY) == 2.0
    assert _get_min_score_publish(cfg, Horizon.SWING, Direction.SELL) == 2.0
