# pyright: reportArgumentType=false, reportGeneralTypeIssues=false
"""Tester for news_intel-tabell + DataStore-metoder + Pydantic-validering
(sub-fase 12.5+ session 114).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import NEWS_INTEL_COLS, NewsIntelArticle
from bedrock.data.store import DataStore


def _article_df(
    rows: list[dict] | None = None,
) -> pd.DataFrame:
    if rows is None:
        rows = [
            {
                "url": "https://news.google.com/article/A1",
                "event_ts": "2026-04-27T10:00:00",
                "fetched_at": "2026-04-27T12:00:00",
                "category": "gold",
                "title": "Gold price surges to record",
                "source": "Reuters",
                "query_id": "gold",
                "sentiment_label": None,
                "disruption_score": None,
            },
            {
                "url": "https://news.google.com/article/A2",
                "event_ts": "2026-04-27T09:00:00",
                "fetched_at": "2026-04-27T12:00:00",
                "category": "oil",
                "title": "Oil supply disruption in Middle East",
                "source": "Bloomberg",
                "query_id": "oil",
                "sentiment_label": None,
                "disruption_score": None,
            },
        ]
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Pydantic-validering
# ---------------------------------------------------------------------------


def test_news_intel_article_accepts_valid_categories() -> None:
    for cat in [
        "gold",
        "silver",
        "copper",
        "oil",
        "gas",
        "grains",
        "softs",
        "geopolitics",
        "agri_weather",
    ]:
        a = NewsIntelArticle(
            url=f"https://x.test/{cat}",
            event_ts=datetime(2026, 4, 27, 10),
            fetched_at=datetime(2026, 4, 27, 12),
            category=cat,
            title="Test headline",
            query_id=cat,
        )
        assert a.category == cat


def test_news_intel_article_lowercases_category() -> None:
    a = NewsIntelArticle(
        url="https://x.test/u",
        event_ts=datetime(2026, 4, 27, 10),
        fetched_at=datetime(2026, 4, 27, 12),
        category="GOLD",
        title="t",
        query_id="gold",
    )
    assert a.category == "gold"


def test_news_intel_article_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="category"):
        NewsIntelArticle(
            url="https://x.test/u",
            event_ts=datetime(2026, 4, 27, 10),
            fetched_at=datetime(2026, 4, 27, 12),
            category="bogus",
            title="t",
            query_id="bogus",
        )


def test_news_intel_article_validates_sentiment_label() -> None:
    for label in ["bull", "bear", "neutral", None]:
        NewsIntelArticle(
            url=f"https://x.test/{label}",
            event_ts=datetime(2026, 4, 27, 10),
            fetched_at=datetime(2026, 4, 27, 12),
            category="gold",
            title="t",
            query_id="gold",
            sentiment_label=label,
        )
    with pytest.raises(ValueError, match="sentiment_label"):
        NewsIntelArticle(
            url="https://x.test/u",
            event_ts=datetime(2026, 4, 27, 10),
            fetched_at=datetime(2026, 4, 27, 12),
            category="gold",
            title="t",
            query_id="gold",
            sentiment_label="positive",
        )


def test_news_intel_article_validates_disruption_score_range() -> None:
    NewsIntelArticle(
        url="https://x.test/u",
        event_ts=datetime(2026, 4, 27, 10),
        fetched_at=datetime(2026, 4, 27, 12),
        category="gold",
        title="t",
        query_id="gold",
        disruption_score=0.5,
    )
    with pytest.raises(ValueError, match="disruption_score"):
        NewsIntelArticle(
            url="https://x.test/u",
            event_ts=datetime(2026, 4, 27, 10),
            fetched_at=datetime(2026, 4, 27, 12),
            category="gold",
            title="t",
            query_id="gold",
            disruption_score=1.5,
        )


# ---------------------------------------------------------------------------
# append + get
# ---------------------------------------------------------------------------


def test_append_and_get_basic(store: DataStore) -> None:
    n = store.append_news_intel(_article_df())
    assert n == 2
    df = store.get_news_intel()
    assert len(df) == 2
    # Sortert DESC på event_ts (nyeste først)
    assert df["url"].iloc[0] == "https://news.google.com/article/A1"


def test_append_idempotent_on_url(store: DataStore) -> None:
    """Samme URL skal IKKE overskrives — bevarer FØRSTE fetched_at."""
    store.append_news_intel(_article_df())
    # Re-append samme rader, men med ny fetched_at
    second = _article_df()
    second["fetched_at"] = "2026-04-28T08:00:00"
    n_new = store.append_news_intel(second)
    assert n_new == 0  # ingen nye rader
    df = store.get_news_intel()
    assert len(df) == 2
    # Først fetched_at (12:00) skal være bevart
    first_row = df[df["url"] == "https://news.google.com/article/A1"].iloc[0]
    assert first_row["fetched_at"] == pd.Timestamp("2026-04-27T12:00:00")


def test_get_news_intel_filter_by_category(store: DataStore) -> None:
    store.append_news_intel(_article_df())
    df = store.get_news_intel(category="oil")
    assert len(df) == 1
    assert df["url"].iloc[0] == "https://news.google.com/article/A2"


def test_get_news_intel_filter_by_from_ts(store: DataStore) -> None:
    store.append_news_intel(_article_df())
    df = store.get_news_intel(from_event_ts="2026-04-27T09:30:00")
    assert len(df) == 1
    assert df["url"].iloc[0] == "https://news.google.com/article/A1"


def test_get_news_intel_last_n(store: DataStore) -> None:
    store.append_news_intel(_article_df())
    df = store.get_news_intel(last_n=1)
    assert len(df) == 1


def test_get_news_intel_empty(store: DataStore) -> None:
    df = store.get_news_intel()
    assert df.empty


def test_append_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"url": ["https://x"], "title": ["t"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_news_intel(bad)


def test_append_empty_returns_zero(store: DataStore) -> None:
    empty = pd.DataFrame(columns=list(NEWS_INTEL_COLS))
    assert store.append_news_intel(empty) == 0


# ---------------------------------------------------------------------------
# has_news_intel
# ---------------------------------------------------------------------------


def test_has_negative(store: DataStore) -> None:
    assert not store.has_news_intel()


def test_has_positive(store: DataStore) -> None:
    store.append_news_intel(_article_df())
    assert store.has_news_intel()


# ---------------------------------------------------------------------------
# Persistens + scoring-ready felt
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_news_intel(_article_df())
    df = DataStore(db).get_news_intel()
    assert len(df) == 2


def test_sentiment_and_disruption_score_nullable_default(store: DataStore) -> None:
    """sentiment_label + disruption_score skal lagres som NULL ved default."""
    store.append_news_intel(_article_df())
    df = store.get_news_intel()
    assert df["sentiment_label"].isna().all()
    assert df["disruption_score"].isna().all()


def test_sentiment_and_disruption_score_can_be_populated(store: DataStore) -> None:
    """Når en fremtidig classifier skriver disse, skal de roundtripe korrekt."""
    rows = [
        {
            "url": "https://news.google.com/article/B1",
            "event_ts": "2026-04-27T10:00:00",
            "fetched_at": "2026-04-27T12:00:00",
            "category": "oil",
            "title": "Strait of Hormuz attack disrupts oil",
            "source": "Reuters",
            "query_id": "oil",
            "sentiment_label": "bull",
            "disruption_score": 0.85,
        }
    ]
    store.append_news_intel(pd.DataFrame(rows))
    df = store.get_news_intel(category="oil")
    assert df["sentiment_label"].iloc[0] == "bull"
    assert df["disruption_score"].iloc[0] == 0.85
