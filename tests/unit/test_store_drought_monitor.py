"""Tester for drought_monitor-støtte i DataStore (sub-fase 12.7 D2 A9, session 133)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _row(
    *,
    map_date: str,
    aoi: str = "us",
    none_pct: float | None = 50.0,
    d0_pct: float | None = 50.0,
    d1_pct: float | None = 30.0,
    d2_pct: float | None = 15.0,
    d3_pct: float | None = 5.0,
    d4_pct: float | None = 1.0,
    valid_start: str | None = None,
    valid_end: str | None = None,
) -> dict[str, object]:
    return {
        "map_date": map_date,
        "aoi": aoi,
        "none_pct": none_pct,
        "d0_pct": d0_pct,
        "d1_pct": d1_pct,
        "d2_pct": d2_pct,
        "d3_pct": d3_pct,
        "d4_pct": d4_pct,
        "valid_start": valid_start,
        "valid_end": valid_end,
    }


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_drought_append_and_get(store: DataStore) -> None:
    df = pd.DataFrame(
        [
            _row(map_date="2024-12-31", d2_pct=14.5),
            _row(map_date="2024-12-24", d2_pct=15.31),
        ]
    )
    store.append_drought_monitor(df)

    out = store.get_drought_monitor("us")
    assert len(out) == 2
    assert out["map_date"].iloc[0] == pd.Timestamp("2024-12-24")  # ASC sort
    assert out["d2_pct"].iloc[0] == 15.31


def test_drought_idempotent_replace(store: DataStore) -> None:
    """PK = (map_date, aoi); replay overskriver."""
    store.append_drought_monitor(pd.DataFrame([_row(map_date="2024-12-31", d2_pct=14.5)]))
    store.append_drought_monitor(pd.DataFrame([_row(map_date="2024-12-31", d2_pct=99.9)]))
    out = store.get_drought_monitor("us")
    assert len(out) == 1
    assert out["d2_pct"].iloc[0] == 99.9


def test_drought_aoi_normalized_lowercase(store: DataStore) -> None:
    """AOI normaliseres til lowercase."""
    store.append_drought_monitor(pd.DataFrame([_row(map_date="2024-12-31", aoi="US")]))
    assert store.has_drought_monitor("us") is True
    assert store.has_drought_monitor("US") is True


def test_drought_unknown_aoi_raises(store: DataStore) -> None:
    store.append_drought_monitor(pd.DataFrame([_row(map_date="2024-12-31")]))
    with pytest.raises(KeyError):
        store.get_drought_monitor("ia")


def test_drought_has_helper(store: DataStore) -> None:
    assert store.has_drought_monitor("us") is False
    store.append_drought_monitor(pd.DataFrame([_row(map_date="2024-12-31")]))
    assert store.has_drought_monitor("us") is True


def test_drought_missing_columns_raises(store: DataStore) -> None:
    df = pd.DataFrame({"map_date": ["2024-12-31"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_drought_monitor(df)


def test_drought_nullable_metrics_preserved(store: DataStore) -> None:
    """Optional valid_start/valid_end + alle d-pct nullable."""
    df = pd.DataFrame(
        [
            _row(
                map_date="2024-12-31",
                d2_pct=None,
                d3_pct=None,
                valid_start=None,
                valid_end=None,
            )
        ]
    )
    store.append_drought_monitor(df)
    out = store.get_drought_monitor("us")
    assert pd.isna(out["d2_pct"].iloc[0])
    assert out["valid_start"].iloc[0] is None
