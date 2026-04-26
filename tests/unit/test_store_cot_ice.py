"""Tester for ICE Futures Europe COT-støtte i DataStore (session 106)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ice_df(
    contract: str = "ice brent crude",
    dates: list[str] | None = None,
    base_mm_long: int = 80_000,
) -> pd.DataFrame:
    """Bygg en DataFrame med n ICE-COT-rapporter (parallell til CFTC disagg)."""
    if dates is None:
        dates = ["2024-01-02", "2024-01-09", "2024-01-16"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": [contract] * n,
            "mm_long": [base_mm_long + 1_000 * i for i in range(n)],
            "mm_short": [40_000 + 500 * i for i in range(n)],
            "other_long": [12_000] * n,
            "other_short": [9_000] * n,
            "comm_long": [180_000] * n,
            "comm_short": [200_000] * n,
            "nonrep_long": [4_000] * n,
            "nonrep_short": [3_500] * n,
            "open_interest": [400_000] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_cot_ice_append_and_get(store: DataStore) -> None:
    store.append_cot_ice(_ice_df())
    df = store.get_cot_ice("ice brent crude")
    assert len(df) == 3
    assert list(df.columns) == [
        "report_date",
        "contract",
        "mm_long",
        "mm_short",
        "other_long",
        "other_short",
        "comm_long",
        "comm_short",
        "nonrep_long",
        "nonrep_short",
        "open_interest",
    ]
    assert df["report_date"].iloc[0] == pd.Timestamp("2024-01-02")
    assert df["mm_long"].iloc[0] == 80_000


def test_cot_ice_last_n(store: DataStore) -> None:
    store.append_cot_ice(_ice_df())
    df = store.get_cot_ice("ice brent crude", last_n=2)
    assert len(df) == 2
    assert df["report_date"].iloc[0] == pd.Timestamp("2024-01-09")
    assert df["report_date"].iloc[1] == pd.Timestamp("2024-01-16")


def test_cot_ice_dedupe_on_same_date_and_contract(store: DataStore) -> None:
    """Samme (report_date, contract) overskrives, ikke dupliseres."""
    store.append_cot_ice(_ice_df())

    replay = _ice_df(dates=["2024-01-02"], base_mm_long=999_999)
    store.append_cot_ice(replay)

    df = store.get_cot_ice("ice brent crude")
    assert len(df) == 3  # fortsatt 3 rader
    first = df[df["report_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert first["mm_long"] == 999_999


def test_cot_ice_append_appends_new_dates(store: DataStore) -> None:
    store.append_cot_ice(_ice_df(dates=["2024-01-02", "2024-01-09"]))
    store.append_cot_ice(_ice_df(dates=["2024-01-16", "2024-01-23"]))
    df = store.get_cot_ice("ice brent crude")
    assert len(df) == 4


def test_cot_ice_missing_column_raises(store: DataStore) -> None:
    bad = pd.DataFrame(
        {
            "report_date": ["2024-01-02"],
            "contract": ["ice brent crude"],
            # Mangler mm_long og resten
        }
    )
    with pytest.raises(ValueError, match="missing columns"):
        store.append_cot_ice(bad)


def test_cot_ice_get_unknown_contract_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No ICE COT data"):
        store.get_cot_ice("unknown_contract")


# ---------------------------------------------------------------------------
# Tabell-isolering: cot_ice og cot_disaggregated overlapper IKKE
# ---------------------------------------------------------------------------


def test_cot_ice_separate_from_cftc_disaggregated(store: DataStore) -> None:
    """ICE og CFTC-disaggregated er separate tabeller — samme contract-streng
    skal ikke kollidere."""
    contract = "shared name"
    store.append_cot_ice(_ice_df(contract=contract, base_mm_long=11_111))

    # CFTC-disagg-getter skal ikke se ICE-data
    with pytest.raises(KeyError, match="No COT data"):
        store.get_cot(contract, report="disaggregated")

    # ICE-getter ser sin egen rad
    df_ice = store.get_cot_ice(contract)
    assert df_ice["mm_long"].iloc[0] == 11_111


def test_cot_ice_separate_contracts_do_not_interfere(store: DataStore) -> None:
    store.append_cot_ice(_ice_df(contract="ice brent crude"))
    store.append_cot_ice(_ice_df(contract="ice ttf gas", base_mm_long=20_000))

    brent = store.get_cot_ice("ice brent crude")
    ttf = store.get_cot_ice("ice ttf gas")
    assert brent["mm_long"].iloc[0] == 80_000
    assert ttf["mm_long"].iloc[0] == 20_000


# ---------------------------------------------------------------------------
# has_cot_ice
# ---------------------------------------------------------------------------


def test_has_cot_ice_negative(store: DataStore) -> None:
    assert not store.has_cot_ice("ice brent crude")


def test_has_cot_ice_positive(store: DataStore) -> None:
    store.append_cot_ice(_ice_df(contract="ice brent crude"))
    assert store.has_cot_ice("ice brent crude")
    assert not store.has_cot_ice("ice ttf gas")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_cot_ice_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_cot_ice(_ice_df())

    store_b = DataStore(db)
    df = store_b.get_cot_ice("ice brent crude")
    assert len(df) == 3
