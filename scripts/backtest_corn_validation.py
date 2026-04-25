"""Validerings-backtest for Corn etter Sub-fase 12.5 Block B (session 72).

Kjører run_orchestrator_replay for Corn × 30d/90d og produserer
sammenliknings-rapport med fokus på grade-hit-rate. Sjekker om
Fase 11 session 64s funn — A+ buy invertert vs C buy — er fixet
av nye agri-drivere (weather_stress + enso_regime).

Ulik full Fase 11-rapport: kun Corn, kun direction=buy, step_days=10
(annen-hver-uke) for raskere kjøring (~2-3 min).

Kjørt manuelt:
    PYTHONPATH=src python scripts/backtest_corn_validation.py
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
OUT_PATH = Path("docs/backtest_corn_validation_2026-04.md")
INSTRUMENTS_DIR = Path("config/instruments")
STEP_DAYS = 10  # annen-hver-uke for fart
DIRECTION = "buy"
TODAY = date.today()
FROM_DATE = TODAY - timedelta(days=365)


def _section(store: DataStore, horizon_days: int) -> str:
    cfg = BacktestConfig(
        instrument="Corn",
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
        f"## Corn · h={horizon_days}d · direction={DIRECTION}\n\n"
        f"*Wall-time: {elapsed:.1f}s · {len(result.signals)} signaler · "
        f"step_days={STEP_DAYS}*\n\n"
        f"{body}\n"
    )


def main() -> None:
    store = DataStore(DB_PATH)
    sections: list[str] = []

    sections.append("# Corn-validering etter Sub-fase 12.5 Block B (session 72)\n")
    sections.append(
        f"*Generert {TODAY} via `scripts/backtest_corn_validation.py`. "
        f"Vindu: {FROM_DATE} .. {TODAY}.*\n"
    )
    sections.append(
        "**Hva sjekkes:** Fase 11 session 64 fant at Corn buy-direction "
        "var INVERTERT — A+ hit-rate var lavere enn C-grade. Skyldtes at "
        "alle Corn-familier brukte sma200_align placeholder. Session 72 "
        "erstattet weather + enso med ekte drivere. Forventet: A+ hit-rate "
        "≥ C hit-rate (eller i hvert fall ikke åpenbart invertert).\n"
    )
    sections.append("---\n")

    total_t0 = time.time()
    for h in (30, 90):
        print(f"Running Corn h={h}d ...", flush=True)
        sections.append(_section(store, h))
        sections.append("---\n")
    total_elapsed = time.time() - total_t0

    sections.append(f"*Total wall-time: {total_elapsed:.1f}s*\n")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({total_elapsed:.1f}s total)", flush=True)


if __name__ == "__main__":
    main()
