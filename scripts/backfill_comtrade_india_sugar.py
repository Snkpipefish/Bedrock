"""Backfill UN Comtrade India sugar månedlig eksport-historikk til fundamentals.

Fanger månedlig (vs USDA PSD årlig) for raskere policy-event-deteksjon:
- USDA PSD årlig: oktober-publisering, lagger eksportforbud Q3 → ny data Q4 neste år
- UN Comtrade månedlig: ~2-4 mnd lag, fanger forbud-event innen kvartal

Skriver to series_id (begge månedlige fra 2010):
- COMTRADE_INDIA_SUGAR_EXPORTS_USD_MONTHLY
- COMTRADE_INDIA_SUGAR_EXPORTS_KG_MONTHLY

Kjøring (idempotent — INSERT OR REPLACE på (series_id, date)):
    PYTHONPATH=src python scripts/backfill_comtrade_india_sugar.py
    PYTHONPATH=src python scripts/backfill_comtrade_india_sugar.py --from 2020
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.comtrade import fetch_india_sugar_exports

DB_PATH = Path("data/bedrock.db")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2010)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument(
        "--pacing", type=float, default=0.5, help="Sekunder mellom API-kall (default 0.5)"
    )
    args = parser.parse_args()

    print(
        f"=== Backfill UN Comtrade India sugar ({args.from_year} → {args.to_year}) ===", flush=True
    )
    df = fetch_india_sugar_exports(
        from_year=args.from_year,
        to_year=args.to_year,
        pacing_sec=args.pacing,
    )
    if df.empty:
        print("INGEN data hentet — sjekk API-tilgjengelighet")
        return 1

    print(f"Hentet {len(df)} rader ({len(df) // 2} måneder × 2 series_id)")
    print(f"  Datointervall: {df['date'].min()} → {df['date'].max()}")

    store = DataStore(Path(args.db))
    written = store.append_fundamentals(df)
    print(f"Skrevet til DB: {written} rader (idempotent INSERT OR REPLACE)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
