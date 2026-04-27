"""Tester for conab_estimates-støtte i DataStore (sub-fase 12.5+ session 111)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore


def _conab_df(
    commodity: str = "soja",
    dates: list[str] | None = None,
    base_production: float = 179_151.6,
    units: str = "kt",
) -> pd.DataFrame:
    if dates is None:
        dates = ["2026-02-15", "2026-03-15", "2026-04-15"]
    n = len(dates)
    return pd.DataFrame(
        {
            "report_date": dates,
            "commodity": [commodity] * n,
            "levantamento": [f"{i + 5}o" for i in range(n)],
            "safra": ["2025/26"] * n,
            "production": [base_production + 100 * i for i in range(n)],
            "production_units": [units] * n,
            "area_kha": [48_472.7 + 50 * i for i in range(n)],
            "yield_value": [3696 + i for i in range(n)],
            "yield_units": ["kgha"] * n,
            "yoy_change_pct": [4.5 - 0.1 * i for i in range(n)],
            "mom_change_pct": [None] + [0.1 * i for i in range(1, n)],
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


# ---------------------------------------------------------------------------
# Append + get
# ---------------------------------------------------------------------------


def test_append_and_get(store: DataStore) -> None:
    store.append_conab_estimates(_conab_df())
    df = store.get_conab_estimates("soja")
    assert len(df) == 3
    assert df["production"].iloc[0] == 179_151.6
    assert df["production_units"].iloc[0] == "kt"
    assert df["levantamento"].iloc[0] == "5o"


def test_last_n(store: DataStore) -> None:
    store.append_conab_estimates(_conab_df())
    df = store.get_conab_estimates("soja", last_n=2)
    assert len(df) == 2
    assert df["report_date"].iloc[0] == pd.Timestamp("2026-03-15")


def test_dedupe_on_date_and_commodity(store: DataStore) -> None:
    """Samme (report_date, commodity) overskrives — Conab kan revidere."""
    store.append_conab_estimates(_conab_df())
    revision = _conab_df(dates=["2026-02-15"], base_production=999_999.9)
    store.append_conab_estimates(revision)
    df = store.get_conab_estimates("soja")
    assert len(df) == 3
    first = df[df["report_date"] == pd.Timestamp("2026-02-15")].iloc[0]
    assert first["production"] == 999_999.9


def test_separate_commodities(store: DataStore) -> None:
    store.append_conab_estimates(_conab_df(commodity="soja", base_production=179_000))
    store.append_conab_estimates(_conab_df(commodity="milho", base_production=139_500))

    soja = store.get_conab_estimates("soja")
    milho = store.get_conab_estimates("milho")

    assert len(soja) == 3
    assert len(milho) == 3
    assert soja["production"].iloc[0] == 179_000
    assert milho["production"].iloc[0] == 139_500


def test_coffee_uses_ksacas_units(store: DataStore) -> None:
    """Kaffe lagres i 'ksacas' (1000 60-kg-sekker), ikke 'kt'."""
    df = pd.DataFrame(
        {
            "report_date": ["2026-04-15"],
            "commodity": ["cafe_total"],
            "levantamento": ["1o"],
            "safra": ["2026"],
            "production": [50_500.0],
            "production_units": ["ksacas"],
            "area_kha": [1850.0],
            "yield_value": [27.3],
            "yield_units": ["sacasha"],
            "yoy_change_pct": [-3.2],
            "mom_change_pct": [None],
        }
    )
    store.append_conab_estimates(df)
    out = store.get_conab_estimates("cafe_total")
    assert out["production_units"].iloc[0] == "ksacas"
    assert out["yield_units"].iloc[0] == "sacasha"


def test_missing_columns_raises(store: DataStore) -> None:
    bad = pd.DataFrame({"report_date": ["2026-04-15"], "commodity": ["soja"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_conab_estimates(bad)


def test_get_unknown_commodity_raises(store: DataStore) -> None:
    with pytest.raises(KeyError, match="No Conab data"):
        store.get_conab_estimates("plutonium")


def test_nullable_fields_preserved(store: DataStore) -> None:
    """levantamento, safra, area_kha, yield_*, mom_change_pct kan være None."""
    df = pd.DataFrame(
        {
            "report_date": ["2026-04-15"],
            "commodity": ["trigo"],
            "levantamento": [None],
            "safra": [None],
            "production": [10_000.0],
            "production_units": ["kt"],
            "area_kha": [None],
            "yield_value": [None],
            "yield_units": [None],
            "yoy_change_pct": [None],
            "mom_change_pct": [None],
        }
    )
    store.append_conab_estimates(df)
    out = store.get_conab_estimates("trigo")
    assert pd.isna(out["levantamento"].iloc[0])
    assert pd.isna(out["mom_change_pct"].iloc[0])
    assert out["production"].iloc[0] == 10_000.0


# ---------------------------------------------------------------------------
# has_conab_estimates
# ---------------------------------------------------------------------------


def test_has_negative(store: DataStore) -> None:
    assert not store.has_conab_estimates("soja")


def test_has_positive(store: DataStore) -> None:
    store.append_conab_estimates(_conab_df(commodity="soja"))
    assert store.has_conab_estimates("soja")
    assert not store.has_conab_estimates("milho")


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------


def test_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    DataStore(db).append_conab_estimates(_conab_df())
    df = DataStore(db).get_conab_estimates("soja")
    assert len(df) == 3
