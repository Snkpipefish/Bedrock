# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""UNICA Brazil sugar/ethanol fetcher (sub-fase 12.5+ session 112).

Henter halvmånedlige "Acompanhamento quinzenal da safra"-rapporter fra
unicadata.com.br. Dekker Brazil Centro-Sul — verdens største sukker/
etanol-region.

Data-flow:
1. GET https://unicadata.com.br/listagem.php?idMn=63 (index)
2. Regex ut PDF-lenken (embedded i Google Docs viewer-URL)
3. Last ned PDF direkte
4. pdftotext -layout (poppler-utils) primær, pypdf fallback per
   ADR-007 § 6 (gjenbruker `pdf_to_text` fra session 111).

Cot-explorer's `fetch_unica.py` portet med samme parsing-logikk.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import UNICA_REPORTS_COLS
from bedrock.fetch.base import http_get_with_retry
from bedrock.fetch.conab import pdf_to_text  # gjenbruker session 111-helper

_log = logging.getLogger(__name__)

INDEX_URL = "https://unicadata.com.br/listagem.php?idMn=63"
_DEFAULT_TIMEOUT = 30.0
_REQUEST_PACING_SEC = 1.5
_MANUAL_CSV = Path("data/manual/unica_reports.csv")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


# ---------------------------------------------------------------------------
# Brasiliansk tallformat — UNICA-spesifikk (med %-håndtering)
# ---------------------------------------------------------------------------


def br_num(s: Any) -> float | None:
    """'603.667' → 603667.0. '-2,21%' → -2.21. Strip '%' før parsing."""
    if s is None:
        return None
    s = str(s).strip().replace("%", "").strip()
    if not s:
        return None
    neg = s.startswith("-")
    if neg:
        s = s[1:].strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------


def find_latest_pdf_url(*, timeout: float = _DEFAULT_TIMEOUT) -> str | None:
    """Scrape UNICA-index, returner direkte URL til siste quinzenal-PDF.

    UNICA embedder PDF i Google Docs viewer:
    ``docs.google.com/gview?url=<direkte-URL>``. Vi ekstraherer den
    direkte URLen (ikke viewer-lenken).
    """
    try:
        response = http_get_with_retry(INDEX_URL, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        _log.warning("unica.index_fetch_failed error=%s", exc)
        return None
    if response.status_code != 200:
        return None

    text = response.text

    # Mønster A: gview?url=https://unicadata.com.br/arquivos/pdfs/YYYY/MM/{hash}.pdf
    match = re.search(
        r"gview\?url=(https?://unicadata\.com\.br/arquivos/pdfs/"
        r"\d{4}/\d{1,2}/[a-f0-9]+\.pdf)",
        text,
    )
    if match:
        return match.group(1)

    # Fallback: direkte .pdf-lenker
    direct = re.findall(
        r"(https?://unicadata\.com\.br/arquivos/pdfs/\d{4}/\d{1,2}/[a-f0-9]+\.pdf)",
        text,
    )
    return direct[0] if direct else None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_unica(text: str) -> dict[str, Any]:
    """Trekk ut mix-prosent, crush + produksjon-akkumulert, periode fra UNICA PDF.

    Returnerer dict med subset av ``UNICA_REPORTS_COLS``-felt.
    Manglende felter er fraværende i resultatet (driver gjør None-fallback).
    """
    data: dict[str, Any] = {}

    # Periode: "Posição até DD/MM/YYYY"
    match = re.search(r"Posição\s+até\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if match:
        data["position_date"] = match.group(1)

    # "Xª quinzena de MMM de YYYY"
    match = re.search(
        r"(1ª|2ª)\s+quinzena\s+de\s+([a-zç]+)\s+de\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        data["period"] = (
            f"{match.group(1)} quinzena de {match.group(2).lower()} de {match.group(3)}"
        )

    # "SAFRA YYYY/YYYY"
    match = re.search(r"SAFRA\s+(\d{4}/\d{4})", text, re.IGNORECASE)
    if match:
        data["crop_year"] = match.group(1)

    # Mix-rad: açúcar prev curr
    match = re.search(r"açúcar\s+([\d,]+)%\s+([\d,]+)%", text, re.IGNORECASE)
    if match:
        data["mix_sugar_pct_prev"] = br_num(match.group(1))
        data["mix_sugar_pct"] = br_num(match.group(2))

    # Mix-rad: etanol prev curr
    match = re.search(r"etanol\s+([\d,]+)%\s+([\d,]+)%", text, re.IGNORECASE)
    if match:
        data["mix_ethanol_pct_prev"] = br_num(match.group(1))
        data["mix_ethanol_pct"] = br_num(match.group(2))

    # Cana-de-açúcar: prev curr yoy%
    match = re.search(
        r"Cana-de-açúcar[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text,
        re.IGNORECASE,
    )
    if match:
        data["crush_kt_prev"] = br_num(match.group(1))
        data["crush_kt"] = br_num(match.group(2))
        data["crush_yoy_pct"] = br_num(match.group(3))

    # Açúcar (sukker-produksjon): linje-start, ikke "Cana-de-açúcar"
    match = re.search(
        r"^\s*Açúcar[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        data["sugar_production_kt_prev"] = br_num(match.group(1))
        data["sugar_production_kt"] = br_num(match.group(2))
        data["sugar_production_yoy_pct"] = br_num(match.group(3))

    # Etanol total (millioner liter)
    match = re.search(
        r"Etanol total[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text,
        re.IGNORECASE,
    )
    if match:
        data["ethanol_total_ml_prev"] = br_num(match.group(1))
        data["ethanol_total_ml"] = br_num(match.group(2))
        data["ethanol_total_yoy_pct"] = br_num(match.group(3))

    return data


# ---------------------------------------------------------------------------
# Combined fetch
# ---------------------------------------------------------------------------


def _download_pdf(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> bytes | None:
    """Last ned PDF-bytes. Returnerer None ved feil."""
    try:
        response = http_get_with_retry(url, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        _log.warning("unica.pdf_download_failed url=%s error=%s", url, exc)
        return None
    if response.status_code != 200:
        _log.warning("unica.pdf_status=%d url=%s", response.status_code, url)
        return None
    return response.content


def fetch_unica_report(
    *,
    report_date: date | None = None,
    raw_pdf: bytes | None = None,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent + parse siste UNICA quinzena-rapport.

    Args:
        report_date: lagres som ``report_date`` (default = i dag UTC).
        raw_pdf: pre-fetched PDF-bytes (for testing).
        pacing_sec: delay mellom index-scrape og PDF-download.

    Returns:
        DataFrame med 0..1 rad. Tom hvis URL-discovery eller parsing
        feilet.
    """
    if raw_pdf is None:
        url = find_latest_pdf_url()
        if url is None:
            _log.warning("unica.pdf_url_not_found")
            return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))
        time.sleep(pacing_sec)
        raw_pdf = _download_pdf(url)
        if raw_pdf is None:
            return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))

    text = pdf_to_text(raw_pdf)
    if text is None:
        _log.warning("unica.pdf_text_extraction_failed")
        return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))

    parsed = parse_unica(text)
    if not parsed:
        _log.warning("unica.no_fields_parsed")
        return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))

    # Bygg full-rad med None for manglende felter.
    rd = (report_date or datetime.now(timezone.utc).date()).isoformat()
    row: dict[str, Any] = dict.fromkeys(UNICA_REPORTS_COLS)
    row["report_date"] = rd
    for k, v in parsed.items():
        if k in row:
            row[k] = v

    return pd.DataFrame([row], columns=list(UNICA_REPORTS_COLS))


# ---------------------------------------------------------------------------
# Manuell CSV-fallback
# ---------------------------------------------------------------------------


def fetch_unica_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuell CSV. Returnerer tom DataFrame hvis filen mangler."""
    if not csv_path.exists():
        _log.info("unica.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))
    df = pd.read_csv(csv_path)
    missing = [c for c in UNICA_REPORTS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"unica_reports manual CSV mangler kolonner: {sorted(missing)}")
    df["report_date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
    return df[list(UNICA_REPORTS_COLS)].copy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def fetch_unica(
    *,
    report_date: date | None = None,
    csv_path: Path = _MANUAL_CSV,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent UNICA-rapport; fall tilbake på manuell CSV.

    Returnerer alltid DataFrame; tom hvis både PDF og CSV mangler.
    """
    try:
        df = fetch_unica_report(report_date=report_date, pacing_sec=pacing_sec)
        if not df.empty:
            return df
    except Exception as exc:
        _log.warning("unica.report_pipeline_failed error=%s", exc)

    try:
        return fetch_unica_manual(csv_path)
    except Exception as exc:
        _log.warning("unica.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(UNICA_REPORTS_COLS))


__all__ = [
    "INDEX_URL",
    "br_num",
    "fetch_unica",
    "fetch_unica_manual",
    "fetch_unica_report",
    "find_latest_pdf_url",
    "parse_unica",
]
