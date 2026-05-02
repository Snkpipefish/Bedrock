"""Sub-fase 12.10 Bunke 6 #22 — EIA-utvidelse via thin wrappers.

Levert: 7 driver-navn som mapper til ulike EIA series_ids. Internt
delegerer alle til eksisterende ``eia_stock_change``-driver i macro.py.

Wrapper-pattern brukt fordi:
1. Spec lister navngitte drivere (PLAN § 22.2 #22)
2. eia_stock_change har allerede full mode-suite (default + pct_12m + pct_36m
   + delta_5d_z + delta_20d_z + extreme_flag_*) per ADR-010
3. Alternativ: forsterke `eia_stock_change`'s YAML-mapping — men da må alle
   YAMLs spesifisere series_id som kan glemmes; thin wrappers er ergonomisk

Backfill: 11180 rader på 6 weekly serier (2026-05-02 bunke6) +
~430 rader på N9060US2 monthly (Spor F8 2026-05-02).

Spor F8 (2026-05-02): ``eia_natgas_processing`` LEVERT. Bruker monthly
N9060US2 (NGPL Production, route ``natural-gas/prod/sum``). Math er
cadence-agnostisk: pct_change blir MoM% i stedet for WoW%, z-score mot
~52 mnd (~4.3 år) historikk. YAML må sette ``invert: false`` siden
semantikken er flipped (høy MoM% i NGPL-extraction = mer wet-gas-
prosessering = mindre dry-gas til pipeline = bull NG).
"""

from __future__ import annotations

from typing import Any

from bedrock.engine.drivers import get, register


def _eia_wrapper(store: Any, instrument: str, params: dict, *, series_id: str) -> float:
    """Delegate til eksisterende eia_stock_change med hardkodet series_id.

    Caller-params (mode, bull_when, lookback osv) propageres uendret.
    """
    base_fn = get("eia_stock_change")
    sub_params = dict(params)
    sub_params["series_id"] = series_id
    return base_fn(store, instrument, sub_params)


@register("eia_distillate_change")
def eia_distillate_change(store: Any, instrument: str, params: dict) -> float:
    """Distillate Fuel Oil Stocks (WDISTUS1) WoW-z. Default invert=True
    (build = bear)."""
    return _eia_wrapper(store, instrument, params, series_id="WDISTUS1")


@register("eia_propane_change")
def eia_propane_change(store: Any, instrument: str, params: dict) -> float:
    """Propane/Propylene Stocks (WPRSTUS1) WoW-z."""
    return _eia_wrapper(store, instrument, params, series_id="WPRSTUS1")


@register("eia_refinery_utilization_z")
def eia_refinery_utilization_z(store: Any, instrument: str, params: dict) -> float:
    """Refiner Net Inputs of Crude Oil (WPULEUS3) — proxy for utilization.
    Bull_when='high' typisk (høy utilization = sterk demand-mønster)."""
    return _eia_wrapper(store, instrument, params, series_id="WPULEUS3")


@register("eia_petroleum_supplied")
def eia_petroleum_supplied(store: Any, instrument: str, params: dict) -> float:
    """US Petroleum Products Supplied (WRPUPUS2) — total demand-proxy."""
    return _eia_wrapper(store, instrument, params, series_id="WRPUPUS2")


@register("eia_imports_crude")
def eia_imports_crude(store: Any, instrument: str, params: dict) -> float:
    """US Imports of Crude Oil (WCRIMUS2)."""
    return _eia_wrapper(store, instrument, params, series_id="WCRIMUS2")


@register("eia_gasoline_demand")
def eia_gasoline_demand(store: Any, instrument: str, params: dict) -> float:
    """Finished Motor Gasoline Supplied (WGFUPUS2) — gasoline-demand-proxy."""
    return _eia_wrapper(store, instrument, params, series_id="WGFUPUS2")


@register("eia_natgas_processing")
def eia_natgas_processing(store: Any, instrument: str, params: dict) -> float:
    """US NGPL Production — Gaseous Equivalent (N9060US2) MoM-z (Spor F8).

    Monthly serie fra route ``natural-gas/prod/sum``. Z-score av siste
    MoM% pct-change vs ~52 mnd historikk (samme math som default
    eia_stock_change-banen — cadence-agnostisk).

    Default invert-semantikk er flipped: høy MoM% NGPL-extraction =
    mer wet-gas-prosessering = mindre dry-gas til Henry-Hub-pipeline =
    bull NG. YAML må sette ``invert: false`` for å overstyre default
    invert=True. Eksisterende `eia_stock_change`-modes (pct_12m, etc)
    fungerer på samme MoM%-serie.
    """
    return _eia_wrapper(store, instrument, params, series_id="N9060US2")


__all__ = [
    "eia_distillate_change",
    "eia_gasoline_demand",
    "eia_imports_crude",
    "eia_natgas_processing",
    "eia_petroleum_supplied",
    "eia_propane_change",
    "eia_refinery_utilization_z",
]
