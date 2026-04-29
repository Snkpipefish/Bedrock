"""Backfill AGSI EU gas storage til ``agsi_storage``-tabellen.

Sub-fase 12.7 D1 A2 (session 130). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP med 1.5s pacing, lov til å være "shitty").

Hva skriptet gjør:
- Henter daglig EU-aggregat (``type=eu``) + 4 hovedland (DE/NL/FR/IT) fra
  AGSI+ via gas-storage-API.
- Lagrer til ``agsi_storage``-tabellen med PK (country, gas_day_start).

Forventet historikk:
- EU-aggregat: 2014+ (~12 år ved 2026-04-29 cut-off)
- Per-land DE: 2011+
- Per-land NL/FR/IT: 2011-2016+ (varierer)

Per ADR-011 § 1: backfill fra ~2016-04-29 (10-år rolling cutoff).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/agsi.py

Forventet kjøretid: ~10-15 min for 5 countries × 10 år (sekvensielt med
1.5s pacing — AGSI har én request per land per range, så det er kun ~5
HTTP-kall totalt, men hver returnerer ~3500 rader).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.agsi import (
    AGSI_API_KEY_ENV,
    AgsiFetchError,
    fetch_agsi_country_range,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5

DEFAULT_COUNTRIES: tuple[str, ...] = ("eu", "de", "nl", "fr", "it")


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
        "--country",
        action="append",
        help="Spesifiser ett eller flere land (gjenta flagget). "
        f"Default: {', '.join(DEFAULT_COUNTRIES)}.",
    )
    args = parser.parse_args()

    today = date.today()
    to_date = date.fromisoformat(args.to_date) if args.to_date else today
    from_date = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else today - timedelta(days=DEFAULT_LOOKBACK_YEARS * 365 + 5)
    )
    countries = tuple(args.country) if args.country else DEFAULT_COUNTRIES

    api_key = require_secret(AGSI_API_KEY_ENV)

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill A2 AGSI EU gas storage: %d countries, %s → %s, db=%s",
        len(countries),
        from_date,
        to_date,
        db_path,
    )

    # AGSI v2 paginerer med size=300 cap per request → vi chunker per
    # 9-mnd-vinduer (~270 dager) for å få full historikk uten paging-rot.
    chunk_days = 270

    def _chunks(start: date, end: date):
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
            yield cursor, chunk_end
            cursor = chunk_end + timedelta(days=1)

    total_rows = 0
    for i, country in enumerate(countries, start=1):
        country_rows = 0
        country_min: str | None = None
        country_max: str | None = None
        for chunk_start, chunk_end in _chunks(from_date, to_date):
            time.sleep(PACING_SECONDS)
            try:
                df = fetch_agsi_country_range(
                    country, api_key, from_date=chunk_start, to_date=chunk_end
                )
            except AgsiFetchError as exc:
                _log.error("FAILED %s %s..%s: %s", country, chunk_start, chunk_end, exc)
                continue

            if df.empty:
                continue

            rows = store.append_agsi_storage(df)
            country_rows += rows
            chunk_min = str(df["gas_day_start"].min())
            chunk_max = str(df["gas_day_start"].max())
            country_min = chunk_min if country_min is None else min(country_min, chunk_min)
            country_max = chunk_max if country_max is None else max(country_max, chunk_max)

        total_rows += country_rows
        _log.info(
            "[%d/%d] %s: %d rader (%s..%s)",
            i,
            len(countries),
            country,
            country_rows,
            country_min,
            country_max,
        )

    _log.info(
        "Ferdig: %d rader skrevet totalt på tvers av %d countries.",
        total_rows,
        len(countries),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
