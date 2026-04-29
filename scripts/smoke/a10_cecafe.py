"""A10 — Cecafé Brasil kaffe-eksport (Tier 3) PDF smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at Cecafé månedlig kaffe-
eksport-rapport er tilgjengelig som PDF.

Endepunkt: https://www.cecafe.com.br/publicacoes/relatorio-mensal-de-exportacoes/

Forventet historikk: 2002+ månedlig.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

URL_INDEX = "https://www.cecafe.com.br/publicacoes/relatorio-de-exportacoes/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
}


def fetch(url: str, timeout: int = 30) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A10 Cecafé Brasil kaffe-eksport (Tier 3) ===\n")
    print(f"Forsøk index: {URL_INDEX}")
    start = time.monotonic()
    code, data = fetch(URL_INDEX)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code}, {elapsed:.2f}s, {len(data) if isinstance(data, bytes) else 'err'} bytes")

    if code != 200 or not isinstance(data, bytes):
        print("  BLOCK: index ikke nåbar")
        return

    text = data.decode("utf-8", errors="ignore")
    pdf_links = list(set(re.findall(r'https?://[^\s"\'<>]+\.pdf', text, re.I)))
    print(f"\nPDF-lenker funnet: {len(pdf_links)}")
    for link in pdf_links[:10]:
        print(f"  {link}")

    if not pdf_links:
        print("  RISK: ingen direkte PDF-lenker")
        return

    # Forsøk hente første
    first = pdf_links[0]
    print(f"\nForsøk laste PDF: {first}")
    time.sleep(1.5)
    start = time.monotonic()
    code2, data2 = fetch(first)
    elapsed = time.monotonic() - start
    print(
        f"  HTTP {code2}, {elapsed:.2f}s, {len(data2) if isinstance(data2, bytes) else 'err'} bytes"
    )
    if code2 == 200 and isinstance(data2, bytes) and data2[:4] == b"%PDF":
        print(f"  PDF magic OK ({len(data2)} bytes)")
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data2))
            n_pages = len(reader.pages)
            text_p1 = reader.pages[0].extract_text() if n_pages > 0 else ""
            print(f"  PDF-pages: {n_pages}")
            print(f"  Side 1 preview (300 chars):\n{text_p1[:300]}")
        except Exception as exc:
            print(f"  pypdf-parsing feilet: {exc}")


if __name__ == "__main__":
    main()
