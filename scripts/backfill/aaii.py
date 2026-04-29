"""Backfill AAII Sentiment Survey til ``aaii_sentiment`` (D2 A12, session 131).

Engangs-skript per ADR-011 (10-år rolling cutoff, sekvensiell HTTP).

Hva skriptet gjør:
- Henter sentiment.xls fra aaii.com (full historikk 1987+)
- Filtrerer til ADR-011 cutoff (10 år rolling)
- Lagrer til ``aaii_sentiment``-tabellen

Forventet kjøretid: ~5-10 sekunder (én HTTP-call + xls-parse).

Per ADR-007 § 4: hvis live-fetch feiler, bruk manuell CSV-fallback i
``data/manual/aaii_sentiment.csv``.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/aaii.py
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.fetch.aaii import AaiiFetchError, fetch_aaii_sentiment, filter_from_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10


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
        "--manual-csv",
        default=None,
        help="Bruk manuell CSV-fallback i stedet for live-fetch.",
    )
    args = parser.parse_args()

    today = date.today()
    from_d = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else date(today.year - DEFAULT_LOOKBACK_YEARS, 1, 1)
    )

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error(f"DB ikke funnet: {db_path}")
        return 1

    try:
        if args.manual_csv:
            _log.info("Leser manuell CSV: %s", args.manual_csv)
            df = pd.read_csv(args.manual_csv)
            df["date"] = pd.to_datetime(df["date"])
        else:
            _log.info("Henter live AAII-survey fra aaii.com...")
            df = fetch_aaii_sentiment()
    except AaiiFetchError as exc:
        _log.error("FAILED: %s", exc)
        return 1

    df = filter_from_date(df, from_d)
    if df.empty:
        _log.warning("Tom DataFrame etter filtering. Ingen rader skrevet.")
        return 0

    store = DataStore(db_path)
    n = store.append_aaii_sentiment(df)
    _log.info(
        "Ferdig: %d rader skrevet (%s..%s).",
        n,
        df["date"].min().date(),
        df["date"].max().date(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
