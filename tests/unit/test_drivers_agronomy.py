"""Tester for agronomy-drivere (PLAN § 7.3, session 83)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from bedrock.engine.drivers import get


class _DummyStore:
    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs

    def get_crop_progress(
        self, commodity: str, state: str = "US TOTAL", metric: str | None = None
    ) -> pd.DataFrame:
        return self._data.get("crop_progress", pd.DataFrame())

    def get_wasde(self, commodity: str, metric: str, region: str = "US") -> pd.DataFrame:
        return self._data.get("wasde", pd.DataFrame())

    def get_export_events(
        self,
        commodity: str | None = None,
        country: str | None = None,
        from_date: str | None = None,
    ) -> pd.DataFrame:
        df = self._data.get("export_events", pd.DataFrame())
        if df.empty:
            return df
        if commodity:
            df = df[df["commodity"] == commodity]
        return df

    def get_disease_alerts(
        self, commodity: str | None = None, from_date: str | None = None
    ) -> pd.DataFrame:
        df = self._data.get("disease_alerts", pd.DataFrame())
        if df.empty:
            return df
        if commodity:
            df = df[df["commodity"] == commodity]
        return df

    def get_bdi(self, last_n: int | None = None) -> pd.Series:
        s = self._data.get("bdi")
        if s is None or len(s) == 0:
            raise KeyError("no BDI")
        return s.tail(last_n) if last_n else s

    def get_shipping_index(self, index_code: str, last_n: int | None = None) -> pd.Series:
        # Lookup either by explicit code (e.g. shipping_BPI) eller default 'bdi'-key
        # for å bevare bakoverkompatibilitet med eksisterende tester.
        code = index_code.upper()
        s = self._data.get(f"shipping_{code}")
        if s is None and code == "BDI":
            s = self._data.get("bdi")  # legacy-key
        if s is None or len(s) == 0:
            raise KeyError(f"no shipping_indices data for {code}")
        return s.tail(last_n) if last_n else s

    def get_igc(self, grain: str, metric: str) -> pd.DataFrame:
        return self._data.get("igc", pd.DataFrame())


# ---------------------------------------------------------------------------
# crop_progress_stage
# ---------------------------------------------------------------------------


def test_crop_progress_no_usda_mapping_returns_neutral() -> None:
    fn = get("crop_progress_stage")
    score = fn(_DummyStore(), "Coffee", {})
    assert score == 0.5


def test_crop_progress_empty_returns_neutral() -> None:
    fn = get("crop_progress_stage")
    score = fn(_DummyStore(crop_progress=pd.DataFrame()), "Corn", {})
    assert score == 0.5


def test_crop_progress_low_is_bull_default() -> None:
    """Low good/excellent percentile = bull (yield-risk)."""
    fn = get("crop_progress_stage")
    df = pd.DataFrame({"value_pct": [80.0] * 9 + [50.0]})
    score = fn(_DummyStore(crop_progress=df), "Corn", {})
    # Latest=50 er lowest → percentil ~0 → low_is_bull → ~1.0
    assert score >= 0.85


def test_crop_progress_high_is_bull_inverts() -> None:
    fn = get("crop_progress_stage")
    df = pd.DataFrame({"value_pct": [50.0] * 9 + [85.0]})
    score = fn(_DummyStore(crop_progress=df), "Corn", {"mode": "high_is_bull"})
    assert score >= 0.85


# ---------------------------------------------------------------------------
# wasde_s2u_change
# ---------------------------------------------------------------------------


def _wasde_df(values: list[float], marketing_year: str = "2025/26") -> pd.DataFrame:
    """Bygg dummy WASDE-DataFrame med same MY på tvers av rapporter."""
    n = len(values)
    return pd.DataFrame(
        {
            "value": values,
            "report_date": pd.to_datetime([f"2025-{i + 1:02d}-10" for i in range(n)]),
            "marketing_year": [marketing_year] * n,
        }
    )


def test_wasde_s2u_dropping_is_bull() -> None:
    fn = get("wasde_s2u_change")
    df = _wasde_df([15.0, 13.5])  # -10%
    score = fn(_DummyStore(wasde=df), "Corn", {})
    assert score == 1.0


def test_wasde_s2u_rising_is_bear() -> None:
    fn = get("wasde_s2u_change")
    df = _wasde_df([10.0, 11.5])  # +15%
    score = fn(_DummyStore(wasde=df), "Corn", {})
    assert score == 0.0


def test_wasde_s2u_neutral() -> None:
    fn = get("wasde_s2u_change")
    df = _wasde_df([10.0, 10.05])  # +0.5%
    score = fn(_DummyStore(wasde=df), "Corn", {})
    assert score == 0.5


def test_wasde_s2u_short_history_returns_neutral() -> None:
    fn = get("wasde_s2u_change")
    df = _wasde_df([10.0])
    score = fn(_DummyStore(wasde=df), "Corn", {})
    assert score == 0.5


# ---------------------------------------------------------------------------
# export_event_active
# ---------------------------------------------------------------------------


def test_export_event_severity_5_bull() -> None:
    fn = get("export_event_active")
    df = pd.DataFrame(
        [
            {
                "commodity": "RICE",
                "event_date": date.today() - timedelta(days=10),
                "country": "INDIA",
                "event_type": "EXPORT_BAN",
                "severity": 5,
                "bull_bear": "BULL",
            }
        ]
    )
    # Note: instrument map har ikke "Rice" — bruk Wheat istedenfor for test.
    df["commodity"] = "WHEAT"
    score = fn(_DummyStore(export_events=df), "Wheat", {"lookback_days": 60})
    assert score == 1.0


def test_export_event_no_events_returns_neutral() -> None:
    fn = get("export_event_active")
    score = fn(_DummyStore(export_events=pd.DataFrame()), "Wheat", {})
    assert score == 0.5


def test_export_event_unknown_instrument_returns_neutral() -> None:
    fn = get("export_event_active")
    score = fn(_DummyStore(), "BTC", {})
    assert score == 0.5


# ---------------------------------------------------------------------------
# disease_pressure
# ---------------------------------------------------------------------------


def test_disease_pressure_severe_returns_high() -> None:
    fn = get("disease_pressure")
    df = pd.DataFrame(
        [
            {
                "commodity": "WHEAT",
                "alert_date": date.today() - timedelta(days=10),
                "severity": 4,
                "yield_impact_pct": 8.0,
            }
        ]
    )
    score = fn(_DummyStore(disease_alerts=df), "Wheat", {})
    assert score >= 0.85


def test_disease_pressure_no_alerts_returns_neutral() -> None:
    fn = get("disease_pressure")
    score = fn(_DummyStore(disease_alerts=pd.DataFrame()), "Wheat", {})
    assert score == 0.5


def test_disease_pressure_high_yield_impact_bonus() -> None:
    """Yield-impact >= 10% gir +0.05 bonus over base-severity-score."""
    fn = get("disease_pressure")
    df = pd.DataFrame(
        [
            {
                "commodity": "WHEAT",
                "alert_date": date.today() - timedelta(days=10),
                "severity": 5,
                "yield_impact_pct": 15.0,
            }
        ]
    )
    score = fn(_DummyStore(disease_alerts=df), "Wheat", {})
    assert score == 1.0  # 0.95 + 0.05


# ---------------------------------------------------------------------------
# shipping_pressure (sub-fase 12.5+ session 113 — rebrand av bdi_chg30d)
# ---------------------------------------------------------------------------


def test_shipping_pressure_no_data_returns_neutral() -> None:
    fn = get("shipping_pressure")
    score = fn(_DummyStore(), "Wheat", {})
    assert score == 0.5


def test_shipping_pressure_default_index_is_bdi() -> None:
    """Uten index-param brukes BDI for bakoverkompatibilitet."""
    fn = get("shipping_pressure")
    values = [1000.0] * 32 + [900.0, 850.0, 800.0]  # -20%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(_DummyStore(bdi=series), "Wheat", {"window_days": 30})
    assert score == 1.0


def test_shipping_pressure_falling_is_bull() -> None:
    fn = get("shipping_pressure")
    values = [1000.0] * 32 + [900.0, 850.0, 800.0]  # -20%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(
        _DummyStore(shipping_BDI=series),
        "Wheat",
        {"index": "BDI", "window_days": 30},
    )
    assert score == 1.0


def test_shipping_pressure_rising_is_bear() -> None:
    fn = get("shipping_pressure")
    values = [1000.0] * 32 + [1100.0, 1180.0, 1250.0]  # +25%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(
        _DummyStore(shipping_BDI=series),
        "Wheat",
        {"index": "BDI", "window_days": 30},
    )
    assert score == 0.0


def test_shipping_pressure_bpi_index() -> None:
    """BPI er Panamax — primær for grain-eksport."""
    fn = get("shipping_pressure")
    values = [1500.0] * 32 + [1300.0, 1250.0, 1200.0]  # -20%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(
        _DummyStore(shipping_BPI=series),
        "Wheat",
        {"index": "BPI", "window_days": 30},
    )
    assert score == 1.0


def test_shipping_pressure_unknown_index_returns_neutral() -> None:
    fn = get("shipping_pressure")
    score = fn(_DummyStore(), "Wheat", {"index": "BSI"})
    assert score == 0.5


def test_shipping_pressure_short_history_returns_neutral() -> None:
    fn = get("shipping_pressure")
    series = pd.Series(
        [1000.0, 1100.0, 1200.0],
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    score = fn(_DummyStore(bdi=series), "Wheat", {"window_days": 30})
    assert score == 0.5


def test_shipping_pressure_index_param_lowercase_uppercases() -> None:
    """index-param er case-insensitive."""
    fn = get("shipping_pressure")
    values = [1000.0] * 32 + [900.0, 850.0, 800.0]  # -20%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(
        _DummyStore(shipping_BDI=series),
        "Wheat",
        {"index": "bdi", "window_days": 30},
    )
    assert score == 1.0


def test_shipping_pressure_bull_when_positive_inverts() -> None:
    fn = get("shipping_pressure")
    values = [1000.0] * 32 + [1100.0, 1180.0, 1250.0]  # +25%
    series = pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))
    score = fn(
        _DummyStore(shipping_BDI=series),
        "Wheat",
        {"index": "BDI", "window_days": 30, "bull_when": "positive"},
    )
    assert score == 1.0  # rate opp = bull i positive-modus


def test_old_bdi_chg30d_no_longer_registered() -> None:
    """Sub-fase 12.5+ session 113: bdi_chg30d skal være avregistrert."""
    import pytest

    from bedrock.engine.drivers import get as _get

    with pytest.raises(KeyError):
        _get("bdi_chg30d")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# igc_stocks_change
# ---------------------------------------------------------------------------


def test_igc_stocks_dropping_is_bull() -> None:
    fn = get("igc_stocks_change")
    df = pd.DataFrame({"value_mil_tons": [200.0, 175.0]})  # -12.5%
    score = fn(_DummyStore(igc=df), "Corn", {})
    assert score == 1.0


def test_igc_stocks_rising_is_bear() -> None:
    fn = get("igc_stocks_change")
    df = pd.DataFrame({"value_mil_tons": [200.0, 230.0]})  # +15%
    score = fn(_DummyStore(igc=df), "Wheat", {})
    assert score == 0.0


def test_igc_stocks_unknown_instrument_returns_neutral() -> None:
    fn = get("igc_stocks_change")
    score = fn(_DummyStore(), "BTC", {})
    assert score == 0.5


def test_igc_stocks_short_history_returns_neutral() -> None:
    fn = get("igc_stocks_change")
    df = pd.DataFrame({"value_mil_tons": [200.0]})
    score = fn(_DummyStore(igc=df), "Corn", {})
    assert score == 0.5


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_drivers_all_registered() -> None:
    for name in [
        "crop_progress_stage",
        "wasde_s2u_change",
        "export_event_active",
        "disease_pressure",
        "shipping_pressure",
        "igc_stocks_change",
    ]:
        assert get(name) is not None
