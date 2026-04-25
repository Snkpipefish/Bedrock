"""Tester for `bedrock.setups.generator` — setup-bygger."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.setups.generator import (
    Direction,
    Horizon,
    SetupConfig,
    build_setup,
    cluster_levels,
    compute_atr,
)
from bedrock.setups.levels import Level, LevelType

# ---------------------------------------------------------------------------
# compute_atr
# ---------------------------------------------------------------------------


def _ohlc(
    n: int = 20,
    high_base: float = 102.0,
    low_base: float = 98.0,
    close_base: float = 100.0,
) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [close_base] * n,
            "high": [high_base + i * 0.1 for i in range(n)],
            "low": [low_base + i * 0.1 for i in range(n)],
            "close": [close_base + i * 0.1 for i in range(n)],
        },
        index=ts,
    )


def test_compute_atr_returns_float() -> None:
    ohlc = _ohlc(20)
    atr = compute_atr(ohlc, period=14)
    assert isinstance(atr, float)
    assert atr > 0


def test_compute_atr_on_flat_range_returns_range() -> None:
    """Konstant high-low range = ATR lik rangen (ingen gap)."""
    ts = pd.date_range("2024-01-01", periods=20, freq="D")
    ohlc = pd.DataFrame(
        {
            "open": [100.0] * 20,
            "high": [102.0] * 20,
            "low": [98.0] * 20,
            "close": [100.0] * 20,
        },
        index=ts,
    )
    atr = compute_atr(ohlc, period=14)
    assert atr == pytest.approx(4.0)


def test_compute_atr_missing_columns_raises() -> None:
    bad = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="missing columns"):
        compute_atr(bad, period=14)


def test_compute_atr_insufficient_bars_raises() -> None:
    with pytest.raises(ValueError, match=">= period"):
        compute_atr(_ohlc(5), period=14)


# ---------------------------------------------------------------------------
# cluster_levels
# ---------------------------------------------------------------------------


def _lvl(price: float, type_: LevelType, strength: float = 0.7) -> Level:
    return Level(price=price, type=type_, strength=strength)


def test_cluster_levels_empty_input() -> None:
    assert cluster_levels([], buffer=1.0) == []


def test_cluster_levels_single_level() -> None:
    out = cluster_levels([_lvl(100.0, LevelType.SWING_HIGH)], buffer=1.0)
    assert len(out) == 1
    assert out[0].price == 100.0
    assert out[0].source_count == 1


def test_cluster_levels_far_apart_no_merge() -> None:
    levels = [
        _lvl(100.0, LevelType.SWING_HIGH),
        _lvl(110.0, LevelType.PRIOR_HIGH),
    ]
    out = cluster_levels(levels, buffer=1.0)
    assert len(out) == 2


def test_cluster_levels_close_merge() -> None:
    """Swing + round number innenfor buffer → merget."""
    levels = [
        _lvl(100.0, LevelType.SWING_HIGH, strength=0.7),
        _lvl(100.2, LevelType.ROUND_NUMBER, strength=0.9),
    ]
    out = cluster_levels(levels, buffer=0.3)
    assert len(out) == 1
    cluster = out[0]
    assert cluster.source_count == 2
    # Pris = sterkestes pris
    assert cluster.price == 100.2
    # Konfluens: strongest=0.9 + 0.1 → 1.0 cap
    assert cluster.strength == pytest.approx(1.0)
    # Begge typer bevart
    assert set(cluster.types) == {LevelType.SWING_HIGH, LevelType.ROUND_NUMBER}


def test_cluster_levels_transitive_single_link() -> None:
    """100.0, 100.2, 100.5 med buffer=0.3 → én klynge (kjede)."""
    levels = [
        _lvl(100.0, LevelType.SWING_HIGH, strength=0.6),
        _lvl(100.2, LevelType.ROUND_NUMBER, strength=0.6),
        _lvl(100.5, LevelType.PRIOR_HIGH, strength=0.8),
    ]
    out = cluster_levels(levels, buffer=0.3)
    assert len(out) == 1
    assert out[0].source_count == 3
    # Konfluens-bonus: strongest 0.8 + 0.2 (2 ekstra) = 1.0
    assert out[0].strength == pytest.approx(1.0)


def test_cluster_levels_buffer_zero_no_merging() -> None:
    """Buffer=0 → hver level blir egen klynge, også ved lik pris."""
    levels = [
        _lvl(100.0, LevelType.SWING_HIGH),
        _lvl(100.0, LevelType.ROUND_NUMBER),
    ]
    out = cluster_levels(levels, buffer=0.0)
    assert len(out) == 2


def test_cluster_types_stable_order() -> None:
    """`types`-lista bevarer førstegangs-rekkefølge."""
    levels = [
        _lvl(100.0, LevelType.ROUND_NUMBER),
        _lvl(100.1, LevelType.SWING_HIGH),
        _lvl(100.2, LevelType.ROUND_NUMBER),  # duplikat-type
    ]
    out = cluster_levels(levels, buffer=0.5)
    assert out[0].types == [LevelType.ROUND_NUMBER, LevelType.SWING_HIGH]


# ---------------------------------------------------------------------------
# build_setup — BUY
# ---------------------------------------------------------------------------


def _buy_scenario() -> list[Level]:
    """Scenario: nåpris ~102; støtte på 100 (entry), motstand på 106+108."""
    return [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.8),  # entry-støtte
        _lvl(106.0, LevelType.SWING_HIGH, strength=0.7),  # SCALP-TP
        _lvl(108.0, LevelType.PRIOR_HIGH, strength=0.8),  # SWING-TP (2. i retningen)
    ]


def test_build_setup_buy_scalp_succeeds() -> None:
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=102.0,
        atr=1.0,
        levels=_buy_scenario(),
    )
    assert setup is not None
    assert setup.entry == 100.0
    # SL = entry - 0.3 * atr = 100 - 0.3 = 99.7
    assert setup.sl == pytest.approx(99.7)
    assert setup.tp == 106.0
    # R:R = (106-100) / (100-99.7) = 6 / 0.3 = 20
    assert setup.rr == pytest.approx(20.0)


def test_build_setup_buy_swing_uses_second_level() -> None:
    """SWING skal hoppe over 1. nivå (SCALP-target) til 2."""
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SWING,
        current_price=102.0,
        atr=1.0,
        levels=_buy_scenario(),
    )
    assert setup is not None
    assert setup.tp == 108.0


def test_build_setup_buy_makro_has_no_tp() -> None:
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.MAKRO,
        current_price=102.0,
        atr=1.0,
        levels=_buy_scenario(),
    )
    assert setup is not None
    assert setup.tp is None
    assert setup.rr is None
    assert setup.tp_cluster_price is None
    assert setup.tp_cluster_types is None


def test_build_setup_entry_cluster_types_reported() -> None:
    """Entry-clusteren sine typer skal være bevart for UI/explain."""
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.6),
        _lvl(100.1, LevelType.ROUND_NUMBER, strength=0.9),  # konfluens
        _lvl(106.0, LevelType.SWING_HIGH, strength=0.7),
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=102.0,
        atr=1.0,
        levels=levels,
    )
    assert setup is not None
    assert set(setup.entry_cluster_types) == {LevelType.SWING_LOW, LevelType.ROUND_NUMBER}


# ---------------------------------------------------------------------------
# build_setup — SELL (symmetri)
# ---------------------------------------------------------------------------


def _sell_scenario() -> list[Level]:
    """Nåpris ~98; motstand på 100, support på 94+92."""
    return [
        _lvl(100.0, LevelType.SWING_HIGH, strength=0.8),  # entry-motstand
        _lvl(94.0, LevelType.SWING_LOW, strength=0.7),  # SCALP-TP
        _lvl(92.0, LevelType.PRIOR_LOW, strength=0.8),  # SWING-TP
    ]


def test_build_setup_sell_scalp() -> None:
    setup = build_setup(
        instrument="Gold",
        direction=Direction.SELL,
        horizon=Horizon.SCALP,
        current_price=98.0,
        atr=1.0,
        levels=_sell_scenario(),
    )
    assert setup is not None
    assert setup.entry == 100.0
    assert setup.sl == pytest.approx(100.3)  # 100 + 0.3*1.0
    assert setup.tp == 94.0


def test_build_setup_sell_swing() -> None:
    setup = build_setup(
        instrument="Gold",
        direction=Direction.SELL,
        horizon=Horizon.SWING,
        current_price=98.0,
        atr=1.0,
        levels=_sell_scenario(),
    )
    assert setup is not None
    assert setup.tp == 92.0


# ---------------------------------------------------------------------------
# build_setup — rejection paths
# ---------------------------------------------------------------------------


def test_build_setup_returns_none_when_no_entry_level() -> None:
    """BUY men ingen støtte under nåpris."""
    levels = [
        _lvl(105.0, LevelType.SWING_HIGH, strength=0.8),
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=100.0,
        atr=1.0,
        levels=levels,
    )
    assert setup is None


def test_build_setup_returns_none_when_entry_too_weak() -> None:
    """Støtte under eksisterer, men strength under min_entry_strength."""
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.5),  # under default 0.6
        _lvl(106.0, LevelType.SWING_HIGH, strength=0.8),
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=102.0,
        atr=1.0,
        levels=levels,
    )
    assert setup is None


def test_build_setup_returns_none_when_no_tp_levels() -> None:
    """Entry finnes, men ingen motstand over nåpris for BUY SCALP."""
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.8),
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=102.0,
        atr=1.0,
        levels=levels,
    )
    assert setup is None


def test_build_setup_scalp_rejects_when_rr_below_min() -> None:
    """SCALP med R:R < 1.5 → forkast."""
    # Entry 100, TP 100.5 — for nær, gir R:R < 1.5 med sl_atr=0.3
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.8),
        _lvl(100.35, LevelType.SWING_HIGH, strength=0.8),  # altfor nær
    ]
    # atr=1.0 → sl_buffer=0.3; entry=100, sl=99.7, reward=0.35 → rr ~1.17
    # Men current_price må være under TP og over entry, så 100.0 < current < 100.35
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=100.2,
        atr=1.0,
        levels=levels,
    )
    assert setup is None


def test_build_setup_swing_falls_back_to_third_level() -> None:
    """SWING skal prøve 2. nivå først, så 3. hvis 2. gir for lav R:R.

    Setup: entry=100, sl_atr=1.0 → sl=99, risk=1.0. Ahead-liste sortert
    ASC: [101 (X0 skippes), 102 (X1 target), 103 (X2 fallback)].

    - X1 (102): reward=2, R:R=2.0 < 2.5 → fail
    - X2 (103): reward=3, R:R=3.0 ≥ 2.5 → pass, velg denne
    """
    cfg = SetupConfig(sl_atr_multiplier=1.0)
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.8),
        _lvl(101.0, LevelType.ROUND_NUMBER, strength=0.7),  # X0 (skippes av SWING)
        _lvl(102.0, LevelType.SWING_HIGH, strength=0.7),  # X1 — faller pga R:R
        _lvl(103.0, LevelType.PRIOR_HIGH, strength=0.8),  # X2 — velges
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SWING,
        current_price=100.5,
        atr=1.0,
        levels=levels,
        config=cfg,
    )
    assert setup is not None
    assert setup.tp == 103.0
    assert setup.rr == pytest.approx(3.0)


def test_build_setup_empty_levels() -> None:
    """Tom levels-liste → None."""
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=100.0,
        atr=1.0,
        levels=[],
    )
    assert setup is None


# ---------------------------------------------------------------------------
# build_setup — determinisme
# ---------------------------------------------------------------------------


def test_build_setup_is_deterministic() -> None:
    """Samme input → samme output, uansett hvor mange ganger."""
    levels = _buy_scenario()
    setups = [
        build_setup(
            instrument="Gold",
            direction=Direction.BUY,
            horizon=Horizon.SCALP,
            current_price=102.0,
            atr=1.0,
            levels=levels,
        )
        for _ in range(5)
    ]
    # Alle skal være identiske
    reference = setups[0]
    assert reference is not None
    for s in setups[1:]:
        assert s is not None
        assert s.model_dump() == reference.model_dump()


def test_build_setup_custom_config_overrides_defaults() -> None:
    """Caller kan overstyre min_rr og buffer via SetupConfig."""
    cfg = SetupConfig(
        min_rr_scalp=10.0,  # uvanlig strengt
        sl_atr_multiplier=0.1,
    )
    # Med default 1.5 ville denne pass; med 10.0 forkastes
    levels = [
        _lvl(100.0, LevelType.SWING_LOW, strength=0.8),
        _lvl(100.5, LevelType.SWING_HIGH, strength=0.8),  # R:R=5 < 10
    ]
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=100.2,
        atr=1.0,
        levels=levels,
        config=cfg,
    )
    assert setup is None


def test_setup_config_min_rr_for_makro_is_none() -> None:
    cfg = SetupConfig()
    assert cfg.min_rr_for(Horizon.MAKRO) is None
    assert cfg.min_rr_for(Horizon.SCALP) == 1.5
    assert cfg.min_rr_for(Horizon.SWING) == 2.5


# ---------------------------------------------------------------------------
# Integrasjon: detektor → cluster → setup
# ---------------------------------------------------------------------------


def test_integration_detect_levels_then_build_setup() -> None:
    """End-to-end: detektorer gir råliste → cluster_levels → build_setup."""
    from bedrock.setups.levels import detect_round_numbers, detect_swing_levels

    # OHLC med en tydelig swing low ved 100 (for BUY-støtte)
    ts = pd.date_range("2024-01-01", periods=20, freq="D")
    highs = [105.0] * 9 + [106.0] + [105.0] * 10
    lows = [103.0] * 9 + [100.0] + [103.0] * 10  # swing low ved idx 9
    ohlc = pd.DataFrame({"open": highs, "high": highs, "low": lows, "close": highs}, index=ts)
    swing_levels = detect_swing_levels(ohlc, window=3)
    round_levels = detect_round_numbers(current_price=104.0, step=2.0, count_above=3, count_below=3)

    levels = swing_levels + round_levels

    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=104.0,
        atr=1.0,
        levels=levels,
    )
    assert setup is not None
    # Entry bør være på støtte-siden (< 104)
    assert setup.entry < 104.0
