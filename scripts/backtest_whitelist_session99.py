"""Session 99: Backtest-validering av 17 whitelist-instrumenter.

Aggregerer på `analog_outcomes`-tabellen (forward_return + max_drawdown)
for hver (instrument, horizon, direction). Rapporterer:

- Antall rader (data-coverage)
- Hit-rate: andel der forward_return >= +X% (BUY) eller ≤ -X% (SELL)
- Avg return + median return
- Max drawdown (avg + worst-case)
- Direksjonell asymmetri: er BUY-distribusjonen meningsfullt forskjellig
  fra SELL?

Output: docs/backtest_whitelist_2026-04-26.md.

Threshold per horisont (matcher analog-driver default):
- 30d: ±3.0% (samme som outcome_threshold_pct)
- 90d: ±5.0%

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backtest_whitelist_session99.py
"""
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

WHITELIST = [
    # FX
    "EURUSD",
    "USDJPY",
    "GBPUSD",
    "AUDUSD",
    # Metals
    "Gold",
    "Silver",
    # Energy
    "CrudeOil",
    "Brent",
    # Indices
    "SP500",
    "Nasdaq",
    # Grains
    "Corn",
    "Wheat",
    "Soybean",
    # Softs
    "Coffee",
    "Cotton",
    "Sugar",
    "Cocoa",
]

THRESHOLDS = {
    30: 3.0,
    90: 5.0,
}

DB = Path("data/bedrock.db")
OUT = Path("docs/backtest_whitelist_2026-04-26.md")


def fetch_returns(con, instrument: str, horizon: int) -> list[tuple[float, float | None]]:
    rows = con.execute(
        "SELECT forward_return_pct, max_drawdown_pct FROM analog_outcomes "
        "WHERE instrument=? AND horizon_days=? "
        "ORDER BY ref_date ASC",
        (instrument, horizon),
    ).fetchall()
    return [(r[0], r[1]) for r in rows if r[0] is not None]


def stats_for_direction(
    returns: list[float], drawdowns: list[float], threshold_pct: float, direction: str
) -> dict:
    if not returns:
        return {"n": 0}
    if direction == "BUY":
        hits = sum(1 for r in returns if r >= threshold_pct)
    else:  # SELL
        hits = sum(1 for r in returns if r <= -threshold_pct)
    n = len(returns)
    out = {
        "n": n,
        "hit_rate_pct": (hits / n) * 100.0,
        "avg_return_pct": statistics.mean(returns),
        "median_return_pct": statistics.median(returns),
        "stdev_return_pct": statistics.stdev(returns) if n > 1 else 0.0,
    }
    if drawdowns:
        out["avg_drawdown_pct"] = statistics.mean(drawdowns)
        out["worst_drawdown_pct"] = min(drawdowns)  # mest negativ
    return out


def render_table(rows: list[dict]) -> str:
    """Render én tabell-blokk med rows = list of dicts."""
    if not rows:
        return "_(ingen data)_\n"
    lines = []
    lines.append(
        "| Instrument | n | BUY hit-rate | SELL hit-rate | Avg return | Stdev | Avg DD | Worst DD |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r['instrument']:12s} "
            f"| {r['n']:5d} "
            f"| {r['buy_hit']:5.1f}% "
            f"| {r['sell_hit']:5.1f}% "
            f"| {r['avg_return']:+5.2f}% "
            f"| {r['stdev']:5.2f}% "
            f"| {r['avg_dd'] if r['avg_dd'] is not None else 'n/a':>5} "
            f"| {r['worst_dd'] if r['worst_dd'] is not None else 'n/a':>5} |"
        )
    return "\n".join(lines) + "\n"


def fmt_pct_or_na(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+5.2f}%"


def main() -> None:
    con = sqlite3.connect(DB)

    sections: dict[int, list[dict]] = {}
    for horizon in sorted(THRESHOLDS.keys()):
        threshold = THRESHOLDS[horizon]
        rows: list[dict] = []
        for inst in WHITELIST:
            data = fetch_returns(con, inst, horizon)
            if not data:
                rows.append(
                    {
                        "instrument": inst,
                        "n": 0,
                        "buy_hit": 0.0,
                        "sell_hit": 0.0,
                        "avg_return": 0.0,
                        "stdev": 0.0,
                        "avg_dd": None,
                        "worst_dd": None,
                    }
                )
                continue
            returns = [r for r, _ in data]
            drawdowns = [dd for _, dd in data if dd is not None]
            buy = stats_for_direction(returns, drawdowns, threshold, "BUY")
            sell = stats_for_direction(returns, drawdowns, threshold, "SELL")
            rows.append(
                {
                    "instrument": inst,
                    "n": buy["n"],
                    "buy_hit": buy["hit_rate_pct"],
                    "sell_hit": sell["hit_rate_pct"],
                    "avg_return": buy["avg_return_pct"],
                    "stdev": buy["stdev_return_pct"],
                    "avg_dd": fmt_pct_or_na(buy.get("avg_drawdown_pct")),
                    "worst_dd": fmt_pct_or_na(buy.get("worst_drawdown_pct")),
                }
            )
        sections[horizon] = rows

    # Render
    lines: list[str] = [
        "# Backtest-validering: 17 whitelist-instrumenter",
        "",
        "Dato: 2026-04-26 (session 99). Kilde: `analog_outcomes`-tabellen ",
        "(2010-01-04 .. 2026-03-12 for 30d, .. 2025-12-12 for 90d).",
        "",
        "Hit-rate måler andel av historiske dager der forward-return krysser ",
        "absolutt-tersklen (BUY: ≥ +X%; SELL: ≤ -X%). Threshold matcher ",
        "`analog`-driverens `outcome_threshold_pct`-default.",
        "",
        "| Horisont | Threshold |",
        "|---|---|",
        "| 30d | ±3.0% |",
        "| 90d | ±5.0% |",
        "",
    ]

    for horizon in sorted(THRESHOLDS.keys()):
        threshold = THRESHOLDS[horizon]
        lines.append(f"## Horisont {horizon}d (terskel ±{threshold:.1f}%)")
        lines.append("")
        lines.append(render_table(sections[horizon]))
        lines.append("")

    # Asymmetri-analyse
    lines.append("## Direksjonell asymmetri")
    lines.append("")
    lines.append(
        "Forskjellen mellom BUY og SELL hit-rate forteller om instrumentet "
        "er strukturelt biased opp eller ned i hold-perioden. Hvis BUY-hit-rate "
        "er høyere enn SELL-hit-rate, har instrumentet hatt netto upside "
        "(passende for BUY-først-strategi). Symmetri er nær 50/50."
    )
    lines.append("")
    lines.append("| Instrument | 30d BUY-SELL | 90d BUY-SELL | Tolkning |")
    lines.append("|---|---:|---:|---|")
    for inst in WHITELIST:
        diff_30 = next(
            (r["buy_hit"] - r["sell_hit"] for r in sections[30] if r["instrument"] == inst),
            0.0,
        )
        diff_90 = next(
            (r["buy_hit"] - r["sell_hit"] for r in sections[90] if r["instrument"] == inst),
            0.0,
        )
        if abs(diff_30) < 5 and abs(diff_90) < 5:
            tolkning = "symmetrisk"
        elif diff_30 > 5 and diff_90 > 5:
            tolkning = "**BUY-bias**"
        elif diff_30 < -5 and diff_90 < -5:
            tolkning = "**SELL-bias**"
        else:
            tolkning = "blandet"
        lines.append(f"| {inst:12s} | {diff_30:+5.1f}pp | {diff_90:+5.1f}pp | {tolkning} |")
    lines.append("")

    # Score-fordelinger fra ekte signals.json (publish-ratio + grade)
    lines.append("## Live signals-distribusjon (fra signals.json + signals_bot.json)")
    lines.append("")
    import json

    sig_data = json.loads(Path("data/signals.json").read_text())
    agri_data = json.loads(Path("data/agri_signals.json").read_text())
    bot_data = json.loads(Path("data/signals_bot.json").read_text())

    def get_entries(data):
        return data if isinstance(data, list) else data.get("entries", [])

    all_entries = get_entries(sig_data) + get_entries(agri_data)
    bot_entries = get_entries(bot_data)
    by_inst: dict[str, dict] = {}
    for e in all_entries:
        inst = e["instrument"]
        if inst not in WHITELIST:
            continue
        by_inst.setdefault(
            inst,
            {"total": 0, "published": 0, "grades": {}, "by_dir": {"buy": 0, "sell": 0}},
        )
        by_inst[inst]["total"] += 1
        if e.get("published"):
            by_inst[inst]["published"] += 1
        g = e.get("grade", "?")
        by_inst[inst]["grades"][g] = by_inst[inst]["grades"].get(g, 0) + 1
        d = e.get("direction", "?")
        by_inst[inst]["by_dir"][d] = by_inst[inst]["by_dir"].get(d, 0) + 1

    lines.append("| Instrument | Total | Published | Grades | Bot-published |")
    lines.append("|---|---:|---:|---|---|")
    for inst in WHITELIST:
        bi = by_inst.get(inst, {})
        if not bi:
            lines.append(f"| {inst:12s} | 0 | 0 | – | – |")
            continue
        grades = ", ".join(f"{g}:{n}" for g, n in sorted(bi["grades"].items()))
        bot_pub = sum(
            1
            for e in bot_entries
            if e.get("instrument", "").lower() == inst.lower() and e.get("published")
        )
        lines.append(f"| {inst:12s} | {bi['total']} | {bi['published']} | {grades} | {bot_pub} |")
    lines.append("")

    # Sammendrag
    lines.append("## Sammendrag")
    lines.append("")
    lines.append("**Cutover-evaluering (PLAN § 12.3):**")
    lines.append("")
    # Identifiser rare distribusjoner
    flagged = []
    for r in sections[30]:
        if r["n"] < 1000:
            flagged.append(f"- {r['instrument']}: lite data ({r['n']} rader 30d)")
        if r["stdev"] > 15:
            flagged.append(f"- {r['instrument']}: høy stdev ({r['stdev']:.1f}%) — exotisk")
        if abs(r["buy_hit"] - r["sell_hit"]) > 15:
            flagged.append(
                f"- {r['instrument']}: sterk asymmetri "
                f"(BUY {r['buy_hit']:.1f}% vs SELL {r['sell_hit']:.1f}%) "
                f"— mulig structural bias"
            )
    if flagged:
        lines.append("**Flagg for review før cutover:**")
        lines.append("")
        for f in flagged:
            lines.append(f)
    else:
        lines.append(
            "Alle 17 instrumenter har akseptable data-kvaliteter (>1000 obs, "
            "stdev < 15%, BUY/SELL-asymmetri < 15pp)."
        )
    lines.append("")
    lines.append(
        "**Anbefaling:** instrumenter med sterk strukturell bias bør vurderes "
        "for direction-spesifikk publish-floor-justering, eller fjernes fra "
        "whitelist hvis bias er pga thin data."
    )

    OUT.write_text("\n".join(lines))
    print(f"Skrevet: {OUT}")
    print(f"Sections: {list(sections.keys())}")
    for h, rows in sections.items():
        print(f"  {h}d: {len(rows)} instrumenter")


if __name__ == "__main__":
    main()
