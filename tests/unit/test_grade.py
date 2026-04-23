"""Tester for grade-logikk."""

from __future__ import annotations

import pytest

from bedrock.engine.grade import (
    AgriGradeThreshold,
    AgriGradeThresholds,
    GradeThreshold,
    GradeThresholds,
    grade_agri,
    grade_financial,
)


@pytest.fixture
def gold_thresholds() -> GradeThresholds:
    """Terskler fra PLAN.md § 4.2 (Gold SWING)."""
    return GradeThresholds(
        a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=4),
        a=GradeThreshold(min_pct_of_max=0.55, min_families=3),
        b=GradeThreshold(min_pct_of_max=0.35, min_families=2),
    )


def test_grade_a_plus_when_pct_and_families_met(gold_thresholds: GradeThresholds) -> None:
    # 4.8/6.0 = 0.80 > 0.75, og 4 familier aktive
    assert grade_financial(4.8, 6.0, 4, gold_thresholds) == "A+"


def test_grade_a_plus_denied_when_families_insufficient(
    gold_thresholds: GradeThresholds,
) -> None:
    """A+ krever BÅDE pct og min_families. Mangler én familie -> A, ikke A+."""
    assert grade_financial(4.8, 6.0, 3, gold_thresholds) == "A"


def test_grade_a(gold_thresholds: GradeThresholds) -> None:
    # 3.5/6.0 = 0.58 > 0.55, 3 familier
    assert grade_financial(3.5, 6.0, 3, gold_thresholds) == "A"


def test_grade_b(gold_thresholds: GradeThresholds) -> None:
    # 2.2/6.0 = 0.367 > 0.35, 2 familier
    assert grade_financial(2.2, 6.0, 2, gold_thresholds) == "B"


def test_grade_c_below_all_thresholds(gold_thresholds: GradeThresholds) -> None:
    assert grade_financial(1.0, 6.0, 1, gold_thresholds) == "C"


def test_grade_c_when_max_score_is_zero(gold_thresholds: GradeThresholds) -> None:
    """Defensivt: max_score=0 gir C (ikke div-0)."""
    assert grade_financial(0.0, 0.0, 4, gold_thresholds) == "C"


def test_grade_c_when_max_score_negative(gold_thresholds: GradeThresholds) -> None:
    assert grade_financial(1.0, -1.0, 4, gold_thresholds) == "C"


def test_grade_thresholds_accept_yaml_style_aliases() -> None:
    """YAML-feltene er `A_plus`, `A`, `B` — må kunne parses via alias."""
    yaml_style = {
        "A_plus": {"min_pct_of_max": 0.75, "min_families": 4},
        "A": {"min_pct_of_max": 0.55, "min_families": 3},
        "B": {"min_pct_of_max": 0.35, "min_families": 2},
    }
    thresholds = GradeThresholds.model_validate(yaml_style)
    assert thresholds.a_plus.min_pct_of_max == 0.75
    assert thresholds.a.min_families == 3


# ---------------------------------------------------------------------------
# grade_agri (absolutte terskler)
# ---------------------------------------------------------------------------


@pytest.fixture
def corn_agri_thresholds() -> AgriGradeThresholds:
    """Terskler fra PLAN § 4.3 Corn."""
    return AgriGradeThresholds(
        a_plus=AgriGradeThreshold(min_score=14.0, min_families_active=4),
        a=AgriGradeThreshold(min_score=10.0, min_families_active=3),
        b=AgriGradeThreshold(min_score=7.0, min_families_active=2),
    )


def test_grade_agri_a_plus(corn_agri_thresholds: AgriGradeThresholds) -> None:
    assert grade_agri(15.0, 4, corn_agri_thresholds) == "A+"


def test_grade_agri_a_plus_denied_when_families_insufficient(
    corn_agri_thresholds: AgriGradeThresholds,
) -> None:
    # Score OK for A+ men kun 3 familier aktive -> faller til A
    assert grade_agri(15.0, 3, corn_agri_thresholds) == "A"


def test_grade_agri_a(corn_agri_thresholds: AgriGradeThresholds) -> None:
    assert grade_agri(10.0, 3, corn_agri_thresholds) == "A"


def test_grade_agri_b(corn_agri_thresholds: AgriGradeThresholds) -> None:
    assert grade_agri(7.0, 2, corn_agri_thresholds) == "B"


def test_grade_agri_c_when_below_all(corn_agri_thresholds: AgriGradeThresholds) -> None:
    assert grade_agri(3.0, 1, corn_agri_thresholds) == "C"


def test_grade_agri_c_when_score_high_but_one_family_active(
    corn_agri_thresholds: AgriGradeThresholds,
) -> None:
    """Én familie aktiv selv med høy score -> C. Hindrer at én ekstrem familie
    alene gir A+."""
    assert grade_agri(20.0, 1, corn_agri_thresholds) == "C"


def test_agri_grade_thresholds_accept_yaml_aliases() -> None:
    yaml_style = {
        "A_plus": {"min_score": 14, "min_families_active": 4},
        "A": {"min_score": 10, "min_families_active": 3},
        "B": {"min_score": 7, "min_families_active": 2},
    }
    thresholds = AgriGradeThresholds.model_validate(yaml_style)
    assert thresholds.a_plus.min_score == 14
    assert thresholds.b.min_families_active == 2
