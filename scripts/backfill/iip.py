"""Backfill IIP REMIT supply-unavailability til ``iip_remit``-tabellen.

Sub-fase 12.10 follow-up Spor C, session 136. Engangs-skript per ADR-011
(arkiv siden 2022-01-31, sekvensiell HTTP med 1.5s pacing).

Hva skriptet gjør:
- Itererer alle sider av IIP UMM-feed (~213 sider × 50 records ved
  default size=50) sekvensielt.
- Lagrer til ``iip_remit``-tabellen med PK message_id (idempotent
  INSERT OR REPLACE — IIP-meldinger kan revideres).
- Optionell ``--stop-before-published`` for inkrementell-mode etter
  initial backfill (stopper når en page returnerer kun meldinger
  publisert <= threshold).

Per ADR-011 § 1: full historikk siden API-arkiv-start (~2022-01-31).
Det er ingen 10-år-cutoff her siden API-arkivet er kort allerede.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/iip.py

Forventet kjøretid: ~5 min for full backfill (213 sider × 1.5s = ~5 min).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.iip import (
    DEFAULT_PAGE_SIZE,
    IIP_API_KEY_ENV,
    fetch_iip_remit,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max antall sider å hente. Default: alle (~213 sider).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Records per side. Default: {DEFAULT_PAGE_SIZE}.",
    )
    parser.add_argument(
        "--stop-before-published",
        default=None,
        help=(
            "ISO-streng (YYYY-MM-DD HH:MM:SS). Stopp når en side returnerer "
            "kun meldinger publisert <= denne. Brukes for inkrementell-mode."
        ),
    )
    args = parser.parse_args()

    api_key = require_secret(IIP_API_KEY_ENV)

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill IIP REMIT: max_pages=%s, page_size=%d, db=%s",
        args.max_pages or "all",
        args.page_size,
        db_path,
    )

    df = fetch_iip_remit(
        api_key=api_key,
        max_pages=args.max_pages,
        page_size=args.page_size,
        stop_before_published_ts=args.stop_before_published,
    )

    if df.empty:
        _log.warning("Ingen meldinger hentet.")
        return 0

    rows = store.append_iip_remit(df)
    pub_min = str(df["published_ts"].min())
    pub_max = str(df["published_ts"].max())
    _log.info(
        "Ferdig: %d rader skrevet (published %s..%s).",
        rows,
        pub_min,
        pub_max,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
