"""A2 — AGSI EU gas storage smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at AGSI (Aggregated Gas
Storage Inventory) API er tilgjengelig — krever gratis token.

Endepunkt: https://agsi.gie.eu/api
Token: gratis fra https://agsi.gie.eu/account (registrering)

Forventet historikk: 2011+ daglig.

Smoke-strategi:
1. Sjekk om endpoint svarer uten token (forventet: 401/403).
2. Hvis token er tilgjengelig i ~/.bedrock/secrets.env via AGSI_API_KEY,
   forsøk en autentisert query.
3. Ellers: dokumenter token-flyten og marker RISK.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from bedrock.config.secrets import get_secret

URL_BASE = "https://agsi.gie.eu/api"

HEADERS_NO_TOKEN = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def fetch(url: str, headers: dict[str, str], timeout: int = 15) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A2 AGSI EU gas storage ===\n")

    # Steg 1: forsøk uten token
    url_test = f"{URL_BASE}?country=EU&from=2024-01-01&to=2024-01-07"
    print(f"Forsøk uten token: {url_test}")
    start = time.monotonic()
    code, data = fetch(url_test, HEADERS_NO_TOKEN)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code}, {elapsed:.2f}s")
    if isinstance(data, bytes) and code == 200:
        preview = data[:300].decode("utf-8", errors="ignore")
        print(f"  Preview (uventet 200 uten token): {preview}")

    # Steg 2: hvis AGSI_API_KEY er satt, forsøk authentisert
    token = get_secret("AGSI_API_KEY")
    if not token:
        print("\nAGSI_API_KEY ikke satt i env eller ~/.bedrock/secrets.env")
        print("Token-flyt:")
        print("  1. Registrer på https://agsi.gie.eu/account")
        print("  2. Bekreft email")
        print("  3. Legg key i ~/.bedrock/secrets.env: AGSI_API_KEY=<token>")
        print("\nKlassifikasjon: RISK — token-registrering blocker")
        return

    print("\nAGSI_API_KEY funnet, forsøk authentisert query")
    headers_auth = {**HEADERS_NO_TOKEN, "x-key": token}
    time.sleep(1.5)
    start = time.monotonic()
    code2, data2 = fetch(url_test, headers_auth)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code2}, {elapsed:.2f}s")
    if code2 == 200 and isinstance(data2, bytes):
        preview = data2[:500].decode("utf-8", errors="ignore")
        print("  Authentisert respons OK")
        print(f"  Preview: {preview[:400]}")


if __name__ == "__main__":
    main()
