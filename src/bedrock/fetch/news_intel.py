# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""News intel fetcher (sub-fase 12.5+ session 114).

Henter Google News RSS-artikler per bedrock-kategori og normaliserer
dem til ``NEWS_INTEL_COLS``-schema. Ingen API-key kreves; sekvensielle
HTTP-kall per memory-feedback (gratis-kilder skal ikke parallelliseres).

UI-only foreløpig per ADR-007 § 5 + ADR-008 § 114. Etter ≥1 mnds
data-akkumulering vurderes en ``news_intel_pressure``-driver som
beregner pressure per kategori (recency-vektet count av disruption-words).

Cot-explorer's `fetch_intel.py` brukes som referanse — vi utvider fra
7 til 9 kategorier (splitter "geopolitics" i oil/gas/geopolitics) for
bedre per-instrument-mapping i fremtidig scoring.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from bedrock.data.schemas import NEWS_INTEL_COLS

_log = structlog.get_logger(__name__)

_MANUAL_CSV = Path("data/manual/news_intel.csv")
_GNEWS_BASE = "https://news.google.com/rss/search"
_DEFAULT_TIMEOUT = 15.0
_REQUEST_PACING_SEC = 2.0  # gratis-kilde: sekvensielt med 2s pacing
_MAX_ARTICLES_PER_QUERY = 10

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# Hver kategori har én RSS-query. category-feltet matcher
# bedrock-canonical kategorinavnet i schemas.py.
_CATEGORIES: tuple[dict[str, str], ...] = (
    {
        "id": "gold",
        "category": "gold",
        "query": "gold mine OR gold price OR gold reserves",
    },
    {
        "id": "silver",
        "category": "silver",
        "query": "silver mine OR silver price OR COMEX silver",
    },
    {
        "id": "copper",
        "category": "copper",
        "query": "copper mine OR copper supply OR copper price",
    },
    {
        "id": "oil",
        "category": "oil",
        "query": "crude oil supply OR OPEC OR oil refinery OR oil pipeline",
    },
    {
        "id": "gas",
        "category": "gas",
        "query": "natural gas supply OR LNG OR Henry Hub OR gas pipeline",
    },
    {
        "id": "grains",
        "category": "grains",
        "query": "wheat corn soybeans crop harvest drought flood supply",
    },
    {
        "id": "softs",
        "category": "softs",
        "query": "coffee cocoa sugar cotton canola palm oil crop price",
    },
    {
        "id": "geopolitics",
        "category": "geopolitics",
        "query": "mining conflict chokepoint shipping disruption sanctions",
    },
    {
        "id": "agri_weather",
        "category": "agri_weather",
        "query": "crop weather drought flood La Nina El Nino agriculture supply",
    },
)


def _fetch_rss(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """HTTP GET wrapper. Egen indireksjon for å gjøre mocking enkelt."""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_pub_date(pub_raw: str) -> datetime | None:
    """Robust parsing av RSS pubDate. Returnerer UTC datetime eller None."""
    if not pub_raw:
        return None
    try:
        dt = parsedate_to_datetime(pub_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch_news_intel_category(
    category: dict[str, str],
    fetched_at: datetime | None = None,
    raw_response: str | None = None,
) -> list[dict[str, Any]]:
    """Hent én kategori og returner liste av article-dicts (NEWS_INTEL_COLS).

    Args:
        category: dict med 'id', 'category', 'query'.
        fetched_at: tidspunkt for fetching (default = now UTC).
        raw_response: hvis gitt, brukes istedenfor HTTP-kall (for testing).

    Returns:
        Liste av dicts som matcher NEWS_INTEL_COLS. Tom liste ved feil.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc)

    if raw_response is None:
        params = urllib.parse.urlencode(
            {
                "q": category["query"],
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        )
        url = f"{_GNEWS_BASE}?{params}"
        try:
            raw_response = _fetch_rss(url)
        except Exception as exc:
            _log.warning(
                "news_intel.fetch_failed",
                category=category["id"],
                error=str(exc),
            )
            return []

    try:
        root = ET.fromstring(raw_response)
    except ET.ParseError as exc:
        _log.warning(
            "news_intel.parse_failed",
            category=category["id"],
            error=str(exc),
        )
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    articles: list[dict[str, Any]] = []
    for item in channel.findall("item")[:_MAX_ARTICLES_PER_QUERY]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else None
        pub_dt = _parse_pub_date(item.findtext("pubDate") or "")
        if pub_dt is None:
            # Fall back på fetched_at hvis pubDate mangler/uparsbar
            pub_dt = fetched_at
        articles.append(
            {
                "url": link,
                "event_ts": pub_dt,
                "fetched_at": fetched_at,
                "category": category["category"],
                "title": title,
                "source": source,
                "query_id": category["id"],
                "sentiment_label": None,
                "disruption_score": None,
            }
        )
    return articles


def fetch_news_intel(
    fetched_at: datetime | None = None,
    pacing_sec: float = _REQUEST_PACING_SEC,
    raw_responses: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Hent alle 9 kategorier sekvensielt og returner combined DataFrame.

    Args:
        fetched_at: tidspunkt for fetching (default = now UTC).
        pacing_sec: pause mellom kategori-kall (gratis-kilde-etiquette).
        raw_responses: dict {category_id: xml_string} for testing.

    Returns:
        DataFrame med ``NEWS_INTEL_COLS``-schema. Tom DataFrame hvis
        alle kall feiler.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc)
    raw_responses = raw_responses or {}

    rows: list[dict[str, Any]] = []
    for i, cat in enumerate(_CATEGORIES):
        if i > 0 and not raw_responses:
            time.sleep(pacing_sec)
        raw = raw_responses.get(cat["id"])
        articles = fetch_news_intel_category(cat, fetched_at=fetched_at, raw_response=raw)
        rows.extend(articles)

    if not rows:
        return pd.DataFrame(columns=list(NEWS_INTEL_COLS))

    df = pd.DataFrame(rows)
    return df[list(NEWS_INTEL_COLS)]


def fetch_news_intel_manual_csv(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt-populert news_intel-CSV (fallback ved RSS-feil eller
    for å pre-seede demo-data).

    Forventet schema: ``NEWS_INTEL_COLS``.
    Returnerer tom DataFrame hvis filen ikke finnes.
    """
    if not csv_path.exists():
        _log.info("news_intel.manual_csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(NEWS_INTEL_COLS))

    df = pd.read_csv(csv_path)
    missing = set(NEWS_INTEL_COLS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{csv_path.name} mangler kolonner: {sorted(missing)}. Påkrevd: {list(NEWS_INTEL_COLS)}"
        )
    return df[list(NEWS_INTEL_COLS)]


__all__ = [
    "fetch_news_intel",
    "fetch_news_intel_category",
    "fetch_news_intel_manual_csv",
]
