# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Euronext MiFID II COT-fetcher (sub-fase 12.5+ session 110).

Henter ukentlige COT-rapporter for Milling Wheat (EBM), Corn (EMA),
og Canola (ECO) fra Euronext. MiFID II-kategorier likner CFTC's
disaggregated-format; vi ekstraherer kun MM-totaler + OI per
cot-explorer-presedens.

URL-mønster:
    https://live.euronext.com/sites/default/files/commodities_reporting/
        YYYY/MM/DD/en/cdwpr_{SYMBOL}_{YYYYMMDD}.html

Euronext publiserer hver onsdag ettermiddag. Vi prøver siste 6 onsdager
slik at vi tåler at en rapport kan være forsinket eller flyttet.
Sekvensielle requests per memory-feedback (gratis-API → ingen parallell).
Manuell CSV-fallback per ADR-007 § 4 (HTML-skraping er fragil).

Cot-explorer's `fetch_euronext_cot.py` brukte både Playwright og
requests; vi porter kun requests-stien (Playwright er for tung
dependency for bedrock).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from bedrock.data.schemas import COT_EURONEXT_COLS

_log = logging.getLogger(__name__)

_EURONEXT_BASE = "https://live.euronext.com/sites/default/files/commodities_reporting"
_EURONEXT_HOME = "https://live.euronext.com/"
_DEFAULT_TIMEOUT = 20.0
_REQUEST_PACING_SEC = 1.5
_MANUAL_CSV = Path("data/manual/cot_euronext.csv")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://live.euronext.com/",
}


# ---------------------------------------------------------------------------
# Symbol-katalog
# ---------------------------------------------------------------------------


class _EuronextSpec:
    __slots__ = ("contract", "label", "symbol")

    def __init__(self, symbol: str, contract: str, label: str):
        self.symbol = symbol
        self.contract = contract
        self.label = label


DEFAULT_EURONEXT_PRODUCTS: tuple[_EuronextSpec, ...] = (
    _EuronextSpec("EBM", "euronext milling wheat", "Euronext Milling Wheat"),
    _EuronextSpec("EMA", "euronext corn", "Euronext Corn"),
    _EuronextSpec("ECO", "euronext canola", "Euronext Canola"),
)


# ---------------------------------------------------------------------------
# Onsdags-iterasjon
# ---------------------------------------------------------------------------


def recent_wednesdays(n: int = 6, today: date | None = None) -> list[date]:
    """Returner de n siste onsdagsdatoer (descending — nyeste først)."""
    base = today if today is not None else date.today()
    days_since_wed = (base.weekday() - 2) % 7
    last_wed = base - timedelta(days=days_since_wed)
    return [last_wed - timedelta(weeks=i) for i in range(n)]


def report_url(symbol: str, d: date) -> str:
    ds = d.strftime("%Y%m%d")
    return f"{_EURONEXT_BASE}/{d.year}/{d.month:02d}/{d.day:02d}/en/cdwpr_{symbol}_{ds}.html"


# ---------------------------------------------------------------------------
# HTML-parsing (port av cot-explorer's TableParser + parse_html_report)
# ---------------------------------------------------------------------------


_SPEC_KEYWORDS = ["investment fund", "fonds d'investissement", "managed", "fond"]


class _TableParser(HTMLParser):
    """Trekker ut alle tabeller som lister av rader.

    Beholder rowspan-håndtering enkel — duplikat-celler blir manglet og
    kompenseres for i `parse_html_report` via kolonne-offset basert på
    "Investment Funds"-headerens posisjon.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._cur_table: list[list[str]] | None = None
        self._cur_row: list[str] | None = None
        self._cur_cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._cur_table = []
            self._depth += 1
        elif tag == "tr" and self._cur_table is not None:
            self._cur_row = []
        elif tag in ("td", "th") and self._cur_row is not None:
            self._cur_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._depth -= 1
            if self._depth == 0 and self._cur_table is not None:
                self.tables.append(self._cur_table)
                self._cur_table = None
        elif tag == "tr" and self._cur_row is not None:
            if self._cur_table is not None:
                self._cur_table.append(self._cur_row)
            self._cur_row = None
        elif tag in ("td", "th") and self._cur_cell is not None:
            text = " ".join(self._cur_cell).strip()
            if self._cur_row is not None:
                self._cur_row.append(text)
            self._cur_cell = None

    def handle_data(self, data: str) -> None:
        if self._cur_cell is not None:
            self._cur_cell.append(data.strip())


def _safe_int(s: Any) -> int:
    if s is None or s == "":
        return 0
    try:
        return int(float(re.sub(r"[^\d.\-]", "", str(s))))
    except (ValueError, TypeError):
        return 0


def parse_html_report(html: str) -> dict[str, int] | None:
    """Parse Euronext COT-HTML; returnerer dict med mm_long/mm_short/oi.

    Returnerer None hvis tabellstrukturen ikke matcher forventet layout.
    Port av cot-explorer's `parse_html_report` med samme algoritme:

    1. Finn kategori-overskrift-rad som inneholder "Investment Funds".
    2. Beregn Investment Funds-kolonner i "type B"-rader basert på
       offset (rowspan-celler tas ut av layout-en).
    3. Finn "Total"-raden i "Number of positions"-seksjonen og les
       MM-long/short. OI = sum av alle Long-kolonner i samme rad.
    """
    parser = _TableParser()
    parser.feed(html)

    for table in parser.tables:
        if len(table) < 5:
            continue

        cat_row_idx = None
        inv_funds_cat_col = None
        for i, row in enumerate(table[:10]):
            for j, cell in enumerate(row):
                if "investment fund" in cell.lower():
                    cat_row_idx = i
                    inv_funds_cat_col = j
                    break
            if cat_row_idx is not None:
                break

        if cat_row_idx is None or inv_funds_cat_col is None:
            continue

        # Beregn Investment Funds-kolonne i "type B"-rader
        # (rowspan-offset: hver kategori har 2 kolonner Long+Short)
        cats_before = max(0, inv_funds_cat_col - 3)
        if_long_col = 1 + cats_before * 2
        if_short_col = 2 + cats_before * 2

        mm_long = mm_short = oi = 0
        section: str | None = None

        for row in table[cat_row_idx + 2 :]:
            if not row:
                continue
            label = row[0].strip().lower()

            if "number of position" in label:
                section = "positions"
            elif "changes since" in label or "change since" in label:
                section = "changes"

            if label == "total" and len(row) >= if_short_col + 1:
                if section == "positions":
                    mm_long = _safe_int(row[if_long_col])
                    mm_short = _safe_int(row[if_short_col])
                    # OI = sum av alle Long-kolonner (annenhver fra col 1)
                    oi = sum(_safe_int(row[c]) for c in range(1, len(row), 2))
                    return {
                        "mm_long": mm_long,
                        "mm_short": mm_short,
                        "open_interest": oi,
                    }

    return None


# ---------------------------------------------------------------------------
# HTTP-fetch (sekvensiell)
# ---------------------------------------------------------------------------


def fetch_html_for_date(
    spec: _EuronextSpec,
    d: date,
    *,
    session: requests.Session | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str | None:
    """Hent én HTML-rapport for ``spec`` på dato ``d``. Returnerer HTML
    eller None hvis status ≠ 200 eller responsen mangler en tabell.
    """
    sess = session or requests.Session()
    url = report_url(spec.symbol, d)
    try:
        r = sess.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        _log.warning("euronext.http_failed url=%s error=%s", url, exc)
        return None
    if r.status_code != 200:
        _log.debug("euronext.report_not_found url=%s status=%s", url, r.status_code)
        return None
    if "<table" not in r.text.lower():
        return None
    return r.text


def fetch_one_product(
    spec: _EuronextSpec,
    *,
    n_wednesdays: int = 6,
    session: requests.Session | None = None,
    today: date | None = None,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Iterer onsdager bakover; samle ALLE tilgjengelige rapporter.

    Returnerer DataFrame med en rad per tilgjengelig onsdag (kan være
    færre enn n_wednesdays hvis noen URL-er gir 404).
    """
    rows: list[dict[str, Any]] = []
    sess = session or requests.Session()
    try:
        sess.get(_EURONEXT_HOME, headers=_HEADERS, timeout=_DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        _log.debug("euronext.cookie_warmup_failed error=%s", exc)

    for i, d in enumerate(recent_wednesdays(n=n_wednesdays, today=today)):
        if i > 0:
            time.sleep(pacing_sec)
        html = fetch_html_for_date(spec, d, session=sess)
        if html is None:
            continue
        parsed = parse_html_report(html)
        if not parsed:
            _log.warning("euronext.parse_failed symbol=%s date=%s", spec.symbol, d)
            continue
        rows.append(
            {
                "report_date": d.strftime("%Y-%m-%d"),
                "contract": spec.contract,
                "mm_long": parsed["mm_long"],
                "mm_short": parsed["mm_short"],
                "open_interest": parsed["open_interest"],
            }
        )
        _log.info(
            "euronext.parsed symbol=%s date=%s mm_long=%d mm_short=%d oi=%d",
            spec.symbol,
            d,
            parsed["mm_long"],
            parsed["mm_short"],
            parsed["open_interest"],
        )

    return pd.DataFrame(rows, columns=list(COT_EURONEXT_COLS))


# ---------------------------------------------------------------------------
# Manuell CSV-fallback
# ---------------------------------------------------------------------------


def fetch_cot_euronext_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert CSV. Returnerer tom DataFrame hvis filen mangler."""
    if not csv_path.exists():
        _log.info("euronext.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(COT_EURONEXT_COLS))

    df = pd.read_csv(csv_path)
    missing = [c for c in COT_EURONEXT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"cot_euronext manual CSV mangler kolonner: {sorted(missing)}")

    df["report_date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
    return df[list(COT_EURONEXT_COLS)].copy()


# ---------------------------------------------------------------------------
# Combined: HTML-fetch + fallback
# ---------------------------------------------------------------------------


def fetch_cot_euronext(
    *,
    products: tuple[_EuronextSpec, ...] = DEFAULT_EURONEXT_PRODUCTS,
    n_wednesdays: int = 6,
    csv_path: Path = _MANUAL_CSV,
    today: date | None = None,
    pacing_sec: float = _REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent Euronext COT for alle products. Faller tilbake på manuell CSV.

    Returnerer alltid DataFrame; tom hvis både HTML og CSV mangler.
    """
    frames: list[pd.DataFrame] = []
    sess = requests.Session()
    for i, spec in enumerate(products):
        if i > 0:
            time.sleep(pacing_sec)
        try:
            df = fetch_one_product(
                spec,
                n_wednesdays=n_wednesdays,
                session=sess,
                today=today,
                pacing_sec=pacing_sec,
            )
        except Exception as exc:
            _log.warning("euronext.product_failed symbol=%s error=%s", spec.symbol, exc)
            continue
        if not df.empty:
            frames.append(df)

    if frames:
        return pd.concat(frames, ignore_index=True)

    try:
        return fetch_cot_euronext_manual(csv_path)
    except Exception as exc:
        _log.warning("euronext.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(COT_EURONEXT_COLS))


__all__ = [
    "DEFAULT_EURONEXT_PRODUCTS",
    "_EuronextSpec",
    "fetch_cot_euronext",
    "fetch_cot_euronext_manual",
    "fetch_html_for_date",
    "fetch_one_product",
    "parse_html_report",
    "recent_wednesdays",
    "report_url",
]
