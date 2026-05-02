"""Backfill data-kilder for sub-fase 12.10 Bunke 4 (Yahoo + CBOE + NOAA).

Per ADR-011 (10-år rolling cutoff, sekvensiell HTTP). Henter:

  Yahoo vol-indekser (#15):
    - ^MOVE: ICE BofA US Treasury MOVE Index (2003+, daglig)
    - ^VVIX: VIX of VIX (2007+, daglig)
    - ^GVZ: CBOE Gold ETF VIX (2008+, daglig)
    - ^OVX: CBOE Crude Oil VIX (2007+, daglig)

  CBOE indekser (#16) — via Yahoo (gratis):
    - ^SKEW: CBOE SKEW Index (1990+, daglig)
    - ^VXN, ^VXST: VXN + VIX-Short-Term (allerede har VIX9D fra session 131)
    Putt/call-ratios + VIX term curve hentes fra CBOE direkte (ikke Yahoo).
    Bunke 4 #16 leverer SKEW først; pcr/term_curve flagges DEFER.

  NOAA ENSO/PDO (#17) — via NOAA-tekstfiler (gratis):
    - ONI (Oceanic Niño Index): https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php
    - PDO Index: https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat
    For backfill her tar vi NOAA-tekstfilene direkte (ingen schema-endring).

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/bunke4_data.py
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.fetch.yahoo import YahooFetchError, fetch_yahoo_prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

# Yahoo-ticker → fundamentals series_id
YAHOO_TICKERS = {
    "^MOVE": "MOVE",
    "^VVIX": "VVIX",
    "^GVZ": "GVZ",
    "^OVX": "OVX",
    "^SKEW": "SKEW",
    "^VXN": "VXN",
}

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5


def backfill_yahoo_indices(store: DataStore, from_d: date, to_d: date) -> int:
    """Backfill Yahoo vol/skew-indekser til fundamentals-tabellen."""
    total = 0
    failed: list[tuple[str, str]] = []
    for i, (ticker, series_id) in enumerate(YAHOO_TICKERS.items()):
        if i > 0:
            time.sleep(PACING_SECONDS)
        try:
            df = fetch_yahoo_prices(ticker, from_date=from_d, to_date=to_d, interval="1d")
        except YahooFetchError as exc:
            _log.error("FAILED %s: %s", ticker, exc)
            failed.append((ticker, str(exc)))
            continue

        if df.empty:
            _log.warning("SKIP %s: tom", ticker)
            continue

        fund_df = pd.DataFrame(
            {
                "series_id": series_id,
                "date": df["ts"].dt.strftime("%Y-%m-%d"),
                "value": df["close"].astype("float64"),
            }
        )
        n = store.append_fundamentals(fund_df)
        total += n
        _log.info(
            "[%d/%d] %s → %s: %d rader (%s..%s)",
            i + 1,
            len(YAHOO_TICKERS),
            ticker,
            series_id,
            n,
            df["ts"].min().date(),
            df["ts"].max().date(),
        )

    if failed:
        _log.warning("Yahoo failures: %d", len(failed))
        for t, msg in failed:
            _log.warning("  %s: %s", t, msg)
    return total


def backfill_noaa_oni(store: DataStore) -> int:
    """Backfill NOAA Oceanic Niño Index (ONI) via tekstfil.

    URL: https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php
    Format: HTML-tabell med YEAR + DJF/JFM/.../NDJ-kolonner. Vi parser ut
    de 12 3-måneders-overlap-windows og lagrer som månedlig serie der
    en window-row gjelder midt-måneden. F.eks. DJF=Jan (mid).

    Forenklet: vi laster en CSV-versjon av ONI hvis tilgjengelig.
    Fallback: hardkodet siste-12-mnd-data fra public NOAA tekstkilden.
    """
    import requests

    # NOAA gjør CSV-versjon tilgjengelig på psl.noaa.gov
    url = "https://psl.noaa.gov/data/correlation/oni.data"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        _log.error("NOAA ONI fetch failed: %s", exc)
        return 0

    # Format: linje 1 = "1950 2026" (year range); deretter rader per år med
    # 12 månedlige verdier. Slutt-markør = -99.9 eller blank. Footer = metadata.
    lines = r.text.splitlines()
    rows: list[dict] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 13:
            continue
        try:
            year = int(parts[0])
        except ValueError:
            continue
        if year < 1950 or year > 2100:
            continue
        for month in range(1, 13):
            try:
                val = float(parts[month])
            except (ValueError, IndexError):
                continue
            if val <= -99:  # missing-marker
                continue
            d = date(year, month, 1)
            rows.append({"series_id": "ONI", "date": d.isoformat(), "value": val})

    if not rows:
        _log.warning("NOAA ONI: ingen rader parset")
        return 0

    df = pd.DataFrame(rows)
    n = store.append_fundamentals(df)
    _log.info(
        "NOAA ONI: %d rader (%s..%s)",
        n,
        df["date"].min(),
        df["date"].max(),
    )
    return n


def backfill_noaa_pdo(store: DataStore) -> int:
    """Backfill NOAA PDO Index. Same pattern as ONI."""
    import requests

    url = "https://psl.noaa.gov/data/correlation/pdo.data"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        _log.error("NOAA PDO fetch failed: %s", exc)
        return 0

    lines = r.text.splitlines()
    rows: list[dict] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 13:
            continue
        try:
            year = int(parts[0])
        except ValueError:
            continue
        if year < 1854 or year > 2100:
            continue
        for month in range(1, 13):
            try:
                val = float(parts[month])
            except (ValueError, IndexError):
                continue
            if val <= -99:
                continue
            d = date(year, month, 1)
            rows.append({"series_id": "PDO", "date": d.isoformat(), "value": val})

    if not rows:
        _log.warning("NOAA PDO: ingen rader parset")
        return 0

    df = pd.DataFrame(rows)
    n = store.append_fundamentals(df)
    _log.info(
        "NOAA PDO: %d rader (%s..%s)",
        n,
        df["date"].min(),
        df["date"].max(),
    )
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-noaa", action="store_true")
    args = parser.parse_args()

    today = date.today()
    to_d = today + timedelta(days=1)
    from_d = date(today.year - DEFAULT_LOOKBACK_YEARS, 1, 1)

    store = DataStore(Path(args.db))

    total = 0
    if not args.skip_yahoo:
        _log.info("=== Yahoo vol-indekser ===")
        total += backfill_yahoo_indices(store, from_d, to_d)

    if not args.skip_noaa:
        _log.info("=== NOAA ONI ===")
        total += backfill_noaa_oni(store)
        _log.info("=== NOAA PDO ===")
        total += backfill_noaa_pdo(store)

    _log.info("Total: %d rader", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
