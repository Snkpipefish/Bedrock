"""Tester for `bedrock.setups.horizon`."""

from __future__ import annotations

import pytest

from bedrock.setups.generator import Horizon
from bedrock.setups.horizon import (
    apply_horizon_hysteresis,
    classify_horizon,
    estimate_expected_hold_days,
    is_score_sufficient,
)


# ---------------------------------------------------------------------------
# estimate_expected_hold_days
# ---------------------------------------------------------------------------


def test_estimate_hold_basic() -> None:
    """TP 5 ATR unna → hold ≈ 5 dager med default atr_per_day=1."""
    hold = estimate_expected_hold_days(entry=100.0, tp=105.0, atr=1.0)
    assert hold == pytest.approx(5.0)


def test_estimate_hold_short_tp_close_gives_small_hold() -> None:
    hold = estimate_expected_hold_days(entry=100.0, tp=100.3, atr=1.0)
    assert hold == pytest.approx(0.3)


def test_estimate_hold_makro_tp_none_returns_none() -> None:
    assert estimate_expected_hold_days(entry=100.0, tp=None, atr=1.0) is None


def test_estimate_hold_zero_atr_returns_none() -> None:
    """Defensiv: atr=0 skal ikke gi div-by-zero."""
    assert estimate_expected_hold_days(entry=100.0, tp=105.0, atr=0.0) is None


def test_estimate_hold_sell_direction_positive() -> None:
    """TP under entry (SELL) → positiv hold via absolutt-verdi."""
    hold = estimate_expected_hold_days(entry=100.0, tp=95.0, atr=1.0)
    assert hold == pytest.approx(5.0)


def test_estimate_hold_custom_atr_per_day() -> None:
    """Kalibrert volatilitet: 2 ATR/dag → halvparten så lang hold."""
    hold = estimate_expected_hold_days(entry=100.0, tp=110.0, atr=1.0, atr_per_day=2.0)
    assert hold == pytest.approx(5.0)  # 10 ATR / 2 per day


# ---------------------------------------------------------------------------
# classify_horizon
# ---------------------------------------------------------------------------


def test_classify_intraday_scalp() -> None:
    assert classify_horizon(entry_tf="M15", expected_hold_days=0.5) == Horizon.SCALP


def test_classify_intraday_long_hold_becomes_swing() -> None:
    """Intraday TF men hold > 1d → SWING (karakter overstyrer TF)."""
    assert classify_horizon(entry_tf="15m", expected_hold_days=10.0) == Horizon.SWING


def test_classify_daily_short_hold_scalp() -> None:
    """Daglig chart kan også produsere kort setup."""
    assert classify_horizon(entry_tf="D1", expected_hold_days=3.0) == Horizon.SCALP


def test_classify_daily_swing_hold() -> None:
    assert classify_horizon(entry_tf="D1", expected_hold_days=14.0) == Horizon.SWING


def test_classify_daily_boundary_swing_21_days() -> None:
    """21 dager skal være siste gyldige SWING (per PLAN-spenn 7-21)."""
    assert classify_horizon(entry_tf="D1", expected_hold_days=21.0) == Horizon.SWING


def test_classify_daily_over_21_days_becomes_makro() -> None:
    assert classify_horizon(entry_tf="D1", expected_hold_days=22.0) == Horizon.MAKRO


def test_classify_weekly_long_hold_makro() -> None:
    assert classify_horizon(entry_tf="W1", expected_hold_days=60.0) == Horizon.MAKRO


def test_classify_hold_none_is_makro() -> None:
    """Caller signaliserer MAKRO ved å sende hold=None."""
    assert classify_horizon(entry_tf="D1", expected_hold_days=None) == Horizon.MAKRO


def test_classify_4h_tf_uses_daily_plus_rules() -> None:
    """4H er ikke intraday per vår grense (≤30m); behandles som daglig."""
    assert classify_horizon(entry_tf="4H", expected_hold_days=14.0) == Horizon.SWING
    assert classify_horizon(entry_tf="4H", expected_hold_days=0.5) == Horizon.SCALP


def test_classify_unknown_tf_falls_back_to_daily_rules() -> None:
    """Ukjent TF behandles konservativt (daglig-regler)."""
    assert classify_horizon(entry_tf="nonsense", expected_hold_days=10.0) == Horizon.SWING
    assert classify_horizon(entry_tf="nonsense", expected_hold_days=60.0) == Horizon.MAKRO


# ---------------------------------------------------------------------------
# is_score_sufficient
# ---------------------------------------------------------------------------

_THRESHOLDS: dict[Horizon, float] = {
    Horizon.SCALP: 1.5,
    Horizon.SWING: 2.5,
    Horizon.MAKRO: 3.5,
}


def test_score_sufficient_at_threshold_is_true() -> None:
    assert is_score_sufficient(2.5, Horizon.SWING, _THRESHOLDS)


def test_score_sufficient_above_threshold() -> None:
    assert is_score_sufficient(3.0, Horizon.SWING, _THRESHOLDS)


def test_score_sufficient_below_threshold_is_false() -> None:
    assert not is_score_sufficient(2.0, Horizon.SWING, _THRESHOLDS)


def test_score_sufficient_missing_threshold_is_true() -> None:
    """Horisont mangler i config → anta konfigurasjon-feil håndteres andre steder."""
    partial: dict[Horizon, float] = {Horizon.SCALP: 1.5}
    assert is_score_sufficient(0.0, Horizon.SWING, partial)


# ---------------------------------------------------------------------------
# apply_horizon_hysteresis
# ---------------------------------------------------------------------------


def test_hysteresis_no_previous_returns_candidate() -> None:
    out = apply_horizon_hysteresis(
        candidate=Horizon.SWING,
        previous=None,
        score=2.5,
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SWING


def test_hysteresis_same_as_candidate_returns_unchanged() -> None:
    out = apply_horizon_hysteresis(
        candidate=Horizon.SWING,
        previous=Horizon.SWING,
        score=2.5,
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SWING


def test_hysteresis_far_from_threshold_uses_candidate() -> None:
    """Score klart over/under terskel → ingen hysterese, bruk candidate."""
    # Prev SWING, candidate SCALP, score 1.0 (klart under 1.5-buffer 0.075)
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=1.0,
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SCALP


def test_hysteresis_within_buffer_keeps_previous() -> None:
    """Score 2.4 med 5% buffer rundt 2.5 → |2.4-2.5|=0.1 ≤ 0.125 → keep SWING."""
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=2.4,
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SWING


def test_hysteresis_just_outside_buffer_uses_candidate() -> None:
    """Score 2.3 faller litt utenfor buffer (0.125) rundt 2.5 → SCALP."""
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=2.3,
        horizon_thresholds=_THRESHOLDS,
    )
    # |2.3 - 2.5| = 0.2 > 0.125. Men også: |2.3 - 1.5| = 0.8 > 0.075. Ingen i buffer.
    assert out == Horizon.SCALP


def test_hysteresis_symmetric_on_upgrade_too() -> None:
    """Oppgang SCALP → SWING dempes også: score 2.55 innenfor 2.5-buffer."""
    out = apply_horizon_hysteresis(
        candidate=Horizon.SWING,
        previous=Horizon.SCALP,
        score=2.55,
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SCALP


def test_hysteresis_custom_buffer_pct() -> None:
    """10% buffer gir større keep-zone."""
    # 10% av 2.5 = 0.25 → keep-zone 2.25 - 2.75
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=2.3,  # innenfor 10%-buffer
        horizon_thresholds=_THRESHOLDS,
        buffer_pct=0.10,
    )
    assert out == Horizon.SWING


def test_hysteresis_zero_buffer_disables() -> None:
    """buffer_pct=0 → ingen hysterese; candidate alltid."""
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=2.49,
        horizon_thresholds=_THRESHOLDS,
        buffer_pct=0.0,
    )
    assert out == Horizon.SCALP


def test_hysteresis_multiple_thresholds_any_match_holds() -> None:
    """Score nær MAKRO-terskel (3.5 ± 0.175) skal også trigge hysterese."""
    out = apply_horizon_hysteresis(
        candidate=Horizon.MAKRO,
        previous=Horizon.SWING,
        score=3.6,  # |3.6 - 3.5| = 0.1 ≤ 3.5*0.05 = 0.175 → keep SWING
        horizon_thresholds=_THRESHOLDS,
    )
    assert out == Horizon.SWING


def test_hysteresis_negative_threshold_skipped() -> None:
    """Negativ terskel (konfig-bug) ignoreres i buffer-sjekk."""
    bad_thresholds: dict[Horizon, float] = {
        Horizon.SCALP: 1.5,
        Horizon.SWING: -1.0,  # invalid
        Horizon.MAKRO: 3.5,
    }
    # Score 2.5 er nær 1.5-buffer (0.075? nei, |2.5-1.5|=1.0 > 0.075)
    # og 3.5-buffer (|2.5-3.5|=1.0 > 0.175). Ingen hysterese → candidate
    out = apply_horizon_hysteresis(
        candidate=Horizon.SCALP,
        previous=Horizon.SWING,
        score=2.5,
        horizon_thresholds=bad_thresholds,
    )
    # Uten den negative SWING-terskelen blir SCALP valgt
    assert out == Horizon.SCALP


# ---------------------------------------------------------------------------
# Kombinert: classify → hysterese → score-gate
# ---------------------------------------------------------------------------


def test_full_pipeline_consistent_across_runs() -> None:
    """Simuler: hold varierer litt (14d → 20d → 22d), hysterese forhindrer flipping.

    Med hold 22 ville classify returnere MAKRO, men hvis score er i
    buffer-sonen rundt MAKRO-terskelen (3.5) skal SWING beholdes.
    """
    # Run 1: hold=14, klassifiseres SWING
    candidate_1 = classify_horizon(entry_tf="D1", expected_hold_days=14.0)
    assert candidate_1 == Horizon.SWING

    # Run 2: hold=20, fortsatt SWING
    candidate_2 = classify_horizon(entry_tf="D1", expected_hold_days=20.0)
    assert candidate_2 == Horizon.SWING

    # Run 3: hold=22, klassifiseres MAKRO — men score 3.55 er i buffer
    candidate_3 = classify_horizon(entry_tf="D1", expected_hold_days=22.0)
    assert candidate_3 == Horizon.MAKRO

    stabilized = apply_horizon_hysteresis(
        candidate=candidate_3,
        previous=Horizon.SWING,  # fra run 2
        score=3.55,  # i buffer rundt 3.5 (±0.175)
        horizon_thresholds=_THRESHOLDS,
    )
    assert stabilized == Horizon.SWING
