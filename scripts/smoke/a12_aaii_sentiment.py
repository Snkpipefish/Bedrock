"""A12 — AAII Sentiment Survey smoke-test.

Sub-fase 12.7 D0 (session 126). Verifiserer at AAII (American Association
of Individual Investors) Sentiment Survey er tilgjengelig som CSV.

Endepunkt-kandidater (fra cot-explorer-research):
- https://www.aaii.com/files/surveys/sentiment.xls (Excel)
- https://www.aaii.com/sentimentsurvey/sent_results (HTML-skraping)

Forventet historikk: ukentlig fra 1987.

Smoke-strategi: forsøk å hente sentiment.xls (Excel). Hvis 403/login-
kreves, marker BLOCK. AAII har historisk hatt offentlig tilgang til
historikken, men har strammet inn tilgang i nyere år.
"""

from __future__ import annotations

import io
import time
import urllib.error
import urllib.request

URL_XLS = "https://www.aaii.com/files/surveys/sentiment.xls"
URL_FALLBACK = "https://www.aaii.com/sentimentsurvey/sent_results"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "*/*",
}


def try_url(url: str) -> tuple[int, bytes | str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            return resp.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("=== A12 AAII Sentiment ===\n")

    print(f"Forsøk: {URL_XLS}")
    start = time.monotonic()
    code, data = try_url(URL_XLS)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code}, {elapsed:.2f}s, {len(data) if isinstance(data, bytes) else 'err'} bytes")

    if code == 200 and isinstance(data, bytes):
        # Forsøk å parse Excel
        try:
            import pandas as pd

            df = pd.read_excel(io.BytesIO(data), sheet_name=None)
            print(f"  Excel-parsing OK. Sheets: {list(df.keys())}")
            for sheet_name, sheet_df in df.items():
                print(
                    f"\n  Sheet '{sheet_name}': {len(sheet_df)} rader, kolonner: {list(sheet_df.columns)[:8]}"
                )
                if not sheet_df.empty:
                    print(f"  Første rad: {sheet_df.iloc[0].to_dict()}")
                    print(f"  Siste rad: {sheet_df.iloc[-1].to_dict()}")
        except Exception as exc:
            print(f"  Excel-parsing feilet: {exc}")
        return

    print(f"\nForsøk fallback: {URL_FALLBACK}")
    time.sleep(1.5)
    start = time.monotonic()
    code2, data2 = try_url(URL_FALLBACK)
    elapsed = time.monotonic() - start
    print(f"  HTTP {code2}, {elapsed:.2f}s")
    if code2 == 200:
        print(f"  HTML-respons: {len(data2)} bytes — krever HTML-skraping")


if __name__ == "__main__":
    main()
