# pyright: reportArgumentType=false
"""Tester for ALSI + IIP drivere (sub-fase 12.10 follow-up Spor C, session 136)."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered


@pytest.mark.parametrize(
    "driver_name",
    ["alsi_eu_pct", "alsi_storage_change", "iip_supply_unavailability"],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name)
    assert callable(get(driver_name))


# ---------------------------------------------------------------------------
# alsi_eu_pct
# ---------------------------------------------------------------------------


class _AlsiStore:
    """In-memory ALSI-store-stub for driver-tester."""

    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df

    def get_alsi_storage(self, country: str, last_n: int | None = None) -> pd.DataFrame:
        if self._df is None:
            raise KeyError(country)
        return self._df.copy()


def _alsi_df(full_pcts: list[float]) -> pd.DataFrame:
    n = len(full_pcts)
    dates = pd.date_range("2026-04-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "country": ["eu"] * n,
            "gas_day_start": dates,
            "inventory_twh": [p / 100.0 * 62.0 for p in full_pcts],
            "dtmi_twh": [62.0] * n,
            "full_pct": full_pcts,
            "send_out_twh": [4.0] * n,
            "dtrs_twh": [7.9] * n,
        }
    )


def test_alsi_eu_pct_low_full_returns_high_score() -> None:
    """bull_when='low' (default): lav fyllingsgrad = bull NG = høy score."""
    fn = get("alsi_eu_pct")
    score = fn(_AlsiStore(_alsi_df([10.0, 12.0, 14.0])), "NaturalGas", {})
    # 14 ≤ 15 → 1.0
    assert score == 1.0


def test_alsi_eu_pct_high_full_returns_low_score() -> None:
    fn = get("alsi_eu_pct")
    score = fn(_AlsiStore(_alsi_df([78.0, 80.0, 85.0])), "NaturalGas", {})
    # 85 → > 75% i siste step → 0.1
    assert score == 0.1


def test_alsi_eu_pct_neutral_range() -> None:
    fn = get("alsi_eu_pct")
    score = fn(_AlsiStore(_alsi_df([45.0])), "NaturalGas", {})
    # 45% → 30-55% → 0.5
    assert score == 0.5


def test_alsi_eu_pct_bull_when_high_inverts() -> None:
    fn = get("alsi_eu_pct")
    score_low = fn(_AlsiStore(_alsi_df([10.0])), "NaturalGas", {"bull_when": "low"})
    score_high = fn(_AlsiStore(_alsi_df([10.0])), "NaturalGas", {"bull_when": "high"})
    assert score_low == 1.0
    assert score_high == 0.0


def test_alsi_eu_pct_no_data_returns_zero() -> None:
    fn = get("alsi_eu_pct")
    assert fn(_AlsiStore(None), "NaturalGas", {}) == 0.0


def test_alsi_eu_pct_empty_df_returns_zero() -> None:
    fn = get("alsi_eu_pct")
    empty = pd.DataFrame(
        columns=[
            "country",
            "gas_day_start",
            "inventory_twh",
            "dtmi_twh",
            "full_pct",
            "send_out_twh",
            "dtrs_twh",
        ]
    )
    assert fn(_AlsiStore(empty), "NaturalGas", {}) == 0.0


def test_alsi_eu_pct_country_param_propagates() -> None:
    """Driver kaller store.get_alsi_storage med valgt country."""
    captured: dict = {}

    class _Stub:
        def get_alsi_storage(self, country: str, last_n: int | None = None):
            captured["country"] = country
            return _alsi_df([50.0])

    fn = get("alsi_eu_pct")
    fn(_Stub(), "NaturalGas", {"country": "de"})
    assert captured["country"] == "de"


def test_alsi_eu_pct_user_thresholds_override() -> None:
    fn = get("alsi_eu_pct")
    custom = [(50.0, 1.0), (80.0, 0.5), (100.0, 0.0)]
    score = fn(
        _AlsiStore(_alsi_df([45.0])),
        "NaturalGas",
        {"thresholds": custom},
    )
    # 45 ≤ 50 → 1.0
    assert score == 1.0


# ---------------------------------------------------------------------------
# alsi_storage_change
# ---------------------------------------------------------------------------


def _alsi_inv_df(inventories: list[float]) -> pd.DataFrame:
    n = len(inventories)
    dates = pd.date_range("2026-04-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "country": ["eu"] * n,
            "gas_day_start": dates,
            "inventory_twh": inventories,
            "dtmi_twh": [62.0] * n,
            "full_pct": [(v / 62.0 * 100) for v in inventories],
            "send_out_twh": [4.0] * n,
            "dtrs_twh": [7.9] * n,
        }
    )


def test_alsi_storage_change_drawdown_high_score() -> None:
    """20% fall over 5 dager → -10%-step → 1.0 (bull_when='low' default)."""
    fn = get("alsi_storage_change")
    # 12 entries; sammenlign i=11 (20.0) vs i=6 (40.0). Pct change = -50%.
    invs = [40.0, 38.0, 36.0, 34.0, 32.0, 30.0, 40.0, 36.0, 32.0, 28.0, 24.0, 20.0]
    score = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {})
    assert score == 1.0


def _alsi_df_inv(inventories: list[float]) -> pd.DataFrame:
    """Wrapper rundt _alsi_inv_df for å unngå name shadowing."""
    return _alsi_inv_df(inventories)


def test_alsi_storage_change_refill_low_score() -> None:
    """20% økning over 5 dager → +5% step → 0.0."""
    fn = get("alsi_storage_change")
    invs = [20.0, 22.0, 24.0, 26.0, 28.0, 30.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0]
    score = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {})
    # +100% change, ≥ +5 → 0.0
    assert score == 0.0


def test_alsi_storage_change_neutral_when_flat() -> None:
    fn = get("alsi_storage_change")
    invs = [30.0] * 12
    score = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {})
    # 0% change → ≤ 0.0 step → 0.5 (neutral)
    assert score == 0.5


def test_alsi_storage_change_returns_neutral_when_too_few() -> None:
    fn = get("alsi_storage_change")
    invs = [30.0, 28.0]
    score = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {})
    assert score == 0.5


def test_alsi_storage_change_bull_when_high_inverts() -> None:
    fn = get("alsi_storage_change")
    invs = [40.0, 38.0, 36.0, 34.0, 32.0, 30.0, 40.0, 36.0, 32.0, 28.0, 24.0, 20.0]
    score_low = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {"bull_when": "low"})
    score_high = fn(_AlsiStore(_alsi_df_inv(invs)), "NaturalGas", {"bull_when": "high"})
    assert score_low == 1.0
    assert score_high == 0.0


def test_alsi_storage_change_no_data_returns_zero() -> None:
    fn = get("alsi_storage_change")
    assert fn(_AlsiStore(None), "NaturalGas", {}) == 0.0


# ---------------------------------------------------------------------------
# iip_supply_unavailability
# ---------------------------------------------------------------------------


class _IipStore:
    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df

    def get_iip_remit(
        self,
        *,
        balancing_zone_prefix: str | None = None,
        from_published_ts: str | None = None,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        if self._df is None:
            return pd.DataFrame()
        df = self._df.copy()
        if balancing_zone_prefix:
            df = df[
                df["balancing_zone_code"].str.upper().str.startswith(balancing_zone_prefix.upper())
            ]
        return df.reset_index(drop=True)


def _iip_event(
    msg_id: str,
    *,
    published: str,
    event_from: str,
    event_to: str,
    capacity_gwhd: float,
    zone: str = "21YNL----TTF---1",
    unavailability_type: str = "Planned",
) -> dict:
    return {
        "message_id": msg_id,
        "submitted_ts": pd.Timestamp(published),
        "published_ts": pd.Timestamp(published),
        "event_from_ts": pd.Timestamp(event_from),
        "event_to_ts": pd.Timestamp(event_to),
        "status": "Active",
        "message_type": "Gas storage facility unavailability",
        "unavailability_type": unavailability_type,
        "unavailability_reason": "maintenance",
        "unavailable_capacity_gwhd": capacity_gwhd,
        "available_capacity_gwhd": 100.0,
        "technical_capacity_gwhd": 500.0,
        "balancing_zone_code": zone,
        "balancing_zone_name": "Test Zone",
        "direction": "Exit",
        "asset_code": "X",
        "asset_name": "Y",
    }


def test_iip_neutral_when_no_data() -> None:
    """Tom DB → 0.5 (informasjons-fravær, ikke bear-signal)."""
    fn = get("iip_supply_unavailability")
    assert fn(_IipStore(None), "NaturalGas", {}) == 0.5


def test_iip_active_mode_high_capacity_high_score() -> None:
    """Aktive events ved as_of (siste pub-dato) > 5000 GWh/d → 1.0."""
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=3000.0,
            ),
            _iip_event(
                "M2",
                published="2026-04-30 13:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=2500.0,
            ),
        ]
    )
    score = fn(_IipStore(df), "NaturalGas", {})
    # Sum 5500 GWh/d > 5000 → 1.0
    assert score == 1.0


def test_iip_active_mode_low_capacity_low_score() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=200.0,
            ),
        ]
    )
    score = fn(_IipStore(df), "NaturalGas", {})
    # 200 ≤ 500 → 0.0
    assert score == 0.0


def test_iip_inactive_events_excluded() -> None:
    """Events som har sluttet før as_of skal ikke inkluderes i 'active' mode."""
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            # Avsluttet event
            _iip_event(
                "M1",
                published="2026-03-01 12:00",
                event_from="2026-03-01",
                event_to="2026-03-15",
                capacity_gwhd=10000.0,
            ),
            # Aktivt event ved as_of=2026-04-30
            _iip_event(
                "M2",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=300.0,
            ),
        ]
    )
    score = fn(_IipStore(df), "NaturalGas", {})
    # Kun M2 aktiv (300) → ≤500 → 0.0
    assert score == 0.0


def test_iip_recent_mode_uses_published_window() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            # Eldre event - innen 30d-vindu
            _iip_event(
                "M1",
                published="2026-04-15 12:00",
                event_from="2026-06-01",
                event_to="2026-06-15",
                capacity_gwhd=2000.0,
            ),
            # Nylig event
            _iip_event(
                "M2",
                published="2026-04-29 12:00",
                event_from="2026-06-01",
                event_to="2026-06-15",
                capacity_gwhd=1500.0,
            ),
        ]
    )
    score = fn(
        _IipStore(df),
        "NaturalGas",
        {"mode": "recent", "lookback_days": 30},
    )
    # Sum 3500 GWh/d → 2000-5000 step → 0.75
    assert score == 0.75


def test_iip_balancing_zone_filter() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=4000.0,
                zone="21YNL----TTF---1",
            ),
            _iip_event(
                "M2",
                published="2026-04-30 13:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=3000.0,
                zone="21Y100A1001A0612",
            ),
        ]
    )
    # Med NL-only filter → kun 4000 → 2000-5000 → 0.75
    score_nl = fn(
        _IipStore(df),
        "NaturalGas",
        {"balancing_zone_prefix": "21YNL"},
    )
    assert score_nl == 0.75
    # Uten filter → sum 7000 → > 5000 → 1.0
    score_all = fn(_IipStore(df), "NaturalGas", {})
    assert score_all == 1.0


def test_iip_unavailability_type_filter() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=4000.0,
                unavailability_type="Unplanned",
            ),
            _iip_event(
                "M2",
                published="2026-04-30 13:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=200.0,
                unavailability_type="Planned",
            ),
        ]
    )
    score = fn(
        _IipStore(df),
        "NaturalGas",
        {"unavailability_type": "Unplanned"},
    )
    # Kun Unplanned (4000) → 2000-5000 → 0.75
    assert score == 0.75


def test_iip_bull_when_low_inverts() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=10000.0,
            ),
        ]
    )
    score_high = fn(_IipStore(df), "NaturalGas", {"bull_when": "high"})
    score_low = fn(_IipStore(df), "NaturalGas", {"bull_when": "low"})
    assert score_high == 1.0
    assert score_low == 0.0


def test_iip_user_thresholds_override() -> None:
    fn = get("iip_supply_unavailability")
    df = pd.DataFrame(
        [
            _iip_event(
                "M1",
                published="2026-04-30 12:00",
                event_from="2026-04-29",
                event_to="2026-05-15",
                capacity_gwhd=600.0,
            ),
        ]
    )
    score = fn(
        _IipStore(df),
        "NaturalGas",
        {"thresholds": [(100.0, 0.0), (1000.0, 1.0)]},
    )
    # 600 ≤ 1000 → 1.0 (custom-step)
    assert score == 1.0
