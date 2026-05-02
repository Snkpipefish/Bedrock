"""Tester for AsOfDateStore-proxy for ALSI + IIP REMIT (sub-fase 12.10 follow-up Spor C, session 136)."""

# pyright: reportArgumentType=false

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore


@pytest.fixture
def store_with_alsi_iip(tmp_path: Path) -> DataStore:
    store = DataStore(tmp_path / "bedrock.db")
    days = pd.date_range("2026-01-01", periods=30, freq="D")

    # ALSI EU
    store.append_alsi_storage(
        pd.DataFrame(
            {
                "country": ["eu"] * 30,
                "gas_day_start": [d.strftime("%Y-%m-%d") for d in days],
                "inventory_twh": [40.0 - i * 0.2 for i in range(30)],
                "dtmi_twh": [62.0] * 30,
                "full_pct": [(40.0 - i * 0.2) / 62.0 * 100 for i in range(30)],
                "send_out_twh": [4.0 + 0.05 * i for i in range(30)],
                "dtrs_twh": [7.9] * 30,
            }
        )
    )

    # IIP REMIT — 12 events publisert ukentlig
    weeks = pd.date_range("2026-01-01", periods=12, freq="7D")
    store.append_iip_remit(
        pd.DataFrame(
            {
                "message_id": [f"MSG-{i}" for i in range(12)],
                "submitted_ts": [w - pd.Timedelta(minutes=10) for w in weeks],
                "published_ts": list(weeks),
                "event_from_ts": [w + pd.Timedelta(days=1) for w in weeks],
                "event_to_ts": [w + pd.Timedelta(days=10) for w in weeks],
                "status": ["Active"] * 12,
                "message_type": ["Gas storage facility unavailability"] * 12,
                "unavailability_type": ["Planned"] * 12,
                "unavailability_reason": ["maintenance"] * 12,
                "unavailable_capacity_gwhd": [300.0 + i * 10 for i in range(12)],
                "available_capacity_gwhd": [200.0] * 12,
                "technical_capacity_gwhd": [500.0] * 12,
                "balancing_zone_code": (["21YNL----TTF---1"] * 6 + ["21Y100A1001A0612"] * 6),
                "balancing_zone_name": ["NL TTF"] * 6 + ["DE THE"] * 6,
                "direction": ["Exit"] * 12,
                "asset_code": [f"ASSET-{i}" for i in range(12)],
                "asset_name": [f"Asset {i}" for i in range(12)],
            }
        )
    )

    return store


# ALSI clipping ----------------------------------------------------------


def test_alsi_clipped_by_gas_day(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 1, 15))
    df = view.get_alsi_storage("eu")
    assert len(df) == 15
    assert df["gas_day_start"].iloc[-1] == pd.Timestamp("2026-01-15")


def test_alsi_clipped_to_empty_returns_empty_df(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2025, 1, 1))
    df = view.get_alsi_storage("eu")
    assert df.empty


def test_alsi_clipped_last_n(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 1, 20))
    df = view.get_alsi_storage("eu", last_n=5)
    assert len(df) == 5
    assert df["gas_day_start"].iloc[-1] == pd.Timestamp("2026-01-20")


def test_has_alsi_storage_after_clip(store_with_alsi_iip: DataStore) -> None:
    view_before = AsOfDateStore(store_with_alsi_iip, date(2025, 1, 1))
    assert not view_before.has_alsi_storage("eu")
    view_after = AsOfDateStore(store_with_alsi_iip, date(2026, 1, 15))
    assert view_after.has_alsi_storage("eu")


def test_has_alsi_storage_unknown_country(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 2, 1))
    assert not view.has_alsi_storage("xx")


# IIP clipping -----------------------------------------------------------


def test_iip_clipped_by_published_ts(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 2, 1))
    # weeks 0..4 publisert 2026-01-01 .. 2026-01-29
    df = view.get_iip_remit()
    assert len(df) == 5
    assert df["message_id"].iloc[-1] == "MSG-4"


def test_iip_clipped_to_empty(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2025, 1, 1))
    df = view.get_iip_remit()
    assert df.empty


def test_iip_balancing_zone_filter_after_clip(store_with_alsi_iip: DataStore) -> None:
    """Filter + clip skal komponere — først filter på zone, så clip på as_of."""
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 3, 1))
    nl = view.get_iip_remit(balancing_zone_prefix="21YNL")
    assert len(nl) == 6
    de = view.get_iip_remit(balancing_zone_prefix="21Y100")
    # 6 DE-events publisert weeks 6..11 → 6 ukers spenn fra 2026-02-12.
    # As-of 2026-03-01 inkluderer weeks 6..8 (3 events).
    assert len(de) == 3


def test_has_iip_remit_after_clip(store_with_alsi_iip: DataStore) -> None:
    view_before = AsOfDateStore(store_with_alsi_iip, date(2025, 1, 1))
    assert not view_before.has_iip_remit()
    view_after = AsOfDateStore(store_with_alsi_iip, date(2026, 1, 15))
    assert view_after.has_iip_remit()


def test_iip_last_n_after_clip(store_with_alsi_iip: DataStore) -> None:
    view = AsOfDateStore(store_with_alsi_iip, date(2026, 3, 1))
    df = view.get_iip_remit(last_n=2)
    assert len(df) == 2
    # Sortert ASC etter published_ts; siste 2 er weeks 7 og 8.
    assert df["message_id"].tolist() == ["MSG-7", "MSG-8"]
