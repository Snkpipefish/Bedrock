"""Tester for structure + risk-drivere (Block A polish, session 79).

Verifiserer ``range_position`` og ``vol_regime`` mot syntetisk OHLCV-
data. Hverken driver krever store-impl utover ``get_prices_ohlc``;
dummy-store dekker kontrakten.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Hjelpere
# ---------------------------------------------------------------------------


class _DummyStore:
    """Minimal store-stub for OHLCV-baserte drivere."""

    def __init__(self, ohlc: pd.DataFrame) -> None:
        self._ohlc = ohlc

    def get_prices_ohlc(
        self, instrument: str, tf: str = "D1", lookback: int | None = None
    ) -> pd.DataFrame:
        if lookback is None:
            return self._ohlc
        return self._ohlc.tail(lookback)


def _build_ohlc(closes: list[float], spread: float = 0.5) -> pd.DataFrame:
    """Bygg syntetisk OHLCV med high = close + spread, low = close - spread."""
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + spread for c in closes],
            "low": [c - spread for c in closes],
            "close": closes,
            "volume": [0.0] * n,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# range_position
# ---------------------------------------------------------------------------


def test_range_position_at_top() -> None:
    """Close = max av siste 20 = 1.0 (spread=0 for å matche high)."""
    fn = get("range_position")
    closes = [100.0] * 19 + [120.0]  # spike på siste bar
    store = _DummyStore(_build_ohlc(closes, spread=0.0))
    score = fn(store, "X", {"window": 20, "mode": "continuation"})
    assert score == pytest.approx(1.0)


def test_range_position_at_bottom() -> None:
    """Close = min av siste 20 = 0.0 (spread=0)."""
    fn = get("range_position")
    closes = [100.0] * 19 + [80.0]
    store = _DummyStore(_build_ohlc(closes, spread=0.0))
    score = fn(store, "X", {"window": 20, "mode": "continuation"})
    assert score == pytest.approx(0.0)


def test_range_position_midrange() -> None:
    """Close midt mellom min og max ≈ 0.5."""
    fn = get("range_position")
    closes = [100.0, 110.0] * 9 + [105.0, 105.0]
    store = _DummyStore(_build_ohlc(closes, spread=0.0))
    score = fn(store, "X", {"window": 20, "mode": "continuation"})
    assert 0.4 <= score <= 0.6


def test_range_position_mean_revert_inverts() -> None:
    """mean_revert-mode: nær bunn = bull (1.0)."""
    fn = get("range_position")
    closes = [100.0] * 19 + [80.0]
    store = _DummyStore(_build_ohlc(closes, spread=0.0))
    score = fn(store, "X", {"window": 20, "mode": "mean_revert"})
    assert score == pytest.approx(1.0)


def test_range_position_short_history_returns_zero() -> None:
    """Kort historikk (< window) = 0.0."""
    fn = get("range_position")
    closes = [100.0] * 5
    store = _DummyStore(_build_ohlc(closes))
    score = fn(store, "X", {"window": 20})
    assert score == 0.0


def test_range_position_flat_range_returns_zero() -> None:
    """high == low → 0.0 (unngår div-by-zero)."""
    fn = get("range_position")
    closes = [100.0] * 25
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [0.0] * 25,
        },
        index=pd.date_range("2024-01-01", periods=25, freq="D"),
    )
    store = _DummyStore(df)
    score = fn(store, "X", {"window": 20})
    assert score == 0.0


def test_range_position_handles_store_error() -> None:
    """Store-exception → 0.0 (defensive)."""
    fn = get("range_position")

    class _BadStore:
        def get_prices_ohlc(self, *a: Any, **kw: Any) -> pd.DataFrame:
            raise RuntimeError("db gone")

    score = fn(_BadStore(), "X", {})
    assert score == 0.0


# ---------------------------------------------------------------------------
# vol_regime
# ---------------------------------------------------------------------------


def test_vol_regime_high_vol_returns_high_score() -> None:
    """Vol-spike helt på slutten → høy percentil → høy score (high_is_bull)."""
    fn = get("vol_regime")
    # 250 dager med low vol (close ±0.1), siste 20 dager høy vol (close ±5).
    closes = [100.0 + 0.1 * (i % 2) for i in range(250)] + [
        100.0 + 5.0 * ((-1) ** i) for i in range(20)
    ]
    store = _DummyStore(_build_ohlc(closes))
    score = fn(store, "X", {"period": 14, "lookback": 252})
    assert score >= 0.8


def test_vol_regime_low_vol_returns_low_score() -> None:
    """Vol-kompresjon på slutten → lav percentil → lav score (high_is_bull)."""
    fn = get("vol_regime")
    closes = [100.0 + 5.0 * ((-1) ** i) for i in range(250)] + [
        100.0 + 0.05 * (i % 2) for i in range(20)
    ]
    store = _DummyStore(_build_ohlc(closes))
    score = fn(store, "X", {"period": 14, "lookback": 252})
    assert score <= 0.2


def test_vol_regime_low_is_bull_inverts() -> None:
    """low_is_bull: kompresjon → høy score."""
    fn = get("vol_regime")
    closes = [100.0 + 5.0 * ((-1) ** i) for i in range(250)] + [
        100.0 + 0.05 * (i % 2) for i in range(20)
    ]
    store = _DummyStore(_build_ohlc(closes))
    score = fn(store, "X", {"period": 14, "lookback": 252, "mode": "low_is_bull"})
    assert score >= 0.8


def test_vol_regime_short_history_returns_zero() -> None:
    fn = get("vol_regime")
    closes = [100.0] * 5
    store = _DummyStore(_build_ohlc(closes))
    score = fn(store, "X", {"period": 14, "lookback": 252})
    assert score == 0.0


def test_vol_regime_handles_store_error() -> None:
    fn = get("vol_regime")

    class _BadStore:
        def get_prices_ohlc(self, *a: Any, **kw: Any) -> pd.DataFrame:
            raise RuntimeError("db gone")

    score = fn(_BadStore(), "X", {})
    assert score == 0.0


def test_drivers_registered() -> None:
    assert get("range_position") is not None
    assert get("vol_regime") is not None
