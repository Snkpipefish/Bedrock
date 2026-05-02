"""Backfill ALSI EU LNG-terminal storage til ``alsi_storage``-tabellen.

Sub-fase 12.10 follow-up Spor C, session 136. Engangs-skript per ADR-011
(10-år rolling cutoff, sekvensiell HTTP med 1.5s pacing). Søsken til
``scripts/backfill/agsi.py``.

Hva skriptet gjør:
- Henter daglig EU-aggregat (``type=eu``) + 5 hovedland (DE/NL/FR/IT/ES) fra
  ALSI+ via GIE LNG-storage-API.
- Lagrer til ``alsi_storage``-tabellen med PK (country, gas_day_start).

Forventet historikk:
- EU-aggregat: ~2012+ (~14 år ved 2026-05-02)
- Per-land: varierer (ES/IT eldre, FR senere)

Per ADR-011 § 1: backfill fra ~2016-05-02 (10-år rolling cutoff).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/alsi.py

Forventet kjøretid: ~3-5 min for 6 countries × 10 år (sekvensielt, 9-mnd-
chunks per land à ~14 chunks; ~84 HTTP-kall × 1.5s = ~2 min plus parsing).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.alsi import (
    ALSI_API_KEY_ENV,
    AlsiFetchError,
    fetch_alsi_country_range,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5

DEFAULT_COUNTRIES: tuple[str, ...] = ("eu", "de", "nl", "fr", "it", "es")


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

    api_key = require_secret(ALSI_API_KEY_ENV)

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill ALSI EU LNG-terminal storage: %d countries, %s → %s, db=%s",
        len(countries),
        from_date,
        to_date,
        db_path,
    )

    chunk_days = 270  # ALSI v2 size=300 cap → 9-mnd-vinduer

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
                df = fetch_alsi_country_range(
                    country, api_key, from_date=chunk_start, to_date=chunk_end
                )
            except AlsiFetchError as exc:
                _log.error("FAILED %s %s..%s: %s", country, chunk_start, chunk_end, exc)
                continue

            if df.empty:
                continue

            rows = store.append_alsi_storage(df)
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
