"""Tester for ``comex_stress`` driver (sub-fase 12.5+ session 108)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockComexStore:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self._data = data

    def get_comex_inventory(self, metal: str, last_n: int | None = None):
        if metal not in self._data:
            raise KeyError(f"No COMEX data for {metal!r}")
        df = self._data[metal]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _build_df(
    *,
    n_days: int = 200,  # Sub-fase 12.10 Bunke 1 Bug-2: ≥ default min_samples=20
    metal: str = "gold",
    base_reg: float = 15_000_000.0,
    base_total: float = 25_000_000.0,
    reg_step: float = 0.0,
    units: str = "oz",
) -> pd.DataFrame:
    """Bygg COMEX-DataFrame med kontrollerbar trend i registered."""
    base = date(2024, 1, 1)
    rows = []
    for i in range(n_days):
        rows.append(
            {
                "metal": metal,
                "date": pd.Timestamp(base + timedelta(days=i)),
                "registered": base_reg + reg_step * i,
                "eligible": base_total - base_reg,
                "total": base_total,
                "units": units,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("comex_stress") is not None


# ---------------------------------------------------------------------------
# Coverage-baseberegning (gold/silver)
# ---------------------------------------------------------------------------


def test_low_coverage_high_stress() -> None:
    """registered=2M / total=25M = 8% coverage → base = 0.92*0.8 = 0.736."""
    df = _build_df(base_reg=2_000_000, base_total=25_000_000, n_days=200)
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    score = fn(store, "Gold", {"metal": "gold"})
    assert score > 0.7  # Høy stress


def test_high_coverage_low_stress() -> None:
    """registered=23M / total=25M = 92% coverage → base = 0.08*0.8 = 0.064."""
    df = _build_df(base_reg=23_000_000, base_total=25_000_000, n_days=200)
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    score = fn(store, "Gold", {"metal": "gold"})
    assert score < 0.3  # Lav stress


def test_falling_registered_adds_stress() -> None:
    """5d WoW < -5% → +0.15 bonus."""
    df = _build_df(base_reg=20_000_000, base_total=25_000_000, reg_step=-200_000, n_days=200)
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    score_with_drop = fn(store, "Gold", {"metal": "gold", "wow_window": 5})

    # Sammenlign med flat scenario
    df_flat = _build_df(base_reg=20_000_000, base_total=25_000_000, reg_step=0, n_days=200)
    store_flat = _MockComexStore({"gold": df_flat})
    score_flat = fn(store_flat, "Gold", {"metal": "gold", "wow_window": 5})

    assert score_with_drop > score_flat


def test_rising_registered_reduces_stress() -> None:
    """5d WoW > +5% → -0.05 bonus."""
    df = _build_df(base_reg=15_000_000, base_total=25_000_000, reg_step=200_000, n_days=200)
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    score_rising = fn(store, "Gold", {"metal": "gold", "wow_window": 5})

    df_flat = _build_df(base_reg=15_000_000, base_total=25_000_000, reg_step=0, n_days=200)
    store_flat = _MockComexStore({"gold": df_flat})
    score_flat = fn(store_flat, "Gold", {"metal": "gold", "wow_window": 5})

    assert score_rising < score_flat


# ---------------------------------------------------------------------------
# Kobber-spesial-håndtering
# ---------------------------------------------------------------------------


def test_copper_skip_default_returns_neutral_when_flat() -> None:
    """Kobber med flat registered → 0.5 (neutral) pga skip."""
    n = 200  # Bunke 9 #35: ≥ default min_samples=180
    df = pd.DataFrame(
        {
            "metal": ["copper"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "registered": [50_000.0] * n,
            "eligible": [0.0] * n,
            "total": [50_000.0] * n,
            "units": ["st"] * n,
        }
    )
    store = _MockComexStore({"copper": df})
    fn = get("comex_stress")
    score = fn(store, "Copper", {"metal": "copper"})
    # 0.5 (neutral) — ingen WoW-bonus med flat data
    assert score == 0.5


def test_copper_with_falling_inventory_picks_up_stress() -> None:
    """Kobber med synkende registered får WoW-bonus selv om base = 0.5."""
    n = 200
    df = pd.DataFrame(
        {
            "metal": ["copper"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "registered": [50_000.0 - 100 * i for i in range(n)],
            "eligible": [0.0] * n,
            "total": [50_000.0 - 100 * i for i in range(n)],
            "units": ["st"] * n,
        }
    )
    store = _MockComexStore({"copper": df})
    fn = get("comex_stress")
    score = fn(store, "Copper", {"metal": "copper", "wow_window": 5})
    # WoW < -5% → +0.15 → 0.65
    assert score > 0.5


def test_copper_handling_trend_only_uses_coverage_anyway() -> None:
    """trend_only-mode skipper coverage-base og bruker kun WoW (= 0 base)."""
    n = 200
    df = pd.DataFrame(
        {
            "metal": ["copper"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "registered": [50_000.0 - 100 * i for i in range(n)],
            "eligible": [0.0] * n,
            "total": [50_000.0 - 100 * i for i in range(n)],
            "units": ["st"] * n,
        }
    )
    store = _MockComexStore({"copper": df})
    fn = get("comex_stress")
    score = fn(
        store,
        "Copper",
        {"metal": "copper", "wow_window": 5, "copper_handling": "trend_only"},
    )
    # trend_only: bruker base = (1 - reg/total)*0.8 — for kobber er
    # reg=total så base=0, men WoW ≈ -2% → +0.05 → 0.05
    assert 0.0 <= score <= 0.25


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_metal_missing() -> None:
    fn = get("comex_stress")
    assert fn(_MockComexStore({}), "Gold", {}) == 0.0


def test_returns_zero_when_metal_not_in_db() -> None:
    fn = get("comex_stress")
    assert fn(_MockComexStore({}), "Gold", {"metal": "gold"}) == 0.0


def test_returns_zero_when_store_raises() -> None:
    class _Broken:
        def get_comex_inventory(self, metal, last_n=None):
            raise RuntimeError("DB issue")

    fn = get("comex_stress")
    assert fn(_Broken(), "Gold", {"metal": "gold"}) == 0.0


def test_returns_neutral_when_total_is_zero() -> None:
    """Kantverdier: total=0 returner 0.5 ikke division-by-zero."""
    df = pd.DataFrame(
        {
            "metal": ["gold"],
            "date": [pd.Timestamp("2024-01-05")],
            "registered": [0.0],
            "eligible": [0.0],
            "total": [0.0],
            "units": ["oz"],
        }
    )
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    assert fn(store, "Gold", {"metal": "gold"}) == 0.5


# ---------------------------------------------------------------------------
# Multi-metal isolering
# ---------------------------------------------------------------------------


def test_different_metals_resolve_independently() -> None:
    """Gull med low coverage, sølv med high coverage → forskjellige scores."""
    gold_df = _build_df(base_reg=2_000_000, base_total=25_000_000, n_days=200, metal="gold")
    silver_df = _build_df(base_reg=380_000_000, base_total=400_000_000, n_days=200, metal="silver")
    store = _MockComexStore({"gold": gold_df, "silver": silver_df})
    fn = get("comex_stress")

    gold_score = fn(store, "Gold", {"metal": "gold"})
    silver_score = fn(store, "Silver", {"metal": "silver"})

    # Gold: low coverage → high stress
    # Silver: high coverage → low stress
    assert gold_score > silver_score
    assert gold_score > 0.5
    assert silver_score < 0.3


# ---------------------------------------------------------------------------
# Score-bounds
# ---------------------------------------------------------------------------


def test_min_samples_guard_returns_neutral_when_sparse() -> None:
    """Sub-fase 12.10 Bunke 1 Bug-2: tabell med < min_samples → 0.5."""
    fn = get("comex_stress")
    # 5 rader (< default min_samples=20) → 0.5 selv om coverage tilsier høy stress
    df = _build_df(base_reg=2_000_000, base_total=25_000_000, n_days=5)
    store = _MockComexStore({"gold": df})
    assert fn(store, "Gold", {"metal": "gold"}) == 0.5


def test_min_samples_guard_overridable_via_param() -> None:
    """min_samples=3 → 5 rader er nok → vanlig score."""
    fn = get("comex_stress")
    df = _build_df(base_reg=2_000_000, base_total=25_000_000, n_days=5)
    store = _MockComexStore({"gold": df})
    score = fn(store, "Gold", {"metal": "gold", "min_samples": 3})
    assert score > 0.7


def test_score_clamped_to_unit_interval() -> None:
    """Eksterm WoW + lav coverage skal ikke gå over 1.0."""
    n = 200
    df = pd.DataFrame(
        {
            "metal": ["gold"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "registered": [10_000_000.0 if i < 12 else 500_000.0 for i in range(n)],
            "eligible": [15_000_000.0] * n,
            "total": [25_000_000.0] * n,
            "units": ["oz"] * n,
        }
    )
    store = _MockComexStore({"gold": df})
    fn = get("comex_stress")
    score = fn(store, "Gold", {"metal": "gold", "wow_window": 5})
    assert 0.0 <= score <= 1.0
