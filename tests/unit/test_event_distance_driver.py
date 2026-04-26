"""Tester for `event_distance`-driveren (sub-fase 12.5+ session 105)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore
from bedrock.engine.drivers.risk import event_distance


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


_NOW = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)


def _seed(store: DataStore, events: list[tuple[datetime, str, str, str]]) -> None:
    """Seed events: list of (event_ts, country, title, impact)."""
    rows = [
        {
            "event_ts": dt.isoformat(),
            "country": c,
            "title": t,
            "impact": i,
            "forecast": None,
            "previous": None,
            "fetched_at": _NOW.isoformat(),
        }
        for (dt, c, t, i) in events
    ]
    store.append_econ_events(pd.DataFrame(rows))


def test_no_events_returns_empty_score(store: DataStore) -> None:
    """Tom kalender → empty_score (default 1.0)."""
    score = event_distance(store, "Gold", {"_now": _NOW.isoformat()})
    assert score == 1.0


def test_event_far_in_future_returns_one(store: DataStore) -> None:
    """Event 12 timer unna med min_hours=4 → 1.0."""
    _seed(store, [(_NOW + timedelta(hours=12), "USD", "FOMC", "High")])
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4, "lookahead_hours": 24},
    )
    assert score == 1.0


def test_event_at_min_hours_returns_one(store: DataStore) -> None:
    """Event akkurat min_hours unna → 1.0 (klart-grense)."""
    _seed(store, [(_NOW + timedelta(hours=4), "USD", "FOMC", "High")])
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4},
    )
    assert score == 1.0


def test_event_now_returns_zero(store: DataStore) -> None:
    """Event akkurat nå → 0.0."""
    _seed(store, [(_NOW, "USD", "FOMC", "High")])
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4},
    )
    assert score == 0.0


def test_event_at_half_min_hours_returns_half(store: DataStore) -> None:
    """Event 2 timer unna med min_hours=4 → 0.5."""
    _seed(store, [(_NOW + timedelta(hours=2), "USD", "FOMC", "High")])
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4},
    )
    assert score == pytest.approx(0.5)


def test_country_filter(store: DataStore) -> None:
    """JPY-event skal ikke trigge for USD-kun-instrument."""
    _seed(
        store,
        [
            (_NOW + timedelta(hours=1), "JPY", "BOJ Press", "High"),
            (_NOW + timedelta(hours=12), "USD", "Late event", "High"),
        ],
    )
    # Gold ser bare USD → JPY ignoreres → nærmeste USD er 12h unna → 1.0
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4, "countries": ["USD"]},
    )
    assert score == 1.0


def test_multi_country_filter(store: DataStore) -> None:
    """USDJPY ser både USD og JPY."""
    _seed(
        store,
        [
            (_NOW + timedelta(hours=1), "JPY", "BOJ", "High"),
        ],
    )
    score = event_distance(
        store,
        "USDJPY",
        {"_now": _NOW.isoformat(), "min_hours": 4, "countries": ["USD", "JPY"]},
    )
    # JPY-event 1h unna med min_hours=4 → 0.25
    assert score == pytest.approx(0.25)


def test_impact_filter(store: DataStore) -> None:
    """Medium-impact event ignoreres når impact_levels=['High']."""
    _seed(
        store,
        [
            (_NOW + timedelta(hours=1), "USD", "ISM PMI", "Medium"),
            (_NOW + timedelta(hours=12), "USD", "FOMC", "High"),
        ],
    )
    score = event_distance(
        store,
        "Gold",
        {
            "_now": _NOW.isoformat(),
            "min_hours": 4,
            "impact_levels": ["High"],
        },
    )
    assert score == 1.0  # Medium ignorert; High er 12h unna


def test_high_and_medium_combined(store: DataStore) -> None:
    """impact_levels=['High','Medium'] tar med begge."""
    _seed(
        store,
        [
            (_NOW + timedelta(hours=1), "USD", "ISM PMI", "Medium"),
            (_NOW + timedelta(hours=12), "USD", "FOMC", "High"),
        ],
    )
    score = event_distance(
        store,
        "Gold",
        {
            "_now": _NOW.isoformat(),
            "min_hours": 4,
            "impact_levels": ["High", "Medium"],
        },
    )
    # Medium 1h unna → 0.25
    assert score == pytest.approx(0.25)


def test_past_events_ignored(store: DataStore) -> None:
    """Events før now ignoreres helt."""
    _seed(
        store,
        [
            (_NOW - timedelta(hours=2), "USD", "Past FOMC", "High"),
            (_NOW + timedelta(hours=12), "USD", "Future", "High"),
        ],
    )
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4},
    )
    # Past ignorert; future 12h unna → 1.0
    assert score == 1.0


def test_lookahead_caps_window(store: DataStore) -> None:
    """Event utenfor lookahead-vinduet teller ikke."""
    _seed(
        store,
        [
            (_NOW + timedelta(hours=48), "USD", "Far FOMC", "High"),
        ],
    )
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 4, "lookahead_hours": 24},
    )
    # 48h utenfor 24h-window → empty_score (1.0)
    assert score == 1.0


def test_error_when_store_missing_method() -> None:
    """Defekt store (mangler get_econ_events) → error_score (0.5)."""

    class BrokenStore:
        pass

    score = event_distance(BrokenStore(), "Gold", {"_now": _NOW.isoformat()})
    assert score == 0.5


def test_invalid_min_hours_returns_error_score(store: DataStore) -> None:
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "min_hours": 0},
    )
    assert score == 0.5


def test_custom_empty_and_error_scores(store: DataStore) -> None:
    """YAML kan overstyre empty_score / error_score."""
    # Tom DB med custom empty
    score = event_distance(
        store,
        "Gold",
        {"_now": _NOW.isoformat(), "empty_score": 0.7},
    )
    assert score == 0.7

    # Defekt store med custom error
    class BrokenStore:
        pass

    score2 = event_distance(
        BrokenStore(),
        "Gold",
        {"_now": _NOW.isoformat(), "error_score": 0.3},
    )
    assert score2 == 0.3


def test_driver_registered() -> None:
    """Verifiser at @register-dekoratoren har tatt event_distance opp."""
    from bedrock.engine.drivers import get, is_registered

    assert is_registered("event_distance")
    fn = get("event_distance")
    assert callable(fn)
