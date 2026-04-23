"""Logiske tester for trend-drivere.

Format: "gitt X-data, forvent Y-atferd". Prisene er kurerte fiktive serier
designet for å eksponere én bestemt driver-atferd. Dette er mønsteret for
alle driver-tester fremover.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bedrock.data.store import DataStore
from bedrock.engine.drivers.trend import momentum_z, sma200_align


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    """Fersk SQLite-backet DataStore per test, i pytests tmp_path."""
    return DataStore(tmp_path / "bedrock.db")


def _add_closes(
    store: DataStore,
    instrument: str,
    tf: str,
    closes: Sequence[float] | pd.Series,
) -> None:
    """Test-helper: skriv close-only pris-serie med syntetiske daglige ts.

    Driverne leser kun close; OHLV er irrelevant for trend-tester.
    """
    values = list(closes) if isinstance(closes, pd.Series) else list(closes)
    ts = pd.date_range("2024-01-01", periods=len(values), freq="D")
    df = pd.DataFrame({"ts": ts, "close": values})
    store.append_prices(instrument, tf, df)


# ---------------------------------------------------------------------------
# sma200_align
# ---------------------------------------------------------------------------


def _flat_then_spike(flat_price: float, last_close: float, bars: int = 250) -> list[float]:
    """Serie med `bars-1` like priser, så én spike til `last_close`. Gir en
    SMA ~= flat_price og dermed deterministisk close vs SMA-sammenligning."""
    return [flat_price] * (bars - 1) + [last_close]


def test_sma200_align_well_above_sma_returns_full_score(store: DataStore) -> None:
    """Close > SMA × 1.01 -> 1.0."""
    _add_closes(store, "Gold", "D1", _flat_then_spike(100.0, 105.0))
    assert sma200_align(store, "Gold", {"tf": "D1"}) == 1.0


def test_sma200_align_just_above_sma_returns_medium_score(store: DataStore) -> None:
    """Close knapt over SMA (innenfor 1 %) -> 0.6."""
    # SMA vil ligge like under 100.0, close = 100.5 -> forhold 1.005 -> mellom
    # 1.0 og 1.01 -> returnerer 0.6 per drivers terskler.
    _add_closes(store, "Gold", "D1", _flat_then_spike(100.0, 100.5))
    assert sma200_align(store, "Gold", {"tf": "D1"}) == 0.6


def test_sma200_align_close_within_one_pct_below_sma(store: DataStore) -> None:
    """Close mellom SMA × 0.99 og SMA -> 0.4 (tvetydig sone)."""
    _add_closes(store, "Gold", "D1", _flat_then_spike(100.0, 99.5))
    assert sma200_align(store, "Gold", {"tf": "D1"}) == 0.4


def test_sma200_align_well_below_sma_returns_zero(store: DataStore) -> None:
    _add_closes(store, "Gold", "D1", _flat_then_spike(100.0, 95.0))
    assert sma200_align(store, "Gold", {"tf": "D1"}) == 0.0


def test_sma200_align_short_history_returns_zero(store: DataStore) -> None:
    """Færre enn 200 bars -> SMA udefinert -> 0.0 (driver-kontrakt: feil er 0.0)."""
    _add_closes(store, "Gold", "D1", [100.0] * 50)
    assert sma200_align(store, "Gold", {"tf": "D1"}) == 0.0


def test_sma200_align_missing_instrument_returns_zero_not_raises(store: DataStore) -> None:
    """Driver-kontrakt: data-feil skal ikke propageres som unntak."""
    # Ingen data lagt inn for Gold
    result = sma200_align(store, "Gold", {"tf": "D1"})
    assert result == 0.0


def test_sma200_align_respects_tf_param(store: DataStore) -> None:
    """Samme instrument med to TF: skal plukke riktig serie fra param."""
    # D1: bullish (close over SMA) ; 4H: bearish (close under SMA)
    _add_closes(store, "Gold", "D1", _flat_then_spike(100.0, 110.0))
    _add_closes(store, "Gold", "4H", _flat_then_spike(100.0, 90.0))

    assert sma200_align(store, "Gold", {"tf": "D1"}) == 1.0
    assert sma200_align(store, "Gold", {"tf": "4H"}) == 0.0


# ---------------------------------------------------------------------------
# momentum_z
# ---------------------------------------------------------------------------


def _noisy_series(
    n: int,
    base: float,
    noise_std: float,
    last_close: float,
    seed: int = 0,
) -> list[float]:
    """n-1 bars rundt `base` med std `noise_std`, så én siste bar `last_close`.

    Dette gir en rolling-std som er omtrent `noise_std`, og rolling-mean ≈ `base`,
    slik at siste bar får z ≈ (last_close - base) / noise_std.
    """
    rng = np.random.default_rng(seed)
    body = rng.normal(loc=base, scale=noise_std, size=n - 1)
    return list(np.concatenate([body, [last_close]]))


def test_momentum_z_close_two_std_above_mean_returns_full(store: DataStore) -> None:
    """z >= 2.0 -> 1.0."""
    # 20 bars rundt base=100 std=1, siste close = 103 -> z ≈ 3 -> >= 2.0 -> 1.0
    _add_closes(store, "Gold", "D1", _noisy_series(30, base=100.0, noise_std=1.0, last_close=103.0))
    assert momentum_z(store, "Gold", {"window": 20}) == 1.0


def test_momentum_z_close_one_std_above_mean_returns_high(store: DataStore) -> None:
    """z i [1.0, 2.0) -> 0.75."""
    # close = 101.5 -> z ≈ 1.5 -> 0.75
    _add_closes(
        store,
        "Gold",
        "D1",
        _noisy_series(30, base=100.0, noise_std=1.0, last_close=101.5, seed=42),
    )
    assert momentum_z(store, "Gold", {"window": 20}) == 0.75


def test_momentum_z_close_below_mean_returns_zero_or_low(store: DataStore) -> None:
    """z sterkt negativ -> 0.0."""
    # close = 97 -> z ≈ -3 -> < -0.5 -> 0.0
    _add_closes(
        store,
        "Gold",
        "D1",
        _noisy_series(30, base=100.0, noise_std=1.0, last_close=97.0, seed=1),
    )
    assert momentum_z(store, "Gold", {"window": 20}) == 0.0


def test_momentum_z_close_equal_to_mean_returns_mid(store: DataStore) -> None:
    """Flat serie (std=0) -> 0.0 (driver definerer dette som ikke-signal)."""
    _add_closes(store, "Gold", "D1", [100.0] * 30)
    # std = 0 -> driver returnerer 0.0
    assert momentum_z(store, "Gold", {"window": 20}) == 0.0


def test_momentum_z_short_history_returns_zero(store: DataStore) -> None:
    """window=20 krever minst 21 bars."""
    _add_closes(store, "Gold", "D1", [100.0] * 10)
    assert momentum_z(store, "Gold", {"window": 20}) == 0.0


def test_momentum_z_missing_instrument_returns_zero_not_raises(store: DataStore) -> None:
    assert momentum_z(store, "Gold", {"window": 20}) == 0.0


def test_momentum_z_uses_default_window_when_not_specified(store: DataStore) -> None:
    """Uten `window`-param skal default 20 brukes."""
    _add_closes(store, "Gold", "D1", _noisy_series(30, 100.0, 1.0, 103.0, seed=7))
    assert momentum_z(store, "Gold", {}) == 1.0


# ---------------------------------------------------------------------------
# Integrerings-sanity: Engine kjører med ekte trend-drivere (Gold SWING)
# ---------------------------------------------------------------------------


def test_engine_runs_gold_swing_with_real_trend_drivers(store: DataStore) -> None:
    """Sanity: Engine + trend-drivere + DataStore ender opp med et tall.

    Dette er ikke en full Gold-scenario-test (den venter på resten av
    driverne), kun bekreftelse på at wiring fungerer end-to-end med ekte
    drivere + SQLite-backet store i stedet for mocks."""
    from bedrock.engine.engine import (
        DriverSpec,
        Engine,
        FinancialFamilySpec,
        FinancialRules,
        HorizonSpec,
    )
    from bedrock.engine.grade import GradeThreshold, GradeThresholds

    # Sterk bull-serie: godt over SMA + høy positiv z.
    _add_closes(
        store, "Gold", "D1", _noisy_series(250, base=100.0, noise_std=1.0, last_close=110.0)
    )

    rules = FinancialRules(
        aggregation="weighted_horizon",
        horizons={
            "SWING": HorizonSpec(
                family_weights={"trend": 1.0},
                max_score=2.0,  # max mulig for trend-familien her
                min_score_publish=0.5,
            ),
        },
        families={
            "trend": FinancialFamilySpec(
                drivers=[
                    DriverSpec(name="sma200_align", weight=0.5, params={"tf": "D1"}),
                    DriverSpec(name="momentum_z", weight=0.5, params={"window": 20}),
                ]
            ),
        },
        grade_thresholds=GradeThresholds(
            a_plus=GradeThreshold(min_pct_of_max=0.75, min_families=1),
            a=GradeThreshold(min_pct_of_max=0.55, min_families=1),
            b=GradeThreshold(min_pct_of_max=0.35, min_families=1),
        ),
    )

    result = Engine().score("Gold", store=store, rules=rules, horizon="SWING")

    # sma200_align = 1.0 (close > SMA × 1.01), momentum_z = 1.0 (z > 2).
    # trend-familie = 0.5*1.0 + 0.5*1.0 = 1.0
    # weighted_horizon med family_weight=1.0 -> total 1.0
    assert result.score == pytest.approx(1.0)
    assert result.families["trend"].drivers[0].value == 1.0  # sma200_align
    assert result.families["trend"].drivers[1].value == 1.0  # momentum_z
    # 1.0 / 2.0 = 0.5 -> under A (0.55), over B (0.35) -> B
    assert result.grade == "B"
