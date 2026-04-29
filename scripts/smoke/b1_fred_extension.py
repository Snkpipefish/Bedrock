"""B1 — FRED-utvidelse smoke-test (11 nye serier).

Sub-fase 12.7 D0 (session 126). Verifiserer at alle 11 nye FRED-serier
i § 19.5 Del B1 er tilgjengelige og har ≥10 år historikk.

Serier:
- DGS2: 2-årig Treasury yield (for yield-diff-driver)
- IRLTLT01DEM156N: DE 10Y govt yield
- IRLTLT01GBM156N: GB 10Y govt yield
- IRLTLT01JPM156N: JP 10Y govt yield
- IRLTLT01AUM156N: AU 10Y govt yield
- BAMLH0A0HYM2: ICE BofA US High Yield OAS
- BAMLC0A0CM: ICE BofA US Corporate (IG) OAS
- WALCL: Fed total assets
- RRPONTSYD: Reverse Repo overnight
- WTREGEN: TGA balance
- NFCI: Chicago Fed National Financial Conditions Index

Krav: ≥10 år historikk per serie. Endpoint stabilt (FRED API har bevist
seg gjennom mange sessions).

Kjør: PYTHONPATH=src .venv/bin/python scripts/smoke/b1_fred_extension.py
"""

from __future__ import annotations

import time
from datetime import date

from bedrock.config.secrets import get_secret
from bedrock.fetch.fred import fetch_fred_series

SERIES_TO_TEST = [
    "DGS2",
    "IRLTLT01DEM156N",
    "IRLTLT01GBM156N",
    "IRLTLT01JPM156N",
    "IRLTLT01AUM156N",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "WALCL",
    "RRPONTSYD",
    "WTREGEN",
    "NFCI",
]


def main() -> None:
    api_key = get_secret("FRED_API_KEY")
    if not api_key:
        print("BLOCK: FRED_API_KEY mangler i env og ~/.bedrock/secrets.env")
        return

    print(f"=== B1 FRED-utvidelse ({len(SERIES_TO_TEST)} serier) ===\n")
    results = []
    for series_id in SERIES_TO_TEST:
        time.sleep(1.5)  # FRED rate-limit + gratis-API-pacing
        start = time.monotonic()
        try:
            df = fetch_fred_series(
                series_id, api_key, from_date=date(1970, 1, 1), to_date=date.today()
            )
        except Exception as exc:
            print(f"{series_id}: ERROR — {type(exc).__name__}: {exc}")
            results.append((series_id, None, None, "ERROR"))
            continue
        elapsed = time.monotonic() - start

        if df.empty:
            print(f"{series_id}: BLOCK — tom DataFrame ({elapsed:.2f}s)")
            results.append((series_id, None, 0, "BLOCK"))
            continue

        df["date"] = df["date"].astype(str)
        earliest = df["date"].min()
        latest = df["date"].max()
        # Beregn år historikk
        from datetime import datetime as dt

        try:
            d_early = dt.fromisoformat(earliest).date()
            d_late = dt.fromisoformat(latest).date()
            years = (d_late - d_early).days / 365.25
        except Exception:
            years = 0.0
        cls = "GO" if years >= 10 else ("RISK" if years >= 5 else "SKIP")
        print(
            f"{series_id}: {cls} | {earliest} → {latest} | {years:.1f}y | {len(df)} rader | {elapsed:.2f}s"
        )
        results.append((series_id, earliest, years, cls))

    print("\n=== Sammendrag ===")
    go_count = sum(1 for _, _, _, c in results if c == "GO")
    risk_count = sum(1 for _, _, _, c in results if c == "RISK")
    skip_count = sum(1 for _, _, _, c in results if c == "SKIP")
    block_count = sum(1 for _, _, _, c in results if c in ("BLOCK", "ERROR"))
    print(f"GO: {go_count}, RISK: {risk_count}, SKIP: {skip_count}, BLOCK/ERROR: {block_count}")


if __name__ == "__main__":
    main()
