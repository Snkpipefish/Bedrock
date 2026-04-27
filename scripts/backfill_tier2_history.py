"""Tier 2 historisk backfill: ICE-COT 2010-2024 + utvidede Euronext/CONAB.

Per docs/data_gaps_2026-04.md Tier 2:

1. **cot_ice**: nåværende har 2025-2026 (68 uker). ICE Public Reports-arkiv
   inneholder COTHist<YEAR>.csv for tidligere år. Iterer 2010-2024 og
   append. Eksisterende `fetch_cot_ice_remote(year=N)` støtter dette
   direkte.

2. **cot_euronext**: nåværende 15 rader. Re-fetch med `n=200` (4 år)
   istedenfor default `n=6` (~6 uker).

3. **conab_estimates**: nåværende 7 rader. CONAB har månedlige PDF-er
   tilbake til 2017+. Walker måneder bakover via `find_pdf_on_index`.

4. **unica_reports**: nåværende 1 rad. UNICA har halvmånedlige PDF-er
   tilbake til 2010+.

Sekvensielle HTTP-requests per memory-feedback (free-API-etiquette).

Kjør (sekvensielt, kan ta 1-2 timer):
    PYTHONPATH=src .venv/bin/python scripts/backfill_tier2_history.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import argparse
import sqlite3
import sys
import time

from bedrock.data.store import DataStore
from bedrock.fetch import cot_euronext, cot_ice
from bedrock.signal_server.config import load_from_env

# ---------------------------------------------------------------------------
# Tier 2.1: cot_ice historikk 2010-2024
# ---------------------------------------------------------------------------


def backfill_cot_ice_history(store: DataStore, from_year: int = 2010, to_year: int = 2024) -> int:
    """Hent COTHist<YEAR>.csv per år og append til DB. Returnerer total rader."""
    print(f"\n=== Tier 2.1: cot_ice historikk {from_year}-{to_year} ===")
    total_inserted = 0
    for year in range(from_year, to_year + 1):
        print(f"  Henter COTHist{year}.csv ...")
        try:
            t0 = time.time()
            df = cot_ice.fetch_cot_ice_remote(year=year)
            elapsed = time.time() - t0
            n = len(df)
            print(
                f"    {n} rader på {elapsed:.1f}s ({df['contract'].nunique() if n else 0} kontrakter)"
            )
            if n > 0:
                inserted = store.append_cot_ice(df)
                total_inserted += inserted
                print(f"    {inserted} rader inserted/replaced i DB")
        except ValueError as exc:
            print(f"    ✗ feilet: {exc}")
        # Vær snill mot ICE
        time.sleep(2)
    return total_inserted


# ---------------------------------------------------------------------------
# Tier 2.2: cot_euronext historikk
# ---------------------------------------------------------------------------


def backfill_cot_euronext_history(store: DataStore, n_weeks: int = 200) -> int:
    """Re-fetch Euronext med utvidet `n` for å gå lenger bakover.

    Bruker `recent_wednesdays(n_weeks)` for å iterere ~4 års onsdager.
    """
    print(f"\n=== Tier 2.2: cot_euronext historikk (n_wednesdays={n_weeks}) ===")
    try:
        df = cot_euronext.fetch_cot_euronext(n_wednesdays=n_weeks)
        n = len(df)
        print(f"  {n} rader hentet ({df['contract'].nunique() if n else 0} kontrakter)")
        if n > 0:
            inserted = store.append_cot_euronext(df)
            print(f"  {inserted} rader inserted/replaced i DB")
            return inserted
    except Exception as exc:
        print(f"  ✗ feilet: {exc}")
    return 0


# ---------------------------------------------------------------------------
# Tier 2.3: CONAB månedlige rapporter (PDF-walker)
# ---------------------------------------------------------------------------


def backfill_conab_history(store: DataStore, from_year: int = 2017, to_year: int = 2026) -> int:
    """CONAB-historikk via gov.br-arkiv. Walker hver mnd's report.

    Conab publiserer 'Boletim Levantamento' månedlig. Vi har ikke en
    pre-computed liste over historiske URL-er, men gov.br holder dem
    på samme paginerte index.

    Pragmatisk: bruker eksisterende `fetch_conab` for grains + cafe og
    setter `levantamento` til hver mnd vi vil ha. Hvis fetcheren ikke
    støtter historisk-mode direkte, hopper vi denne for nå og marker
    som follow-up.
    """
    print(f"\n=== Tier 2.3: conab historikk (planlagt {from_year}-{to_year}) ===")
    print("  ⏸ utsatt: krever ny historisk-walker for gov.br-PDF-arkiv.")
    print("    Eksisterende fetch_conab er hard-kodet til siste rapport.")
    print("    Behov: lese conab.gov.br/info-agro/safras/graos for hver tidligere mnd")
    print("    Estimat: 2-3 timer kode for paginerings-walker. Se follow-up.")
    return 0


# ---------------------------------------------------------------------------
# Tier 2.4: UNICA halvmånedlige (PDF-walker)
# ---------------------------------------------------------------------------


def backfill_unica_history(store: DataStore, from_year: int = 2010, to_year: int = 2026) -> int:
    """UNICA-historikk via unicadata.com.br-arkiv."""
    print(f"\n=== Tier 2.4: unica historikk (planlagt {from_year}-{to_year}) ===")
    print("  ⏸ utsatt: krever ny historisk-walker for unicadata.com.br-arkiv.")
    print("    Eksisterende fetch_unica er hard-kodet til siste rapport.")
    print("    Behov: enumerate quinzenas (~370 rapporter for 2010-2026)")
    print("    Estimat: 2-3 timer kode + ~2 timer kjøring. Se follow-up.")
    return 0


# ---------------------------------------------------------------------------
# Sammendrag
# ---------------------------------------------------------------------------


def report_state(db_path) -> None:
    con = sqlite3.connect(db_path)
    print("\n=== Tabell-status etter Tier 2 ===")
    for tbl, ts_col in [
        ("cot_ice", "report_date"),
        ("cot_euronext", "report_date"),
        ("conab_estimates", "report_date"),
        ("unica_reports", "report_date"),
    ]:
        try:
            row = con.execute(
                f"SELECT MIN({ts_col}), MAX({ts_col}), COUNT(*) FROM {tbl}"
            ).fetchone()
            print(f"  {tbl:25s}: {row[0]} -> {row[1]} ({row[2]} rader)")
        except sqlite3.OperationalError as e:
            print(f"  {tbl}: {e}")
    con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cot-ice-from", type=int, default=2010)
    parser.add_argument("--cot-ice-to", type=int, default=2024)
    parser.add_argument("--euronext-n", type=int, default=200)
    parser.add_argument("--skip-cot-ice", action="store_true")
    parser.add_argument("--skip-euronext", action="store_true")
    parser.add_argument("--skip-conab", action="store_true")
    parser.add_argument("--skip-unica", action="store_true")
    args = parser.parse_args()

    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    print(f"Tier 2 backfill — DB: {cfg.db_path}")

    if not args.skip_cot_ice:
        backfill_cot_ice_history(store, args.cot_ice_from, args.cot_ice_to)
    if not args.skip_euronext:
        backfill_cot_euronext_history(store, args.euronext_n)
    if not args.skip_conab:
        backfill_conab_history(store)
    if not args.skip_unica:
        backfill_unica_history(store)

    report_state(cfg.db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
