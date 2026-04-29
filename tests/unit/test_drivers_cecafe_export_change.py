"""Tester for ``cecafe_export_change``-driver (sub-fase 12.7 D3 A10, session 135)."""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames

    def get_cecafe_exports(self, coffee_type: str = "sum") -> pd.DataFrame:
        key = coffee_type.lower()
        if key not in self._frames:
            raise KeyError(f"No Cecafé exports for coffee_type={key!r}")
        return self._frames[key]


def _make_df(volumes: list[int], start: str = "2024-01-01") -> pd.DataFrame:
    """Bygg Cecafé-DF med månedlig volume_60kg_bags-trajectory."""
    idx = pd.date_range(start, periods=len(volumes), freq="MS")
    n = len(volumes)
    return pd.DataFrame(
        {
            "month": idx,
            "coffee_type": ["sum"] * n,
            "volume_60kg_bags": volumes,
            "fob_value_usd": [v * 350 for v in volumes],  # ~$350/saca
            "source_pdf": ["test"] * n,
        }
    )


def test_strong_drop_returns_max_low_bull() -> None:
    """-50% MoM = sterk supply-shock → 1.0 for default bull_when=low (kaffe)."""
    fn = get("cecafe_export_change")
    # 4M sacas → 2M sacas = -50%, fanger ved -40-threshold → 0.0 i high-conv,
    # invertert til 1.0 i low-conv (kaffe default).
    df = _make_df([4_000_000, 2_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {}) == 1.0


def test_strong_increase_returns_min_low_bull() -> None:
    """+50% MoM = harvest-flush = bear for kaffe → 0.0."""
    fn = get("cecafe_export_change")
    df = _make_df([2_000_000, 3_000_000])  # +50% — fanger >+40 → 1.0 high, 0.0 low
    assert fn(_MockStore({"sum": df}), "Coffee", {}) == 0.0


def test_flat_returns_neutral() -> None:
    """0% MoM = nøytral → 0.5 begge konvensjoner."""
    fn = get("cecafe_export_change")
    df = _make_df([3_000_000, 3_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {}) == 0.5


def test_bull_when_high_inverts() -> None:
    """-50% MoM med bull_when=high → 0.0 (eksport-fall = bear i high-konv)."""
    fn = get("cecafe_export_change")
    df = _make_df([4_000_000, 2_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {"bull_when": "high"}) == 0.0


def test_no_data_returns_zero() -> None:
    fn = get("cecafe_export_change")
    assert fn(_MockStore({}), "Coffee", {}) == 0.0


def test_single_observation_returns_neutral() -> None:
    """Med kun én obs kan ikke MoM beregnes — neutral."""
    fn = get("cecafe_export_change")
    df = _make_df([3_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {}) == 0.5


def test_zero_prev_returns_neutral() -> None:
    """Edge: forrige måned = 0 (uregelmessighet) → neutral."""
    fn = get("cecafe_export_change")
    df = _make_df([0, 3_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {}) == 0.5


def test_coffee_type_arabica_param() -> None:
    """coffee_type='arabica' overstyrer default sum."""
    fn = get("cecafe_export_change")
    df_arabica = _make_df([2_500_000, 1_500_000])  # -40% i arabica → 1.0 low_bull
    df_arabica["coffee_type"] = ["arabica"] * len(df_arabica)
    out = fn(_MockStore({"arabica": df_arabica}), "Coffee", {"coffee_type": "arabica"})
    assert out == 1.0


def test_mode_pct_12m_dispatched() -> None:
    """pct_12m-mode returnerer noe i [0, 1]."""
    fn = get("cecafe_export_change")
    # 30 måneder med varierende volum
    volumes = [3_000_000 + 200_000 * (i % 6) for i in range(30)]
    df = _make_df(volumes, start="2023-01-01")
    out = fn(_MockStore({"sum": df}), "Coffee", {"mode": "pct_12m"})
    assert 0.0 <= out <= 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    fn = get("cecafe_export_change")
    df = _make_df([4_000_000, 2_000_000])
    assert fn(_MockStore({"sum": df}), "Coffee", {"mode": "made_up"}) == 1.0


def test_custom_thresholds() -> None:
    fn = get("cecafe_export_change")
    # 3M → 2.85M = -5% MoM
    df = _make_df([3_000_000, 2_850_000])
    # Custom: -10 → 0.0, 0 → 0.5, 10 → 1.0; -5% → fanger ved 0 → 0.5 i high-konv
    # → 0.5 i low-konv (symmetri)
    custom = [(-10.0, 0.0), (0.0, 0.5), (10.0, 1.0)]
    out = fn(_MockStore({"sum": df}), "Coffee", {"thresholds": custom})
    assert out == 0.5


def test_extreme_flag_hard_dispatched() -> None:
    """extreme_flag_hard returnerer 0.0 eller 1.0."""
    fn = get("cecafe_export_change")
    volumes = [3_000_000 + 200_000 * (i % 6) for i in range(30)]
    df = _make_df(volumes, start="2023-01-01")
    out = fn(_MockStore({"sum": df}), "Coffee", {"mode": "extreme_flag_hard"})
    assert out in (0.0, 1.0)
