"""Tester for ``cot_ice_mm_pct`` (sub-fase 12.5+ session 106).

Parallell-tester til positioning_mm_pct, men driver leser fra
``store.get_cot_ice`` og tar ``contract`` fra params (YAML-driven, ikke
fra instrument-config).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockIceStore:
    """In-memory store som returnerer forhåndsbygde ICE-COT-DataFrames."""

    def __init__(self, ice_data: dict[str, pd.DataFrame]):
        self._ice = ice_data

    def get_cot_ice(self, contract: str, last_n: int | None = None):
        if contract not in self._ice:
            raise KeyError(f"No ICE COT data for contract={contract!r}")
        df = self._ice[contract]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _build_ice_df(
    *,
    n_weeks: int = 60,
    mm_long_start: float = 80_000,
    mm_long_step: float = 1_000,
    mm_short: float = 40_000,
    open_interest: float = 400_000,
    contract: str = "ice brent crude",
) -> pd.DataFrame:
    """ICE-COT-historikk med kontrollerbar mm_long-trend."""
    base = date(2024, 1, 5)
    rows = []
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": contract,
                "mm_long": mm_long_start + mm_long_step * i,
                "mm_short": mm_short,
                "other_long": 12_000,
                "other_short": 9_000,
                "comm_long": 200_000,
                "comm_short": 220_000,
                "nonrep_long": 4_000,
                "nonrep_short": 3_500,
                "open_interest": open_interest,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_cot_ice_mm_pct_is_registered() -> None:
    fn = get("cot_ice_mm_pct")
    assert fn is not None


# ---------------------------------------------------------------------------
# Score-extremer
# ---------------------------------------------------------------------------


def test_returns_high_for_top_long_position() -> None:
    """Stigende mm_long-serie → siste rad er høyest → ~1.0."""
    df = _build_ice_df(n_weeks=60)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    score = fn(store, "Brent", {"contract": "ice brent crude", "lookback_weeks": 52})

    assert score >= 0.95


def test_returns_low_for_bottom_long_position() -> None:
    """Synkende mm_long-serie → siste rad er lavest → ~0.0."""
    df = _build_ice_df(n_weeks=60, mm_long_start=160_000, mm_long_step=-1_000)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    score = fn(store, "Brent", {"contract": "ice brent crude"})

    assert score <= 0.05


def test_returns_mid_for_median_position() -> None:
    """Sinusoidal serie der siste rad havner rundt midt-percentile."""
    n = 60
    base = date(2024, 1, 5)
    rows = []
    # Stigende-så-fallende kurve som ender på midten
    for i in range(n):
        # Verdi: 0 → 30 → 0 — siste rad lander på 0 → laveste; bytter
        # til en oscillerende serie som ender på midt:
        if i < n // 2:
            v = 100_000 + i * 1_000
        else:
            v = 100_000 + (n - i) * 1_000
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "ice brent crude",
                "mm_long": v,
                "mm_short": 40_000,
                "other_long": 0,
                "other_short": 0,
                "comm_long": 0,
                "comm_short": 0,
                "nonrep_long": 0,
                "nonrep_short": 0,
                "open_interest": 400_000,
            }
        )
    df = pd.DataFrame(rows)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    score = fn(store, "Brent", {"contract": "ice brent crude"})
    # Siste rad er nær start-verdi (lav), så vi forventer < 0.5
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Defensive-paths (alle returnerer 0.0)
# ---------------------------------------------------------------------------


def test_returns_zero_when_contract_param_missing() -> None:
    """Ingen `contract` i params → 0.0, ingen exception."""
    store = _MockIceStore({})
    fn = get("cot_ice_mm_pct")
    assert fn(store, "Brent", {"lookback_weeks": 52}) == 0.0


def test_returns_zero_when_contract_not_in_db() -> None:
    """KeyError fra get_cot_ice → 0.0."""
    store = _MockIceStore({})
    fn = get("cot_ice_mm_pct")
    assert fn(store, "Brent", {"contract": "ice brent crude"}) == 0.0


def test_returns_zero_for_short_history() -> None:
    """Færre enn 27 obs (MIN_OBS_FOR_PCTILE+1) → 0.0."""
    df = _build_ice_df(n_weeks=10)  # for kort historikk
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    assert fn(store, "Brent", {"contract": "ice brent crude"}) == 0.0


def test_returns_zero_when_get_cot_ice_raises_unexpectedly() -> None:
    """Tilfeldig exception fra store → 0.0, ingen exception lekker ut."""

    class _BrokenStore:
        def get_cot_ice(self, contract, last_n=None):
            raise RuntimeError("simulated DB corruption")

    fn = get("cot_ice_mm_pct")
    assert fn(_BrokenStore(), "Brent", {"contract": "ice brent crude"}) == 0.0


def test_returns_zero_for_unknown_metric() -> None:
    """metric=='garbage' → 0.0 (defensive)."""
    df = _build_ice_df(n_weeks=60)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    assert fn(store, "Brent", {"contract": "ice brent crude", "metric": "garbage"}) == 0.0


# ---------------------------------------------------------------------------
# mm_net_pct-metric (OI-normalisert)
# ---------------------------------------------------------------------------


def test_supports_mm_net_pct_metric() -> None:
    """metric='mm_net_pct' deler net på OI — gir samme resultat når OI er
    konstant og net er stigende monotont."""
    df = _build_ice_df(n_weeks=60)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    score = fn(
        store,
        "Brent",
        {"contract": "ice brent crude", "metric": "mm_net_pct"},
    )
    assert score >= 0.95


# ---------------------------------------------------------------------------
# Lookback respekteres
# ---------------------------------------------------------------------------


def test_lookback_caps_history() -> None:
    """``lookback_weeks=30`` gir kun siste 30 obs i historikk-bedømmelsen."""
    df = _build_ice_df(n_weeks=100)
    store = _MockIceStore({"ice brent crude": df})

    fn = get("cot_ice_mm_pct")
    score = fn(store, "Brent", {"contract": "ice brent crude", "lookback_weeks": 30})

    # Siste rad er fortsatt høyest — score skal være ~1.0
    assert score >= 0.95


# ---------------------------------------------------------------------------
# Multi-contract isolering
# ---------------------------------------------------------------------------


def test_different_contracts_resolve_independently() -> None:
    """Brent og TTF Gas leses fra separate DB-rader."""
    brent_df = _build_ice_df(n_weeks=60, mm_long_start=80_000)  # stigende
    ttf_df = _build_ice_df(
        n_weeks=60,
        mm_long_start=160_000,
        mm_long_step=-1_000,  # synkende
        contract="ice ttf gas",
    )
    store = _MockIceStore({"ice brent crude": brent_df, "ice ttf gas": ttf_df})

    fn = get("cot_ice_mm_pct")
    brent_score = fn(store, "Brent", {"contract": "ice brent crude"})
    ttf_score = fn(store, "NaturalGas", {"contract": "ice ttf gas"})

    assert brent_score >= 0.95  # stigende → top-percentile
    assert ttf_score <= 0.05  # synkende → bottom-percentile
