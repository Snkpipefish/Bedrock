# pyright: reportArgumentType=false
"""Tester for ``bedrock.fetch.news_intel`` (sub-fase 12.5+ session 114).

Verifiserer Google News RSS-parsing + per-kategori-orchestrator + manuell
CSV-fallback. Ingen network-IO i tester (raw_response/raw_responses-injection).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import NEWS_INTEL_COLS
from bedrock.fetch.news_intel import (
    _CATEGORIES,
    fetch_news_intel,
    fetch_news_intel_category,
    fetch_news_intel_manual_csv,
)


def _rss_xml(items: list[dict[str, str]]) -> str:
    """Bygg minimalt Google News RSS-format for testing."""
    items_xml = "".join(
        f"""
        <item>
            <title>{it.get("title", "")}</title>
            <link>{it.get("link", "")}</link>
            <pubDate>{it.get("pubDate", "")}</pubDate>
            {(f"<source>{it['source']}</source>" if "source" in it else "")}
        </item>"""
        for it in items
    )
    return f"""<?xml version="1.0"?><rss><channel><title>News</title>
{items_xml}
</channel></rss>"""


_GOLD_CAT = {"id": "gold", "category": "gold", "query": "gold mine"}


# ---------------------------------------------------------------------------
# Categories sanity
# ---------------------------------------------------------------------------


def test_all_9_categories_defined() -> None:
    ids = {c["id"] for c in _CATEGORIES}
    assert ids == {
        "gold",
        "silver",
        "copper",
        "oil",
        "gas",
        "grains",
        "softs",
        "geopolitics",
        "agri_weather",
    }


def test_each_category_has_canonical_id_match() -> None:
    """category-feltet i _CATEGORIES skal matche bedrock-canonical."""
    for cat in _CATEGORIES:
        assert cat["category"] == cat["id"]


# ---------------------------------------------------------------------------
# fetch_news_intel_category
# ---------------------------------------------------------------------------


def test_category_parses_basic_rss() -> None:
    raw = _rss_xml(
        [
            {
                "title": "Gold rally",
                "link": "https://news.google.com/A1",
                "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
                "source": "Reuters",
            },
        ]
    )
    fetched = datetime(2026, 4, 27, 12, tzinfo=timezone.utc)
    rows = fetch_news_intel_category(_GOLD_CAT, fetched_at=fetched, raw_response=raw)
    assert len(rows) == 1
    r = rows[0]
    assert r["url"] == "https://news.google.com/A1"
    assert r["title"] == "Gold rally"
    assert r["source"] == "Reuters"
    assert r["category"] == "gold"
    assert r["query_id"] == "gold"
    assert r["sentiment_label"] is None
    assert r["disruption_score"] is None
    assert r["event_ts"].astimezone(timezone.utc) == datetime(2026, 4, 27, 10, tzinfo=timezone.utc)
    assert r["fetched_at"] == fetched


def test_category_falls_back_to_fetched_at_when_pubdate_unparsable() -> None:
    raw = _rss_xml(
        [
            {
                "title": "Bad date",
                "link": "https://news.google.com/A2",
                "pubDate": "garbage",
            }
        ]
    )
    fetched = datetime(2026, 4, 27, 12, tzinfo=timezone.utc)
    rows = fetch_news_intel_category(_GOLD_CAT, fetched_at=fetched, raw_response=raw)
    assert len(rows) == 1
    assert rows[0]["event_ts"] == fetched


def test_category_skips_items_without_title_or_link() -> None:
    raw = _rss_xml(
        [
            {"title": "", "link": "https://x.test/A1"},
            {"title": "OK", "link": ""},
            {
                "title": "Valid",
                "link": "https://x.test/A3",
                "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
            },
        ]
    )
    rows = fetch_news_intel_category(_GOLD_CAT, raw_response=raw)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://x.test/A3"


def test_category_handles_missing_source_element() -> None:
    raw = _rss_xml(
        [
            {
                "title": "No src",
                "link": "https://x.test/A1",
                "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
            }
        ]
    )
    rows = fetch_news_intel_category(_GOLD_CAT, raw_response=raw)
    assert rows[0]["source"] is None


def test_category_caps_at_max_articles() -> None:
    """Maks 10 artikler per query — beskyttelse mot RSS-feed-explosion."""
    items = [
        {
            "title": f"Item {i}",
            "link": f"https://x.test/A{i}",
            "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
        }
        for i in range(20)
    ]
    raw = _rss_xml(items)
    rows = fetch_news_intel_category(_GOLD_CAT, raw_response=raw)
    assert len(rows) == 10


def test_category_returns_empty_on_malformed_xml() -> None:
    rows = fetch_news_intel_category(_GOLD_CAT, raw_response="<not valid xml>")
    assert rows == []


def test_category_returns_empty_when_no_channel() -> None:
    rows = fetch_news_intel_category(
        _GOLD_CAT,
        raw_response='<?xml version="1.0"?><rss><other/></rss>',
    )
    assert rows == []


# ---------------------------------------------------------------------------
# fetch_news_intel orchestrator
# ---------------------------------------------------------------------------


def test_fetch_news_intel_combines_all_categories() -> None:
    """Orchestrator skal hente alle 9 kategorier og returnere kombinert
    DataFrame."""
    raws = {}
    for cat in _CATEGORIES:
        raws[cat["id"]] = _rss_xml(
            [
                {
                    "title": f"{cat['id']} news",
                    "link": f"https://x.test/{cat['id']}/A1",
                    "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
                    "source": "Reuters",
                }
            ]
        )
    df = fetch_news_intel(
        fetched_at=datetime(2026, 4, 27, 12, tzinfo=timezone.utc),
        raw_responses=raws,
    )
    assert len(df) == 9
    assert set(df["category"]) == {c["id"] for c in _CATEGORIES}
    assert list(df.columns) == list(NEWS_INTEL_COLS)


def test_fetch_news_intel_continues_when_one_category_fails() -> None:
    """Per-kategori feil skal ikke ta ned hele orchestratoren."""
    raws = {"gold": "<not xml>"}
    for cat in _CATEGORIES:
        if cat["id"] == "gold":
            continue
        raws[cat["id"]] = _rss_xml(
            [
                {
                    "title": f"{cat['id']} news",
                    "link": f"https://x.test/{cat['id']}/A1",
                    "pubDate": "Sun, 27 Apr 2026 10:00:00 GMT",
                }
            ]
        )
    df = fetch_news_intel(
        fetched_at=datetime(2026, 4, 27, 12, tzinfo=timezone.utc),
        raw_responses=raws,
    )
    assert len(df) == 8
    assert "gold" not in set(df["category"])


def test_fetch_news_intel_empty_when_all_fail() -> None:
    raws = {cat["id"]: "<bad>" for cat in _CATEGORIES}
    df = fetch_news_intel(
        fetched_at=datetime(2026, 4, 27, 12, tzinfo=timezone.utc),
        raw_responses=raws,
    )
    assert df.empty
    assert list(df.columns) == list(NEWS_INTEL_COLS)


# ---------------------------------------------------------------------------
# Manuell CSV
# ---------------------------------------------------------------------------


def test_manual_csv_reads_valid_rows(tmp_path: Path) -> None:
    csv = tmp_path / "news.csv"
    pd.DataFrame(
        {
            "url": ["https://x.test/M1"],
            "event_ts": ["2026-04-26T10:00:00"],
            "fetched_at": ["2026-04-27T08:00:00"],
            "category": ["gold"],
            "title": ["Manual entry"],
            "source": ["Manual"],
            "query_id": ["gold"],
            "sentiment_label": [None],
            "disruption_score": [None],
        }
    ).to_csv(csv, index=False)
    df = fetch_news_intel_manual_csv(csv)
    assert len(df) == 1
    assert df["url"].iloc[0] == "https://x.test/M1"
    assert list(df.columns) == list(NEWS_INTEL_COLS)


def test_manual_csv_missing_file_returns_empty(tmp_path: Path) -> None:
    df = fetch_news_intel_manual_csv(tmp_path / "missing.csv")
    assert df.empty
    assert list(df.columns) == list(NEWS_INTEL_COLS)


def test_manual_csv_missing_columns_raises(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    pd.DataFrame({"url": ["https://x"], "title": ["t"]}).to_csv(csv, index=False)
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_news_intel_manual_csv(csv)
