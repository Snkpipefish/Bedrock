"""Backfill VIX-termstruktur fra Yahoo (sub-fase 12.7 D2 B2, session 131).

Engangs-skript per ADR-011 (10-år rolling cutoff, sekvensiell HTTP,
lov til å være "shitty").

Hva skriptet gjør:
- Henter ^VIX3M, ^VIX6M, ^VIX9D fra Yahoo Chart-API via eksisterende
  ``bedrock.fetch.yahoo.fetch_yahoo_prices``.
- Lagrer daglig close som fundamentals-rader med ``series_id`` =
  ticker-symbol (uten ^).

Hvorfor fundamentals-tabellen (ikke prices):
- ``vix_term_ratio``-driver leser FRED-style series via
  ``store.get_fundamentals(series_id)`` — samme presedens som B3 DXY
  (session 128) og VIXCLS (session 71). Holder driver-laget enkelt.

Tickere og forventet historikk (per smoke-test session 126):
- ^VIX3M: 2006-07-17+ (19.8 år)
- ^VIX6M: 2008-01-02+ (18.3 år)
- ^VIX9D: 2011-01-03+ (15.3 år)

Per ADR-011: backfill fra ~2016 (10-år rolling).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/vix_term.py
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.fetch.yahoo import YahooFetchError, fetch_yahoo_prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

# Yahoo-ticker → fundamentals series_id (med ^ strippet)
TICKER_TO_SERIES = {
    "^VIX3M": "VIX3M",
    "^VIX6M": "VIX6M",
    "^VIX9D": "VIX9D",
}

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help=f"Start-dato (YYYY-MM-DD). Default: {DEFAULT_LOOKBACK_YEARS} år tilbake (ADR-011).",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        help="Slutt-dato (YYYY-MM-DD). Default: i morgen (Yahoo bruker exclusive end).",
    )
    args = parser.parse_args()

    today = date.today()
    to_d = date.fromisoformat(args.to_date) if args.to_date else today + timedelta(days=1)
    from_d = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else date(today.year - DEFAULT_LOOKBACK_YEARS, 1, 1)
    )

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error(f"DB ikke funnet: {db_path}")
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill B2 VIX-term: %d tickere, %s → %s, db=%s",
        len(TICKER_TO_SERIES),
        from_d,
        to_d,
        db_path,
    )

    total_rows = 0
    for i, (ticker, series_id) in enumerate(TICKER_TO_SERIES.items()):
        if i > 0:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_yahoo_prices(ticker, from_date=from_d, to_date=to_d, interval="1d")
        except YahooFetchError as exc:
            _log.error("FAILED %s: %s", ticker, exc)
            continue

        if df.empty:
            _log.warning("SKIP %s: tom DataFrame", ticker)
            continue

        fund_df = pd.DataFrame(
            {
                "series_id": series_id,
                "date": df["ts"].dt.strftime("%Y-%m-%d"),
                "value": df["close"].astype("float64"),
            }
        )
        n = store.append_fundamentals(fund_df)
        total_rows += n
        _log.info(
            "[%d/%d] %s → %s: %d rader (%s..%s)",
            i + 1,
            len(TICKER_TO_SERIES),
            ticker,
            series_id,
            n,
            df["ts"].min().date(),
            df["ts"].max().date(),
        )

    _log.info(
        "Ferdig: %d rader skrevet totalt på tvers av %d tickere.",
        total_rows,
        len(TICKER_TO_SERIES),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
