"""Backfill US Treasury auction-historikk fra TreasuryDirect (Spor F6).

Henter auction-results fra
``https://www.treasurydirect.gov/TA_WS/securities/auctioned`` og
appender til ``treasury_auctions``-tabellen.

Default-strategi: enkelt-kall med ``pagesize=1000`` returnerer de nyeste
1000 auksjonene (~6-12 mnd avhengig av Bills-cadens). For full 10-års
historikk kjør med ``--days 3650``-flagg, eller iterer over flere kall.
TreasuryDirect ser ut til å støtte enkelte filterparametere men full
arkiv-paginering ikke testet.

Sekvensielt mot endepunktet per memory-feedback (gratis-API).

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill/treasury_auctions.py
    PYTHONPATH=src .venv/bin/python scripts/backfill/treasury_auctions.py --days 3650
    PYTHONPATH=src .venv/bin/python scripts/backfill/treasury_auctions.py --pagesize 1000
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.treasury_auctions import fetch_treasury_auctions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/bedrock.db")
    parser.add_argument(
        "--pagesize",
        type=int,
        default=1000,
        help="Antall auksjoner å hente per kall (default 1000; max ~1000)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Begrens til auksjoner siste N dager (default: alt API leverer)",
    )
    args = parser.parse_args()

    df = fetch_treasury_auctions(pagesize=args.pagesize, days_ago=args.days)
    if df.empty:
        _log.warning("Ingen auksjoner returnert")
        return 0

    store = DataStore(Path(args.db))
    n = store.append_treasury_auctions(df)
    _log.info(
        "treasury_auctions: %d rader skrevet (%s..%s)",
        n,
        df["auction_date"].min(),
        df["auction_date"].max(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
