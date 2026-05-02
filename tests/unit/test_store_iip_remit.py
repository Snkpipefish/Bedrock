"""Tester for iip_remit-støtte i DataStore (sub-fase 12.10 follow-up Spor C, session 136)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import IIP_REMIT_COLS, IipRemitRow
from bedrock.data.store import DataStore


def _iip_df(message_ids: list[str] | None = None) -> pd.DataFrame:
    if message_ids is None:
        message_ids = ["MSG-A", "MSG-B", "MSG-C"]
    n = len(message_ids)
    base_pub = pd.Timestamp("2026-05-01 12:00:00")
    return pd.DataFrame(
        {
            "message_id": message_ids,
            "submitted_ts": [
                base_pub - pd.Timedelta(minutes=10) + pd.Timedelta(hours=i) for i in range(n)
            ],
            "published_ts": [base_pub + pd.Timedelta(hours=i) for i in range(n)],
            "event_from_ts": [base_pub + pd.Timedelta(days=1 + i) for i in range(n)],
            "event_to_ts": [base_pub + pd.Timedelta(days=5 + i) for i in range(n)],
            "status": ["Active"] * n,
            "message_type": ["Gas storage facility unavailability"] * n,
            "unavailability_type": ["Planned", "Unplanned", "Planned"][:n],
            "unavailability_reason": ["maintenance"] * n,
            "unavailable_capacity_gwhd": [304.8 + 10 * i for i in range(n)],
            "available_capacity_gwhd": [192.0] * n,
            "technical_capacity_gwhd": [496.8] * n,
            "balancing_zone_code": ["21YNL----TTF---1", "21Y100A1001A0612", "21YNL----TTF---1"][:n],
            "balancing_zone_name": ["NL TTF", "DE THE", "NL TTF"][:n],
            "direction": ["Exit"] * n,
            "asset_code": [f"ASSET-{i}" for i in range(n)],
            "asset_name": [f"Asset {i}" for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_iip_cols_count() -> None:
    assert len(IIP_REMIT_COLS) == 17
    assert IIP_REMIT_COLS[0] == "message_id"


def test_iip_pydantic_minimal() -> None:
    row = IipRemitRow(message_id="ABC")
    assert row.message_id == "ABC"
    assert row.published_ts is None


def test_iip_pydantic_full() -> None:
    row = IipRemitRow(
        message_id="MSG-1",
        published_ts=dt.datetime(2026, 5, 1, 12, 0),
        unavailable_capacity_gwhd=304.8,
        balancing_zone_code="21YNL----TTF---1",
    )
    assert row.unavailable_capacity_gwhd == 304.8
    assert row.balancing_zone_code == "21YNL----TTF---1"


def test_iip_append_and_get(store: DataStore) -> None:
    n = store.append_iip_remit(_iip_df())
    assert n == 3
    df = store.get_iip_remit()
    assert len(df) == 3
    # Sortert ASC på published_ts.
    assert df["message_id"].tolist() == ["MSG-A", "MSG-B", "MSG-C"]
    assert df["unavailable_capacity_gwhd"].iloc[0] == 304.8


def test_iip_idempotent_replace(store: DataStore) -> None:
    """INSERT OR REPLACE på message_id — IIP-meldinger kan revideres."""
    store.append_iip_remit(_iip_df())
    overwrite = _iip_df()
    overwrite.loc[0, "unavailable_capacity_gwhd"] = 999.0
    store.append_iip_remit(overwrite)
    df = store.get_iip_remit()
    assert len(df) == 3
    assert df["unavailable_capacity_gwhd"].iloc[0] == 999.0


def test_iip_balancing_zone_filter(store: DataStore) -> None:
    """Prefix-match på balancing_zone_code — case-insensitive."""
    store.append_iip_remit(_iip_df())
    nl = store.get_iip_remit(balancing_zone_prefix="21YNL")
    assert len(nl) == 2
    assert (nl["balancing_zone_code"] == "21YNL----TTF---1").all()
    de = store.get_iip_remit(balancing_zone_prefix="21Y100")
    assert len(de) == 1


def test_iip_published_ts_filter(store: DataStore) -> None:
    store.append_iip_remit(_iip_df())
    # MSG-A pub 12:00, MSG-B pub 13:00, MSG-C pub 14:00.
    df = store.get_iip_remit(from_published_ts="2026-05-01 13:00:00")
    assert df["message_id"].tolist() == ["MSG-B", "MSG-C"]


def test_iip_last_n(store: DataStore) -> None:
    store.append_iip_remit(_iip_df())
    df = store.get_iip_remit(last_n=2)
    assert df["message_id"].tolist() == ["MSG-B", "MSG-C"]


def test_iip_empty_returns_empty_df(store: DataStore) -> None:
    """IIP er event-basert; tom DB skal returnere tom DataFrame, ikke kaste."""
    df = store.get_iip_remit()
    assert df.empty
    assert not store.has_iip_remit()


def test_iip_has(store: DataStore) -> None:
    assert not store.has_iip_remit()
    store.append_iip_remit(_iip_df())
    assert store.has_iip_remit()


def test_iip_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"message_id": ["X"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_iip_remit(bad)


def test_iip_null_capacities_ok(store: DataStore) -> None:
    df = _iip_df(message_ids=["MSG-X"])
    df.loc[0, "unavailable_capacity_gwhd"] = None
    df.loc[0, "available_capacity_gwhd"] = None
    df.loc[0, "technical_capacity_gwhd"] = None
    store.append_iip_remit(df)
    out = store.get_iip_remit()
    assert len(out) == 1
    assert pd.isna(out["unavailable_capacity_gwhd"].iloc[0])
