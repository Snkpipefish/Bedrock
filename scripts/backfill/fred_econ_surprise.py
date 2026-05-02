"""Backfill FRED-serier for *_surprise-drivere (sub-fase 12.10 follow-up Spor B, session 138).

Engangs-skript per ADR-014. Henter 4 FRED-serier som "actual"-kilde for
econ_surprise-drivere:

- PAYEMS — Total Nonfarm Employment (månedlig, MoM Δ tusen)
- CPIAUCSL — Consumer Price Index All Urban Consumers (månedlig, MoM %)
- GDP — Gross Domestic Product (kvartalsvis, QoQ %)
- PCEPI — Personal Consumption Expenditures Price Index (månedlig, MoM %)

Per ADR-011 § 1: 10-år rolling cutoff (~2016-05-02 → 2026-05-02).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/fred_econ_surprise.py

Forventet kjøretid: ~30s (4 serier × ~120 obs hver).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.fred import FredFetchError, fetch_fred_series

FRED_API_KEY_ENV = "FRED_API_KEY"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.0

ECON_SURPRISE_SERIES: tuple[str, ...] = (
    "PAYEMS",
    "CPIAUCSL",
    "GDP",
    "PCEPI",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument("--from", dest="from_date", default=None)
    parser.add_argument("--to", dest="to_date", default=None)
    args = parser.parse_args()

    today = date.today()
    to_date = date.fromisoformat(args.to_date) if args.to_date else today
    from_date = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else today - timedelta(days=DEFAULT_LOOKBACK_YEARS * 365 + 5)
    )

    api_key = require_secret(FRED_API_KEY_ENV)

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill FRED econ-surprise-serier: %s, %s → %s",
        ECON_SURPRISE_SERIES,
        from_date,
        to_date,
    )

    total_rows = 0
    for i, sid in enumerate(ECON_SURPRISE_SERIES):
        if i > 0:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_fred_series(sid, api_key, from_date, to_date)
        except FredFetchError as exc:
            _log.error("FAILED %s: %s", sid, exc)
            continue
        if df.empty:
            _log.warning("%s: ingen rader returnert.", sid)
            continue
        n = store.append_fundamentals(df)
        total_rows += n
        _log.info(
            "[%d/%d] %s: %d rader (%s..%s)",
            i + 1,
            len(ECON_SURPRISE_SERIES),
            sid,
            n,
            df["date"].min(),
            df["date"].max(),
        )

    _log.info("Ferdig: %d rader skrevet totalt.", total_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
