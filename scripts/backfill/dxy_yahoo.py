"""Backfill Yahoo DX-Y.NYB (ICE Dollar Index) til fundamentals-tabellen.

Sub-fase 12.7 D1 B3 (session 128). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP, lov til å være "shitty").

Hva skriptet gjør:
- Henter ICE Dollar Index (`DX-Y.NYB`) fra Yahoo Chart-API via
  eksisterende `bedrock.fetch.yahoo.fetch_yahoo_prices`.
- Lagrer daglig close som fundamentals-rad med ``series_id="DX-Y.NYB"``.

Hvorfor fundamentals-tabellen (ikke prices):
- `dxy_chg5d`-driver (macro.py) leser via ``store.get_fundamentals(series_id)``.
- Bytte til prices ville krevd (a) ny instrument-registering, (b) endring
  av driver til ``store.get_prices(...)``, (c) endring av 4 instrument-
  YAMLs som har DTWEXBGS i fred_series_ids. Per V2-ADR-011-disiplin er
  minimal-impact pattern å lagre Yahoo-ticker som pseudo-FRED-serie i
  fundamentals.

ICE Dollar Index (`DX-Y.NYB`) vs FRED `DTWEXBGS`:
- ICE-DXY: 6-valuta basket (EUR/JPY/GBP/CAD/SEK/CHF), markedsstandard,
  daglig fra 1971.
- FRED DTWEXBGS: Federal Reserve "Broad Dollar Index", 26-valuta basket
  inkl. fremvoksende markeder, daglig fra 2006.
- ICE-DXY er hva markedsdeltakere faktisk handler på.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/dxy_yahoo.py
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.fetch.yahoo import fetch_yahoo_prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

YAHOO_TICKER = "DX-Y.NYB"
SERIES_ID = "DX-Y.NYB"  # Pseudo-FRED-id i fundamentals-tabellen
DEFAULT_DB = "data/bedrock.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help="Start-dato (YYYY-MM-DD). Default: 10 år tilbake (ADR-011).",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        help="End-dato (YYYY-MM-DD). Default: i dag.",
    )
    args = parser.parse_args()

    today = date.today()
    if args.from_date:
        from_d = date.fromisoformat(args.from_date)
    else:
        # 10-år rolling cutoff per ADR-011
        from_d = date(today.year - 10, 1, 1)
    to_d = date.fromisoformat(args.to_date) if args.to_date else today + timedelta(days=1)

    _log.info(f"Henter {YAHOO_TICKER} fra Yahoo for {from_d} → {to_d}")
    df = fetch_yahoo_prices(YAHOO_TICKER, from_date=from_d, to_date=to_d, interval="1d")

    if df.empty:
        _log.error(f"Tom respons fra Yahoo for {YAHOO_TICKER}")
        return 1

    # Konverter til fundamentals-schema: series_id, date, value
    fund_df = pd.DataFrame(
        {
            "series_id": SERIES_ID,
            "date": df["ts"].dt.strftime("%Y-%m-%d"),
            "value": df["close"].astype("float64"),
        }
    )

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error(f"DB ikke funnet: {db_path}")
        return 1

    store = DataStore(db_path)
    n = store.append_fundamentals(fund_df)
    _log.info(
        f"Skrev {n} rader til fundamentals-tabellen for series_id={SERIES_ID} "
        f"({df['ts'].min().date()} → {df['ts'].max().date()})"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
