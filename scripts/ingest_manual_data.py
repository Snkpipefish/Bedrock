"""Ingest manuelt nedlastede historikk-filer til bedrock-DB.

Kilder:
- forex   — Forex Factory CSV (2007-2025, ~83k events)
- conab   — CONAB Excel-filer (per-safra-mappe med levantamentos)
- bdi     — Investing.com BDI PDF (2014-2018 daglig)
- gld     — SPDR Gold (GLD) holdings CSV (2004-11+, daglig)
- slv     — iShares Silver (SLV) holdings CSV (2006-04+, daglig, proxy)

Hver kilde mapper manuell fil til schema i `bedrock/data/schemas.py`
og bruker `DataStore.append_*` for idempotent insert.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/ingest_manual_data.py forex --file path/to/forex.csv
    PYTHONPATH=src .venv/bin/python scripts/ingest_manual_data.py conab --dir path/to/conab_boletins
    PYTHONPATH=src .venv/bin/python scripts/ingest_manual_data.py bdi --file path/to/bdi.pdf
    PYTHONPATH=src .venv/bin/python scripts/ingest_manual_data.py gld --file 'bedrock manuell data/gld_holdings/gld_holdings.csv'
    PYTHONPATH=src .venv/bin/python scripts/ingest_manual_data.py slv --file 'bedrock manuell data/slv_holdings/slv_holdings.csv'
"""
# pyright: reportArgumentType=false, reportMissingImports=false

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore
from bedrock.signal_server.config import load_from_env

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


# ===========================================================================
# Forex Factory CSV → econ_events
# ===========================================================================


def _parse_ff_impact(raw: str) -> str | None:
    """'High Impact Expected' → 'High'. Returner None hvis Low/Non-Economic."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.startswith("High"):
        return "High"
    if raw.startswith("Medium"):
        return "Medium"
    # Vi filtrerer bort Low + Non-Economic per bedrock-konvensjon (calendar_ff)
    return None


def ingest_forex_factory(csv_path: Path, store: DataStore, *, publication_lag_days: int = 7) -> int:
    """Ingest Forex Factory CSV til econ_events. Filtrerer på High/Medium impact.

    `publication_lag_days` (audit-runde 5 sub-fase 12.6 fix-spec Steg 2):
    Forex Factory publiserer kalenderen ~7 dager før event. Vi setter
    `fetched_at = event_ts - publication_lag_days` slik at AsOfDateStore-
    clipping på `fetched_at` gir korrekt look-ahead-fri backtest-semantikk
    ("hvilke events ville vi vite om på ref_date"). Default 7 er
    konservativ approximation — Forex Factory faktisk publiserer
    typisk uker/måneder i forveien for scheduled events.
    """
    print(f"Forex Factory CSV: {csv_path}")
    print(f"  publication_lag_days: {publication_lag_days}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Rader rå: {len(df)}")

    # Mapping
    df["impact_clean"] = df["Impact"].map(_parse_ff_impact)
    filtered = df[df["impact_clean"].notna()].copy()
    print(f"  Rader etter High/Medium-filter: {len(filtered)}")

    # event_ts: konvertér til UTC
    filtered["event_ts"] = pd.to_datetime(filtered["DateTime"], utc=True, errors="coerce")
    filtered = filtered[filtered["event_ts"].notna()].copy()

    # Country = currency code (3 chars)
    filtered["country"] = filtered["Currency"].astype(str).str.strip().str.upper()
    filtered = filtered[filtered["country"].str.len().between(2, 4)].copy()

    # Title = Event
    filtered["title"] = filtered["Event"].astype(str).str.strip()
    filtered = filtered[filtered["title"].str.len() > 0].copy()

    # Forecast/Previous: keep as string, drop NaN
    def _opt(v):
        if pd.isna(v):
            return None
        s = str(v).strip()
        return s if s else None

    filtered["forecast"] = filtered["Forecast"].map(_opt)
    filtered["previous"] = filtered["Previous"].map(_opt)
    filtered["impact"] = filtered["impact_clean"]

    # fetched_at = event_ts - publication_lag_days (semantikk (c), audit-
    # runde 4): Forex Factory publiserer kalenderen ~7 dager før event.
    # AsOfDateStore-clipping (på fetched_at) gir da korrekt look-ahead-fri
    # backtest-semantikk. Tidligere `fetched_at = event_ts` var bug — alle
    # samme-dag-events for ref_date=midnatt UTC ble feilaktig filtrert ut
    # (jf. event_distance Type B i Sjekk 9.5).
    filtered["fetched_at"] = filtered["event_ts"] - pd.Timedelta(days=publication_lag_days)

    # Dedupe på (event_ts, country, title) — schema-PK
    before = len(filtered)
    filtered = filtered.drop_duplicates(subset=["event_ts", "country", "title"], keep="first")
    print(f"  Dedupe: {before} → {len(filtered)}")

    # Schema-konformerende DF
    out_df = filtered[
        ["event_ts", "country", "title", "impact", "forecast", "previous", "fetched_at"]
    ].copy()

    # store.append_econ_events forventer ISO-tz-aware
    inserted = store.append_econ_events(out_df)
    print(f"  Inserted/replaced: {inserted}")
    return inserted


# ===========================================================================
# CONAB Excel-mappe → conab_estimates
# ===========================================================================

# Mapping fra Excel-rad-navn (Área_Brasil/Produção_Brasil/Produtividade_Brasil)
# til bedrock-canonical commodity-navn (matcher fetcher i fetch/conab.py).
#
# Algodao-merknad (fix § 7b 2026-04-28): CONAB-Excel splitter algodao i to
# rader — "ALGODÃO EM PLUMA" (lint, primær eksport-vare = ICE Cotton-prising)
# og "ALGODÃO - CAROÇO" (frø, biprodukt). Vi mapper KUN pluma → algodao for
# å unngå PK-kollisjon på (report_date, commodity). PDF-fetcher (eldre kode)
# kan returnere bare "ALGODÃO" — beholdt som alias.
_CONAB_PRODUCT_MAP = {
    "ALGODÃO": "algodao",
    "ALGODAO": "algodao",
    "ALGODÃO EM PLUMA": "algodao",
    "ALGODAO EM PLUMA": "algodao",
    "MILHO TOTAL": "milho",
    "MILHO": "milho",
    "SOJA": "soja",
    "TRIGO": "trigo",
}

_FILENAME_RE = re.compile(r"safra-(\d{4})-(\d{2})_(\d+)o[_-]")


def _parse_conab_filename(fname: str) -> tuple[str, str] | None:
    """Returner (safra, levantamento). Eks: 'safra-2023-24_5o' → ('2023/24', '5o')."""
    m = _FILENAME_RE.search(fname)
    if not m:
        return None
    yr1, yr2, lev = m.group(1), m.group(2), m.group(3)
    return f"{yr1}/{yr2}", f"{lev}o"


def _read_conab_section(xlsx_path: Path, sheet: str) -> pd.DataFrame | None:
    """Les én CONAB-seksjon (Área_Brasil/Produção_Brasil/Produtividade_Brasil).

    Sheet-strukturen er ikke konsistent — finn header-raden dynamisk ved å
    søke etter 'PRODUTO' i første kolonne. Returner DataFrame med kolonner:
    produto, prev_safra, prior_estimate, latest_estimate, mom_pct, yoy_pct.
    """
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, engine="openpyxl")
    except Exception:
        return None

    if raw.empty:
        return None

    # Finn header-raden ved å lete etter 'PRODUTO' i kolonne 0
    header_row = None
    for i in range(min(15, len(raw))):
        cell = raw.iloc[i, 0]
        if isinstance(cell, str) and "PRODUTO" in cell.upper():
            header_row = i
            break

    if header_row is None:
        return None

    # Strukturen er: PRODUTO | (a)=prev safra | (b)=prior estimate |
    #                (c)=latest | (c/b)=mom% | (c/a)=yoy%
    data_start = header_row + 3  # skip 2-3 sub-headere
    body = raw.iloc[data_start:].reset_index(drop=True)
    body = body.dropna(subset=[0])  # drop rader uten produkt-navn
    if body.empty:
        return None
    body.columns = list(range(body.shape[1]))
    body = body.rename(
        columns={
            0: "produto",
            1: "prev_safra",
            2: "prior_estimate",
            3: "latest_estimate",
            4: "mom_pct",
            5: "yoy_pct",
        }
    )
    return body[
        ["produto", "prev_safra", "prior_estimate", "latest_estimate", "mom_pct", "yoy_pct"]
    ]


def _safra_first_day(safra: str, levantamento: str) -> str:
    """Mapper levantamento + safra til omtrentlig publiseringsdato.

    CONAB publiserer ~månedlig oktober-september for grain-safra.
    1o Levantamento = oktober (måned 10), 2o = november, ..., 12o = september.
    safra=2023/24 → år=2023 for okt-des, 2024 for jan-sep.
    """
    yr1 = int(safra.split("/")[0])
    lev_n = int(levantamento.rstrip("o"))
    # 1o = okt yr1, 2o = nov yr1, 3o = des yr1, 4o = jan yr1+1, ..., 12o = sep yr1+1
    month = ((lev_n - 1 + 9) % 12) + 1  # 1→10, 2→11, 3→12, 4→1, ..., 12→9
    year = yr1 if lev_n <= 3 else yr1 + 1
    return f"{year:04d}-{month:02d}-15"


def ingest_conab_excel(xlsx_path: Path, store: DataStore) -> int:
    """Ingest én CONAB-XLSX. Returnerer antall rader skrevet."""
    parsed = _parse_conab_filename(xlsx_path.name)
    if not parsed:
        print(f"  ✗ kan ikke parse filnavn: {xlsx_path.name}")
        return 0
    safra, levantamento = parsed
    report_date = _safra_first_day(safra, levantamento)

    rows = []
    # Hent produksjon (kt) fra Produção_Brasil
    prod = _read_conab_section(xlsx_path, "Produção_Brasil")
    area = _read_conab_section(xlsx_path, "Área_Brasil")
    yld = _read_conab_section(xlsx_path, "Produtividade_Brasil")

    if prod is None:
        return 0

    for _, prow in prod.iterrows():
        produto_raw = str(prow["produto"]).strip().upper()
        commodity = _CONAB_PRODUCT_MAP.get(produto_raw)
        if not commodity:
            continue

        try:
            production = float(prow["latest_estimate"])
        except (TypeError, ValueError):
            continue

        try:
            yoy = float(prow["yoy_pct"])
        except (TypeError, ValueError):
            yoy = None
        try:
            mom = float(prow["mom_pct"])
        except (TypeError, ValueError):
            mom = None

        # Område + yield (best-effort)
        area_val = None
        if area is not None:
            match = area[area["produto"].astype(str).str.strip().str.upper() == produto_raw]
            if not match.empty:
                try:
                    area_val = float(match.iloc[0]["latest_estimate"])
                except (TypeError, ValueError):
                    area_val = None

        yield_val = None
        yield_units = None
        if yld is not None:
            match = yld[yld["produto"].astype(str).str.strip().str.upper() == produto_raw]
            if not match.empty:
                try:
                    yield_val = float(match.iloc[0]["latest_estimate"])
                    yield_units = "kg/ha"
                except (TypeError, ValueError):
                    yield_val = None

        rows.append(
            {
                "report_date": report_date,
                "commodity": commodity,
                "production": production,
                "production_units": "kt",
                "area_kha": area_val,
                "yield_value": yield_val,
                "yield_units": yield_units,
                "levantamento": levantamento,
                "safra": safra,
                "yoy_change_pct": yoy,
                "mom_change_pct": mom,
            }
        )

    if not rows:
        return 0

    df = pd.DataFrame(rows)
    inserted = store.append_conab_estimates(df)
    return inserted


def ingest_conab_dir(dir_path: Path, store: DataStore) -> int:
    files = sorted(dir_path.glob("*.xlsx"))
    print(f"CONAB-mappe: {dir_path} ({len(files)} filer)")
    total = 0
    for xlsx in files:
        n = ingest_conab_excel(xlsx, store)
        print(f"  {xlsx.name}: {n} rader")
        total += n
    return total


# ===========================================================================
# BDI PDF → shipping_indices
# ===========================================================================

# Investing.com PDF har tabellen i form:
#   Mon DD, YYYY  Price  Open  High  Low  Vol.  Change %
_BDI_DATE_RE = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s+([\d,]+\.\d+)")
_BDI_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def ingest_bdi_pdf(pdf_path: Path, store: DataStore) -> int:
    """Ekstraher BDI-historikk fra Investing.com PDF. Append til shipping_indices."""
    print(f"BDI PDF: {pdf_path}")

    try:
        text = subprocess.check_output(
            ["pdftotext", "-layout", str(pdf_path), "-"], stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"  ✗ pdftotext-feil: {exc}")
        return 0

    rows = []
    for line in text.splitlines():
        line = line.strip()
        m = _BDI_DATE_RE.match(line)
        if not m:
            continue
        date_str, price_str = m.group(1), m.group(2)
        # "Jan 26, 2018" → 2018-01-26
        try:
            mon, day, year = re.match(r"([A-Z][a-z]{2})\s+(\d+),\s+(\d{4})", date_str).groups()
            month = _BDI_MONTHS[mon]
            iso_date = f"{int(year):04d}-{month:02d}-{int(day):02d}"
            value = float(price_str.replace(",", ""))
        except (AttributeError, KeyError, ValueError):
            continue
        rows.append({"index_code": "BDI", "date": iso_date, "value": value, "source": "investing"})

    if not rows:
        print("  ✗ ingen rader parset")
        return 0

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["index_code", "date"], keep="first")
    print(f"  Parsed {len(df)} rader (range {df['date'].min()} → {df['date'].max()})")
    inserted = store.append_shipping_indices(df)
    print(f"  Inserted/replaced: {inserted}")
    return inserted


# ===========================================================================
# ETF holdings — GLD (SPDR Gold) + SLV (iShares Silver)
# ===========================================================================


def ingest_etf_holdings_csv(csv_path: Path, ticker: str, store: DataStore) -> int:
    """Ingest manuell physical-ETF-holdings-CSV til etf_holdings-tabellen.

    Forventet schema for GLD: ``date, tonnes_in_trust, ounces_in_trust,
    nav_per_share, closing_price, shares_volume, nav_total``.
    Forventet schema for SLV: ``date, nav_per_share, shares_outstanding``.

    Manglende kolonner = NULL i DB (Pydantic-schema tolererer dette).
    """
    print(f"ETF holdings ({ticker.upper()}): {csv_path}")
    df_raw = pd.read_csv(csv_path)
    print(f"  Rader rå: {len(df_raw)}")

    out = pd.DataFrame()
    out["ticker"] = [ticker.lower()] * len(df_raw)
    out["date"] = pd.to_datetime(df_raw["date"]).dt.strftime("%Y-%m-%d")
    out["tonnes_in_trust"] = (
        pd.to_numeric(df_raw["tonnes_in_trust"], errors="coerce")
        if "tonnes_in_trust" in df_raw.columns
        else None
    )
    out["ounces_in_trust"] = (
        pd.to_numeric(df_raw["ounces_in_trust"], errors="coerce")
        if "ounces_in_trust" in df_raw.columns
        else None
    )
    out["shares_outstanding"] = (
        pd.to_numeric(df_raw["shares_outstanding"], errors="coerce")
        if "shares_outstanding" in df_raw.columns
        else None
    )
    out["nav_per_share"] = (
        pd.to_numeric(df_raw["nav_per_share"], errors="coerce")
        if "nav_per_share" in df_raw.columns
        else None
    )

    out = out.drop_duplicates(subset=["ticker", "date"], keep="last")
    print(f"  Etter dedupe: {len(out)} (range {out['date'].min()} → {out['date'].max()})")
    inserted = store.append_etf_holdings(out)
    print(f"  Inserted/replaced: {inserted}")
    return inserted


# ===========================================================================
# CLI
# ===========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="source", required=True)

    p_forex = sub.add_parser("forex", help="Forex Factory CSV ingest")
    p_forex.add_argument("--file", type=Path, required=True)
    p_forex.add_argument(
        "--publication-lag-days",
        type=int,
        default=7,
        help=(
            "Antall dager Forex Factory publiserer kalenderen i forveien. "
            "Brukes som offset: fetched_at = event_ts - publication_lag_days. "
            "Default 7 (konservativ approximation for look-ahead-fri backtest)."
        ),
    )

    p_conab = sub.add_parser("conab", help="CONAB Excel-mappe ingest")
    p_conab.add_argument("--dir", type=Path, required=True)

    p_bdi = sub.add_parser("bdi", help="BDI Investing.com PDF ingest")
    p_bdi.add_argument("--file", type=Path, required=True)

    p_gld = sub.add_parser("gld", help="SPDR Gold (GLD) holdings CSV ingest")
    p_gld.add_argument("--file", type=Path, required=True)

    p_slv = sub.add_parser("slv", help="iShares Silver (SLV) holdings CSV ingest (proxy)")
    p_slv.add_argument("--file", type=Path, required=True)

    args = parser.parse_args()
    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    if args.source == "forex":
        n = ingest_forex_factory(args.file, store, publication_lag_days=args.publication_lag_days)
    elif args.source == "conab":
        n = ingest_conab_dir(args.dir, store)
    elif args.source == "bdi":
        n = ingest_bdi_pdf(args.file, store)
    elif args.source == "gld":
        n = ingest_etf_holdings_csv(args.file, "gld", store)
    elif args.source == "slv":
        n = ingest_etf_holdings_csv(args.file, "slv", store)
    else:
        parser.error(f"unknown source: {args.source}")

    print(f"\n=== {args.source}: {n} rader ingested ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
