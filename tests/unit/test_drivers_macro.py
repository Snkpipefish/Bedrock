"""Tester for ``bedrock.engine.drivers.macro``.

Verifiserer real_yield, dxy_chg5d, vix_regime mot in-memory mock-store.
Bruker ikke ekte FRED-data — testene er deterministiske og dekker
grenseverdier + ``bull_when``-konfigurasjoner.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockStore:
    """Stub som returnerer pd.Series for FRED-serier."""

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
    """Bygg pd.Series med daglig index."""
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


# ---------------------------------------------------------------------------
# real_yield
# ---------------------------------------------------------------------------


def test_real_yield_negative_returns_max_score_for_low_bull() -> None:
    """Negativ real yield → 1.0 (default Gold-tolkning)."""
    store = _MockStore(
        {
            "DGS10": _series([2.0]),
            "T10YIE": _series([2.5]),  # real_yield = -0.5
        }
    )
    fn = get("real_yield")
    assert fn(store, "Gold", {}) == 1.0


def test_real_yield_high_returns_zero_for_low_bull() -> None:
    """Høy real yield → 0.0 (default Gold-tolkning)."""
    store = _MockStore(
        {
            "DGS10": _series([5.0]),
            "T10YIE": _series([1.5]),  # real_yield = 3.5
        }
    )
    fn = get("real_yield")
    # 3.5 > 2.5 default-terskel → ingen step matchet → 0.0
    assert fn(store, "Gold", {}) == 0.0


def test_real_yield_high_bull_inverts_mapping() -> None:
    """``bull_when="high"`` skal speile mappingen."""
    store = _MockStore(
        {
            "DGS10": _series([5.0]),
            "T10YIE": _series([1.5]),  # real_yield = 3.5
        }
    )
    fn = get("real_yield")
    # 3.5 ≥ 2.5 → 1.0 i high-bull-mapping
    assert fn(store, "USD", {"bull_when": "high"}) == 1.0


def test_real_yield_moderate_returns_neutral() -> None:
    """Real yield i nøytral-sone (~1.0) → 0.5."""
    store = _MockStore(
        {
            "DGS10": _series([3.0]),
            "T10YIE": _series([2.0]),  # real_yield = 1.0
        }
    )
    fn = get("real_yield")
    # 1.0 ≤ 1.5 default-terskel → 0.5
    assert fn(store, "Gold", {}) == 0.5


def test_real_yield_missing_series_returns_zero() -> None:
    store = _MockStore({"DGS10": _series([2.0])})  # T10YIE mangler
    fn = get("real_yield")
    assert fn(store, "Gold", {}) == 0.0


def test_real_yield_no_overlap_returns_zero() -> None:
    """Hvis serier ikke overlapper → tom diff → 0.0."""
    dgs = pd.Series([2.0], index=pd.to_datetime(["2024-01-01"]))
    t10 = pd.Series([2.0], index=pd.to_datetime(["2025-06-01"]))
    store = _MockStore({"DGS10": dgs, "T10YIE": t10})
    fn = get("real_yield")
    assert fn(store, "Gold", {}) == 0.0


def test_real_yield_custom_thresholds() -> None:
    """Brukerstyrt thresholds skal overstyre default."""
    store = _MockStore(
        {
            "DGS10": _series([3.0]),
            "T10YIE": _series([1.0]),  # real_yield = 2.0
        }
    )
    fn = get("real_yield")
    # Custom: real_yield ≤ 2.5 → 0.9
    score = fn(
        store,
        "Gold",
        {"thresholds": [[2.5, 0.9], [5.0, 0.4]]},
    )
    assert score == 0.9


# ---------------------------------------------------------------------------
# dxy_chg5d
# ---------------------------------------------------------------------------


def test_dxy_chg5d_strong_negative_returns_max_for_negative_bull() -> None:
    """USD-svakhet (-2%) → 1.0 (default Gold)."""
    # 100 → 100 → 100 → 100 → 100 → 98 (5d windows: -2%)
    store = _MockStore({"DTWEXBGS": _series([100, 100, 100, 100, 100, 98])})
    fn = get("dxy_chg5d")
    assert fn(store, "Gold", {}) == 1.0


def test_dxy_chg5d_strong_positive_returns_zero_for_negative_bull() -> None:
    """USD-styrke (+2%) → ingen match i ascending-pass → 0.0 (default Gold)."""
    store = _MockStore({"DTWEXBGS": _series([100, 100, 100, 100, 100, 102])})
    fn = get("dxy_chg5d")
    # +2 > +1.5 default-terskel; ingen flere → 0.0
    assert fn(store, "Gold", {}) == 0.0


def test_dxy_chg5d_positive_bull_inverts() -> None:
    """``bull_when="positive"`` skal gi 1.0 ved USD-styrke."""
    store = _MockStore({"DTWEXBGS": _series([100, 100, 100, 100, 100, 102])})
    fn = get("dxy_chg5d")
    assert fn(store, "USD", {"bull_when": "positive"}) == 1.0


def test_dxy_chg5d_neutral_returns_mid() -> None:
    """Liten endring (±0.5%) → 0.5."""
    store = _MockStore({"DTWEXBGS": _series([100, 100, 100, 100, 100, 100.2])})
    fn = get("dxy_chg5d")
    assert fn(store, "Gold", {}) == 0.5


def test_dxy_chg5d_missing_series_returns_zero() -> None:
    store = _MockStore({})
    fn = get("dxy_chg5d")
    assert fn(store, "Gold", {}) == 0.0


def test_dxy_chg5d_short_history_returns_zero() -> None:
    store = _MockStore({"DTWEXBGS": _series([100, 100, 100])})  # 3 obs < window+1
    fn = get("dxy_chg5d")
    assert fn(store, "Gold", {"window": 5}) == 0.0


def test_dxy_chg5d_custom_window() -> None:
    """Window=2 skal regne 2-dager pct change."""
    # 100 → 102 → 95 over 3 dager (ikke nok for 5d, men fungerer for window=2)
    store = _MockStore({"DTWEXBGS": _series([100, 102, 95])})
    fn = get("dxy_chg5d")
    # 2d-endring: (95-100)/100 = -5%, sterk USD-svakhet → 1.0
    assert fn(store, "Gold", {"window": 2}) == 1.0


# ---------------------------------------------------------------------------
# vix_regime
# ---------------------------------------------------------------------------


def test_vix_regime_low_returns_max_for_default() -> None:
    """VIX = 12 (rolig) → 1.0 (default risk-on)."""
    store = _MockStore({"VIXCLS": _series([12.0])})
    fn = get("vix_regime")
    assert fn(store, "Gold", {}) == 1.0


def test_vix_regime_extreme_returns_zero() -> None:
    """VIX = 50 (krise) → 0.0 (default risk-on)."""
    store = _MockStore({"VIXCLS": _series([50.0])})
    fn = get("vix_regime")
    assert fn(store, "Gold", {}) == 0.0


def test_vix_regime_invert_for_safe_haven() -> None:
    """``invert=True`` flipper mappingen — Gold som safe-haven er bull
    når VIX er høy."""
    store_low = _MockStore({"VIXCLS": _series([12.0])})
    store_high = _MockStore({"VIXCLS": _series([35.0])})
    fn = get("vix_regime")

    score_low_invert = fn(store_low, "Gold", {"invert": True})
    score_high_invert = fn(store_high, "Gold", {"invert": True})

    assert score_low_invert < score_high_invert


def test_vix_regime_normal_returns_mid_to_high() -> None:
    """VIX = 18 (normal) → 0.75."""
    store = _MockStore({"VIXCLS": _series([18.0])})
    fn = get("vix_regime")
    assert fn(store, "Gold", {}) == 0.75


def test_vix_regime_missing_series_returns_zero() -> None:
    store = _MockStore({})
    fn = get("vix_regime")
    assert fn(store, "Gold", {}) == 0.0


def test_vix_regime_empty_series_returns_zero() -> None:
    store = _MockStore({"VIXCLS": pd.Series([], dtype="float64")})
    fn = get("vix_regime")
    assert fn(store, "Gold", {}) == 0.0


def test_vix_regime_custom_thresholds() -> None:
    """Brukerstyrt thresholds skal overstyre."""
    store = _MockStore({"VIXCLS": _series([22.0])})
    fn = get("vix_regime")
    # Custom: VIX ≤ 25 → 0.9
    score = fn(
        store,
        "Gold",
        {"thresholds": [[25.0, 0.9], [50.0, 0.5]]},
    )
    assert score == 0.9


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_all_macro_drivers_registered() -> None:
    """Alle tre drivere skal være tilgjengelige fra registry."""
    for name in ("real_yield", "dxy_chg5d", "vix_regime"):
        fn = get(name)
        assert fn is not None
