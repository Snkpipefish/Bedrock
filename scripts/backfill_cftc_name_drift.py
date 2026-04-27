"""Tier 1 backfill: CFTC-kontrakt-navn-drift.

Per docs/data_gaps_2026-04.md har 8 instrumenter ufullstendig CFTC-COT
fordi CFTC har omdøpt kontrakter mid-historikk. For hver inst:
  1. Hent CFTC-data fra 2010-01-01 til i dag for ALLE kjente alias
  2. Append til DB
  3. Rename gamle navn til kanonisk navn (= det YAMLs peker på)

Etter kjøring: hver instrument har full historikk under kanonisk navn.

**Aliaser** er empirisk satt basert på CFTC-konvensjoner. Skript-logikk:
- CFTC-API returnerer tom liste hvis et navn ikke finnes i deres DB
- Vi prøver alle navn, lagrer det som kommer tilbake, sammenligner

Kjør (sekvensielt, ~30-60 min):
    PYTHONPATH=src .venv/bin/python scripts/backfill_cftc_name_drift.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import (
    CotFetchError,
    fetch_cot_disaggregated,
    fetch_cot_legacy,
)
from bedrock.signal_server.config import load_from_env

# (instrument_id, report_type, canonical_name, [aliases including canonical])
# Canonical = navn YAML peker på (eller bør peke på etter migrasjon).
# Aliases inkluderer canonical + historiske CFTC-navn for samme kontrakt.
TIER_1_BACKFILL: list[tuple[str, str, str, list[str]]] = [
    # CrudeOil — gammelt "LIGHT SWEET" + nytt "LIGHT SWEET-WTI"
    (
        "CrudeOil",
        "disaggregated",
        "CRUDE OIL, LIGHT SWEET-WTI - NEW YORK MERCANTILE EXCHANGE",
        [
            "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
            "CRUDE OIL, LIGHT SWEET-WTI - NEW YORK MERCANTILE EXCHANGE",
        ],
    ),
    # SP500 — "STOCK INDEX" → fjernet "STOCK INDEX" suffix
    (
        "SP500",
        "legacy",
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        [
            "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE",
            "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        ],
    ),
    # Wheat — "WHEAT" → "WHEAT-SRW" (når SRW = Soft Red Winter ble eksplisitt)
    (
        "Wheat",
        "disaggregated",
        "WHEAT-SRW - CHICAGO BOARD OF TRADE",
        [
            "WHEAT - CHICAGO BOARD OF TRADE",
            "WHEAT-SRW - CHICAGO BOARD OF TRADE",
        ],
    ),
    # Nasdaq — "(MINI)" → "Consolidated"
    (
        "Nasdaq",
        "legacy",
        "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        [
            "NASDAQ-100 STOCK INDEX (MINI) - CHICAGO MERCANTILE EXCHANGE",
            "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        ],
    ),
    # NaturalGas — antar gammel "NATURAL GAS" + ny "NAT GAS NYME"
    (
        "NaturalGas",
        "disaggregated",
        "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",
        [
            "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE",
            "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",
        ],
    ),
    # Brent — bare ett navn, men vi mangler 2018-2022 — backfill samme navn
    (
        "Brent",
        "disaggregated",
        "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE",
        [
            "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE",
        ],
    ),
    # Copper — bare ett navn, mangler 2010-2022
    (
        "Copper",
        "disaggregated",
        "COPPER- #1 - COMMODITY EXCHANGE INC.",
        [
            "COPPER- #1 - COMMODITY EXCHANGE INC.",
            "COPPER - #1 - COMMODITY EXCHANGE INC.",  # alternativ space
        ],
    ),
    # GBPUSD — bare ett navn, mangler 2010-2022
    (
        "GBPUSD",
        "legacy",
        "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
        [
            "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
            "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE",  # mulig alternativ
        ],
    ),
]

START_DATE = date(2010, 1, 1)
END_DATE = date.today()


def fetch_for_alias(
    contract: str, report_type: str, from_date: date, to_date: date
) -> pd.DataFrame:
    """Wrapper rundt fetch_cot_*. Returnerer tom DF ved feil."""
    try:
        if report_type == "disaggregated":
            return fetch_cot_disaggregated(contract, from_date, to_date)
        elif report_type == "legacy":
            return fetch_cot_legacy(contract, from_date, to_date)
        else:
            raise ValueError(f"Unknown report_type: {report_type}")
    except CotFetchError as exc:
        print(f"  ! fetch-feil {contract!r}: {exc}")
        return pd.DataFrame()


def append_to_db(store: DataStore, df: pd.DataFrame, report_type: str) -> int:
    """Append til riktig tabell. Returnerer antall innsatte rader."""
    if df.empty:
        return 0
    if report_type == "disaggregated":
        return store.append_cot_disaggregated(df)
    elif report_type == "legacy":
        return store.append_cot_legacy(df)
    else:
        raise ValueError(f"Unknown report_type: {report_type}")


def rename_in_db(
    db_path: Path,
    report_type: str,
    canonical: str,
    aliases: list[str],
) -> int:
    """Rename alle aliases (utenom canonical) til canonical i DB.

    Bruker INSERT OR IGNORE for å unngå PK-konflikt hvis canonical og
    alias har overlapping report_dates. Sletter alias-rader etter merge.
    """
    from bedrock.data.schemas import COT_DISAGGREGATED_COLS, COT_LEGACY_COLS

    if report_type == "disaggregated":
        table = "cot_disaggregated"
        cols = COT_DISAGGREGATED_COLS
    else:
        table = "cot_legacy"
        cols = COT_LEGACY_COLS

    # Bygg SELECT-list: bytt 'contract' med ?-parameter (canonical)
    select_cols = []
    for c in cols:
        if c == "contract":
            select_cols.append("?")
        else:
            select_cols.append(c)
    select_clause = ", ".join(select_cols)
    insert_clause = ", ".join(cols)

    con = sqlite3.connect(db_path)
    total_renamed = 0
    try:
        for alias in aliases:
            if alias == canonical:
                continue
            n_alias = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE contract = ?", (alias,)
            ).fetchone()[0]
            if n_alias == 0:
                continue
            print(f"  Migrer {n_alias} rader: {alias!r} → {canonical!r}")
            con.execute(
                f"INSERT OR IGNORE INTO {table} ({insert_clause}) "
                f"SELECT {select_clause} FROM {table} WHERE contract = ?",
                (canonical, alias),
            )
            con.execute(f"DELETE FROM {table} WHERE contract = ?", (alias,))
            total_renamed += n_alias
        con.commit()
    finally:
        con.close()
    return total_renamed


def process_instrument(
    store: DataStore,
    instrument: str,
    report_type: str,
    canonical: str,
    aliases: list[str],
) -> dict:
    """Backfill alle alias for én instrument, merge til canonical."""
    print(f"\n=== {instrument} ({report_type}) ===")
    print(f"  Canonical: {canonical}")
    print(f"  Aliases: {aliases}")

    fetched: dict[str, int] = {}
    for alias in aliases:
        print(f"  Henter {alias!r} {START_DATE} → {END_DATE} ...")
        t0 = time.time()
        df = fetch_for_alias(alias, report_type, START_DATE, END_DATE)
        elapsed = time.time() - t0
        n_rows = len(df)
        fetched[alias] = n_rows
        print(f"    {n_rows} rader på {elapsed:.1f}s")
        if not df.empty:
            inserted = append_to_db(store, df, report_type)
            print(f"    {inserted} append/replaced i DB")
        # Vær snill mot CFTC-API (rate limit)
        time.sleep(2)

    # Etter alle aliaser er fetchet og lagret, merge til canonical
    cfg = load_from_env()
    renamed = rename_in_db(cfg.db_path, report_type, canonical, aliases)
    print(f"  Total renamed til canonical: {renamed}")

    return {
        "instrument": instrument,
        "fetched_per_alias": fetched,
        "renamed_to_canonical": renamed,
    }


def main() -> int:
    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    print("Tier 1 CFTC-name-drift backfill")
    print(f"DB: {cfg.db_path}")
    print(f"Periode: {START_DATE} → {END_DATE}")
    print(f"Instrumenter: {len(TIER_1_BACKFILL)}")
    print()

    results: list[dict] = []
    for inst, report_type, canonical, aliases in TIER_1_BACKFILL:
        try:
            r = process_instrument(store, inst, report_type, canonical, aliases)
            results.append(r)
        except Exception as e:
            print(f"  !! FEIL for {inst}: {e}")

    # Sammendrag
    print("\n=== Sammendrag ===")
    for r in results:
        per_alias_str = ", ".join(f"{k}: {v}" for k, v in r["fetched_per_alias"].items())
        print(f"{r['instrument']:12s}: {per_alias_str} | renamed={r['renamed_to_canonical']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
