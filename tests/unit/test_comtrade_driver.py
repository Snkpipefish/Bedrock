"""Unit-tests for comtrade_export_yoy driver (sub-fase 12.11+ session 154)."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers import get


class _StubStore:
    """Minimal store-stub for driver-testing."""

    def __init__(self, series_data: dict[str, pd.Series]) -> None:
        self._data = series_data

    def get_fundamentals(self, series_id: str) -> pd.Series:
        if series_id not in self._data:
            raise KeyError(series_id)
        return self._data[series_id]


def _monthly_series(values: list[float], start: str = "2023-01-01") -> pd.Series:
    """Lag månedlig serie med MS-frequency."""
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def test_returns_neutral_when_series_missing() -> None:
    fn = get("comtrade_export_yoy")
    store = _StubStore({})
    assert fn(store, "Sugar", {"series_id": "MISSING"}) == 0.5


def test_returns_neutral_when_no_series_id() -> None:
    fn = get("comtrade_export_yoy")
    store = _StubStore({})
    assert fn(store, "Sugar", {}) == 0.5


def test_returns_neutral_when_lt_24_months() -> None:
    fn = get("comtrade_export_yoy")
    store = _StubStore({"X": _monthly_series([100.0] * 23)})
    assert fn(store, "Sugar", {"series_id": "X"}) == 0.5


def test_strong_drop_yields_bull_score_when_bull_when_low() -> None:
    """12-mo trailing -50% YoY → step (-30, 1.00) → score 1.00."""
    fn = get("comtrade_export_yoy")
    # Prev 12 mo: 100 each, current 12 mo: 50 each → -50% YoY
    values = [100.0] * 12 + [50.0] * 12
    store = _StubStore({"X": _monthly_series(values)})
    score = fn(store, "Sugar", {"series_id": "X", "bull_when": "low"})
    assert score == 1.00


def test_strong_growth_yields_bear_score_when_bull_when_low() -> None:
    """12-mo trailing +50% YoY → step (10.0, 0.35) overshoot → fallback 0.15."""
    fn = get("comtrade_export_yoy")
    values = [50.0] * 12 + [75.0] * 12  # +50% YoY
    store = _StubStore({"X": _monthly_series(values)})
    score = fn(store, "Sugar", {"series_id": "X", "bull_when": "low"})
    assert score == 0.15


def test_bull_when_high_inverts_score() -> None:
    """Med bull_when='high' returneres 1 - score."""
    fn = get("comtrade_export_yoy")
    values = [100.0] * 12 + [50.0] * 12  # -50% YoY
    store = _StubStore({"X": _monthly_series(values)})
    score_low = fn(store, "Sugar", {"series_id": "X", "bull_when": "low"})
    score_high = fn(store, "Sugar", {"series_id": "X", "bull_when": "high"})
    assert score_low == 1.0
    assert score_high == pytest.approx(1.0 - 1.0)


def test_zero_previous_returns_neutral() -> None:
    """Hvis forrige 12-mo sum er 0, returner 0.5 (unngå div-by-zero)."""
    fn = get("comtrade_export_yoy")
    values = [0.0] * 12 + [100.0] * 12
    store = _StubStore({"X": _monthly_series(values)})
    assert fn(store, "Sugar", {"series_id": "X"}) == 0.5


def test_custom_thresholds_override_default() -> None:
    """User-thresholds overstyrer default step-mappen."""
    fn = get("comtrade_export_yoy")
    values = [100.0] * 12 + [105.0] * 12  # +5% YoY
    store = _StubStore({"X": _monthly_series(values)})
    # Default ville gitt 0.35; override gir 0.99 ved <=10% threshold
    score = fn(
        store,
        "Sugar",
        {
            "series_id": "X",
            "thresholds": [(-100.0, 1.0), (-50.0, 0.85), (10.0, 0.99)],
        },
    )
    assert score == 0.99
