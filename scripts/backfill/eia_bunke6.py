"""Backfill EIA-serier for sub-fase 12.10 Bunke 6 (#22).

Henter 7 nye EIA-serier for utvidede driver-overlays:
- WDISTUS1: Distillate Fuel Oil Stocks
- WPRSTUS1: Propane/Propylene Stocks
- WPULEUS3: Refiner Net Inputs of Crude Oil (proxy for utilization)
- WRPUPUS2: US Petroleum Products Supplied (Total)
- N9050US2: Natural Gas Processed (monthly — bruker route natural-gas/prod/sum)
- WCRIMUS2: Imports of Crude Oil
- WGFUPUS2: Finished Motor Gasoline Product Supplied (demand-proxy)

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/eia_bunke6.py
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from bedrock.config.secrets import require_secret
from bedrock.data.store import DataStore
from bedrock.fetch.eia_inventories import _SeriesSpec, fetch_eia_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

PACING_SECONDS = 1.5

# Routes-mapping: petroleum/stoc/wstk for ukentlige stocks; petroleum/cons/wpsup
# for products supplied; petroleum/move/wkly for imports; petroleum/pnp/wiup for
# refiner inputs; natural-gas/prod/sum for monthly natgas processed.
SERIES_TO_BACKFILL = (
    _SeriesSpec("WDISTUS1", "petroleum/stoc/wstk", "weekly", "US Distillate Fuel Oil Stocks"),
    _SeriesSpec("WPRSTUS1", "petroleum/stoc/wstk", "weekly", "US Propane/Propylene Stocks"),
    _SeriesSpec("WPULEUS3", "petroleum/pnp/wiup", "weekly", "US Refiner Net Inputs of Crude Oil"),
    _SeriesSpec(
        "WRPUPUS2", "petroleum/cons/wpsup", "weekly", "US Total Petroleum Products Supplied"
    ),
    _SeriesSpec("WCRIMUS2", "petroleum/move/wkly", "weekly", "US Imports of Crude Oil"),
    _SeriesSpec(
        "WGFUPUS2", "petroleum/cons/wpsup", "weekly", "US Finished Motor Gasoline Supplied"
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
    for i, spec in enumerate(SERIES_TO_BACKFILL):
        if i > 0:
            time.sleep(PACING_SECONDS)
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
            "[%d/%d] %s: %d rader (%s..%s)",
            i + 1,
            len(SERIES_TO_BACKFILL),
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
