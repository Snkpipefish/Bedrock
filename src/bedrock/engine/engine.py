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

from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    """YAML: `{name: sma200_align, weight: 0.4, params: {tf: D1}}`.

    Sub-fase 12.9 Fase 3 (per § 20.2 horisont-bruk-prinsipper):
    `horizons` lar driveren begrenses til en delmengde av {SCALP, SWING,
    MAKRO}. Eksempel: `event_distance` (calendar_ff KJERNE) er
    SCALP+SWING-spesifikk; `vix_term_ratio` er ren MAKRO-regime;
    `aaii_extreme` er SWING-mean-reversion. None (default) = alle 3
    horisonter, bakoverkompatibelt med eksisterende YAMLer.

    Engine `_score_families` filtrerer drivere etter horisont og re-
    normaliserer gjenværende vekter slik at familie-summen holdes på
    1.0 (financial) / sum-av-spec (agri). Hvis filtrering tømmer
    familien, hopper familien med skip-grunn
    `all_drivers_filtered_for_horizon`.
    """

    name: str
    weight: float
    params: dict[str, Any] = Field(default_factory=dict)
    horizons: list[str] | None = Field(
        default=None,
        description=(
            "Valgfri liste av horisont-navn (SCALP/SWING/MAKRO eller "
            "lowercase). None = driveren bidrar til alle 3 horisonter."
        ),
    )

    @field_validator("horizons")
    @classmethod
    def _validate_horizons(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("horizons kan ikke være tom liste; bruk None for 'alle'")
        valid = {"SCALP", "SWING", "MAKRO"}
        normalized: list[str] = []
        for h in v:
            up = h.upper()
            if up not in valid:
                raise ValueError(f"Ukjent horisont {h!r}. Tillatt: {sorted(valid)}")
            normalized.append(up)
        return normalized

    def applies_to(self, horizon: str | None) -> bool:
        """True hvis driveren skal kjøre for gitt horisont.

        None horizon = ingen filter (kjør alltid). Brukes f.eks. når
        agri-engine kaller score uten horisont-kontekst (status quo
        før Fase 3).
        """
        if self.horizons is None or horizon is None:
            return True
        return horizon.upper() in self.horizons


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
    """En horisonts familie-vekter + score-cap + publish-gulv.

    `min_score_publish` kan være enten:
    - `float`: felles floor for begge retninger (default-mønster)
    - `dict[str, float]` med keys ``buy``/``sell``: asymmetrisk floor

    Asymmetrisk publish-floor (session 101) lar instrumenter med
    strukturell BUY-bias (SP500/Nasdaq/Gold) ha lavere BUY-floor +
    høyere SELL-floor. Brukes når session 99-backtest viser
    asymmetri > 15pp i hit-rate.
    """

    family_weights: dict[str, float]
    max_score: float = Field(gt=0.0)
    min_score_publish: float | dict[str, float] = Field(default=0.0)

    def get_publish_floor(self, direction: str) -> float:
        """Returnér gjeldende publish-floor for en retning.

        Default: float-verdi gjelder begge. Hvis dict: slå opp på
        ``direction.lower()`` (``buy``/``sell``); fallback til
        max-floor hvis ukjent retning.
        """
        if isinstance(self.min_score_publish, dict):
            key = direction.lower()
            if key in self.min_score_publish:
                return float(self.min_score_publish[key])
            # Strengeste fallback: høyeste oppgitte floor
            return float(max(self.min_score_publish.values()))
        return float(self.min_score_publish)


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
    min_score_publish: float | dict[str, float] = Field(default=0.0)
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
    """En drivers bidrag til familie-score.

    `horizons` er kopi av DriverSpec.horizons (None hvis driveren gjelder
    alle 3 horisonter). Brukes av UI for å vise per-driver horisont-
    badge (sub-fase 12.9 Fase 3). `weight` er effective_weight etter
    re-normalisering (kan avvike fra DriverSpec.weight når filter aktivt).
    """

    name: str
    value: float
    weight: float
    contribution: float
    horizons: list[str] | None = None


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
        now: datetime | None = None,
    ) -> GroupResult:
        """Scorer `instrument` mot `rules`.

        For `FinancialRules` må `horizon` oppgis. For `AgriRules` propageres
        `horizon` til driver-filteret (sub-fase 12.11): drivere uten match
        på horisonten droppes, og familier uten gjenværende drivere bidrar
        0 til total-score. Effektiv `max_score` per kall = sum av familier
        som har minst én applicable driver. `horizon=None` på agri =
        bakoverkompatibel "alle drivere kjører" (status quo før 12.11).

        `direction` (ADR-006 session 95b): ``BUY`` (default) bruker driver-
        verdier as-is. ``SELL`` flipper hver drivers value til ``1 - value``
        på familier med ``polarity="directional"``; familier med
        ``polarity="neutral"`` er identiske mellom retninger. Default
        BUY bevarer bakoverkompatibilitet med tester som ikke bryr seg
        om retning.

        `now` (audit-runde 5, sub-fase 12.6): "as-of"-tidspunkt for
        tids-bevisste drivere (i dag kun ``event_distance``). Propageres
        til driver-laget via ``params["_now"]`` (ISO-streng). ``None`` =
        driveren faller tilbake til wallclock — kun riktig i live-mode.
        I backtest skal caller alltid sende ref-date for å unngå
        look-ahead-bias.
        """
        if isinstance(rules, FinancialRules):
            return self._score_financial(instrument, store, rules, horizon, direction, now)
        if isinstance(rules, AgriRules):
            return self._score_agri(instrument, store, rules, horizon, direction, now)
        raise TypeError(f"Unknown rules type: {type(rules).__name__}")

    # -- financial ----------------------------------------------------------

    def _score_financial(
        self,
        instrument: str,
        store: Any,
        rules: FinancialRules,
        horizon: str | None,
        direction: Direction,
        now: datetime | None,
    ) -> GroupResult:
        if horizon is None:
            raise ValueError("FinancialRules require a `horizon` argument (e.g. 'SWING').")

        horizon_spec = rules.horizons.get(horizon)
        if horizon_spec is None:
            known = ", ".join(sorted(rules.horizons)) or "<none>"
            raise KeyError(f"Horizon '{horizon}' not defined in rules. Known: {known}")

        family_results, family_scores = self._score_families(
            store, instrument, rules.families, direction, horizon, now
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
        horizon: str | None,
        direction: Direction,
        now: datetime | None,
    ) -> GroupResult:
        """Sub-fase 12.11: agri-engine respekterer DriverSpec.horizons.

        Når `horizon` er angitt filtreres drivere via DriverSpec.applies_to.
        Familier hvor alle drivere droppes bidrar 0 til total-score OG
        ekskluderes fra effective_max_score for kallet — slik at en SWING-
        score på 9 av 9 mulige (Soybean) vurderes mot 9, ikke 16. Dette
        unngår at MAKRO-only-familier (eks. enso, conab) leaker score-
        rom til SWING/SCALP-vurderingen. `horizon=None` = bakover-
        kompatibel atferd (alle familier teller, max_score = rules.max_score).
        """
        family_results, family_scores = self._score_families(
            store, instrument, rules.families, direction, horizon=horizon, now=now
        )

        family_caps = {name: spec.weight for name, spec in rules.families.items()}
        total_score = aggregators.additive_sum(family_scores, family_caps)
        active_families = self._count_active(family_scores)

        if horizon is None:
            effective_max = rules.max_score
        else:
            effective_max = sum(
                spec.weight
                for name, spec in rules.families.items()
                if any(d.applies_to(horizon) for d in spec.drivers)
            )
            if effective_max <= 0:
                effective_max = rules.max_score

        g = grade.grade_agri(
            total_score=total_score,
            active_families=active_families,
            thresholds=rules.grade_thresholds,
        )

        ctx = GateContext(
            instrument=instrument,
            score=total_score,
            max_score=effective_max,
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
            max_score=effective_max,
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
        horizon: str | None,
        now: datetime | None = None,
    ) -> tuple[dict[str, FamilyResult], dict[str, float]]:
        """Kjør alle drivere per familie. Felles for financial og agri.

        Begge FamilySpec-klasser har attributtet `.drivers: list[DriverSpec]`
        og `.polarity: FamilyPolarity`. For ``direction=SELL`` på familier
        med ``polarity="directional"`` flippes hver drivers ``value`` til
        ``1 - value`` (se ADR-006). ``polarity="neutral"`` er identisk for
        BUY og SELL.

        ``horizon`` propageres til driver-laget via en intern
        ``_horizon``-key (analog til ``_direction``, ADR-006). Drivere som
        er horisont-bevisste leser ``params["_horizon"]`` og velger
        feature; andre ignorerer key-en og scorer som før. ``None`` for
        agri (ADR-010, sub-fase 12.7 R1).

        ``now`` propageres som ``_now``-key (ISO-streng) for tids-bevisste
        drivere (i dag ``event_distance``). ``None`` = wallclock-fallback
        i driver. Audit-runde 5 sub-fase 12.6 fix-spec Steg 1.
        """
        family_results: dict[str, FamilyResult] = {}
        family_scores: dict[str, float] = {}
        flip = direction == Direction.SELL
        now_iso = now.isoformat() if now is not None else None

        for family_name, family_spec in families.items():
            driver_results: list[DriverResult] = []
            family_score = 0.0
            do_flip = flip and family_spec.polarity == "directional"

            # Sub-fase 12.9 Fase 3: filtrer drivere etter horisont via
            # DriverSpec.applies_to. None horisont = ingen filter
            # (status quo for agri-engine før Fase 3-rebase).
            applicable = [d for d in family_spec.drivers if d.applies_to(horizon)]

            # Re-normaliser vekter etter filtrering. Bevarer family-sum=1.0
            # (financial) eller spec-sum (agri) som det var før filter.
            # Hvis applicable er tom, hopper familien — driver_results+score=0.
            if applicable:
                applied_weight_sum = sum(d.weight for d in applicable)
                original_weight_sum = sum(d.weight for d in family_spec.drivers)
                # Skaler kun hvis filtrering faktisk fjernet noe; ellers er
                # applied_weight_sum == original_weight_sum og scale=1.0.
                if applied_weight_sum > 0 and applied_weight_sum != original_weight_sum:
                    scale = original_weight_sum / applied_weight_sum
                else:
                    scale = 1.0
            else:
                scale = 1.0

            for driver_spec in applicable:
                fn = drivers.get(driver_spec.name)
                # Propagér direction + horisont + now via interne `_direction`/
                # `_horizon`/`_now`-keys i en kopi av params. Drivere som er
                # context-aware (analog_* for direction; multi-horisont-
                # drivere fra sub-fase 12.7 R3+ for horisont; event_distance
                # for now) leser disse; andre ignorerer dem. Se ADR-006
                # (direction), ADR-010 (horisont), audit 12.6 Sjekk 9.5 (now).
                params_with_dir = {
                    **driver_spec.params,
                    "_direction": direction.value,
                    "_horizon": horizon,
                    "_now": now_iso,
                }
                raw_value = fn(store, instrument, params_with_dir)
                value = (1.0 - raw_value) if do_flip else raw_value
                effective_weight = driver_spec.weight * scale
                contribution = value * effective_weight
                driver_results.append(
                    DriverResult(
                        name=driver_spec.name,
                        value=value,
                        weight=effective_weight,
                        contribution=contribution,
                        horizons=driver_spec.horizons,
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
