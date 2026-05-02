# pyright: reportArgumentType=false
"""Tester for NASS yield + grain_stocks-drivere (sub-fase 12.10 follow-up Spor D, session 137)."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered


@pytest.mark.parametrize(
    "driver_name",
    [
        "nass_yield_corn_yoy",
        "nass_yield_soy_yoy",
        "nass_grain_stocks_quarterly",
    ],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name)
    assert callable(get(driver_name))


# ---------------------------------------------------------------------------
# yield-driver-stub
# ---------------------------------------------------------------------------


class _YieldStore:
    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df

    def get_nass_yield(
        self,
        commodity: str,
        *,
        reference_period: str | None = None,
    ) -> pd.DataFrame:
        if self._df is None:
            return pd.DataFrame()
        df = self._df[self._df["commodity"] == commodity.upper()].copy()
        if reference_period is not None:
            df = df[df["reference_period"] == reference_period]
        return df.reset_index(drop=True)


def _yield_df(rows: list[tuple[str, int, str, float]]) -> pd.DataFrame:
    """Build yield-DataFrame fra (commodity, year, ref_period, value)."""
    return pd.DataFrame(
        [
            {
                "commodity": c,
                "year": y,
                "reference_period": rp,
                "yield_value": v,
                "yield_units": "BU / ACRE",
                "util_practice": "GRAIN",
                "load_time": pd.Timestamp(f"{y}-09-01"),
            }
            for (c, y, rp, v) in rows
        ]
    )


def test_yield_corn_yoy_drawdown_high_score() -> None:
    """2023 yield 150 vs 2022 yield 175 → -14% YoY → step ≤-10 → 1.0."""
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR", 150.0),
        ]
    )
    score = fn(_YieldStore(df), "Corn", {})
    assert score == 1.0


def test_yield_corn_yoy_growth_low_score() -> None:
    """2023 yield 185 vs 2022 yield 175 → +5.7% → step >+5 → 0.15."""
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR", 185.0),
        ]
    )
    score = fn(_YieldStore(df), "Corn", {})
    assert score == 0.15


def test_yield_corn_yoy_neutral_when_flat() -> None:
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR", 175.0),
        ]
    )
    assert fn(_YieldStore(df), "Corn", {}) == 0.5


def test_yield_corn_yoy_uses_forecast_when_year_missing() -> None:
    """Hvis 2023 YEAR-final mangler, fall back til siste forecast (NOV/OCT/...)."""
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR - NOV FORECAST", 150.0),
            ("CORN", 2023, "YEAR - AUG FORECAST", 160.0),
        ]
    )
    # Bruker NOV (priority høyere) → 150 vs 175 = -14% → 1.0
    score = fn(_YieldStore(df), "Corn", {})
    assert score == 1.0


def test_yield_corn_yoy_no_data_returns_zero() -> None:
    fn = get("nass_yield_corn_yoy")
    assert fn(_YieldStore(None), "Corn", {}) == 0.0


def test_yield_corn_yoy_neutral_when_no_prior_year() -> None:
    """Har current men ingen ifjor-anker → 0.5."""
    fn = get("nass_yield_corn_yoy")
    df = _yield_df([("CORN", 2023, "YEAR", 175.0)])
    score = fn(_YieldStore(df), "Corn", {})
    assert score == 0.5


def test_yield_corn_yoy_bull_when_high_inverts() -> None:
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR", 150.0),
        ]
    )
    high = fn(_YieldStore(df), "Corn", {"bull_when": "high"})
    assert high == 0.0


def test_yield_soy_yoy_separate_commodity() -> None:
    fn = get("nass_yield_soy_yoy")
    df = _yield_df(
        [
            ("SOYBEANS", 2022, "YEAR", 50.0),
            ("SOYBEANS", 2023, "YEAR", 47.0),
        ]
    )
    # -6% YoY → step ≤-5 → 0.85
    assert fn(_YieldStore(df), "Soybean", {}) == 0.85


def test_yield_corn_yoy_user_thresholds_override() -> None:
    fn = get("nass_yield_corn_yoy")
    df = _yield_df(
        [
            ("CORN", 2022, "YEAR", 175.0),
            ("CORN", 2023, "YEAR", 165.0),
        ]
    )
    # YoY ≈ -5.7%
    custom = [(-3.0, 1.0), (3.0, 0.5)]  # ≤-3 → 1.0
    score = fn(_YieldStore(df), "Corn", {"thresholds": custom})
    assert score == 1.0


# ---------------------------------------------------------------------------
# nass_grain_stocks_quarterly
# ---------------------------------------------------------------------------


class _StocksStore:
    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df

    def get_nass_grain_stocks(self, commodity: str, *, category: str = "TOTAL") -> pd.DataFrame:
        if self._df is None:
            return pd.DataFrame()
        df = self._df[
            (self._df["commodity"] == commodity.upper())
            & (self._df["category"] == category.upper())
        ].copy()
        return df.reset_index(drop=True)


def _stocks_df(
    rows: list[tuple[str, int, str, str, float]],
) -> pd.DataFrame:
    """Rows: (commodity, year, reference_period, category, stocks_bu)."""
    return pd.DataFrame(
        [
            {
                "commodity": c,
                "year": y,
                "reference_period": rp,
                "category": cat,
                "stocks_bu": v,
                "load_time": pd.Timestamp(f"{y}-04-01"),
            }
            for (c, y, rp, cat, v) in rows
        ]
    )


def test_stocks_no_commodity_param_returns_zero() -> None:
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df([("CORN", 2023, "FIRST OF MAR", "TOTAL", 7e9)])
    assert fn(_StocksStore(df), "Corn", {}) == 0.0


def test_stocks_drawdown_high_score() -> None:
    """Mar 2023 = 5e9 vs Mar 2022 = 7e9 → -28.6% → ≤-15 step → 1.0."""
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df(
        [
            ("CORN", 2022, "FIRST OF MAR", "TOTAL", 7e9),
            ("CORN", 2023, "FIRST OF MAR", "TOTAL", 5e9),
        ]
    )
    assert fn(_StocksStore(df), "Corn", {"commodity": "CORN"}) == 1.0


def test_stocks_growth_low_score() -> None:
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df(
        [
            ("CORN", 2022, "FIRST OF MAR", "TOTAL", 7e9),
            ("CORN", 2023, "FIRST OF MAR", "TOTAL", 8e9),
        ]
    )
    # +14.3% → step >+5 → 0.15
    assert fn(_StocksStore(df), "Corn", {"commodity": "CORN"}) == 0.15


def test_stocks_uses_latest_quarter_priority() -> None:
    """Sammenligning skjer for samme quarter (DEC 2023 vs DEC 2022), ikke
    DEC 2023 vs MAR 2022."""
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df(
        [
            ("CORN", 2022, "FIRST OF MAR", "TOTAL", 7e9),
            ("CORN", 2022, "FIRST OF DEC", "TOTAL", 12e9),
            ("CORN", 2023, "FIRST OF DEC", "TOTAL", 10e9),
        ]
    )
    # Latest = DEC 2023 (10e9), prev = DEC 2022 (12e9). -16.7% → ≤-15 → 1.0
    assert fn(_StocksStore(df), "Corn", {"commodity": "CORN"}) == 1.0


def test_stocks_neutral_when_no_prior_year() -> None:
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df([("CORN", 2023, "FIRST OF MAR", "TOTAL", 7e9)])
    assert fn(_StocksStore(df), "Corn", {"commodity": "CORN"}) == 0.5


def test_stocks_no_data_returns_zero() -> None:
    fn = get("nass_grain_stocks_quarterly")
    assert fn(_StocksStore(None), "Corn", {"commodity": "CORN"}) == 0.0


def test_stocks_category_param_routes() -> None:
    """category='ON FARM' → kun ON FARM-rader brukes."""
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df(
        [
            ("CORN", 2022, "FIRST OF MAR", "TOTAL", 7e9),
            ("CORN", 2023, "FIRST OF MAR", "TOTAL", 7e9),  # flat TOTAL
            ("CORN", 2022, "FIRST OF MAR", "ON FARM", 3e9),
            ("CORN", 2023, "FIRST OF MAR", "ON FARM", 2e9),  # -33% ON FARM
        ]
    )
    # category=TOTAL → 0% YoY → 0.5
    score_total = fn(_StocksStore(df), "Corn", {"commodity": "CORN", "category": "TOTAL"})
    assert score_total == 0.5
    # category='ON FARM' → -33% → 1.0
    score_on_farm = fn(_StocksStore(df), "Corn", {"commodity": "CORN", "category": "ON FARM"})
    assert score_on_farm == 1.0


def test_stocks_bull_when_high_inverts() -> None:
    fn = get("nass_grain_stocks_quarterly")
    df = _stocks_df(
        [
            ("CORN", 2022, "FIRST OF MAR", "TOTAL", 7e9),
            ("CORN", 2023, "FIRST OF MAR", "TOTAL", 5e9),
        ]
    )
    score_low = fn(_StocksStore(df), "Corn", {"commodity": "CORN"})
    score_high = fn(_StocksStore(df), "Corn", {"commodity": "CORN", "bull_when": "high"})
    assert score_low == 1.0
    assert score_high == 0.0
