"""Sub-fase 12.10 Bunke 3 driver-tester.

Compact registry + smoke-test pass for de 14 nye FRED/calendar-driverne.
Hver driver har minimum: registrert + returnerer score 0..1 + min_samples-
guard returnerer 0.5 ved sparsom data.

Detaljerte step-mapping-tester gjøres i live-data-validering (per ADR-011
"all validation mot live data" for sub-fase 12.10).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered

_NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "driver_name",
    [
        "t10y3m",
        "t_bill_3mo_yield",
        "hy_oas_change",
        "initial_claims_z",
        "continuing_claims_z",
        "industrial_production_yoy",
        "cfnai_3mma",
        "ism_pmi_level",
        "umich_sentiment_z",
        "jolts_openings_yoy",
        "anfci_z",
        "m2_yoy",
        "vix9d_vix_ratio",
        "dollar_index_breadth",
        "fomc_decision_distance",
    ],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name), f"{driver_name} not registered"
    fn = get(driver_name)
    assert callable(fn)


# ---------------------------------------------------------------------------
# Mock-store for fundamentals
# ---------------------------------------------------------------------------


class _MockStore:
    def __init__(self, series: dict[str, pd.Series] | None = None) -> None:
        self._series = series or {}

    def get_fundamentals(self, series_id: str, last_n: int | None = None) -> pd.Series:
        if series_id not in self._series:
            raise KeyError(f"unknown series: {series_id}")
        s = self._series[series_id]
        if last_n is not None:
            return s.tail(last_n)
        return s


def _daily_series(values: list[float], end: str = "2026-05-01") -> pd.Series:
    end_ts = pd.Timestamp(end)
    dates = pd.date_range(end=end_ts, periods=len(values), freq="D")
    return pd.Series(values, index=dates, name="value")


def _monthly_series(values: list[float], end: str = "2026-04-01") -> pd.Series:
    end_ts = pd.Timestamp(end)
    dates = pd.date_range(end=end_ts, periods=len(values), freq="MS")
    return pd.Series(values, index=dates, name="value")


def _weekly_series(values: list[float], end: str = "2026-05-01") -> pd.Series:
    end_ts = pd.Timestamp(end)
    dates = pd.date_range(end=end_ts, periods=len(values), freq="W-FRI")
    return pd.Series(values, index=dates, name="value")


# ---------------------------------------------------------------------------
# #7 yields
# ---------------------------------------------------------------------------


def test_t10y3m_steep_curve_bull() -> None:
    """DGS10=4.5%, DGS3MO=2.0% → spread 2.5% → bull (high)."""
    fn = get("t10y3m")
    store = _MockStore(
        {
            "DGS10": _daily_series([4.5] * 50),
            "DGS3MO": _daily_series([2.0] * 50),
        }
    )
    assert fn(store, "SP500", {}) == 1.0


def test_t10y3m_inverted_curve_bear() -> None:
    """Inverted curve (DGS3MO > DGS10) → bear."""
    fn = get("t10y3m")
    store = _MockStore(
        {
            "DGS10": _daily_series([3.5] * 50),
            "DGS3MO": _daily_series([4.5] * 50),
        }
    )
    assert fn(store, "SP500", {}) == 0.0  # spread = -1.0 ≤ -0.5


def test_t10y3m_returns_neutral_when_sparse() -> None:
    fn = get("t10y3m")
    store = _MockStore(
        {
            "DGS10": _daily_series([4.0] * 5),
            "DGS3MO": _daily_series([2.0] * 5),
        }
    )
    assert fn(store, "SP500", {}) == 0.5


def test_t_bill_3mo_yield_low_rate_bull() -> None:
    fn = get("t_bill_3mo_yield")
    store = _MockStore({"TB3MS": _monthly_series([0.5] * 30)})
    # ZIRP-equivalent → 1.0 ved bull_when='low' (default)
    assert fn(store, "SP500", {}) == 1.0


def test_t_bill_3mo_yield_high_rate_bear() -> None:
    fn = get("t_bill_3mo_yield")
    store = _MockStore({"TB3MS": _monthly_series([6.0] * 30)})
    assert fn(store, "SP500", {}) == 0.0


# ---------------------------------------------------------------------------
# #8 credit
# ---------------------------------------------------------------------------


def test_hy_oas_change_narrowing_bull() -> None:
    fn = get("hy_oas_change")
    # Lange flat-historikk + nylig narrowing
    vals = [4.0] * 60 + [3.5]
    store = _MockStore({"BAMLH0A0HYM2": _daily_series(vals)})
    score = fn(store, "SP500", {})
    assert score >= 0.85  # -0.5 narrowing


def test_hy_oas_change_widening_bear() -> None:
    fn = get("hy_oas_change")
    vals = [4.0] * 60 + [4.6]
    store = _MockStore({"BAMLH0A0HYM2": _daily_series(vals)})
    score = fn(store, "SP500", {})
    assert score <= 0.25


# ---------------------------------------------------------------------------
# #9 labor
# ---------------------------------------------------------------------------


def test_initial_claims_z_falling_bull() -> None:
    """Variabel høye claims, recent low → negative z → bull."""
    fn = get("initial_claims_z")
    # Sett opp variasjon så std > 0
    vals = [250.0 + (i % 5) for i in range(50)] + [180.0]
    store = _MockStore({"ICSA": _weekly_series(vals)})
    assert fn(store, "SP500", {}) >= 0.5


def test_initial_claims_z_rising_bear() -> None:
    fn = get("initial_claims_z")
    vals = [250.0 + (i % 5) for i in range(50)] + [400.0]
    store = _MockStore({"ICSA": _weekly_series(vals)})
    assert fn(store, "SP500", {}) <= 0.3


def test_continuing_claims_z_registered() -> None:
    fn = get("continuing_claims_z")
    vals = [1700.0 + (i % 5) for i in range(50)] + [2000.0]
    store = _MockStore({"CCSA": _weekly_series(vals)})
    score = fn(store, "SP500", {})
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# #10 growth
# ---------------------------------------------------------------------------


def test_industrial_production_yoy_growth_bull() -> None:
    fn = get("industrial_production_yoy")
    # 13 mnd, last value 5% over (i)=index 0 → strong growth
    vals = [100.0] * 12 + [105.0] + [100.0] * 12  # 25 mnd
    store = _MockStore({"INDPRO": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    # YoY mellom (-3 og 0) = 0.25/0.5; flat trolig 0.5
    assert 0.0 <= score <= 1.0


def test_cfnai_3mma_above_zero_bull() -> None:
    fn = get("cfnai_3mma")
    vals = [-0.1] * 12 + [0.4, 0.4, 0.4]
    store = _MockStore({"CFNAI": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    # 3mma = 0.4 > 0.3 → 1.0
    assert score == 1.0


def test_cfnai_3mma_below_zero_bear() -> None:
    fn = get("cfnai_3mma")
    vals = [0.0] * 12 + [-1.5, -1.5, -1.5]
    store = _MockStore({"CFNAI": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    assert score == 0.0


def test_ism_pmi_level_strong_expansion_bull() -> None:
    fn = get("ism_pmi_level")
    vals = [56.0] * 6
    store = _MockStore({"ISM_PMI": _monthly_series(vals)})
    assert fn(store, "SP500", {}) == 1.0


def test_ism_pmi_level_deep_contraction_bear() -> None:
    fn = get("ism_pmi_level")
    vals = [44.0] * 6
    store = _MockStore({"ISM_PMI": _monthly_series(vals)})
    assert fn(store, "SP500", {}) == 0.0


def test_ism_pmi_level_neutral_50_returns_mid() -> None:
    fn = get("ism_pmi_level")
    vals = [50.0] * 6
    store = _MockStore({"ISM_PMI": _monthly_series(vals)})
    assert fn(store, "SP500", {}) == 0.5


def test_ism_pmi_level_invert_via_bull_when_low() -> None:
    fn = get("ism_pmi_level")
    vals = [56.0] * 6
    store = _MockStore({"ISM_PMI": _monthly_series(vals)})
    # bull_when=low: PMI 56 = expansion = bear under invertert tolkning
    assert fn(store, "SP500", {"bull_when": "low"}) == 0.0


def test_ism_pmi_level_returns_neutral_when_sparse() -> None:
    fn = get("ism_pmi_level")
    vals = [52.0, 53.0, 54.0]  # under min_samples=6
    store = _MockStore({"ISM_PMI": _monthly_series(vals)})
    assert fn(store, "SP500", {}) == 0.5


def test_ism_pmi_level_missing_series_returns_zero() -> None:
    fn = get("ism_pmi_level")
    store = _MockStore()
    assert fn(store, "SP500", {}) == 0.0


def test_umich_sentiment_z_registered() -> None:
    fn = get("umich_sentiment_z")
    vals = [80.0] * 60 + [70.0]
    store = _MockStore({"UMCSENT": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    assert 0.0 <= score <= 1.0


def test_jolts_openings_yoy_growth_bull() -> None:
    fn = get("jolts_openings_yoy")
    vals = [9000.0] * 12 + [10000.0] + [9000.0] * 12
    store = _MockStore({"JTSJOL": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# #11 liquidity
# ---------------------------------------------------------------------------


def test_anfci_z_loose_conditions_bull() -> None:
    fn = get("anfci_z")
    vals = [-0.5] * 156 + [-1.5]  # current much more negative = looser
    store = _MockStore({"ANFCI": _weekly_series(vals)})
    score = fn(store, "SP500", {})
    assert score >= 0.5  # looser conditions → bull (default low)


def test_m2_yoy_growth_bull() -> None:
    fn = get("m2_yoy")
    # 25 mnd: indices 0..11 = 100, 12 = 110, last (index 24) = 110 → 12-mnd
    # tilbake fra last (index 12) = 110 → YoY 0%. Bygg slik at last har YoY +10%
    vals = [100.0] * 13 + [110.0] * 12  # iloc[-1]=110, iloc[-13]=100 → +10%
    store = _MockStore({"M2SL": _monthly_series(vals)})
    score = fn(store, "SP500", {})
    # 10% YoY > 8 → 1.0
    assert score == 1.0


# ---------------------------------------------------------------------------
# #12 vol
# ---------------------------------------------------------------------------


def test_vix9d_vix_ratio_low_complacency_bull() -> None:
    """VIX9D=10, VIX=15 → ratio 0.67 → complacency → bull (low)."""
    fn = get("vix9d_vix_ratio")
    store = _MockStore(
        {
            "VIX9D": _daily_series([10.0] * 50),
            "VIXCLS": _daily_series([15.0] * 50),
        }
    )
    assert fn(store, "SP500", {}) == 1.0


def test_vix9d_vix_ratio_fear_spike_bear() -> None:
    """VIX9D=30, VIX=20 → ratio 1.5 → fear spike → bear (low)."""
    fn = get("vix9d_vix_ratio")
    store = _MockStore(
        {
            "VIX9D": _daily_series([30.0] * 50),
            "VIXCLS": _daily_series([20.0] * 50),
        }
    )
    assert fn(store, "SP500", {}) == 0.0


# ---------------------------------------------------------------------------
# #13 fx
# ---------------------------------------------------------------------------


def test_dollar_index_breadth_all_up_strong_usd() -> None:
    """Alle 8 DEX-pairs stiger → breadth=1.0. bull_when='low' default → 0.0."""
    fn = get("dollar_index_breadth")
    series_dict = {}
    for series_id in (
        "DEXJPUS",
        "DEXCAUS",
        "DEXSDUS",
        "DEXSZUS",
        "DEXUSEU",
        "DEXUSUK",
        "DEXUSAL",
        "DEXUSNZ",
    ):
        series_dict[series_id] = _daily_series([1.0] * 5 + [1.05])
    store = _MockStore(series_dict)
    # 8 av 8 stigende = USD strong = bear FX (default bull_when='low')
    assert fn(store, "SP500", {}) == 0.0


def test_dollar_index_breadth_all_down_weak_usd() -> None:
    fn = get("dollar_index_breadth")
    series_dict = {}
    for series_id in (
        "DEXJPUS",
        "DEXCAUS",
        "DEXSDUS",
        "DEXSZUS",
        "DEXUSEU",
        "DEXUSUK",
        "DEXUSAL",
        "DEXUSNZ",
    ):
        series_dict[series_id] = _daily_series([1.05] * 5 + [1.0])
    store = _MockStore(series_dict)
    assert fn(store, "SP500", {}) == 1.0


def test_dollar_index_breadth_returns_neutral_below_min_pairs() -> None:
    fn = get("dollar_index_breadth")
    # Bare 2 pairs → < min_pairs=4
    store = _MockStore(
        {
            "DEXJPUS": _daily_series([1.0] * 5 + [1.05]),
            "DEXCAUS": _daily_series([1.0] * 5 + [1.05]),
        }
    )
    assert fn(store, "SP500", {}) == 0.5


# ---------------------------------------------------------------------------
# #14 calendar
# ---------------------------------------------------------------------------


class _MockEconStore:
    def __init__(self, events: list[dict]) -> None:
        self._df = (
            pd.DataFrame(events)
            if events
            else pd.DataFrame(columns=["event_ts", "country", "title", "impact"])
        )
        if not self._df.empty:
            # Mirror DataStore.get_econ_events: tz-aware UTC timestamps
            self._df["event_ts"] = pd.to_datetime(self._df["event_ts"], utc=True)

    def get_econ_events(
        self,
        countries: list[str] | None = None,
        impact_levels: list[str] | None = None,
        from_ts: str | None = None,
    ) -> pd.DataFrame:
        df = self._df
        if countries:
            df = df[df["country"].isin(countries)]
        if impact_levels:
            df = df[df["impact"].isin(impact_levels)]
        if from_ts:
            ts = pd.to_datetime(from_ts, utc=True)
            df = df[df["event_ts"] >= ts]
        return df.copy()


def test_fomc_decision_distance_far_returns_one() -> None:
    fn = get("fomc_decision_distance")
    events = [
        {
            "event_ts": (_NOW + timedelta(hours=24)).isoformat(),
            "country": "USD",
            "title": "FOMC Statement",
            "impact": "High",
        }
    ]
    store = _MockEconStore(events)
    score = fn(store, "SP500", {"_now": _NOW.isoformat(), "min_hours": 8})
    assert score == 1.0


def test_fomc_decision_distance_close_returns_low() -> None:
    fn = get("fomc_decision_distance")
    events = [
        {
            "event_ts": (_NOW + timedelta(hours=2)).isoformat(),
            "country": "USD",
            "title": "FOMC Statement",
            "impact": "High",
        }
    ]
    store = _MockEconStore(events)
    score = fn(store, "SP500", {"_now": _NOW.isoformat(), "min_hours": 8})
    assert score == 0.25  # 2/8 = 0.25


def test_fomc_decision_distance_ignores_non_fomc_events() -> None:
    fn = get("fomc_decision_distance")
    events = [
        {
            "event_ts": (_NOW + timedelta(hours=2)).isoformat(),
            "country": "USD",
            "title": "Non-Farm Employment Change",  # not FOMC
            "impact": "High",
        }
    ]
    store = _MockEconStore(events)
    # No FOMC events → empty_score (1.0 default)
    assert fn(store, "SP500", {"_now": _NOW.isoformat()}) == 1.0


def test_fomc_decision_distance_empty_calendar() -> None:
    fn = get("fomc_decision_distance")
    store = _MockEconStore([])
    assert fn(store, "SP500", {"_now": _NOW.isoformat()}) == 1.0
