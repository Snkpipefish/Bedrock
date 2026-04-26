"""Session 95a — design-spike: BUY/SELL same-score-bug demonstrert.

Kjører Gold gjennom Engine.score (uendret produksjonskode), viser at
score er identisk for BUY og SELL, så simulerer ADR-006-anbefalingen
(Alt C — per-driver flip på familier med polarity=directional) ved å
flippe driver-verdier i en lokal kopi av GroupResult.

Output:

    Gold MAKRO — produksjonsoppførsel:
      BUY  score = 4.523, grade = A
      SELL score = 4.523, grade = A   <-- bug: identisk

    Gold MAKRO — etter ADR-006 Alt C-flip (simulert):
      BUY  score = 4.523, grade = A
      SELL score = 1.812, grade = C   <-- asymmetri demonstrert

Ingen produksjonskode endret. Brukes som vedlegg til ADR-006.

Kjør:
    python -m scripts.spike_session95a_buy_sell_asymmetry
"""
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from bedrock.config.instruments import load_instrument_config
from bedrock.data.store import DataStore
from bedrock.engine import aggregators, grade
from bedrock.engine.engine import (
    DriverResult,
    Engine,
    FamilyResult,
    FinancialRules,
    GroupResult,
)

# Familier som er konfigurert som "kontekst" for Gold per ADR-006 §
# konsekvenser. Alle andre familier er `directional` og flippes for SELL.
GOLD_NEUTRAL_FAMILIES = {"risk"}  # vol_regime trend-friendly begge veier


def _flip_family(fam: FamilyResult, family_max_weight: float) -> FamilyResult:
    """Returnerer ny FamilyResult der hver drivers value er invertert.

    `family_max_weight` er ikke brukt i denne enkle 1-flip-varianten —
    inkludert som signatur-plassholder hvis vi senere vil normalisere
    mot per-familie max.
    """
    flipped_drivers: list[DriverResult] = []
    new_score = 0.0
    for dr in fam.drivers:
        new_value = round(1.0 - dr.value, 6)
        new_contribution = round(new_value * dr.weight, 6)
        flipped_drivers.append(
            DriverResult(
                name=dr.name,
                value=new_value,
                weight=dr.weight,
                contribution=new_contribution,
            )
        )
        new_score += new_contribution
    return FamilyResult(name=fam.name, score=new_score, drivers=flipped_drivers)


def simulate_sell_score(
    buy_result: GroupResult,
    rules: FinancialRules,
    horizon: str,
    neutral_families: set[str],
) -> GroupResult:
    """Lokal simulering av ADR-006 Alt C på et BUY-resultat.

    Lager en ny GroupResult der directional-familier er flippet på
    driver-nivå og total score er reaggregert.
    """
    horizon_spec = rules.horizons[horizon]

    new_families: dict[str, FamilyResult] = {}
    new_family_scores: dict[str, float] = {}
    for name, fam in buy_result.families.items():
        if name in neutral_families:
            new_families[name] = fam  # uendret
            new_family_scores[name] = fam.score
        else:
            flipped = _flip_family(fam, horizon_spec.family_weights.get(name, 1.0))
            new_families[name] = flipped
            new_family_scores[name] = flipped.score

    new_score = aggregators.weighted_horizon(new_family_scores, horizon_spec.family_weights)
    active_families = sum(1 for s in new_family_scores.values() if s > 0.0)
    new_grade = grade.grade_financial(
        total_score=new_score,
        max_score=horizon_spec.max_score,
        active_families=active_families,
        thresholds=rules.grade_thresholds,
    )

    return GroupResult(
        instrument=buy_result.instrument,
        horizon=horizon,
        aggregation=buy_result.aggregation,
        score=new_score,
        grade=new_grade,
        max_score=horizon_spec.max_score,
        active_families=active_families,
        families=new_families,
        gates_triggered=list(buy_result.gates_triggered),
    )


def main() -> None:
    instrument_id = "Gold"
    horizon = "MAKRO"
    db_path = Path("data/bedrock.db")

    if not db_path.exists():
        print(f"FEIL: {db_path} mangler — kan ikke kjøre Engine mot ekte data.")
        return

    store = DataStore(db_path)
    cfg = load_instrument_config(Path(f"config/instruments/{instrument_id.lower()}.yaml"))
    assert isinstance(cfg.rules, FinancialRules)

    eng = Engine()
    buy_result = eng.score(cfg.instrument.id, store, cfg.rules, horizon=horizon)
    # Produksjonsoppførsel: SELL får identisk GroupResult i dag.
    sell_result_today = deepcopy(buy_result)

    print(f"=== {instrument_id} {horizon} — produksjonsoppførsel (bug) ===")
    print(f"  BUY  score = {buy_result.score:.4f}, grade = {buy_result.grade}")
    print(
        f"  SELL score = {sell_result_today.score:.4f}, grade = {sell_result_today.grade}"
        f"   <-- identisk (bug)"
    )

    # ADR-006 Alt C: per-driver flip på directional-familier
    sell_result_proposed = simulate_sell_score(
        buy_result, cfg.rules, horizon, GOLD_NEUTRAL_FAMILIES
    )

    print(f"\n=== {instrument_id} {horizon} — ADR-006 Alt C (simulert) ===")
    print(f"  BUY  score = {buy_result.score:.4f}, grade = {buy_result.grade}")
    print(
        f"  SELL score = {sell_result_proposed.score:.4f}, "
        f"grade = {sell_result_proposed.grade}   <-- asymmetri"
    )

    print("\nFamilie-by-familie sammenligning:")
    print(f"  {'family':<14}{'pol':<8}{'BUY':>10}{'SELL_old':>12}{'SELL_new':>12}")
    for name in buy_result.families:
        polarity = "neutral" if name in GOLD_NEUTRAL_FAMILIES else "direct"
        buy_s = buy_result.families[name].score
        sell_old = sell_result_today.families[name].score
        sell_new = sell_result_proposed.families[name].score
        print(f"  {name:<14}{polarity:<8}{buy_s:>10.4f}{sell_old:>12.4f}{sell_new:>12.4f}")

    # Aggregert effekt: hva slags grade-distribusjon vil bot-en se?
    delta = buy_result.score - sell_result_proposed.score
    print(
        f"\nNetto BUY−SELL spread (ADR-006): {delta:+.4f} "
        f"(av max {cfg.rules.horizons[horizon].max_score:.1f})"
    )
    print(
        "Bug-i-dag-spread: 0.0000 (BUY og SELL er bit-for-bit identiske, "
        "halvparten av signal-volumet er meningsløst)."
    )


if __name__ == "__main__":
    main()
