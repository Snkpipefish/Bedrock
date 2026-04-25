"""Aggregatorer — kombinerer familie-scores til én total-score.

To aggregatorer finnes:

- `weighted_horizon` (financial): hver familie har en vekt per horisont,
  total = Σ family_score × family_weight_for_horizon.
- `additive_sum` (agri): hver familie har en absolutt cap i YAML
  (`families.<f>.weight`), total = Σ family_score × family_cap.

Matematisk er de identiske (Σ score × faktor) — men semantikken og
hvor faktoren kommer fra i YAML er forskjellig, og de er ment å kunne
divergere (f.eks. framtidig capping eller non-linearitet i agri). Holdes
derfor som to separate funksjoner med hver sin kontrakt.

Aggregator-valg bestemmes av `aggregation`-feltet i YAML-reglene.
Se `docs/decisions/001-one-engine-two-aggregators.md`.
"""

from __future__ import annotations


def weighted_horizon(
    family_scores: dict[str, float],
    family_weights: dict[str, float],
) -> float:
    """Financial: `total = Σ family_score[f] × family_weight_for_horizon[f]`.

    `family_weights` kommer fra den aktive horisontens `family_weights`-blokk
    i YAML, og er derfor horisont-avhengig. Samme instrument kan ha ulike
    vekter for SCALP, SWING og MAKRO.

    Regler:
    - Familier i `family_weights` men ikke i `family_scores` teller som 0.
      (Dvs. horisonten forventet en familie, men scoring-løkken produserte
      ikke en score for den.)
    - Familier i `family_scores` men ikke i `family_weights` *ignoreres*.
      (Dvs. bruker har ikke gitt dem vekt for denne horisonten. Eksplisitt
      opt-in pr horisont.)

    Dette er prinsipp 1 fra PLAN.md: YAML bestemmer *hvilke* familier som
    teller for en gitt horisont.
    """
    return sum(family_scores.get(family, 0.0) * weight for family, weight in family_weights.items())


def additive_sum(
    family_scores: dict[str, float],
    family_caps: dict[str, float],
) -> float:
    """Agri: `total = Σ family_score[f] × family_cap[f]`.

    `family_caps` kommer fra YAML `families.<f>.weight` og representerer
    familiens *absolutte* maks-bidrag i agri-score-skalaen (f.eks.
    `outlook: weight: 5` betyr outlook kan gi opp til 5 poeng av total-max).

    Matematikken er lik `weighted_horizon` i dag, men semantikken er ulik:
    her er faktoren en absolutt score-cap, ikke en relativ horisont-vekt.

    Regler (samme som `weighted_horizon`):
    - Familier i `family_caps` men ikke i `family_scores` teller som 0.
    - Familier i `family_scores` men ikke i `family_caps` ignoreres.
    """
    return sum(family_scores.get(family, 0.0) * cap for family, cap in family_caps.items())
