"""Grade-logikk: omregn numerisk score til A+/A/B/C.

Terskler leses fra YAML-regelen (`grade_thresholds`-blokken). Hver grade
krever både at score-andelen av max overskrider en terskel, OG at et
minimum antall familier er aktive (score > 0). Dette hindrer at én
ekstremt sterk familie alene kan trigge en høy grade.

Denne modulen implementerer kun `grade_financial` i Fase 1. `grade_agri`
(terskel på absolutt score i stedet for pct-av-max) kommer med
`additive_sum`-aggregatoren.
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

    if pct >= thresholds.a_plus.min_pct_of_max and active_families >= thresholds.a_plus.min_families:
        return "A+"
    if pct >= thresholds.a.min_pct_of_max and active_families >= thresholds.a.min_families:
        return "A"
    if pct >= thresholds.b.min_pct_of_max and active_families >= thresholds.b.min_families:
        return "B"
    return "C"
