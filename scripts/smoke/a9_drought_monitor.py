"""A9 — US Drought Monitor smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at US Drought Monitor (USDM)
har CSV-API for drought-statistikk.

Endepunkt-kandidat: https://usdmdataservices.unl.edu/api/<service>/<...>
- /api/USStatistics/GetDroughtSeverityStatisticsByAreaPercent
- /api/StateStatistics/...

Forventet historikk: 2000+ ukentlig (tor).

Smoke-strategi: Hent siste rapport for landsdekkende USA og verifiser
schema. CSV-format eller JSON.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

# Public USDM data service. Returnerer CSV når format=csv.
URL_TEMPLATE = (
    "https://usdmdataservices.unl.edu/api/USStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
    "?aoi=us&startdate=1/1/2000&enddate=12/31/2026&statisticsType=1&format=csv"
)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "*/*",
}


def main() -> None:
    print("=== A9 US Drought Monitor ===\n")
    print(f"Forsøk: {URL_TEMPLATE[:80]}...")
    req = urllib.request.Request(URL_TEMPLATE, headers=HEADERS)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code}: {exc}")
        return
    except Exception as exc:
        print(f"  ERR {type(exc).__name__}: {exc}")
        return
    elapsed = time.monotonic() - start

    print(f"  HTTP {status}, {elapsed:.2f}s, {len(data)} bytes")

    text = data.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    print(f"  Antall linjer: {len(lines)}")
    if not lines:
        print("  BLOCK: tom respons")
        return

    print(f"\n  Header: {lines[0]}")
    print(f"  Første data-rad: {lines[1] if len(lines) > 1 else '(ingen)'}")
    print(f"  Siste data-rad: {lines[-1]}")

    # Beregn historikk basert på CSV-data
    if len(lines) > 2:
        # CSV format: forventet ValidStart eller MapDate som dato-felt
        first_data = lines[1]
        last_data = lines[-1]
        print(f"\n  Antall data-rader: {len(lines) - 1}")
        print(f"  Første data: {first_data[:120]}")
        print(f"  Siste data: {last_data[:120]}")


if __name__ == "__main__":
    main()
