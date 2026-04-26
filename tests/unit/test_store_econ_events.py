"""Tester for econ_events-tabellen i DataStore (sub-fase 12.5+ session 105)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _events_df(rows: list[dict]) -> pd.DataFrame:
    """Bygg econ_events-DataFrame fra liste av dicts."""
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_econ_events_init_creates_table(store: DataStore) -> None:
    """DataStore.__init__ kjører DDL_ECON_EVENTS — tabellen skal eksistere."""
    df = store.get_econ_events()
    assert df.empty
    # Forventede kolonner
    assert set(df.columns) == {
        "event_ts",
        "country",
        "title",
        "impact",
        "forecast",
        "previous",
        "fetched_at",
    }


def test_append_and_get_roundtrip(store: DataStore) -> None:
    fetched_at = "2026-04-27T12:00:00+00:00"
    df = _events_df(
        [
            {
                "event_ts": "2026-04-30T18:00:00+00:00",
                "country": "USD",
                "title": "FOMC Statement",
                "impact": "High",
                "forecast": "5.25%",
                "previous": "5.25%",
                "fetched_at": fetched_at,
            },
            {
                "event_ts": "2026-05-02T12:30:00+00:00",
                "country": "USD",
                "title": "Non-Farm Employment Change",
                "impact": "High",
                "forecast": "180K",
                "previous": "175K",
                "fetched_at": fetched_at,
            },
        ]
    )
    n = store.append_econ_events(df)
    assert n == 2

    out = store.get_econ_events()
    assert len(out) == 2
    # Sortert ASC på event_ts
    assert out.iloc[0]["title"] == "FOMC Statement"
    assert out.iloc[1]["title"] == "Non-Farm Employment Change"
    # event_ts skal være tz-aware
    assert out["event_ts"].dt.tz is not None


def test_filter_by_country(store: DataStore) -> None:
    fetched_at = "2026-04-27T12:00:00+00:00"
    df = _events_df(
        [
            {
                "event_ts": "2026-05-01T12:00:00+00:00",
                "country": "USD",
                "title": "CPI m/m",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
            {
                "event_ts": "2026-05-01T12:30:00+00:00",
                "country": "EUR",
                "title": "ECB Rate",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
        ]
    )
    store.append_econ_events(df)

    eur_only = store.get_econ_events(countries=["EUR"])
    assert len(eur_only) == 1
    assert eur_only.iloc[0]["country"] == "EUR"

    multi = store.get_econ_events(countries=["USD", "EUR"])
    assert len(multi) == 2


def test_filter_by_impact(store: DataStore) -> None:
    fetched_at = "2026-04-27T12:00:00+00:00"
    df = _events_df(
        [
            {
                "event_ts": "2026-05-01T08:00:00+00:00",
                "country": "USD",
                "title": "ISM PMI",
                "impact": "Medium",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
            {
                "event_ts": "2026-05-01T12:30:00+00:00",
                "country": "USD",
                "title": "FOMC",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
        ]
    )
    store.append_econ_events(df)

    high = store.get_econ_events(impact_levels=["High"])
    assert len(high) == 1
    assert high.iloc[0]["title"] == "FOMC"


def test_filter_by_time_range(store: DataStore) -> None:
    fetched_at = "2026-04-27T12:00:00+00:00"
    df = _events_df(
        [
            {
                "event_ts": "2026-04-28T12:00:00+00:00",
                "country": "USD",
                "title": "T-",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
            {
                "event_ts": "2026-05-15T12:00:00+00:00",
                "country": "USD",
                "title": "T+",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": fetched_at,
            },
        ]
    )
    store.append_econ_events(df)

    later = store.get_econ_events(from_ts="2026-05-01T00:00:00")
    assert len(later) == 1
    assert later.iloc[0]["title"] == "T+"

    earlier = store.get_econ_events(to_ts="2026-05-01T00:00:00")
    assert len(earlier) == 1
    assert earlier.iloc[0]["title"] == "T-"


def test_idempotent_on_pk(store: DataStore) -> None:
    """Samme (event_ts, country, title) overskrives, ikke dupliseres."""
    fetched_at_v1 = "2026-04-27T12:00:00+00:00"
    fetched_at_v2 = "2026-04-27T18:00:00+00:00"
    df_v1 = _events_df(
        [
            {
                "event_ts": "2026-04-30T18:00:00+00:00",
                "country": "USD",
                "title": "FOMC",
                "impact": "High",
                "forecast": "5.25%",
                "previous": "5.25%",
                "fetched_at": fetched_at_v1,
            }
        ]
    )
    df_v2 = _events_df(
        [
            {
                "event_ts": "2026-04-30T18:00:00+00:00",
                "country": "USD",
                "title": "FOMC",
                "impact": "High",
                "forecast": "5.50%",  # endret
                "previous": "5.25%",
                "fetched_at": fetched_at_v2,
            }
        ]
    )
    store.append_econ_events(df_v1)
    store.append_econ_events(df_v2)
    out = store.get_econ_events()
    assert len(out) == 1
    assert out.iloc[0]["forecast"] == "5.50%"


def test_append_empty_df_returns_zero(store: DataStore) -> None:
    n = store.append_econ_events(pd.DataFrame(columns=["event_ts", "country", "title"]))
    assert n == 0
    assert store.get_econ_events().empty


def test_pydantic_validates_impact_level() -> None:
    """EconomicEvent rejekterer ugyldig impact-verdi."""
    from datetime import datetime, timezone

    from bedrock.data.schemas import EconomicEvent

    with pytest.raises(ValueError, match="impact"):
        EconomicEvent(
            event_ts=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc),
            country="USD",
            title="FOMC",
            impact="Critical",  # ikke gyldig
            fetched_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        )

    # Valid impact passes
    ev = EconomicEvent(
        event_ts=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc),
        country="USD",
        title="FOMC",
        impact="High",
        fetched_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
    )
    assert ev.impact == "High"
