"""Backfill historiske UNICA quinzenal-rapporter fra disk.

Forutsetter at PDFer ligger i ``data/manual/unica_archive/pdfs/``
navngitt ``YYYYMM_<hash>.pdf``. Disse er hentet via Wayback Machine
(scripts/manual fra browser-session, sub-fase 12.11+).

Parser hver PDF med eksisterende ``bedrock.fetch.unica.parse_unica()``
og skriver til ``unica_reports``-tabellen via ``DataStore``.

Idempotent (INSERT OR REPLACE på report_date).
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import UNICA_REPORTS_COLS
from bedrock.data.store import DataStore
from bedrock.fetch.conab import pdf_to_text
from bedrock.fetch.unica import parse_unica

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"
DEFAULT_PDF_DIR = Path("data/manual/unica_archive/pdfs")

_MONTH_BR_TO_NUM = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def derive_report_date(parsed: dict[str, Any], filename: str) -> str:
    """Utled report_date (YYYY-MM-DD) fra position_date eller period.

    UNICA rapporterer "Posição até DD/MM/YYYY" — bruk denne.
    Fallback: parse "Xª quinzena de MMM de YYYY" → 1ª = 15., 2ª = sist
    i måneden. Siste fallback: filnavnets YYYYMM (sett som 15.).
    """
    pd_str = parsed.get("position_date")
    if pd_str:
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", pd_str)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    period = parsed.get("period")
    if period:
        m = re.match(r"(1ª|2ª)\s+quinzena\s+de\s+([a-zç]+)\s+de\s+(\d{4})", period)
        if m:
            mon = _MONTH_BR_TO_NUM.get(m.group(2).lower())
            if mon:
                day = 15 if m.group(1) == "1ª" else 28
                return f"{m.group(3)}-{mon:02d}-{day:02d}"

    # Fallback: YYYYMM_xxx.pdf → YYYY-MM-15
    m = re.match(r"(\d{4})(\d{2})_", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-15"

    raise ValueError(f"Cannot derive report_date for {filename}")


def parse_pdf(pdf_path: Path) -> dict[str, Any] | None:
    """Les og parse en UNICA-PDF til dict eller None ved parser-feil."""
    raw = pdf_path.read_bytes()
    text = pdf_to_text(raw)
    if text is None:
        _log.warning("pdf_text_extraction_failed file=%s", pdf_path.name)
        return None
    parsed = parse_unica(text)
    if not parsed:
        _log.warning("no_fields_parsed file=%s", pdf_path.name)
        return None
    return parsed


def build_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))
    full_rows: list[dict[str, Any]] = []
    for r in rows:
        full = dict.fromkeys(UNICA_REPORTS_COLS)
        for k, v in r.items():
            if k in full:
                full[k] = v
        full_rows.append(full)
    return pd.DataFrame(full_rows, columns=list(UNICA_REPORTS_COLS))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        _log.error("PDF-dir not found: %s", pdf_dir)
        return 1

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        _log.error("No PDFs in %s", pdf_dir)
        return 2

    _log.info("Parser %d PDFer fra %s", len(pdfs), pdf_dir)
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for p in pdfs:
        parsed = parse_pdf(p)
        if parsed is None:
            skipped.append(p.name)
            continue
        try:
            parsed["report_date"] = derive_report_date(parsed, p.name)
        except ValueError as exc:
            _log.warning("date_failed file=%s err=%s", p.name, exc)
            skipped.append(p.name)
            continue
        rows.append(parsed)
        _log.info(
            "OK %s → date=%s sugar_yoy=%s mix=%s",
            p.name,
            parsed.get("report_date"),
            parsed.get("sugar_production_yoy_pct"),
            parsed.get("mix_sugar_pct"),
        )

    df = build_dataframe(rows)
    if df.empty:
        _log.error("Ingen rader å skrive (alle PDFer feilet parsing)")
        return 3

    # Drop duplikater på report_date — behold første (eldste i sortering)
    df = df.drop_duplicates(subset=["report_date"], keep="first")

    db_path = Path(args.db)
    if not db_path.exists():
        _log.error("DB ikke funnet: %s", db_path)
        return 4

    store = DataStore(db_path)
    n = store.append_unica_reports(df)
    _log.info(
        "Skrev %d rader til unica_reports (skipped: %d). Datoer: %s..%s",
        n,
        len(skipped),
        df["report_date"].min(),
        df["report_date"].max(),
    )
    if skipped:
        _log.warning("Skippet PDFer: %s", skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
