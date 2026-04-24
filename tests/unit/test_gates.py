"""Unit-tester for `bedrock.engine.gates`."""

from __future__ import annotations

import pytest

from bedrock.engine.gates import (
    GateContext,
    GateSpec,
    VALID_CAP_GRADES,
    _REGISTRY,  # type: ignore[attr-defined]
    all_gate_names,
    apply_gates,
    cap_grade,
    gate_register,
    get_gate,
    is_gate_registered,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_custom_gates():
    """Sørg for at tester som registrerer nye gates ikke lekker."""
    existing = set(_REGISTRY.keys())
    yield
    for name in list(_REGISTRY.keys()):
        if name not in existing:
            del _REGISTRY[name]


def test_register_and_lookup() -> None:
    @gate_register("test_gate_ok")
    def _gate(ctx: GateContext, params: dict) -> bool:
        return True

    assert is_gate_registered("test_gate_ok")
    assert get_gate("test_gate_ok") is _gate


def test_register_duplicate_raises() -> None:
    @gate_register("test_gate_dup")
    def _first(ctx: GateContext, params: dict) -> bool:
        return False

    with pytest.raises(ValueError, match="already registered"):

        @gate_register("test_gate_dup")
        def _second(ctx: GateContext, params: dict) -> bool:
            return True


def test_get_unknown_gate_raises() -> None:
    with pytest.raises(KeyError, match="not registered"):
        get_gate("does_not_exist")


def test_all_gate_names_sorted() -> None:
    names = all_gate_names()
    assert names == sorted(names)
    # Standard-bibliotek er registrert
    assert "min_active_families" in names
    assert "score_below" in names
    assert "family_score_below" in names


# ---------------------------------------------------------------------------
# Cap-logikk
# ---------------------------------------------------------------------------


def test_cap_grade_none_returns_unchanged() -> None:
    assert cap_grade("A+", None) == "A+"


def test_cap_grade_lower_cap_caps() -> None:
    assert cap_grade("A+", "A") == "A"
    assert cap_grade("A", "B") == "B"


def test_cap_grade_higher_cap_no_effect() -> None:
    """Cap som er høyere enn computed grade skal ikke 'heve' grade."""
    assert cap_grade("B", "A") == "B"
    assert cap_grade("C", "A+") == "C"


def test_cap_grade_equal_unchanged() -> None:
    assert cap_grade("A", "A") == "A"


def test_cap_grade_a_plus_alias_matches_a_plus_symbol() -> None:
    """YAML bruker `A_plus`; engine internt bruker `"A+"`. Alias fungerer."""
    assert cap_grade("A+", "A_plus") == "A+"
    assert cap_grade("A+", "A") == "A"


def test_cap_grade_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown grade"):
        cap_grade("Z", "A")
    with pytest.raises(ValueError, match="Unknown cap_grade"):
        cap_grade("A", "Z")


def test_valid_cap_grades_contains_both_conventions() -> None:
    """Støtter både 'A+' (engine) og 'A_plus' (YAML) som cap_grade."""
    assert "A+" in VALID_CAP_GRADES
    assert "A_plus" in VALID_CAP_GRADES
    assert {"A", "B", "C"}.issubset(VALID_CAP_GRADES)


# ---------------------------------------------------------------------------
# apply_gates
# ---------------------------------------------------------------------------


def _ctx(**overrides) -> GateContext:
    defaults: dict = dict(
        instrument="Test",
        score=1.0,
        max_score=5.0,
        active_families=3,
        family_scores={"trend": 1.0},
    )
    defaults.update(overrides)
    return GateContext(**defaults)


def test_apply_gates_empty_returns_no_cap() -> None:
    cap, triggered = apply_gates([], _ctx())
    assert cap is None
    assert triggered == []


def test_apply_gates_not_triggered_returns_no_cap() -> None:
    specs = [GateSpec(name="min_active_families", params={"min_count": 1}, cap_grade="A")]
    cap, triggered = apply_gates(specs, _ctx(active_families=3))
    assert cap is None
    assert triggered == []


def test_apply_gates_triggered_returns_cap() -> None:
    specs = [GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A")]
    cap, triggered = apply_gates(specs, _ctx(active_families=3))
    assert cap == "A"
    assert triggered == ["min_active_families"]


def test_apply_gates_multiple_triggered_lowest_cap_wins() -> None:
    specs = [
        GateSpec(name="min_active_families", params={"min_count": 5}, cap_grade="A"),
        GateSpec(name="score_below", params={"threshold": 10.0}, cap_grade="B"),
    ]
    cap, triggered = apply_gates(specs, _ctx(active_families=3, score=1.0))
    assert cap == "B"
    # Triggered rekkefølge følger spec-rekkefølge for determinisme
    assert triggered == ["min_active_families", "score_below"]


def test_apply_gates_unknown_gate_raises() -> None:
    specs = [GateSpec(name="ghost_gate", cap_grade="A")]
    with pytest.raises(KeyError, match="not registered"):
        apply_gates(specs, _ctx())


# ---------------------------------------------------------------------------
# Standard-bibliotek
# ---------------------------------------------------------------------------


def test_min_active_families_triggers_when_below() -> None:
    fn = get_gate("min_active_families")
    assert fn(_ctx(active_families=2), {"min_count": 3}) is True
    assert fn(_ctx(active_families=3), {"min_count": 3}) is False  # streng <
    assert fn(_ctx(active_families=4), {"min_count": 3}) is False


def test_score_below_triggers_when_under() -> None:
    fn = get_gate("score_below")
    assert fn(_ctx(score=1.5), {"threshold": 2.0}) is True
    assert fn(_ctx(score=2.0), {"threshold": 2.0}) is False
    assert fn(_ctx(score=2.5), {"threshold": 2.0}) is False


def test_family_score_below_triggers_when_under() -> None:
    fn = get_gate("family_score_below")
    assert fn(_ctx(family_scores={"risk": 0.3}), {"family": "risk", "threshold": 0.5}) is True
    assert fn(_ctx(family_scores={"risk": 0.6}), {"family": "risk", "threshold": 0.5}) is False


def test_family_score_below_missing_family_triggers_conservative() -> None:
    """Hvis familien ikke finnes i scorene → gate utløses (konservativt)."""
    fn = get_gate("family_score_below")
    assert fn(_ctx(family_scores={"trend": 1.0}), {"family": "risk", "threshold": 0.5}) is True


# ---------------------------------------------------------------------------
# GateSpec validering
# ---------------------------------------------------------------------------


def test_gatespec_rejects_unknown_field() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        GateSpec(name="x", cap_grade="A", when="foo")  # type: ignore[call-arg]


def test_gatespec_default_params_empty_dict() -> None:
    spec = GateSpec(name="x", cap_grade="A")
    assert spec.params == {}
