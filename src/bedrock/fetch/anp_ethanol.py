# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""ANP Brasil etanol pumpe-pris fetcher (sub-fase 12.11+ analytiker D.2).

Henter månedlige CSV/XLSX-filer fra ANP "dados abertos" og aggregerer
ETANOL hydrous-pris (R$/liter) til daglig eksport-impact-vektet snitt
for Centro-Sul-states (sukker-region).

Fil-oppdagelse (2026-09-30):
    ANP navngir månedsfilene inkonsistent — f.eks. i 2026:
      01-dados-abertos-precos-gasolina-etanol.csv
      02-cados-abertos-preco-gasolina-etanol.csv      (skrivefeil)
      04-dados-abertos-precos-gasolina-etanol         (uten filendelse)
      06-dados-abertos-precos-2026-06-gasolina-etanol.csv
    Vi leser derfor mappe-listingen for året først
    (.../arquivos/shpc/dsan/{YYYY}) og plukker etanol-filer per måned
    på ledende «MM-» eller avsluttende «-MM». URL-malene under er
    fallback når listingen ikke er tilgjengelig.

Format varierer mellom CSV (eldre) og XLSX (siste). Per memory:
sekvensielle kall mot gratis-API.

Output series_id: ANP_ETANOL_HIDR_CS_BRL_LITER (Centro-Sul vektet snitt).

Eksport-impact-vekter for sukker-regioner:
    SP=0.45, GO=0.15, MG=0.15, MS=0.10, MT=0.10, (PR+RJ+ES)/3=0.05
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import date
from typing import Any

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

URL_TMPL_NEW = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
    "arquivos/shpc/dsan/{year}/{month:02d}-dados-abertos-precos-gasolina-etanol.{ext}"
)
URL_TMPL_OLD = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
    "arquivos/shpc/dsan/{year}/precos-gasolina-etanol-{month:02d}.{ext}"
)
# Backward-compat ref
URL_TMPL = URL_TMPL_NEW

LISTING_URL_TMPL = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/{year}"
)

# href til fil i mappe-listing; Plone legger «/view» bak fil-URL-en.
_LISTING_HREF_RE = re.compile(r'href="([^"]*?/dsan/(\d{4})/([^"/?]+?))(?:/view)?/?"')
_NEXT_PAGE_RE = re.compile(r"b_start:int=(\d+)")

SERIES_ID = "ANP_ETANOL_HIDR_CS_BRL_LITER"

# Eksport-impact-vekter (sub-fase 12.11+ analytiker D)
STATE_WEIGHTS: dict[str, float] = {
    "SP": 0.45,  # São Paulo dominerer
    "GO": 0.15,
    "MG": 0.15,
    "MS": 0.10,
    "MT": 0.10,
    "PR": 0.0167,  # 0.05/3
    "RJ": 0.0167,
    "ES": 0.0167,
}
CENTRO_SUL_STATES = set(STATE_WEIGHTS.keys())

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, application/vnd.ms-excel, */*",
}

PACING_SEC = 1.5


class AnpFetchError(RuntimeError):
    """ANP-fetch feilet permanent."""


def _br_to_float(s: str) -> float | None:
    """'5,99' → 5.99. None ved tom/ugyldig."""
    if not s or not s.strip():
        return None
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None


def _is_xlsx_bytes(data: bytes) -> bool:
    """XLSX starter med PK\x03\x04 (zip magic)."""
    return data[:4] == b"PK\x03\x04"


def _parse_csv_bytes(data: bytes) -> list[dict[str, Any]]:
    """Parse ANP CSV-bytes (UTF-8 with BOM, semicolon-separated)."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    return list(reader)


def _parse_xlsx_bytes(data: bytes) -> list[dict[str, Any]]:
    """Parse ANP XLSX-bytes via pandas."""
    df = pd.read_excel(io.BytesIO(data))
    return df.to_dict("records")


def _month_from_filename(name: str) -> int | None:
    """Måned fra ANP-filnavn: ledende «MM-…» (2026+) eller «…-MM[.ext]» (≤2025)."""
    m = re.match(r"^(\d{2})(?![\d])", name)
    if m is None:
        m = re.search(r"-(\d{2})(?:\.[A-Za-z0-9]+)?$", name)
    if m is None:
        return None
    month = int(m.group(1))
    return month if 1 <= month <= 12 else None


def parse_listing(html: str, year: int) -> dict[int, list[str]]:
    """Plukk etanol-fil-URL-er per måned fra ANP-mappe-listing (HTML).

    Ignorerer glp/diesel-filer og andre år. Relative hrefs løses mot
    LISTING_URL_TMPL. «/view»-suffiks strippes så URL-en peker på selve fila.
    """
    base = LISTING_URL_TMPL.format(year=year)
    out: dict[int, list[str]] = {}
    for m in _LISTING_HREF_RE.finditer(html):
        url, y, name = m.group(1), int(m.group(2)), m.group(3)
        if y != year:
            continue
        low = name.lower()
        if "etanol" not in low or "glp" in low or "diesel" in low:
            continue
        month = _month_from_filename(low)
        if month is None:
            continue
        if not url.startswith("http"):
            url = base.rsplit("/dsan/", 1)[0] + "/dsan/" + url.split("/dsan/", 1)[-1]
        urls = out.setdefault(month, [])
        if url not in urls:
            urls.append(url)
    return out


def discover_month_urls(
    year: int,
    *,
    timeout: float = 60.0,
    max_pages: int = 12,
    pacing_sec: float = PACING_SEC,
) -> dict[int, list[str]]:
    """Hent mappe-listing for året → {måned: [fil-URL-er]}. Tom dict ved feil.

    Plone paginerer listingen (20 elementer/side, `?b_start:int=N`);
    vi følger neste-side-lenken til det ikke finnes flere. Et år har
    12 mnd × 3 produkter = 36 elementer, dvs. 2 sider.
    """
    base = LISTING_URL_TMPL.format(year=year)
    found: dict[int, list[str]] = {}
    start = 0
    for page in range(max_pages):
        url = base if start == 0 else f"{base}?b_start:int={start}"
        try:
            response = http_get_with_retry(url, headers=_HEADERS, timeout=timeout)
        except Exception as exc:
            _log.warning("anp.listing_failed year=%s page=%s err=%s", year, page, exc)
            break
        if response.status_code != 200:
            _log.warning(
                "anp.listing_failed year=%s page=%s status=%s", year, page, response.status_code
            )
            break
        for month, urls in parse_listing(response.text, year).items():
            merged = found.setdefault(month, [])
            merged.extend(u for u in urls if u not in merged)
        later = [int(n) for n in _NEXT_PAGE_RE.findall(response.text) if int(n) > start]
        if not later:
            break
        start = min(later)
        time.sleep(pacing_sec)
    _log.info("anp.listing_ok year=%s months=%s", year, sorted(found))
    return found


def _candidate_urls(year: int, month: int, candidates: list[str] | None) -> list[tuple[str, str]]:
    """(url, ext-hint) i prioritert rekkefølge: oppdagede først, så maler."""
    out: list[tuple[str, str]] = []
    for url in candidates or []:
        out.append((url, "xlsx" if url.lower().endswith(".xlsx") else "csv"))
    for url_tmpl in (URL_TMPL_NEW, URL_TMPL_OLD):
        for ext in ("csv", "xlsx"):
            url = url_tmpl.format(year=year, month=month, ext=ext)
            if all(url != u for u, _ in out):
                out.append((url, ext))
    return out


def fetch_month(
    year: int,
    month: int,
    *,
    timeout: float = 60.0,
    candidates: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Last ned + parse én måneds ANP-data.

    `candidates` er fil-URL-er funnet via `discover_month_urls` og prøves
    først. Deretter URL-malene (`{MM}-dados-abertos-…` og
    `precos-gasolina-etanol-{MM}`) × csv/xlsx som fallback. Innholdet
    sniffes (zip-magic) så filer uten endelse også parses riktig.
    """
    for url, ext in _candidate_urls(year, month, candidates):
        try:
            response = http_get_with_retry(url, headers=_HEADERS, timeout=timeout)
        except Exception as exc:
            _log.debug("anp.month_fetch_failed url=%s err=%s", url, exc)
            continue
        if response.status_code != 200:
            continue
        data = response.content
        if not data:
            continue
        try:
            if _is_xlsx_bytes(data) or ext == "xlsx":
                return _parse_xlsx_bytes(data)
            return _parse_csv_bytes(data)
        except Exception as exc:
            _log.warning("anp.parse_failed year=%s month=%s err=%s", year, month, exc)
            continue
    raise AnpFetchError(f"Failed to fetch ANP for {year}-{month:02d}")


def _normalize_row_keys(row: dict) -> dict:
    """Map XLSX-pandas-keys og CSV-keys til standard."""
    # ANP-headere har norske/portugisiske tegn — søk fleksibelt
    out: dict[str, Any] = {}
    for k, v in row.items():
        ks = str(k).strip()
        if "Produto" in ks:
            out["produto"] = str(v or "").strip().upper()
        elif "Estado" in ks and "Sigla" in ks:
            out["estado"] = str(v or "").strip()
        elif "Data da Coleta" in ks:
            out["data"] = str(v or "").strip()
        elif "Valor de Venda" in ks:
            if isinstance(v, str):
                out["valor"] = _br_to_float(v)
            else:
                try:
                    out["valor"] = float(v) if v is not None else None
                except (ValueError, TypeError):
                    out["valor"] = None
    return out


def _parse_date_dd_mm_yyyy(s: str) -> str | None:
    """'01/01/2026' → '2026-01-01'. None ved feil."""
    if not s:
        return None
    # XLSX kan returnere ISO-string allerede, eller datetime
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", str(s))
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # ISO-format fallback
    try:
        return str(s)[:10] if "-" in str(s)[:10] else None
    except Exception:
        return None


def aggregate_to_daily(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Aggregér ANP-records til daglig vektet snitt for Centro-Sul.

    Returnerer DataFrame med kolonner: series_id, date, value.
    """
    by_date_state: dict[tuple[str, str], list[float]] = {}

    for raw in records:
        norm = _normalize_row_keys(raw)
        if norm.get("produto") != "ETANOL":
            continue
        st = norm.get("estado")
        if st not in CENTRO_SUL_STATES:
            continue
        date_iso = _parse_date_dd_mm_yyyy(norm.get("data") or "")
        if not date_iso:
            continue
        v = norm.get("valor")
        if v is None or v <= 0 or v > 20:  # sanity bounds
            continue
        by_date_state.setdefault((date_iso, st), []).append(v)

    if not by_date_state:
        return pd.DataFrame(columns=["series_id", "date", "value"])

    # Per dato: vektet snitt på tvers av states
    by_date: dict[str, list[tuple[float, float]]] = {}
    for (d, st), prices in by_date_state.items():
        avg = sum(prices) / len(prices)
        weight = STATE_WEIGHTS.get(st, 0.0)
        by_date.setdefault(d, []).append((weight, avg))

    rows: list[dict[str, Any]] = []
    for d, weighted in by_date.items():
        total_w = sum(w for w, _ in weighted)
        if total_w == 0:
            continue
        weighted_avg = sum(w * p for w, p in weighted) / total_w
        rows.append({"series_id": SERIES_ID, "date": d, "value": round(weighted_avg, 4)})

    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def fetch_anp_ethanol(
    from_year: int = 2024,
    to_year: int | None = None,
    pacing_sec: float = PACING_SEC,
) -> pd.DataFrame:
    """Hent ANP etanol-pris for vindu og aggregér til daglig CS-snitt.

    Default fra 2024 (begrenset by request size). For full backfill
    sett from_year=2017 (ANP dados-abertos start).
    """
    today = date.today()
    if to_year is None:
        to_year = today.year

    all_records: list[dict[str, Any]] = []
    for year in range(from_year, to_year + 1):
        last_month = 12 if year < today.year else today.month
        discovered = discover_month_urls(year)
        time.sleep(pacing_sec)
        for month in range(1, last_month + 1):
            try:
                records = fetch_month(year, month, candidates=discovered.get(month))
                all_records.extend(records)
                _log.info(
                    "anp.month_ok year=%s month=%s records=%d",
                    year,
                    month,
                    len(records),
                )
            except AnpFetchError as exc:
                _log.warning("anp.month_skip year=%s month=%s err=%s", year, month, exc)
            time.sleep(pacing_sec)

    return aggregate_to_daily(all_records)
