"""Tester for COT-støtte i DataStore (CFTC disaggregated + legacy)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disaggregated_df(
    contract: str = "GOLD",
    dates: list[str] | None = None,
    base_mm_long: int = 100_000,
) -> pd.DataFrame:
    """Bygg en DataFrame med n CFTC-disaggregated-rapporter."""
    if dates is None:
        dates = ["2024-01-02", "2024-01-09", "2024-01-16"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": [contract] * n,
            "mm_long": [base_mm_long + 1000 * i for i in range(n)],
            "mm_short": [50_000 + 500 * i for i in range(n)],
            "other_long": [10_000] * n,
            "other_short": [8_000] * n,
            "comm_long": [200_000] * n,
            "comm_short": [220_000] * n,
            "nonrep_long": [5_000] * n,
            "nonrep_short": [4_500] * n,
            "open_interest": [500_000] * n,
        }
    )


def _legacy_df(
    contract: str = "GOLD",
    dates: list[str] | None = None,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2024-01-02", "2024-01-09"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": [contract] * n,
            "noncomm_long": [120_000 + 1_000 * i for i in range(n)],
            "noncomm_short": [60_000] * n,
            "comm_long": [200_000] * n,
            "comm_short": [220_000] * n,
            "nonrep_long": [5_000] * n,
            "nonrep_short": [4_500] * n,
            "open_interest": [500_000] * n,
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Disaggregated
# ---------------------------------------------------------------------------


def test_cot_disaggregated_append_and_get(store: DataStore) -> None:
    store.append_cot_disaggregated(_disaggregated_df())
    df = store.get_cot("GOLD", report="disaggregated")
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
    assert df["mm_long"].iloc[0] == 100_000


def test_cot_disaggregated_default_report_type(store: DataStore) -> None:
    """Default = disaggregated (vanligst brukt)."""
    store.append_cot_disaggregated(_disaggregated_df())
    df_default = store.get_cot("GOLD")
    df_explicit = store.get_cot("GOLD", report="disaggregated")
    assert df_default.equals(df_explicit)


def test_cot_disaggregated_last_n(store: DataStore) -> None:
    store.append_cot_disaggregated(_disaggregated_df())
    df = store.get_cot("GOLD", last_n=2)
    assert len(df) == 2
    assert df["report_date"].iloc[0] == pd.Timestamp("2024-01-09")
    assert df["report_date"].iloc[1] == pd.Timestamp("2024-01-16")


def test_cot_disaggregated_dedupe_on_same_date_and_contract(store: DataStore) -> None:
    """Samme (report_date, contract) overskrives, ikke dupliseres."""
    store.append_cot_disaggregated(_disaggregated_df())

    # Re-send første rapport med nye tall
    replay = _disaggregated_df(dates=["2024-01-02"], base_mm_long=999_999)
    store.append_cot_disaggregated(replay)

    df = store.get_cot("GOLD")
    assert len(df) == 3  # fortsatt 3 rader, ingen duplikat
    # Første rapporten har nå oppdaterte tall
    first = df[df["report_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert first["mm_long"] == 999_999


def test_cot_disaggregated_append_appends_new_dates(store: DataStore) -> None:
    store.append_cot_disaggregated(_disaggregated_df(dates=["2024-01-02", "2024-01-09"]))
    store.append_cot_disaggregated(_disaggregated_df(dates=["2024-01-16", "2024-01-23"]))
    df = store.get_cot("GOLD")
    assert len(df) == 4


def test_cot_disaggregated_missing_column_raises(store: DataStore) -> None:
    bad = pd.DataFrame(
        {
            "report_date": ["2024-01-02"],
            "contract": ["GOLD"],
            # Mangler mm_long og flere
        }
    )
    with pytest.raises(ValueError, match="missing columns"):
        store.append_cot_disaggregated(bad)


def test_cot_get_unknown_contract_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No COT data"):
        store.get_cot("UNKNOWN_CONTRACT")


# ---------------------------------------------------------------------------
# Legacy
# ---------------------------------------------------------------------------


def test_cot_legacy_append_and_get(store: DataStore) -> None:
    store.append_cot_legacy(_legacy_df())
    df = store.get_cot("GOLD", report="legacy")
    assert len(df) == 2
    assert "noncomm_long" in df.columns
    assert df["noncomm_long"].iloc[0] == 120_000


def test_cot_legacy_get_default_is_not_legacy(store: DataStore) -> None:
    """get_cot() uten `report`-arg skal IKKE treffe legacy — default er
    disaggregated. Tester at tabellene er separate."""
    store.append_cot_legacy(_legacy_df())
    # Ingen disaggregated-data; default should fail.
    with pytest.raises(KeyError, match="No COT data"):
        store.get_cot("GOLD")  # default disaggregated
    # Med eksplisitt report=legacy skal det funke
    assert len(store.get_cot("GOLD", report="legacy")) == 2


def test_cot_legacy_dedupe(store: DataStore) -> None:
    store.append_cot_legacy(_legacy_df())
    replay = _legacy_df(dates=["2024-01-02"])
    replay["noncomm_long"] = [777_777]
    store.append_cot_legacy(replay)

    df = store.get_cot("GOLD", report="legacy")
    assert len(df) == 2  # fortsatt 2 rader
    first = df[df["report_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert first["noncomm_long"] == 777_777


# ---------------------------------------------------------------------------
# Felles
# ---------------------------------------------------------------------------


def test_cot_unknown_report_type_raises(store: DataStore) -> None:
    with pytest.raises(ValueError, match="Unknown COT report type"):
        store.get_cot("GOLD", report="nonsense")  # type: ignore[arg-type]


def test_has_cot_negative(store: DataStore) -> None:
    assert not store.has_cot("GOLD")
    assert not store.has_cot("GOLD", report="legacy")


def test_has_cot_positive(store: DataStore) -> None:
    store.append_cot_disaggregated(_disaggregated_df(contract="GOLD"))
    assert store.has_cot("GOLD")
    assert not store.has_cot("SILVER")
    # Legacy skal være tom
    assert not store.has_cot("GOLD", report="legacy")


def test_cot_separate_contracts_do_not_interfere(store: DataStore) -> None:
    store.append_cot_disaggregated(_disaggregated_df(contract="GOLD"))
    store.append_cot_disaggregated(_disaggregated_df(contract="SILVER", base_mm_long=50_000))

    gold = store.get_cot("GOLD")
    silver = store.get_cot("SILVER")
    assert gold["mm_long"].iloc[0] == 100_000
    assert silver["mm_long"].iloc[0] == 50_000


def test_cot_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_cot_disaggregated(_disaggregated_df())

    store_b = DataStore(db)
    df = store_b.get_cot("GOLD")
    assert len(df) == 3
