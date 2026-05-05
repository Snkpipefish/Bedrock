"""Driver-attribution for A-SELL underperformance på Sukker.

Analytiker-funn (peer-review 2026-05): A SELL har -3.5%/22% hit-rate på
180d mens C SELL har +5.4%/58.6% — non-monoton progresjon. Hypotese:
ekstrem-grade SELL fanger COT MM-positioning-overshoots som mean-
reverter. Dette scriptet identifiserer hvilken familie som dominerer
A-grade-bøtta.

Per ref_date:
1. Kjør generate_signals for Sugar
2. Plukk SELL-entry for h=180d
3. Hvis grade ∈ {A, A+}, lagre family-scores + faktisk forward_return
4. Aggregér: median family_score per familie, conditioned på hit/miss

Output: docs/sugar_attribution_a_sell_2026-05.md med:
- Familie-bidrag per grade-bøtte
- Korrelasjon family_score vs forward_return per familie
- Identifisering av "anti-driver" (positiv score → negativ avkastning)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore

DEFAULT_DB = "data/bedrock.db"
DEFAULT_OUT = "docs/sugar_attribution_a_sell_2026-05.md"
INSTRUMENTS_DIR = "config/instruments"
INSTRUMENT = "Sugar"
DIRECTION = "sell"
HORIZON_NAME = "MAKRO"  # 90d/180d backtest mappes til MAKRO i runner
STEP_DAYS = 7
HORIZON_DAYS = 180  # primært vindu — 180d hadde sterkest non-monotonisitet


def collect_signals(
    store: DataStore,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    """Returnerer liste med dict per ref_date: families, grade, score, forward_return."""
    from bedrock.orchestrator.signals import generate_signals

    outcomes = store.get_outcomes(INSTRUMENT, horizon_days=HORIZON_DAYS)
    outcomes = outcomes[
        (outcomes["ref_date"] >= pd.Timestamp(from_date))
        & (outcomes["ref_date"] <= pd.Timestamp(to_date))
    ].sort_values("ref_date").reset_index(drop=True)
    outcomes = outcomes.iloc[::STEP_DAYS].reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    n = len(outcomes)
    for i, row in enumerate(outcomes.itertuples(index=False)):
        ref_ts: pd.Timestamp = row.ref_date
        if i % 50 == 0:
            print(f"[{i}/{n}] {ref_ts.date()}", flush=True)
        as_of_store = AsOfDateStore(store, ref_ts)
        try:
            result = generate_signals(
                INSTRUMENT,
                as_of_store,
                instruments_dir=INSTRUMENTS_DIR,
                horizons=[HORIZON_NAME],
                directions=None,
                write_snapshot=False,
                now=ref_ts.to_pydatetime() if hasattr(ref_ts, "to_pydatetime") else None,
            )
        except Exception as exc:
            print(f"  skip {ref_ts.date()}: {exc}", flush=True)
            continue

        entry = next(
            (
                e
                for e in result.entries
                if getattr(e.direction, "value", str(e.direction)).lower() == DIRECTION
            ),
            None,
        )
        if entry is None:
            continue

        family_scores = {fname: float(fr.score) for fname, fr in entry.families.items()}
        rows.append(
            {
                "ref_date": ref_ts.date().isoformat(),
                "grade": entry.grade,
                "score": float(entry.score),
                "published": bool(entry.published),
                "forward_return_pct": float(row.forward_return_pct),
                "hit": float(row.forward_return_pct) >= 3.0,
                **{f"fam_{k}": v for k, v in family_scores.items()},
            }
        )
    return rows


def attribution_report(df: pd.DataFrame) -> str:
    """Bygg markdown-rapport med grade-bøtter og korrelasjoner."""
    lines: list[str] = []
    lines.append("# Sugar driver-attribution: A-SELL underperformance\n")
    lines.append(
        f"*Generert {date.today()} via `scripts/sugar_attribution_a_sell.py`. "
        f"Vindu: {df['ref_date'].min()} → {df['ref_date'].max()}. "
        f"n={len(df)} SELL-entries på h={HORIZON_DAYS}d.*\n"
    )

    fam_cols = [c for c in df.columns if c.startswith("fam_")]

    lines.append("## 1. Per grade-bøtte\n")
    lines.append("| Grade | n | Hit-rate | Avg fwd_return | Avg score |")
    lines.append("|---|---:|---:|---:|---:|")
    for g in ["A_plus", "A", "B", "C"]:
        sub = df[df["grade"] == g]
        if sub.empty:
            continue
        lines.append(
            f"| {g} | {len(sub)} | {sub['hit'].mean()*100:.1f}% | "
            f"{sub['forward_return_pct'].mean():+.2f}% | {sub['score'].mean():.2f} |"
        )
    lines.append("")

    lines.append("## 2. Median familie-score per grade-bøtte\n")
    headers = ["Grade", "n"] + [c.replace("fam_", "") for c in fam_cols]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for g in ["A_plus", "A", "B", "C"]:
        sub = df[df["grade"] == g]
        if sub.empty:
            continue
        row = [g, str(len(sub))]
        for c in fam_cols:
            row.append(f"{sub[c].median():.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## 3. Korrelasjon familie-score vs forward-return (alle SELL)\n")
    lines.append(
        "*Negativ korrelasjon = familien fungerer som SELL-signal "
        "(høy score → fallende pris). Positiv korrelasjon = familien "
        "**virker mot retningen** og kan være anti-driver.*\n"
    )
    lines.append("| Familie | Pearson ρ | n | Tolkning |")
    lines.append("|---|---:|---:|---|")
    for c in fam_cols:
        valid = df[[c, "forward_return_pct"]].dropna()
        if len(valid) < 30:
            continue
        rho = valid[c].corr(valid["forward_return_pct"])
        if abs(rho) < 0.05:
            tolkning = "ingen relasjon"
        elif rho < 0:
            tolkning = "OK (sell-signal fungerer)"
        else:
            tolkning = "**ANTI-DRIVER** (overshoot/mean-reversion)"
        lines.append(f"| {c.replace('fam_', '')} | {rho:+.3f} | {len(valid)} | {tolkning} |")
    lines.append("")

    lines.append("## 4. A-grade SELL: hit vs miss familie-snitt\n")
    a_grade = df[df["grade"].isin(["A", "A_plus"])]
    if not a_grade.empty:
        lines.append(
            "*Hvilke familier scoret høyere når A-SELL bommet? Disse "
            "drar opp scoren feilaktig.*\n"
        )
        lines.append("| Familie | Avg score (HIT) | Avg score (MISS) | Diff (M-H) |")
        lines.append("|---|---:|---:|---:|")
        for c in fam_cols:
            hit_avg = a_grade[a_grade["hit"]][c].mean()
            miss_avg = a_grade[~a_grade["hit"]][c].mean()
            diff = miss_avg - hit_avg
            star = " **⚠**" if diff > 0.05 else ""
            lines.append(
                f"| {c.replace('fam_', '')} | {hit_avg:.3f} | {miss_avg:.3f} | "
                f"{diff:+.3f}{star} |"
            )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--years", type=int, default=14)
    args = parser.parse_args()

    today = date.today()
    from_d = today - timedelta(days=365 * args.years)

    store = DataStore(Path(args.db))
    print(f"Samler SELL-signaler {from_d} → {today}", flush=True)
    t0 = time.time()
    rows = collect_signals(store, from_d, today)
    print(f"Samlet {len(rows)} signaler på {(time.time()-t0)/60:.1f} min", flush=True)

    df = pd.DataFrame(rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(attribution_report(df), encoding="utf-8")
    # Lagre rådata også for senere re-aggregering
    df.to_csv(out.with_suffix(".csv"), index=False)
    print(f"Skrevet {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
