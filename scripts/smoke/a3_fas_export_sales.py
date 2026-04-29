"""A3 — FAS (Foreign Agricultural Service) Export Sales smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at USDA FAS Export Sales
Reporting (ESR) API er tilgjengelig.

Endepunkt: https://apps.fas.usda.gov/OpenData/api/esr/...
- /commodities — liste over commodity-koder
- /weeklyExports/commodityCode/{code}/marketYear/{year}
- /allCountries

Forventet historikk: 1990+ ukentlig (tor 8:30 ET).

Smoke-strategi: forsøk /commodities-endepunktet (ingen auth?) eller
test om API krever subscription-key.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

URLS = [
    "https://apps.fas.usda.gov/OpenData/api/esr/commodities",
    "https://apps.fas.usda.gov/OpenData/api/esr/data/exports/commodityCode/801/allCountries/marketYear/2024",
]


def fetch(url: str, timeout: int = 20) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A3 FAS Export Sales ===\n")

    for url in URLS:
        print(f"Forsøk: {url}")
        start = time.monotonic()
        code, data = fetch(url)
        elapsed = time.monotonic() - start
        print(
            f"  HTTP {code}, {elapsed:.2f}s, "
            f"{len(data) if isinstance(data, bytes) else 'err'} bytes"
        )
        if isinstance(data, bytes) and code == 200:
            preview = data[:500].decode("utf-8", errors="ignore")
            print(f"  Preview: {preview[:300]}")
        elif isinstance(data, str):
            print(f"  Error msg: {data[:200]}")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
