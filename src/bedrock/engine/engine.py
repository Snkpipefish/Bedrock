# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""Engine — hovedklasse for scoring.

Kontrakt:

    result = Engine().score(instrument, store, rules, horizon=...)

Engine slår opp aggregator ut fra `rules.aggregation`-typen, kjører hver
driver i `rules.families` via `drivers`-registry, aggregerer, og returnerer
en `GroupResult` med full explain-trace.

Reglene kommer i to former:

- `FinancialRules` (aggregation="weighted_horizon"): har `horizons`-blokk,
  score er horisont-avhengig. `horizon`-argumentet er påkrevd.
- `AgriRules` (aggregation="additive_sum"): har `max_score` på toppnivå og
  familie-`weight` som absolutt cap. Ingen horisont — den bestemmes i
  Fase 4 (setup-generator) basert på setup-karakteristikk.

`Rules` er en TypeAlias for unionen, slik at funksjoner som ikke bryr seg
om varianten kan ta `Rules` direkte.

`store` er typet `Any` i Fase 1 — formaliseres til `DataStore` i Fase 2.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from bedrock.engine import aggregators, drivers, grade
from bedrock.engine.gates import (
    GateContext,
    GateSpec,
    apply_gates,
    cap_grade,
)

# ---------------------------------------------------------------------------
# Felles modeller
# ---------------------------------------------------------------------------

Aggregation = Literal["weighted_horizon", "additive_sum"]


class DriverSpec(BaseModel):
    """YAML: `{name: sma200_align, weight: 0.4, params: {tf: D1}}`."""

    name: str
    weight: float
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Financial-modeller (weighted_horizon)
# ---------------------------------------------------------------------------


class FinancialFamilySpec(BaseModel):
    """Familie-spesifikasjon for financial. Vekt kommer fra horisonten."""

    drivers: list[DriverSpec]


class HorizonSpec(BaseModel):
    """En horisonts familie-vekter + score-cap + publish-gulv."""

    family_weights: dict[str, float]
    max_score: float = Field(gt=0.0)
    min_score_publish: float = Field(ge=0.0)


class FinancialRules(BaseModel):
    """Regelsett for et financial-instrument (Gold, EURUSD, Brent ...).

    YAML-eksempel: se PLAN § 4.2 (Gold).
    """

    aggregation: Literal["weighted_horizon"]
    horizons: dict[str, HorizonSpec]
    families: dict[str, FinancialFamilySpec]
    grade_thresholds: grade.GradeThresholds
    gates: list[GateSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Agri-modeller (additive_sum)
# ---------------------------------------------------------------------------


class AgriFamilySpec(BaseModel):
    """Familie-spesifikasjon for agri. `weight` er familiens absolutte cap."""

    weight: float = Field(gt=0.0)
    drivers: list[DriverSpec]


class AgriRules(BaseModel):
    """Regelsett for et agri-instrument (Corn, Coffee, Sugar ...).

    YAML-eksempel: se PLAN § 4.3 (Corn).

    Ingen `horizons` — horisont tildeles av setup-generator i Fase 4.
    """

    aggregation: Literal["additive_sum"]
    max_score: float = Field(gt=0.0)
    min_score_publish: float = Field(ge=0.0)
    families: dict[str, AgriFamilySpec]
    grade_thresholds: grade.AgriGradeThresholds
    gates: list[GateSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# Felles type-alias. Konkrete konstruktører er `FinancialRules` / `AgriRules`.
Rules: TypeAlias = FinancialRules | AgriRules


# ---------------------------------------------------------------------------
# Resultat / explain-trace
# ---------------------------------------------------------------------------


class DriverResult(BaseModel):
    """En drivers bidrag til familie-score."""

    name: str
    value: float
    weight: float
    contribution: float


class FamilyResult(BaseModel):
    """En families aggregerte score + driver-trace."""

    name: str
    score: float
    drivers: list[DriverResult]


class GroupResult(BaseModel):
    """Full scoring-output for ett instrument.

    `horizon` er None for agri-resultat (horisonten kommer fra setup-generator).
    """

    instrument: str
    horizon: str | None = None
    aggregation: Aggregation
    score: float
    grade: str
    max_score: float
    active_families: int
    families: dict[str, FamilyResult]
    gates_triggered: list[str] = Field(default_factory=list)


# Intern type for "noen FamilySpec" (financial eller agri — begge har `drivers`).
_AnyFamilySpec = FinancialFamilySpec | AgriFamilySpec


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Engine:
    """Orkestrerer scoring: families -> drivere -> aggregator -> grade."""

    def score(
        self,
        instrument: str,
        store: Any,
        rules: Rules,
        horizon: str | None = None,
    ) -> GroupResult:
        """Scorer `instrument` mot `rules`.

        For `FinancialRules` må `horizon` oppgis. For `AgriRules` ignoreres
        `horizon` (agri har ikke horisont-splitt på scoring-siden — det
        bestemmes senere av setup-generator).
        """
        if isinstance(rules, FinancialRules):
            return self._score_financial(instrument, store, rules, horizon)
        if isinstance(rules, AgriRules):
            return self._score_agri(instrument, store, rules)
        raise TypeError(f"Unknown rules type: {type(rules).__name__}")

    # -- financial ----------------------------------------------------------

    def _score_financial(
        self,
        instrument: str,
        store: Any,
        rules: FinancialRules,
        horizon: str | None,
    ) -> GroupResult:
        if horizon is None:
            raise ValueError("FinancialRules require a `horizon` argument (e.g. 'SWING').")

        horizon_spec = rules.horizons.get(horizon)
        if horizon_spec is None:
            known = ", ".join(sorted(rules.horizons)) or "<none>"
            raise KeyError(f"Horizon '{horizon}' not defined in rules. Known: {known}")

        family_results, family_scores = self._score_families(store, instrument, rules.families)

        total_score = aggregators.weighted_horizon(family_scores, horizon_spec.family_weights)
        active_families = self._count_active(family_scores)
        g = grade.grade_financial(
            total_score=total_score,
            max_score=horizon_spec.max_score,
            active_families=active_families,
            thresholds=rules.grade_thresholds,
        )

        ctx = GateContext(
            instrument=instrument,
            score=total_score,
            max_score=horizon_spec.max_score,
            active_families=active_families,
            family_scores=dict(family_scores),
        )
        cap, triggered = apply_gates(rules.gates, ctx)
        g = cap_grade(g, cap)

        return GroupResult(
            instrument=instrument,
            horizon=horizon,
            aggregation=rules.aggregation,
            score=total_score,
            grade=g,
            max_score=horizon_spec.max_score,
            active_families=active_families,
            families=family_results,
            gates_triggered=triggered,
        )

    # -- agri ---------------------------------------------------------------

    def _score_agri(
        self,
        instrument: str,
        store: Any,
        rules: AgriRules,
    ) -> GroupResult:
        family_results, family_scores = self._score_families(store, instrument, rules.families)

        family_caps = {name: spec.weight for name, spec in rules.families.items()}
        total_score = aggregators.additive_sum(family_scores, family_caps)
        active_families = self._count_active(family_scores)
        g = grade.grade_agri(
            total_score=total_score,
            active_families=active_families,
            thresholds=rules.grade_thresholds,
        )

        ctx = GateContext(
            instrument=instrument,
            score=total_score,
            max_score=rules.max_score,
            active_families=active_families,
            family_scores=dict(family_scores),
        )
        cap, triggered = apply_gates(rules.gates, ctx)
        g = cap_grade(g, cap)

        return GroupResult(
            instrument=instrument,
            horizon=None,
            aggregation=rules.aggregation,
            score=total_score,
            grade=g,
            max_score=rules.max_score,
            active_families=active_families,
            families=family_results,
            gates_triggered=triggered,
        )

    # -- felles -------------------------------------------------------------

    @staticmethod
    def _score_families(
        store: Any,
        instrument: str,
        families: dict[str, _AnyFamilySpec],
    ) -> tuple[dict[str, FamilyResult], dict[str, float]]:
        """Kjør alle drivere per familie. Felles for financial og agri.

        Begge FamilySpec-klasser har attributtet `.drivers: list[DriverSpec]`.
        """
        family_results: dict[str, FamilyResult] = {}
        family_scores: dict[str, float] = {}

        for family_name, family_spec in families.items():
            driver_results: list[DriverResult] = []
            family_score = 0.0

            for driver_spec in family_spec.drivers:
                fn = drivers.get(driver_spec.name)
                value = fn(store, instrument, driver_spec.params)
                contribution = value * driver_spec.weight
                driver_results.append(
                    DriverResult(
                        name=driver_spec.name,
                        value=value,
                        weight=driver_spec.weight,
                        contribution=contribution,
                    )
                )
                family_score += contribution

            family_results[family_name] = FamilyResult(
                name=family_name,
                score=family_score,
                drivers=driver_results,
            )
            family_scores[family_name] = family_score

        return family_results, family_scores

    @staticmethod
    def _count_active(family_scores: dict[str, float]) -> int:
        """Antall familier med score > 0."""
        return sum(1 for s in family_scores.values() if s > 0.0)
