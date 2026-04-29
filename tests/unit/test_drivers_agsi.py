"""Tester for ``agsi_storage_pct``-driver (sub-fase 12.7 D1 A2, session 130).

Bruker in-memory mock-store; ingen ekte AGSI API-kall. Dekker default-mode
+ mode-dispatch + ``bull_when``-konfigurasjoner + edge-cases.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockStore:
    """Stub som returnerer pd.DataFrame for AGSI-storage."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames

    def get_agsi_storage(self, country: str, last_n: int | None = None) -> pd.DataFrame:
        key = country.lower()
        if key not in self._frames:
            raise KeyError(f"No AGSI data for country={key!r}")
        df = self._frames[key]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _make_df(values: list[float], start: str = "2024-01-01", country: str = "eu") -> pd.DataFrame:
    """Bygg AGSI-DF med daglig consumption_full_pct."""
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "country": country,
            "gas_day_start": idx,
            "consumption_full_pct": values,
            "gas_in_storage_twh": [v * 11.0 for v in values],
            "working_gas_volume_twh": [1100.0] * len(values),
        }
    )


# ---------------------------------------------------------------------------
# Default mode
# ---------------------------------------------------------------------------


def test_low_storage_returns_max_score_for_low_bull() -> None:
    """15% full = energy-crisis-territorium → 1.0 for bull_when=low."""
    store = _MockStore({"eu": _make_df([15.0])})
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {}) == 1.0


def test_high_storage_returns_low_score_for_low_bull() -> None:
    """90% full → 0.1 (bear NG-pris, sterk supply)."""
    store = _MockStore({"eu": _make_df([90.0])})
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {}) == 0.1


def test_neutral_storage_returns_neutral() -> None:
    """50% full = nøytral-sone → 0.5."""
    store = _MockStore({"eu": _make_df([50.0])})
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {}) == 0.5


def test_high_bull_inverts_for_contrarian() -> None:
    """bull_when='high': lav storage = bear (kontrært)."""
    store = _MockStore({"eu": _make_df([15.0])})
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"bull_when": "high"})
    # 15% → low-score=1.0 → invertert = 0.0
    assert score == 0.0


def test_per_country_param() -> None:
    """country-param: hent fra DE i stedet for default eu."""
    store = _MockStore(
        {
            "eu": _make_df([50.0], country="eu"),
            "de": _make_df([15.0], country="de"),
        }
    )
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"country": "de"})
    assert score == 1.0


def test_missing_country_returns_zero() -> None:
    store = _MockStore({})
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {"country": "xx"}) == 0.0


def test_empty_df_returns_zero() -> None:
    store = _MockStore(
        {"eu": pd.DataFrame(columns=["country", "gas_day_start", "consumption_full_pct"])}
    )
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {}) == 0.0


def test_all_nan_consumption_returns_zero() -> None:
    df = _make_df([50.0, 50.0])
    df["consumption_full_pct"] = [None, None]
    store = _MockStore({"eu": df})
    fn = get("agsi_storage_pct")
    assert fn(store, "NaturalGas", {}) == 0.0


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def test_pct_12m_mode_returns_score() -> None:
    """pct_12m mode: current på top → bull_when=low → ≈ 0.0."""
    values = [50.0 + i * 0.05 for i in range(300)]  # monotonically increasing
    store = _MockStore({"eu": _make_df(values)})
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"mode": "pct_12m"})
    assert 0.0 <= score <= 0.1


def test_delta_5d_z_with_oscillation() -> None:
    """delta_5d_z: oscillerende serie gir gyldig 0..1."""
    import math

    values = [50.0 + 5.0 * math.sin(i * 0.5) for i in range(300)]
    store = _MockStore({"eu": _make_df(values)})
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"mode": "delta_5d_z"})
    assert 0.0 <= score <= 1.0


def test_extreme_flag_hard_at_top() -> None:
    """Extreme-flag-hard: outlier i topp → 1.0 (symmetrisk)."""
    values = [50.0] * 299 + [99.0]  # outlier
    store = _MockStore({"eu": _make_df(values)})
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"mode": "extreme_flag_hard"})
    assert score == 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    store = _MockStore({"eu": _make_df([15.0])})
    fn = get("agsi_storage_pct")
    score = fn(store, "NaturalGas", {"mode": "garbage_mode"})
    assert score == 1.0  # default på 15% = max bull
