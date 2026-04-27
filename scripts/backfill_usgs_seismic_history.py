"""USGS seismic historisk backfill 2010+ via FDSN-API.

USGS sin FDSN-API (https://earthquake.usgs.gov/fdsnws/event/1/) tillater
date-range queries med `starttime`/`endtime`. Vi paginerer år-for-år
(globalt M≥4.5 er ~10000 events/år, godt under FDSN's 20 000-limit per
request).

Reuser eksisterende `parse_usgs_geojson` fra `bedrock/fetch/seismic.py`
slik at parsing-logikken (region-detektering, schema-mapping) er
identisk med real-time-fetcheren.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill_usgs_seismic_history.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import sys
import time
from datetime import datetime

from bedrock.data.store import DataStore
from bedrock.fetch.base import http_get_with_retry
from bedrock.fetch.seismic import _HEADERS, parse_usgs_geojson
from bedrock.signal_server.config import load_from_env

USGS_FDSN_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_year(year: int, min_magnitude: float = 4.5) -> int:
    """Hent alle events for ett år og append til DB. Returnerer antall rader."""
    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    starttime = f"{year}-01-01T00:00:00"
    endtime = f"{year}-12-31T23:59:59"
    params = {
        "format": "geojson",
        "starttime": starttime,
        "endtime": endtime,
        "minmagnitude": str(min_magnitude),
        "orderby": "time-asc",
    }
    url = f"{USGS_FDSN_BASE}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    print(f"  Henter {year} (M≥{min_magnitude}) ...", flush=True)
    t0 = time.time()
    try:
        resp = http_get_with_retry(url, headers=_HEADERS, timeout=120.0)
    except Exception as exc:
        print(f"    ✗ HTTP-feil: {exc}", flush=True)
        return 0
    if resp.status_code != 200:
        print(f"    ✗ HTTP {resp.status_code}", flush=True)
        return 0
    try:
        payload = resp.json()
    except Exception as exc:
        print(f"    ✗ JSON-parse: {exc}", flush=True)
        return 0
    df = parse_usgs_geojson(payload)
    fetch_elapsed = time.time() - t0
    print(
        f"    {len(df)} events parsed på {fetch_elapsed:.1f}s "
        f"({df['region'].notna().sum() if not df.empty else 0} i mining-regions)",
        flush=True,
    )
    if df.empty:
        return 0
    inserted = store.append_seismic_events(df)
    print(f"    {inserted} rader inserted/replaced i DB", flush=True)
    return inserted


def main() -> int:
    from_year = 2010
    to_year = datetime.now().year
    print(f"USGS seismic historisk backfill {from_year}-{to_year}")
    print("Min magnitude: 4.5")
    total = 0
    for year in range(from_year, to_year + 1):
        total += fetch_year(year)
        time.sleep(2)  # USGS FDSN er åpen, men vær snill
    print(f"\n=== Totalt {total} events backfilt ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
