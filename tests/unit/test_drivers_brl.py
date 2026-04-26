"""Tester for ``brl_chg5d``-driver (session 80).

Verifiserer at driveren leser DEXBZUS-serie, beregner 5-dagers
prosent-endring, og mapper til 0..1 via BRL-kalibrerte terskler.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from bedrock.engine.drivers import get


class _DummyStore:
    """Minimal store-stub for fundamentals-baserte drivere."""

    def __init__(self, series: pd.Series, series_id: str = "DEXBZUS") -> None:
        self._series = series
        self._series_id = series_id

    def get_fundamentals(self, series_id: str) -> pd.Series:
        if series_id != self._series_id:
            raise KeyError(series_id)
        return self._series


def _build(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx)


# ---------------------------------------------------------------------------
# brl_chg5d
# ---------------------------------------------------------------------------


def test_brl_chg5d_strong_brl_weak_returns_one() -> None:
    """USDBRL +3% over 5d → BRL svekket sterkt → bull (1.0) for positive-mode."""
    fn = get("brl_chg5d")
    # Bygg en serie der siste = 5.15, t-5 = 5.0 (3% opp)
    values = [5.0] * 6 + [5.15]  # n=7, change[-1] vs [-6]
    store = _DummyStore(_build(values))
    score = fn(store, "Coffee", {"window": 5, "bull_when": "positive"})
    assert score == 1.0


def test_brl_chg5d_strong_brl_strong_returns_zero() -> None:
    """USDBRL -3% (BRL styrket sterkt) → bear (0.0) for positive-mode."""
    fn = get("brl_chg5d")
    values = [5.0] * 6 + [4.85]  # -3%
    store = _DummyStore(_build(values))
    score = fn(store, "Coffee", {"window": 5, "bull_when": "positive"})
    assert score == 0.0


def test_brl_chg5d_neutral_returns_half() -> None:
    """±0.5% er innenfor ±1% terskel → 0.5 (nøytral)."""
    fn = get("brl_chg5d")
    values = [5.0] * 6 + [5.025]  # +0.5%
    store = _DummyStore(_build(values))
    score = fn(store, "Coffee", {"window": 5, "bull_when": "positive"})
    assert score == 0.5


def test_brl_chg5d_negative_mode_inverts() -> None:
    """bull_when=negative: USDBRL -3% (BRL styrke) blir bull (1.0)."""
    fn = get("brl_chg5d")
    values = [5.0] * 6 + [4.85]
    store = _DummyStore(_build(values))
    score = fn(store, "X", {"window": 5, "bull_when": "negative"})
    assert score == 1.0


def test_brl_chg5d_short_history_returns_zero() -> None:
    fn = get("brl_chg5d")
    values = [5.0, 5.05]  # n=2, window=5 krever ≥6
    store = _DummyStore(_build(values))
    score = fn(store, "X", {"window": 5})
    assert score == 0.0


def test_brl_chg5d_missing_series_returns_zero() -> None:
    fn = get("brl_chg5d")
    store = _DummyStore(_build([5.0] * 10), series_id="OTHER")
    score = fn(store, "X", {})
    assert score == 0.0


def test_brl_chg5d_handles_store_error() -> None:
    fn = get("brl_chg5d")

    class _BadStore:
        def get_fundamentals(self, *a: Any, **kw: Any) -> pd.Series:
            raise RuntimeError("db gone")

    score = fn(_BadStore(), "X", {})
    assert score == 0.0


def test_brl_chg5d_custom_thresholds() -> None:
    """Brukerstyrt thresholds skal overstyre default."""
    fn = get("brl_chg5d")
    values = [5.0] * 6 + [5.005]  # +0.1%
    store = _DummyStore(_build(values))
    custom = [(0.05, 1.0), (0.0, 0.6)]
    score = fn(store, "X", {"window": 5, "bull_when": "positive", "thresholds": custom})
    assert score == 1.0  # 0.1% >= 0.05% terskel


def test_brl_chg5d_registered() -> None:
    assert get("brl_chg5d") is not None
