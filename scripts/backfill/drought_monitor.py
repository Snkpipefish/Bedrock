"""Backfill US Drought Monitor til ``drought_monitor``-tabellen.

Sub-fase 12.7 D2 A9 (session 133). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP med 1.5s pacing, lov til å være "shitty").

Hva skriptet gjør:
- Henter ukentlig CONUS-aggregat (statisticsType=1, cumulative) fra USDM
  via gratis-API uten auth.
- Lagrer til ``drought_monitor``-tabellen med PK (map_date, aoi).

USDM API har en ~365-dagers chunk-grense per call. Skriptet chunker per
1-års-vinduer (Jan 1 → Dec 31 per kalenderår).

Per ADR-011 § 1: 10-år rolling cutoff. 2026 → fra 2016. Faktisk USDM
har data tilbake til 2000-01-04, så vi kan utvide ved behov, men 10y
holder for 12m/36m percentile-vinduer per PLAN § 19.3.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/drought_monitor.py
Forventet kjøretid: ~15-30 sek (10 år × 1 AOI × 1.5s pacing = ~15s + I/O).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.drought_monitor import (
    DroughtMonitorFetchError,
    fetch_drought_monitor,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from-year",
        dest="from_year",
        type=int,
        default=None,
        help=f"Start-år. Default: {DEFAULT_LOOKBACK_YEARS} år tilbake.",
    )
    parser.add_argument(
        "--to-year",
        dest="to_year",
        type=int,
        default=None,
        help="Slutt-år (inkluderende). Default: gjeldende år.",
    )
    parser.add_argument(
        "--aoi",
        default="us",
        help="AOI-kode (us=CONUS-aggregat default, eller state-koder som IA/IL/etc).",
    )
    args = parser.parse_args()

    today = date.today()
    to_year = args.to_year if args.to_year is not None else today.year
    from_year = (
        args.from_year if args.from_year is not None else today.year - DEFAULT_LOOKBACK_YEARS
    )

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    aoi = args.aoi.lower()

    _log.info(
        "Backfill A9 USDM: aoi=%s, %d..%d, db=%s",
        aoi,
        from_year,
        to_year,
        db_path,
    )

    total_rows = 0
    overall_min: str | None = None
    overall_max: str | None = None
    first = True
    for year in range(from_year, to_year + 1):
        if not first:
            time.sleep(PACING_SECONDS)
        first = False

        # Per-år chunk: Jan 1 → Dec 31.
        chunk_start = date(year, 1, 1)
        chunk_end = date(year, 12, 31)
        if chunk_end > today:
            chunk_end = today

        try:
            df = fetch_drought_monitor(aoi=aoi, start_date=chunk_start, end_date=chunk_end)
        except DroughtMonitorFetchError as exc:
            _log.warning("FAILED %s %s..%s: %s", aoi, chunk_start, chunk_end, exc)
            continue

        if df.empty:
            continue

        rows = store.append_drought_monitor(df)
        total_rows += rows
        chunk_min = str(df["map_date"].min())
        chunk_max = str(df["map_date"].max())
        overall_min = chunk_min if overall_min is None else min(overall_min, chunk_min)
        overall_max = chunk_max if overall_max is None else max(overall_max, chunk_max)

    _log.info(
        "Ferdig: %d rader skrevet (aoi=%s, %s..%s).",
        total_rows,
        aoi,
        overall_min,
        overall_max,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
