"""Tester for ``drought_monitor``-driver (sub-fase 12.7 D2 A9, session 133)."""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames

    def get_drought_monitor(self, aoi: str = "us") -> pd.DataFrame:
        key = aoi.lower()
        if key not in self._frames:
            raise KeyError(f"No drought_monitor data for aoi={key!r}")
        return self._frames[key]


def _make_df(d2_values: list[float], start: str = "2024-09-03") -> pd.DataFrame:
    """Bygg USDM-DF med d2_pct-trajectory."""
    idx = pd.date_range(start, periods=len(d2_values), freq="W-TUE")
    n = len(d2_values)
    return pd.DataFrame(
        {
            "map_date": idx,
            "aoi": ["us"] * n,
            "none_pct": [50.0] * n,
            "d0_pct": [v + 30 for v in d2_values],
            "d1_pct": [v + 10 for v in d2_values],
            "d2_pct": d2_values,
            "d3_pct": [v / 3 for v in d2_values],
            "d4_pct": [v / 10 for v in d2_values],
        }
    )


def test_extreme_drought_returns_max_high_bull() -> None:
    """50% i D2+ = ekstrem drought → 1.0 for default bull_when=high."""
    fn = get("drought_monitor")
    df = _make_df([50.0])
    assert fn(_MockStore({"us": df}), "Corn", {}) == 1.0


def test_no_drought_returns_min_high_bull() -> None:
    """0% i D2+ = ingen drought → 0.0 for default bull_when=high."""
    fn = get("drought_monitor")
    df = _make_df([0.0])
    assert fn(_MockStore({"us": df}), "Corn", {}) == 0.0


def test_moderate_drought_returns_neutral() -> None:
    """20% i D2+ ≈ moderat → 0.5."""
    fn = get("drought_monitor")
    df = _make_df([20.0])
    assert fn(_MockStore({"us": df}), "Corn", {}) == 0.5


def test_bull_when_low_inverts() -> None:
    """50% i D2+ med bull_when=low → 0.0."""
    fn = get("drought_monitor")
    df = _make_df([50.0])
    assert fn(_MockStore({"us": df}), "Corn", {"bull_when": "low"}) == 0.0


def test_no_data_returns_zero() -> None:
    fn = get("drought_monitor")
    assert fn(_MockStore({}), "Corn", {}) == 0.0


def test_state_aoi_param() -> None:
    """state-AOI overstyrer default us."""
    fn = get("drought_monitor")
    df_ia = _make_df([45.0])
    df_ia["aoi"] = ["ia"] * len(df_ia)
    out = fn(_MockStore({"ia": df_ia}), "Corn", {"aoi": "IA"})
    assert out == 1.0


def test_metric_d3_pct_param() -> None:
    """Override metric til d3_pct."""
    fn = get("drought_monitor")
    df = _make_df([45.0])
    # d3_pct = d2/3 = 15.0 → fanger ved threshold 15.0 → 0.25 (ikke d2-default)
    out = fn(_MockStore({"us": df}), "Corn", {"metric": "d3_pct"})
    assert out == 0.25


def test_mode_pct_12m_dispatched() -> None:
    """pct_12m-mode returnerer noe i [0, 1]."""
    fn = get("drought_monitor")
    df = _make_df([float(20 + i % 10) for i in range(60)])
    out = fn(_MockStore({"us": df}), "Corn", {"mode": "pct_12m"})
    assert 0.0 <= out <= 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    fn = get("drought_monitor")
    df = _make_df([50.0])
    assert fn(_MockStore({"us": df}), "Corn", {"mode": "made_up"}) == 1.0


def test_custom_thresholds() -> None:
    fn = get("drought_monitor")
    df = _make_df([10.0])
    custom = [(5.0, 0.0), (15.0, 0.5), (100.0, 1.0)]
    # 10% fanger ved threshold=15 → 0.5
    assert fn(_MockStore({"us": df}), "Corn", {"thresholds": custom}) == 0.5
