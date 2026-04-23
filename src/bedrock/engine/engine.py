"""Engine — hovedklasse for scoring.

Kontrakt (forenklet):

    result = Engine().score(instrument, store, rules, horizon)

Engine slår opp aggregator ut fra `rules.aggregation`, kjører hver driver i
`rules.families` via `drivers`-registry, aggregerer, og returnerer en
`GroupResult` med full explain-trace.

I Fase 1 session 2 er kun `weighted_horizon` implementert; `additive_sum`
kaster `NotImplementedError`. Driver-kall bruker en minimal `store`-parameter
(typet `Any` inntil `DataStore` fra Fase 2 lander).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bedrock.engine import aggregators, drivers, grade

# ---------------------------------------------------------------------------
# Pydantic-modeller for YAML-reglene
# ---------------------------------------------------------------------------

Aggregation = Literal["weighted_horizon", "additive_sum"]


class DriverSpec(BaseModel):
    """YAML: `{name: sma200_align, weight: 0.4, params: {tf: D1}}`."""

    name: str
    weight: float
    params: dict[str, Any] = Field(default_factory=dict)


class FamilySpec(BaseModel):
    """YAML: en familie har en liste drivere."""

    drivers: list[DriverSpec]


class HorizonSpec(BaseModel):
    """YAML: en horisont har familie-vekter + score-cap + publish-gulv."""

    family_weights: dict[str, float]
    max_score: float = Field(gt=0.0)
    min_score_publish: float = Field(ge=0.0)


class Rules(BaseModel):
    """Full regel-set for ett instrument. Parset fra YAML.

    Fase 1-utgave — utvides i senere faser med `gates`, `inherits`,
    instrument-metadata, og agri-spesifikke felter.
    """

    aggregation: Aggregation
    horizons: dict[str, HorizonSpec] = Field(default_factory=dict)
    families: dict[str, FamilySpec]
    grade_thresholds: grade.GradeThresholds

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Pydantic-modeller for resultat / explain-trace
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
    """Full scoring-output for ett instrument + horisont.

    Denne modellen er API-et som setup-generator + signal-builder +
    explain-CLI + UI leser. Holdes stabil på tvers av faser.
    """

    instrument: str
    horizon: str
    aggregation: Aggregation
    score: float
    grade: str
    max_score: float
    active_families: int
    families: dict[str, FamilyResult]
    gates_triggered: list[str] = Field(default_factory=list)


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
        horizon: str,
    ) -> GroupResult:
        """Scorer `instrument` for en gitt `horizon` med gitte `rules`.

        `store` er typet `Any` i Fase 1 — formaliseres til `DataStore` i
        Fase 2. Alle drivere mottar samme `store`-objekt og plukker det de
        trenger.
        """
        if rules.aggregation == "additive_sum":
            # Kommer i neste session. Kastes eksplisitt for å unngå stille feil.
            raise NotImplementedError(
                "Aggregator 'additive_sum' is not implemented yet. "
                "Expected in next Fase 1 session (agri-support)."
            )

        horizon_spec = rules.horizons.get(horizon)
        if horizon_spec is None:
            known = ", ".join(sorted(rules.horizons)) or "<none>"
            raise KeyError(f"Horizon '{horizon}' not defined in rules. Known: {known}")

        # Kjør alle familier + drivere -> scores + per-driver-trace.
        family_results, family_scores = self._score_families(store, instrument, rules.families)

        # Kombiner familie-scores -> total via aggregator.
        total_score = aggregators.weighted_horizon(family_scores, horizon_spec.family_weights)

        # Tell aktive familier (score > 0) for grade-kravet.
        active_families = sum(1 for s in family_scores.values() if s > 0.0)

        g = grade.grade_financial(
            total_score=total_score,
            max_score=horizon_spec.max_score,
            active_families=active_families,
            thresholds=rules.grade_thresholds,
        )

        return GroupResult(
            instrument=instrument,
            horizon=horizon,
            aggregation=rules.aggregation,
            score=total_score,
            grade=g,
            max_score=horizon_spec.max_score,
            active_families=active_families,
            families=family_results,
        )

    @staticmethod
    def _score_families(
        store: Any,
        instrument: str,
        families: dict[str, FamilySpec],
    ) -> tuple[dict[str, FamilyResult], dict[str, float]]:
        """Kjør alle drivere per familie og returner (per-familie-trace, scores)."""
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
