"""Tester for R4-horisont-modes på trend-driverne (sma200_align, momentum_z).

Sub-fase 12.7 R4 batch 1 (session 122). Verifiserer per
``docs/driver_horizon_pattern.md`` § 2:

- Type A: default (mode=None) er bit-identisk pre-R4 (ingen mock-tester
  her — Type A er garantert globalt via snapshot-baseline-diff = 0).
- Type B (§ 2.2): ``mode="pct_12m"`` produserer høy output når current
  er ekstrem mot historikk-distribusjonen.
- Type C (§ 2.3): ``mode="delta_5d_z"`` reagerer på regime-shift (5d-hopp).
- ``mode="pct_36m"`` faller gracefully tilbake til pct_12m ved
  utilstrekkelig 36m-historikk.
- ``mode="extreme_flag_*"`` returnerer 1.0 ved 2/98- og 5/95-tersklene.
- Ukjent mode logger warning og fall-backer til default.
- Defensive-baner (KeyError, kort historikk) returnerer 0.0.

For ``momentum_z``: ``delta_*_z``-modes representerer **akselerasjon av
momentum** (z-score av delta av z-score-serien), ikke endring i
underliggende pris.

Bruker enkel in-memory mock-store-mønster (se ``test_drivers_*``-presedens).
"""

from __future__ import annotations

import pandas as pd

from bedrock.engine.drivers.trend import momentum_z, sma200_align


class _PriceStore:
    def __init__(self, prices: pd.Series):
        self._prices = prices

    def get_prices(self, instrument: str, tf: str = "D1", lookback: int | None = None) -> pd.Series:
        if lookback is None:
            return self._prices
        return self._prices.tail(lookback).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Fixture-byggere
# ---------------------------------------------------------------------------


def _flat_then_rise(
    n_flat: int = 500, n_rise: int = 100, base: float = 100.0, end: float = 130.0
) -> pd.Series:
    """Lang flat-periode etterfulgt av stigning. Gir current SMA-distance
    som er klart ekstrem mot historikkens nær-null distance-fordeling.
    """
    rise = [base + (end - base) * (i + 1) / n_rise for i in range(n_rise)]
    return pd.Series([base] * n_flat + rise)


def _flat_then_drop(
    n_flat: int = 500, n_rise: int = 100, base: float = 100.0, end: float = 70.0
) -> pd.Series:
    """Speil av _flat_then_rise — fall-regime."""
    drop = [base + (end - base) * (i + 1) / n_rise for i in range(n_rise)]
    return pd.Series([base] * n_flat + drop)


def _rising_then_jump(n: int = 600, base: float = 100.0, jump: float = 5.0) -> pd.Series:
    """Smal støy-serie + 5d-jump på slutten for delta_5d_z-test."""
    rng = pd.Series([base + (i % 3 - 1) * 0.05 for i in range(n)])
    rng.iloc[-5:] = rng.iloc[-5:] + jump
    return rng


def _flat_series(n: int = 600, base: float = 100.0) -> pd.Series:
    return pd.Series([base] * n)


def _noisy_then_rise(
    n_noisy: int = 500, n_rise: int = 100, base: float = 100.0, end: float = 130.0
) -> pd.Series:
    """Liten støy i lang periode + sen stigning. For momentum_z hvor
    rolling-z krever std > 0 (flat data → std=0 → NaN-z, dropper testene)."""
    noisy = [base + 0.5 * ((i % 7) - 3) + 0.3 * ((i % 11) - 5) for i in range(n_noisy)]
    rise = [base + (end - base) * (i + 1) / n_rise for i in range(n_rise)]
    return pd.Series(noisy + rise)


# ---------------------------------------------------------------------------
# sma200_align — Type B (current ekstrem mot historikk)
# ---------------------------------------------------------------------------


def test_sma200_align_pct_12m_high_on_late_rise():
    """Type B § 2.2: lang flat + sen stigning → current SMA-distance er
    top-percentile av 12m-historikk."""
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    score = sma200_align(store, "Test", {"mode": "pct_12m"})
    assert score >= 0.95
    assert score <= 1.0


def test_sma200_align_pct_12m_low_on_late_drop():
    """Speil: lang flat + sen drop → current distance er bunn-percentile."""
    prices = _flat_then_drop()
    store = _PriceStore(prices)
    score = sma200_align(store, "Test", {"mode": "pct_12m"})
    assert score <= 0.05


# ---------------------------------------------------------------------------
# sma200_align — Type C (regime-shift)
# ---------------------------------------------------------------------------


def test_sma200_align_delta_5d_z_reacts_to_jump():
    """Type C § 2.3: 5d-pris-hopp gir stor endring i SMA-distance →
    ekstrem delta_5d_z-z-score → høy score."""
    prices = _rising_then_jump(jump=10.0)
    store = _PriceStore(prices)
    score = sma200_align(store, "Test", {"mode": "delta_5d_z"})
    assert score >= 0.6


# ---------------------------------------------------------------------------
# sma200_align — pct_36m fallback aktiveres
# ---------------------------------------------------------------------------


def test_sma200_align_pct_36m_fallback_returns_valid_value(caplog):
    """Utilstrekkelig 36m-historikk → fall-back-log + gyldig output (§ 1.1)."""
    import logging

    caplog.set_level(logging.INFO)
    prices = _flat_then_rise()  # 600 < 956 (756+200) → fallback aktiveres
    store = _PriceStore(prices)
    score = sma200_align(store, "Test", {"mode": "pct_36m"})
    # Fall-back skal returnere et tall i [0,1], ikke 0.0 (siden 12m er ok)
    assert 0.0 <= score <= 1.0
    assert score > 0.0  # dataen er ekstrem, så pct_12m-fall-back skal ikke være null


# ---------------------------------------------------------------------------
# sma200_align — extreme_flag_*
# ---------------------------------------------------------------------------


def test_sma200_align_extreme_flag_hard_triggers_at_98():
    """Top-percentile (≥0.98) → flag_hard = 1.0."""
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    flag = sma200_align(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_sma200_align_extreme_flag_soft_triggers_at_95():
    """Også soft trigger på top-percentile."""
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    flag = sma200_align(store, "Test", {"mode": "extreme_flag_soft"})
    assert flag == 1.0


def test_sma200_align_extreme_flag_does_not_trigger_in_middle():
    """Mid-range pct (~0.5) → flag = 0.0."""
    # Bygg en serie der current distance er midt i historikk-distribusjonen.
    # Stigende-fallende-stigende sykel gir varierende distance.
    base_data = []
    for cycle in range(3):
        base_data.extend([100.0 + cycle * 5 + i * 0.1 for i in range(200)])
    prices = pd.Series(base_data)
    store = _PriceStore(prices)
    flag = sma200_align(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


# ---------------------------------------------------------------------------
# sma200_align — ukjent mode + defensiv
# ---------------------------------------------------------------------------


def test_sma200_align_unknown_mode_falls_back_to_default():
    """Ukjent mode → log + samme output som default."""
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    default = sma200_align(store, "Test", {})
    unknown = sma200_align(store, "Test", {"mode": "zorx"})
    assert default == unknown


def test_sma200_align_horizon_param_does_not_affect_default():
    """ADR-010: _horizon leses men endrer ikke default-output."""
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    no_horizon = sma200_align(store, "Test", {})
    swing = sma200_align(store, "Test", {"_horizon": "SWING"})
    makro = sma200_align(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == swing == makro


def test_sma200_align_short_history_returns_zero_for_modes():
    """Mode-bane med < 200 bars → 0.0 (SMA udefinert)."""
    prices = pd.Series([100.0 + 0.5 * i for i in range(50)])
    store = _PriceStore(prices)
    for mode in (
        "pct_12m",
        "pct_36m",
        "delta_5d_z",
        "delta_20d_z",
        "extreme_flag_hard",
        "extreme_flag_soft",
    ):
        assert sma200_align(store, "Test", {"mode": mode}) == 0.0


# ---------------------------------------------------------------------------
# momentum_z — Type B (current ekstrem mot historikk)
# ---------------------------------------------------------------------------


def test_momentum_z_pct_12m_higher_on_acceleration_vs_calm():
    """Type B § 2.2 (komparativ): pct_12m skal være HØYERE for serie med
    sen akselerasjon enn for ren støy-serie. Bekrefter at modus reagerer
    på regime-shift i z-distribusjonen.

    (Absolute terskler er sensitive for window-størrelse på rolling-z;
    komparativ test er robustere som monotonisitets-bevis.)
    """
    prices_calm = pd.Series(
        [100.0 + 0.5 * ((i % 7) - 3) + 0.3 * ((i % 11) - 5) for i in range(600)]
    )
    prices_acc = _noisy_then_rise(n_noisy=580, n_rise=20, end=130.0)
    score_calm = momentum_z(_PriceStore(prices_calm), "Test", {"mode": "pct_12m"})
    score_acc = momentum_z(_PriceStore(prices_acc), "Test", {"mode": "pct_12m"})
    assert score_acc > score_calm
    assert 0.0 <= score_calm <= 1.0
    assert 0.0 <= score_acc <= 1.0


# ---------------------------------------------------------------------------
# momentum_z — Type C (5d-akselerasjon)
# ---------------------------------------------------------------------------


def test_momentum_z_delta_5d_z_reacts_to_acceleration():
    """Type C § 2.3 (momentum_z-versjon): 5d-pris-jump gir z-jump i rolling-
    z-serien → ekstrem delta_5d_z. Tolkning: akselerasjon av momentum."""
    prices = _rising_then_jump(jump=10.0)
    store = _PriceStore(prices)
    score = momentum_z(store, "Test", {"mode": "delta_5d_z"})
    assert score >= 0.6


# ---------------------------------------------------------------------------
# momentum_z — pct_36m fallback
# ---------------------------------------------------------------------------


def test_momentum_z_pct_36m_fallback_returns_valid_value():
    """Utilstrekkelig 36m-historikk → fall-back til pct_12m."""
    prices = _flat_then_rise()  # 600 obs, ikke nok for 756-vindu
    store = _PriceStore(prices)
    score = momentum_z(store, "Test", {"mode": "pct_36m"})
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# momentum_z — extreme_flag + ukjent mode + horizon
# ---------------------------------------------------------------------------


def test_momentum_z_extreme_flag_returns_binary():
    """Flag-modes returnerer kun 0.0 eller 1.0 (ikke fractional)."""
    prices = _noisy_then_rise()
    store = _PriceStore(prices)
    hard = momentum_z(store, "Test", {"mode": "extreme_flag_hard"})
    soft = momentum_z(store, "Test", {"mode": "extreme_flag_soft"})
    assert hard in (0.0, 1.0)
    assert soft in (0.0, 1.0)


def test_momentum_z_unknown_mode_falls_back_to_default():
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    default = momentum_z(store, "Test", {})
    unknown = momentum_z(store, "Test", {"mode": "zorx"})
    assert default == unknown


def test_momentum_z_horizon_param_does_not_affect_default():
    prices = _flat_then_rise()
    store = _PriceStore(prices)
    no_horizon = momentum_z(store, "Test", {})
    swing = momentum_z(store, "Test", {"_horizon": "SWING"})
    makro = momentum_z(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == swing == makro


def test_momentum_z_short_history_returns_zero_for_modes():
    prices = pd.Series([100.0 + 0.5 * i for i in range(20)])
    store = _PriceStore(prices)
    for mode in (
        "pct_12m",
        "pct_36m",
        "delta_5d_z",
        "delta_20d_z",
        "extreme_flag_hard",
        "extreme_flag_soft",
    ):
        assert momentum_z(store, "Test", {"mode": mode}) == 0.0


# ---------------------------------------------------------------------------
# Defensive — KeyError fra store
# ---------------------------------------------------------------------------


class _RaisingStore:
    def get_prices(self, instrument, tf="D1", lookback=None):
        raise KeyError("missing prices")


def test_sma200_align_keyerror_returns_zero():
    store = _RaisingStore()
    assert sma200_align(store, "Test", {"mode": "pct_12m"}) == 0.0
    assert sma200_align(store, "Test", {}) == 0.0


def test_momentum_z_keyerror_returns_zero():
    store = _RaisingStore()
    assert momentum_z(store, "Test", {"mode": "pct_12m"}) == 0.0
    assert momentum_z(store, "Test", {}) == 0.0
