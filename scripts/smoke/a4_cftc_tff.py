"""A4 — CFTC TFF (Traders in Financial Futures) smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Socrata-dataset
`gpe5-46if` (Futures Only - Traders in Financial Futures) er tilgjengelig
fra samme klient som eksisterende `cot_cftc`-modul (disaggregated `72hh-3qpy`,
legacy `6dca-aqww`).

TFF-rapporten er for FINANSIELLE futures (S&P 500, Treasury, eurodollar,
DXY, etc.) og deler trader-typene Dealer/Asset Manager/Leveraged Funds/
Other Reportables — annerledes enn disaggregated som er for kommoditeter.

Forventet historikk: juni 2010+ (TFF-rapporten startet ~2010).

Smoke-strategi: gjør én Socrata-query mot gpe5-46if og verifiser schema +
tidligste dato. Bruker samme HTTP-klient som eksisterende cot.py.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request

CFTC_TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def main() -> None:
    print("=== A4 CFTC TFF (`gpe5-46if`) ===\n")

    # Query 1: hent eldste rad — drop $select (tar alle felter)
    params = urllib.parse.urlencode(
        {
            "$order": "report_date_as_yyyy_mm_dd ASC",
            "$limit": "1",
        }
    )
    url = f"{CFTC_TFF_URL}?{params}"
    print(f"Query (eldste rad): {url[:120]}...")

    req = urllib.request.Request(url, headers=HEADERS)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"  ERR: {type(exc).__name__}: {exc}")
        return
    elapsed = time.monotonic() - start

    print(f"  HTTP OK, {elapsed:.2f}s, {len(data)} bytes")

    import json

    rows = json.loads(data)
    if not rows:
        print("  BLOCK: tom respons")
        return

    print(f"\nAntall rader: {len(rows)}")
    print(f"Eldste rad ({rows[0].get('report_date_as_yyyy_mm_dd')}):")
    keys = list(rows[0].keys())
    print(f"  Felter ({len(keys)}): {keys[:20]}")
    if len(keys) > 20:
        print(f"  ... + {len(keys) - 20} til")
    print(f"  Sample contract: {rows[0].get('market_and_exchange_names')}")
    print(
        f"  Dealer long: {rows[0].get('dealer_positions_long_all') or rows[0].get('dealer_positions_long')}"
    )

    # Query 2: hent siste rad for å bekrefte aktiv
    time.sleep(1.5)
    params2 = urllib.parse.urlencode(
        {
            "$select": "report_date_as_yyyy_mm_dd,market_and_exchange_names",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "1",
        }
    )
    url2 = f"{CFTC_TFF_URL}?{params2}"
    req2 = urllib.request.Request(url2, headers=HEADERS)
    try:
        with urllib.request.urlopen(req2, timeout=30) as resp:
            data2 = resp.read()
        rows2 = json.loads(data2)
        if rows2:
            latest_date = rows2[0].get("report_date_as_yyyy_mm_dd")
            earliest_date = rows[0].get("report_date_as_yyyy_mm_dd")
            print(f"\nSiste rapport: {latest_date}")
            from datetime import datetime as dt

            try:
                d_early = dt.fromisoformat(str(earliest_date)[:10]).date()
                d_late = dt.fromisoformat(str(latest_date)[:10]).date()
                years = (d_late - d_early).days / 365.25
                print(f"Historikk: {years:.1f} år")
            except Exception as exc:
                print(f"Date parse: {exc}")
    except Exception as exc:
        print(f"  Latest query feilet: {exc}")


if __name__ == "__main__":
    main()
