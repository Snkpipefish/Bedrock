"""Backfill NASS yield + grain_stocks til SQLite (sub-fase 12.10 follow-up Spor D, session 137).

Engangs-skript per ADR-011 (10-år rolling cutoff, sekvensiell HTTP).

Hva skriptet gjør:
- Henter årlig yield-survey for CORN/SOYBEANS/WHEAT/COTTON.
- Henter quarterly grain-stocks for CORN/SOYBEANS/WHEAT (COTTON har ikke).
- Lagrer til ``nass_yield`` + ``nass_grain_stocks``.

Per ADR-011 § 1: backfill fra ~2016-05-02 (10-år rolling cutoff).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/nass_yield_stocks.py

Forventet kjøretid: ~2-3 min (4 commodities × 10 år for yield + 3 ×
10 år for stocks = ~70 HTTP-kall).
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.nass import (
    NASS_API_KEY_ENV,
    fetch_nass_grain_stocks_api,
    fetch_nass_yield_api,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10

YIELD_COMMODITIES: tuple[str, ...] = ("CORN", "SOYBEANS", "WHEAT", "COTTON")
STOCKS_COMMODITIES: tuple[str, ...] = ("CORN", "SOYBEANS", "WHEAT")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help=f"Start-år. Default: {DEFAULT_LOOKBACK_YEARS} år tilbake.",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Slutt-år (inklusive). Default: gjeldende år.",
    )
    parser.add_argument("--skip-yield", action="store_true")
    parser.add_argument("--skip-stocks", action="store_true")
    args = parser.parse_args()

    current = date.today().year
    to_year = args.to_year or current
    from_year = args.from_year or (current - DEFAULT_LOOKBACK_YEARS + 1)
    years = list(range(from_year, to_year + 1))

    api_key = require_secret(NASS_API_KEY_ENV)
    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill NASS yield+stocks: years=%d-%d, db=%s",
        from_year,
        to_year,
        db_path,
    )

    if not args.skip_yield:
        _log.info("Henter yield (commodities=%s)", YIELD_COMMODITIES)
        df_yield = fetch_nass_yield_api(commodities=YIELD_COMMODITIES, years=years, api_key=api_key)
        if not df_yield.empty:
            n = store.append_nass_yield(df_yield)
            yr_min = df_yield["year"].min()
            yr_max = df_yield["year"].max()
            _log.info(
                "Yield: %d rader skrevet (%s..%s, %d unique commodity-years)",
                n,
                yr_min,
                yr_max,
                df_yield[["commodity", "year"]].drop_duplicates().shape[0],
            )
        else:
            _log.warning("Yield: ingen rader hentet.")

    if not args.skip_stocks:
        _log.info("Henter stocks (commodities=%s)", STOCKS_COMMODITIES)
        df_stocks = fetch_nass_grain_stocks_api(
            commodities=STOCKS_COMMODITIES, years=years, api_key=api_key
        )
        if not df_stocks.empty:
            n = store.append_nass_grain_stocks(df_stocks)
            yr_min = df_stocks["year"].min()
            yr_max = df_stocks["year"].max()
            _log.info(
                "Stocks: %d rader skrevet (%s..%s, %d unique commodity-years)",
                n,
                yr_min,
                yr_max,
                df_stocks[["commodity", "year"]].drop_duplicates().shape[0],
            )
        else:
            _log.warning("Stocks: ingen rader hentet.")

    _log.info("Ferdig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
