# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportReturnType=false
"""Tester for ``unica_change`` driver (sub-fase 12.5+ session 112)."""

from __future__ import annotations

import pandas as pd

from bedrock.data.schemas import UNICA_REPORTS_COLS
from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockUnicaStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_unica_reports(self, last_n: int | None = None) -> pd.DataFrame:
        if last_n is None:
            return self._df
        return self._df.tail(last_n).reset_index(drop=True)


def _row(**overrides) -> pd.DataFrame:
    """Bygg UNICA-rader med valgfrie overrides på siste rad.

    Genererer 12 rader per default (≥ min_samples-guard fra Bug-2) slik at
    eksisterende tester ikke trenger endre params. Overrides settes kun på
    siste rad — de andre 11 fungerer som padding for sample-count-guarden.
    """
    base = dict.fromkeys(UNICA_REPORTS_COLS)
    rows = [
        {**base, "report_date": pd.Timestamp("2026-04-15") - pd.Timedelta(days=15 * (11 - i))}
        for i in range(11)
    ]
    last = dict(base)
    last["report_date"] = pd.Timestamp("2026-04-15")
    last.update(overrides)
    rows.append(last)
    return pd.DataFrame(rows, columns=list(UNICA_REPORTS_COLS))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registered() -> None:
    assert get("unica_change") is not None


# ---------------------------------------------------------------------------
# Sub-fase 12.10 Bunke 1 Bug-2: min_samples-guard
# ---------------------------------------------------------------------------


def test_min_samples_guard_returns_neutral_when_table_sparse() -> None:
    """Hvis UNICA-tabellen har < min_samples rader, returnér 0.5 (nøytral)."""
    # Bygg en 5-rads fixture (under default min_samples=12)
    base = dict.fromkeys(UNICA_REPORTS_COLS)
    rows = [
        {**base, "report_date": pd.Timestamp(f"2026-01-{i:02d}"), "sugar_production_yoy_pct": -15.0}
        for i in range(1, 6)
    ]
    df = pd.DataFrame(rows, columns=list(UNICA_REPORTS_COLS))
    store = _MockUnicaStore(df)
    fn = get("unica_change")
    # Default min_samples=12; 5 rader er for lite → 0.5 selv om verdien
    # ellers ville gi 1.0
    assert fn(store, "Sugar", {}) == 0.5


def test_min_samples_guard_overridable_via_param() -> None:
    """min_samples kan overrides via YAML-param."""
    base = dict.fromkeys(UNICA_REPORTS_COLS)
    rows = [
        {**base, "report_date": pd.Timestamp(f"2026-01-{i:02d}"), "sugar_production_yoy_pct": -15.0}
        for i in range(1, 6)
    ]
    df = pd.DataFrame(rows, columns=list(UNICA_REPORTS_COLS))
    store = _MockUnicaStore(df)
    fn = get("unica_change")
    # min_samples=3 — 5 rader er nok → vanlig score (-15% YoY = 1.0)
    assert fn(store, "Sugar", {"min_samples": 3}) == 1.0


# ---------------------------------------------------------------------------
# Default metric: sugar_production_yoy
# ---------------------------------------------------------------------------


def test_strong_shortfall_yoy_returns_1() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=-15.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 1.0


def test_modest_growth_yoy_returns_035() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=3.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 0.35


def test_strong_growth_yoy_returns_015() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=10.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 0.15


def test_flat_yoy_returns_05() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=0.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 0.5


def test_null_yoy_returns_neutral() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=None))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 0.5


# ---------------------------------------------------------------------------
# crush_yoy metric
# ---------------------------------------------------------------------------


def test_crush_yoy_metric() -> None:
    store = _MockUnicaStore(_row(crush_yoy_pct=-7.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "crush_yoy"}) == 0.85


# ---------------------------------------------------------------------------
# mix_sugar_pct metric (abs-mode med egen step-mapping)
# ---------------------------------------------------------------------------


def test_mix_sugar_pct_low_etanol_tilt_bullish() -> None:
    """mix_sugar_pct=44% (etanol-tilt) → 1.0."""
    store = _MockUnicaStore(_row(mix_sugar_pct=44.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_pct"}) == 1.0


def test_mix_sugar_pct_balance_returns_05() -> None:
    """mix_sugar_pct=50% (balanse) → 0.5."""
    store = _MockUnicaStore(_row(mix_sugar_pct=50.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_pct"}) == 0.5


def test_mix_sugar_pct_high_sugar_tilt_bearish() -> None:
    """mix_sugar_pct=55% (sukker-tilt) → 0.15."""
    store = _MockUnicaStore(_row(mix_sugar_pct=55.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_pct"}) == 0.15


# ---------------------------------------------------------------------------
# mix_sugar_change metric (current - prev)
# ---------------------------------------------------------------------------


def test_mix_sugar_change_negative_bullish() -> None:
    """current 48 vs prev 51 → -3 → 0.65 (bullish)."""
    store = _MockUnicaStore(_row(mix_sugar_pct=48.0, mix_sugar_pct_prev=51.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_change"}) == 0.65


def test_mix_sugar_change_positive_bearish() -> None:
    """current 53 vs prev 48 → +5 → 0.35 (bearish)."""
    store = _MockUnicaStore(_row(mix_sugar_pct=53.0, mix_sugar_pct_prev=48.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_change"}) == 0.35


def test_mix_sugar_change_null_returns_neutral() -> None:
    store = _MockUnicaStore(_row(mix_sugar_pct=None, mix_sugar_pct_prev=None))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "mix_sugar_change"}) == 0.5


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_store_raises() -> None:
    class _Broken:
        def get_unica_reports(self, last_n=None):
            raise RuntimeError("DB error")

    fn = get("unica_change")
    assert fn(_Broken(), "Sugar", {}) == 0.0


def test_returns_zero_when_db_empty() -> None:
    store = _MockUnicaStore(pd.DataFrame(columns=list(UNICA_REPORTS_COLS)))
    fn = get("unica_change")
    assert fn(store, "Sugar", {}) == 0.0


def test_returns_zero_for_unknown_metric() -> None:
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=-5.0))
    fn = get("unica_change")
    assert fn(store, "Sugar", {"metric": "nonexistent_metric"}) == 0.0


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds() -> None:
    """YAML kan overstyre step-mapping."""
    store = _MockUnicaStore(_row(sugar_production_yoy_pct=-3.0))
    fn = get("unica_change")
    score = fn(
        store,
        "Sugar",
        {"thresholds": [(-5, 0.9), (0, 0.4), (5, 0.2)]},
    )
    # -3 ≤ 0 → 0.4
    assert score == 0.4
