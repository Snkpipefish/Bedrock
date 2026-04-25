"""Grade-logikk: omregn numerisk score til A+/A/B/C.

Terskler leses fra YAML-regelen (`grade_thresholds`-blokken). Hver grade
krever både at score-terskelen er oppfylt, OG at et minimum antall
familier er aktive (score > 0). Dette hindrer at én ekstremt sterk
familie alene kan trigge en høy grade.

To grade-funksjoner:

- `grade_financial`: terskel er pct-av-horizon-max (f.eks. 0.75 av 6.0).
  Brukes med `weighted_horizon`-aggregatoren.
- `grade_agri`: terskel er absolutt score (f.eks. 14 av 18).
  Brukes med `additive_sum`-aggregatoren.

Agri-terskler er absolutte fordi agri-skalaen er fast (typisk max 18) og
familie-caps i YAML er absolutte poeng.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GradeThreshold(BaseModel):
    """Én grade-terskel.

    `min_pct_of_max`: score må være minst denne andelen av `max_score`
    (0.75 = 75 % av horisontens max).

    `min_families`: minst så mange familier må ha score > 0.
    """

    min_pct_of_max: float = Field(ge=0.0, le=1.0)
    min_families: int = Field(ge=0)


class GradeThresholds(BaseModel):
    """Tre-lags grade-terskler. YAML-feltene er `A_plus`, `A`, `B`.

    Ingen `C`-terskel — C er "ingen av de over".
    """

    a_plus: GradeThreshold = Field(alias="A_plus")
    a: GradeThreshold = Field(alias="A")
    b: GradeThreshold = Field(alias="B")

    model_config = ConfigDict(populate_by_name=True)


def grade_financial(
    total_score: float,
    max_score: float,
    active_families: int,
    thresholds: GradeThresholds,
) -> str:
    """Returnerer 'A+', 'A', 'B', eller 'C'.

    Terskler evalueres fra høyest til lavest; første som matcher vinner.
    `max_score <= 0` gir alltid 'C' (defensivt — hindrer div-0).
    """
    if max_score <= 0:
        return "C"

    pct = total_score / max_score

    if (
        pct >= thresholds.a_plus.min_pct_of_max
        and active_families >= thresholds.a_plus.min_families
    ):
        return "A+"
    if pct >= thresholds.a.min_pct_of_max and active_families >= thresholds.a.min_families:
        return "A"
    if pct >= thresholds.b.min_pct_of_max and active_families >= thresholds.b.min_families:
        return "B"
    return "C"


# ---------------------------------------------------------------------------
# Agri-grade (additive_sum)
# ---------------------------------------------------------------------------


class AgriGradeThreshold(BaseModel):
    """Én agri-grade-terskel.

    `min_score`: total-score må være minst dette absolutt-tallet (f.eks. 14).
    `min_families_active`: minst så mange familier må ha score > 0.

    YAML-eksempel (PLAN § 4.3 Corn):
        grade_thresholds:
          A_plus: {min_score: 14, min_families_active: 4}
    """

    min_score: float = Field(ge=0.0)
    min_families_active: int = Field(ge=0)


class AgriGradeThresholds(BaseModel):
    """Tre-lags agri-terskler. YAML-felter: `A_plus`, `A`, `B`."""

    a_plus: AgriGradeThreshold = Field(alias="A_plus")
    a: AgriGradeThreshold = Field(alias="A")
    b: AgriGradeThreshold = Field(alias="B")

    model_config = ConfigDict(populate_by_name=True)


def grade_agri(
    total_score: float,
    active_families: int,
    thresholds: AgriGradeThresholds,
) -> str:
    """Returnerer 'A+', 'A', 'B', eller 'C' for agri (absolutte terskler).

    Terskler evalueres fra høyest til lavest; første som matcher vinner.
    """
    if (
        total_score >= thresholds.a_plus.min_score
        and active_families >= thresholds.a_plus.min_families_active
    ):
        return "A+"
    if (
        total_score >= thresholds.a.min_score
        and active_families >= thresholds.a.min_families_active
    ):
        return "A"
    if (
        total_score >= thresholds.b.min_score
        and active_families >= thresholds.b.min_families_active
    ):
        return "B"
    return "C"
