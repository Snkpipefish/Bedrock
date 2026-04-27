"""Harvester for globale features per ref_date — for kryss-asset-analyse.

Utfyller `driver_observations` (per-instrument scoring) med en flat
long-format tabell `feature_snapshots` som inneholder ALL global
markeds-state ved hver ref_date. Brukes til å beregne kryss-asset-
korrelasjoner: f.eks. "påvirker oljepris fwd-return for sukker?",
"hvor sterkt predikerer DXY fwd-return for Gold vs EURUSD?",
"har BDI-endring forklaring på Wheat-utviklingen?".

Lagret features per ref_date:

- ``price.<inst>``: close-pris for hvert av 22 instrumenter
- ``fred.<series_id>``: makro-tidsserier (DGS10, T10YIE, DTWEXBGS,
  VIXCLS, DEXBZUS = USD/BRL)
- ``shipping.<index>``: BDI/BCI/BPI/BSI
- ``enso.oni``: ENSO Oceanic Niño Index
- ``cot.mm_net_pct.<contract>``: CFTC managed-money net % per kontrakt
  (henter siste rapport på/før ref_date)
- ``wasde.s2u.<commodity>``: WASDE stocks-to-use ratio US/global
- ``crop_progress.<commodity>.<metric>``: NASS crop progress (planted,
  silking, harvested, good_excellent)

Idempotent skriving: PRIMARY KEY (ref_date, feature_key). Resumable.

Kjør:

    PYTHONPATH=src .venv/bin/python scripts/harvest_feature_snapshots.py \\
        --step-days 7 --from-date 2010-01-01

Wall-time: ~4000 dager × ~30 SQL-queries × ~10ms ≈ 20-30 min for full
historikk.
"""
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore
from bedrock.signal_server.config import load_from_env

ALL_INSTRUMENTS: list[str] = [
    "EURUSD",
    "USDJPY",
    "GBPUSD",
    "AUDUSD",
    "Gold",
    "Silver",
    "Copper",
    "Platinum",
    "CrudeOil",
    "Brent",
    "NaturalGas",
    "SP500",
    "Nasdaq",
    "Corn",
    "Wheat",
    "Soybean",
    "Cotton",
    "Sugar",
    "Coffee",
    "Cocoa",
    "BTC",
    "ETH",
]

# FRED-serier som drivere bruker
FRED_SERIES: list[str] = [
    "DGS10",  # 10y nominal
    "T10YIE",  # 10y breakeven inflation
    "DTWEXBGS",  # broad USD index
    "VIXCLS",  # VIX close
    "DEXBZUS",  # USD/BRL
]

SHIPPING_CODES: list[str] = ["BDI", "BCI", "BPI", "BSI"]

# CFTC-kontrakter for hvert instrument (matcher YAMLs `cot_contract`)
COT_CONTRACTS: dict[str, tuple[str, str]] = {
    "Gold": ("GOLD - COMMODITY EXCHANGE INC.", "disaggregated"),
    "Silver": ("SILVER - COMMODITY EXCHANGE INC.", "disaggregated"),
    "Copper": ("COPPER- #1 - COMMODITY EXCHANGE INC.", "disaggregated"),
    "Platinum": ("PLATINUM - NEW YORK MERCANTILE EXCHANGE", "disaggregated"),
    "CrudeOil": ("CRUDE OIL, LIGHT SWEET-WTI - NEW YORK MERCANTILE EXCHANGE", "disaggregated"),
    "Brent": ("BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE", "disaggregated"),
    "NaturalGas": ("NATURAL GAS - NEW YORK MERCANTILE EXCHANGE", "disaggregated"),
    "Corn": ("CORN - CHICAGO BOARD OF TRADE", "disaggregated"),
    "Wheat": ("WHEAT-SRW - CHICAGO BOARD OF TRADE", "disaggregated"),
    "Soybean": ("SOYBEANS - CHICAGO BOARD OF TRADE", "disaggregated"),
    "Cotton": ("COTTON NO. 2 - ICE FUTURES U.S.", "disaggregated"),
    "Sugar": ("SUGAR NO. 11 - ICE FUTURES U.S.", "disaggregated"),
    "Coffee": ("COFFEE C - ICE FUTURES U.S.", "disaggregated"),
    "Cocoa": ("COCOA - ICE FUTURES U.S.", "disaggregated"),
    "SP500": ("E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "Nasdaq": ("NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "EURUSD": ("EURO FX - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "GBPUSD": ("BRITISH POUND - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "USDJPY": ("JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "AUDUSD": ("AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "BTC": ("BITCOIN - CHICAGO MERCANTILE EXCHANGE", "legacy"),
    "ETH": ("MICRO ETHER - CHICAGO MERCANTILE EXCHANGE", "legacy"),
}

DDL_FEATURE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS feature_snapshots (
    ref_date TEXT NOT NULL,
    feature_key TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (ref_date, feature_key)
);
CREATE INDEX IF NOT EXISTS idx_feat_snap_lookup
    ON feature_snapshots (feature_key, ref_date);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(DDL_FEATURE_SNAPSHOTS)
    con.commit()


def already_done_dates(con: sqlite3.Connection) -> set[str]:
    """Returner set av ref_dates som har minst én feature lagret."""
    rows = con.execute("SELECT DISTINCT ref_date FROM feature_snapshots").fetchall()
    return {r[0] for r in rows}


def _safe_last_value(series_or_df, value_col: str | None = None) -> float | None:
    """Returner siste numerisk verdi fra Series/DataFrame, eller None."""
    if series_or_df is None:
        return None
    if isinstance(series_or_df, pd.DataFrame):
        if series_or_df.empty:
            return None
        if value_col is None:
            # Default: ta close-kolonnen for OHLCV
            value_col = "close" if "close" in series_or_df.columns else series_or_df.columns[-1]
        try:
            v = series_or_df[value_col].iloc[-1]
        except (KeyError, IndexError):
            return None
    else:
        if series_or_df.empty:
            return None
        v = series_or_df.iloc[-1]
    try:
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def collect_features_at_date(store: DataStore, ref_ts: pd.Timestamp) -> dict[str, float]:
    """Bygg dict over alle features som finnes på ref_ts. Stille om
    KeyError eller manglende data."""
    view = AsOfDateStore(store, ref_ts)
    out: dict[str, float] = {}

    # Prices (close) per instrument
    for inst in ALL_INSTRUMENTS:
        try:
            ohlc = view.get_prices_ohlc(inst, tf="D1", lookback=1)
            v = _safe_last_value(ohlc, value_col="close")
            if v is not None:
                out[f"price.{inst}"] = v
        except KeyError:
            continue

    # FRED makro-serier
    for series_id in FRED_SERIES:
        try:
            s = view.get_fundamentals(series_id, last_n=1)
            v = _safe_last_value(s)
            if v is not None:
                out[f"fred.{series_id}"] = v
        except KeyError:
            continue

    # Shipping indices
    for code in SHIPPING_CODES:
        try:
            s = view.get_shipping_index(code, last_n=1)
            v = _safe_last_value(s)
            if v is not None:
                out[f"shipping.{code}"] = v
        except KeyError:
            continue

    # COT MM net % per kontrakt
    for inst, (contract, report) in COT_CONTRACTS.items():
        try:
            df = view.get_cot(contract, report=report, last_n=1)
            if df.empty:
                continue
            row = df.iloc[-1]
            mm_long = float(row.get("mm_long", 0) or 0)
            mm_short = float(row.get("mm_short", 0) or 0)
            oi = float(row.get("open_interest", 0) or 0)
            if oi > 0:
                mm_net_pct = (mm_long - mm_short) / oi * 100.0
                out[f"cot.mm_net_pct.{inst}"] = mm_net_pct
        except KeyError:
            continue

    return out


def harvest(
    *,
    db_path: Path,
    from_date: date | None,
    to_date: date | None,
    step_days: int,
    progress_every: int = 50,
) -> int:
    """Walk ref_dates fra den dagen prisene starter (eller from_date) og
    snapshot features. Returnerer antall nye rader."""
    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    # Bruk Gold-prices som "master calendar" — Gold har lengst kontinuerlig
    # historikk i bedrock.db. Andre instrumenter har egne start-datoer
    # men det er OK fordi feature-getterne returnerer KeyError som vi
    # håndterer stille.
    try:
        master_prices = store.get_prices("Gold", tf="D1")
    except KeyError:
        print("FEIL: ingen Gold-prices i DB — kan ikke bygge ref_date-kalender")
        return 0

    dates_idx = master_prices.index
    if from_date is not None:
        dates_idx = dates_idx[dates_idx >= pd.Timestamp(from_date)]
    if to_date is not None:
        dates_idx = dates_idx[dates_idx <= pd.Timestamp(to_date)]
    if step_days > 1:
        dates_idx = dates_idx[::step_days]

    print(
        f"Master-kalender: {len(dates_idx)} ref_dates "
        f"({dates_idx.min().date()} .. {dates_idx.max().date()})"
    )

    con = sqlite3.connect(db_path)
    ensure_schema(con)
    done = already_done_dates(con)
    print(f"Allerede done: {len(done)} ref_dates")

    todo_dates = [ts for ts in dates_idx if ts.strftime("%Y-%m-%d") not in done]
    print(f"Skal harveste: {len(todo_dates)} ref_dates\n")

    new_rows = 0
    t0 = time.time()
    for i, ref_ts in enumerate(todo_dates, start=1):
        ref_date_str = ref_ts.strftime("%Y-%m-%d")
        try:
            features = collect_features_at_date(store, ref_ts)
        except Exception as e:
            print(f"  [{ref_date_str}] feilet: {e}", flush=True)
            continue

        if features:
            rows = [(ref_date_str, key, val) for key, val in features.items()]
            con.executemany(
                "INSERT OR IGNORE INTO feature_snapshots (ref_date, feature_key, value) "
                "VALUES (?, ?, ?)",
                rows,
            )
            con.commit()
            new_rows += len(rows)

        if i % progress_every == 0:
            elapsed = time.time() - t0
            eta_min = (elapsed / i) * (len(todo_dates) - i) / 60
            print(
                f"  {i}/{len(todo_dates)} ({ref_date_str})  "
                f"+{new_rows} rows  ({elapsed:5.1f}s, ETA {eta_min:5.1f}min)",
                flush=True,
            )

    con.close()
    elapsed = time.time() - t0
    print(f"\nFerdig: +{new_rows} rader på {elapsed / 60:.1f} min")
    return new_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--step-days", type=int, default=7)
    args = parser.parse_args()

    cfg = load_from_env()
    print(f"DB: {cfg.db_path}")
    print(f"Step: {args.step_days} dager (= ~{365 // args.step_days} ref_dates per år)")
    print()

    n = harvest(
        db_path=cfg.db_path,
        from_date=args.from_date,
        to_date=args.to_date,
        step_days=args.step_days,
    )
    print(f"\nTotalt: {n} nye rader skrevet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
