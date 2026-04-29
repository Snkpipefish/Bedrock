"""B3 — DXY Yahoo (`DX-Y.NYB`) smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Yahoo Finance Chart-API
returnerer DXY-historikk via ticker `DX-Y.NYB` (US Dollar Index, NYBOT).

Bruker eksisterende `bedrock.fetch.yahoo.fetch_yahoo_prices` for å
matche produksjons-kontrakten — D1 vil utvide `prices`-fetcher med
denne ticker'en istedenfor å skrive ny modul.

Krav: ≥10 år historikk, gratis, stabilt endpoint.

Kjør: PYTHONPATH=src .venv/bin/python scripts/smoke/b3_dxy_yahoo.py
"""

from __future__ import annotations

import time
from datetime import date

from bedrock.fetch.yahoo import fetch_yahoo_prices

TICKER = "DX-Y.NYB"


def main() -> None:
    start = time.monotonic()
    # Yahoo returnerer max-historikk når period1 er langt tilbake.
    df = fetch_yahoo_prices(TICKER, from_date=date(1970, 1, 1), to_date=date.today(), interval="1d")
    elapsed = time.monotonic() - start

    print(f"=== B3 DXY Yahoo (`{TICKER}`) ===")
    print(f"Endpoint-respons: {elapsed:.2f}s")
    print(f"Antall rader: {len(df)}")
    if df.empty:
        print("BLOCK: tom DataFrame fra Yahoo")
        return
    earliest = df["ts"].min()
    latest = df["ts"].max()
    years = (latest - earliest).days / 365.25
    print(f"Tidligste dato: {earliest}")
    print(f"Siste dato: {latest}")
    print(f"Historikk: {years:.1f} år")
    print("\nFørste 3 rader:")
    print(df.head(3).to_string(index=False))
    print("\nSiste 3 rader:")
    print(df.tail(3).to_string(index=False))
    print(f"\nKolonner: {list(df.columns)}")
    print(f"Dtypes: {df.dtypes.to_dict()}")


if __name__ == "__main__":
    main()
