"""Sub-fase 12.10 Bunke 8 driver-tester."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered

_NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("d", ["seismic_m6_global_24h", "seismic_chile_peru_copper"])
def test_driver_registered(d: str) -> None:
    assert is_registered(d)
    assert callable(get(d))


class _MockSeismicStore:
    def __init__(self, events: list[dict]) -> None:
        self._events = events

    def get_seismic_events(
        self,
        *,
        region: str | None = None,
        regions=None,
        from_ts=None,
        min_magnitude: float | None = None,
    ):
        rows = []
        for ev in self._events:
            ev_ts = pd.to_datetime(ev["event_ts"], utc=True)
            if from_ts is not None:
                ft = (
                    pd.to_datetime(from_ts, utc=True)
                    if not isinstance(from_ts, datetime)
                    else (
                        pd.Timestamp(from_ts)
                        if from_ts.tzinfo
                        else pd.Timestamp(from_ts).tz_localize("UTC")
                    )
                )
                if ev_ts < ft:
                    continue
            if min_magnitude is not None and ev["magnitude"] < min_magnitude:
                continue
            if region is not None and ev.get("region") != region:
                continue
            rows.append(ev)
        return (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["event_ts", "magnitude", "region"])
        )


def test_seismic_m6_no_events() -> None:
    fn = get("seismic_m6_global_24h")
    store = _MockSeismicStore([])
    # Tom DB → bull_when=high default, score=0 (ingen safe-haven-trigger)
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 0.0


def test_seismic_m6_two_events_clustering() -> None:
    fn = get("seismic_m6_global_24h")
    events = [
        {
            "event_ts": (_NOW - timedelta(hours=2)).isoformat(),
            "magnitude": 6.5,
            "region": "Indonesia",
        },
        {
            "event_ts": (_NOW - timedelta(hours=10)).isoformat(),
            "magnitude": 6.1,
            "region": "Chile / Peru",
        },
    ]
    store = _MockSeismicStore(events)
    assert fn(store, "Gold", {"_now": _NOW.isoformat()}) == 1.0


def test_seismic_chile_peru_one_event() -> None:
    fn = get("seismic_chile_peru_copper")
    events = [
        {
            "event_ts": (_NOW - timedelta(days=2)).isoformat(),
            "magnitude": 5.8,
            "region": "Chile / Peru",
        },
    ]
    store = _MockSeismicStore(events)
    assert fn(store, "Copper", {"_now": _NOW.isoformat()}) == 0.75


def test_seismic_chile_peru_no_events() -> None:
    fn = get("seismic_chile_peru_copper")
    store = _MockSeismicStore([])
    # Empty → 0.5 baseline (ikke 0 — ingen disruption-bevis ≠ bear)
    assert fn(store, "Copper", {"_now": _NOW.isoformat()}) == 0.5
