"""Backfill CFTC TFF (Traders in Financial Futures) for 8 finansielle.

Sub-fase 12.7 D1 A4 (session 128). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP, lov til å være "shitty").

Hva skriptet gjør:
- Henter CFTC TFF-rapporter for 8 finansielle instrumenter (FX, krypto,
  indekser) via Socrata-API (`gpe5-46if`).
- Lagrer via `DataStore.append_cot_tff` (idempotent på (date, contract)).

Kontrakter (TFF-canonical, eksakt match til instrument-YAML cot_contract):
- EURUSD: EURO FX
- GBPUSD: BRITISH POUND
- USDJPY: JAPANESE YEN
- AUDUSD: AUSTRALIAN DOLLAR
- BTC:    BITCOIN
- ETH:    ETHER CASH SETTLED
- Nasdaq: NASDAQ-100 Consolidated
- SP500:  E-MINI S&P 500

Per V4-funn (D0 smoke-test): TFF-historikk fra juni 2006 (ekte data).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/cot_tff.py
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import fetch_cot_tff

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

CONTRACTS = [
    ("EURUSD", "EURO FX - CHICAGO MERCANTILE EXCHANGE"),
    ("GBPUSD", "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"),
    ("USDJPY", "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE"),
    ("AUDUSD", "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE"),
    ("BTC", "BITCOIN - CHICAGO MERCANTILE EXCHANGE"),
    ("ETH", "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE"),
    ("Nasdaq", "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"),
    ("SP500", "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"),
]

DEFAULT_DB = "data/bedrock.db"
PACING_SEC = 1.5  # ADR-011 / memory:free-api-no-parallel-requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help="Start-dato YYYY-MM-DD. Default: 10 år tilbake (ADR-011).",
    )
    parser.add_argument("--to", dest="to_date", default=None, help="End-dato YYYY-MM-DD.")
    args = parser.parse_args()

    today = date.today()
    if args.from_date:
        from_d = date.fromisoformat(args.from_date)
    else:
        from_d = date(today.year - 10, 1, 1)
    to_d = date.fromisoformat(args.to_date) if args.to_date else today

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error(f"DB ikke funnet: {db_path}")
        return 1

    store = DataStore(db_path)
    total = 0
    failed = []

    for instrument, contract in CONTRACTS:
        _log.info(f"--- {instrument}: {contract} ---")
        try:
            df = fetch_cot_tff(contract, from_date=from_d, to_date=to_d)
        except Exception as exc:
            _log.warning(f"  FEIL: {type(exc).__name__}: {exc}")
            failed.append((instrument, str(exc)))
            time.sleep(PACING_SEC)
            continue

        if df.empty:
            _log.warning(f"  Tom respons for {contract}")
            time.sleep(PACING_SEC)
            continue

        n = store.append_cot_tff(df)
        total += n
        _log.info(f"  Skrev {n} rader ({df['report_date'].min()} → {df['report_date'].max()})")
        time.sleep(PACING_SEC)

    _log.info(f"=== Backfill ferdig: {total} rader på tvers av {len(CONTRACTS)} kontrakter ===")
    if failed:
        _log.warning(f"Feilet: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
