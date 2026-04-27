"""Tester for ``cot_euronext_mm_pct`` driver (sub-fase 12.5+ session 110)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockEuronextStore:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self._data = data

    def get_cot_euronext(self, contract: str, last_n: int | None = None):
        if contract not in self._data:
            raise KeyError(f"No Euronext data for {contract!r}")
        df = self._data[contract]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _build_df(
    *,
    n_weeks: int = 60,
    contract: str = "euronext milling wheat",
    base_long: int = 80_000,
    base_short: int = 110_000,
    base_oi: int = 475_000,
    long_step: int = 0,
    short_step: int = 0,
) -> pd.DataFrame:
    """Bygg Euronext-DF med kontrollerbar trend i mm_long/mm_short."""
    base = date(2024, 1, 1)
    rows = []
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": pd.Timestamp(base + timedelta(weeks=i)),
                "contract": contract,
                "mm_long": base_long + long_step * i,
                "mm_short": base_short + short_step * i,
                "open_interest": base_oi,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("cot_euronext_mm_pct") is not None


# ---------------------------------------------------------------------------
# Score-formel
# ---------------------------------------------------------------------------


def test_extreme_long_gives_high_score() -> None:
    """Siste rad mm_net er høyest → top-percentile → score nær 1.0."""
    df = _build_df(n_weeks=60, base_long=80_000, base_short=110_000, long_step=100)
    # Boost siste rad
    df.iloc[-1, df.columns.get_loc("mm_long")] = 150_000
    df.iloc[-1, df.columns.get_loc("mm_short")] = 80_000  # net = +70K (utenom)
    store = _MockEuronextStore({"euronext milling wheat": df})

    fn = get("cot_euronext_mm_pct")
    score = fn(store, "Wheat", {"contract": "euronext milling wheat", "metric": "mm_net"})
    assert score > 0.9


def test_extreme_short_gives_low_score() -> None:
    """Siste rad mm_net er lavest → bunn-percentile → score nær 0.0."""
    df = _build_df(n_weeks=60, base_long=80_000, base_short=110_000)
    df.iloc[-1, df.columns.get_loc("mm_long")] = 20_000
    df.iloc[-1, df.columns.get_loc("mm_short")] = 200_000  # ekstrem short
    store = _MockEuronextStore({"euronext milling wheat": df})

    fn = get("cot_euronext_mm_pct")
    score = fn(store, "Wheat", {"contract": "euronext milling wheat", "metric": "mm_net"})
    assert score < 0.1


def test_score_in_unit_interval() -> None:
    """Konstant mm_net → score er i [0, 1] (rank_percentile-konvensjon
    plasserer ties på 100% per cot_ice_mm_pct-presedens)."""
    df = _build_df(n_weeks=60, base_long=80_000, base_short=110_000)
    store = _MockEuronextStore({"euronext milling wheat": df})

    fn = get("cot_euronext_mm_pct")
    score = fn(store, "Wheat", {"contract": "euronext milling wheat", "metric": "mm_net"})
    assert 0.0 <= score <= 1.0


def test_metric_mm_net_pct() -> None:
    """mm_net_pct virker (deler net på OI)."""
    df = _build_df(n_weeks=60, long_step=200)
    df.iloc[-1, df.columns.get_loc("mm_long")] = 200_000  # high pct
    store = _MockEuronextStore({"euronext milling wheat": df})

    fn = get("cot_euronext_mm_pct")
    score = fn(
        store,
        "Wheat",
        {"contract": "euronext milling wheat", "metric": "mm_net_pct"},
    )
    assert score > 0.7


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_contract_missing() -> None:
    fn = get("cot_euronext_mm_pct")
    assert fn(_MockEuronextStore({}), "Wheat", {}) == 0.0


def test_returns_zero_when_contract_unknown() -> None:
    fn = get("cot_euronext_mm_pct")
    assert (
        fn(
            _MockEuronextStore({}),
            "Wheat",
            {"contract": "euronext milling wheat"},
        )
        == 0.0
    )


def test_returns_zero_for_short_history() -> None:
    """Færre enn min_obs → defensiv 0.0."""
    df = _build_df(n_weeks=5)
    store = _MockEuronextStore({"euronext milling wheat": df})
    fn = get("cot_euronext_mm_pct")
    assert fn(store, "Wheat", {"contract": "euronext milling wheat"}) == 0.0


def test_returns_zero_when_store_raises() -> None:
    class _Broken:
        def get_cot_euronext(self, contract, last_n=None):
            raise RuntimeError("DB error")

    fn = get("cot_euronext_mm_pct")
    assert fn(_Broken(), "Wheat", {"contract": "euronext milling wheat"}) == 0.0


def test_returns_zero_for_unknown_metric() -> None:
    df = _build_df(n_weeks=60)
    store = _MockEuronextStore({"euronext milling wheat": df})
    fn = get("cot_euronext_mm_pct")
    assert (
        fn(
            store,
            "Wheat",
            {"contract": "euronext milling wheat", "metric": "unknown_metric"},
        )
        == 0.0
    )


# ---------------------------------------------------------------------------
# Multi-contract isolering
# ---------------------------------------------------------------------------


def test_different_contracts_resolve_independently() -> None:
    wheat = _build_df(contract="euronext milling wheat", base_long=80_000, base_short=110_000)
    wheat.iloc[-1, wheat.columns.get_loc("mm_long")] = 150_000  # ekstrem long
    wheat.iloc[-1, wheat.columns.get_loc("mm_short")] = 80_000

    corn = _build_df(contract="euronext corn", base_long=7_000, base_short=2_000)
    corn.iloc[-1, corn.columns.get_loc("mm_long")] = 1_000
    corn.iloc[-1, corn.columns.get_loc("mm_short")] = 50_000  # ekstrem short

    store = _MockEuronextStore({"euronext milling wheat": wheat, "euronext corn": corn})
    fn = get("cot_euronext_mm_pct")
    wheat_score = fn(store, "Wheat", {"contract": "euronext milling wheat"})
    corn_score = fn(store, "Corn", {"contract": "euronext corn"})

    assert wheat_score > 0.9
    assert corn_score < 0.1
