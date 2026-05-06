"""Score-distribusjon-analyse for å kalibrere sugar grade_thresholds.

Punkt C.4 fra analytiker-peer-review: A+ BUY har n=10-13 (h=180-270d) som
er under analytikerens n>=30-krav. Senke A+ min_score fra 11 til ~9-10 for
å trekke flere signaler inn i bøtta uten å miste hit-rate-edge.

Strategi:
1. Kjør orchestrator-replay for h=180 + h=270 BUY (sweet spots fra v6)
2. Dump (ref_date, score, hit, return) per signal til CSV
3. Beregn hit-rate + avg-return per score-bøtte (5.0-5.5, ..., 11.0+)
4. Anbefal cutoff der hit-rate >=65% og n>=30

Kjør:
    PYTHONPATH=src python scripts/sugar_grade_calibration.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from bedrock.backtest import BacktestConfig, run_orchestrator_replay
from bedrock.data.store import DataStore

DB_PATH = Path("/home/pc/bedrock/data/bedrock.db")
OUT_CSV = Path("docs/sugar_grade_score_dump_2026-05.csv")
OUT_MD = Path("docs/sugar_grade_calibration_2026-05.md")
INSTRUMENTS_DIR = Path("config/instruments")
HORIZONS = [180, 270]
STEP_DAYS = 7
YEARS_BACK = 14


def _bucket(score: float) -> str:
    """Score-bøtte 0.5-bredde: 5.0-5.5 osv."""
    lo = round(score * 2) / 2
    if lo > score:
        lo -= 0.5
    return f"{lo:.1f}-{lo + 0.5:.1f}"


def main() -> int:
    today = date.today()
    from_date = today - timedelta(days=365 * YEARS_BACK)
    store = DataStore(DB_PATH)

    rows: list[dict[str, str | float | bool | int]] = []
    for h in HORIZONS:
        cfg = BacktestConfig(
            instrument="Sugar",
            horizon_days=h,
            from_date=from_date,
            to_date=today,
        )
        print(f"[h={h}d] kjører orchestrator-replay (BUY)...", flush=True)
        result = run_orchestrator_replay(
            store,
            cfg,
            instruments_dir=str(INSTRUMENTS_DIR),
            direction="buy",
            step_days=STEP_DAYS,
        )
        for s in result.signals:
            if s.score is None:
                continue
            rows.append(
                {
                    "horizon_days": h,
                    "ref_date": s.ref_date.isoformat(),
                    "score": float(s.score),
                    "grade": s.grade or "",
                    "published": bool(s.published) if s.published is not None else False,
                    "hit": bool(s.hit),
                    "forward_return_pct": float(s.forward_return_pct),
                }
            )
        print(f"[h={h}d] {len(result.signals)} signaler dumped.", flush=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "horizon_days",
                "ref_date",
                "score",
                "grade",
                "published",
                "hit",
                "forward_return_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV skrevet: {OUT_CSV} ({len(rows)} rader)")

    md_sections: list[str] = []
    md_sections.append("# Sugar grade-cutoff-kalibrering (sub-fase 12.11+ punkt C.4)\n")
    md_sections.append(
        f"*Generert {today} via `scripts/sugar_grade_calibration.py`. "
        f"Vindu: {from_date} → {today} ({YEARS_BACK} år). Direction=BUY.*\n"
    )
    md_sections.append(
        "**Mål:** finne cutoff for `grade_thresholds.A_plus.min_score` "
        "der A+ BUY får n>=30 (analytiker-krav) men beholder hit-rate >=65%. "
        "Nåværende cutoff=11 gir n=10-13 (under n>=30).\n"
    )
    md_sections.append("---\n")

    for h in HORIZONS:
        h_rows = [r for r in rows if r["horizon_days"] == h]
        md_sections.append(f"## Sugar h={h}d BUY — kumulativ A+ ved senket cutoff\n")
        md_sections.append(
            "| Cutoff (>=score) | n | hit-rate | avg return | "
            "median return | min | max |\n"
            "|---:|---:|---:|---:|---:|---:|---:|\n"
        )
        for cutoff in [11.0, 10.5, 10.0, 9.5, 9.0, 8.5, 8.0]:
            subset = [r for r in h_rows if float(r["score"]) >= cutoff]
            if not subset:
                continue
            hits = sum(1 for r in subset if r["hit"])
            returns = sorted(float(r["forward_return_pct"]) for r in subset)
            n = len(subset)
            avg = sum(returns) / n
            median = (
                returns[n // 2]
                if n % 2 == 1
                else (returns[n // 2 - 1] + returns[n // 2]) / 2
            )
            md_sections.append(
                f"| >={cutoff:.1f} | {n} | {hits / n * 100:.1f}% | "
                f"{avg:+.2f}% | {median:+.2f}% | {returns[0]:+.2f}% | {returns[-1]:+.2f}% |\n"
            )
        md_sections.append("\n")

        md_sections.append(f"### Score-distribusjon per 0.5-bøtte (h={h}d BUY)\n")
        bucket_stats: dict[str, dict[str, float]] = {}
        for r in h_rows:
            b = _bucket(float(r["score"]))
            stat = bucket_stats.setdefault(b, {"n": 0, "hits": 0, "ret_sum": 0.0})
            stat["n"] += 1
            if r["hit"]:
                stat["hits"] += 1
            stat["ret_sum"] += float(r["forward_return_pct"])
        md_sections.append(
            "| Bøtte | n | hit-rate | avg return |\n"
            "|---|---:|---:|---:|\n"
        )
        for b in sorted(bucket_stats.keys(), key=lambda x: float(x.split("-")[0])):
            st = bucket_stats[b]
            n_b = int(st["n"])
            md_sections.append(
                f"| {b} | {n_b} | {st['hits'] / n_b * 100:.1f}% | "
                f"{st['ret_sum'] / n_b:+.2f}% |\n"
            )
        md_sections.append("\n")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("".join(md_sections), encoding="utf-8")
    print(f"Markdown skrevet: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
