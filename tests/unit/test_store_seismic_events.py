"""Tester for seismic_events-støtte i DataStore (sub-fase 12.5+ session 109)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _seismic_df(
    *,
    event_id_prefix: str = "us",
    n: int = 3,
    base_mag: float = 5.0,
    region: str | None = "Chile / Peru",
    base_lat: float = -23.0,
    base_lon: float = -70.0,
) -> pd.DataFrame:
    """Bygger en DataFrame med n seismic-events."""
    base_ts = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        rows.append(
            {
                "event_id": f"{event_id_prefix}_{i:04d}",
                "event_ts": base_ts.replace(day=5 + i),
                "magnitude": base_mag + 0.1 * i,
                "latitude": base_lat + 0.5 * i,
                "longitude": base_lon - 0.3 * i,
                "depth_km": 30.0 + 5.0 * i,
                "place": f"Region {i}",
                "region": region,
                "url": f"https://example.com/{i}",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_append_and_get_all(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df())
    df = store.get_seismic_events()
    assert len(df) == 3
    assert list(df.columns) == [
        "event_id",
        "event_ts",
        "magnitude",
        "latitude",
        "longitude",
        "depth_km",
        "place",
        "region",
        "url",
    ]
    assert df["event_id"].iloc[0] == "us_0000"
    assert df["magnitude"].iloc[0] == 5.0


def test_dedupe_on_event_id(store: DataStore) -> None:
    """Samme event_id med endret magnitude (revisjon) overskriver."""
    store.append_seismic_events(_seismic_df())
    revision = pd.DataFrame(
        [
            {
                "event_id": "us_0000",
                "event_ts": datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc),
                "magnitude": 9.99,  # revidert
                "latitude": -23.0,
                "longitude": -70.0,
                "depth_km": 30.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": "https://example.com/0",
            }
        ]
    )
    store.append_seismic_events(revision)
    df = store.get_seismic_events()
    assert len(df) == 3  # ikke 4
    revised = df[df["event_id"] == "us_0000"].iloc[0]
    assert revised["magnitude"] == 9.99


def test_filter_by_region(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df(region="Chile / Peru"))
    store.append_seismic_events(_seismic_df(event_id_prefix="cn", region="Mongolia / Kina"))

    chile = store.get_seismic_events(region="Chile / Peru")
    mongolia = store.get_seismic_events(region="Mongolia / Kina")

    assert len(chile) == 3
    assert len(mongolia) == 3
    assert (chile["region"] == "Chile / Peru").all()


def test_filter_by_regions_list(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df(region="Chile / Peru"))
    store.append_seismic_events(_seismic_df(event_id_prefix="cn", region="Mongolia / Kina"))
    store.append_seismic_events(_seismic_df(event_id_prefix="jp", region="Japan"))

    metals = store.get_seismic_events(regions=["Chile / Peru", "Mongolia / Kina"])
    assert len(metals) == 6
    assert set(metals["region"].unique()) == {"Chile / Peru", "Mongolia / Kina"}


def test_filter_by_from_ts(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df())  # day 5, 6, 7
    after = store.get_seismic_events(from_ts=datetime(2024, 1, 7, 0, 0, tzinfo=timezone.utc))
    assert len(after) == 1
    assert after["event_id"].iloc[0] == "us_0002"


def test_filter_by_min_magnitude(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df(base_mag=4.5))  # 4.5, 4.6, 4.7
    above = store.get_seismic_events(min_magnitude=4.6)
    assert len(above) == 2


def test_combined_filters(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df(region="Chile / Peru", base_mag=5.0))
    store.append_seismic_events(
        _seismic_df(event_id_prefix="cn", region="Mongolia / Kina", base_mag=6.0)
    )
    df = store.get_seismic_events(regions=["Chile / Peru", "Mongolia / Kina"], min_magnitude=5.5)
    # Chile alle < 5.5, Mongolia alle >= 6.0
    assert len(df) == 3
    assert (df["region"] == "Mongolia / Kina").all()


def test_returns_empty_when_no_match(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df())
    df = store.get_seismic_events(region="Antarktis")
    assert df.empty


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"event_id": ["a"], "magnitude": [5.0]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_seismic_events(bad)


def test_null_region_preserved(store: DataStore) -> None:
    """Events utenfor mining-regions har region=None men lagres uansett."""
    df = pd.DataFrame(
        [
            {
                "event_id": "us_random",
                "event_ts": datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc),
                "magnitude": 5.0,
                "latitude": 0.0,
                "longitude": 0.0,
                "depth_km": 30.0,
                "place": "Mid-Atlantic",
                "region": None,
                "url": "https://example.com/r",
            }
        ]
    )
    store.append_seismic_events(df)
    out = store.get_seismic_events()
    assert len(out) == 1
    assert pd.isna(out["region"].iloc[0])


# ---------------------------------------------------------------------------
# has_seismic_events
# ---------------------------------------------------------------------------


def test_has_seismic_events_negative(store: DataStore) -> None:
    assert not store.has_seismic_events()


def test_has_seismic_events_positive(store: DataStore) -> None:
    store.append_seismic_events(_seismic_df())
    assert store.has_seismic_events()


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_seismic_events(_seismic_df())
    df = DataStore(db).get_seismic_events()
    assert len(df) == 3
