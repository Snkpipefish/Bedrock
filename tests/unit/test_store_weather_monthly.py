"""Tester for weather_monthly-støtte i DataStore (Fase 10 ADR-005).

Dekker:
- Pydantic-skjema-validering (`WeatherMonthlyRow.month`-format)
- append_weather_monthly + get_weather_monthly (round-trip)
- Idempotens via PRIMARY KEY (region, month)
- has_weather_monthly + last_n + KeyError ved manglende region
- DDL-init (tabell finnes i fersk DB, kobles inn av _init_schema)
- NULL-håndtering for valgfrie kolonner
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from bedrock.data.schemas import (
    DDL_WEATHER_MONTHLY,
    TABLE_WEATHER_MONTHLY,
    WEATHER_MONTHLY_COLS,
    WeatherMonthlyRow,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------
# Pydantic-schema
# ---------------------------------------------------------------------


def test_weather_monthly_row_minimal() -> None:
    row = WeatherMonthlyRow(region="us_cornbelt", month="2024-07")
    assert row.temp_mean is None
    assert row.hot_days is None
    assert row.water_bal is None


def test_weather_monthly_row_full() -> None:
    row = WeatherMonthlyRow(
        region="brazil_mato_grosso",
        month="2024-12",
        temp_mean=27.5,
        temp_max=34.1,
        precip_mm=180.4,
        et0_mm=120.0,
        hot_days=5,
        dry_days=2,
        wet_days=15,
        water_bal=60.4,
    )
    assert row.water_bal == pytest.approx(60.4)


def test_weather_monthly_row_rejects_bad_month() -> None:
    with pytest.raises(ValidationError):
        WeatherMonthlyRow(region="us_cornbelt", month="2024-13")
    with pytest.raises(ValidationError):
        WeatherMonthlyRow(region="us_cornbelt", month="2024-7")  # ikke 0-padded
    with pytest.raises(ValidationError):
        WeatherMonthlyRow(region="us_cornbelt", month="2024/07")


def test_weather_monthly_row_rejects_negative_precip() -> None:
    with pytest.raises(ValidationError):
        WeatherMonthlyRow(region="us_cornbelt", month="2024-07", precip_mm=-1.0)


def test_weather_monthly_row_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        WeatherMonthlyRow(region="us_cornbelt", month="2024-07", surprise=1)


# ---------------------------------------------------------------------
# DataStore round-trip
# ---------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def _df(region: str = "us_cornbelt", months: list[str] | None = None) -> pd.DataFrame:
    if months is None:
        months = ["2024-05", "2024-06", "2024-07"]
    n = len(months)
    return pd.DataFrame(
        {
            "region": [region] * n,
            "month": months,
            "temp_mean": [20.0 + i for i in range(n)],
            "temp_max": [28.0 + i for i in range(n)],
            "precip_mm": [50.0 + 5 * i for i in range(n)],
            "et0_mm": [40.0 + 2 * i for i in range(n)],
            "hot_days": list(range(n)),
            "dry_days": [10 - i for i in range(n)],
            "wet_days": [5 + i for i in range(n)],
            "water_bal": [10.0 + i for i in range(n)],
        }
    )


def test_init_creates_weather_monthly_table(store: DataStore, tmp_path: Path) -> None:
    # Sjekker at _init_schema oppretter tabellen
    import sqlite3

    conn = sqlite3.connect(store._db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_WEATHER_MONTHLY,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "weather_monthly" in DDL_WEATHER_MONTHLY  # sanity


def test_append_and_get(store: DataStore) -> None:
    n = store.append_weather_monthly(_df())
    assert n == 3

    df = store.get_weather_monthly("us_cornbelt")
    assert len(df) == 3
    assert list(df.columns) == list(WEATHER_MONTHLY_COLS)
    assert df["month"].iloc[0] == "2024-05"
    assert df["temp_mean"].iloc[1] == pytest.approx(21.0)
    assert df["hot_days"].iloc[2] == 2


def test_append_idempotent(store: DataStore) -> None:
    store.append_weather_monthly(_df())
    # Re-append samme datoer med justerte verdier — skal overskrive
    df2 = _df()
    df2["temp_mean"] = [99.0, 99.0, 99.0]
    store.append_weather_monthly(df2)

    df = store.get_weather_monthly("us_cornbelt")
    assert len(df) == 3  # ikke 6 — INSERT OR REPLACE
    assert df["temp_mean"].tolist() == [99.0, 99.0, 99.0]


def test_get_missing_region_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="brazil_mato_grosso"):
        store.get_weather_monthly("brazil_mato_grosso")


def test_get_last_n(store: DataStore) -> None:
    store.append_weather_monthly(
        _df(months=["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"])
    )
    df = store.get_weather_monthly("us_cornbelt", last_n=2)
    assert len(df) == 2
    assert df["month"].tolist() == ["2024-04", "2024-05"]


def test_has_weather_monthly(store: DataStore) -> None:
    assert store.has_weather_monthly("us_cornbelt") is False
    store.append_weather_monthly(_df())
    assert store.has_weather_monthly("us_cornbelt") is True
    assert store.has_weather_monthly("nonexistent") is False


def test_null_columns_roundtrip(store: DataStore) -> None:
    df = pd.DataFrame(
        {
            "region": ["sea_palm"],
            "month": ["2023-08"],
            "temp_mean": [None],
            "temp_max": [27.0],
            "precip_mm": [None],
            "et0_mm": [None],
            "hot_days": [None],
            "dry_days": [None],
            "wet_days": [None],
            "water_bal": [None],
        }
    )
    store.append_weather_monthly(df)
    out = store.get_weather_monthly("sea_palm")
    assert pd.isna(out["temp_mean"].iloc[0])
    assert out["temp_max"].iloc[0] == 27.0
    assert pd.isna(out["water_bal"].iloc[0])


def test_append_missing_required_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"region": ["x"], "temp_mean": [10.0]})
    with pytest.raises(ValueError, match="region.*month"):
        store.append_weather_monthly(bad)


def test_multiple_regions_isolated(store: DataStore) -> None:
    store.append_weather_monthly(_df(region="us_cornbelt"))
    store.append_weather_monthly(_df(region="brazil_coffee"))
    a = store.get_weather_monthly("us_cornbelt")
    b = store.get_weather_monthly("brazil_coffee")
    assert (a["region"] == "us_cornbelt").all()
    assert (b["region"] == "brazil_coffee").all()
    assert len(a) == 3
    assert len(b) == 3
