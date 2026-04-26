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
from bedrock.setups.generator import Direction

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


FamilyPolarity = Literal["directional", "neutral"]


class FinancialFamilySpec(BaseModel):
    """Familie-spesifikasjon for financial. Vekt kommer fra horisonten.

    `polarity` styrer direction-asymmetri (ADR-006 session 95b):
    - ``directional`` (default): drivere returnerer "bull-of-instrument-
      confidence". For ``direction=SELL`` flippes hver drivers value til
      ``1 - value`` og familie-scoren reaggregreres.
    - ``neutral``: familien er kontekst (eks. vol_regime som er trend-
      friendly begge retninger). Score er identisk for BUY og SELL.
    """

    drivers: list[DriverSpec]
    polarity: FamilyPolarity = "directional"


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
    """Familie-spesifikasjon for agri. `weight` er familiens absolutte cap.

    `polarity` styrer direction-asymmetri (ADR-006 session 95b) — se
    ``FinancialFamilySpec.polarity`` for semantikk.
    """

    weight: float = Field(gt=0.0)
    drivers: list[DriverSpec]
    polarity: FamilyPolarity = "directional"


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
        direction: Direction = Direction.BUY,
    ) -> GroupResult:
        """Scorer `instrument` mot `rules`.

        For `FinancialRules` må `horizon` oppgis. For `AgriRules` ignoreres
        `horizon` (agri har ikke horisont-splitt på scoring-siden — det
        bestemmes senere av setup-generator).

        `direction` (ADR-006 session 95b): ``BUY`` (default) bruker driver-
        verdier as-is. ``SELL`` flipper hver drivers value til ``1 - value``
        på familier med ``polarity="directional"``; familier med
        ``polarity="neutral"`` er identiske mellom retninger. Default
        BUY bevarer bakoverkompatibilitet med tester som ikke bryr seg
        om retning.
        """
        if isinstance(rules, FinancialRules):
            return self._score_financial(instrument, store, rules, horizon, direction)
        if isinstance(rules, AgriRules):
            return self._score_agri(instrument, store, rules, direction)
        raise TypeError(f"Unknown rules type: {type(rules).__name__}")

    # -- financial ----------------------------------------------------------

    def _score_financial(
        self,
        instrument: str,
        store: Any,
        rules: FinancialRules,
        horizon: str | None,
        direction: Direction,
    ) -> GroupResult:
        if horizon is None:
            raise ValueError("FinancialRules require a `horizon` argument (e.g. 'SWING').")

        horizon_spec = rules.horizons.get(horizon)
        if horizon_spec is None:
            known = ", ".join(sorted(rules.horizons)) or "<none>"
            raise KeyError(f"Horizon '{horizon}' not defined in rules. Known: {known}")

        family_results, family_scores = self._score_families(
            store, instrument, rules.families, direction
        )

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
        direction: Direction,
    ) -> GroupResult:
        family_results, family_scores = self._score_families(
            store, instrument, rules.families, direction
        )

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
        direction: Direction,
    ) -> tuple[dict[str, FamilyResult], dict[str, float]]:
        """Kjør alle drivere per familie. Felles for financial og agri.

        Begge FamilySpec-klasser har attributtet `.drivers: list[DriverSpec]`
        og `.polarity: FamilyPolarity`. For ``direction=SELL`` på familier
        med ``polarity="directional"`` flippes hver drivers ``value`` til
        ``1 - value`` (se ADR-006). ``polarity="neutral"`` er identisk for
        BUY og SELL.
        """
        family_results: dict[str, FamilyResult] = {}
        family_scores: dict[str, float] = {}
        flip = direction == Direction.SELL

        for family_name, family_spec in families.items():
            driver_results: list[DriverResult] = []
            family_score = 0.0
            do_flip = flip and family_spec.polarity == "directional"

            for driver_spec in family_spec.drivers:
                fn = drivers.get(driver_spec.name)
                # Propagér direction via en intern `_direction`-key i en
                # kopi av params. Drivere som er direction-aware (eks.
                # analog_*) leser dette; andre ignorerer det.
                # Session 100: gjør det mulig for analog-driver å invertere
                # forward-return-threshold for SELL istedenfor mekanisk
                # 1-x-flip på engine-siden (se ADR-006 § Spesialtilfeller).
                params_with_dir = {
                    **driver_spec.params,
                    "_direction": direction.value,
                }
                raw_value = fn(store, instrument, params_with_dir)
                value = (1.0 - raw_value) if do_flip else raw_value
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
