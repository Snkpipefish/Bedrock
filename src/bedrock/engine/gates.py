"""Gate-registry og `apply_gates`.

Gates er "cap"-regler: hvis en gate utløses, kan ikke computed grade
overstige et definert nivå. Se ADR-003 for design (navn-basert registry,
ikke string-DSL).

YAML:

```yaml
gates:
  - {name: min_active_families, params: {min_count: 3}, cap_grade: A}
  - {name: score_below, params: {threshold: 2.0}, cap_grade: B}
```

Python:

```python
@gate_register("min_active_families")
def min_active_families(context: GateContext, params: dict) -> bool:
    return context.active_families < params["min_count"]
```

Gate returnerer `True` = utløst. Engine kapper til `cap_grade` på
alle utløste gater og velger laveste cap på tvers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------------


class GateSpec(BaseModel):
    """YAML-form for én gate."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    cap_grade: str  # "A_plus" | "A" | "B" | "C"

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class GateContext:
    """Kontekst tilgjengelig for gate-funksjoner.

    Holdes bevisst smal: bare felter som er nødvendige for data-frie
    gates (score/grade/family-counts). Gates som trenger eksterne data
    (kalender, freshness) må eksplisitt utvide denne strukturen i egen
    session med tilhørende ADR.
    """

    instrument: str
    score: float
    max_score: float
    active_families: int
    family_scores: dict[str, float] = field(default_factory=dict)
    now: datetime | None = None


GateFn = Callable[[GateContext, dict[str, Any]], bool]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, GateFn] = {}


def gate_register(name: str) -> Callable[[GateFn], GateFn]:
    """Dekorator som legger gate-funksjon i global registry.

    Kaster `ValueError` ved duplikat-navn (samme modell som drivers).
    """

    def decorator(fn: GateFn) -> GateFn:
        if name in _REGISTRY:
            raise ValueError(
                f"Gate {name!r} already registered "
                f"(by {_REGISTRY[name].__module__}.{_REGISTRY[name].__qualname__})"
            )
        _REGISTRY[name] = fn
        return fn

    return decorator


def get_gate(name: str) -> GateFn:
    """Slå opp gate ved navn. Kaster `KeyError` hvis ukjent."""
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Gate {name!r} not registered. Known: {known}") from None


def all_gate_names() -> list[str]:
    return sorted(_REGISTRY)


def is_gate_registered(name: str) -> bool:
    return name in _REGISTRY


# ---------------------------------------------------------------------------
# Cap-logikk
# ---------------------------------------------------------------------------

# Laveste → høyeste grade-rangering. C er "lavest" (verst), A+ høyest.
# `grade_financial` / `grade_agri` returnerer strengene "A+", "A", "B", "C".
# YAML cap_grade-feltet aksepterer samme strenger (og "A_plus" som alias
# for konsistens med YAML-grade_thresholds-nøkler, som bruker A_plus).
_GRADE_ORDER: dict[str, int] = {"C": 0, "B": 1, "A": 2, "A+": 3}

# YAML-cap-alias for konsistens med grade_thresholds-nøkkelen A_plus.
_CAP_ALIAS: dict[str, str] = {"A_plus": "A+"}

VALID_CAP_GRADES: frozenset[str] = frozenset({"C", "B", "A", "A+", "A_plus"})


def _normalize_grade(value: str) -> str:
    """Map YAML-skrivemåte til engine-intern form."""
    return _CAP_ALIAS.get(value, value)


def apply_gates(
    specs: list[GateSpec],
    context: GateContext,
) -> tuple[str | None, list[str]]:
    """Kjør alle gates og returner (lavest-cap, liste-av-utløste-navn).

    - Hvis ingen gate er utløst: `(None, [])`.
    - Flere utløste gates: lavest cap_grade vinner (f.eks. cap til B
      slår cap til A fordi B < A i rangeringen).
    - Rekkefølge av utløste navn i returlisten er samme som specs-
      rekkefølgen (for determinisme i explain-trace).

    `GateFn`-exceptions propageres — gate-forfatter ansvar for å håndtere
    manglende params, mens Engine kan logge utløseren med instrument-
    kontekst.
    """
    triggered_names: list[str] = []
    cap_grades: list[str] = []

    for spec in specs:
        fn = get_gate(spec.name)
        if fn(context, spec.params):
            triggered_names.append(spec.name)
            cap_grades.append(spec.cap_grade)

    if not cap_grades:
        return None, []

    # Velg laveste cap (mest restriktiv)
    lowest_cap = min(cap_grades, key=lambda g: _GRADE_ORDER[g])
    return lowest_cap, triggered_names


def cap_grade(grade: str, cap: str | None) -> str:
    """Anvend cap på grade — returner minimum av de to.

    `cap=None` → grade uendret.
    Både "A+" og "A_plus" aksepteres som cap (YAML-nøkkel A_plus
    speiler grade_thresholds-konvensjonen).
    Ugyldig cap eller grade → ValueError.
    """
    if cap is None:
        return grade
    norm_grade = _normalize_grade(grade)
    norm_cap = _normalize_grade(cap)
    if norm_grade not in _GRADE_ORDER:
        raise ValueError(f"Unknown grade: {grade!r}")
    if norm_cap not in _GRADE_ORDER:
        raise ValueError(f"Unknown cap_grade: {cap!r}. Valid: {sorted(VALID_CAP_GRADES)}")
    if _GRADE_ORDER[norm_cap] < _GRADE_ORDER[norm_grade]:
        return norm_cap
    return norm_grade


# ---------------------------------------------------------------------------
# Standard-bibliotek av gates (data-frie)
# ---------------------------------------------------------------------------


@gate_register("min_active_families")
def _min_active_families(context: GateContext, params: dict[str, Any]) -> bool:
    """Utløses hvis `active_families < params['min_count']`.

    Nyttig for å kappe grade når for få familier bidrar (fragil signal).

    YAML:
        gates:
          - {name: min_active_families, params: {min_count: 3}, cap_grade: A}
    """
    min_count = params["min_count"]
    return context.active_families < int(min_count)


@gate_register("score_below")
def _score_below(context: GateContext, params: dict[str, Any]) -> bool:
    """Utløses hvis `score < params['threshold']`.

    Dobbelt-sjekk mot computed grade — brukbart hvis grade-modellen har
    edge cases (f.eks. stor `max_score` men lav `min_pct`-terskel).

    YAML:
        gates:
          - {name: score_below, params: {threshold: 2.0}, cap_grade: B}
    """
    threshold = params["threshold"]
    return context.score < float(threshold)


@gate_register("family_score_below")
def _family_score_below(context: GateContext, params: dict[str, Any]) -> bool:
    """Utløses hvis `family_scores[family] < threshold`.

    Nyttig for asset-klasser der én familie MÅ bidra (f.eks. risk).

    YAML:
        gates:
          - {name: family_score_below, params: {family: risk, threshold: 0.5}, cap_grade: A}

    Hvis familien ikke finnes i scorene → gate utløses (konservativt).
    """
    family = params["family"]
    threshold = float(params["threshold"])
    score = context.family_scores.get(family)
    if score is None:
        return True
    return score < threshold


__all__ = [
    "VALID_CAP_GRADES",
    "GateContext",
    "GateFn",
    "GateSpec",
    "all_gate_names",
    "apply_gates",
    "cap_grade",
    "gate_register",
    "get_gate",
    "is_gate_registered",
]
