# pyright: reportAttributeAccessIssue=false, reportReturnType=false
"""Tester for ``conab_yoy`` driver (sub-fase 12.5+ session 111)."""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockConabStore:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self._data = data

    def get_conab_estimates(self, commodity: str, last_n: int | None = None):
        if commodity not in self._data:
            raise KeyError(f"No Conab data for {commodity!r}")
        df = self._data[commodity]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _row(yoy_pct: float | None, commodity: str = "soja") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "report_date": pd.Timestamp("2026-04-15"),
                "commodity": commodity,
                "levantamento": "7o",
                "safra": "2025/26",
                "production": 179151.6,
                "production_units": "kt",
                "area_kha": 48472.7,
                "yield_value": 3696,
                "yield_units": "kgha",
                "yoy_change_pct": yoy_pct,
                "mom_change_pct": None,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("conab_yoy") is not None


# ---------------------------------------------------------------------------
# Step-mapping
# ---------------------------------------------------------------------------


def test_strong_shortfall_returns_1() -> None:
    """YoY -15% (≤ -10) → 1.0."""
    store = _MockConabStore({"soja": _row(yoy_pct=-15.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 1.0


def test_moderate_shortfall_returns_085() -> None:
    """YoY -7% (≤ -5) → 0.85."""
    store = _MockConabStore({"soja": _row(yoy_pct=-7.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.85


def test_mild_shortfall_returns_065() -> None:
    """YoY -3% (≤ -2) → 0.65."""
    store = _MockConabStore({"soja": _row(yoy_pct=-3.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.65


def test_flat_returns_05() -> None:
    """YoY 0% (≤ 0) → 0.5 (nøytral)."""
    store = _MockConabStore({"soja": _row(yoy_pct=0.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.5


def test_modest_growth_returns_035() -> None:
    """YoY +3% (≤ +5) → 0.35."""
    store = _MockConabStore({"soja": _row(yoy_pct=3.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.35


def test_strong_growth_returns_015() -> None:
    """YoY +10% (> +5) → 0.15."""
    store = _MockConabStore({"soja": _row(yoy_pct=10.0)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.15


# ---------------------------------------------------------------------------
# null/missing yoy_change_pct
# ---------------------------------------------------------------------------


def test_null_yoy_returns_neutral() -> None:
    """yoy_change_pct = None → 0.5 (kan ikke tolke)."""
    store = _MockConabStore({"soja": _row(yoy_pct=None)})
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.5


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_commodity_missing() -> None:
    fn = get("conab_yoy")
    assert fn(_MockConabStore({}), "Soybean", {}) == 0.0


def test_returns_zero_when_commodity_unknown() -> None:
    fn = get("conab_yoy")
    assert fn(_MockConabStore({}), "Soybean", {"commodity": "soja"}) == 0.0


def test_returns_zero_when_store_raises() -> None:
    class _Broken:
        def get_conab_estimates(self, commodity, last_n=None):
            raise RuntimeError("DB error")

    fn = get("conab_yoy")
    assert fn(_Broken(), "Soybean", {"commodity": "soja"}) == 0.0


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds() -> None:
    """YAML kan overstyre step-mapping."""
    store = _MockConabStore({"soja": _row(yoy_pct=-3.0)})
    fn = get("conab_yoy")
    score = fn(
        store,
        "Soybean",
        {
            "commodity": "soja",
            "thresholds": [(-5, 0.9), (0, 0.4), (5, 0.2)],
        },
    )
    # -3 ≤ 0 → 0.4 (per custom mapping)
    assert score == 0.4


# ---------------------------------------------------------------------------
# Multi-commodity isolering
# ---------------------------------------------------------------------------


def test_different_commodities_resolve_independently() -> None:
    """Soja shortfall + milho excess → forskjellige scores."""
    store = _MockConabStore(
        {
            "soja": _row(yoy_pct=-7.0, commodity="soja"),  # shortfall
            "milho": _row(yoy_pct=8.0, commodity="milho"),  # excess
        }
    )
    fn = get("conab_yoy")
    assert fn(store, "Soybean", {"commodity": "soja"}) == 0.85  # bullish
    assert fn(store, "Corn", {"commodity": "milho"}) == 0.15  # bearish
