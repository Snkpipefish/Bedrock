"""Tester for audit-runde 5 sub-fase 12.6 fix-spec Steg 1 — `_now`-propagering.

Verifiserer at:

A. Engine sender ``_now``-key til driver-params som ISO-streng når caller
   sender ``now=...`` til ``Engine.score(...)``. Bug-en som dette fixer:
   ``event_distance``-driveren leste ``params["_now"]`` men engine
   propagerte aldri verdien — driveren falt tilbake til wallclock og
   fikk samme value 1.0 (empty_score) for alle 3153 backtest-ref-dates.

B. Når caller IKKE sender ``now``, settes ``_now=None`` slik at driver
   wallclock-fallback (``risk.py:201-205``) fortsatt fungerer for
   tester og live-mode.

Mønsteret følger ``test_engine_horizon_propagation.py`` (ADR-010).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest

from bedrock.engine import drivers
from bedrock.engine.engine import (
    DriverSpec,
    Engine,
    FinancialFamilySpec,
    FinancialRules,
    HorizonSpec,
)
from bedrock.engine.grade import GradeThreshold, GradeThresholds


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Ringfence registry-mutasjoner per test."""
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


def _financial_rules() -> FinancialRules:
    return FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(family_weights={"f1": 1.0}, max_score=1.0),
        },
        families={"f1": FinancialFamilySpec(drivers=[DriverSpec(name="probe_now", weight=1.0)])},
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.85, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.70, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.50, min_families=1),
        ),
    )


def test_now_propagated_to_driver_params() -> None:
    """Engine.score(now=...) skal sette params['_now'] = now.isoformat()."""
    seen: dict[str, object] = {}

    @drivers.register("probe_now")
    def _probe(store: object, instrument: str, params: dict) -> float:
        seen["_now"] = params.get("_now", "missing-key")
        return 0.5

    rules = _financial_rules()
    fixed = datetime(2010, 2, 12, 0, 0, 0, tzinfo=timezone.utc)
    Engine().score("Gold", store=object(), rules=rules, horizon="SWING", now=fixed)

    assert seen["_now"] == fixed.isoformat()


def test_no_now_falls_back_to_wallclock() -> None:
    """Når Engine.score kalles uten now, skal params['_now'] være None.

    Driver-laget faller da tilbake til ``datetime.now(timezone.utc)``
    (``risk.py:201-205``). Vi verifiserer her at engine ikke setter
    en falsk verdi som ville bryte fallback-logikken.
    """
    seen: dict[str, object] = {"_now": "sentinel"}

    @drivers.register("probe_now")
    def _probe(store: object, instrument: str, params: dict) -> float:
        seen["_now"] = params.get("_now", "missing-key")
        return 0.5

    rules = _financial_rules()
    Engine().score("Gold", store=object(), rules=rules, horizon="SWING")

    assert seen["_now"] is None
