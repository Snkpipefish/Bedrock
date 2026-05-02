"""Re-backfill swap_long/short + conc_net_top4/8 på cot_disaggregated.

Spor F5 (sub-fase 12.10 follow-up). Eksisterende rader i cot_disaggregated
har NULL i de nye Spor F5-kolonnene. Dette scriptet:

1. Henter listen over distincte contracts som finnes i tabellen.
2. For hver contract: fetcher hele historikken (default 5 år) fra CFTC
   med utvidet field_map (inkluderer swap_* + conc_net_*).
3. Kaller `store.append_cot_disaggregated(df)` — UPDATE-passet i Spor F5
   populerer de nye kolonnene på eksisterende (report_date, contract)-PK
   uten å overskrive andre felter.

Sekvensiell mot CFTC Socrata per memory-feedback (gratis-API). Pacing
mellom kall via samme http_get_with_retry-defaults som fetch_runner.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill/cot_disaggregated_metadata.py
    PYTHONPATH=src .venv/bin/python scripts/backfill/cot_disaggregated_metadata.py \\
        --years 10 --contract "GOLD - COMMODITY EXCHANGE INC."
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

from bedrock.data.schemas import TABLE_COT_DISAGGREGATED
from bedrock.data.store import DataStore
from bedrock.fetch.cot_cftc import CotFetchError, fetch_cot_disaggregated

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

PACING_SECONDS = 1.0


def _list_contracts(db_path: Path) -> list[str]:
    """SELECT DISTINCT contract FROM cot_disaggregated."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT DISTINCT contract FROM {TABLE_COT_DISAGGREGATED} ORDER BY contract"
        )
        return [row[0] for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/bedrock.db")
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Hvor mange år bakover å re-fetche (default 5; CFTC har data fra 2010)",
    )
    parser.add_argument(
        "--contract",
        default=None,
        help="Begrens til ett contract (default: alle distincte i DB)",
    )
    args = parser.parse_args()

    db = Path(args.db)
    contracts = [args.contract] if args.contract else _list_contracts(db)
    if not contracts:
        _log.warning("Ingen contracts funnet i %s", TABLE_COT_DISAGGREGATED)
        return 0

    _log.info("Re-backfiller %d contracts (%d år historikk)", len(contracts), args.years)

    today = date.today()
    from_date = today - timedelta(days=365 * args.years)

    store = DataStore(db)

    total_rows = 0
    failed: list[tuple[str, str]] = []
    for i, contract in enumerate(contracts):
        if i > 0:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_cot_disaggregated(contract, from_date, today)
        except CotFetchError as exc:
            _log.error("FAIL %s: %s", contract, exc)
            failed.append((contract, str(exc)))
            continue
        except Exception as exc:
            _log.error("FAIL %s: unexpected: %s", contract, exc)
            failed.append((contract, str(exc)))
            continue

        if df.empty:
            _log.warning("SKIP %s: tom respons", contract)
            continue

        n = store.append_cot_disaggregated(df)
        total_rows += n
        non_null_swap = int(df["swap_long"].notna().sum())
        non_null_conc = int(df["conc_net_top4"].notna().sum())
        _log.info(
            "[%d/%d] %s: %d rader (swap_non_null=%d, conc_non_null=%d)",
            i + 1,
            len(contracts),
            contract,
            n,
            non_null_swap,
            non_null_conc,
        )

    _log.info("Total: %d rader oppdatert. Failed: %d", total_rows, len(failed))
    for contract, msg in failed:
        _log.warning("  %s: %s", contract, msg)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
