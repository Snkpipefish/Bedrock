"""Tester for fas_esr-støtte i DataStore (sub-fase 12.7 D2 A3, session 133)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _row(
    *,
    commodity_code: int,
    country_code: int,
    market_year: int,
    week_ending_date: str,
    weekly_exports: float | None = 1000.0,
    accumulated_exports: float | None = 5000.0,
    outstanding_sales: float | None = 2000.0,
    gross_new_sales: float | None = 1100.0,
    current_my_net_sales: float | None = 800.0,
    current_my_total_commitment: float | None = 7000.0,
    next_my_outstanding_sales: float | None = 100.0,
    next_my_net_sales: float | None = 50.0,
    unit_id: int | None = 1,
) -> dict[str, object]:
    return {
        "commodity_code": commodity_code,
        "country_code": country_code,
        "market_year": market_year,
        "week_ending_date": week_ending_date,
        "weekly_exports": weekly_exports,
        "accumulated_exports": accumulated_exports,
        "outstanding_sales": outstanding_sales,
        "gross_new_sales": gross_new_sales,
        "current_my_net_sales": current_my_net_sales,
        "current_my_total_commitment": current_my_total_commitment,
        "next_my_outstanding_sales": next_my_outstanding_sales,
        "next_my_net_sales": next_my_net_sales,
        "unit_id": unit_id,
    }


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_fas_append_and_get_aggregated(store: DataStore) -> None:
    """get_fas_esr uten country_code aggregerer på tvers av countries."""
    df = pd.DataFrame(
        [
            _row(
                commodity_code=401,
                country_code=2095,
                market_year=2024,
                week_ending_date="2024-09-12",
                weekly_exports=300.0,
            ),
            _row(
                commodity_code=401,
                country_code=1220,
                market_year=2024,
                week_ending_date="2024-09-12",
                weekly_exports=700.0,
            ),
            _row(
                commodity_code=401,
                country_code=2095,
                market_year=2024,
                week_ending_date="2024-09-19",
                weekly_exports=400.0,
            ),
        ]
    )
    store.append_fas_esr(df)

    agg = store.get_fas_esr(401)
    assert len(agg) == 2  # to uker
    first = agg[agg["week_ending_date"] == pd.Timestamp("2024-09-12")].iloc[0]
    assert first["weekly_exports"] == pytest.approx(1000.0)  # 300+700


def test_fas_filter_by_country(store: DataStore) -> None:
    df = pd.DataFrame(
        [
            _row(
                commodity_code=401,
                country_code=2095,
                market_year=2024,
                week_ending_date="2024-09-12",
                weekly_exports=300.0,
            ),
            _row(
                commodity_code=401,
                country_code=1220,
                market_year=2024,
                week_ending_date="2024-09-12",
                weekly_exports=700.0,
            ),
        ]
    )
    store.append_fas_esr(df)

    only_jp = store.get_fas_esr(401, country_code=2095)
    assert len(only_jp) == 1
    assert only_jp["weekly_exports"].iloc[0] == 300.0


def test_fas_idempotent_replace(store: DataStore) -> None:
    """PK = (commodity, country, MY, week) — replay overskriver."""
    store.append_fas_esr(
        pd.DataFrame(
            [
                _row(
                    commodity_code=401,
                    country_code=2095,
                    market_year=2024,
                    week_ending_date="2024-09-12",
                    weekly_exports=300.0,
                )
            ]
        )
    )
    store.append_fas_esr(
        pd.DataFrame(
            [
                _row(
                    commodity_code=401,
                    country_code=2095,
                    market_year=2024,
                    week_ending_date="2024-09-12",
                    weekly_exports=999.0,
                )
            ]
        )
    )
    agg = store.get_fas_esr(401, country_code=2095)
    assert len(agg) == 1
    assert agg["weekly_exports"].iloc[0] == 999.0


def test_fas_date_range_filter(store: DataStore) -> None:
    df = pd.DataFrame(
        [
            _row(
                commodity_code=401,
                country_code=0,
                market_year=2024,
                week_ending_date=d,
                weekly_exports=100.0,
            )
            for d in ["2024-09-05", "2024-09-12", "2024-09-19", "2024-09-26"]
        ]
    )
    store.append_fas_esr(df)

    mid = store.get_fas_esr(401, from_date="2024-09-10", to_date="2024-09-22")
    assert len(mid) == 2


def test_fas_unknown_commodity_raises(store: DataStore) -> None:
    store.append_fas_esr(
        pd.DataFrame(
            [
                _row(
                    commodity_code=401,
                    country_code=0,
                    market_year=2024,
                    week_ending_date="2024-09-12",
                )
            ]
        )
    )
    with pytest.raises(KeyError):
        store.get_fas_esr(999)


def test_fas_has_helper(store: DataStore) -> None:
    assert store.has_fas_esr(401) is False
    store.append_fas_esr(
        pd.DataFrame(
            [
                _row(
                    commodity_code=401,
                    country_code=0,
                    market_year=2024,
                    week_ending_date="2024-09-12",
                )
            ]
        )
    )
    assert store.has_fas_esr(401) is True
    assert store.has_fas_esr(801) is False


def test_fas_missing_columns_raises(store: DataStore) -> None:
    df = pd.DataFrame({"commodity_code": [401], "week_ending_date": ["2024-09-12"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_fas_esr(df)


def test_fas_nullable_metrics_preserved(store: DataStore) -> None:
    """Numeriske felt (untatt PK) er nullable; pd.NaN/None går rundt."""
    df = pd.DataFrame(
        [
            _row(
                commodity_code=801,
                country_code=2095,
                market_year=2024,
                week_ending_date="2024-09-12",
                weekly_exports=None,
                outstanding_sales=None,
                gross_new_sales=None,
                next_my_net_sales=None,
            )
        ]
    )
    store.append_fas_esr(df)
    out = store.get_fas_esr(801, country_code=2095)
    assert pd.isna(out["weekly_exports"].iloc[0])
    assert pd.isna(out["outstanding_sales"].iloc[0])
