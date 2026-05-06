"""Full backtest av Sugar-scoring etter sub-fase 12.11+ datafix.

Kjører run_orchestrator_replay over 16 års historikk for å validere:
1. UNICA-driverne fungerer med 42 historiske rapporter (2012-2026)
2. brazil_centro_sul weather-region gir bedre yield-signal
3. Asymmetrisk publish-floor (buy=7, sell=5) er kalibrert riktig
4. Grade-progresjon (A+ → C) holder monotonisk hit-rate

Designet for å kjøres i Codespace (gratis CPU). Tar ~5-10 min for
16 års vindu på alle 3 horisonter × 2 retninger.

Bruk:
    PYTHONPATH=src python scripts/backtest_sugar_full.py
    PYTHONPATH=src python scripts/backtest_sugar_full.py --years 5
"""

from __future__ import annotations

import argparse
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
OUT_PATH = Path("docs/backtest_sugar_full_2026-05.md")
INSTRUMENTS_DIR = Path("config/instruments")
STEP_DAYS = 7  # ukentlig step for høy oppløsning
# Agri har kun SWING + MAKRO (per orchestrator/signals._DEFAULT_AGRI_HORIZONS).
# SCALP er ikke aktiv — agri-fundamenta (COT ukentlig, WASDE månedlig)
# har ikke datafrekvens for scalping.
#
# Sukker-traders posisjonerer seg 6-12 måneder i forveien for neste
# Brasil zafra (apr-nov). ICE no.11 forward curve listet 3 år frem.
# Test multiple MAKRO-horisonter for å finne hvor markedet best priser
# inn fundamenta: 90d (taktisk SWING), 180d (kort MAKRO), 270d (zafra-
# overlap), 365d (full crop year cycle).
HORIZONS = [90, 180, 270, 365]


def _section(
    store: DataStore,
    horizon_days: int,
    direction: str,
    from_date: date,
    to_date: date,
) -> str:
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
        instruments_dir=str(INSTRUMENTS_DIR),
        direction=direction,
        step_days=STEP_DAYS,
    )
    elapsed = time.time() - t0
    report = summary_stats(result)
    body = format_markdown(result, report)
    return (
        f"## Sugar · h={horizon_days}d · direction={direction}\n\n"
        f"*Wall-time: {elapsed:.1f}s · {len(result.signals)} signaler · "
        f"step_days={STEP_DAYS} · vindu: {from_date} → {to_date}*\n\n"
        f"{body}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=int,
        default=14,
        help="Antall år tilbake fra i dag (default 14, dvs full UNICA-historikk).",
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    today = date.today()
    from_date = today - timedelta(days=365 * args.years)

    store = DataStore(Path(args.db))
    sections: list[str] = []
    sections.append("# Sugar full-historikk-backtest (sub-fase 12.11+)\n")
    sections.append(
        f"*Generert {today} via `scripts/backtest_sugar_full.py`. "
        f"Vindu: {from_date} → {today} ({args.years} år).*\n"
    )
    sections.append(
        "**Hva validerer:** UNICA-familie med 42 historiske rapporter "
        "(backfilled via Wayback Machine), brazil_centro_sul weather-region "
        "(184 mnd), og asymmetrisk publish-floor buy=7/sell=5. Forventet: "
        "monotonisk grade-progresjon (A+ > A > B > C hit-rate), og "
        "BUY-bias ≤ SELL-bias (sukker er strukturelt SELL-favorisert per "
        "session 99-backtest).\n"
    )
    sections.append("---\n")

    total_t0 = time.time()
    for direction in ("buy", "sell"):
        for h in HORIZONS:
            print(f"[{time.strftime('%H:%M:%S')}] kjører h={h}d {direction}...", flush=True)
            sections.append(_section(store, h, direction, from_date, today))

    total_elapsed = time.time() - total_t0
    sections.append(f"---\n\n*Total wall-time: {total_elapsed / 60:.1f} min*\n")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sections), encoding="utf-8")
    print(f"\nFerdig. Rapport skrevet til {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
