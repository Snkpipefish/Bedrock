"""Tester for AsOfDateStore-wrapper (Fase 11 session 63).

Dekker hver getter: prices/prices_ohlc/cot/fundamentals/weather_monthly/
outcomes med dato-clip + lookback. Outcomes har strict look-ahead-clip
(ref_date + horizon_days ≤ as_of_date).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore


@pytest.fixture
def seeded_store(tmp_path: Path) -> DataStore:
    store = DataStore(tmp_path / "bedrock.db")
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="D")

    # Prices: full OHLCV
    store.append_prices(
        "Gold",
        "D1",
        pd.DataFrame(
            {
                "ts": dates,
                "open": [1800.0 + i for i in range(n)],
                "high": [1810.0 + i for i in range(n)],
                "low": [1790.0 + i for i in range(n)],
                "close": [1800.0 + i for i in range(n)],
                "volume": [1000.0] * n,
            }
        ),
    )

    # Fundamentals
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DGS10"] * n,
                "date": dates,
                "value": [4.0 + 0.01 * i for i in range(n)],
            }
        )
    )

    # COT (én rapport per uke)
    cot_dates = pd.date_range("2024-01-05", periods=10, freq="7D")
    store.append_cot_disaggregated(
        pd.DataFrame(
            {
                "report_date": cot_dates,
                "contract": ["GOLD - COMMODITY EXCHANGE INC."] * 10,
                "mm_long": [100 + i for i in range(10)],
                "mm_short": [50] * 10,
                "other_long": [10] * 10,
                "other_short": [10] * 10,
                "comm_long": [10] * 10,
                "comm_short": [10] * 10,
                "nonrep_long": [5] * 10,
                "nonrep_short": [5] * 10,
                "open_interest": [200] * 10,
            }
        )
    )

    # Weather monthly
    store.append_weather_monthly(
        pd.DataFrame(
            {
                "region": ["us_cornbelt"] * 4,
                "month": ["2024-01", "2024-02", "2024-03", "2024-04"],
                "temp_mean": [-2.0, 2.0, 8.0, 14.0],
                "temp_max": [None] * 4,
                "precip_mm": [None] * 4,
                "et0_mm": [None] * 4,
                "hot_days": [None] * 4,
                "dry_days": [None] * 4,
                "wet_days": [None] * 4,
                "water_bal": [10.0, 8.0, -2.0, -10.0],
            }
        )
    )

    # Outcomes (Gold 30d)
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                "forward_return_pct": [3.0 + 0.1 * i for i in range(n)],
                "max_drawdown_pct": [-1.0] * n,
            }
        )
    )
    return store


# ---------------------------------------------------------------------
# Construction + normalization
# ---------------------------------------------------------------------


def test_normalizes_date_to_midnight(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 6, 30))
    assert view.as_of_date == pd.Timestamp("2024-06-30 00:00:00")


def test_strips_timezone(seeded_store: DataStore) -> None:
    aware = pd.Timestamp("2024-06-30 12:00:00", tz="US/Eastern")
    view = AsOfDateStore(seeded_store, aware)
    # Konvertert til UTC: 2024-06-30 16:00, naive
    assert view.as_of_date.tz is None


# ---------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------


def test_prices_clipped(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 31))
    full = seeded_store.get_prices("Gold")
    clipped = view.get_prices("Gold")
    assert len(full) == 100
    assert len(clipped) == 31  # jan 1..31 inkl
    assert clipped.index[-1] == pd.Timestamp("2024-01-31 00:00:00")


def test_prices_lookback_after_clip(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 31))
    s = view.get_prices("Gold", lookback=5)
    assert len(s) == 5
    assert s.index[-1] == pd.Timestamp("2024-01-31 00:00:00")
    assert s.index[0] == pd.Timestamp("2024-01-27 00:00:00")


def test_prices_clipped_to_empty_raises(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2020, 1, 1))  # før all data
    with pytest.raises(KeyError, match="as of"):
        view.get_prices("Gold")


def test_prices_ohlc_clipped(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 15))
    df = view.get_prices_ohlc("Gold")
    assert len(df) == 15
    assert "open" in df.columns
    assert df.index[-1] == pd.Timestamp("2024-01-15 00:00:00")


def test_has_prices_true_when_data_exists(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 31))
    assert view.has_prices("Gold", "D1") is True


def test_has_prices_false_when_clipped_empty(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2020, 1, 1))
    assert view.has_prices("Gold", "D1") is False


# ---------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------


def test_fundamentals_clipped(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 2, 15))
    s = view.get_fundamentals("DGS10")
    assert len(s) == 46  # jan 1..feb 15 = 31 + 15
    assert s.index[-1] == pd.Timestamp("2024-02-15")


def test_fundamentals_unknown_series_raises(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 6, 30))
    with pytest.raises(KeyError):
        view.get_fundamentals("NONEXISTENT")


# ---------------------------------------------------------------------
# COT
# ---------------------------------------------------------------------


def test_cot_clipped(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 25))
    df = view.get_cot("GOLD - COMMODITY EXCHANGE INC.")
    # COT dates: 2024-01-05, 2024-01-12, 2024-01-19 (≤ jan 25), neste er 2024-01-26 (>)
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-19")


def test_cot_clipped_to_empty_raises(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 1))  # før første rapport
    with pytest.raises(KeyError, match="as of"):
        view.get_cot("GOLD - COMMODITY EXCHANGE INC.")


# ---------------------------------------------------------------------
# Weather monthly
# ---------------------------------------------------------------------


def test_weather_monthly_clipped(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 2, 15))
    df = view.get_weather_monthly("us_cornbelt")
    # First-of-month: 2024-01-01 (≤ feb 15), 2024-02-01 (≤ feb 15), 2024-03-01 (>), 2024-04-01 (>)
    assert len(df) == 2
    assert df["month"].tolist() == ["2024-01", "2024-02"]


def test_weather_monthly_lookback(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 4, 15))
    df = view.get_weather_monthly("us_cornbelt", last_n=2)
    assert len(df) == 2
    assert df["month"].tolist() == ["2024-03", "2024-04"]


# ---------------------------------------------------------------------
# Outcomes (look-ahead-strict)
# ---------------------------------------------------------------------


def test_outcomes_strict_clipped_30d(seeded_store: DataStore) -> None:
    """For horizon=30d på as_of=2024-02-15: kun ref_dates ≤ 2024-01-16
    (= 2024-02-15 - 30d) er gyldige. forward_return for nyere ref_dates
    var ikke kjent på as_of."""
    view = AsOfDateStore(seeded_store, date(2024, 2, 15))
    df = view.get_outcomes("Gold", horizon_days=30)
    # 2024-01-01..2024-01-16 = 16 datoer
    assert len(df) == 16
    assert df["ref_date"].iloc[-1] == pd.Timestamp("2024-01-16")


def test_outcomes_horizon_per_row(seeded_store: DataStore) -> None:
    """Når horizon_days er None ved oppslag, bruker hver rads horizon_days."""
    # Legg til en 90d-row også
    seeded_store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * 50,
                "ref_date": pd.date_range("2024-01-01", periods=50, freq="D"),
                "horizon_days": [90] * 50,
                "forward_return_pct": [5.0] * 50,
                "max_drawdown_pct": [-2.0] * 50,
            }
        )
    )
    view = AsOfDateStore(seeded_store, date(2024, 4, 30))
    df = view.get_outcomes("Gold")
    # 30d-rader: ≤ 2024-04-30 - 30d = 2024-03-31 → 91 rader (jan 1..mar 31)
    n_30 = (df["horizon_days"] == 30).sum()
    # 90d-rader: ≤ 2024-04-30 - 90d = 2024-01-31 (2024 er skuddår) → 31 rader
    n_90 = (df["horizon_days"] == 90).sum()
    assert n_30 == 91
    assert n_90 == 31


def test_outcomes_clipped_to_empty(seeded_store: DataStore) -> None:
    """Hvis alle outcomes er fremtidige relativt as_of, returner empty."""
    view = AsOfDateStore(seeded_store, date(2023, 1, 1))
    df = view.get_outcomes("Gold", horizon_days=30)
    assert df.empty


def test_outcomes_unknown_instrument_returns_empty(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 6, 30))
    df = view.get_outcomes("Silver", horizon_days=30)
    assert df.empty
