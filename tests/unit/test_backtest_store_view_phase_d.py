"""Tester for AsOfDateStore Phase A-C-utvidelser (session 116).

Sub-fase 12.5+ session 116: 9 nye proxy-getters lagt til
(econ_events, cot_ice, eia_inventory, comex_inventory, seismic_events,
cot_euronext, conab_estimates, unica_reports, shipping_indices) som
clipper Phase A-C-tabeller til as_of_date for orchestrator-replay.
"""
# pyright: reportArgumentType=false

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore


@pytest.fixture
def store_with_phase_ac(tmp_path: Path) -> DataStore:
    """DataStore seedet med Phase A-C-data spennende uker frem og tilbake."""
    store = DataStore(tmp_path / "bedrock.db")
    weeks = pd.date_range("2026-01-01", periods=12, freq="7D")

    # Econ events — én per uke
    econ_rows = []
    for i, ts in enumerate(weeks):
        econ_rows.append(
            {
                "event_ts": pd.Timestamp(ts, tz="UTC"),
                "country": "USD",
                "title": f"Event {i}",
                "impact": "High",
                "forecast": None,
                "previous": None,
                "fetched_at": pd.Timestamp(ts, tz="UTC"),
            }
        )
    store.append_econ_events(pd.DataFrame(econ_rows))

    # cot_ice
    store.append_cot_ice(
        pd.DataFrame(
            {
                "report_date": weeks,
                "contract": ["ice brent crude"] * 12,
                "mm_long": [100 + i for i in range(12)],
                "mm_short": [50] * 12,
                "other_long": [10] * 12,
                "other_short": [10] * 12,
                "comm_long": [10] * 12,
                "comm_short": [10] * 12,
                "nonrep_long": [5] * 12,
                "nonrep_short": [5] * 12,
                "open_interest": [200] * 12,
            }
        )
    )

    # cot_euronext
    store.append_cot_euronext(
        pd.DataFrame(
            {
                "report_date": weeks,
                "contract": ["euronext milling wheat"] * 12,
                "mm_long": [100 + i for i in range(12)],
                "mm_short": [50] * 12,
                "open_interest": [200] * 12,
            }
        )
    )

    # eia_inventory
    store.append_eia_inventory(
        pd.DataFrame(
            {
                "series_id": ["WCESTUS1"] * 12,
                "date": weeks,
                "value": [400000.0 + i * 1000 for i in range(12)],
                "units": ["MBBL"] * 12,
            }
        )
    )

    # comex_inventory
    store.append_comex_inventory(
        pd.DataFrame(
            {
                "metal": ["gold"] * 12,
                "date": weeks,
                "registered": [10000000.0 + i * 1000 for i in range(12)],
                "eligible": [15000000.0] * 12,
                "total": [25000000.0 + i * 1000 for i in range(12)],
                "units": ["oz"] * 12,
            }
        )
    )

    # seismic_events
    seismic_rows = []
    for i, ts in enumerate(weeks):
        seismic_rows.append(
            {
                "event_id": f"us100{i}",
                "event_ts": pd.Timestamp(ts, tz="UTC"),
                "magnitude": 5.0 + 0.1 * i,
                "latitude": -33.0,
                "longitude": -71.0,
                "depth_km": 50.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": None,
            }
        )
    store.append_seismic_events(pd.DataFrame(seismic_rows))

    # conab_estimates
    store.append_conab_estimates(
        pd.DataFrame(
            {
                "report_date": weeks,
                "commodity": ["milho"] * 12,
                "production": [100000.0 + i * 100 for i in range(12)],
                "production_units": ["kt"] * 12,
                "area_kha": [None] * 12,
                "yield_value": [None] * 12,
                "yield_units": [None] * 12,
                "levantamento": ["7o"] * 12,
                "safra": ["2025/26"] * 12,
                "yoy_change_pct": [-1.0] * 12,
                "mom_change_pct": [None] * 12,
            }
        )
    )

    # unica_reports — 12 rapporter
    store.append_unica_reports(
        pd.DataFrame(
            {
                "report_date": weeks,
                "position_date": [None] * 12,
                "period": [None] * 12,
                "crop_year": [None] * 12,
                "mix_sugar_pct": [50.0 + 0.1 * i for i in range(12)],
                "mix_sugar_pct_prev": [48.0] * 12,
                "mix_ethanol_pct": [None] * 12,
                "mix_ethanol_pct_prev": [None] * 12,
                "crush_kt": [None] * 12,
                "crush_kt_prev": [None] * 12,
                "crush_yoy_pct": [None] * 12,
                "sugar_production_kt": [None] * 12,
                "sugar_production_kt_prev": [None] * 12,
                "sugar_production_yoy_pct": [None] * 12,
                "ethanol_total_ml": [None] * 12,
                "ethanol_total_ml_prev": [None] * 12,
                "ethanol_total_yoy_pct": [None] * 12,
            }
        )
    )

    # shipping_indices — daglig BDI for 12 uker
    daily_dates = pd.date_range("2026-01-01", "2026-03-31", freq="D")
    store.append_shipping_indices(
        pd.DataFrame(
            {
                "index_code": ["BDI"] * len(daily_dates),
                "date": [d.strftime("%Y-%m-%d") for d in daily_dates],
                "value": [1500.0 + i for i in range(len(daily_dates))],
                "source": ["test"] * len(daily_dates),
            }
        )
    )

    return store


# ---------------------------------------------------------------------
# Econ events — bruker fetched_at for clipping
# ---------------------------------------------------------------------


def test_econ_events_clipped_by_fetched_at(store_with_phase_ac: DataStore) -> None:
    # As_of midt i serien (2026-01-15) skal klippe til 3 uker
    view = AsOfDateStore(store_with_phase_ac, date(2026, 1, 15))
    full = store_with_phase_ac.get_econ_events()
    clipped = view.get_econ_events()
    assert len(full) == 12
    assert len(clipped) == 3  # 2026-01-01, -08, -15
    assert clipped["event_ts"].max() <= pd.Timestamp("2026-01-15", tz="UTC")


def test_econ_events_clipped_to_empty(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    clipped = view.get_econ_events()
    assert clipped.empty


# ---------------------------------------------------------------------
# COT-ICE
# ---------------------------------------------------------------------


def test_cot_ice_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_cot_ice("ice brent crude")
    assert len(clipped) == 5  # uker 1-5 (jan 1, 8, 15, 22, 29)
    assert clipped["report_date"].max() <= pd.Timestamp("2026-02-01")


def test_cot_ice_clipped_to_empty_raises(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    with pytest.raises(KeyError, match="as of"):
        view.get_cot_ice("ice brent crude")


def test_has_cot_ice_returns_false_when_clipped_to_empty(
    store_with_phase_ac: DataStore,
) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    assert view.has_cot_ice("ice brent crude") is False


# ---------------------------------------------------------------------
# COT-Euronext
# ---------------------------------------------------------------------


def test_cot_euronext_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 15))
    clipped = view.get_cot_euronext("euronext milling wheat")
    assert len(clipped) == 7
    assert clipped["report_date"].max() <= pd.Timestamp("2026-02-15")


def test_cot_euronext_last_n_after_clip(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 15))
    clipped = view.get_cot_euronext("euronext milling wheat", last_n=2)
    assert len(clipped) == 2


# ---------------------------------------------------------------------
# Conab
# ---------------------------------------------------------------------


def test_conab_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_conab_estimates("milho")
    assert len(clipped) == 5


def test_conab_unknown_commodity_raises(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    with pytest.raises(KeyError):
        view.get_conab_estimates("unknown")


# ---------------------------------------------------------------------
# UNICA
# ---------------------------------------------------------------------


def test_unica_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_unica_reports()
    assert len(clipped) == 5


def test_unica_clipped_to_empty(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    clipped = view.get_unica_reports()
    assert clipped.empty


# ---------------------------------------------------------------------
# EIA inventory
# ---------------------------------------------------------------------


def test_eia_inventory_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_eia_inventory("WCESTUS1")
    assert len(clipped) == 5


def test_eia_inventory_lookback(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_eia_inventory("WCESTUS1", last_n=3)
    assert len(clipped) == 3


# ---------------------------------------------------------------------
# COMEX inventory
# ---------------------------------------------------------------------


def test_comex_inventory_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_comex_inventory("gold")
    assert len(clipped) == 5


def test_comex_inventory_unknown_metal_raises(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    with pytest.raises(KeyError):
        view.get_comex_inventory("zinc")


# ---------------------------------------------------------------------
# Seismic events
# ---------------------------------------------------------------------


def test_seismic_events_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    clipped = view.get_seismic_events()
    assert len(clipped) == 5
    assert clipped["event_ts"].max() <= pd.Timestamp("2026-02-01", tz="UTC")


def test_seismic_events_with_region_filter(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 3, 1))
    clipped = view.get_seismic_events(region="Chile / Peru")
    assert len(clipped) == 9
    assert all(clipped["region"] == "Chile / Peru")


def test_seismic_events_min_magnitude(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 3, 1))
    # Initial fetch filtrer på underliggende store, så as-of kommer på toppen.
    clipped = view.get_seismic_events(min_magnitude=5.5)
    # Mag 5.5 betyr i+1 ≥ 0.5 * 10 = i ≥ 5. As-of 2026-03-01 = 9 første uker
    # → indekser 5-8 (4 events)
    assert len(clipped) == 4


# ---------------------------------------------------------------------
# Shipping indices
# ---------------------------------------------------------------------


def test_shipping_index_clipped(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 1, 31))
    series = view.get_shipping_index("BDI")
    assert len(series) == 31  # jan 1..31 inkl
    assert series.index[-1] == pd.Timestamp("2026-01-31")


def test_shipping_index_lookback(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2026, 1, 31))
    series = view.get_shipping_index("BDI", last_n=5)
    assert len(series) == 5
    assert series.index[-1] == pd.Timestamp("2026-01-31")


def test_shipping_index_clipped_to_empty_raises(store_with_phase_ac: DataStore) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    with pytest.raises(KeyError):
        view.get_shipping_index("BDI")


def test_has_shipping_index_returns_false_when_clipped_to_empty(
    store_with_phase_ac: DataStore,
) -> None:
    view = AsOfDateStore(store_with_phase_ac, date(2025, 1, 1))
    assert view.has_shipping_index("BDI") is False


# ---------------------------------------------------------------------
# Driver-integrasjon: bekreft at orchestrator-drivere ser clipped data
# ---------------------------------------------------------------------


def test_event_distance_via_as_of_store_uses_clipped_events(
    store_with_phase_ac: DataStore,
) -> None:
    """End-to-end bekreftelse: event_distance-driver via AsOfDateStore.

    Hvis driveren ser events fra fremtiden (>=as_of), ville den scoret
    annerledes. Med clip skal den se kun 5 events innen 2026-02-01.
    """
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    events = view.get_econ_events(countries=["USD"], impact_levels=["High"])
    assert len(events) == 5
    assert all(events["event_ts"] <= pd.Timestamp("2026-02-01", tz="UTC"))


def test_seismic_events_uses_from_ts_filter(store_with_phase_ac: DataStore) -> None:
    """Driver mining_disruption kaller med from_ts (siste 7 dager).

    Bekrefter at as-of-clip kjører ETTER from_ts-filter slik at vi får
    union av begge restriksjoner.
    """
    view = AsOfDateStore(store_with_phase_ac, date(2026, 2, 1))
    from_ts = datetime(2026, 1, 25, tzinfo=timezone.utc)
    clipped = view.get_seismic_events(from_ts=from_ts)
    # Events i [2026-01-25, 2026-02-01]: 2026-01-29 — 1 event
    assert len(clipped) == 1
