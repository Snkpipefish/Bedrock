"""Tester for ``aaii_extreme``-driver (sub-fase 12.7 D2 A12, session 131).

Pattern-doc § 3.2 mean-reversion-mønster: returnerer ``1 − percentile`` for
bullish_pct (kontra-indikator). Ekstrem bullish-historikk = lav score
(bear-of-SP500 fra contrarian-perspective).
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    def __init__(self, df: pd.DataFrame | None):
        self._df = df

    def get_aaii_sentiment(self, last_n: int | None = None) -> pd.DataFrame:
        if self._df is None or self._df.empty:
            raise KeyError("No AAII data")
        if last_n is None:
            return self._df
        return self._df.tail(last_n).reset_index(drop=True)


def _make_aaii(values: list[float], start: str = "2024-01-04") -> pd.DataFrame:
    """Bygg AAII-DF med ukentlig (tor) kadens."""
    idx = pd.date_range(start, periods=len(values), freq="W-THU")
    return pd.DataFrame(
        {
            "date": idx,
            "bullish_pct": values,
            "neutral_pct": [33.0] * len(values),
            "bearish_pct": [33.0] * len(values),
            "bull_bear_spread": [v - 33.0 for v in values],
        }
    )


# ---------------------------------------------------------------------------
# Default mode (mean-reversion inversjon)
# ---------------------------------------------------------------------------


def test_high_bullish_returns_low_score() -> None:
    """Ekstrem bullish_pct (current på topp av 52w) → invertert ≈ 0.0."""
    # 52 obs, monotont stigende → current på topp percentile
    values = [30.0 + i * 0.5 for i in range(60)]
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {})
    # current er topp → percentile ≈ 1.0 → invertert ≈ 0.0
    assert score <= 0.05


def test_low_bullish_returns_high_score() -> None:
    """Ekstrem lav bullish_pct (current på bunnen) → invertert ≈ 1.0."""
    # Monotont synkende
    values = [60.0 - i * 0.5 for i in range(60)]
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {})
    # current på bunn → percentile ≈ 0.0 → invertert ≈ 1.0
    assert score >= 0.95


def test_neutral_bullish_returns_mid() -> None:
    """Bullish_pct nær median → score nær 0.5."""
    values = [30.0, 40.0, 50.0, 60.0, 70.0] * 12 + [50.0]  # 61 obs, current = midten
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {})
    assert 0.3 <= score <= 0.7


def test_bearish_pct_metric_not_inverted() -> None:
    """metric='bearish_pct': invertering bør IKKE skje (bearish høy = bullish for SP500)."""
    df = _make_aaii([30.0] * 51 + [60.0])  # current bearish_pct=33; topp i bullish_pct (60)
    # men vi ber om bearish_pct-feature, som er flat (33.0 for alle).
    df["bearish_pct"] = [10.0 + i * 0.5 for i in range(52)]  # monotont stigende
    store = _MockStore(df)
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {"metric": "bearish_pct"})
    # current bearish høy → percentile høy → IKKE invertert → score ≈ 1.0
    assert score >= 0.9


def test_bull_bear_spread_inverted() -> None:
    """metric='bull_bear_spread': invertert (høy spread = bullish-extreme = mean-rev-bear)."""
    df = _make_aaii([30.0] * 52)
    df["bull_bear_spread"] = [-20.0 + i * 0.5 for i in range(52)]  # monotont stigende
    store = _MockStore(df)
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {"metric": "bull_bear_spread"})
    assert score <= 0.05


def test_no_data_returns_zero() -> None:
    store = _MockStore(None)
    fn = get("aaii_extreme")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_short_history_returns_zero() -> None:
    """Mindre enn MIN_OBS_FOR_PCTILE+1 obs → 0.0."""
    store = _MockStore(_make_aaii([40.0, 45.0, 50.0]))  # 3 obs
    fn = get("aaii_extreme")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_invalid_metric_returns_zero() -> None:
    store = _MockStore(_make_aaii([40.0] * 52))
    fn = get("aaii_extreme")
    assert fn(store, "Nasdaq", {"metric": "garbage_field"}) == 0.0


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def test_pct_12m_mode_same_as_default() -> None:
    """pct_12m mode er identisk default for bullish_pct."""
    values = [30.0 + i * 0.5 for i in range(60)]
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    default = fn(store, "Nasdaq", {})
    pct_12m = fn(store, "Nasdaq", {"mode": "pct_12m"})
    assert default == pct_12m


def test_extreme_flag_hard_at_top() -> None:
    """extreme_flag_hard: outlier på topp → 1.0 (symmetrisk, ikke invertert)."""
    values = [40.0] * 51 + [99.0]  # outlier
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    score = fn(store, "Nasdaq", {"mode": "extreme_flag_hard"})
    assert score == 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    """Ukjent mode → invertert percentile-score (samme som default)."""
    values = [30.0 + i * 0.5 for i in range(60)]
    store = _MockStore(_make_aaii(values))
    fn = get("aaii_extreme")
    default = fn(store, "Nasdaq", {})
    fallback = fn(store, "Nasdaq", {"mode": "garbage"})
    assert default == fallback
