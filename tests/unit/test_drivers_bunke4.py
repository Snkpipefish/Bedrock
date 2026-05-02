"""Sub-fase 12.10 Bunke 4 driver-tester.

Compact registry + smoke-test for de 8 nye Yahoo/CBOE/NOAA-driverne.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered


@pytest.mark.parametrize(
    "driver_name",
    [
        "move_index_z",
        "vvix_z",
        "gvz_z",
        "ovx_z",
        "cboe_skew_z",
        "noaa_oni_index",
        "noaa_enso_forecast_3mo",
        "noaa_pdo_index",
        "intraday_atr_h1",
    ],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name), f"{driver_name} not registered"
    fn = get(driver_name)
    assert callable(fn)


# ---------------------------------------------------------------------------
# Mock store for fundamentals
# ---------------------------------------------------------------------------


class _MockStore:
    def __init__(
        self,
        series: dict[str, pd.Series] | None = None,
        ohlc: dict[tuple[str, str], pd.DataFrame] | None = None,
    ) -> None:
        self._series = series or {}
        self._ohlc = ohlc or {}

    def get_fundamentals(self, series_id: str, last_n: int | None = None) -> pd.Series:
        if series_id not in self._series:
            raise KeyError(f"unknown series: {series_id}")
        s = self._series[series_id]
        return s.tail(last_n) if last_n else s

    def get_prices_ohlc(
        self, instrument: str, tf: str = "D1", lookback: int | None = None
    ) -> pd.DataFrame:
        key = (instrument, tf)
        if key not in self._ohlc:
            raise KeyError(f"no OHLC for {key}")
        df = self._ohlc[key]
        return df.tail(lookback) if lookback else df


def _daily(values: list[float], end: str = "2026-05-01") -> pd.Series:
    end_ts = pd.Timestamp(end)
    return pd.Series(values, index=pd.date_range(end=end_ts, periods=len(values), freq="D"))


def _monthly(values: list[float], end: str = "2026-04-01") -> pd.Series:
    end_ts = pd.Timestamp(end)
    return pd.Series(values, index=pd.date_range(end=end_ts, periods=len(values), freq="MS"))


# ---------------------------------------------------------------------------
# #15 vol-indekser
# ---------------------------------------------------------------------------


def test_move_index_z_low_vol_bull() -> None:
    fn = get("move_index_z")
    vals = [120.0 + (i % 3) for i in range(100)] + [80.0]
    store = _MockStore({"MOVE": _daily(vals)})
    assert fn(store, "SP500", {}) == 1.0


def test_vvix_z_high_vol_bear() -> None:
    fn = get("vvix_z")
    vals = [85.0 + (i % 3) for i in range(100)] + [130.0]
    store = _MockStore({"VVIX": _daily(vals)})
    assert fn(store, "SP500", {}) == 0.0


def test_gvz_z_returns_neutral_when_sparse() -> None:
    fn = get("gvz_z")
    store = _MockStore({"GVZ": _daily([15.0] * 30)})
    assert fn(store, "Gold", {}) == 0.5


def test_ovx_z_score_in_unit_interval() -> None:
    fn = get("ovx_z")
    vals = [35.0 + (i % 3) for i in range(100)] + [45.0]
    store = _MockStore({"OVX": _daily(vals)})
    score = fn(store, "CrudeOil", {})
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# #16 CBOE
# ---------------------------------------------------------------------------


def test_cboe_skew_z_low_skew_bull() -> None:
    fn = get("cboe_skew_z")
    vals = [140.0 + (i % 3) for i in range(100)] + [110.0]
    store = _MockStore({"SKEW": _daily(vals)})
    assert fn(store, "SP500", {}) == 1.0


# ---------------------------------------------------------------------------
# #17 NOAA
# ---------------------------------------------------------------------------


def test_noaa_oni_strong_la_nina_bull() -> None:
    fn = get("noaa_oni_index")
    vals = [-1.8] * 24
    store = _MockStore({"ONI": _monthly(vals)})
    assert fn(store, "Corn", {}) == 1.0


def test_noaa_oni_strong_el_nino_bear() -> None:
    fn = get("noaa_oni_index")
    vals = [2.0] * 24
    store = _MockStore({"ONI": _monthly(vals)})
    assert fn(store, "Corn", {}) == 0.0


def test_noaa_enso_forecast_3mo_strong_la_nina_bull() -> None:
    fn = get("noaa_enso_forecast_3mo")
    vals = [-1.8] * 6
    store = _MockStore({"IRI_ENSO_FCST_3MO": _monthly(vals)})
    assert fn(store, "Sugar", {}) == 1.0


def test_noaa_enso_forecast_3mo_strong_el_nino_bear() -> None:
    fn = get("noaa_enso_forecast_3mo")
    vals = [1.6] * 6
    store = _MockStore({"IRI_ENSO_FCST_3MO": _monthly(vals)})
    assert fn(store, "Sugar", {}) == 0.0


def test_noaa_enso_forecast_3mo_neutral_returns_mid() -> None:
    fn = get("noaa_enso_forecast_3mo")
    vals = [0.1] * 6
    store = _MockStore({"IRI_ENSO_FCST_3MO": _monthly(vals)})
    assert fn(store, "Coffee", {}) == 0.5


def test_noaa_enso_forecast_3mo_returns_neutral_when_sparse() -> None:
    fn = get("noaa_enso_forecast_3mo")
    vals = [0.5, 0.6]  # under min_samples=3
    store = _MockStore({"IRI_ENSO_FCST_3MO": _monthly(vals)})
    assert fn(store, "Cocoa", {}) == 0.5


def test_noaa_enso_forecast_3mo_missing_series_returns_zero() -> None:
    fn = get("noaa_enso_forecast_3mo")
    store = _MockStore()
    assert fn(store, "Cocoa", {}) == 0.0


def test_noaa_pdo_neutral_phase() -> None:
    fn = get("noaa_pdo_index")
    vals = [0.1] * 24
    store = _MockStore({"PDO": _monthly(vals)})
    assert fn(store, "Wheat", {}) == 0.5


# ---------------------------------------------------------------------------
# #18 intraday_atr_h1
# ---------------------------------------------------------------------------


def test_intraday_atr_h1_returns_neutral_when_no_h1_data() -> None:
    fn = get("intraday_atr_h1")
    store = _MockStore()
    assert fn(store, "SP500", {}) == 0.5


def test_intraday_atr_h1_high_vol_high_score() -> None:
    fn = get("intraday_atr_h1")
    # Bygg H1-DataFrame med variabel volatilitet, siste bar høyest
    n = 200
    rows = []
    for i in range(n - 1):
        rows.append({"high": 100.0 + (i % 5), "low": 99.0 - (i % 5), "close": 100.0})
    rows.append({"high": 120.0, "low": 80.0, "close": 100.0})  # ekstrem siste bar
    df = pd.DataFrame(rows, index=pd.date_range(end="2026-05-01", periods=n, freq="h"))
    store = _MockStore(ohlc={("SP500", "H1"): df})
    score = fn(store, "SP500", {})
    # Høy ATR-percentil → 1.0 ved bull_when='high' default
    assert score >= 0.9
