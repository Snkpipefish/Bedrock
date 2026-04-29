"""A1 — Baker Hughes Rig Count smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Baker Hughes North
American Rig Count er tilgjengelig som CSV.

Endepunkt-kandidater (cot-explorer-research):
- https://rigcount.bakerhughes.com/static-files/<filename>.xlsb
- https://rigcount.bakerhughes.com/na-rig-count
- Direkte XLSB-link via investor-page

Forventet historikk: 1944+ for US. Ukentlig (fredager).

Smoke-strategi: Forsøk å laste investor-siden, parse for direkte CSV/
XLSB-link, og verifiser at minst én rapport kan hentes. Hvis kun login-
beskyttet → BLOCK.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

URL_INVESTOR = "https://rigcount.bakerhughes.com/na-rig-count"
URL_DOWNLOADS = "https://rigcount.bakerhughes.com/rig-count-overview"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


def try_url(url: str) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            return resp.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A1 Baker Hughes Rig Count ===\n")

    print(f"Forsøk: {URL_INVESTOR}")
    start = time.monotonic()
    code, data = try_url(URL_INVESTOR)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code}, {elapsed:.2f}s, {len(data) if isinstance(data, bytes) else 'err'} bytes")

    if code != 200 or not isinstance(data, bytes):
        print("  BLOCK: kunne ikke laste investor-side")
        return

    # Søk etter direkte XLSB/CSV-lenker i HTML
    text = data.decode("utf-8", errors="ignore")
    xlsb_links = re.findall(r'https?://[^\s"\'<>]+\.xlsb', text)
    xlsx_links = re.findall(r'https?://[^\s"\'<>]+\.xlsx', text)
    csv_links = re.findall(r'https?://[^\s"\'<>]+\.csv', text)

    print("\nLenker funnet i HTML:")
    print(f"  XLSB-lenker: {len(xlsb_links)}")
    for link in xlsb_links[:5]:
        print(f"    {link}")
    print(f"  XLSX-lenker: {len(xlsx_links)}")
    for link in xlsx_links[:5]:
        print(f"    {link}")
    print(f"  CSV-lenker: {len(csv_links)}")
    for link in csv_links[:5]:
        print(f"    {link}")

    # Forsøk å hente første XLSB-lenke
    if xlsb_links:
        first = xlsb_links[0]
        print(f"\nForsøk hente: {first}")
        time.sleep(1.5)
        start = time.monotonic()
        code2, data2 = try_url(first)
        elapsed = time.monotonic() - start
        print(
            f"  HTTP {code2}, {elapsed:.2f}s, "
            f"{len(data2) if isinstance(data2, bytes) else 'err'} bytes"
        )
        if code2 == 200 and isinstance(data2, bytes) and len(data2) > 1000:
            print(f"  XLSB-fil hentet OK ({len(data2)} bytes)")
            print(f"  Første 16 bytes (magic): {data2[:16].hex()}")


if __name__ == "__main__":
    main()
