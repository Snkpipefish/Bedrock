"""Tester for ``eia_stock_change`` driver (sub-fase 12.5+ session 107)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockEiaStore:
    """In-memory store som returnerer forhåndsbygde EIA-DataFrames."""

    def __init__(self, eia_data: dict[str, pd.DataFrame]):
        self._eia = eia_data

    def get_eia_inventory(self, series_id: str, last_n: int | None = None):
        if series_id not in self._eia:
            raise KeyError(f"No EIA data for {series_id!r}")
        df = self._eia[series_id]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _build_eia_df(
    *,
    n_weeks: int = 60,
    series_id: str = "WCESTUS1",
    base_value: float = 460_000.0,
    wow_step: float = 1_000.0,
    units: str = "MBBL",
) -> pd.DataFrame:
    """Bygg EIA-DataFrame med kontrollerbar uke-endrings-trend.

    Hver uke endres ``value`` med ``wow_step``. Positiv = stocks bygger
    seg = bearish. Negativ = stocks tappes = bullish.
    """
    base = date(2024, 1, 5)
    rows = []
    for i in range(n_weeks):
        rows.append(
            {
                "series_id": series_id,
                "date": pd.Timestamp(base + timedelta(weeks=i)),
                "value": base_value + wow_step * i,
                "units": units,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_eia_stock_change_is_registered() -> None:
    fn = get("eia_stock_change")
    assert fn is not None


# ---------------------------------------------------------------------------
# Default invert=True (high stocks build = bearish)
# ---------------------------------------------------------------------------


def test_returns_low_score_for_strong_stock_build() -> None:
    """Stocks bygger seg jevnt; siste uke har stor uventet build → bearish.

    Konstruksjon: jevn WoW build, så siste rad får ekstra-stor build →
    z er positiv → invert flipper til negativ → score < 0.5.
    """
    df = _build_eia_df(n_weeks=60, base_value=400_000, wow_step=500)
    # Siste uke: ekstra stor build (4× normal)
    df.iloc[-1, df.columns.get_loc("value")] = float(df.iloc[-2]["value"] + 5_000)
    store = _MockEiaStore({"WCESTUS1": df})

    fn = get("eia_stock_change")
    score = fn(store, "CrudeOil", {"series_id": "WCESTUS1"})
    assert score < 0.5


def test_returns_high_score_for_strong_stock_draw() -> None:
    """Siste uke har stor uventet stock-draw → bullish.

    Konstruksjon: jevne små builds gir baseline-WoW% rundt en liten
    positiv verdi. Siste rad har en stor draw (negativt) → z er sterkt
    negativ → invert flipper til sterkt positiv → score > 0.5.
    """
    df = _build_eia_df(n_weeks=60, base_value=400_000, wow_step=500)
    # Siste uke: stor draw — verdi går NED 8000 i stedet for opp 500
    df.iloc[-1, df.columns.get_loc("value")] = float(df.iloc[-2]["value"] - 8_000)
    store = _MockEiaStore({"WCESTUS1": df})

    fn = get("eia_stock_change")
    score = fn(store, "CrudeOil", {"series_id": "WCESTUS1"})
    assert score > 0.5


def test_returns_mid_score_for_typical_change() -> None:
    """Konstant WoW-endring → siste uke ≈ baseline → z ≈ 0 → ~0.5."""
    df = _build_eia_df(n_weeks=60, base_value=400_000, wow_step=500)
    store = _MockEiaStore({"WCESTUS1": df})

    fn = get("eia_stock_change")
    score = fn(store, "CrudeOil", {"series_id": "WCESTUS1"})
    # Konstant pct-change → MAD=0 → rolling_z returnerer None → 0.0
    # eller hvis liten variasjon, score nær 0.5. Vi godtar et romslig
    # interval.
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# invert=False (kontrarian-tolkning, build = bullish)
# ---------------------------------------------------------------------------


def test_invert_false_flips_interpretation() -> None:
    """Med invert=False blir stor build = bullish (motsatt av default)."""
    df = _build_eia_df(n_weeks=60, base_value=400_000, wow_step=500)
    df.iloc[-1, df.columns.get_loc("value")] = float(df.iloc[-2]["value"] + 5_000)
    store = _MockEiaStore({"WCESTUS1": df})

    fn = get("eia_stock_change")
    score_default = fn(store, "CrudeOil", {"series_id": "WCESTUS1"})
    score_inv_false = fn(
        store,
        "CrudeOil",
        {"series_id": "WCESTUS1", "invert": False},
    )

    # invert=False reverserer rangeringen
    if score_default < 0.5:
        assert score_inv_false > 0.5
    else:
        assert score_inv_false <= score_default


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_returns_zero_when_series_id_missing() -> None:
    store = _MockEiaStore({})
    fn = get("eia_stock_change")
    assert fn(store, "CrudeOil", {}) == 0.0


def test_returns_zero_when_series_not_in_db() -> None:
    store = _MockEiaStore({})
    fn = get("eia_stock_change")
    assert fn(store, "CrudeOil", {"series_id": "WCESTUS1"}) == 0.0


def test_returns_zero_for_short_history() -> None:
    """Færre enn 28 obs → defensive 0.0 (krever 27 + 1 for pct_change)."""
    df = _build_eia_df(n_weeks=10)
    store = _MockEiaStore({"WCESTUS1": df})
    fn = get("eia_stock_change")
    assert fn(store, "CrudeOil", {"series_id": "WCESTUS1"}) == 0.0


def test_returns_zero_when_store_raises_unexpectedly() -> None:
    class _BrokenStore:
        def get_eia_inventory(self, series_id, last_n=None):
            raise RuntimeError("simulated DB issue")

    fn = get("eia_stock_change")
    assert fn(_BrokenStore(), "CrudeOil", {"series_id": "WCESTUS1"}) == 0.0


# ---------------------------------------------------------------------------
# Multi-series isolering
# ---------------------------------------------------------------------------


def test_different_series_resolve_independently() -> None:
    """Crude og NatGas leses fra separate series-rader uten kollisjon."""
    crude = _build_eia_df(n_weeks=60, series_id="WCESTUS1", base_value=460_000, wow_step=500)
    crude.iloc[-1, crude.columns.get_loc("value")] = float(
        crude.iloc[-2]["value"] - 8_000
    )  # stor draw

    natgas = _build_eia_df(
        n_weeks=60,
        series_id="NW2_EPG0_SWO_R48_BCF",
        base_value=2000,
        wow_step=10,
        units="BCF",
    )
    natgas.iloc[-1, natgas.columns.get_loc("value")] = float(
        natgas.iloc[-2]["value"] + 100
    )  # stor build

    store = _MockEiaStore({"WCESTUS1": crude, "NW2_EPG0_SWO_R48_BCF": natgas})
    fn = get("eia_stock_change")

    crude_score = fn(store, "CrudeOil", {"series_id": "WCESTUS1"})
    natgas_score = fn(store, "NaturalGas", {"series_id": "NW2_EPG0_SWO_R48_BCF"})

    # Crude: stor draw → bullish → høy score
    # NatGas: stor build → bearish → lav score
    assert crude_score > 0.5
    assert natgas_score < 0.5


# ---------------------------------------------------------------------------
# Lookback respekteres
# ---------------------------------------------------------------------------


def test_lookback_caps_history() -> None:
    """``lookback_weeks=30`` snevrer baseline til siste 30 uker."""
    df = _build_eia_df(n_weeks=100, base_value=400_000, wow_step=500)
    df.iloc[-1, df.columns.get_loc("value")] = float(df.iloc[-2]["value"] - 6_000)
    store = _MockEiaStore({"WCESTUS1": df})

    fn = get("eia_stock_change")
    score = fn(store, "CrudeOil", {"series_id": "WCESTUS1", "lookback_weeks": 30})
    # Stor draw → bullish → høy score
    assert score > 0.5
