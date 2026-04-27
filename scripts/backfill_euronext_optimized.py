"""Optimalisert Euronext COT historisk backfill.

Optimaliseringer mot eksisterende `fetch_cot_euronext`:

1. **DB-skip:** spørr DB for hvilke onsdager vi ALLEREDE har, og hopper
   over dem. For 194 eksisterende rader sparer vi 194×3 = 582 HTTP-kall.
2. **Redusert pacing:** 1.5s → 0.7s. live.euronext.com er CDN-backed
   og tåler det fint.
3. **Cookie-warmup én gang totalt** (ikke per produkt).

Reuser eksisterende `fetch_html_for_date` + `parse_html_report` slik at
parsing-logikken er identisk med real-time-fetcheren.

Mål: 2018-01-01 → i dag (Euronext startet MiFID II-rapportering ifm.
2018). For 3 produkter × ~430 onsdager = ~1290 potensielle rader.
Subtrahere 582 vi har = ~700 nye HTTP-kall, ~500s = ~8 min.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill_euronext_optimized.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

from bedrock.data.schemas import COT_EURONEXT_COLS
from bedrock.data.store import DataStore
from bedrock.fetch.cot_euronext import (
    _EURONEXT_HOME,
    _HEADERS,
    DEFAULT_EURONEXT_PRODUCTS,
    fetch_html_for_date,
    parse_html_report,
)
from bedrock.signal_server.config import load_from_env

PACING_SEC = 0.7  # ned fra default 1.5
TIMEOUT = 20.0


def all_wednesdays(from_date: date, to_date: date) -> list[date]:
    """Generer alle onsdager mellom from og to (inklusive endepunktene hvis onsdag)."""
    out = []
    d = from_date
    # Finn første onsdag
    while d.weekday() != 2:
        d += timedelta(days=1)
        if d > to_date:
            return []
    while d <= to_date:
        out.append(d)
        d += timedelta(days=7)
    return out


def existing_dates_for_contract(con: sqlite3.Connection, contract: str) -> set[date]:
    rows = con.execute(
        "SELECT DISTINCT report_date FROM cot_euronext WHERE contract = ?",
        (contract,),
    ).fetchall()
    out = set()
    for r in rows:
        try:
            out.add(datetime.strptime(r[0][:10], "%Y-%m-%d").date())
        except (ValueError, TypeError):
            continue
    return out


def main() -> int:
    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    from_date = date(2018, 1, 1)
    to_date = date.today()

    print(f"Euronext optimalisert backfill {from_date} → {to_date}")
    print(f"Pacing: {PACING_SEC}s, timeout: {TIMEOUT}s")

    candidate_dates = all_wednesdays(from_date, to_date)
    print(f"Total onsdager i vinduet: {len(candidate_dates)}")

    sess = requests.Session()
    try:
        sess.get(_EURONEXT_HOME, headers=_HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"  cookie-warmup feilet: {exc}")

    con = sqlite3.connect(cfg.db_path)
    total_inserted = 0
    for spec in DEFAULT_EURONEXT_PRODUCTS:
        existing = existing_dates_for_contract(con, spec.contract)
        missing = [d for d in candidate_dates if d not in existing]
        print(f"\n{spec.label} ({spec.symbol}, {spec.contract}):")
        print(f"  eksisterende: {len(existing)} rader")
        print(f"  manglende:    {len(missing)} onsdager å hente")
        if not missing:
            continue

        rows: list[dict[str, Any]] = []
        t0 = time.time()
        for i, d in enumerate(missing):
            if i > 0:
                time.sleep(PACING_SEC)
            html = fetch_html_for_date(spec, d, session=sess, timeout=TIMEOUT)
            if html is None:
                continue
            parsed = parse_html_report(html)
            if not parsed:
                continue
            rows.append(
                {
                    "report_date": d.strftime("%Y-%m-%d"),
                    "contract": spec.contract,
                    "mm_long": parsed["mm_long"],
                    "mm_short": parsed["mm_short"],
                    "open_interest": parsed["open_interest"],
                }
            )
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                print(
                    f"    {i + 1}/{len(missing)} hentet ({len(rows)} rader, {elapsed:.0f}s)",
                    flush=True,
                )

        elapsed = time.time() - t0
        print(f"  {len(rows)} rader fra {len(missing)} forsøk på {elapsed:.0f}s")
        if rows:
            df = pd.DataFrame(rows, columns=list(COT_EURONEXT_COLS))
            inserted = store.append_cot_euronext(df)
            total_inserted += inserted
            print(f"  {inserted} rader inserted/replaced i DB")

    con.close()
    print(f"\n=== Totalt {total_inserted} rader backfilt ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
