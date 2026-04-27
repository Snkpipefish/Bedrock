# pyright: reportAttributeAccessIssue=false, reportReturnType=false
"""Tester for ``mining_disruption`` driver (sub-fase 12.5+ session 109)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockSeismicStore:
    """Returnerer pre-bygde DataFrames; støtter samme filtrerings-API."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_seismic_events(
        self,
        *,
        region=None,
        regions=None,
        from_ts=None,
        min_magnitude=None,
    ) -> pd.DataFrame:
        out = self._df.copy()
        if region is not None:
            out = out[out["region"] == region]
        elif regions:
            out = out[out["region"].isin(regions)]
        if from_ts is not None:
            out = out[out["event_ts"] >= from_ts]
        if min_magnitude is not None:
            out = out[out["magnitude"] >= min_magnitude]
        return out.reset_index(drop=True)


def _ev(
    *,
    event_id: str = "us_001",
    days_ago: int = 1,
    magnitude: float = 5.0,
    region: str = "Chile / Peru",
) -> dict:
    return {
        "event_id": event_id,
        "event_ts": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "magnitude": magnitude,
        "latitude": -23.5,
        "longitude": -70.4,
        "depth_km": 30.0,
        "place": "test",
        "region": region,
        "url": "https://x",
    }


def _df(events: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(events)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("mining_disruption") is not None


# ---------------------------------------------------------------------------
# Score-formel
# ---------------------------------------------------------------------------


def test_no_events_returns_zero() -> None:
    """Ingen events → score 0.0 (defensiv default = ingen disruption-risk)."""
    store = _MockSeismicStore(_df([]))
    fn = get("mining_disruption")
    assert fn(store, "Gold", {"metal": "gold"}) == 0.0


def test_m45_event_gives_zero_impact() -> None:
    """M4.5 er nedre grense → impact = 0."""
    store = _MockSeismicStore(_df([_ev(magnitude=4.5)]))
    fn = get("mining_disruption")
    score = fn(store, "Gold", {"metal": "gold"})
    assert score == 0.0


def test_m6_chile_event_for_copper() -> None:
    """M6.0 i Chile/Peru for kobber: impact = 1.5/3.0 = 0.5; weight = 0.40 → 0.2."""
    store = _MockSeismicStore(_df([_ev(magnitude=6.0, region="Chile / Peru")]))
    fn = get("mining_disruption")
    score = fn(store, "Copper", {"metal": "copper"})
    # 0.5 * 0.40 = 0.20
    assert abs(score - 0.20) < 0.001


def test_m6_south_africa_for_platinum_huge_impact() -> None:
    """M6 i Sør-Afrika for platinum: impact 0.5 × weight 0.70 = 0.35."""
    store = _MockSeismicStore(_df([_ev(magnitude=6.0, region="Sør-Afrika")]))
    fn = get("mining_disruption")
    score = fn(store, "Platinum", {"metal": "platinum"})
    # 0.5 * 0.70 = 0.35
    assert abs(score - 0.35) < 0.001


def test_m75_caps_at_1() -> None:
    """M7.5 i Sør-Afrika for platinum: impact 1.0 × weight 0.70 = 0.70."""
    store = _MockSeismicStore(_df([_ev(magnitude=7.5, region="Sør-Afrika")]))
    fn = get("mining_disruption")
    score = fn(store, "Platinum", {"metal": "platinum"})
    assert abs(score - 0.70) < 0.001


def test_score_clamped_at_1() -> None:
    """Mange store skjelv på samme region → score capped på 1.0."""
    events = [_ev(event_id=f"e_{i}", magnitude=7.5, region="Sør-Afrika") for i in range(5)]
    store = _MockSeismicStore(_df(events))
    fn = get("mining_disruption")
    score = fn(store, "Platinum", {"metal": "platinum"})
    assert score == 1.0


def test_multiple_regions_summed() -> None:
    """M6 i Chile + M6 i DRC for kobber: 0.5*0.40 + 0.5*0.15 = 0.275."""
    events = [
        _ev(event_id="chile", magnitude=6.0, region="Chile / Peru"),
        _ev(event_id="drc", magnitude=6.0, region="DRC / Zambia"),
    ]
    store = _MockSeismicStore(_df(events))
    fn = get("mining_disruption")
    score = fn(store, "Copper", {"metal": "copper"})
    assert abs(score - 0.275) < 0.001


# ---------------------------------------------------------------------------
# Region-vekt-mapping per metall
# ---------------------------------------------------------------------------


def test_event_in_irrelevant_region_ignored_for_metal() -> None:
    """M6 i DRC for platinum (DRC ikke i platinum-vekt-mapping) → 0."""
    store = _MockSeismicStore(_df([_ev(magnitude=6.0, region="DRC / Zambia")]))
    fn = get("mining_disruption")
    score = fn(store, "Platinum", {"metal": "platinum"})
    assert score == 0.0


def test_chile_huge_impact_for_copper_minor_for_gold() -> None:
    """Chile er 40% kobber-mining men kun ~10% av gull-mining."""
    store = _MockSeismicStore(_df([_ev(magnitude=6.0, region="Chile / Peru")]))
    fn = get("mining_disruption")
    copper_score = fn(store, "Copper", {"metal": "copper"})
    gold_score = fn(store, "Gold", {"metal": "gold"})
    assert copper_score > gold_score


# ---------------------------------------------------------------------------
# Lookback
# ---------------------------------------------------------------------------


def test_old_events_excluded() -> None:
    """Events > lookback_days droppes via from_ts-filter."""
    events = [
        _ev(event_id="recent", days_ago=2, magnitude=6.0, region="Chile / Peru"),
        _ev(event_id="old", days_ago=30, magnitude=7.0, region="Chile / Peru"),
    ]
    store = _MockSeismicStore(_df(events))
    fn = get("mining_disruption")
    score = fn(store, "Copper", {"metal": "copper", "lookback_days": 7})
    # Kun "recent" bidrar: 0.5 * 0.40 = 0.20
    assert abs(score - 0.20) < 0.001


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_metal_missing() -> None:
    fn = get("mining_disruption")
    assert fn(_MockSeismicStore(_df([])), "Gold", {}) == 0.0


def test_returns_zero_for_unknown_metal() -> None:
    fn = get("mining_disruption")
    assert fn(_MockSeismicStore(_df([])), "Plutonium", {"metal": "plutonium"}) == 0.0


def test_returns_zero_when_store_raises() -> None:
    class _Broken:
        def get_seismic_events(self, **kwargs):
            raise RuntimeError("DB error")

    fn = get("mining_disruption")
    assert fn(_Broken(), "Gold", {"metal": "gold"}) == 0.0


# ---------------------------------------------------------------------------
# Custom regions override
# ---------------------------------------------------------------------------


def test_custom_regions_override() -> None:
    """YAML-override av region-vekter virker."""
    store = _MockSeismicStore(_df([_ev(magnitude=6.0, region="Antarktis")]))
    fn = get("mining_disruption")
    # Default: ingen "Antarktis" i mappingen → 0
    score_default = fn(store, "Gold", {"metal": "gold"})
    assert score_default == 0.0

    # Override: Antarktis 100% av "gold"-vekt → 0.5
    score_custom = fn(store, "Gold", {"metal": "gold", "regions": {"Antarktis": 1.0}})
    assert abs(score_custom - 0.5) < 0.001


# ---------------------------------------------------------------------------
# min_magnitude param
# ---------------------------------------------------------------------------


def test_min_magnitude_filter() -> None:
    """min_magnitude=6.0 ekskluderer M5 events."""
    events = [
        _ev(event_id="m5", magnitude=5.0, region="Chile / Peru"),
        _ev(event_id="m6", magnitude=6.0, region="Chile / Peru"),
    ]
    store = _MockSeismicStore(_df(events))
    fn = get("mining_disruption")
    # Med default min_magnitude=4.5: begge teller; med 6.0 kun den ene.
    s_low = fn(store, "Copper", {"metal": "copper"})
    s_high = fn(store, "Copper", {"metal": "copper", "min_magnitude": 6.0})
    assert s_high < s_low
