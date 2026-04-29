"""Tester for etf_holdings-støtte i DataStore (sub-fase 12.7 D2 A5/A6, session 132)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _gld_df(dates: list[str] | None = None, base: float = 900.0) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    n = len(dates)
    return pd.DataFrame(
        {
            "ticker": ["gld"] * n,
            "date": dates,
            "tonnes_in_trust": [base + 0.5 * i for i in range(n)],
            "ounces_in_trust": [(base + 0.5 * i) * 32150.7 for i in range(n)],
            "shares_outstanding": [None] * n,
            "nav_per_share": [180.0 + 0.1 * i for i in range(n)],
        }
    )


def _slv_df(dates: list[str] | None = None, base_shares: float = 5e8) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    n = len(dates)
    return pd.DataFrame(
        {
            "ticker": ["slv"] * n,
            "date": dates,
            "tonnes_in_trust": [None] * n,
            "ounces_in_trust": [None] * n,
            "shares_outstanding": [base_shares + 1e6 * i for i in range(n)],
            "nav_per_share": [22.0 + 0.05 * i for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_etf_append_and_get_gld(store: DataStore) -> None:
    store.append_etf_holdings(_gld_df())
    df = store.get_etf_holdings("gld")
    assert len(df) == 3
    assert df["tonnes_in_trust"].iloc[0] == 900.0
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-02")


def test_etf_append_and_get_slv_proxy(store: DataStore) -> None:
    """SLV mangler tonnes — kun shares_outstanding er primær."""
    store.append_etf_holdings(_slv_df())
    df = store.get_etf_holdings("slv")
    assert len(df) == 3
    assert pd.isna(df["tonnes_in_trust"].iloc[0])
    assert df["shares_outstanding"].iloc[0] == 5e8


def test_etf_two_tickers_isolated(store: DataStore) -> None:
    store.append_etf_holdings(_gld_df())
    store.append_etf_holdings(_slv_df())
    gld = store.get_etf_holdings("gld")
    slv = store.get_etf_holdings("slv")
    assert len(gld) == 3
    assert len(slv) == 3
    assert (gld["ticker"] == "gld").all()
    assert (slv["ticker"] == "slv").all()


def test_etf_idempotent_replace(store: DataStore) -> None:
    """(ticker, date) er PK — replay overskriver."""
    store.append_etf_holdings(_gld_df())
    replay = _gld_df(dates=["2024-01-02"], base=999.0)
    store.append_etf_holdings(replay)
    df = store.get_etf_holdings("gld")
    assert len(df) == 3
    first = df[df["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert first["tonnes_in_trust"] == 999.0


def test_etf_date_range_filter(store: DataStore) -> None:
    store.append_etf_holdings(
        _gld_df(dates=["2024-01-02", "2024-01-15", "2024-02-01", "2024-03-01"])
    )
    df = store.get_etf_holdings("gld", from_date="2024-01-10", to_date="2024-02-15")
    assert len(df) == 2
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-15")
    assert df["date"].iloc[-1] == pd.Timestamp("2024-02-01")


def test_etf_get_unknown_ticker_raises(store: DataStore) -> None:
    store.append_etf_holdings(_gld_df())
    with pytest.raises(KeyError):
        store.get_etf_holdings("unknown")


def test_etf_has_helpers(store: DataStore) -> None:
    assert store.has_etf_holdings("gld") is False
    store.append_etf_holdings(_gld_df())
    assert store.has_etf_holdings("gld") is True
    assert store.has_etf_holdings("slv") is False


def test_etf_ticker_normalized_lowercase(store: DataStore) -> None:
    df_upper = _gld_df()
    df_upper["ticker"] = ["GLD"] * len(df_upper)
    store.append_etf_holdings(df_upper)
    assert store.has_etf_holdings("gld") is True
    assert store.has_etf_holdings("GLD") is True  # accessor lowercases too


def test_etf_missing_columns_raises(store: DataStore) -> None:
    df = pd.DataFrame({"ticker": ["gld"], "date": ["2024-01-02"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_etf_holdings(df)
