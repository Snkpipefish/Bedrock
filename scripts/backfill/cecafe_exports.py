"""Backfill Cecafé Brasil kaffe-eksport til ``cecafe_exports``-tabellen.

Sub-fase 12.7 D3 A10 (session 135). Engangs-skript per ADR-011 (10-år
rolling cutoff, sekvensiell HTTP med 1.5s pacing, lov til å være "shitty").

Hva skriptet gjør:
- Laster ned månedlige Cecafé-PDFer fra
  ``https://www.cecafe.com.br/site/wp-content/uploads/graficos/
  CECAFE-Relatorio-Mensal-{MONTH-PT}-{YEAR}.pdf``
- Parser tabell "Últimos 12 meses" (eller multi-år-comparison fallback)
  fra hver PDF og deduperer på (year, month). Hver PDF gir 12-16 unike
  månedsrader; backfill av 120 PDFer (10 år) gir ~120-200 unike måneder
  etter dedupe.
- For hver måned skriver 4 rader: arabica, robusta, industrialized, sum.
- Lagrer til ``cecafe_exports`` med PK (month, coffee_type).

URL-pattern verifisert tilgjengelig fra 2017-01 (eldre returnerer 404).
Per ADR-011 § 1: 10-år rolling cutoff oppfylt (2026 - 2017 = 9 år
komplett + inneværende).

PDF-format-stabilitet: testet på 2017/2018/2020/2024/2026 — samme
"Últimos 12 meses"-tabell-konvensjon hele veien. Disambiguering mellom
volume-only / receita-only / kombinerte tabeller via krav om at
preço-médio-kolonnen (token #9) er i 50-1000 USD/saca-rangen.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/cecafe_exports.py
Forventet kjøretid: ~120 PDF × (1.5s pacing + 1-3s download/parse)
                   = ~5-9 minutter.
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from bedrock.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_LOOKBACK_YEARS = 10
PACING_SECONDS = 1.5

URL_TEMPLATE = (
    "https://www.cecafe.com.br/site/wp-content/uploads/graficos/"
    "CECAFE-Relatorio-Mensal-{month_pt}-{year}.pdf"
)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0"

PT_MONTHS = (
    "JANEIRO",
    "FEVEREIRO",
    "MARCO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
)

PT_ABBR_TO_MONTH = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

# Match: <mon>-<yy> followed by 9-11 numeric tokens (volume + FOB + price + opt R$).
_ROW_RE = re.compile(
    r"\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)-(\d{2})\s+"
    r"((?:[\d.,]+\s+){8,11}[\d.,]+)",
    re.IGNORECASE,
)


def _br_to_int(s: str) -> int:
    return int(s.replace(".", "").replace(",", "."))


def _br_to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parse_cecafe_pdf(pdf_bytes: bytes, source_url: str) -> list[dict[str, object]]:
    """Parse Cecafé månedlig PDF til liste av rader.

    Returnerer én dict per (month, coffee_type) — 4 typer × N unike måneder.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    seen: set[tuple[int, int]] = set()
    out: list[dict[str, object]] = []

    for pg in reader.pages:
        text = pg.extract_text() or ""
        for line in text.splitlines():
            m = _ROW_RE.match(line)
            if not m:
                continue
            mon_abbr = m.group(1).lower()
            yr2 = int(m.group(2))
            year = 2000 + yr2 if yr2 < 70 else 1900 + yr2
            mon = PT_ABBR_TO_MONTH[mon_abbr]
            toks = m.group(3).split()
            if len(toks) < 9:
                continue
            try:
                # Disambig: token #9 (idx 8) = preço médio, must be 50-1000 USD/saca.
                price_med = _br_to_float(toks[8])
                if not (50 < price_med < 1000):
                    continue
                robusta = _br_to_int(toks[0])
                arabica = _br_to_int(toks[1])
                total_indust = _br_to_int(toks[5])
                total_export = _br_to_int(toks[6])
                fob_usd_mil = _br_to_float(toks[7])
            except (ValueError, KeyError):
                continue

            key = (year, mon)
            if key in seen:
                continue
            seen.add(key)

            month_iso = f"{year:04d}-{mon:02d}-01"
            # Cecafé reporterer FOB i USD-tusen → konverter til USD.
            fob_usd = fob_usd_mil * 1000.0

            for coffee_type, volume in (
                ("arabica", arabica),
                ("robusta", robusta),
                ("industrialized", total_indust),
                ("sum", total_export),
            ):
                out.append(
                    {
                        "month": month_iso,
                        "coffee_type": coffee_type,
                        "volume_60kg_bags": volume,
                        # FOB rapporteres på sum-nivå; per-type-FOB ikke tilgjengelig.
                        # Vi setter fob kun på 'sum' for å unngå dobbeltelling.
                        "fob_value_usd": fob_usd if coffee_type == "sum" else None,
                        "source_pdf": source_url,
                    }
                )
    return out


def fetch_pdf(url: str, timeout: int = 30) -> bytes | None:
    """Last ned PDF. Returnerer None ved 404 eller annen feil."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if not data.startswith(b"%PDF"):
                _log.warning("Not a PDF: %s (got %d bytes)", url, len(data))
                return None
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        _log.warning("HTTP %d: %s", exc.code, url)
        return None
    except Exception as exc:
        _log.warning("Fetch failed: %s — %s", url, exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="Sti til SQLite-DB")
    parser.add_argument(
        "--from-year",
        dest="from_year",
        type=int,
        default=None,
        help=f"Start-år. Default: {DEFAULT_LOOKBACK_YEARS} år tilbake.",
    )
    parser.add_argument(
        "--to-year",
        dest="to_year",
        type=int,
        default=None,
        help="Slutt-år (inkluderende). Default: gjeldende år.",
    )
    args = parser.parse_args()

    today = date.today()
    to_year = args.to_year if args.to_year is not None else today.year
    from_year = (
        args.from_year if args.from_year is not None else today.year - DEFAULT_LOOKBACK_YEARS
    )

    db_path = Path(args.db).resolve()
    if not db_path.parent.exists():
        _log.error("DB-mappe finnes ikke: %s", db_path.parent)
        return 1

    store = DataStore(db_path)
    _log.info("Backfill A10 Cecafé: %d..%d, db=%s", from_year, to_year, db_path)

    all_rows: list[dict[str, object]] = []
    n_pdf_ok = 0
    n_pdf_404 = 0
    seen_months: set[tuple[int, int]] = set()
    first = True

    for year in range(from_year, to_year + 1):
        for month_idx, month_pt in enumerate(PT_MONTHS, start=1):
            # Skip future months for current year.
            if year == today.year and month_idx > today.month:
                break

            if not first:
                time.sleep(PACING_SECONDS)
            first = False

            url = URL_TEMPLATE.format(month_pt=month_pt, year=year)
            data = fetch_pdf(url)
            if data is None:
                n_pdf_404 += 1
                continue
            n_pdf_ok += 1

            try:
                rows = parse_cecafe_pdf(data, source_url=url)
            except Exception as exc:
                _log.warning("Parse failed for %s: %s", url, exc)
                continue

            # Hver PDF gir multiple måneder (12 meses + multi-år-comparison).
            # INSERT OR REPLACE på (month, coffee_type)-PK håndterer dedupe;
            # senere PDFer overskriver tidligere (Cecafé reviderer iblant
            # historiske rader, så den nyeste PDF-en er autoritativ).
            for r in rows:
                all_rows.append(r)
                if r["coffee_type"] == "sum":
                    month_str = str(r["month"])
                    seen_months.add((int(month_str[0:4]), int(month_str[5:7])))

            _log.info(
                "  PDF %d/%d %s %d: %d rows parsed (%d unique months total so far)",
                n_pdf_ok,
                (to_year - from_year + 1) * 12,
                month_pt,
                year,
                len(rows) // 4,
                len(seen_months),
            )

    if not all_rows:
        _log.error("Ingen rader parset — sjekk URL-pattern eller PDF-format.")
        return 1

    df = pd.DataFrame(all_rows)
    n_written = store.append_cecafe_exports(df)

    months_in_db = sorted(seen_months)
    _log.info(
        "Ferdig: %d PDF lastet (%d 404), %d rader skrevet, %d unike måneder i DB (%s..%s).",
        n_pdf_ok,
        n_pdf_404,
        n_written,
        len(months_in_db),
        f"{months_in_db[0][0]}-{months_in_db[0][1]:02d}" if months_in_db else "—",
        f"{months_in_db[-1][0]}-{months_in_db[-1][1]:02d}" if months_in_db else "—",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
