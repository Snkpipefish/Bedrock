"""Rullerende publish-floor-analyse for sukker (analytiker-anbefaling B).

Adresserer kritikk: statisk 14-års-floor antar regime-stasjonaritet.
Sukker har minimum 2 regimer (oversupply 2017-2020, shortage-press
2023+). Floor settes der historisk grade-grense gir ≥ 55% hit-rate
i den retningen.

For hver dato i 2018-2026:
1. Slå opp 5-års rolling vindu på SELL/BUY-signaler
2. Finn lavest score-terskel der hit-rate ≥ 55%
3. Sammenlign mot statisk floor (buy=7, sell=5)

Bruker eksisterende attribution-CSV som har score+grade+forward_return
for SELL h=180d. Utvider til BUY senere.

Output: docs/sugar_rolling_floor_2026-05.md
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import pandas as pd

ATTR_CSV = Path("docs/sugar_attribution_a_sell_2026-05.csv")
OUT = Path("docs/sugar_rolling_floor_2026-05.md")
ROLLING_YEARS = 5
MIN_HIT_RATE = 0.55
MIN_SAMPLES = 30


def find_floor_for_target_hit_rate(
    df: pd.DataFrame,
    hit_col: str,
    target_hr: float = 0.55,
    min_n: int = 30,
) -> float | None:
    """Returner laveste score-terskel der hit-rate ≥ target_hr og n ≥ min_n."""
    if df.empty:
        return None
    candidates: list[tuple[float, float, int]] = []
    for thresh in sorted(set(df["score"].round(2).tolist()), reverse=True):
        sub = df[df["score"] >= thresh]
        if len(sub) < min_n:
            continue
        hr = float(sub[hit_col].mean())
        candidates.append((float(thresh), hr, len(sub)))
    valid = [c for c in candidates if c[1] >= target_hr]
    if not valid:
        return None
    return min(valid, key=lambda c: c[0])[0]


def main() -> int:
    df = pd.read_csv(ATTR_CSV, parse_dates=["ref_date"])

    # For SELL er hit = forward_return ≤ -3% (markedet falt ≥ 3%)
    # I attribution-CSV er hit allerede beregnet med threshold +3% for BUY.
    # Vi flipper for SELL: hit = forward_return < -3%
    df["sell_hit"] = df["forward_return_pct"] <= -3.0

    lines: list[str] = []
    lines.append("# Sugar rullerende publish-floor (5-års vindu)\n")
    lines.append(
        "*Analytiker-anbefaling B (peer-review 2026-05): bytt fra statisk "
        f"14-års-floor til rullerende 5-års vindu, oppdatert kvartalsvis.*\n"
    )
    lines.append(
        f"**Kriterium:** laveste score-terskel der SELL hit-rate ≥ "
        f"{MIN_HIT_RATE*100:.0f}% (forward_return ≤ -3%) og n ≥ {MIN_SAMPLES}.\n"
    )
    lines.append(
        f"**Datasett:** {len(df)} SELL-signaler h=180d, "
        f"{df['ref_date'].min().date()} → {df['ref_date'].max().date()}.\n"
    )

    # Statisk floor (sukker har sell=5)
    static_floor = 5.0
    static_sub = df[df["score"] >= static_floor]
    static_hr = static_sub["sell_hit"].mean()
    static_avg = static_sub["forward_return_pct"].mean()
    lines.append("## 1. Statisk floor (nåværende = 5)\n")
    lines.append(f"- n = {len(static_sub)}")
    lines.append(f"- hit-rate (return ≤ -3%): {static_hr*100:.1f}%")
    lines.append(f"- avg forward_return: {static_avg:+.2f}%")
    lines.append("")

    # Rullerende floor — quarterly snapshots
    lines.append(f"## 2. Rullerende {ROLLING_YEARS}-års floor (kvartalsvis re-kalibrering)\n")
    lines.append("| Snapshot | Lookback | Floor | n | hit-rate | avg_return |")
    lines.append("|---|---|---:|---:|---:|---:|")

    snapshots: list[tuple[pd.Timestamp, float | None, int, float, float]] = []
    start = df["ref_date"].min() + pd.DateOffset(years=ROLLING_YEARS)
    end = df["ref_date"].max()
    cur = start
    while cur <= end:
        lookback_start = cur - pd.DateOffset(years=ROLLING_YEARS)
        sub = df[(df["ref_date"] >= lookback_start) & (df["ref_date"] < cur)]
        if len(sub) < MIN_SAMPLES:
            cur += pd.DateOffset(months=3)
            continue
        floor = find_floor_for_target_hit_rate(sub, "sell_hit", MIN_HIT_RATE, MIN_SAMPLES)
        if floor is not None:
            valid = sub[sub["score"] >= floor]
            hr = valid["sell_hit"].mean() if len(valid) > 0 else 0
            avg = valid["forward_return_pct"].mean() if len(valid) > 0 else 0
            snapshots.append((cur, floor, len(valid), hr, avg))
            lines.append(
                f"| {cur.date()} | {lookback_start.date()}..{cur.date()} | "
                f"{floor:.2f} | {len(valid)} | {hr*100:.1f}% | {avg:+.2f}% |"
            )
        else:
            lines.append(
                f"| {cur.date()} | {lookback_start.date()}..{cur.date()} | "
                f"— | — | n/a (ingen score-grense oppnår {MIN_HIT_RATE*100:.0f}% hr) | — |"
            )
            snapshots.append((cur, None, 0, 0, 0))
        cur += pd.DateOffset(months=3)
    lines.append("")

    # Statistikk på rolling floors
    valid_floors = [s[1] for s in snapshots if s[1] is not None]
    if valid_floors:
        lines.append("## 3. Rolling-floor stabilitet\n")
        lines.append(f"- Antall snapshots med valid floor: {len(valid_floors)} av {len(snapshots)}")
        lines.append(f"- Min: {min(valid_floors):.2f}")
        lines.append(f"- Max: {max(valid_floors):.2f}")
        lines.append(f"- Median: {sorted(valid_floors)[len(valid_floors)//2]:.2f}")
        lines.append(f"- Std: {(sum((f - sum(valid_floors)/len(valid_floors))**2 for f in valid_floors)/len(valid_floors))**0.5:.2f}")
        lines.append("")
        lines.append("**Tolkning:**")
        spread = max(valid_floors) - min(valid_floors)
        if spread > 2.0:
            lines.append(f"- Floor-spread {spread:.2f} > 2.0 → regime-shifts er reelle, statisk floor=5 er upassende")
        else:
            lines.append(f"- Floor-spread {spread:.2f} ≤ 2.0 → statisk floor er nær-optimal")
        lines.append("")

    # ------------------------------------------------------------------
    # Seksjon 4: 2023 OOS-test (India-forbud-regime)
    # ------------------------------------------------------------------
    lines.append("## 4. 2023 OOS-test (India-eksportforbud-regime)\n")
    oos_2023 = df[(df["ref_date"] >= "2023-01-01") & (df["ref_date"] < "2024-01-01")]
    lines.append(f"- Total SELL-signaler 2023: {len(oos_2023)}")
    lines.append("")
    lines.append("| Floor | n publisert | hit-rate | avg return | Tap blokkert |")
    lines.append("|---:|---:|---:|---:|---:|")
    for f in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]:
        sub = oos_2023[oos_2023["score"] >= f]
        if sub.empty:
            lines.append(f"| {f:.1f} | 0 | — | — | — |")
            continue
        hr = sub["sell_hit"].mean()
        avg = sub["forward_return_pct"].mean()
        lines.append(f"| {f:.1f} | {len(sub)} | {hr*100:.1f}% | {avg:+.2f}% | n/a |")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Skrevet {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
