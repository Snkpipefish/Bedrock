# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Conab Brazil crop estimates fetcher (sub-fase 12.5+ session 111).

Henter månedlige rapporter fra gov.br:
- Boletim da Safra de Grãos (Soja, Milho, Trigo, Algodão)
- Boletim da Safra de Café (Arábica + Conilon)

PDF-parsing per ADR-007 § 6:
- Primær: ``pdftotext -layout`` (poppler-utils via subprocess)
- Fallback: ``pypdf.PdfReader`` (pure-python)

Cot-explorer's `fetch_conab.py` portet med samme parsing-logikk men
forenklet URL-håndtering (predikert URL → index-scrape-fallback).

Sekvensielle requests per memory-feedback. Manuell CSV-fallback i
``data/manual/conab_estimates.csv``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import CONAB_ESTIMATES_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_REQUEST_PACING_SEC = 1.5
_MANUAL_CSV = Path("data/manual/conab_estimates.csv")

GRAINS_INDEX = (
    "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/"
    "safras/safra-de-graos/boletim-da-safra-de-graos"
)
CAFE_INDEX = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


# ---------------------------------------------------------------------------
# Brasiliansk tallformat
# ---------------------------------------------------------------------------


def br_num(s: Any) -> float | None:
    """Konverter '179.151,6' eller '(2,1)' til float.

    Punktum = tusen-skiller, komma = desimal. Parentes = negativt.
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# PDF → text (pdftotext primær, pypdf fallback)
# ---------------------------------------------------------------------------


def pdf_to_text(pdf_bytes: bytes) -> str | None:
    """Konverter PDF til tekst. pdftotext primær, pypdf fallback.

    Returnerer None hvis begge feiler.
    """
    text = _pdftotext(pdf_bytes)
    if text is not None:
        return text

    _log.warning("conab.pdftotext_failed_falling_back_to_pypdf")
    text = _pypdf_text(pdf_bytes)
    if text is not None:
        return text

    _log.warning("conab.both_pdf_extractors_failed")
    return None


def _pdftotext(pdf_bytes: bytes) -> str | None:
    """``pdftotext -layout`` via subprocess. Returnerer tekst eller None."""
    if not pdf_bytes:
        return None
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
            fp.write(pdf_bytes)
            tmp_path = fp.name
        result = subprocess.run(
            ["pdftotext", "-layout", tmp_path, "-"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            _log.debug("conab.pdftotext_rc=%d stderr=%s", result.returncode, result.stderr[:200])
            return None
        return result.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _log.warning("conab.pdftotext_timeout")
        return None
    except FileNotFoundError:
        _log.info("conab.pdftotext_not_installed")  # forventet hvis poppler-utils mangler
        return None
    except Exception as exc:
        _log.warning("conab.pdftotext_error=%s", exc)
        return None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _pypdf_text(pdf_bytes: bytes) -> str | None:
    """``pypdf.PdfReader`` fallback. Returnerer tekst eller None."""
    if not pdf_bytes:
        return None
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:
                _log.debug("conab.pypdf_page_failed: %s", exc)
        return "\n".join(pages) if pages else None
    except ImportError:
        _log.warning("conab.pypdf_not_installed")
        return None
    except Exception as exc:
        _log.warning("conab.pypdf_error=%s", exc)
        return None


# ---------------------------------------------------------------------------
# URL-discovery (index-scraping)
# ---------------------------------------------------------------------------


def find_pdf_on_index(
    index_url: str, keyword_substr: str, *, timeout: float = _DEFAULT_TIMEOUT
) -> str | None:
    """Scrape index-side, returner første PDF-lenke som inneholder keyword."""
    try:
        response = http_get_with_retry(index_url, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        _log.warning("conab.index_fetch_failed url=%s error=%s", index_url, exc)
        return None
    if response.status_code != 200:
        return None

    matches = re.findall(r'href=["\']([^"\']+\.pdf)["\']', response.text)
    for match in matches:
        if keyword_substr.lower() not in match.lower():
            continue
        if match.startswith("/"):
            return "https://www.gov.br" + match
        if match.startswith("http"):
            return match
    return None


def find_cafe_pdf(*, timeout: float = _DEFAULT_TIMEOUT) -> str | None:
    """Coffee-spesifikk: 2-nivå (index → levantamento-side → PDF)."""
    try:
        response = http_get_with_retry(CAFE_INDEX, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        _log.warning("conab.cafe_index_failed error=%s", exc)
        return None
    if response.status_code != 200:
        return None

    levantamento_urls = re.findall(
        r'href=["\'](https://www\.gov\.br/conab/[^"\']*?/'
        r"\d+o-levantamento-de-cafe-safra-\d+/"
        r'\d+o-levantamento-de-cafe-safra-\d+)["\']',
        response.text,
    )
    seen: set[str] = set()
    for lev_url in levantamento_urls:
        if lev_url in seen:
            continue
        seen.add(lev_url)
        try:
            lev_response = http_get_with_retry(lev_url, headers=_HEADERS, timeout=timeout)
        except Exception:
            continue
        if lev_response.status_code != 200:
            continue
        pdfs = re.findall(r'href=["\']([^"\']+\.pdf)["\']', lev_response.text)
        for pdf in pdfs:
            if "cafe" in pdf.lower() or "boletim-de-safras" in pdf.lower():
                if pdf.startswith("/"):
                    return "https://www.gov.br" + pdf
                return pdf
    return None


# ---------------------------------------------------------------------------
# Parsing — Grains
# ---------------------------------------------------------------------------

_NUM = r"\(?[\d.,]+\)?"
_GROW = r"\(?\-?[\d.,]+\)?"

_GRAIN_ROW_RE = re.compile(
    r"^\s*(?P<crop>[A-ZÇÃÁÉÍÓÚÂÊÔÜ\-\s]{3,40}?)\s{2,}"
    rf"(?P<a_prev>{_NUM})\s+(?P<a_curr>{_NUM})\s+(?P<a_chg>{_GROW})\s+"
    rf"(?P<y_prev>{_NUM})\s+(?P<y_curr>{_NUM})\s+(?P<y_chg>{_GROW})\s+"
    rf"(?P<p_prev>{_NUM})\s+(?P<p_curr>{_NUM})\s+(?P<p_chg>{_GROW})\s*$",
    re.MULTILINE,
)

GRAINS_OF_INTEREST: dict[str, list[str]] = {
    "soja": ["SOJA"],
    "milho": ["MILHO TOTAL"],
    "trigo": ["TRIGO"],
    "algodao": ["ALGODÃO - PLUMA", "ALGODAO - PLUMA"],
}


def parse_grains(text: str) -> dict[str, dict[str, float | None]]:
    """Ekstraher soja/milho/trigo/algodão fra Conab grains-tabell."""
    result: dict[str, dict[str, float | None]] = {}
    for match in _GRAIN_ROW_RE.finditer(text):
        crop_raw = re.sub(r"\s+", " ", match.group("crop").strip().upper())
        for key, aliases in GRAINS_OF_INTEREST.items():
            if key in result:
                continue
            for alias in aliases:
                if alias.upper() == crop_raw or alias.upper() in crop_raw:
                    prod = br_num(match.group("p_curr"))
                    if prod is None:
                        continue
                    result[key] = {
                        "production": prod,
                        "production_units": "kt",
                        "area_kha": br_num(match.group("a_curr")),
                        "yield_value": br_num(match.group("y_curr")),
                        "yield_units": "kgha",
                        "yoy_change_pct": br_num(match.group("p_chg")),
                    }
                    break
    return result


# ---------------------------------------------------------------------------
# Parsing — Coffee
# ---------------------------------------------------------------------------

_CAFE_TABLE_RE = re.compile(r"TABELA\s+(\d+)\s*[–\-]\s*(.*)", re.IGNORECASE)
_CAFE_BRASIL_RE = re.compile(
    r"^\s*BRASIL\s+"
    rf"(?P<a_prev>{_NUM})\s+(?P<a_curr>{_NUM})\s+(?P<a_chg>{_GROW})\s+"
    rf"(?P<y_prev>{_NUM})\s+(?P<y_curr>{_NUM})\s+(?P<y_chg>{_GROW})\s+"
    rf"(?P<p_prev>{_NUM})\s+(?P<p_curr>{_NUM})\s+(?P<p_chg>{_GROW})\s*$",
    re.MULTILINE,
)

_TABLE_NUM_TO_KEY = {1: "cafe_total", 2: "cafe_arabica", 3: "cafe_conilon"}


def parse_cafe(text: str) -> dict[str, dict[str, float | None]]:
    """Trekk ut BRASIL-totaler fra coffee-rapport (Tabela 1, 2, 3)."""
    result: dict[str, dict[str, float | None]] = {}
    lines = text.splitlines()
    table_positions: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        match = _CAFE_TABLE_RE.search(line)
        if match:
            try:
                table_positions.append((i, int(match.group(1))))
            except ValueError:
                pass

    for idx, (line_idx, tnum) in enumerate(table_positions):
        if tnum not in _TABLE_NUM_TO_KEY:
            continue
        key = _TABLE_NUM_TO_KEY[tnum]
        end_idx = table_positions[idx + 1][0] if idx + 1 < len(table_positions) else len(lines)
        segment = "\n".join(lines[line_idx:end_idx])
        match = _CAFE_BRASIL_RE.search(segment)
        if not match:
            continue
        prod = br_num(match.group("p_curr"))
        if prod is None:
            continue
        result[key] = {
            "production": prod,
            "production_units": "ksacas",
            "area_kha": br_num(match.group("a_curr")),
            "yield_value": br_num(match.group("y_curr")),
            "yield_units": "sacasha",
            "yoy_change_pct": br_num(match.group("p_chg")),
        }
    return result


# ---------------------------------------------------------------------------
# Levantamento + safra extractor
# ---------------------------------------------------------------------------


def extract_levantamento(text: str) -> tuple[str | None, str | None]:
    """Returner (levantamento, safra) eller (None, None)."""
    lev = re.search(r"(\d+)[ºo°]?\s*LEVANTAMENTO", text, re.IGNORECASE)
    if not lev:
        lev = re.search(
            r"n[º.°]\s*(\d+)\s*[–\-]\s*\w+\s+levantamento",
            text,
            re.IGNORECASE,
        )
    safra = re.search(r"SAFRA\s+(\d{4}/\d{2,4})|SAFRA\s+(\d{4})", text, re.IGNORECASE)
    safra_str = (safra.group(1) or safra.group(2)) if safra else None
    return (
        f"{lev.group(1)}o" if lev else None,
        safra_str,
    )


# ---------------------------------------------------------------------------
# Fetch + parse pipelines
# ---------------------------------------------------------------------------


def _download_pdf(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> bytes | None:
    """Last ned PDF-bytes. Returnerer None ved feil."""
    try:
        response = http_get_with_retry(url, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        _log.warning("conab.pdf_download_failed url=%s error=%s", url, exc)
        return None
    if response.status_code != 200:
        _log.warning("conab.pdf_status=%d url=%s", response.status_code, url)
        return None
    return response.content


def fetch_grains_report(
    *, report_date: date | None = None, raw_pdf: bytes | None = None
) -> pd.DataFrame:
    """Hent + parse Conab grains-rapport. Returnerer DataFrame med rader.

    Args:
        report_date: dato som lagres som ``report_date`` (default = i dag UTC).
        raw_pdf: pre-fetched PDF-bytes (for testing). Hopper over HTTP.

    Returns:
        DataFrame med ``CONAB_ESTIMATES_COLS``. Tom hvis parsing feilet.
    """
    if raw_pdf is None:
        url = find_pdf_on_index(GRAINS_INDEX, "boletim")
        if url is None:
            _log.warning("conab.grains_pdf_url_not_found")
            return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))
        raw_pdf = _download_pdf(url)
        if raw_pdf is None:
            return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    text = pdf_to_text(raw_pdf)
    if text is None:
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    levantamento, safra = extract_levantamento(text)
    parsed = parse_grains(text)
    if not parsed:
        _log.warning("conab.grains_no_rows_parsed")
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    rd = (report_date or datetime.now(timezone.utc).date()).isoformat()
    rows = []
    for commodity, data in parsed.items():
        rows.append(
            {
                "report_date": rd,
                "commodity": commodity,
                "levantamento": levantamento,
                "safra": safra,
                "production": data["production"],
                "production_units": data["production_units"],
                "area_kha": data["area_kha"],
                "yield_value": data["yield_value"],
                "yield_units": data["yield_units"],
                "yoy_change_pct": data["yoy_change_pct"],
                "mom_change_pct": None,  # beregnes på server-side ved lookup
            }
        )
    return pd.DataFrame(rows, columns=list(CONAB_ESTIMATES_COLS))


def fetch_cafe_report(
    *, report_date: date | None = None, raw_pdf: bytes | None = None
) -> pd.DataFrame:
    """Hent + parse Conab kaffe-rapport."""
    if raw_pdf is None:
        url = find_cafe_pdf()
        if url is None:
            _log.warning("conab.cafe_pdf_url_not_found")
            return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))
        raw_pdf = _download_pdf(url)
        if raw_pdf is None:
            return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    text = pdf_to_text(raw_pdf)
    if text is None:
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    levantamento, safra = extract_levantamento(text)
    parsed = parse_cafe(text)
    if not parsed:
        _log.warning("conab.cafe_no_rows_parsed")
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))

    rd = (report_date or datetime.now(timezone.utc).date()).isoformat()
    rows = []
    for commodity, data in parsed.items():
        rows.append(
            {
                "report_date": rd,
                "commodity": commodity,
                "levantamento": levantamento,
                "safra": safra,
                "production": data["production"],
                "production_units": data["production_units"],
                "area_kha": data["area_kha"],
                "yield_value": data["yield_value"],
                "yield_units": data["yield_units"],
                "yoy_change_pct": data["yoy_change_pct"],
                "mom_change_pct": None,
            }
        )
    return pd.DataFrame(rows, columns=list(CONAB_ESTIMATES_COLS))


def fetch_conab_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuell CSV. Returnerer tom DataFrame hvis filen mangler."""
    if not csv_path.exists():
        _log.info("conab.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))
    df = pd.read_csv(csv_path)
    missing = [c for c in CONAB_ESTIMATES_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"conab_estimates manual CSV mangler kolonner: {sorted(missing)}")
    df["report_date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
    return df[list(CONAB_ESTIMATES_COLS)].copy()


def fetch_conab(
    *,
    report_date: date | None = None,
    csv_path: Path = _MANUAL_CSV,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent grains + kaffe sekvensielt; fall tilbake på manuell CSV.

    Returnerer alltid DataFrame; tom hvis både PDF og CSV mangler.
    """
    frames: list[pd.DataFrame] = []
    try:
        df = fetch_grains_report(report_date=report_date)
        if not df.empty:
            frames.append(df)
    except Exception as exc:
        _log.warning("conab.grains_pipeline_failed error=%s", exc)

    time.sleep(pacing_sec)

    try:
        df = fetch_cafe_report(report_date=report_date)
        if not df.empty:
            frames.append(df)
    except Exception as exc:
        _log.warning("conab.cafe_pipeline_failed error=%s", exc)

    if frames:
        return pd.concat(frames, ignore_index=True)

    try:
        return fetch_conab_manual(csv_path)
    except Exception as exc:
        _log.warning("conab.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(CONAB_ESTIMATES_COLS))


__all__ = [
    "CAFE_INDEX",
    "GRAINS_INDEX",
    "GRAINS_OF_INTEREST",
    "br_num",
    "extract_levantamento",
    "fetch_cafe_report",
    "fetch_conab",
    "fetch_conab_manual",
    "fetch_grains_report",
    "find_cafe_pdf",
    "find_pdf_on_index",
    "parse_cafe",
    "parse_grains",
    "pdf_to_text",
]
