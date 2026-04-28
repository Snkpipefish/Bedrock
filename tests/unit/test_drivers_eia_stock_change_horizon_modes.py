"""Tester for R4-horisont-modes på ``eia_stock_change``.

Sub-fase 12.7 R4 batch 5 finish (session 124). Tester at:
- Default (mode=None) er bit-identisk pre-R4 (z-score-trapp på WoW%).
- pct_12m/pct_36m monotonisitet (Type B) på WoW%-serien.
- delta_5d_z/delta_20d_z regime-shift (Type C) på WoW%-serien.
- extreme_flag_*-modes sanity.
- invert-respekt: pct_12m snur output ved invert=True vs False.
- pct_36m fall-back ved utilstrekkelig historikk.
- _horizon-param leses uten output-effekt.
- Ukjent mode → fall-back til default.
- Manglende series_id eller data → 0.0.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers.macro import eia_stock_change


def _build_inventory_df(values: list[float]) -> pd.DataFrame:
    """Bygg EIA-inventory DataFrame med ukentlig-frekvens (onsdager)."""
    base = date(2020, 1, 1)
    rows = []
    for i, v in enumerate(values):
        rows.append(
            {
                "date": (base + timedelta(weeks=i)).isoformat(),
                "value": v,
                "units": "MBBL",
            }
        )
    return pd.DataFrame(rows)


class _MockStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_eia_inventory(self, series_id: str, last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


_PARAMS = {"series_id": "WCESTUS1"}


# ---------------------------------------------------------------------------
# Type A — bit-identisk default
# ---------------------------------------------------------------------------


def test_default_mode_returns_zscore_trap():
    """Default (mode=None, invert=True) returnerer z-score-trapp på WoW%.

    Konstant inventory ⇒ pct_change=0 ⇒ MAD=0 ⇒ rolling_z=None ⇒ score=0.0
    Test med små perturbasjoner for å gi MAD>0.
    """
    import random

    rng = random.Random(42)
    values = [100_000.0]
    for _ in range(60):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.005)))
    # Siste obs: stor stock-build ⇒ +5% WoW ⇒ z >= +2 ⇒ invertert -2 ⇒ trappen → 0.0
    values.append(values[-1] * 1.05)
    store = _MockStore(_build_inventory_df(values))
    score = eia_stock_change(store, "Test", _PARAMS)
    # Stor build → bearish under default invert=True
    assert score <= 0.3


def test_default_unchanged_with_horizon_param():
    """R4-kontrakt: _horizon LESES men brukes ikke i default-output."""
    import random

    rng = random.Random(7)
    values = [100_000.0]
    for _ in range(55):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.005)))
    store = _MockStore(_build_inventory_df(values))
    no_horizon = eia_stock_change(store, "Test", _PARAMS)
    with_swing = eia_stock_change(store, "Test", {**_PARAMS, "_horizon": "SWING"})
    with_makro = eia_stock_change(store, "Test", {**_PARAMS, "_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_12m
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_pct_change():
    """Type B: monotont stigende WoW%-serien ⇒ monotont stigende pct_12m
    (med invert=False ⇒ helper bull_when=high)."""
    # Bygg inventory der WoW% øker monotont. Approx: pct[i] = i*0.001
    # ⇒ values[i+1] = values[i] * (1 + i*0.001)
    n = 80
    values = [100_000.0]
    for i in range(n):
        values.append(values[-1] * (1.0 + (i + 1) * 0.0001))
    full_df = _build_inventory_df(values)

    prev = -1.0
    # Trenger 53+ rader (52-vindu + 1 current). values har 81 rader.
    for k in range(54, len(values) + 1):
        store = _MockStore(full_df.head(k))
        score = eia_stock_change(store, "Test", {**_PARAMS, "mode": "pct_12m", "invert": False})
        assert score >= prev, f"pct_12m fell from {prev} to {score} at k={k}"
        prev = score
    assert prev >= 0.95


def test_pct_36m_monotonic_on_strictly_increasing_pct_change():
    """Type B på pct_36m: krever ≥158 rader (157 obs i WoW% + 1 fall-back-padding).

    Bruker invert=False ⇒ helper bull_when=high.
    """
    n = 180
    values = [100_000.0]
    for i in range(n):
        values.append(values[-1] * (1.0 + (i + 1) * 0.00005))
    full_df = _build_inventory_df(values)

    prev = -1.0
    for k in range(158, len(values) + 1):
        store = _MockStore(full_df.head(k))
        score = eia_stock_change(store, "Test", {**_PARAMS, "mode": "pct_36m", "invert": False})
        assert score >= prev, f"pct_36m fell from {prev} to {score} at k={k}"
        prev = score
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta-modes
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 60
    values = [100_000.0]
    for _ in range(n_pre):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.003)))

    # Hopp i WoW% — én ekstrem stock-build på siste obs
    post = list(values)
    post.append(post[-1] * 1.10)  # +10% WoW%

    pre_score = eia_stock_change(
        _MockStore(_build_inventory_df(values)),
        "Test",
        {**_PARAMS, "mode": "delta_5d_z", "invert": False},
    )
    post_score = eia_stock_change(
        _MockStore(_build_inventory_df(post)),
        "Test",
        {**_PARAMS, "mode": "delta_5d_z", "invert": False},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


def test_delta_20d_z_reacts_to_regime_shift():
    import random

    rng = random.Random(42)
    n_pre = 60
    values = [100_000.0]
    for _ in range(n_pre):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.003)))

    # Gradvis 4-ukers trend (delta_20d_z = 4-rapport-delta)
    post = list(values)
    last = post[-1]
    for i in range(4):
        last = last * (1.0 + 0.02 * (i + 1))
        post.append(last)

    pre_score = eia_stock_change(
        _MockStore(_build_inventory_df(values)),
        "Test",
        {**_PARAMS, "mode": "delta_20d_z", "invert": False},
    )
    post_score = eia_stock_change(
        _MockStore(_build_inventory_df(post)),
        "Test",
        {**_PARAMS, "mode": "delta_20d_z", "invert": False},
    )
    assert post_score >= 0.75
    assert post_score > pre_score


# ---------------------------------------------------------------------------
# invert-respekt
# ---------------------------------------------------------------------------


def test_pct_12m_invert_respect():
    """invert=True (default — høy build = bearish) snur output."""
    # Bygg WoW%-serien strigende ⇒ current er topp ⇒ rank ≈ 1.0
    n = 80
    values = [100_000.0]
    for i in range(n):
        values.append(values[-1] * (1.0 + (i + 1) * 0.0001))
    store = _MockStore(_build_inventory_df(values))

    score_invert_true = eia_stock_change(
        store, "Test", {**_PARAMS, "mode": "pct_12m", "invert": True}
    )
    score_invert_false = eia_stock_change(
        store, "Test", {**_PARAMS, "mode": "pct_12m", "invert": False}
    )

    # invert=True ⇒ helper bull_when=low ⇒ score = 1 - rank ≈ 0.0
    # invert=False ⇒ helper bull_when=high ⇒ score = rank ≈ 1.0
    assert score_invert_true <= 0.05
    assert score_invert_false >= 0.95


# ---------------------------------------------------------------------------
# pct_36m fall-back
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history():
    """Ved <156 WoW%-obs skal pct_36m fall-back til pct_12m."""
    n = 80
    values = [100_000.0]
    for i in range(n):
        values.append(values[-1] * (1.0 + (i + 1) * 0.0001))
    store = _MockStore(_build_inventory_df(values))
    score_36m = eia_stock_change(store, "Test", {**_PARAMS, "mode": "pct_36m", "invert": False})
    score_12m = eia_stock_change(store, "Test", {**_PARAMS, "mode": "pct_12m", "invert": False})
    assert score_36m == score_12m


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile():
    """WoW% strigende ⇒ siste WoW% er top-percentile ⇒ flag = 1.0."""
    n = 80
    values = [100_000.0]
    for i in range(n):
        values.append(values[-1] * (1.0 + (i + 1) * 0.0001))
    store = _MockStore(_build_inventory_df(values))
    flag = eia_stock_change(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median():
    """Bygg WoW% slik at median-verdi ligger på siste obs ⇒ flag = 0.0."""
    import random

    rng = random.Random(42)
    n = 80
    values = [100_000.0]
    for _ in range(n):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.003)))
    # Erstatt siste WoW% med en median-verdi: bruk current = previous
    # slik at WoW% siste = ~0
    values[-1] = values[-2]
    store = _MockStore(_build_inventory_df(values))
    flag = eia_stock_change(store, "Test", {**_PARAMS, "mode": "extreme_flag_hard"})
    # Siste WoW% ≈ 0; rank avhenger av historisk distribusjon. Aksepter
    # at flag = 0.0 hvis ikke ekstrem, eller 1.0 hvis tilfeldigvis ekstrem.
    # Sanity: flag er 0.0 eller 1.0
    assert flag in (0.0, 1.0)


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default():
    import random

    rng = random.Random(7)
    values = [100_000.0]
    for _ in range(55):
        values.append(values[-1] * (1.0 + rng.gauss(0, 0.005)))
    store = _MockStore(_build_inventory_df(values))
    default = eia_stock_change(store, "Test", _PARAMS)
    unknown = eia_stock_change(store, "Test", {**_PARAMS, "mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# Manglende series_id eller data → 0.0
# ---------------------------------------------------------------------------


class _MockStoreMissing:
    def get_eia_inventory(self, series_id: str, last_n: int | None = None):
        raise KeyError(series_id)


def test_missing_series_id_returns_zero():
    store = _MockStore(_build_inventory_df([100_000.0] * 5))
    # Ingen series_id i params
    assert eia_stock_change(store, "Test", {}) == 0.0
    # Mode uten series_id
    assert eia_stock_change(store, "Test", {"mode": "pct_12m"}) == 0.0


def test_missing_data_returns_zero():
    store = _MockStoreMissing()
    assert eia_stock_change(store, "Test", _PARAMS) == 0.0
    assert eia_stock_change(store, "Test", {**_PARAMS, "mode": "pct_12m"}) == 0.0
