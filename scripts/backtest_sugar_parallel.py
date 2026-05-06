"""Parallell-versjon av backtest_sugar_full.py — bruker N kjerner.

Designet for codespace (4 kjerner). Hver (horizon, direction)-kombinasjon
kjører i sin egen prosess. 8 jobber over 4 kjerner ≈ 2x speedup vs sekvensiell.

Bruk:
    PYTHONPATH=src python scripts/backtest_sugar_parallel.py \\
        --db data/bedrock.db \\
        --out docs/backtest_sugar_v7_full_2026-05.md \\
        --workers 4
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path("data/bedrock.db")
OUT_PATH = Path("docs/backtest_sugar_v7_full_2026-05.md")
INSTRUMENTS_DIR = Path("config/instruments")
STEP_DAYS = 7
HORIZONS = [90, 180, 270, 365]
DIRECTIONS = ["buy", "sell"]


def _run_section(args: tuple[int, str, date, date, str, str]) -> tuple[int, str, str, float]:
    """Worker: kjør én (horizon, direction)-replay og returner markdown-blokk."""
    horizon_days, direction, from_date, to_date, db_path, instruments_dir = args

    # Late import for å unngå pickle-problemer i workers.
    from bedrock.backtest import (
        BacktestConfig,
        format_markdown,
        run_orchestrator_replay,
        summary_stats,
    )
    from bedrock.data.store import DataStore

    store = DataStore(Path(db_path))
    cfg = BacktestConfig(
        instrument="Sugar",
        horizon_days=horizon_days,
        from_date=from_date,
        to_date=to_date,
    )
    t0 = time.time()
    result = run_orchestrator_replay(
        store,
        cfg,
        instruments_dir=instruments_dir,
        direction=direction,
        step_days=STEP_DAYS,
    )
    elapsed = time.time() - t0
    report = summary_stats(result)
    body = format_markdown(result, report)
    section = (
        f"## Sugar · h={horizon_days}d · direction={direction}\n\n"
        f"*Wall-time: {elapsed:.1f}s · {len(result.signals)} signaler · "
        f"step_days={STEP_DAYS} · vindu: {from_date} → {to_date}*\n\n"
        f"{body}\n"
    )
    return horizon_days, direction, section, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=14)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--instruments-dir", default=str(INSTRUMENTS_DIR))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    today = date.today()
    from_date = today - timedelta(days=365 * args.years)

    jobs = [
        (h, d, from_date, today, args.db, args.instruments_dir)
        for d in DIRECTIONS
        for h in HORIZONS
    ]

    sections: dict[tuple[int, str], str] = {}
    total_t0 = time.time()
    print(f"=== Spawning {len(jobs)} jobs over {args.workers} workers ===", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_run_section, job): (job[0], job[1]) for job in jobs}
        for fut in as_completed(futures):
            h, d = futures[fut]
            try:
                horizon, direction, section, elapsed = fut.result()
                sections[(horizon, direction)] = section
                print(
                    f"[{time.strftime('%H:%M:%S')}] DONE h={horizon}d {direction} "
                    f"({elapsed:.0f}s, {len(sections)}/{len(jobs)})",
                    flush=True,
                )
            except Exception as exc:
                print(f"FAIL h={h}d {d}: {exc}", flush=True)

    total_elapsed = time.time() - total_t0
    print(f"\nTotal wall-time: {total_elapsed/60:.1f} min", flush=True)

    out_lines: list[str] = []
    out_lines.append("# Sugar full-historikk-backtest v7 (sub-fase 12.11+)\n")
    out_lines.append(
        f"*Generert {today} via `scripts/backtest_sugar_parallel.py` "
        f"(workers={args.workers}). Vindu: {from_date} → {today} ({args.years} år).*\n"
    )
    out_lines.append(
        "**Hva validerer:** A_plus.min_score=10 (senket fra 11 per analytiker C.4). "
        "Forventet: A+ BUY n>=30 og hit-rate >=65% på sweet-spot-horisonter "
        "(h=180d / h=270d).\n"
    )
    out_lines.append("---\n")
    for d in DIRECTIONS:
        for h in HORIZONS:
            section = sections.get((h, d), f"## Sugar · h={h}d · direction={d}\n\nFAILED.\n")
            out_lines.append(section)
    out_lines.append(f"---\n\n*Total wall-time: {total_elapsed/60:.1f} min "
                     f"(workers={args.workers})*\n")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\nFerdig. Rapport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
