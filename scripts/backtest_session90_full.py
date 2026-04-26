"""Full system-validering — backtest 5 instrumenter × 2 horisonter (session 90).

Kjører run_orchestrator_replay for å validere at scoring-systemet med
alle nye drivere (WASDE, BDI, disease, eksport-events, BRL, real_yield,
DXY, VIX, ENSO, weather, seasonal, positioning, COT, analog) gir
edge på historisk data.

Output: docs/backtest_session90_full.md.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from bedrock.backtest import (
    BacktestConfig,
    format_markdown,
    run_orchestrator_replay,
    summary_stats,
)
from bedrock.data.store import DataStore

DB_PATH = Path("data/bedrock.db")
OUT_PATH = Path("docs/backtest_session90_full.md")
INSTRUMENTS_DIR = Path("config/instruments")

# Vindu: 12 mnd. Step_days=14 = annenhver uke (raskere, 26 ref_dates)
WINDOW_DAYS = 365
STEP_DAYS = 14


def main() -> None:
    store = DataStore(DB_PATH)
    end_date = date.today()
    start_date = end_date - timedelta(days=WINDOW_DAYS)

    parts: list[str] = []
    parts.append("# Backtest — full system-validering (session 90)\n")
    parts.append(f"*Generert {date.today().isoformat()}.*\n")
    parts.append(f"Vindu: {start_date} .. {end_date}, step_days={STEP_DAYS}\n")
    parts.append("Instrumenter: 5 (Corn, Wheat, Cotton, Soybean, Gold)\n")
    parts.append("Horisonter: 30d, 90d\n")
    parts.append("Direction: buy\n\n")
    parts.append("---\n\n")

    total_start = time.time()
    summary_lines: list[str] = []

    for instrument in ["Corn", "Wheat", "Cotton", "Soybean", "Gold"]:
        for horizon_days in [30, 90]:
            config = BacktestConfig(
                instrument=instrument,
                horizon_days=horizon_days,
                from_date=start_date,
                to_date=end_date,
                outcome_threshold_pct=3.0,
            )
            t0 = time.time()
            try:
                result = run_orchestrator_replay(
                    store,
                    config,
                    instruments_dir=INSTRUMENTS_DIR,
                    direction="buy",
                    step_days=STEP_DAYS,
                )
                stats = summary_stats(result)
                wall_time = time.time() - t0
                parts.append(f"## {instrument} · h={horizon_days}d · direction=buy\n\n")
                parts.append(f"*Wall-time: {wall_time:.1f}s · {len(result.signals)} signaler*\n\n")
                parts.append(format_markdown(result, stats))
                parts.append("\n\n---\n\n")

                # Per-grade-summary for sammendrag
                grade_lines = []
                for g in ["A+", "A", "B", "C"]:
                    sub = [s for s in result.signals if s.grade == g]
                    if sub:
                        hits = sum(1 for s in sub if s.hit)
                        grade_lines.append(f"  {g}: n={len(sub)} hit={hits / len(sub) * 100:.0f}%")
                summary_lines.append(f"{instrument} h={horizon_days}d: " + " | ".join(grade_lines))
            except Exception as exc:
                parts.append(f"## {instrument} · h={horizon_days}d — ERROR\n\n")
                parts.append(f"```\n{exc}\n```\n\n---\n\n")
                summary_lines.append(f"{instrument} h={horizon_days}d: ERROR {exc}")

    total_wall = time.time() - total_start
    parts.append("\n## Sammendrag\n\n")
    for line in summary_lines:
        parts.append(f"- {line}\n")
    parts.append(f"\n*Total wall-time: {total_wall:.1f}s*\n")

    OUT_PATH.write_text("".join(parts))
    print(f"Wrote {OUT_PATH} ({total_wall:.1f}s total)")


if __name__ == "__main__":
    main()
