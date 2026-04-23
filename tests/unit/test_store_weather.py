"""Tester for weather-støtte (daglige region-observasjoner) i DataStore."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _weather_df(
    region: str = "us_cornbelt",
    dates: list[str] | None = None,
    tmax: list[float | None] | None = None,
    precip: list[float | None] | None = None,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-07-01", "2024-07-02", "2024-07-03"]
    n = len(dates)
    if tmax is None:
        tmax = [28.0 + 0.5 * i for i in range(n)]
    if precip is None:
        precip = [float(i) * 2.5 for i in range(n)]
    return pd.DataFrame(
        {
            "region": [region] * n,
            "date": dates,
            "tmax": tmax,
            "tmin": [16.0] * n,
            "precip": precip,
            "gdd": [14.0 + 0.75 * i for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_weather_append_and_get(store: DataStore) -> None:
    store.append_weather(_weather_df())
    df = store.get_weather("us_cornbelt")
    assert len(df) == 3
    assert list(df.columns) == ["date", "tmax", "tmin", "precip", "gdd"]
    assert df["tmax"].iloc[0] == 28.0
    assert df["date"].iloc[0] == pd.Timestamp("2024-07-01")


def test_weather_last_n(store: DataStore) -> None:
    store.append_weather(_weather_df())
    df = store.get_weather("us_cornbelt", last_n=2)
    assert len(df) == 2
    assert df["date"].iloc[0] == pd.Timestamp("2024-07-02")


def test_weather_dedupe_on_same_date_region(store: DataStore) -> None:
    store.append_weather(_weather_df())
    replay = _weather_df(dates=["2024-07-01"], tmax=[99.0], precip=[0.0])
    store.append_weather(replay)

    df = store.get_weather("us_cornbelt")
    assert len(df) == 3  # fortsatt 3 dager, ikke 4
    first = df[df["date"] == pd.Timestamp("2024-07-01")].iloc[0]
    assert first["tmax"] == 99.0


def test_weather_optional_columns_nullable(store: DataStore) -> None:
    """Minimalt input (kun region + date) skal funke; andre kolonner blir NULL."""
    minimal = pd.DataFrame(
        {"region": ["us_cornbelt"], "date": ["2024-07-01"]}
    )
    store.append_weather(minimal)
    df = store.get_weather("us_cornbelt")
    assert len(df) == 1
    assert pd.isna(df["tmax"].iloc[0])
    assert pd.isna(df["precip"].iloc[0])


def test_weather_missing_region_or_date_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"tmax": [28.0]})
    with pytest.raises(ValueError, match="region.*date"):
        store.append_weather(bad)


def test_weather_unknown_region_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No weather"):
        store.get_weather("mars")


def test_weather_separate_regions(store: DataStore) -> None:
    store.append_weather(_weather_df(region="us_cornbelt", tmax=[28.0, 29.0, 30.0]))
    store.append_weather(
        _weather_df(region="brazil_mato_grosso", tmax=[32.0, 33.0, 34.0])
    )

    us = store.get_weather("us_cornbelt")
    br = store.get_weather("brazil_mato_grosso")
    assert list(us["tmax"]) == [28.0, 29.0, 30.0]
    assert list(br["tmax"]) == [32.0, 33.0, 34.0]


def test_has_weather(store: DataStore) -> None:
    assert not store.has_weather("us_cornbelt")
    store.append_weather(_weather_df())
    assert store.has_weather("us_cornbelt")
    assert not store.has_weather("mars")


def test_weather_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_weather(_weather_df())
    df = DataStore(db).get_weather("us_cornbelt")
    assert len(df) == 3
