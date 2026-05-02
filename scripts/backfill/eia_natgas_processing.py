"""Backfill EIA NGPL Production (monthly) for sub-fase 12.10 follow-up Spor F8.

Henter:
- N9060US2: US Natural Gas Plant Liquids Production, Gaseous Equivalent
  (route natural-gas/prod/sum, frequency=monthly)

NGPL-extraction-volumet er vår F8-natgas-processing-throughput-proxy.
Bunke6 (#22) leverte 6 weekly petroleum-serier; F8 fyller gjenstående
DEFERRED-driver med tilsvarende thin-wrapper-pattern.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/eia_natgas_processing.py
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.eia_inventories import _SeriesSpec, fetch_eia_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

SERIES_TO_BACKFILL = (
    _SeriesSpec(
        "N9060US2",
        "natural-gas/prod/sum",
        "monthly",
        "US NGPL Production, Gaseous Equivalent (MMcf)",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/bedrock.db")
    args = parser.parse_args()

    api_key = require_secret("BEDROCK_EIA_API_KEY")
    store = DataStore(Path(args.db))

    total = 0
    failed: list[tuple[str, str]] = []
    for spec in SERIES_TO_BACKFILL:
        try:
            df = fetch_eia_series(spec, api_key)
        except Exception as exc:
            _log.error("FAILED %s: %s", spec.series_id, exc)
            failed.append((spec.series_id, str(exc)))
            continue

        if df.empty:
            _log.warning("SKIP %s: tom DataFrame", spec.series_id)
            continue

        n = store.append_eia_inventory(df)
        total += n
        _log.info(
            "%s: %d rader (%s..%s)",
            spec.series_id,
            n,
            df["date"].min(),
            df["date"].max(),
        )

    _log.info("Total: %d rader", total)
    if failed:
        _log.warning("Failed: %d serier", len(failed))
        for sid, msg in failed:
            _log.warning("  %s: %s", sid, msg)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
