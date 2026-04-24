"""Tester for `bedrock.setups.levels` — nivå-detektorer."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from bedrock.setups.levels import (
    Level,
    LevelType,
    detect_prior_period_levels,
    detect_round_numbers,
    detect_swing_levels,
    rank_levels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ohlc_from_highs_lows(
    highs: list[float],
    lows: list[float] | None = None,
    start: str = "2024-01-01",
    freq: str = "D",
) -> pd.DataFrame:
    """Bygg OHLC DataFrame fra eksplisitte high-/low-serier."""
    n = len(highs)
    lows = lows if lows is not None else [h - 1.0 for h in highs]
    ts = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame(
        {
            "open": [(h + l) / 2 for h, l in zip(highs, lows, strict=True)],
            "high": highs,
            "low": lows,
            "close": [(h + l) / 2 for h, l in zip(highs, lows, strict=True)],
        },
        index=ts,
    )


# ---------------------------------------------------------------------------
# Level model
# ---------------------------------------------------------------------------


def test_level_model_rejects_out_of_range_strength() -> None:
    with pytest.raises(ValueError, match="strength"):
        Level(price=100.0, type=LevelType.SWING_HIGH, strength=1.5)


def test_level_type_is_json_serializable_string() -> None:
    lvl = Level(price=100.0, type=LevelType.SWING_HIGH, strength=0.7)
    assert lvl.model_dump()["type"] == "swing_high"


# ---------------------------------------------------------------------------
# detect_swing_levels
# ---------------------------------------------------------------------------


def test_swing_high_single_peak_detected() -> None:
    # Flat 100 med enkelt-peak i midten: 100, 100, 102, 100, 100
    highs = [100.0, 100.0, 102.0, 100.0, 100.0]
    ohlc = _ohlc_from_highs_lows(highs)
    levels = detect_swing_levels(ohlc, window=2)

    swing_highs = [lvl for lvl in levels if lvl.type == LevelType.SWING_HIGH]
    assert len(swing_highs) == 1
    assert swing_highs[0].price == 102.0


def test_swing_low_single_trough_detected() -> None:
    lows = [100.0, 100.0, 98.0, 100.0, 100.0]
    highs = [lo + 1.0 for lo in lows]
    ohlc = _ohlc_from_highs_lows(highs, lows)
    levels = detect_swing_levels(ohlc, window=2)

    swing_lows = [lvl for lvl in levels if lvl.type == LevelType.SWING_LOW]
    assert len(swing_lows) == 1
    assert swing_lows[0].price == 98.0


def test_swing_prominence_higher_peak_gets_higher_strength() -> None:
    """Markant peak skal få høyere strength enn så vidt-peak."""
    # To separate peaks med ulik prominens
    # Peak 1 ved i=2: 100, 100, 102, 100, 100  → 2% prominence
    # Peak 2 ved i=7: 100, 100, 100.5, 100, 100 → 0.5% prominence
    highs = [100, 100, 102, 100, 100, 100, 100, 100.5, 100, 100]
    ohlc = _ohlc_from_highs_lows(highs)
    levels = detect_swing_levels(ohlc, window=2)
    swing_highs = sorted(
        [lvl for lvl in levels if lvl.type == LevelType.SWING_HIGH],
        key=lambda lvl: lvl.price,
    )
    assert len(swing_highs) == 2
    # Høyere peak → høyere prominence → høyere strength
    assert swing_highs[1].strength > swing_highs[0].strength


def test_swing_strength_in_valid_range() -> None:
    highs = [100, 100, 110, 100, 100]  # 10% prominence — veldig sterk
    ohlc = _ohlc_from_highs_lows(highs)
    levels = detect_swing_levels(ohlc, window=2)
    for lvl in levels:
        assert 0.5 <= lvl.strength <= 1.0


def test_swing_no_detection_with_too_short_series() -> None:
    """Mindre enn 2×window+1 bars → ingen swings."""
    ohlc = _ohlc_from_highs_lows([100.0, 101.0, 100.0])
    assert detect_swing_levels(ohlc, window=3) == []


def test_swing_no_detection_on_flat_series() -> None:
    ohlc = _ohlc_from_highs_lows([100.0] * 10)
    assert detect_swing_levels(ohlc, window=2) == []


def test_swing_no_detection_on_monotonic_up() -> None:
    """Strictly stigende serie har ingen interne swings."""
    highs = [100.0 + i for i in range(10)]
    ohlc = _ohlc_from_highs_lows(highs)
    levels = detect_swing_levels(ohlc, window=2)
    # Eneste mulige er kant-barer, men de dekkes ikke av [window, n-window)
    assert levels == []


def test_swing_ts_comes_from_dataframe_index() -> None:
    highs = [100.0, 100.0, 105.0, 100.0, 100.0]
    ohlc = _ohlc_from_highs_lows(highs, start="2024-03-15")
    levels = detect_swing_levels(ohlc, window=2)
    assert levels[0].ts == datetime(2024, 3, 17)


def test_swing_missing_high_or_low_column_raises() -> None:
    bad = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="high.*low"):
        detect_swing_levels(bad, window=1)


# ---------------------------------------------------------------------------
# detect_prior_period_levels
# ---------------------------------------------------------------------------


def test_prior_daily_levels() -> None:
    """Daglig resample på timebar: hver kalenderdag får en H og L."""
    # 3 dager × 2 barer per dag
    ts = pd.date_range("2024-01-01", periods=6, freq="12h")
    ohlc = pd.DataFrame(
        {
            "open": [100.0] * 6,
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "low": [99.0, 98.0, 97.0, 96.0, 95.0, 94.0],
            "close": [100.0] * 6,
        },
        index=ts,
    )
    levels = detect_prior_period_levels(ohlc, period="D")

    # 3 dager, siste kan bli droppet → forventer minst 2 dager × 2 levels = 4
    # Siste dato inneholder 06:00 og 18:00 (dag 3), som droppes
    assert len(levels) == 4

    prior_highs = [lvl for lvl in levels if lvl.type == LevelType.PRIOR_HIGH]
    prior_lows = [lvl for lvl in levels if lvl.type == LevelType.PRIOR_LOW]
    assert len(prior_highs) == 2
    assert len(prior_lows) == 2


def test_prior_period_strength_is_fixed_08() -> None:
    highs = [100.0 + i for i in range(10)]
    lows = [99.0 + i for i in range(10)]
    ts = pd.date_range("2024-01-01", periods=10, freq="D")
    ohlc = pd.DataFrame({"open": highs, "high": highs, "low": lows, "close": highs}, index=ts)

    levels = detect_prior_period_levels(ohlc, period="W")
    for lvl in levels:
        assert lvl.strength == 0.8


def test_prior_period_requires_datetime_index() -> None:
    """Integer-index skal gi tydelig feil."""
    ohlc = pd.DataFrame({"high": [1.0, 2.0], "low": [0.5, 1.5]})
    with pytest.raises(ValueError, match="DatetimeIndex"):
        detect_prior_period_levels(ohlc, period="D")


def test_prior_period_single_period_returns_empty() -> None:
    """Med bare én periode (som da droppes som "inkomplett") → tomt."""
    ohlc = _ohlc_from_highs_lows([100.0, 101.0, 102.0])
    # Bare 3 dager, alle i samme "W" om de er mandag-onsdag → 1 periode → drop
    levels = detect_prior_period_levels(ohlc, period="W")
    assert levels == []


def test_prior_monthly_period_accepted() -> None:
    """M-perioder oversettes internt til pandas' ME. Ingen crash."""
    ts = pd.date_range("2024-01-01", periods=90, freq="D")
    ohlc = pd.DataFrame(
        {
            "open": [100.0] * 90,
            "high": [100.0 + i for i in range(90)],
            "low": [99.0 + i for i in range(90)],
            "close": [100.0] * 90,
        },
        index=ts,
    )
    levels = detect_prior_period_levels(ohlc, period="M")
    # 3 måneder; siste droppes → 2 måneder × 2 levels = 4
    assert len(levels) == 4


# ---------------------------------------------------------------------------
# detect_round_numbers
# ---------------------------------------------------------------------------


def test_round_numbers_above_and_below() -> None:
    levels = detect_round_numbers(
        current_price=2003.5, step=10.0, count_above=3, count_below=3
    )
    prices = sorted(lvl.price for lvl in levels)
    assert prices == [1980.0, 1990.0, 2000.0, 2010.0, 2020.0, 2030.0]


def test_round_numbers_strength_scales_with_trailing_zeros() -> None:
    levels = detect_round_numbers(
        current_price=2003.5, step=10.0, count_above=3, count_below=3
    )
    by_price = {lvl.price: lvl.strength for lvl in levels}

    # 2000 / 10 = 200 → 2 trailing zeros → 0.9
    assert by_price[2000.0] == pytest.approx(0.9)
    # 2010 / 10 = 201 → 0 zeros → 0.5
    assert by_price[2010.0] == pytest.approx(0.5)
    # 2020 / 10 = 202 → 0 zeros → 0.5
    assert by_price[2020.0] == pytest.approx(0.5)
    # 2030 / 10 = 203 → 0 zeros → 0.5
    assert by_price[2030.0] == pytest.approx(0.5)


def test_round_numbers_at_exact_multiple_steps_strictly_above_below() -> None:
    """Hvis current_price er på en exact round, ekskluderes den selv."""
    levels = detect_round_numbers(current_price=2000.0, step=10.0, count_above=1, count_below=1)
    prices = sorted(lvl.price for lvl in levels)
    assert prices == [1990.0, 2010.0]  # 2000.0 selv utelukket


def test_round_numbers_ts_is_none() -> None:
    """Round numbers er ikke tidsbundet."""
    levels = detect_round_numbers(2003.5, 10.0, 1, 1)
    for lvl in levels:
        assert lvl.ts is None


def test_round_numbers_type_is_round_number() -> None:
    levels = detect_round_numbers(2003.5, 10.0, 2, 2)
    for lvl in levels:
        assert lvl.type == LevelType.ROUND_NUMBER


def test_round_numbers_fine_step_for_fx() -> None:
    """EURUSD-lignende: step 0.01."""
    levels = detect_round_numbers(
        current_price=1.0957, step=0.01, count_above=2, count_below=2
    )
    prices = sorted(round(lvl.price, 4) for lvl in levels)
    # current=1.0957, step=0.01 → nærmeste over = 1.10, under = 1.09
    assert prices == [1.08, 1.09, 1.1, 1.11]


def test_round_numbers_step_zero_raises() -> None:
    with pytest.raises(ValueError, match="step"):
        detect_round_numbers(100.0, 0.0, 1, 1)


def test_round_numbers_step_negative_raises() -> None:
    with pytest.raises(ValueError, match="step"):
        detect_round_numbers(100.0, -1.0, 1, 1)


def test_round_numbers_count_zero_produces_empty_side() -> None:
    levels = detect_round_numbers(2003.5, 10.0, count_above=0, count_below=2)
    assert all(lvl.price < 2003.5 for lvl in levels)
    assert len(levels) == 2


# ---------------------------------------------------------------------------
# rank_levels
# ---------------------------------------------------------------------------


def test_rank_levels_sorts_descending_on_strength() -> None:
    levels = [
        Level(price=100.0, type=LevelType.SWING_HIGH, strength=0.5),
        Level(price=200.0, type=LevelType.PRIOR_HIGH, strength=0.9),
        Level(price=150.0, type=LevelType.ROUND_NUMBER, strength=0.7),
    ]
    ranked = rank_levels(levels)
    assert [lvl.strength for lvl in ranked] == [0.9, 0.7, 0.5]


def test_rank_levels_empty_input() -> None:
    assert rank_levels([]) == []


def test_rank_levels_preserves_insertion_order_on_ties() -> None:
    """Python `sorted` er stabil."""
    levels = [
        Level(price=100.0, type=LevelType.SWING_HIGH, strength=0.7),
        Level(price=200.0, type=LevelType.PRIOR_HIGH, strength=0.7),
    ]
    ranked = rank_levels(levels)
    assert ranked[0].price == 100.0
    assert ranked[1].price == 200.0


def test_rank_levels_does_not_deduplicate() -> None:
    """Per krav fra session 16: clustering hører i setup-bygger."""
    levels = [
        Level(price=2000.0, type=LevelType.SWING_HIGH, strength=0.8),
        Level(price=2000.0, type=LevelType.ROUND_NUMBER, strength=0.9),
    ]
    ranked = rank_levels(levels)
    assert len(ranked) == 2


# ---------------------------------------------------------------------------
# Integrasjonstest: DataStore → detector
# ---------------------------------------------------------------------------


def test_detect_swings_against_datastore_ohlc(tmp_path) -> None:
    """Fullfør loop: DataStore.append_prices → get_prices_ohlc → detect_swing_levels."""
    from bedrock.data.store import DataStore

    ts = pd.date_range("2024-01-01", periods=20, freq="D")
    ohlc_raw = pd.DataFrame(
        {
            "ts": ts,
            "open": [100.0] * 20,
            "high": [100.0] * 9 + [110.0] + [100.0] * 10,  # peak i midten
            "low": [99.0] * 20,
            "close": [100.0] * 20,
            "volume": [1000.0] * 20,
        }
    )
    store = DataStore(tmp_path / "bedrock.db")
    store.append_prices("Gold", "D1", ohlc_raw)

    ohlc = store.get_prices_ohlc("Gold", "D1")
    levels = detect_swing_levels(ohlc, window=3)

    swing_highs = [lvl for lvl in levels if lvl.type == LevelType.SWING_HIGH]
    assert len(swing_highs) == 1
    assert swing_highs[0].price == 110.0
    assert swing_highs[0].strength > 0.8  # markert peak
