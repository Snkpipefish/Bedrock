"""A11 — ICE certified stocks smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at ICE Futures publiserer
"certified stocks" (warehouse-inventory) for soft commodities (Coffee,
Cocoa, Sugar) og at historikk er tilgjengelig.

Endepunkt-kandidater (cot-explorer-research):
- https://www.theice.com/marketdata/reports/178 (Coffee)
- https://www.theice.com/marketdata/reports/179 (Cocoa)
- https://www.theice.com/marketdata/reports/180 (Sugar)
- Direkte CSV-eksport-API hvis tilgjengelig

Smoke-strategi: forsøk å laste rapport-HTML og finn CSV-export-link.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
}


def fetch(url: str) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A11 ICE certified stocks ===\n")

    URLS = [
        ("Coffee", "https://www.theice.com/marketdata/reports/178"),
        ("Cocoa", "https://www.theice.com/marketdata/reports/179"),
        ("Sugar", "https://www.theice.com/marketdata/reports/180"),
    ]

    for name, url in URLS:
        print(f"--- {name}: {url} ---")
        start = time.monotonic()
        code, data = fetch(url)
        elapsed = time.monotonic() - start
        print(
            f"  HTTP {code}, {elapsed:.2f}s, "
            f"{len(data) if isinstance(data, bytes) else 'err'} bytes"
        )

        if isinstance(data, bytes) and code == 200:
            text = data.decode("utf-8", errors="ignore")
            csv_links = list(set(re.findall(r'https?://[^\s"\'<>]+(?:csv|xlsx?)', text, re.I)))
            if csv_links:
                print(f"  Data-lenker: {len(csv_links)}")
                for link in csv_links[:3]:
                    print(f"    {link}")
            # Search for download-form or AJAX endpoints
            ajax = re.findall(r'/marketdata/(?:reports|api)/[^\s"\'<>]+', text)
            uniq_ajax = list(set(ajax))[:5]
            if uniq_ajax:
                print(f"  AJAX-endpoints: {len(uniq_ajax)}")
                for a in uniq_ajax:
                    print(f"    {a}")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
