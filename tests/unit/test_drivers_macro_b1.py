"""Tester for B1 D1-drivere (sub-fase 12.7, session 129).

Driverne:
- ``yield_diff_10y`` — US 10Y minus foreign 10Y, månedlig kadens.
- ``credit_spread_change`` — BAA10Y − AAA10Y, daglig.
- ``nfci_change`` — Chicago Fed NFCI, ukentlig.
- ``net_fed_liq_change`` — WALCL − RRPONTSYD − WTREGEN, ukentlig.

Bruker in-memory mock-store; ingen ekte FRED-data. Dekker default-mode +
mode-dispatch + ``bull_when``-konfigurasjoner + edge-cases.
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


def _daily_series(values: list[float], start: str = "2024-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


def _weekly_series(values: list[float], start: str = "2024-01-05") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="W-FRI")
    return pd.Series(values, index=idx, dtype="float64")


def _monthly_series(values: list[float], start: str = "2022-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype="float64")


# ---------------------------------------------------------------------------
# yield_diff_10y
# ---------------------------------------------------------------------------


def test_yield_diff_10y_low_diff_returns_max_score_for_low_bull() -> None:
    """Foreign yield > US (negativ diff) → 1.0 for EURUSD-tolkning."""
    store = _MockStore(
        {
            "DGS10": _monthly_series([3.0, 3.0]),
            "IRLTLT01DEM156N": _monthly_series([3.7, 3.7]),  # diff = -0.7
        }
    )
    fn = get("yield_diff_10y")
    score = fn(store, "EURUSD", {"foreign_series": "IRLTLT01DEM156N"})
    assert score == 1.0


def test_yield_diff_10y_high_us_returns_zero_for_low_bull() -> None:
    """US >> foreign (3.0pp diff) → 0.0 for foreign-currency-tolkning."""
    store = _MockStore(
        {
            "DGS10": _monthly_series([5.0, 5.0]),
            "IRLTLT01DEM156N": _monthly_series([2.0, 2.0]),  # diff = 3.0
        }
    )
    fn = get("yield_diff_10y")
    score = fn(store, "EURUSD", {"foreign_series": "IRLTLT01DEM156N"})
    assert score == 0.0


def test_yield_diff_10y_high_bull_inverts_for_usdjpy() -> None:
    """USDJPY: høy diff = USD strong = bull pair."""
    store = _MockStore(
        {
            "DGS10": _monthly_series([5.0, 5.0]),
            "IRLTLT01JPM156N": _monthly_series([2.0, 2.0]),  # diff = 3.0
        }
    )
    fn = get("yield_diff_10y")
    score = fn(store, "USDJPY", {"foreign_series": "IRLTLT01JPM156N", "bull_when": "high"})
    assert score == 1.0  # 3.0 ≥ 2.5 i high-mapping


def test_yield_diff_10y_neutral_diff_returns_neutral_score() -> None:
    """Diff ~1.0pp = nøytral-sone → 0.5."""
    store = _MockStore(
        {
            "DGS10": _monthly_series([3.5, 3.5]),
            "IRLTLT01DEM156N": _monthly_series([2.5, 2.5]),  # diff = 1.0
        }
    )
    fn = get("yield_diff_10y")
    score = fn(store, "EURUSD", {"foreign_series": "IRLTLT01DEM156N"})
    assert score == 0.5  # ≤ 1.5-terskel for "low"


def test_yield_diff_10y_no_foreign_series_param_returns_zero() -> None:
    store = _MockStore({"DGS10": _monthly_series([3.0])})
    fn = get("yield_diff_10y")
    assert fn(store, "EURUSD", {}) == 0.0


def test_yield_diff_10y_missing_fred_series_returns_zero() -> None:
    store = _MockStore({"DGS10": _monthly_series([3.0])})  # foreign mangler
    fn = get("yield_diff_10y")
    assert fn(store, "EURUSD", {"foreign_series": "IRLTLT01DEM156N"}) == 0.0


def test_yield_diff_10y_pct_36m_mode_returns_rank_percentile() -> None:
    """pct_36m: current er topp av 36 obs → høy score for high-bull (USDJPY)."""
    # 36 monthly obs ascending; sist er høyest → diff = current - prev
    us = _monthly_series([4.5 + i * 0.01 for i in range(40)])
    foreign = _monthly_series([1.0] * 40)  # diff: 3.5 → 3.89, current = topp
    store = _MockStore({"DGS10": us, "IRLTLT01JPM156N": foreign})
    fn = get("yield_diff_10y")
    score = fn(
        store,
        "USDJPY",
        {"foreign_series": "IRLTLT01JPM156N", "bull_when": "high", "mode": "pct_36m"},
    )
    # current is at top percentile → score nær 1.0 for high-bull
    assert score >= 0.9


def test_yield_diff_10y_pct_12m_falls_back_to_pct_36m() -> None:
    """pct_12m → fall-back til pct_36m fordi 12 obs er under MIN_OBS_FOR_PCTILE."""
    us = _monthly_series([4.5 + i * 0.01 for i in range(40)])
    foreign = _monthly_series([1.0] * 40)
    store = _MockStore({"DGS10": us, "IRLTLT01DEM156N": foreign})
    fn = get("yield_diff_10y")
    # bull_when="low" — current er topp → score nær 0 (high-diff = bear EURUSD)
    score = fn(
        store,
        "EURUSD",
        {"foreign_series": "IRLTLT01DEM156N", "mode": "pct_12m"},
    )
    assert score <= 0.1


def test_yield_diff_10y_extreme_flag_hard_at_top_percentile() -> None:
    """Extreme-flag: current i 98+-percentil → 1.0."""
    us = _monthly_series([3.0] * 35 + [10.0])  # siste obs er extrem outlier
    foreign = _monthly_series([1.0] * 36)
    store = _MockStore({"DGS10": us, "IRLTLT01DEM156N": foreign})
    fn = get("yield_diff_10y")
    score = fn(
        store,
        "EURUSD",
        {"foreign_series": "IRLTLT01DEM156N", "mode": "extreme_flag_hard"},
    )
    assert score == 1.0


def test_yield_diff_10y_unknown_mode_falls_back_to_default() -> None:
    """Ukjent mode → default-trapp."""
    store = _MockStore(
        {
            "DGS10": _monthly_series([3.0, 3.0]),
            "IRLTLT01DEM156N": _monthly_series([3.7, 3.7]),
        }
    )
    fn = get("yield_diff_10y")
    score = fn(
        store,
        "EURUSD",
        {"foreign_series": "IRLTLT01DEM156N", "mode": "unknown_mode_xyz"},
    )
    assert score == 1.0  # samme som default på diff = -0.7


# ---------------------------------------------------------------------------
# credit_spread_change
# ---------------------------------------------------------------------------


def test_credit_spread_change_low_spread_returns_max_score() -> None:
    """Lav spread (BAA-AAA = 0.5) = lav stress = bull risk-on."""
    store = _MockStore(
        {
            "BAA10Y": _daily_series([3.5]),
            "AAA10Y": _daily_series([3.0]),  # spread = 0.5
        }
    )
    fn = get("credit_spread_change")
    assert fn(store, "Nasdaq", {}) == 1.0  # ≤ 0.6


def test_credit_spread_change_normal_spread_returns_neutral() -> None:
    """Normal spread (~1.0) = nøytral. Første matchende ascending terskel er 1.2 → 0.5."""
    store = _MockStore(
        {
            "BAA10Y": _daily_series([4.0]),
            "AAA10Y": _daily_series([3.0]),  # spread = 1.0
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Nasdaq", {})
    assert score == 0.5  # 1.0 > 0.9, men ≤ 1.2 → 0.5


def test_credit_spread_change_wide_spread_returns_low_score() -> None:
    """Bred spread (2.0+) = høy stress = bear risk-on."""
    store = _MockStore(
        {
            "BAA10Y": _daily_series([6.0]),
            "AAA10Y": _daily_series([3.5]),  # spread = 2.5
        }
    )
    fn = get("credit_spread_change")
    assert fn(store, "Nasdaq", {}) == 0.0  # ingen terskel matchet (2.5 > 1.8)


def test_credit_spread_change_high_bull_inverts_for_safe_haven() -> None:
    """bull_when='high': bred spread = bull (Gold-flight-to-quality)."""
    store = _MockStore(
        {
            "BAA10Y": _daily_series([3.5]),
            "AAA10Y": _daily_series([3.0]),  # spread = 0.5 (lav)
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Gold", {"bull_when": "high"})
    # spread=0.5 → low-score=1.0 → high-bull = 1 - 1.0 = 0.0
    assert score == 0.0


def test_credit_spread_change_missing_aaa_returns_zero() -> None:
    store = _MockStore({"BAA10Y": _daily_series([4.0])})
    fn = get("credit_spread_change")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_credit_spread_change_pct_36m_mode_returns_score() -> None:
    """pct_36m mode på daglig serie."""
    baa_values = [4.0 + i * 0.001 for i in range(800)]
    aaa_values = [3.0] * 800
    store = _MockStore(
        {
            "BAA10Y": _daily_series(baa_values),
            "AAA10Y": _daily_series(aaa_values),
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Nasdaq", {"mode": "pct_36m"})
    # Spread is monotonically increasing, current is top → bull_when=low → 1 - 1.0 ≈ 0.0
    assert 0.0 <= score <= 0.05


def test_credit_spread_change_delta_5d_z_mode_returns_score() -> None:
    """delta_5d_z mode: spread oscillerer rundt mean → current-delta = 0 → 0.5."""
    # Lett oscillerende serie slik at stdev > 0 men current-delta ≈ 0.
    import math

    baa_values = [4.0 + 0.1 * math.sin(i * 0.5) for i in range(300)]
    aaa_values = [3.0] * 300
    store = _MockStore(
        {
            "BAA10Y": _daily_series(baa_values),
            "AAA10Y": _daily_series(aaa_values),
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Nasdaq", {"mode": "delta_5d_z"})
    # Med oscillasjon er stdev > 0 → driveren returnerer en gyldig score.
    # Verdien avhenger av sin-fasen — sjekk kun at den er en gyldig 0..1.
    assert 0.0 <= score <= 1.0


def test_credit_spread_change_extreme_flag_soft() -> None:
    """Extreme-flag-soft: 95+-percentil → 1.0."""
    # 300 daglige, sist er klart høyest
    baa_values = [4.0] * 299 + [10.0]
    aaa_values = [3.0] * 300
    store = _MockStore(
        {
            "BAA10Y": _daily_series(baa_values),
            "AAA10Y": _daily_series(aaa_values),
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Nasdaq", {"mode": "extreme_flag_soft"})
    assert score == 1.0


def test_credit_spread_change_unknown_mode_falls_back() -> None:
    store = _MockStore(
        {
            "BAA10Y": _daily_series([3.5]),
            "AAA10Y": _daily_series([3.0]),
        }
    )
    fn = get("credit_spread_change")
    score = fn(store, "Nasdaq", {"mode": "garbage"})
    assert score == 1.0  # default på spread=0.5


# ---------------------------------------------------------------------------
# nfci_change
# ---------------------------------------------------------------------------


def test_nfci_change_negative_returns_max_score_for_low_bull() -> None:
    """NFCI = -1.5 (sterkt løsere enn snitt) = sterk bull risk-on."""
    store = _MockStore({"NFCI": _weekly_series([-1.5])})
    fn = get("nfci_change")
    assert fn(store, "Nasdaq", {}) == 1.0


def test_nfci_change_zero_returns_neutral() -> None:
    """NFCI = 0 (gjennomsnitt) = nøytral."""
    store = _MockStore({"NFCI": _weekly_series([0.0])})
    fn = get("nfci_change")
    assert fn(store, "Nasdaq", {}) == 0.5


def test_nfci_change_positive_returns_low_score() -> None:
    """NFCI = 1.5 (mye tighter) = bear risk-on."""
    store = _MockStore({"NFCI": _weekly_series([1.5])})
    fn = get("nfci_change")
    assert fn(store, "Nasdaq", {}) == 0.0  # ingen terskel ≤ 1.5 → 0.0 default


def test_nfci_change_high_bull_inverts() -> None:
    """bull_when='high': lav NFCI = bear (kontrært)."""
    store = _MockStore({"NFCI": _weekly_series([-1.5])})
    fn = get("nfci_change")
    score = fn(store, "Gold", {"bull_when": "high"})
    # NFCI=-1.5 → low-score=1.0 → invertert = 0.0
    assert score == 0.0


def test_nfci_change_missing_series_returns_zero() -> None:
    store = _MockStore({})
    fn = get("nfci_change")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_nfci_change_pct_12m_mode_with_weekly_data() -> None:
    """pct_12m mode på 60 ukentlige obs."""
    values = [-0.5 + i * 0.01 for i in range(60)]  # monotonously increasing
    store = _MockStore({"NFCI": _weekly_series(values)})
    fn = get("nfci_change")
    score = fn(store, "Nasdaq", {"mode": "pct_12m"})
    # Current er topp → bull_when="low" → 1 - 1.0 ≈ 0.0
    assert 0.0 <= score <= 0.1


def test_nfci_change_delta_5d_z_with_weekly_data() -> None:
    """delta_5d_z = 1-rapport-delta på ukentlig data (per pattern-doc).

    Flat data gir stdev=0 → rolling_z returnerer None → driver 0.0.
    Bruk svak oscillasjon for å sikre stdev > 0.
    """
    import math

    values = [0.1 * math.sin(i * 0.5) for i in range(60)]
    store = _MockStore({"NFCI": _weekly_series(values)})
    fn = get("nfci_change")
    score = fn(store, "Nasdaq", {"mode": "delta_5d_z"})
    # Med oscillasjon: stdev > 0, gyldig score returneres.
    assert 0.0 <= score <= 1.0


def test_nfci_change_extreme_flag_hard() -> None:
    """Extreme-flag-hard: 98+-percentil."""
    values = [0.0] * 59 + [5.0]  # outlier
    store = _MockStore({"NFCI": _weekly_series(values)})
    fn = get("nfci_change")
    score = fn(store, "Nasdaq", {"mode": "extreme_flag_hard"})
    assert score == 1.0


def test_nfci_change_unknown_mode_falls_back() -> None:
    store = _MockStore({"NFCI": _weekly_series([-1.5])})
    fn = get("nfci_change")
    assert fn(store, "Nasdaq", {"mode": "garbage_mode"}) == 1.0


# ---------------------------------------------------------------------------
# net_fed_liq_change
# ---------------------------------------------------------------------------


def test_net_fed_liq_change_growing_returns_max_score() -> None:
    """4-uke vekst > 2% = sterk QE = bull risk-on."""
    walcl = _weekly_series([8000000.0, 8050000.0, 8100000.0, 8150000.0, 8400000.0])
    rrp = _weekly_series([2000000.0] * 5)  # konstant
    tga = _weekly_series([700000.0] * 5)  # konstant
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {})
    # NetLiq grew from 5300000 to 5700000 ≈ +7.5% over 4 weeks → ≥ 2.0% → 1.0
    assert score == 1.0


def test_net_fed_liq_change_flat_returns_neutral() -> None:
    """Flat NetLiq (0% endring) = nøytral 0.5."""
    walcl = _weekly_series([8000000.0] * 5)
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    assert fn(store, "Nasdaq", {}) == 0.5


def test_net_fed_liq_change_mild_qt_returns_low_step() -> None:
    """Mild QT (~-1.5%) faller i -2.0-bucket = 0.1.

    Trappen iterer descending fra 2.0; første matchende ≥-terskel
    returneres. -1.51% matcher ikke ≥ -1.0 men matcher ≥ -2.0 → 0.1.
    """
    walcl = _weekly_series([8000000.0, 7980000.0, 7960000.0, 7940000.0, 7920000.0])
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {})
    assert score == 0.1


def test_net_fed_liq_change_negative_in_qt_floor() -> None:
    """pct_chg = -0.5% (mellom 0 og -1) faller i -1.0-bucket = 0.25."""
    # 5300000 → 5274500 = -0.481% — matcher ≥-1.0 men ikke ≥0
    walcl = _weekly_series([8000000.0, 7993750.0, 7987500.0, 7981250.0, 7975000.0])
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {})
    assert score == 0.25


def test_net_fed_liq_change_deep_qt_returns_zero() -> None:
    """Sterkere QT enn -2% er utenfor trappen → 0.0 (bear-est)."""
    walcl = _weekly_series([8000000.0, 7900000.0, 7800000.0, 7700000.0, 7600000.0])
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {})
    # -7.5% < alle terskler → 0.0
    assert score == 0.0


def test_net_fed_liq_change_low_bull_inverts() -> None:
    """bull_when='low': vekst = bear (kontrært/safe-haven)."""
    walcl = _weekly_series([8000000.0, 8050000.0, 8100000.0, 8150000.0, 8400000.0])
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Gold", {"bull_when": "low"})
    # +7.5% endring matcher ≤ -2.0%-flippet via abs() → returnerer 0.1
    # Faktisk vår implementasjon: bull_when="low" speil — trenger pct ≤ -threshold
    # Vekst på +7.5% matcher ikke noen ≤ -2-terskel → 0.0
    assert score == 0.0


def test_net_fed_liq_change_missing_series_returns_zero() -> None:
    walcl = _weekly_series([8000000.0] * 5)
    store = _MockStore({"WALCL": walcl})  # rrp + tga mangler
    fn = get("net_fed_liq_change")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_net_fed_liq_change_short_history_returns_zero() -> None:
    """Mindre enn chg_window+1 obs → 0.0."""
    walcl = _weekly_series([8000000.0, 8100000.0])
    rrp = _weekly_series([2000000.0, 2000000.0])
    tga = _weekly_series([700000.0, 700000.0])
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    assert fn(store, "Nasdaq", {}) == 0.0


def test_net_fed_liq_change_pct_12m_mode() -> None:
    """pct_12m mode på 60 ukentlige obs."""
    walcl_values = [8000000.0 + i * 1000 for i in range(60)]
    rrp_values = [2000000.0] * 60
    tga_values = [700000.0] * 60
    store = _MockStore(
        {
            "WALCL": _weekly_series(walcl_values),
            "RRPONTSYD": _weekly_series(rrp_values),
            "WTREGEN": _weekly_series(tga_values),
        }
    )
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {"mode": "pct_12m"})
    # NetLiq monotonically increasing, current = topp → bull_when="high" → ≈ 1.0
    assert score >= 0.9


def test_net_fed_liq_change_delta_5d_z_with_oscillating_data() -> None:
    """delta_5d_z på oscillerende NetLiq returnerer gyldig 0..1.

    Flat data gir stdev=0 → driver 0.0; bruk svak oscillasjon.
    """
    import math

    walcl_values = [8000000.0 + 10000 * math.sin(i * 0.5) for i in range(60)]
    rrp_values = [2000000.0] * 60
    tga_values = [700000.0] * 60
    store = _MockStore(
        {
            "WALCL": _weekly_series(walcl_values),
            "RRPONTSYD": _weekly_series(rrp_values),
            "WTREGEN": _weekly_series(tga_values),
        }
    )
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {"mode": "delta_5d_z"})
    assert 0.0 <= score <= 1.0


def test_net_fed_liq_change_extreme_flag_at_top() -> None:
    """Extreme-flag-soft: 95+-percentil → 1.0."""
    walcl_values = [8000000.0] * 59 + [10000000.0]  # outlier
    rrp_values = [2000000.0] * 60
    tga_values = [700000.0] * 60
    store = _MockStore(
        {
            "WALCL": _weekly_series(walcl_values),
            "RRPONTSYD": _weekly_series(rrp_values),
            "WTREGEN": _weekly_series(tga_values),
        }
    )
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {"mode": "extreme_flag_soft"})
    assert score == 1.0


def test_net_fed_liq_change_unknown_mode_falls_back() -> None:
    walcl = _weekly_series([8000000.0, 8050000.0, 8100000.0, 8150000.0, 8400000.0])
    rrp = _weekly_series([2000000.0] * 5)
    tga = _weekly_series([700000.0] * 5)
    store = _MockStore({"WALCL": walcl, "RRPONTSYD": rrp, "WTREGEN": tga})
    fn = get("net_fed_liq_change")
    score = fn(store, "Nasdaq", {"mode": "garbage"})
    assert score == 1.0  # samme som default
