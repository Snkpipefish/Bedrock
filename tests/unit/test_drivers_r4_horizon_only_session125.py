"""Mini-tester for R4 disiplin B "kun _horizon-lesing"-drivere fra session 125.

Sub-fase 12.7 R4 finish (session 125). Verifiserer at de domene-
spesifikke/event-baserte/K-NN-baserte/kalender-aware driverne fra
session 125 leser ``_horizon``-param uten å endre output.

Drivere dekket:
- disease_pressure (event-basert severity + yield_impact)
- conab_yoy (månedlig CONAB med årlig YoY-metric)
- unica_change (~halv-månedlig multi-metric)
- analog_hit_rate (K-NN hit-rate output)
- analog_avg_return (K-NN avg-return output)
- seasonal_stage (kalender-aware måneds-mapping)

igc_stocks_change ble fjernet i sub-fase 12.6 session 138 som dead
driver (var ikke wired i noen YAML).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers.agronomy import (
    conab_yoy,
    disease_pressure,
    unica_change,
)
from bedrock.engine.drivers.analog import analog_avg_return, analog_hit_rate
from bedrock.engine.drivers.seasonal import seasonal_stage

# ---------------------------------------------------------------------------
# Mock-stores
# ---------------------------------------------------------------------------


class _MockDiseaseStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_disease_alerts(self, commodity: str, from_date: str):
        return self._df


class _MockConabStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_conab_estimates(self, commodity: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


class _MockUnicaStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_unica_reports(self, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


class _MockEmptyStore:
    """For analog-drivere som har egen K-NN-pipeline med extractors."""

    pass


# ---------------------------------------------------------------------------
# disease_pressure
# ---------------------------------------------------------------------------


def test_disease_pressure_horizon_noop():
    df = pd.DataFrame(
        [
            {
                "alert_date": (date.today() - timedelta(days=20)).isoformat(),
                "commodity": "CORN",
                "severity": 4,
                "yield_impact_pct": 8.0,
                "description": "Test disease",
            }
        ]
    )
    store = _MockDiseaseStore(df)
    no_horizon = disease_pressure(store, "Corn", {})
    with_swing = disease_pressure(store, "Corn", {"_horizon": "SWING"})
    with_makro = disease_pressure(store, "Corn", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# conab_yoy
# ---------------------------------------------------------------------------


def test_conab_yoy_horizon_noop():
    df = pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "commodity": "soja",
                "yoy_change_pct": -3.5,
                "production": 150_000.0,
                "production_units": "kt",
                "area_kha": 45_000.0,
                "yield_value": 3.3,
                "yield_units": "kg/ha",
                "levantamento": "7o",
                "safra": "2025/26",
                "mom_change_pct": 0.5,
            }
        ]
    )
    store = _MockConabStore(df)
    params = {"commodity": "soja"}
    no_horizon = conab_yoy(store, "Soybean", params)
    with_swing = conab_yoy(store, "Soybean", {**params, "_horizon": "SWING"})
    with_makro = conab_yoy(store, "Soybean", {**params, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# unica_change
# ---------------------------------------------------------------------------


def test_unica_change_horizon_noop():
    df = pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "sugar_production_yoy_pct": -4.5,
                "crush_yoy_pct": -2.0,
                "mix_sugar_pct": 47.0,
                "mix_sugar_pct_prev": 49.0,
            }
        ]
    )
    store = _MockUnicaStore(df)
    no_horizon = unica_change(store, "Sugar", {})
    with_swing = unica_change(store, "Sugar", {"_horizon": "SWING"})
    with_makro = unica_change(store, "Sugar", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# analog_hit_rate / analog_avg_return
# Disse delegerer til _knn() som krever asset_class og config-lookup.
# Med ukjent asset_class returnerer de 0.0 for alle horisonter — det er
# tilstrekkelig for å verifisere at _horizon ikke endrer output.
# ---------------------------------------------------------------------------


def test_analog_hit_rate_horizon_noop():
    """Ved manglende/ukjent asset_class returnerer alle horisonter 0.0."""
    store = _MockEmptyStore()
    no_horizon = analog_hit_rate(store, "Test", {})
    with_swing = analog_hit_rate(store, "Test", {"_horizon": "SWING"})
    with_makro = analog_hit_rate(store, "Test", {"_horizon": "MAKRO"})
    # Alle = 0.0 (defensive ved manglende asset_class)
    assert no_horizon == with_swing == with_makro


def test_analog_avg_return_horizon_noop():
    store = _MockEmptyStore()
    no_horizon = analog_avg_return(store, "Test", {})
    with_swing = analog_avg_return(store, "Test", {"_horizon": "SWING"})
    with_makro = analog_avg_return(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# seasonal_stage
# ---------------------------------------------------------------------------


def test_seasonal_stage_horizon_noop():
    """seasonal_stage: _horizon LESES uten å endre output."""
    store = _MockEmptyStore()
    params = {"as_of": "2026-06-15"}  # juni → 1.0 i default-kalender
    no_horizon = seasonal_stage(store, "Corn", params)
    with_swing = seasonal_stage(store, "Corn", {**params, "_horizon": "SWING"})
    with_makro = seasonal_stage(store, "Corn", {**params, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro
