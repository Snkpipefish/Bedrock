"""Backfill FRED B1 D1-utvidelse — 10 nye serier til fundamentals-tabellen.

Sub-fase 12.7 D1 B1 (session 129). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP med 1.5s pacing, lov til å være "shitty").

Hva skriptet gjør:
- Henter 10 nye FRED-serier som B1-drivere bruker:

  Yield-diff input (yield_diff_10y-driver):
    - DGS2: US 2Y Treasury (daglig, 1976+) — backfilles for fremtidig
      bruk; ingen driver i 129 leser den ennå.
    - IRLTLT01DEM156N: Tyskland 10Y (månedlig, 1970+) — EURUSD
    - IRLTLT01GBM156N: Storbritannia 10Y (månedlig, 1970+) — GBPUSD
    - IRLTLT01JPM156N: Japan 10Y (månedlig, 1989+) — USDJPY
    - IRLTLT01AUM156N: Australia 10Y (månedlig, 1970+) — AUDUSD

  Credit-spread input (credit_spread_change-driver) — V2-substitusjon
  for HY/IG OAS som var begrenset til 3 år gratis-API-historikk:
    - AAA10Y: Moody's AAA Corporate − 10Y Treasury (daglig, 1996+)
    - BAA10Y: Moody's BAA Corporate − 10Y Treasury (daglig, 1996+)

  NetFedLiq input (net_fed_liq_change-driver):
    - WALCL: Fed total assets (ukentlig ons, 2002+)
    - RRPONTSYD: Reverse Repo outstanding (ukentlig ons, 2003+)
    - WTREGEN: Treasury General Account balance (ukentlig ons, 1986+)

  Risk-conditions input (nfci_change-driver):
    - NFCI: Chicago Fed National Financial Conditions Index
      (ukentlig fre, 1971+)

Hvorfor sentralt skript:
- Auto-fetcher i `bedrock.fetch.fred` itererer kun over instrument-
  registrerte `fred_series_ids`. Ny serie blir ikke fyllt opp historisk
  med daglig timer-fetch (kun forward fra `--from`-default).
- Per ADR-011 § 4: engangs-skript fyller historikk; produksjons-fetcher
  håndterer daglig refresh.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/fred_b1.py

Forventet kjøretid: ~30 sek per serie × 10 = 5-7 min totalt.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10

# Per ADR-011 § 3 — sekvensiell pacing for gratis-API
PACING_SECONDS = 1.5

# 10 nye serier som B1-drivere bruker.
SERIES_TO_BACKFILL: tuple[str, ...] = (
    # Yield-diff input
    "DGS2",
    "IRLTLT01DEM156N",
    "IRLTLT01GBM156N",
    "IRLTLT01JPM156N",
    "IRLTLT01AUM156N",
    # Credit-spread input
    "AAA10Y",
    "BAA10Y",
    # NetFedLiq input
    "WALCL",
    "RRPONTSYD",
    "WTREGEN",
    # NFCI input (samme tabell, ny serie)
    "NFCI",
)


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
        help="Slutt-dato (YYYY-MM-DD). Default: i dag.",
    )
    parser.add_argument(
        "--series",
        action="append",
        help="Spesifiser én eller flere serier å backfille (gjenta flagget). "
        "Default: alle 10 B1-serier.",
    )
    args = parser.parse_args()

    today = date.today()
    to_date = date.fromisoformat(args.to_date) if args.to_date else today
    from_date = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else today - timedelta(days=DEFAULT_LOOKBACK_YEARS * 365 + 5)
    )
    series_list = tuple(args.series) if args.series else SERIES_TO_BACKFILL

    api_key = require_secret("FRED_API_KEY")

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill B1 FRED-utvidelse: %d serier, %s → %s, db=%s",
        len(series_list),
        from_date,
        to_date,
        db_path,
    )

    total_rows = 0
    for i, series_id in enumerate(series_list, start=1):
        if i > 1:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_fred_series(series_id, api_key, from_date, to_date)
        except FredFetchError as exc:
            _log.error("FAILED %s: %s", series_id, exc)
            continue

        if df.empty:
            _log.warning("SKIP %s: tom DataFrame", series_id)
            continue

        rows = store.append_fundamentals(df)
        total_rows += rows
        _log.info(
            "[%d/%d] %s: %d rader (%s..%s)",
            i,
            len(series_list),
            series_id,
            rows,
            df["date"].min(),
            df["date"].max(),
        )

    _log.info(
        "Ferdig: %d rader skrevet totalt på tvers av %d serier.", total_rows, len(series_list)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
