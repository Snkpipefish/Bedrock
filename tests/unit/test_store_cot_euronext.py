"""Tester for Euronext-COT-støtte i DataStore (sub-fase 12.5+ session 110)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _euronext_df(
    contract: str = "euronext milling wheat",
    dates: list[str] | None = None,
    base_long: int = 80_000,
    base_short: int = 110_000,
    base_oi: int = 475_000,
) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-04-08", "2026-04-15", "2026-04-22"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "contract": [contract] * n,
            "mm_long": [base_long + 1000 * i for i in range(n)],
            "mm_short": [base_short - 500 * i for i in range(n)],
            "open_interest": [base_oi + 2000 * i for i in range(n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_append_and_get(store: DataStore) -> None:
    store.append_cot_euronext(_euronext_df())
    df = store.get_cot_euronext("euronext milling wheat")
    assert len(df) == 3
    assert list(df.columns) == [
        "report_date",
        "contract",
        "mm_long",
        "mm_short",
        "open_interest",
    ]
    assert df["mm_long"].iloc[0] == 80_000


def test_last_n(store: DataStore) -> None:
    store.append_cot_euronext(_euronext_df())
    df = store.get_cot_euronext("euronext milling wheat", last_n=2)
    assert len(df) == 2
    assert df["report_date"].iloc[0] == pd.Timestamp("2026-04-15")


def test_dedupe_on_report_date_and_contract(store: DataStore) -> None:
    """Samme (report_date, contract) overskrives, ikke duplikat."""
    store.append_cot_euronext(_euronext_df())
    revision = _euronext_df(dates=["2026-04-08"], base_long=999_999)
    store.append_cot_euronext(revision)
    df = store.get_cot_euronext("euronext milling wheat")
    assert len(df) == 3  # ikke 4
    first = df[df["report_date"] == pd.Timestamp("2026-04-08")].iloc[0]
    assert first["mm_long"] == 999_999


def test_separate_contracts(store: DataStore) -> None:
    store.append_cot_euronext(_euronext_df(contract="euronext milling wheat"))
    store.append_cot_euronext(
        _euronext_df(contract="euronext corn", base_long=7_000, base_short=2_000)
    )

    wheat = store.get_cot_euronext("euronext milling wheat")
    corn = store.get_cot_euronext("euronext corn")

    assert len(wheat) == 3
    assert len(corn) == 3
    assert wheat["mm_long"].iloc[0] == 80_000
    assert corn["mm_long"].iloc[0] == 7_000


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"report_date": ["2026-04-08"], "contract": ["wheat"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_cot_euronext(bad)


def test_get_unknown_contract_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No Euronext COT data"):
        store.get_cot_euronext("euronext unicorn")


def test_appends_new_dates(store: DataStore) -> None:
    store.append_cot_euronext(_euronext_df(dates=["2026-04-08", "2026-04-15"]))
    store.append_cot_euronext(_euronext_df(dates=["2026-04-22", "2026-04-29"]))
    df = store.get_cot_euronext("euronext milling wheat")
    assert len(df) == 4


# ---------------------------------------------------------------------------
# has_cot_euronext
# ---------------------------------------------------------------------------


def test_has_cot_euronext_negative(store: DataStore) -> None:
    assert not store.has_cot_euronext("euronext milling wheat")


def test_has_cot_euronext_positive(store: DataStore) -> None:
    store.append_cot_euronext(_euronext_df(contract="euronext milling wheat"))
    assert store.has_cot_euronext("euronext milling wheat")
    assert not store.has_cot_euronext("euronext corn")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_cot_euronext(_euronext_df())
    df = DataStore(db).get_cot_euronext("euronext milling wheat")
    assert len(df) == 3
