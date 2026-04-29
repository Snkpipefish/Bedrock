"""Tester for ``vix_term_ratio``-driver (sub-fase 12.7 D2 B2, session 131)."""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    def __init__(self, series: dict[str, pd.Series]):
        self._series = series

    def get_fundamentals(self, series_id: str, last_n: int | None = None) -> pd.Series:
        if series_id not in self._series:
            raise KeyError(f"No fundamentals for series_id={series_id!r}")
        s = self._series[series_id]
        if last_n is None:
            return s
        return s.tail(last_n)


def _series(values: list[float], start: str = "2024-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


# ---------------------------------------------------------------------------
# Default mode
# ---------------------------------------------------------------------------


def test_strong_contango_returns_one() -> None:
    """VIX3M/VIX − 1 ≥ 0.10 → 1.0 (rolig regime)."""
    # VIX=15, VIX3M=17 → ratio = 0.133 ≥ 0.10 → 1.0
    store = _MockStore({"VIX3M": _series([17.0]), "VIXCLS": _series([15.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {}) == 1.0


def test_mild_contango_returns_neutral() -> None:
    """0 ≤ ratio < 0.05 → 0.5."""
    # VIX=15, VIX3M=15.3 → ratio = 0.02 → first match descending: 0.0 → 0.5
    store = _MockStore({"VIX3M": _series([15.3]), "VIXCLS": _series([15.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {}) == 0.5


def test_mild_backwardation_returns_low() -> None:
    """-0.05 ≤ ratio < 0 → 0.25."""
    # VIX=20, VIX3M=19.5 → ratio = -0.025
    store = _MockStore({"VIX3M": _series([19.5]), "VIXCLS": _series([20.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {}) == 0.25


def test_crisis_backwardation_returns_zero() -> None:
    """ratio < -0.05 → 0.0 (krise-regime)."""
    # VIX=40, VIX3M=30 → ratio = -0.25 (kraftig backwardation)
    store = _MockStore({"VIX3M": _series([30.0]), "VIXCLS": _series([40.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_invert_flips_score() -> None:
    """invert=True: kraftig contango → 0.0 (kontrært)."""
    store = _MockStore({"VIX3M": _series([17.0]), "VIXCLS": _series([15.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {"invert": True}) == 0.0


def test_missing_series_returns_zero() -> None:
    store = _MockStore({"VIX3M": _series([17.0])})  # VIXCLS mangler
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_zero_denominator_filtered() -> None:
    """Datoer med VIX=0 filtreres bort (div-by-0)."""
    store = _MockStore(
        {
            "VIX3M": _series([17.0, 17.0]),
            "VIXCLS": _series([15.0, 0.0]),  # siste obs har VIX=0
        }
    )
    fn = get("vix_term_ratio")
    # Etter filtrering: kun første rad → ratio = 17/15 - 1 = 0.133 → 1.0
    assert fn(store, "Nasdaq", {}) == 1.0


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def test_pct_12m_top_percentile() -> None:
    """pct_12m: current på topp av 252+ obs → bull_when=high → ≈ 1.0."""
    # Lag VIX3M monotont stigende, VIX flat → ratio monotont stigende.
    vix = [15.0] * 300
    vix3m = [15.0 + i * 0.05 for i in range(300)]
    store = _MockStore({"VIX3M": _series(vix3m), "VIXCLS": _series(vix)})
    fn = get("vix_term_ratio")
    score = fn(store, "Nasdaq", {"mode": "pct_12m"})
    assert score >= 0.9


def test_extreme_flag_hard_outlier() -> None:
    """Extreme-flag-hard: ratio-outlier på topp → 1.0."""
    vix = [15.0] * 300
    vix3m = [15.0] * 299 + [25.0]  # outlier-contango
    store = _MockStore({"VIX3M": _series(vix3m), "VIXCLS": _series(vix)})
    fn = get("vix_term_ratio")
    score = fn(store, "Nasdaq", {"mode": "extreme_flag_hard"})
    assert score == 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    store = _MockStore({"VIX3M": _series([17.0]), "VIXCLS": _series([15.0])})
    fn = get("vix_term_ratio")
    assert fn(store, "Nasdaq", {"mode": "garbage"}) == 1.0


def test_alternative_numerator_vix6m() -> None:
    """numerator_series-param: VIX6M støttes."""
    store = _MockStore({"VIX6M": _series([18.0]), "VIXCLS": _series([15.0])})
    fn = get("vix_term_ratio")
    score = fn(store, "Nasdaq", {"numerator_series": "VIX6M"})
    # ratio = 18/15 - 1 = 0.20 ≥ 0.10 → 1.0
    assert score == 1.0
