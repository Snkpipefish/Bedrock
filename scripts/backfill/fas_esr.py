"""Backfill FAS Export Sales (ESR) til ``fas_esr``-tabellen.

Sub-fase 12.7 D2 A3 (session 133). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP med 1.5s pacing, lov til å være "shitty").

Hva skriptet gjør:
- For hver bedrock-relevant commodity (Corn=401, Soybean=801, Wheat=107,
  Cotton=501) henter ukentlig export-sales-data per (commodity × MY ×
  alle countries) via ``/esr/exports/.../allCountries/...`` per call.
- Lagrer til ``fas_esr``-tabellen med PK (commodity, country, MY, week).

Marketing year-konvensjon (start-året):
- Corn (401):    MY = Sep-Aug
- Soybean (801): MY = Sep-Aug
- Cotton (501):  MY = Aug-Jul
- Wheat (107):   MY = Jun-May

Per ADR-011 § 1: 10-år rolling cutoff. Ved 2026-04-29 betyr det MY 2016
fremover. Vi tar 11 markedsår (2016..2026) for å få litt buffer ved
MY-overganger.

Forventet kjøretid: ~3-5 minutter (4 commodities × 11 marketing years =
44 HTTP-calls × 1.5s pacing ≈ 66s + behandlingstid).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/fas_esr.py
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.fas_esr import (
    COMMODITY_CODES,
    FAS_API_KEY_ENV,
    FasFetchError,
    fetch_esr_exports,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from-my",
        dest="from_my",
        type=int,
        default=None,
        help=f"Start-MY. Default: {DEFAULT_LOOKBACK_YEARS} år tilbake (ADR-011).",
    )
    parser.add_argument(
        "--to-my",
        dest="to_my",
        type=int,
        default=None,
        help="Slutt-MY (inkluderende). Default: gjeldende år + 1 (for å fange "
        "neste MY hvis den allerede har data).",
    )
    parser.add_argument(
        "--commodity",
        action="append",
        help="Begrens commodity-set (gjenta flagget). Aksepterer navn fra "
        f"COMMODITY_CODES: {', '.join(COMMODITY_CODES.keys())}. "
        f"Default: alle.",
    )
    args = parser.parse_args()

    today = date.today()
    to_my = args.to_my if args.to_my is not None else today.year + 1
    from_my = args.from_my if args.from_my is not None else today.year - DEFAULT_LOOKBACK_YEARS

    if args.commodity:
        commodities: dict[str, int] = {}
        for c in args.commodity:
            key = c.lower().strip()
            if key not in COMMODITY_CODES:
                _log.error("Ukjent commodity %r — velg fra %s", c, list(COMMODITY_CODES.keys()))
                return 1
            commodities[key] = COMMODITY_CODES[key]
    else:
        commodities = dict(COMMODITY_CODES)

    api_key = require_secret(FAS_API_KEY_ENV)

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    market_years = list(range(from_my, to_my + 1))

    _log.info(
        "Backfill A3 FAS ESR: %d commodities × %d MYs (%s..%s) = %d calls, db=%s",
        len(commodities),
        len(market_years),
        from_my,
        to_my,
        len(commodities) * len(market_years),
        db_path,
    )

    total_rows = 0
    first = True
    for name, code in commodities.items():
        commodity_rows = 0
        commodity_min: str | None = None
        commodity_max: str | None = None
        for my in market_years:
            if not first:
                time.sleep(PACING_SECONDS)
            first = False
            try:
                df = fetch_esr_exports(code, my, api_key=api_key)
            except FasFetchError as exc:
                _log.warning("FAILED %s (cc=%d) MY=%d: %s", name, code, my, exc)
                continue

            if df.empty:
                _log.info("%s MY=%d: tom respons (kanskje pre-MY-data)", name, my)
                continue

            rows = store.append_fas_esr(df)
            commodity_rows += rows
            chunk_min = str(df["week_ending_date"].min())
            chunk_max = str(df["week_ending_date"].max())
            commodity_min = chunk_min if commodity_min is None else min(commodity_min, chunk_min)
            commodity_max = chunk_max if commodity_max is None else max(commodity_max, chunk_max)

        total_rows += commodity_rows
        _log.info(
            "%s (cc=%d): %d rader (%s..%s)",
            name,
            code,
            commodity_rows,
            commodity_min,
            commodity_max,
        )

    _log.info(
        "Ferdig: %d rader skrevet totalt på tvers av %d commodities.",
        total_rows,
        len(commodities),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
