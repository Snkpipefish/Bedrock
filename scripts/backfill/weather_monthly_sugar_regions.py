"""Backfill weather_monthly for India + Thailand sukker-regioner.

Per analytiker-anbefaling D (peer-review 2026-05): vekt etter eksport-
impact, ikke total produksjon. Multi-region for sukker:
- Brazil Centro-Sul (allerede backfilled, lat -21.18, lon -47.81)
- India Maharashtra (~30% nasjonal sukker, lat 19.50, lon 76.00 - Pune-region)
- Thailand Suphan Buri (sentral sukker-belte, lat 14.47, lon 100.10)

Idempotent (INSERT OR REPLACE på (region, month)).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.weather_monthly import (
    WeatherMonthlyFetchError,
    fetch_weather_monthly,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

REGIONS: list[tuple[str, float, float]] = [
    ("india_maharashtra", 19.50, 76.00),  # Pune-region, sentral Maharashtra
    ("thailand_suphan_buri", 14.47, 100.10),  # Sentral Thailand sukker-belte
]

DEFAULT_DB = "data/bedrock.db"
DEFAULT_FROM = date(2011, 1, 1)
PACING_SEC = 1.5  # Per memory: gratis-API krever sekvensielle kall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--from", dest="from_date", default=None)
    parser.add_argument("--to", dest="to_date", default=None)
    args = parser.parse_args()

    today = date.today()
    to_d = date.fromisoformat(args.to_date) if args.to_date else today
    from_d = date.fromisoformat(args.from_date) if args.from_date else DEFAULT_FROM

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error("DB ikke funnet: %s", db_path)
        return 1

    store = DataStore(db_path)
    total = 0
    for i, (region, lat, lon) in enumerate(REGIONS):
        if i > 0:
            time.sleep(PACING_SEC)
        _log.info("Backfill %s @ (%.2f, %.2f) %s → %s", region, lat, lon, from_d, to_d)
        try:
            df = fetch_weather_monthly(region, lat, lon, from_d, to_d)
        except WeatherMonthlyFetchError as exc:
            _log.error("FAILED %s: %s", region, exc)
            continue

        if df.empty:
            _log.warning("SKIP %s: tom DataFrame", region)
            continue

        n = store.append_weather_monthly(df)
        total += n
        _log.info("Skrev %d rader %s..%s", n, df["month"].iloc[0], df["month"].iloc[-1])

    _log.info("Ferdig: %d rader totalt fra %d regioner", total, len(REGIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
