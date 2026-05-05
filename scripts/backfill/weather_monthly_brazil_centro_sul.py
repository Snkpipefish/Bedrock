"""Backfill brazil_centro_sul weather_monthly via Open-Meteo Archive.

Senter-Sør Brasil (sukker-region). Ribeirão Preto-koordinatene brukes
som proxy — dette er hjertet av sukker-belte (~22% av global sukker-
produksjon alene).

Eksempel:
    python scripts/backfill/weather_monthly_brazil_centro_sul.py \
        --db data/bedrock.db --from 2011-01-01

Idempotent (INSERT OR REPLACE på (region, month)).
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.weather_monthly import (
    WeatherMonthlyFetchError,
    fetch_weather_monthly,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

REGION = "brazil_centro_sul"
LATITUDE = -21.18  # Ribeirão Preto, SP — sentralt sukker-belte
LONGITUDE = -47.81

DEFAULT_DB = "data/bedrock.db"
DEFAULT_FROM = date(2011, 1, 1)


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
    _log.info(
        "Backfill weather_monthly %s @ (%.2f, %.2f) %s → %s",
        REGION,
        LATITUDE,
        LONGITUDE,
        from_d,
        to_d,
    )

    try:
        df = fetch_weather_monthly(REGION, LATITUDE, LONGITUDE, from_d, to_d)
    except WeatherMonthlyFetchError as exc:
        _log.error("FAILED: %s", exc)
        return 2

    if df.empty:
        _log.warning("Ingen rader returnert.")
        return 3

    n = store.append_weather_monthly(df)
    _log.info(
        "Skrev %d rader (%s..%s) til weather_monthly",
        n,
        df["month"].iloc[0],
        df["month"].iloc[-1],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
