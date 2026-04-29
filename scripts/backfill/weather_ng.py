"""Backfill weather for NaturalGas-relevante consumption-regioner (B4 D2).

Sub-fase 12.7 D2 B4 (session 131). Engangs-skript per ADR-011 (10-år
rolling cutoff). Bruker eksisterende `bedrock.fetch.weather`-fetcher mot
Open-Meteo Archive (gratis, ingen auth).

3 NG-relevante populasjons-veide regioner:
- us_ng_ne (Northeast USA): NYC ~40.71°N, -74.01°W. Bruker NYC som proxy
  for NE-USA gas-residential-consumption.
- us_ng_tx_la (Texas/Louisiana): Houston ~29.76°N, -95.37°W. Proxy for
  Gulf Coast gas-cooling/industrial-demand.
- us_ng_midwest (Chicago): ~41.85°N, -87.65°W. Proxy for Midwest
  agricultural + residential heating.

`hdd_cdd_anomaly`-driver (B4) populasjons-veier disse 3 regionene per
default for å beregne aggregert HDD/CDD-anomaly mot sesong-norm.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from bedrock.data.store import DataStore
from bedrock.fetch.weather import WeatherFetchError, fetch_weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

# region → (latitude, longitude) for default NG-regioner
NG_REGIONS: list[tuple[str, float, float]] = [
    ("us_ng_ne", 40.71, -74.01),  # NYC (NE-USA proxy)
    ("us_ng_tx_la", 29.76, -95.37),  # Houston (TX/LA proxy)
    ("us_ng_midwest", 41.85, -87.65),  # Chicago (Midwest proxy)
]

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help=f"Start-dato (YYYY-MM-DD). Default: {DEFAULT_LOOKBACK_YEARS} år tilbake.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        help="Slutt-dato (YYYY-MM-DD). Default: i dag.",
    )
    args = parser.parse_args()

    today = date.today()
    to_d = date.fromisoformat(args.to_date) if args.to_date else today
    from_d = (
        date.fromisoformat(args.from_date)
        if args.from_date
        else date(today.year - DEFAULT_LOOKBACK_YEARS, 1, 1)
    )

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error(f"DB ikke funnet: {db_path}")
        return 1

    store = DataStore(db_path)
    _log.info(
        "Backfill B4 NG-weather: %d regioner, %s → %s, db=%s",
        len(NG_REGIONS),
        from_d,
        to_d,
        db_path,
    )

    total_rows = 0
    for i, (region, lat, lon) in enumerate(NG_REGIONS):
        if i > 0:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_weather(region, lat, lon, from_d, to_d)
        except WeatherFetchError as exc:
            _log.error("FAILED %s: %s", region, exc)
            continue

        if df.empty:
            _log.warning("SKIP %s: tom DataFrame", region)
            continue

        n = store.append_weather(df)
        total_rows += n
        _log.info(
            "[%d/%d] %s @ (%.2f, %.2f): %d rader (%s..%s)",
            i + 1,
            len(NG_REGIONS),
            region,
            lat,
            lon,
            n,
            df["date"].min(),
            df["date"].max(),
        )

    _log.info("Ferdig: %d rader skrevet totalt.", total_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
