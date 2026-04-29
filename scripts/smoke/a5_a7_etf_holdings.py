"""A5/A6/A7 — ETF holdings smoke-test (GLD, SLV, PPLT).

Sub-fase 12.7 D0 (session 126).

GLD: SPDR Gold Shares — daily total holdings i tonner (verdt ~$80B).
SLV: iShares Silver Trust — daily silver holdings.
PPLT: Aberdeen Standard Platinum ETF — daily platinum holdings.

Endepunkt-kandidater (cot-explorer-research):
- GLD: https://www.spdrgoldshares.com/usa/historical-data/  (HTML eller CSV?)
- SLV: https://www.ishares.com/us/products/239855/ishares-silver-trust-fund (CSV download)
- PPLT: https://www.abrdn.com/en-us/etf/pplt (CSV download)

Smoke-strategi: forsøk hovedside + finn historisk-CSV-link.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "*/*",
}


def fetch(url: str, timeout: int = 15) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def smoke_etf(name: str, url: str) -> None:
    print(f"\n--- {name}: {url} ---")
    start = time.monotonic()
    code, data = fetch(url)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code}, {elapsed:.2f}s, {len(data) if isinstance(data, bytes) else 'err'} bytes")
    if not isinstance(data, bytes):
        return

    text = data.decode("utf-8", errors="ignore")
    # Søk etter historiske data-lenker
    csv_links = list(set(re.findall(r'https?://[^\s"\'<>]+\.(?:csv|xls|xlsx)', text)))
    if csv_links:
        print(f"  Data-lenker funnet: {len(csv_links)}")
        for link in csv_links[:3]:
            print(f"    {link}")


def main() -> None:
    print("=== A5/A6/A7 ETF Holdings ===")

    # GLD
    smoke_etf("A5 GLD (SPDR Gold)", "https://www.spdrgoldshares.com/usa/historical-data/")
    time.sleep(1.5)

    # SLV
    smoke_etf(
        "A6 SLV (iShares Silver)",
        "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund",
    )
    time.sleep(1.5)

    # PPLT
    smoke_etf("A7 PPLT (Aberdeen Platinum)", "https://www.abrdn.com/en-us/etf/pplt")


if __name__ == "__main__":
    main()
