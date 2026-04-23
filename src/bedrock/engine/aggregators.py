"""Aggregatorer — kombinerer familie-scores til én total-score.

To aggregatorer finnes:

- `weighted_horizon` (financial): hver familie har en vekt per horisont,
  total = Σ family_score × family_weight_for_horizon.
- `additive_sum` (agri): kommer i neste session. Hver familie har fast cap,
  total = Σ min(family_score, family_cap).

Aggregator-valg bestemmes av `aggregation`-feltet i YAML-reglene.
Se `docs/decisions/001-one-engine-two-aggregators.md`.
"""

from __future__ import annotations


def weighted_horizon(
    family_scores: dict[str, float],
    family_weights: dict[str, float],
) -> float:
    """Vektet sum: `total = Σ family_score[f] × family_weight[f]`.

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
    return sum(
        family_scores.get(family, 0.0) * weight for family, weight in family_weights.items()
    )
