"""B2 — VIX-termstruktur Yahoo (`^VIX3M`, `^VIX6M`, `^VIX9D`) smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Yahoo har VIX-term-
strukturen (3M/6M/9D variants) for vix_term_ratio-driver i D2.

`vix_regime` (R3) bruker FRED `VIXCLS` (1-måneds spot-VIX). Termstruktur
brukes til "kontango/backwardation"-features for SP500/Nasdaq.

Krav: ≥10 år historikk per ticker for pct_36m-vinduet.
"""

from __future__ import annotations

import time
from datetime import date

from bedrock.fetch.yahoo import YahooFetchError, fetch_yahoo_prices

TICKERS = ["^VIX3M", "^VIX6M", "^VIX9D"]


def main() -> None:
    print("=== B2 VIX-termstruktur Yahoo ===")
    for ticker in TICKERS:
        time.sleep(1.5)  # gratis-API-pacing
        start = time.monotonic()
        try:
            df = fetch_yahoo_prices(
                ticker, from_date=date(2000, 1, 1), to_date=date.today(), interval="1d"
            )
        except YahooFetchError as exc:
            print(f"\n{ticker}: BLOCK — {exc}")
            continue
        except Exception as exc:
            print(f"\n{ticker}: BLOCK — {type(exc).__name__}: {exc}")
            continue
        elapsed = time.monotonic() - start

        print(f"\n--- {ticker} ---")
        print(f"Endpoint-respons: {elapsed:.2f}s")
        print(f"Antall rader: {len(df)}")
        if df.empty:
            print(f"{ticker}: BLOCK — tom DataFrame")
            continue
        earliest = df["ts"].min()
        latest = df["ts"].max()
        years = (latest - earliest).days / 365.25
        print(f"Tidligste dato: {earliest}")
        print(f"Siste dato: {latest}")
        print(f"Historikk: {years:.1f} år")
        print(f"Eksempel siste close: {df['close'].iloc[-1]}")


if __name__ == "__main__":
    main()
