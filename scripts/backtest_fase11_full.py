"""Fase 11 leveranse: full 12-mnd orchestrator-replay-rapport.

Kjører run_orchestrator_replay for Gold + Corn × 30d/90d og samler
output i én markdown-fil. Wall-time-estimat: ~7 min med step_days=5
(ukentlig). Brukes som baseline-rapport for Fase 11-fase-tag.

Kjørt manuelt:
    PYTHONPATH=src python scripts/backtest_fase11_full.py
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
OUT_PATH = Path("docs/backtest_fase11_full.md")
INSTRUMENTS_DIR = Path("config/instruments")
STEP_DAYS = 5  # ukentlig — balanse mellom presisjon og wall-time
DIRECTION = "buy"

# 12-mnd-vindu fra i dag. For 90d-horisonten begrenses faktisk dekning
# av at outcome-data trenger ref_date + 90d ≤ siste price-dato.
TODAY = date.today()
FROM_DATE = TODAY - timedelta(days=365)


def _section(store: DataStore, instrument: str, horizon_days: int) -> str:
    cfg = BacktestConfig(
        instrument=instrument,
        horizon_days=horizon_days,
        from_date=FROM_DATE,
        to_date=TODAY,
    )
    t0 = time.time()
    result = run_orchestrator_replay(
        store,
        cfg,
        instruments_dir=str(INSTRUMENTS_DIR),
        direction=DIRECTION,
        step_days=STEP_DAYS,
    )
    elapsed = time.time() - t0
    report = summary_stats(result)
    body = format_markdown(result, report)
    return (
        f"## {instrument} · h={horizon_days}d\n\n"
        f"*Wall-time: {elapsed:.1f}s · {len(result.signals)} signaler · "
        f"step_days={STEP_DAYS}, direction={DIRECTION}*\n\n"
        f"{body}\n"
    )


def main() -> None:
    store = DataStore(DB_PATH)
    sections: list[str] = []

    sections.append("# Backtest Fase 11 — full 12-mnd orchestrator-replay\n")
    sections.append(
        f"*Generert {TODAY} via `scripts/backtest_fase11_full.py` mot "
        f"`{DB_PATH}`. Vindu: {FROM_DATE} .. {TODAY}.*\n"
    )
    sections.append(
        "Replay-modus: full Engine-kjøring as-of-date per ref_date. "
        "Look-ahead-strict via `AsOfDateStore` — ingen K-NN-leak.\n"
    )
    sections.append("---\n")

    total_t0 = time.time()
    for instrument in ("Gold", "Corn"):
        for horizon_days in (30, 90):
            print(f"Running {instrument} h={horizon_days}d ...", flush=True)
            sections.append(_section(store, instrument, horizon_days))
            sections.append("---\n")
    total_elapsed = time.time() - total_t0

    sections.append(f"*Total wall-time: {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)*\n")

    OUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({total_elapsed:.1f}s total)", flush=True)


if __name__ == "__main__":
    main()
