"""Sub-fase 12.10 Bunke 2 #6: news_intel_severity_veto driver-tester.

Driveren returnerer 0.5 (nøytral) som default; 0.0 (veto) hvis det er
en artikkel med ``disruption_score >= severity_threshold`` i en relevant
kategori innenfor ``lookback_hours``-vinduet.

P.t. har news_intel-tabellen ingen scoring (disruption_score=None for
alle rader) — driveren returnerer derfor 0.5 mot live-DB. Tester her
verifiserer logikken via mock-store med eksplisitt scoring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bedrock.engine.drivers import get

_NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


class _MockNewsStore:
    """Mock av DataStore.get_news_intel."""

    def __init__(self, rows: list[dict]) -> None:
        self._df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=[
                    "url",
                    "event_ts",
                    "fetched_at",
                    "category",
                    "title",
                    "source",
                    "query_id",
                    "sentiment_label",
                    "disruption_score",
                ]
            )
        )
        if not self._df.empty:
            # Mirror DataStore.get_news_intel: tz-naive timestamps
            self._df["event_ts"] = pd.to_datetime(self._df["event_ts"]).dt.tz_localize(None)

    def get_news_intel(
        self,
        category: str | None = None,
        from_event_ts: str | None = None,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        df = self._df
        if category is not None:
            df = df[df["category"] == category]
        if from_event_ts is not None:
            from_ts = pd.to_datetime(from_event_ts)
            if from_ts.tz is not None:
                from_ts = from_ts.tz_convert("UTC").tz_localize(None)
            df = df[df["event_ts"] >= from_ts]
        if last_n is not None:
            df = df.head(last_n)
        return df.copy()


def _row(category: str, hours_ago: float, disruption: float | None = None) -> dict:
    """Bygg én news_intel-rad med relativ tids-offset fra _NOW."""
    return {
        "url": f"https://example.com/{category}-{hours_ago}",
        "event_ts": (_NOW - timedelta(hours=hours_ago)).isoformat(),
        "fetched_at": (_NOW - timedelta(hours=hours_ago)).isoformat(),
        "category": category,
        "title": "Test article",
        "source": "Test",
        "query_id": category,
        "sentiment_label": None,
        "disruption_score": disruption,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("news_intel_severity_veto") is not None


# ---------------------------------------------------------------------------
# Default-atferd: ingen veto når ingen disruption_score er populert
# ---------------------------------------------------------------------------


def test_returns_neutral_when_disruption_score_all_null() -> None:
    """5 rader uten disruption_score (live-state p.t.) → 0.5."""
    rows = [_row("geopolitics", h) for h in [1, 5, 10, 24, 48]]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.5


def test_returns_neutral_when_no_articles_in_window() -> None:
    """Alle artikler er utenfor lookback_hours → 0.5."""
    rows = [_row("geopolitics", 100, disruption=0.9), _row("geopolitics", 200, disruption=0.95)]
    rows.extend(_row("geopolitics", 99 + i) for i in range(5))  # padding for min_samples
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    score = fn(store, "Gold", {"_now": _NOW.isoformat(), "lookback_hours": 72})
    assert score == 0.5


def test_returns_neutral_when_severity_below_threshold() -> None:
    rows = [
        _row("geopolitics", 5, disruption=0.5),  # under 0.7 default-terskel
        _row("geopolitics", 20, disruption=0.6),
    ] + [_row("geopolitics", 30 + i) for i in range(5)]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    score = fn(store, "Gold", {"_now": _NOW.isoformat()})
    assert score == 0.5


# ---------------------------------------------------------------------------
# Veto-atferd
# ---------------------------------------------------------------------------


def test_returns_zero_when_high_severity_in_window() -> None:
    """Én artikkel med disruption_score=0.85 i window → 0.0 (veto)."""
    rows = [
        _row("geopolitics", 5, disruption=0.85),  # innenfor 72h, over 0.7
    ] + [_row("geopolitics", 30 + i) for i in range(5)]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.0


def test_custom_severity_threshold() -> None:
    """Lavere threshold → flere events trigger veto."""
    rows = [
        _row("geopolitics", 10, disruption=0.55),
    ] + [_row("geopolitics", 30 + i) for i in range(5)]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    # threshold=0.5 → 0.55 ≥ 0.5 → veto
    assert fn(store, "Gold", {"_now": _NOW.isoformat(), "severity_threshold": 0.5}) == 0.0
    # threshold=0.7 (default) → 0.55 < 0.7 → ingen veto
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.5


def test_custom_lookback_hours() -> None:
    """24h-window: 48h-gammel disruption gjelder ikke."""
    rows = [_row("geopolitics", 48, disruption=0.9)] + [
        _row("geopolitics", 60 + i) for i in range(5)
    ]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    # 72h default — 48h-event er innenfor → veto
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.0
    # 24h custom — 48h-event er utenfor → nøytral
    assert fn(store, "Gold", {"_now": _NOW.isoformat(), "lookback_hours": 24}) == 0.5


def test_multi_category_search() -> None:
    """Driveren søker over flere kategorier."""
    rows = [
        _row("oil", 5, disruption=0.9),  # bare i 'oil'
    ] + [_row("oil", 30 + i) for i in range(5)]
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    # Default categories=['geopolitics'] → ingen 'oil'-events sett
    assert fn(store, "CrudeOil", {"_now": _NOW.isoformat()}) == 0.5
    # Med oil i listen → veto trigger
    assert fn(store, "CrudeOil", {"_now": _NOW.isoformat(), "categories": ["oil"]}) == 0.0
    # Med begge → veto trigger fra oil
    assert (
        fn(store, "CrudeOil", {"_now": _NOW.isoformat(), "categories": ["geopolitics", "oil"]})
        == 0.0
    )


# ---------------------------------------------------------------------------
# min_samples-guard
# ---------------------------------------------------------------------------


def test_min_samples_guard_returns_neutral_when_table_sparse() -> None:
    """< min_samples rader for kategori → 0.5 selv ved disruption."""
    rows = [_row("geopolitics", 5, disruption=0.95)]  # bare 1 rad
    store = _MockNewsStore(rows)
    fn = get("news_intel_severity_veto")
    # default min_samples=5 → 1 < 5 → 0.5
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.5
    # min_samples=1 → guard passes → veto
    assert fn(store, "Gold", {"_now": _NOW.isoformat(), "min_samples": 1}) == 0.0


def test_empty_news_intel_returns_neutral() -> None:
    """Tomt news_intel → 0.5."""
    store = _MockNewsStore([])
    fn = get("news_intel_severity_veto")
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.5


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_handles_store_exception_gracefully() -> None:
    class _Broken:
        def get_news_intel(self, category=None, from_event_ts=None, last_n=None):
            raise RuntimeError("DB error")

    fn = get("news_intel_severity_veto")
    assert fn(_Broken(), "Gold", {"_now": _NOW.isoformat()}) == 0.5
