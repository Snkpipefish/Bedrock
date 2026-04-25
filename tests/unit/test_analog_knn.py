"""Tester for find_analog_cases (Fase 10 ADR-005, session 59).

Bruker controlled fixture-DB der vi kan verifisere K-NN-output mot
kjente naboer. Sanity mot ekte data håndteres i test_analog_realdata.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bedrock.config.instruments import InstrumentMetadata
from bedrock.data.analog import (
    InsufficientHistoryError,
    find_analog_cases,
)
from bedrock.data.store import DataStore


@pytest.fixture
def gold_meta() -> InstrumentMetadata:
    return InstrumentMetadata(
        id="Gold",
        asset_class="metals",
        ticker="XAUUSD",
        cot_contract="GOLD - COMMODITY EXCHANGE INC.",
        cot_report="disaggregated",
    )


def _seed_store_with_known_neighbors(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    """Seed DataStore med 100 dager DTWEXBGS + 100 daglige outcomes for Gold,
    konstruert slik at vi vet eksakt hvilke datoer som er nærmest til en gitt query.

    Setup:
    - DTWEXBGS er en sinusbølge (varieres mellom 95 og 105) → dxy_chg5d har
      kjente verdier
    - For å bruke kun dxy_chg5d som dim trenger vi forskjellige outcomes
      per dato. Vi setter forward_return = ref_date_index (slik at vi
      kan se hvilken ref_date som ble valgt)
    """
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    # DTWEXBGS-verdier: lineær stigning med 0.5/dag → 5d-pct kjent
    dtwexbgs = pd.DataFrame(
        {
            "series_id": ["DTWEXBGS"] * n,
            "date": dates,
            "value": [100.0 + i * 0.5 for i in range(n)],
        }
    )
    store.append_fundamentals(dtwexbgs)

    # Outcomes med forward_return = ref_date_day_of_year (1-200) for unique values
    outcomes = pd.DataFrame(
        {
            "instrument": ["Gold"] * n,
            "ref_date": dates,
            "horizon_days": [30] * n,
            "forward_return_pct": [float(i) * 0.1 for i in range(n)],
            "max_drawdown_pct": [-1.0] * n,
        }
    )
    store.append_outcomes(outcomes)


def test_find_analog_returns_top_k(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)

    # Query: dxy_chg5d midten av historikkens range
    query = {"dxy_chg5d": 2.0}
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        query,
        k=5,
        horizon_days=30,
        min_history_days=0,
    )
    assert len(result) == 5
    assert list(result.columns) == [
        "ref_date",
        "similarity",
        "forward_return_pct",
        "max_drawdown_pct",
    ]
    # Similarity sortert descending
    sims = result["similarity"].tolist()
    assert sims == sorted(sims, reverse=True)


def test_similarity_in_zero_one_range(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 2.0},
        k=10,
        min_history_days=0,
    )
    assert (result["similarity"] >= 0).all()
    assert (result["similarity"] <= 1.0).all()


def test_perfect_match_has_similarity_one(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """Hvis query == en historisk verdi, similarity skal være ~1.0 for den raden."""
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    # Beregn dxy_chg5d for ref_date = 2020-01-15 (index 14): pct_change(5)
    # mellom verdi[9]=104.5 og verdi[14]=107.0 → (107/104.5 - 1)*100
    target_pct = (107.0 / 104.5 - 1) * 100
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": target_pct},
        k=1,
        min_history_days=0,
    )
    # Best match should have similarity very close to 1.0
    assert result["similarity"].iloc[0] > 0.999


def test_validates_query_dim_against_asset_class(
    tmp_path: Path, gold_meta: InstrumentMetadata
) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    # weather_stress er softs/grains, ikke metals
    with pytest.raises(ValueError, match="outside § 6.5"):
        find_analog_cases(
            store,
            "Gold",
            gold_meta,
            "metals",
            {"dxy_chg5d": 0.5, "weather_stress": 1.0},
        )


def test_unknown_asset_class_raises(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    with pytest.raises(KeyError, match="cryptos"):
        find_analog_cases(store, "Gold", gold_meta, "cryptos", {})


def test_empty_query_dims_raises(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    with pytest.raises(ValueError, match="empty"):
        find_analog_cases(store, "Gold", gold_meta, "metals", {})


def test_no_outcomes_returns_empty(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """Hvis instrument ikke har outcomes, returner tom DataFrame (ikke exception)."""
    store = DataStore(tmp_path / "bedrock.db")
    # Seed bare DTWEXBGS, ikke outcomes
    n = 50
    dtwexbgs = pd.DataFrame(
        {
            "series_id": ["DTWEXBGS"] * n,
            "date": pd.date_range("2020-01-01", periods=n, freq="D"),
            "value": [100.0 + i * 0.5 for i in range(n)],
        }
    )
    store.append_fundamentals(dtwexbgs)
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 1.0},
    )
    assert result.empty
    assert list(result.columns) == [
        "ref_date",
        "similarity",
        "forward_return_pct",
        "max_drawdown_pct",
    ]


def test_min_history_days_filter(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """min_history_days skal ekskludere de tidlige ref_dates fra K-NN."""
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    # Med min_history_days=180 (av 200), kun ~20 kandidater igjen
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 2.0},
        k=100,
        min_history_days=180,
    )
    # Alle valgte ref_dates skal være >= 2020-01-01 + 180d
    earliest_allowed = pd.Timestamp("2020-01-01") + pd.Timedelta(days=180)
    assert (result["ref_date"] >= earliest_allowed).all()


def test_dim_weights_skew_toward_weighted_dim(
    tmp_path: Path, gold_meta: InstrumentMetadata
) -> None:
    """Hvis vi gir vekt 100 til én dim og 0 til andre, K-NN skal velge
    rader nærmest på den ene dim."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 100
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    # To dim: DTWEXBGS lineær stigning, DGS10 sinusoidal
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DTWEXBGS"] * n,
                "date": dates,
                "value": [100.0 + i * 0.1 for i in range(n)],
            }
        )
    )
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DGS10"] * n,
                "date": dates,
                "value": [4.0 + np.sin(i / 5) for i in range(n)],
            }
        )
    )
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["T10YIE"] * n,
                "date": dates,
                "value": [2.0] * n,
            }
        )
    )
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                "forward_return_pct": [0.0] * n,
                "max_drawdown_pct": [-1.0] * n,
            }
        )
    )

    query = {"dxy_chg5d": 0.5, "real_yield_chg5d": 0.0}
    # Vekt 100 på dxy → real_yield ignoreres effektivt
    result_dxy = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        query,
        k=5,
        dim_weights={"dxy_chg5d": 100.0, "real_yield_chg5d": 0.001},
        min_history_days=0,
    )
    # Vekt 100 på real_yield → dxy ignoreres
    result_ry = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        query,
        k=5,
        dim_weights={"dxy_chg5d": 0.001, "real_yield_chg5d": 100.0},
        min_history_days=0,
    )
    # Naboene skal være FORSKJELLIGE for de to vektingene
    set_dxy = set(result_dxy["ref_date"])
    set_ry = set(result_ry["ref_date"])
    assert set_dxy != set_ry


def test_single_dim_query(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """K-NN med kun 1 dim skal funke (degraded, men ikke krasj)."""
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 1.0},
        k=3,
        min_history_days=0,
    )
    assert len(result) == 3


def test_horizon_days_filter(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """Outcomes med ulik horizon_days skal være isolerte."""
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)  # seeder horizon=30

    # Legg til outcomes for horizon=90 også, med distinkte returns
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [90] * n,
                "forward_return_pct": [-1.0] * n,  # markant ulik fra horizon=30
                "max_drawdown_pct": [-5.0] * n,
            }
        )
    )

    result30 = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 1.0},
        k=5,
        horizon_days=30,
        min_history_days=0,
    )
    result90 = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 1.0},
        k=5,
        horizon_days=90,
        min_history_days=0,
    )
    # 30d har positive returns (0.0..19.9), 90d har -1.0
    assert (result30["forward_return_pct"] >= 0.0).all()
    assert (result90["forward_return_pct"] == -1.0).all()


def test_zero_history_after_filter_returns_empty(
    tmp_path: Path, gold_meta: InstrumentMetadata
) -> None:
    """Hvis min_history_days er så høy at ingen ref_dates kvalifiserer,
    returner empty (ikke krasj)."""
    store = DataStore(tmp_path / "bedrock.db")
    _seed_store_with_known_neighbors(store, gold_meta)
    result = find_analog_cases(
        store,
        "Gold",
        gold_meta,
        "metals",
        {"dxy_chg5d": 1.0},
        k=5,
        min_history_days=10000,  # langt utenfor
    )
    assert result.empty


def test_no_dim_overlap_raises(tmp_path: Path, gold_meta: InstrumentMetadata) -> None:
    """Hvis dim-historiene ikke har overlappende datoer (umulig i praksis,
    men test at vi feiler ryddig)."""
    store = DataStore(tmp_path / "bedrock.db")
    # Seed DTWEXBGS jan 2020, T10YIE/DGS10 jan 2024 → ingen overlap for real_yield
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DTWEXBGS"] * 30,
                "date": pd.date_range("2020-01-01", periods=30, freq="D"),
                "value": [100.0 + i * 0.1 for i in range(30)],
            }
        )
    )
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DGS10"] * 30,
                "date": pd.date_range("2024-01-01", periods=30, freq="D"),
                "value": [4.0] * 30,
            }
        )
    )
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["T10YIE"] * 30,
                "date": pd.date_range("2024-01-01", periods=30, freq="D"),
                "value": [2.0] * 30,
            }
        )
    )
    # Outcomes for noen dato
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * 5,
                "ref_date": pd.date_range("2020-01-15", periods=5, freq="D"),
                "horizon_days": [30] * 5,
                "forward_return_pct": [0.0] * 5,
                "max_drawdown_pct": [0.0] * 5,
            }
        )
    )
    with pytest.raises(InsufficientHistoryError):
        find_analog_cases(
            store,
            "Gold",
            gold_meta,
            "metals",
            {"dxy_chg5d": 1.0, "real_yield_chg5d": 0.0},
            min_history_days=0,
        )
