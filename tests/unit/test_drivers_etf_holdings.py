"""Tester for ``etf_holdings_change``-driver (sub-fase 12.7 D2 A5/A6, session 132).

Bruker in-memory mock-store; ingen ekte ETF-feed-kall. Dekker default-mode
+ mode-dispatch + ticker-dispatch (gld vs slv) + ``bull_when``-konfigurasjoner
+ edge-cases.
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    """Stub som returnerer pd.DataFrame for ETF holdings."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames

    def get_etf_holdings(
        self,
        ticker: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        key = ticker.lower()
        if key not in self._frames:
            raise KeyError(f"No ETF holdings for ticker={key!r}")
        return self._frames[key]


def _make_gld_df(tonnes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(tonnes), freq="D")
    return pd.DataFrame(
        {
            "ticker": ["gld"] * len(tonnes),
            "date": idx,
            "tonnes_in_trust": tonnes,
            "ounces_in_trust": [t * 32150.7 for t in tonnes],
            "shares_outstanding": [None] * len(tonnes),
            "nav_per_share": [180.0] * len(tonnes),
        }
    )


def _make_slv_df(shares: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(shares), freq="D")
    return pd.DataFrame(
        {
            "ticker": ["slv"] * len(shares),
            "date": idx,
            "tonnes_in_trust": [None] * len(shares),
            "ounces_in_trust": [None] * len(shares),
            "shares_outstanding": shares,
            "nav_per_share": [22.0] * len(shares),
        }
    )


# ---------------------------------------------------------------------------
# Default mode (WoW pct change → terskel-trapp)
# ---------------------------------------------------------------------------


def test_default_strong_inflow_gld_returns_top_score() -> None:
    """+2 % WoW i tonnes_in_trust → 1.0 (≥+1.5 % terskel)."""
    # Steady 900 i 5 dager, så +2 % på dag 6.
    base = [900.0] * 5
    df = _make_gld_df([*base, 918.0])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld"})
    assert score == 1.0


def test_default_strong_outflow_gld_returns_zero() -> None:
    """-2 % WoW → 0.0 (≤-1.5 % terskel)."""
    base = [900.0] * 5
    df = _make_gld_df([*base, 882.0])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld"})
    assert score == 0.0


def test_default_flat_returns_neutral() -> None:
    """0 % WoW → 0.5 (nøytral bucket)."""
    df = _make_gld_df([900.0] * 6)
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld"})
    assert score == 0.5


def test_default_bull_when_low_inverts() -> None:
    """+2 % WoW, bull_when=low → 0.0 (invertert)."""
    df = _make_gld_df([*[900.0] * 5, 918.0])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld", "bull_when": "low"})
    assert score == 0.0


# ---------------------------------------------------------------------------
# SLV ticker-dispatch (uses shares_outstanding proxy)
# ---------------------------------------------------------------------------


def test_slv_uses_shares_outstanding_as_proxy() -> None:
    """SLV-feed mangler tonnes; driver må bruke shares_outstanding."""
    base = [5e8] * 5
    # +1.5 % WoW i shares
    df = _make_slv_df([*base, 5.075e8])
    store = _MockStore({"slv": df})
    score = get("etf_holdings_change")(store, "Silver", {"ticker": "slv"})
    assert score == 1.0


def test_slv_outflow_proxy() -> None:
    """SLV: -2 % i shares_outstanding → 0.0 (outflow)."""
    base = [5e8] * 5
    df = _make_slv_df([*base, 4.9e8])
    store = _MockStore({"slv": df})
    score = get("etf_holdings_change")(store, "Silver", {"ticker": "slv"})
    assert score == 0.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_missing_ticker_returns_zero() -> None:
    """Ticker er required-param. Tom → 0.0 + warning."""
    store = _MockStore({"gld": _make_gld_df([900.0] * 6)})
    score = get("etf_holdings_change")(store, "Gold", {})
    assert score == 0.0


def test_unknown_ticker_returns_zero() -> None:
    """Driver kjenner ikke ``foo`` → 0.0."""
    store = _MockStore({"gld": _make_gld_df([900.0] * 6)})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "foo"})
    assert score == 0.0


def test_no_data_returns_zero() -> None:
    """get_etf_holdings KeyError → 0.0 (defensive)."""
    store = _MockStore({})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld"})
    assert score == 0.0


def test_short_series_returns_zero() -> None:
    """For kort serie til WoW-window → 0.0 defensive."""
    df = _make_gld_df([900.0, 905.0])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld"})
    assert score == 0.0


# ---------------------------------------------------------------------------
# Mode-dispatch (R4 — pct_12m, delta_5d_z, extreme_flag)
# ---------------------------------------------------------------------------


def test_mode_pct_12m_monotonic_high_at_top() -> None:
    """Strictly increasing series → pct_12m ≈ 1.0 (current er på top)."""
    # 280 dager strictly increasing.
    n = 280
    df = _make_gld_df([900.0 + i for i in range(n)])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld", "mode": "pct_12m"})
    # bull_when=high default; toppen er bull → score ≈ 1.0
    assert score >= 0.95


def test_mode_extreme_flag_outlier_detects_top() -> None:
    """Top-percentile outlier → extreme_flag returnerer høy score."""
    n = 260
    base = [900.0 + 0.01 * i for i in range(n - 1)]
    spike = [base[-1] * 1.5]  # outlier på toppen
    df = _make_gld_df([*base, *spike])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(
        store, "Gold", {"ticker": "gld", "mode": "extreme_flag_hard"}
    )
    assert score >= 0.5  # outlier-detection slo til


def test_mode_unknown_falls_back_to_default() -> None:
    """Ukjent mode → default-trapp."""
    df = _make_gld_df([*[900.0] * 5, 918.0])
    store = _MockStore({"gld": df})
    score = get("etf_holdings_change")(store, "Gold", {"ticker": "gld", "mode": "frobnicate"})
    assert score == 1.0  # default-trapp +2 % → 1.0
