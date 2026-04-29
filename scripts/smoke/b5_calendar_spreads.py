"""B5 — Calendar spreads Yahoo (`=F`-tickers) smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Yahoo Finance har full
futures-curve M1-M12 for energi (BZ=F, CL=F, NG=F).

Hypotese: Yahoo har M1 (front-month) per `=F`-ticker, men M2-M12 krever
explicit kontraktsmåneder (CLM26 for juni 2026 oil etc.).

D2 prioriterer energi (BZ/CL/NG). Tier 2 (metaller GC/SI/HG/PL + korn
ZC/ZS/ZW) avhenger av smoke-resultat.
"""

from __future__ import annotations

import time
from datetime import date

from bedrock.fetch.yahoo import YahooFetchError, fetch_yahoo_prices

# Tier 1: Energi M1 + spesifikke kontraktsmåneder
TIER1_TICKERS = [
    "BZ=F",  # Brent M1
    "CL=F",  # WTI Crude M1
    "NG=F",  # Natural Gas M1
    # Spesifikke kontraktsmåneder (eksempel: 3 månader fram)
    "CLM26.NYM",  # WTI juni 2026
    "CLU26.NYM",  # WTI september 2026
    "CLZ26.NYM",  # WTI desember 2026
]

# Tier 2: Metaller + korn M1
TIER2_TICKERS = ["GC=F", "SI=F", "HG=F", "PL=F", "ZC=F", "ZS=F", "ZW=F"]


def smoke_ticker(ticker: str) -> tuple[str, int, str]:
    try:
        df = fetch_yahoo_prices(
            ticker, from_date=date(2010, 1, 1), to_date=date.today(), interval="1d"
        )
    except YahooFetchError as exc:
        return ("ERR", 0, str(exc)[:80])
    except Exception as exc:
        return ("ERR", 0, f"{type(exc).__name__}: {exc}")
    if df.empty:
        return ("EMPTY", 0, "")
    earliest = df["ts"].min()
    latest = df["ts"].max()
    years = (latest - earliest).days / 365.25
    cls = "GO" if years >= 10 else ("RISK" if years >= 5 else "SKIP")
    return (cls, len(df), f"{earliest.date()} → {latest.date()} ({years:.1f}y)")


def main() -> None:
    print("=== B5 Calendar spreads Yahoo ===\n")

    print("--- Tier 1: Energi (D2-prioritet) ---")
    for ticker in TIER1_TICKERS:
        time.sleep(1.5)
        cls, n, info = smoke_ticker(ticker)
        print(f"  {ticker}: {cls} | {n} rader | {info}")

    print("\n--- Tier 2: Metaller + korn (D3 hvis Tier 1 grønn) ---")
    for ticker in TIER2_TICKERS:
        time.sleep(1.5)
        cls, n, info = smoke_ticker(ticker)
        print(f"  {ticker}: {cls} | {n} rader | {info}")


if __name__ == "__main__":
    main()
