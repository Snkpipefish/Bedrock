"""Tester for R3-horisont-modes på ``real_yield``.

Sub-fase 12.7 R3 (session 121). Verifiserer at:

- Default (mode=None) er bit-identisk pre-R3.
- ``mode="pct_12m"`` respekterer ``bull_when`` (low ⇒ 1−rank, high ⇒ rank).
- ``mode="pct_12m"`` er monotonisk på syntetisk strigende serie (Type B).
- ``mode="delta_5d_z"`` reagerer på regime-shift (Type C); bull_when
  håndteres i z→score-mappingen.
- ``mode="pct_36m"`` faller tilbake til pct_12m ved utilstrekkelig historikk.
- ``mode="extreme_flag_*"`` er bull_when-agnostisk og symmetrisk.
- ``_horizon`` LESES men endrer ikke output (R3-kontrakt).

Bruker samme in-memory mock-store-mønster som ``test_drivers_macro.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers.macro import real_yield


class _MockStore:
    def __init__(self, series: dict[str, pd.Series]):
        self._series = series

    def get_fundamentals(self, series_id: str, last_n: int | None = None) -> pd.Series:
        if series_id not in self._series:
            raise KeyError(series_id)
        s = self._series[series_id]
        if last_n is None:
            return s
        return s.tail(last_n)


def _daily(values: list[float], start: str = "2022-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


def _build_store_with_real_yield_series(real_yield_values: list[float]) -> _MockStore:
    """Bygg DGS10 og T10YIE slik at real_yield = real_yield_values per dag."""
    n = len(real_yield_values)
    # T10YIE konstant; DGS10 = T10YIE + real_yield
    inflation = [2.0] * n
    nominal = [inflation[i] + real_yield_values[i] for i in range(n)]
    return _MockStore(
        {
            "DGS10": _daily(nominal),
            "T10YIE": _daily(inflation),
        }
    )


# ---------------------------------------------------------------------------
# Type A — bit-identisk default
# ---------------------------------------------------------------------------


def test_default_mode_unchanged_pre_r3():
    """mode=None ⇒ dagens terskel-trapp på absolutt nivå."""
    store = _build_store_with_real_yield_series([-0.5])
    # bull_when=low default; current=-0.5 ⇒ score = 1.0 per
    # _DEFAULT_REAL_YIELD_THRESHOLDS_LOW.
    assert real_yield(store, "Gold", {}) == 1.0


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_12m
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series_bull_when_high():
    """bull_when=high: stigende real_yield ⇒ stigende score."""
    n = 300
    values = [(-1.0) + i * 0.01 for i in range(n)]  # -1.0 → 1.99

    # Iterér ved å trimme: bygg nytt store-objekt med kortere serie.
    prev = -1.0
    for cutoff in range(MIN_OBS_FOR_PCT12M_PLUS_1, n + 1, 20):
        truncated = list(values[:cutoff])
        truncated_store = _build_store_with_real_yield_series(truncated)
        score = real_yield(truncated_store, "USD", {"mode": "pct_12m", "bull_when": "high"})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at cutoff={cutoff}"
        prev = score
    # Siste: current er det høyeste — score nær 1.0.
    assert prev >= 0.95


def test_pct_12m_bull_when_low_inverts():
    """bull_when=low: stigende real_yield ⇒ FALLENDE score."""
    n = 300
    values = [(-1.0) + i * 0.01 for i in range(n)]
    store = _build_store_with_real_yield_series(values)
    # Hele serien — current er det høyeste ⇒ rank ≈ 1.0 ⇒ for bull_when=low
    # blir score ≈ 1 - 1.0 ≈ 0.0.
    score_low = real_yield(store, "Gold", {"mode": "pct_12m", "bull_when": "low"})
    score_high = real_yield(store, "USD", {"mode": "pct_12m", "bull_when": "high"})
    # Inversjons-relasjon: low + high ≈ 1.0 (kan være litt off pga rounding)
    assert score_low + score_high == pytest.approx(1.0, abs=0.005)
    assert score_low <= 0.05
    assert score_high >= 0.95


# Nødvendig for monotonisitets-testen — må starte etter MIN_OBS_FOR_PCTILE
MIN_OBS_FOR_PCT12M_PLUS_1 = 27  # MIN_OBS_FOR_PCTILE + 1


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta_5d_z
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift_bull_when_high():
    """delta_5d_z fanger 5-dagers hopp i real_yield. bull_when=high:
    positiv hopp ⇒ høy score."""
    import random

    rng = random.Random(42)
    n_pre = 300
    base = 1.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.02))

    # Hopp: +0.5pp er ~25σ på 0.02-σ-noise.
    series = [*values, values[-1] + 0.5]
    store = _build_store_with_real_yield_series(series)
    pre_store = _build_store_with_real_yield_series(values)

    pre_score = real_yield(pre_store, "USD", {"mode": "delta_5d_z", "bull_when": "high"})
    post_score = real_yield(store, "USD", {"mode": "delta_5d_z", "bull_when": "high"})

    assert post_score >= 0.75, f"delta_5d_z post-hopp = {post_score}, forventet >= 0.75"
    assert post_score > pre_score


def test_delta_5d_z_bull_when_low_inverts_score():
    """bull_when=low: positiv real_yield-hopp ⇒ LAV score (anti-Gold)."""
    import random

    rng = random.Random(42)
    n_pre = 300
    base = 1.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 0.02))

    series = [*values, values[-1] + 0.5]
    store = _build_store_with_real_yield_series(series)
    score_low = real_yield(store, "Gold", {"mode": "delta_5d_z", "bull_when": "low"})
    score_high = real_yield(store, "USD", {"mode": "delta_5d_z", "bull_when": "high"})
    # Inversjons-relasjon: low + high = 1.0 (z-trappen er mirror-symmetrisk
    # rundt z=0 → score=0.5).
    assert score_low + score_high == pytest.approx(1.0, abs=0.001)
    assert score_low <= 0.25  # Speil av >= 0.75 i den andre


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history():
    """<756 obs ⇒ fall-back til pct_12m, ikke 0.0."""
    values = [0.5 + i * 0.001 for i in range(300)]  # 300 < 756
    store = _build_store_with_real_yield_series(values)
    score_36m = real_yield(store, "USD", {"mode": "pct_36m", "bull_when": "high"})
    score_12m = real_yield(store, "USD", {"mode": "pct_12m", "bull_when": "high"})
    assert score_36m == score_12m
    assert score_36m > 0.0  # Fall-back, ikke defensive 0.0


# ---------------------------------------------------------------------------
# extreme_flag — bull_when-agnostisk
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile():
    """current = øverste i 252-vinduet ⇒ flag = 1.0 uavhengig av bull_when."""
    values = [0.0 + i * 0.001 for i in range(300)]  # strigende
    store = _build_store_with_real_yield_series(values)
    flag_low = real_yield(store, "Gold", {"mode": "extreme_flag_hard", "bull_when": "low"})
    flag_high = real_yield(store, "USD", {"mode": "extreme_flag_hard", "bull_when": "high"})
    assert flag_low == 1.0
    assert flag_high == 1.0


def test_extreme_flag_hard_at_median_returns_zero():
    """current nær median ⇒ flag = 0.0."""
    n = 300
    # Sett siste verdi til medianen av historikken
    values = [0.0 + i * 0.001 for i in range(n - 1)]
    median_value = values[len(values) // 2]
    values_with_median_current = [*values, median_value]
    store = _build_store_with_real_yield_series(values_with_median_current)
    flag = real_yield(store, "USD", {"mode": "extreme_flag_hard", "bull_when": "high"})
    assert flag == 0.0


# ---------------------------------------------------------------------------
# Ukjent mode + _horizon-lesing
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default():
    store = _build_store_with_real_yield_series([-0.5])
    default = real_yield(store, "Gold", {})
    unknown = real_yield(store, "Gold", {"mode": "no_such_mode"})
    assert default == unknown


def test_horizon_param_does_not_change_output():
    """R3-kontrakt: _horizon LESES men brukes ikke til å endre output."""
    store = _build_store_with_real_yield_series([-0.5])
    no_h = real_yield(store, "Gold", {})
    swing = real_yield(store, "Gold", {"_horizon": "SWING"})
    makro = real_yield(store, "Gold", {"_horizon": "MAKRO"})
    assert no_h == swing == makro
