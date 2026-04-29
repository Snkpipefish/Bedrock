"""Tester for ``fas_exports``-driver (sub-fase 12.7 D2 A3, session 133).

Bruker in-memory mock-store; ingen ekte FAS API-kall. Dekker default-mode +
mode-dispatch + ``bull_when``-konfigurasjoner + instrument-mapping +
edge-cases.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockStore:
    """Stub som returnerer pd.DataFrame for FAS ESR per commodity_code."""

    def __init__(self, frames: dict[int, pd.DataFrame]):
        self._frames = frames

    def get_fas_esr(
        self,
        commodity_code: int,
        *,
        country_code: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        if commodity_code not in self._frames:
            raise KeyError(f"No FAS ESR data for commodity_code={commodity_code}")
        return self._frames[commodity_code]


def _make_df(weekly_values: list[float], start: str = "2024-09-06") -> pd.DataFrame:
    """Bygg FAS ESR-aggregat-DF med ukentlig sum(weekly_exports)."""
    idx = pd.date_range(start, periods=len(weekly_values), freq="W-FRI")
    return pd.DataFrame(
        {
            "commodity_code": [401] * len(weekly_values),
            "market_year": [2024] * len(weekly_values),
            "week_ending_date": idx,
            "weekly_exports": weekly_values,
            "accumulated_exports": [sum(weekly_values[: i + 1]) for i in range(len(weekly_values))],
            "outstanding_sales": [v * 5 for v in weekly_values],
            "gross_new_sales": weekly_values,
            "current_my_net_sales": weekly_values,
            "current_my_total_commitment": [v * 6 for v in weekly_values],
            "next_my_outstanding_sales": [0.0] * len(weekly_values),
            "next_my_net_sales": [0.0] * len(weekly_values),
        }
    )


# ---------------------------------------------------------------------------
# Default mode — WoW step-trapp
# ---------------------------------------------------------------------------


def test_strong_wow_increase_returns_max_for_high_bull() -> None:
    """+30% WoW = sterk inflow → 1.0 for default bull_when=high."""
    df = _make_df([1000.0, 1300.0])  # +30% WoW
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {}) == 1.0


def test_strong_wow_decrease_returns_min_for_high_bull() -> None:
    """-30% WoW = sterk outflow → 0.0 for default bull_when=high."""
    df = _make_df([1000.0, 700.0])  # -30%
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {}) == 0.0


def test_flat_wow_returns_neutral() -> None:
    """0% WoW = 0.5 (nøytral)."""
    df = _make_df([1000.0, 1000.0])
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {}) == 0.5


def test_bull_when_low_inverts_score() -> None:
    """+30% WoW med bull_when=low → 0.0 (kontrært)."""
    df = _make_df([1000.0, 1300.0])
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {"bull_when": "low"}) == 0.0


def test_zero_previous_returns_neutral() -> None:
    """Forrige uke 0 export → 0.5 (MY-overgang-edge)."""
    df = _make_df([0.0, 1000.0])
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {}) == 0.5


def test_single_observation_returns_neutral() -> None:
    """Ikke nok historikk for WoW → 0.5."""
    df = _make_df([1000.0])
    fn = get("fas_exports")
    assert fn(_MockStore({401: df}), "Corn", {}) == 0.5


# ---------------------------------------------------------------------------
# Instrument-mapping
# ---------------------------------------------------------------------------


def test_instrument_to_commodity_code_mapping() -> None:
    """Soybean → 801, Wheat → 107, Cotton → 501."""
    fn = get("fas_exports")
    df_soy = _make_df([1000.0, 1300.0])
    df_soy["commodity_code"] = 801
    df_wht = _make_df([2000.0, 2600.0])
    df_wht["commodity_code"] = 107
    df_ctn = _make_df([300.0, 390.0])
    df_ctn["commodity_code"] = 501

    store = _MockStore({801: df_soy, 107: df_wht, 501: df_ctn})
    assert fn(store, "Soybean", {}) == 1.0
    assert fn(store, "Wheat", {}) == 1.0
    assert fn(store, "Cotton", {}) == 1.0


def test_unknown_instrument_returns_zero_defensive() -> None:
    """Instrument ikke i mapping → 0.0 (defensive)."""
    fn = get("fas_exports")
    assert fn(_MockStore({}), "Gold", {}) == 0.0


def test_explicit_commodity_code_override() -> None:
    """Eksplisitt commodity_code-param trumfer instrument-mapping."""
    df = _make_df([1000.0, 1300.0])
    df["commodity_code"] = 999
    fn = get("fas_exports")
    # Selv om "Gold" ikke er i mapping, override slår igjennom.
    assert fn(_MockStore({999: df}), "Gold", {"commodity_code": 999}) == 1.0


def test_no_data_returns_zero() -> None:
    """Mock-store kaster KeyError → driver returnerer 0.0."""
    fn = get("fas_exports")
    assert fn(_MockStore({}), "Corn", {}) == 0.0


# ---------------------------------------------------------------------------
# Mode-dispatch (R4)
# ---------------------------------------------------------------------------


def test_mode_pct_12m_dispatched() -> None:
    """pct_12m-mode må returnere noe i [0, 1] (ikke kaste)."""
    # 60+ ukentlige observasjoner — under DAILY-lookback men nok til at
    # _fundamentals_pct_score returnerer noe (kan også returnere None →
    # driver returnerer 0.0).
    weekly_values = [1000.0 + 10 * i for i in range(60)]
    df = _make_df(weekly_values)
    fn = get("fas_exports")
    out = fn(_MockStore({401: df}), "Corn", {"mode": "pct_12m"})
    assert 0.0 <= out <= 1.0


def test_unknown_mode_falls_back_to_default() -> None:
    """Ukjent mode logges + faller tilbake til default-trapp."""
    df = _make_df([1000.0, 1300.0])
    fn = get("fas_exports")
    # Ukjent mode → samme som default → 1.0 ved +30% WoW.
    assert fn(_MockStore({401: df}), "Corn", {"mode": "made_up"}) == 1.0


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds_override_default() -> None:
    """Bruker-supplerte terskler overstyrer."""
    df = _make_df([1000.0, 1010.0])  # +1% WoW
    fn = get("fas_exports")
    custom = [(-1.0, 0.0), (1.0, 0.5), (3.0, 1.0)]
    # +1% WoW → fanger ved threshold=1.0 → 0.5
    assert fn(_MockStore({401: df}), "Corn", {"thresholds": custom}) == 0.5
