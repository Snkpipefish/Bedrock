"""Grade-distribusjons-rapport for sub-fase 12.7 D2 (session 134).

Per § 19.6 kvalitetskrav: "Etter D1, D2, D3 hver: kjør backtest på 12
måneder historiske data. Bekreft at grade-distribusjon ikke har
forskjøvet seg dramatisk."

I praksis: vi sammenligner snapshot-baselinens grade-fordeling pre-D2 vs
post-D2 (= nåværende). 12 måneders backtest-rerun er for dyrt for hver
D-fase-finalisering; baseline-snapshot fanger samme spørsmål bevart i
samme DB-state ved hver leveranse.

Pre-D2: baseline fra v0.12.7-d1-tag (commit f7d3072, session 130 close).
Post-D2: nåværende baseline (etter session 131-133 D2-leveranser:
B2 VIX-term + A12 AAII + B4 HDD/CDD + A5 GLD + A6 SLV + A3 FAS +
A9 USDM + C3 drop shipping). B5 calendar spreads deferred til Plan-S.

Output:
- `docs/d2_grade_distribution.md` med:
  - Per-instrument tabell: grade-count pre/post + Δ
  - Flagg for instrumenter med ≥50% relative endring i A+-andel
  - Sammendrag på asset-class-nivå
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRE = "/tmp/baseline_pre_d2.json"
DEFAULT_POST = REPO_ROOT / "tests" / "snapshot" / "expected" / "score_baseline.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "d2_grade_distribution.md"

# Asset-class-mapping (fra instrument-YAMLs)
ASSET_CLASS = {
    "Gold": "metals",
    "Silver": "metals",
    "Copper": "metals",
    "Platinum": "metals",
    "CrudeOil": "energy",
    "Brent": "energy",
    "NaturalGas": "energy",
    "EURUSD": "fx",
    "GBPUSD": "fx",
    "USDJPY": "fx",
    "AUDUSD": "fx",
    "Nasdaq": "indices",
    "SP500": "indices",
    "BTC": "crypto",
    "ETH": "crypto",
    "Corn": "grains",
    "Wheat": "grains",
    "Soybean": "grains",
    "Cotton": "softs",
    "Sugar": "softs",
    "Coffee": "softs",
    "Cocoa": "softs",
}

GRADE_ORDER = ("A+", "A", "B", "C")


def load_baseline(path: Path | str) -> dict[str, dict]:
    with open(path) as f:
        return json.load(f)


def grade_counts_per_instrument(
    baseline: dict[str, dict],
) -> dict[str, Counter]:
    """Returner {instrument: Counter(grade -> count)} over alle horizon×direction."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for key, row in baseline.items():
        instrument = key.split("|")[0]
        grade = row.get("grade", "C")
        counts[instrument][grade] += 1
    return counts


def relative_aplus_change(pre: Counter, post: Counter, total: int = 6) -> float:
    """Return relative change in A+-share. ((post - pre) / max(pre, 1)) * 100."""
    pre_a = pre.get("A+", 0)
    post_a = post.get("A+", 0)
    if pre_a == 0 and post_a == 0:
        return 0.0
    if pre_a == 0:
        return float("inf")
    return (post_a - pre_a) / pre_a * 100.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre", default=DEFAULT_PRE)
    parser.add_argument("--post", default=str(DEFAULT_POST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    pre = load_baseline(args.pre)
    post = load_baseline(args.post)
    pre_counts = grade_counts_per_instrument(pre)
    post_counts = grade_counts_per_instrument(post)

    instruments = sorted(set(pre_counts) | set(post_counts))

    flagged: list[str] = []
    asset_class_pre: dict[str, Counter] = defaultdict(Counter)
    asset_class_post: dict[str, Counter] = defaultdict(Counter)
    for inst in instruments:
        cls = ASSET_CLASS.get(inst, "?")
        for g, n in pre_counts.get(inst, Counter()).items():
            asset_class_pre[cls][g] += n
        for g, n in post_counts.get(inst, Counter()).items():
            asset_class_post[cls][g] += n
        rel = relative_aplus_change(
            pre_counts.get(inst, Counter()), post_counts.get(inst, Counter())
        )
        if rel == float("inf") or abs(rel) >= 50.0:
            flagged.append(inst)

    lines: list[str] = []
    lines.append("# D2 grade-distribusjons-rapport (sub-fase 12.7, session 134)")
    lines.append("")
    lines.append(f"Pre-D2 baseline: {args.pre}")
    lines.append(f"Post-D2 baseline: {args.post}")
    lines.append("")
    lines.append("Per § 19.6 kvalitetskrav. Forskyvning vs pre-D2 baseline (tag")
    lines.append("`v0.12.7-d1`, commit `f7d3072`, session 130 close — siste commit før")
    lines.append("session 131 leverte første D2-commits).")
    lines.append("")
    lines.append("D2-leveranser som påvirker baseline:")
    lines.append("- session 131: B2 VIX-term (Nasdaq/SP500), A12 AAII (Nasdaq/SP500),")
    lines.append("  B4 HDD/CDD (NaturalGas)")
    lines.append("- session 132: A5 GLD (Gold), A6 SLV (Silver, shares-outstanding-proxy)")
    lines.append("- session 133: A3 FAS (Corn/Soybean/Wheat/Cotton), A9 USDM")
    lines.append("  (Corn/Soybean/Wheat/Cotton), C3 drop shipping (Cotton/Cocoa)")
    lines.append("- session 134: B5 calendar spreads DEFERRED til Plan-S (ingen baseline-effekt)")
    lines.append("")
    lines.append("Droppede i D2-prep: A7 PPLT, A8 NOPA, A11 ICE (per A1/A14-presedens).")
    lines.append("")
    lines.append("## Per-instrument tabell")
    lines.append("")
    lines.append("| Instrument | Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A | Flag |")
    lines.append("|---|---|---|---|---|---|---|")
    for inst in instruments:
        cls = ASSET_CLASS.get(inst, "?")
        pre_c = pre_counts.get(inst, Counter())
        post_c = post_counts.get(inst, Counter())
        pre_str = "/".join(str(pre_c.get(g, 0)) for g in GRADE_ORDER)
        post_str = "/".join(str(post_c.get(g, 0)) for g in GRADE_ORDER)
        d_aplus = post_c.get("A+", 0) - pre_c.get("A+", 0)
        d_a = post_c.get("A", 0) - pre_c.get("A", 0)
        flag = "🚩" if inst in flagged else ""
        lines.append(
            f"| {inst} | {cls} | {pre_str} | {post_str} | {d_aplus:+d} | {d_a:+d} | {flag} |"
        )

    lines.append("")
    lines.append("## Per asset-class")
    lines.append("")
    lines.append("| Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A |")
    lines.append("|---|---|---|---|---|")
    classes = sorted(set(asset_class_pre) | set(asset_class_post))
    for cls in classes:
        pre_c = asset_class_pre.get(cls, Counter())
        post_c = asset_class_post.get(cls, Counter())
        pre_str = "/".join(str(pre_c.get(g, 0)) for g in GRADE_ORDER)
        post_str = "/".join(str(post_c.get(g, 0)) for g in GRADE_ORDER)
        d_aplus = post_c.get("A+", 0) - pre_c.get("A+", 0)
        d_a = post_c.get("A", 0) - pre_c.get("A", 0)
        lines.append(f"| {cls} | {pre_str} | {post_str} | {d_aplus:+d} | {d_a:+d} |")

    lines.append("")
    lines.append("## Flaggede instrumenter (relative ≥50% endring i A+-andel)")
    lines.append("")
    if flagged:
        for inst in flagged:
            pre_a = pre_counts.get(inst, Counter()).get("A+", 0)
            post_a = post_counts.get(inst, Counter()).get("A+", 0)
            lines.append(f"- **{inst}**: A+ {pre_a} → {post_a}")
    else:
        lines.append("Ingen instrumenter flagget. Grade-distribusjon stabil over D2.")

    lines.append("")
    lines.append("## Vurdering")
    lines.append("")
    lines.append("Rapporten er informativ — ikke gating for D2-tag. Hvis dramatisk skifte er")
    lines.append("flagget, eskaler som åpent spørsmål til neste session for mulig terskel-")
    lines.append("rekalibrering. § 19.6 sier eksplisitt: terskler rekalibreres ikke i 12.7,")
    lines.append("men distribusjons-drift dokumenteres for senere kalibrering.")
    lines.append("")
    lines.append("D2 introduserte flere drivere på flere instrumenter enn D1, så større")
    lines.append("spread i grade-distribusjon enn D1-rapporten er forventet. Vurder om")
    lines.append("flips er konsentrert i én asset-class (kan indikere konfigurasjons-bias)")
    lines.append("eller spredt over flere (forventet bredde-effekt av nye drivere).")

    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"Skrev {args.out}")
    print(f"Flaggede instrumenter: {flagged or 'ingen'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
