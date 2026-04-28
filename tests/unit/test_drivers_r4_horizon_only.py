"""Mini-tester for R4 disiplin B "kun _horizon-lesing"-drivere.

Sub-fase 12.7 R4 batch 5 finish + batch 6 start (session 124).

Verifiserer at de 6 domene-spesifikke/event-baserte driverne fra
session 124 leser ``_horizon``-param uten å endre output. Dette er
minimum-mandatet for rank-baserte/event-baserte drivere per audit-
mandat: 2 tester per driver — Type A (snapshot kontraktuell, dekket
av tests/snapshot/) + horizon-noop-mini-test (denne fila).

Drivere dekket:
- comex_stress (domene-spesifikk warehouse-coverage)
- mining_disruption (event-basert seismic + region-vekter)
- weather_stress (domene-spesifikk vær-formel)
- enso_regime (domene-spesifikk månedlig ONI regime-mapper)
- wasde_s2u_change (rapport-til-rapport pct-change)
- export_event_active (event-basert severity)
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers.agri import enso_regime, weather_stress
from bedrock.engine.drivers.agronomy import export_event_active, wasde_s2u_change
from bedrock.engine.drivers.macro import comex_stress, mining_disruption

# ---------------------------------------------------------------------------
# Mock-stores for hvert datakilde-domene
# ---------------------------------------------------------------------------


class _MockComexStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_comex_inventory(self, metal: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


class _MockSeismicStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_seismic_events(self, **kwargs):
        return self._df


class _MockWeatherStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_weather_monthly(self, region: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


class _MockFundamentalsStore:
    def __init__(self, series: pd.Series):
        self._series = series

    def get_fundamentals(self, series_id: str) -> pd.Series:
        return self._series


class _MockWasdeStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_wasde(self, commodity: str, metric: str, region: str = "US"):
        return self._df


class _MockExportStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_export_events(self, commodity: str, from_date: str):
        return self._df


# ---------------------------------------------------------------------------
# comex_stress
# ---------------------------------------------------------------------------


def test_comex_stress_horizon_noop():
    """comex_stress: _horizon LESES uten å endre output."""
    df = pd.DataFrame(
        [
            {"date": "2026-04-25", "registered": 1_500_000, "total": 2_500_000, "units": "oz"},
            {"date": "2026-04-26", "registered": 1_550_000, "total": 2_550_000, "units": "oz"},
            {"date": "2026-04-27", "registered": 1_600_000, "total": 2_600_000, "units": "oz"},
            {"date": "2026-04-28", "registered": 1_650_000, "total": 2_650_000, "units": "oz"},
            {"date": "2026-04-29", "registered": 1_700_000, "total": 2_700_000, "units": "oz"},
            {"date": "2026-04-30", "registered": 1_400_000, "total": 2_700_000, "units": "oz"},
        ]
    )
    store = _MockComexStore(df)
    params = {"metal": "gold"}
    no_horizon = comex_stress(store, "Gold", params)
    with_swing = comex_stress(store, "Gold", {**params, "_horizon": "SWING"})
    with_makro = comex_stress(store, "Gold", {**params, "_horizon": "MAKRO"})
    with_scalp = comex_stress(store, "Gold", {**params, "_horizon": "SCALP"})
    assert no_horizon == with_swing == with_makro == with_scalp


# ---------------------------------------------------------------------------
# mining_disruption
# ---------------------------------------------------------------------------


def test_mining_disruption_horizon_noop():
    """mining_disruption: _horizon LESES uten å endre output."""
    df = pd.DataFrame(
        [
            {
                "event_id": "us7000abcd",
                "event_ts": pd.Timestamp("2026-04-25T10:30:00Z"),
                "magnitude": 6.0,
                "lat": -23.5,
                "lon": -69.0,
                "depth_km": 50.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": "https://example.com",
            }
        ]
    )
    store = _MockSeismicStore(df)
    params = {"metal": "copper"}
    no_horizon = mining_disruption(store, "Copper", params)
    with_swing = mining_disruption(store, "Copper", {**params, "_horizon": "SWING"})
    with_makro = mining_disruption(store, "Copper", {**params, "_horizon": "MAKRO"})
    with_scalp = mining_disruption(store, "Copper", {**params, "_horizon": "SCALP"})
    assert no_horizon == with_swing == with_makro == with_scalp


# ---------------------------------------------------------------------------
# weather_stress (krever weather_region; mock instrument-lookup)
# ---------------------------------------------------------------------------


def test_weather_stress_horizon_noop(monkeypatch):
    """weather_stress: _horizon LESES uten å endre output."""

    class _Meta:
        weather_region = "US_MIDWEST"

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )

    df = pd.DataFrame(
        [
            {
                "month": "2026-04",
                "hot_days": 10,
                "dry_days": 12,
                "water_bal": -50.0,
            }
        ]
    )
    store = _MockWeatherStore(df)
    no_horizon = weather_stress(store, "Corn", {})
    with_swing = weather_stress(store, "Corn", {"_horizon": "SWING"})
    with_makro = weather_stress(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# enso_regime
# ---------------------------------------------------------------------------


def test_enso_regime_horizon_noop():
    """enso_regime: _horizon LESES uten å endre output."""
    series = pd.Series([0.3, 0.5, 0.7, 0.8])
    store = _MockFundamentalsStore(series)
    no_horizon = enso_regime(store, "Corn", {})
    with_swing = enso_regime(store, "Corn", {"_horizon": "SWING"})
    with_makro = enso_regime(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# wasde_s2u_change
# ---------------------------------------------------------------------------


def test_wasde_s2u_change_horizon_noop():
    """wasde_s2u_change: _horizon LESES uten å endre output."""
    df = pd.DataFrame(
        [
            {
                "report_date": "2026-03-10",
                "marketing_year": "2025/26",
                "value": 12.0,
            },
            {
                "report_date": "2026-04-10",
                "marketing_year": "2025/26",
                "value": 11.0,
            },
        ]
    )
    store = _MockWasdeStore(df)
    no_horizon = wasde_s2u_change(store, "Corn", {})
    with_swing = wasde_s2u_change(store, "Corn", {"_horizon": "SWING"})
    with_makro = wasde_s2u_change(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# export_event_active
# ---------------------------------------------------------------------------


def test_export_event_active_horizon_noop():
    """export_event_active: _horizon LESES uten å endre output."""
    df = pd.DataFrame(
        [
            {
                "event_date": (date.today() - timedelta(days=10)).isoformat(),
                "commodity": "CORN",
                "bull_bear": "BULL",
                "severity": 4,
                "description": "Test export ban",
            }
        ]
    )
    store = _MockExportStore(df)
    no_horizon = export_event_active(store, "Corn", {})
    with_swing = export_event_active(store, "Corn", {"_horizon": "SWING"})
    with_makro = export_event_active(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro
