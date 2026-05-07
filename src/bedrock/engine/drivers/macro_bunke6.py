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
~52 mnd (~4.3 år) historikk. Default invert=True er korrekt: høy MoM%
NGPL-extraction = mer wet-gas-drilling = mer associated-gas → mer dry-
gas til pipeline = bearish NG (samme polaritet som petroleum-stocks).

POLARITY-FIX (sub-fase 12.10 follow-up audit, sign-inversjons-runde):
Bunke6 deler series i to kategorier:

- **Stock-metrikker** (WDISTUS1 distillate, WPRSTUS1 propane, N9060US2 NGPL
  production): høy WoW% = build = bearish prising. ``invert=True`` (matcher
  ``eia_stock_change``-default).
- **Flow/demand-metrikker** (WPULEUS3 refinery throughput, WRPUPUS2 demand-
  proxy, WCRIMUS2 imports, WGFUPUS2 gasoline demand): høy WoW% = sterkere
  demand = bullish prising. **Disse trenger `invert=False`** — ellers
  inverteres signal-tegnet.

Pre-fix-bug: alle 4 flow-wrappers delegerte med default ``invert=True``, så
``bull_when: high`` i Brent/CrudeOil-YAMLene var et silent no-op (default-
banen i ``eia_stock_change`` leser ikke ``bull_when``). Resultat: refinery
utilization, gasoline demand, imports og petroleum supplied bidro med
inverterte signaler i CrudeOil/Brent macro-familien.

Fix: hvert wrapper setter sin egen ``invert``-default eksplisitt via
``setdefault``. Caller kan fortsatt override per YAML (``params: {invert: ...}``).
"""

from __future__ import annotations

from typing import Any

from bedrock.engine.drivers import get, register


def _eia_wrapper(
    store: Any,
    instrument: str,
    params: dict,
    *,
    series_id: str,
    default_invert: bool,
) -> float:
    """Delegate til eksisterende eia_stock_change med hardkodet series_id
    + per-wrapper invert-default.

    Caller-params (mode, lookback osv) propageres uendret. ``invert`` bruker
    ``setdefault`` slik at YAML-override fortsatt fungerer (`params:
    {invert: ...}`).
    """
    base_fn = get("eia_stock_change")
    sub_params = dict(params)
    sub_params["series_id"] = series_id
    sub_params.setdefault("invert", default_invert)
    return base_fn(store, instrument, sub_params)


@register("eia_distillate_change")
def eia_distillate_change(store: Any, instrument: str, params: dict) -> float:
    """Distillate Fuel Oil Stocks (WDISTUS1) WoW-z. Stock-metrikk —
    invert=True default (build = bearish for kraft/diesel-prising)."""
    return _eia_wrapper(store, instrument, params, series_id="WDISTUS1", default_invert=True)


@register("eia_propane_change")
def eia_propane_change(store: Any, instrument: str, params: dict) -> float:
    """Propane/Propylene Stocks (WPRSTUS1) WoW-z. Stock-metrikk —
    invert=True default (build = bearish)."""
    return _eia_wrapper(store, instrument, params, series_id="WPRSTUS1", default_invert=True)


@register("eia_refinery_utilization_z")
def eia_refinery_utilization_z(store: Any, instrument: str, params: dict) -> float:
    """Refiner Net Inputs of Crude Oil (WPULEUS3) — flow/demand-metrikk.

    Høy WoW% = refinerier kjører hardere = sterkere crude-demand =
    BULLISH for crude. Default ``invert=False`` (motsatt av eia_stock_change-
    default fordi dette er flow, ikke stock). Override via
    ``params: {invert: true}`` hvis YAML vil snu fortolkningen."""
    return _eia_wrapper(store, instrument, params, series_id="WPULEUS3", default_invert=False)


@register("eia_petroleum_supplied")
def eia_petroleum_supplied(store: Any, instrument: str, params: dict) -> float:
    """US Petroleum Products Supplied (WRPUPUS2) — total demand-proxy.

    Flow-metrikk: høy WoW% = sterk total petroleum-demand = bullish crude.
    Default ``invert=False``."""
    return _eia_wrapper(store, instrument, params, series_id="WRPUPUS2", default_invert=False)


@register("eia_imports_crude")
def eia_imports_crude(store: Any, instrument: str, params: dict) -> float:
    """US Imports of Crude Oil (WCRIMUS2) — flow-metrikk.

    Høy WoW% = US importerer mer = innenlandsk demand > tilbud = bullish
    crude (US-balanse-signal). Default ``invert=False``."""
    return _eia_wrapper(store, instrument, params, series_id="WCRIMUS2", default_invert=False)


@register("eia_gasoline_demand")
def eia_gasoline_demand(store: Any, instrument: str, params: dict) -> float:
    """Finished Motor Gasoline Supplied (WGFUPUS2) — flow/demand-metrikk.

    Høy WoW% = sterk gasoline-demand = bullish raffinerings-marginer og
    crude. Default ``invert=False``."""
    return _eia_wrapper(store, instrument, params, series_id="WGFUPUS2", default_invert=False)


@register("eia_natgas_processing")
def eia_natgas_processing(store: Any, instrument: str, params: dict) -> float:
    """US NGPL Production — Gaseous Equivalent (N9060US2) MoM-z (Spor F8).

    Monthly serie fra route ``natural-gas/prod/sum``. Z-score av siste
    MoM% pct-change vs ~52 mnd historikk (samme math som default
    eia_stock_change-banen — cadence-agnostisk).

    Default ``invert=True`` er korrekt: høy MoM% NGPL-extraction = mer
    wet-gas-drilling-aktivitet = mer associated-gas → mer dry-gas til
    Henry-Hub-pipeline = bearish NG. Samme polaritet som petroleum-
    stocks (build = bear). Eksisterende `eia_stock_change`-modes
    (pct_12m, etc) fungerer på samme MoM%-serie.
    """
    return _eia_wrapper(store, instrument, params, series_id="N9060US2", default_invert=True)


__all__ = [
    "eia_distillate_change",
    "eia_gasoline_demand",
    "eia_imports_crude",
    "eia_natgas_processing",
    "eia_petroleum_supplied",
    "eia_propane_change",
    "eia_refinery_utilization_z",
]
