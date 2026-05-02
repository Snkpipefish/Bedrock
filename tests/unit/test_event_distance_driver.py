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


# ---------------------------------------------------------------------------
# Sub-fase 12.10 Bunke 1 Bug-3: future-actual look-ahead-verifisering
# ---------------------------------------------------------------------------
#
# Spec: event_distance må ikke lese `actual`-feltet (= post-event-resultat).
# Schema-status (verifisert 2026-05-02): econ_events-tabellen har ikke
# `actual`-kolonne — kun `forecast` (analytiker-forventning før event) og
# `previous` (forrige rapporterte verdi). Begge er pre-event-data og
# look-ahead-fri.
#
# Disse testene er regresjons-vakter: hvis noen senere legger til
# `actual` i schema eller endrer driveren til å lese det, må
# alarmlydene gå.


def test_econ_events_schema_has_actual_column_for_surprise_drivers() -> None:
    """`actual` ble lagt til i schema per ADR-014 (12.10 Spor B) for cross-
    source *_surprise-drivere (FRED-backfill). Look-ahead-vern er flyttet til
    driver-laget: event-baserte drivere som event_distance leser KUN
    pre-event-felter (event_ts/forecast/previous) — sjekkes av
    `test_event_distance_source_does_not_reference_actual` nedenfor.
    """
    from bedrock.data.schemas import ECON_EVENTS_COLS

    assert "actual" in ECON_EVENTS_COLS, (
        "ADR-014: `actual`-kolonnen skal finnes i econ_events-schema for "
        "*_surprise-drivere. Hvis denne mangler er migrasjonen i "
        "DataStore.__init__ ikke kjørt eller schemas.py er rullet tilbake."
    )


def test_event_distance_source_does_not_reference_actual() -> None:
    """Regresjons-vakt: driver-koden refererer ikke `actual`-feltet."""
    import inspect

    from bedrock.engine.drivers.risk import event_distance

    source = inspect.getsource(event_distance)
    # Sjekker at strengen "actual" ikke forekommer som identifikator i koden
    # (kan tillates i kommentarer som "actual_score" osv. — vi er strenge
    # for å unngå hvilken som helst look-ahead-introduksjon).
    assert '"actual"' not in source, (
        "event_distance refererer 'actual' — Bug-3 brutt: driveren skal "
        "kun lese pre-event-felter (event_ts/forecast/previous)."
    )


def test_event_distance_ignores_forecast_and_previous_values(
    store: DataStore,
) -> None:
    """Score skal være identisk uansett innholdet i forecast/previous-felt
    siden event_distance kun bruker event_ts for tids-buffer-beregning."""
    rows_baseline = [
        {
            "event_ts": (_NOW + timedelta(hours=2)).isoformat(),
            "country": "USD",
            "title": "FOMC",
            "impact": "High",
            "forecast": None,
            "previous": None,
            "fetched_at": _NOW.isoformat(),
        }
    ]
    store.append_econ_events(pd.DataFrame(rows_baseline))
    score_baseline = event_distance(store, "Gold", {"_now": _NOW.isoformat()})

    # Ny store med samme event_ts men populerte forecast+previous
    import sqlite3

    db_path = store._db_path  # type: ignore[attr-defined]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM econ_events")
        conn.commit()
    store.append_econ_events(
        pd.DataFrame(
            [
                {
                    "event_ts": (_NOW + timedelta(hours=2)).isoformat(),
                    "country": "USD",
                    "title": "FOMC",
                    "impact": "High",
                    "forecast": "5.50%",
                    "previous": "5.25%",
                    "fetched_at": _NOW.isoformat(),
                }
            ]
        )
    )
    score_with_values = event_distance(store, "Gold", {"_now": _NOW.isoformat()})

    assert score_baseline == score_with_values, (
        "event_distance skal ikke endre seg når forecast/previous-felter "
        "er populert — driveren bruker kun event_ts."
    )
