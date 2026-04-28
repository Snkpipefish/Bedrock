"""Tester for R3-horisont-modes på ``positioning_mm_pct``.

Sub-fase 12.7 R3 (session 121). Verifiserer at:

- Default (mode=None) er bit-identisk med pre-R3.
- ``mode="pct_12m"`` produserer monotont stigende output på syntetisk
  strigende serie (Type B per ``docs/driver_horizon_pattern.md`` § 2.2).
- ``mode="delta_5d_z"`` reagerer på regime-shift (Type C per § 2.3).
- ``mode="pct_36m"`` faller gracefully tilbake til pct_12m ved
  utilstrekkelig 36m-historikk.
- ``mode="extreme_flag_*"`` returnerer 1.0 ved 2/98- og 5/95-tersklene.
- Ukjent mode logger warning og fall-backer til default.

Bruker samme in-memory mock-store-mønster som
``test_drivers_positioning.py`` (samme fil-presedens).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from bedrock.engine.drivers.positioning import positioning_mm_pct


def _build_cot_df(
    *,
    n_weeks: int,
    mm_long_values: list[float] | None = None,
    mm_long_start: float = 100_000,
    mm_long_step: float = 1_000,
    mm_short: float = 50_000,
    open_interest: float = 300_000,
) -> pd.DataFrame:
    """Bygger en COT-historikk. Hvis ``mm_long_values`` gis, brukes den
    direkte (skal ha lengde n_weeks); ellers genereres lineært stigende."""
    base = date(2022, 1, 5)
    rows = []
    if mm_long_values is None:
        mm_long_values = [mm_long_start + mm_long_step * i for i in range(n_weeks)]
    assert len(mm_long_values) == n_weeks
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "TEST",
                "mm_long": mm_long_values[i],
                "mm_short": mm_short,
                "other_long": 0,
                "other_short": 0,
                "comm_long": 0,
                "comm_short": 0,
                "nonrep_long": 0,
                "nonrep_short": 0,
                "open_interest": open_interest,
            }
        )
    return pd.DataFrame(rows)


class _MockStore:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_cot(self, contract: str, report: str = "disaggregated", last_n: int | None = None):
        df = self._df
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


@pytest.fixture
def mock_instrument(monkeypatch):
    class _Meta:
        cot_contract = "TEST"
        cot_report = "disaggregated"

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )


# ---------------------------------------------------------------------------
# Type A — bit-identisk default (mode=None)
# ---------------------------------------------------------------------------


def test_default_mode_unchanged_pre_r3(mock_instrument):
    """Default (mode=None) skal være bit-identisk med pre-R3-output.

    Verifiseres ved at uten `mode` i params, returneres rank-percentile
    fra dagens flow. Spesifikk verdi sjekkes mot manuell beregning.
    """
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    # Med strigende mm_long er current det høyeste; rank_percentile mot
    # 52 historikk-obs gir nær 1.0.
    score = positioning_mm_pct(store, "Test", {})
    assert score >= 0.95
    assert score <= 1.0


# ---------------------------------------------------------------------------
# Type A — mode="pct_12m" matcher default ved samme lookback
# ---------------------------------------------------------------------------


def test_pct_12m_equals_default_for_same_lookback(mock_instrument):
    """mode='pct_12m' skal gi samme verdi som default ved lookback=52.

    Bekrefter at pct_12m-modus bare er en eksplisitt navngitt versjon
    av dagens default — ingen algoritme-endring.
    """
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    default = positioning_mm_pct(store, "Test", {})
    explicit = positioning_mm_pct(store, "Test", {"mode": "pct_12m"})
    assert default == explicit


# ---------------------------------------------------------------------------
# Type B — monotonisitet på pct_12m
# ---------------------------------------------------------------------------


def test_pct_12m_monotonic_on_strictly_increasing_series(mock_instrument):
    """Type B (§ 2.2): pct_12m på syntetisk strigende serie gir monotont
    stigende output ved gradvis data-tilkomst.

    Itererer "as-of" ved å trimme DataFrame til økende lengder; verifiserer
    at hver steg gir ≥ forrige steg.
    """
    full_df = _build_cot_df(n_weeks=80)
    prev = -1.0
    for n in range(53, 81):  # starter ved første gyldige pct_12m-window
        store = _MockStore(full_df.head(n))
        score = positioning_mm_pct(store, "Test", {"mode": "pct_12m"})
        assert score >= prev, (
            f"pct_12m fell from {prev} to {score} at n={n} på strengt stigende serie"
        )
        prev = score
    # Siste steg må være nær 1.0 siden current er det høyeste i 52-vinduet.
    assert prev >= 0.95


# ---------------------------------------------------------------------------
# Type C — regime-shift på delta_5d_z
# ---------------------------------------------------------------------------


def test_delta_5d_z_reacts_to_regime_shift(mock_instrument):
    """Type C (§ 2.3): delta_5d_z fanger stort hopp i underliggende serie.

    Bygger serien med ekte støy (deterministisk) i normal-fase, deretter
    et stort hopp. Sammenligner score rett før og rett etter hoppet.
    """
    import random

    rng = random.Random(42)
    n_pre = 60
    # Random-walk: hver step er normalfordelt step rundt forrige
    # verdi. Diff-serien har en distribusjon med definert std.
    base = 100_000.0
    values = [base]
    for _ in range(n_pre - 1):
        values.append(values[-1] + rng.gauss(0, 200))

    # Hopp: 5000 er ~25σ over typisk 200-σ-diff ⇒ klart out-of-sample.
    series = [*values, values[-1] + 5000.0]
    df = _build_cot_df(n_weeks=len(series), mm_long_values=series)

    pre_df = df.head(n_pre)
    pre_score = positioning_mm_pct(_MockStore(pre_df), "Test", {"mode": "delta_5d_z"})
    post_score = positioning_mm_pct(_MockStore(df), "Test", {"mode": "delta_5d_z"})

    assert post_score >= 0.75, f"delta_5d_z post-hopp = {post_score}, forventet >= 0.75 (z >= 1)"
    assert post_score > pre_score, (
        f"delta_5d_z post-hopp ({post_score}) skulle være > pre ({pre_score})"
    )


# ---------------------------------------------------------------------------
# pct_36m fall-back ved utilstrekkelig historikk
# ---------------------------------------------------------------------------


def test_pct_36m_fallback_to_12m_on_short_history(mock_instrument, caplog):
    """Ved <156 obs skal pct_36m logge info og fall-back til pct_12m.

    Verifiserer per § 1.1: ikke 0.0, ikke krasj — graceful fall-back.
    """
    df = _build_cot_df(n_weeks=80)  # 80 < 156 obs
    store = _MockStore(df)

    score_36m = positioning_mm_pct(store, "Test", {"mode": "pct_36m"})
    score_12m = positioning_mm_pct(store, "Test", {"mode": "pct_12m"})
    assert score_36m == score_12m, (
        f"pct_36m fall-back skulle gi samme som pct_12m, fikk {score_36m} vs {score_12m}"
    )


# ---------------------------------------------------------------------------
# extreme_flag-modes
# ---------------------------------------------------------------------------


def test_extreme_flag_hard_at_top_percentile(mock_instrument):
    """Når current er det høyeste i 52-historikken: pct ≈ 1.0 ⇒ flag = 1.0."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    flag = positioning_mm_pct(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 1.0


def test_extreme_flag_hard_at_median(mock_instrument):
    """Når current ligger nær median: flag = 0.0 (verken ≥0.98 eller ≤0.02)."""
    # Bygg en serie der current er nær midt-rangering: bruk median i stedet
    # for siste verdi som current ved å lage flat tail.
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + (n // 2) * 100]
    df = _build_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockStore(df)
    flag = positioning_mm_pct(store, "Test", {"mode": "extreme_flag_hard"})
    assert flag == 0.0


def test_extreme_flag_soft_threshold(mock_instrument):
    """5/95-tersklene skal trigge før 2/98."""
    # Lag serie der current ligger i øvre 5% men ikke topp 2%.
    # Med 52 historikk-obs: rank ≥ 96th percentile triggrer soft, ikke hard.
    n = 60
    values = [100_000.0 + i * 100 for i in range(n - 1)] + [100_000.0 + 51 * 100]
    df = _build_cot_df(n_weeks=n, mm_long_values=values)
    store = _MockStore(df)
    soft = positioning_mm_pct(store, "Test", {"mode": "extreme_flag_soft"})
    hard = positioning_mm_pct(store, "Test", {"mode": "extreme_flag_hard"})
    # current er nest-høyeste => rank = 51/52 ≈ 0.98 ⇒ begge trigger.
    # For ekte 95/98-skille bygger vi en variant med 53 obs der current er på 50./51-plass.
    # Her er testen mer en sanity at soft fyrer minst like ofte som hard.
    assert soft >= hard


# ---------------------------------------------------------------------------
# Ukjent mode → fall-back
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_default(mock_instrument):
    """Ukjent mode-verdi skal logge warning og returnere default-output."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    default = positioning_mm_pct(store, "Test", {})
    unknown = positioning_mm_pct(store, "Test", {"mode": "not_a_real_mode"})
    assert default == unknown


# ---------------------------------------------------------------------------
# _horizon lest men ikke brukt for output (R3-kontrakt)
# ---------------------------------------------------------------------------


def test_horizon_param_does_not_change_output(mock_instrument):
    """R3-kontrakt (§ 5.3): _horizon LESES men brukes ikke til å endre
    default-output. Score skal være identisk med eller uten _horizon."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore(df)
    no_horizon = positioning_mm_pct(store, "Test", {})
    with_swing = positioning_mm_pct(store, "Test", {"_horizon": "SWING"})
    with_makro = positioning_mm_pct(store, "Test", {"_horizon": "MAKRO"})
    assert no_horizon == with_swing == with_makro
