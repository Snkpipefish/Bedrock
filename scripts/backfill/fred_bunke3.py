"""Backfill FRED-utvidelse for sub-fase 12.10 Bunke 3 (FRED-drivere).

Per ADR-011 (10-år rolling cutoff, sekvensiell HTTP med 1.5s pacing,
engangs-skript). Henter ~16 nye FRED-serier som Bunke 3-drivere bruker:

  Yields (#7):
    - DGS3MO: 3-Month Treasury Constant Maturity (daglig, 1981+)
    - TB3MS: 3-Month Treasury Bill Secondary Market (månedlig)

  Credit (#8):
    - BAMLH0A0HYM2: ICE BofA US High Yield OAS (daglig, 1996+)

  Labor (#9):
    - ICSA: Initial Claims (ukentlig)
    - CCSA: Continued Claims (ukentlig)

  Growth (#10):
    - INDPRO: Industrial Production Index (månedlig)
    - CFNAI: Chicago Fed National Activity Index (månedlig)
    - UMCSENT: Univ Michigan Consumer Sentiment (månedlig)
    - JTSJOL: Job Openings: Total Nonfarm (månedlig, 2000+)
    - NAPMPMI: ISM Manufacturing PMI Composite (månedlig) — kan feile
      hvis ISM-lisens-restriksjon. Faller tilbake til alternativer.

  Liquidity (#11):
    - ANFCI: Adjusted NFCI (ukentlig fre, 1971+)
    - M2SL: M2 Money Stock (månedlig)

  Volatility (#12):
    - VIX9DCLS: CBOE 9-Day Volatility (daglig)

  FX (#13):
    - DEXJPUS, DEXUSEU, DEXUSUK, DEXUSAL, DEXCAUS, DEXSDUS, DEXUSNZ,
      DEXSZUS — for dollar_index_breadth-driveren (>50% av komponentene
      stigende = USD-styrke-bredde).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/fred_bunke3.py
Forventet kjøretid: ~25-40 sek totalt.
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
PACING_SECONDS = 1.5

SERIES_TO_BACKFILL: tuple[str, ...] = (
    # Yields (#7)
    "DGS3MO",
    "TB3MS",
    # Credit (#8)
    "BAMLH0A0HYM2",
    # Labor (#9)
    "ICSA",
    "CCSA",
    # Growth (#10)
    "INDPRO",
    "CFNAI",
    "UMCSENT",
    "JTSJOL",
    "NAPMPMI",  # ISM PMI — kan feile på FRED, fortsetter
    # Liquidity (#11)
    "ANFCI",
    "M2SL",
    # Volatility (#12)
    "VIX9DCLS",
    # FX (#13) — dollar_index_breadth-komponenter
    "DEXJPUS",
    "DEXUSEU",
    "DEXUSUK",
    "DEXUSAL",
    "DEXCAUS",
    "DEXSDUS",
    "DEXUSNZ",
    "DEXSZUS",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--from", dest="from_date", default=None)
    parser.add_argument("--to", dest="to_date", default=None)
    parser.add_argument("--series", action="append")
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
    store = DataStore(db_path)
    _log.info(
        "Backfill Bunke 3 FRED: %d serier, %s → %s",
        len(series_list),
        from_date,
        to_date,
    )

    total_rows = 0
    failed: list[tuple[str, str]] = []
    for i, series_id in enumerate(series_list, start=1):
        if i > 1:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_fred_series(series_id, api_key, from_date, to_date)
        except FredFetchError as exc:
            _log.error("FAILED %s: %s", series_id, exc)
            failed.append((series_id, str(exc)))
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

    _log.info("Total: %d rader fra %d serier", total_rows, len(series_list))
    if failed:
        _log.warning("Feilet: %d serier", len(failed))
        for sid, msg in failed:
            _log.warning("  %s: %s", sid, msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
