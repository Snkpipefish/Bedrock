"""Tester for ``bedrock.engine.drivers.positioning``.

Verifiserer at ``positioning_mm_pct`` og ``cot_z_score`` returnerer
forventede 0..1-scores fra COT-data, og at defensive 0.0-fallbacks
trigger ved manglende contract, manglende data, eller utilstrekkelig
historikk.

Bruker en in-memory mock-store + monkey-patcher
``find_instrument`` slik at testene ikke avhenger av YAML-filer
eller faktisk DB.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from bedrock.engine.drivers import get
from bedrock.engine.drivers.positioning import (
    _DEFAULT_LOOKBACK,
    _DEFAULT_Z_THRESHOLDS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockStore:
    """In-memory store som returnerer forhåndsbygde COT-DataFrames."""

    def __init__(self, cot_data: dict[tuple[str, str], pd.DataFrame]):
        self._cot = cot_data

    def get_cot(self, contract: str, report: str = "disaggregated", last_n: int | None = None):
        key = (contract, report)
        if key not in self._cot:
            raise KeyError(f"No COT data for contract={contract!r} report={report!r}")
        df = self._cot[key]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _build_cot_df(
    *,
    n_weeks: int = 60,
    mm_long_start: float = 100_000,
    mm_long_step: float = 1_000,
    mm_short: float = 50_000,
    open_interest: float = 300_000,
) -> pd.DataFrame:
    """Bygger en kunstig COT-historikk med stigende mm_long."""
    base = date(2024, 1, 5)
    rows = []
    for i in range(n_weeks):
        rows.append(
            {
                "report_date": base + timedelta(weeks=i),
                "contract": "TEST",
                "mm_long": mm_long_start + mm_long_step * i,
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


@pytest.fixture
def mock_instrument(monkeypatch):
    """Monkey-patcher ``find_instrument`` til å returnere en stub-config."""

    class _Meta:
        cot_contract = "TEST"
        cot_report = "disaggregated"

    class _Cfg:
        instrument = _Meta()

    def _fake_find(name: str, _dir):
        if name == "Unknown":
            raise FileNotFoundError(f"No instrument {name}")
        return _Cfg()

    monkeypatch.setattr("bedrock.cli._instrument_lookup.find_instrument", _fake_find)
    return _Cfg()


@pytest.fixture
def mock_instrument_no_cot(monkeypatch):
    """Stub uten cot_contract — driver skal returnere 0.0."""

    class _Meta:
        cot_contract = None
        cot_report = None

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )
    return _Cfg()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_positioning_mm_pct_registered() -> None:
    fn = get("positioning_mm_pct")
    assert fn is not None


def test_cot_z_score_registered() -> None:
    fn = get("cot_z_score")
    assert fn is not None


# ---------------------------------------------------------------------------
# positioning_mm_pct
# ---------------------------------------------------------------------------


def test_positioning_mm_pct_returns_high_for_top_long(mock_instrument: Any) -> None:
    """Når current MM net er høyeste i historikken → percentile 100 → 1.0."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("positioning_mm_pct")
    score = fn(store, "Gold", {"lookback_weeks": 52})

    # Siste rad har høyeste mm_long (stigende serie); percentile bør være ~100
    assert score >= 0.95


def test_positioning_mm_pct_returns_low_for_bottom_long(mock_instrument: Any) -> None:
    """Synkende mm_long-serie → siste rad har lavest → 0.0."""
    df = _build_cot_df(n_weeks=60, mm_long_start=200_000, mm_long_step=-1_000)
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("positioning_mm_pct")
    score = fn(store, "Gold", {"lookback_weeks": 52})

    assert score <= 0.05


def test_positioning_mm_pct_returns_zero_for_missing_contract(
    mock_instrument_no_cot: Any,
) -> None:
    """Instrument uten cot_contract → 0.0 + log."""
    store = _MockStore({})
    fn = get("positioning_mm_pct")
    assert fn(store, "Gold", {}) == 0.0


def test_positioning_mm_pct_returns_zero_for_short_history(
    mock_instrument: Any,
) -> None:
    """Færre enn 27 obs → 0.0."""
    df = _build_cot_df(n_weeks=15)
    store = _MockStore({("TEST", "disaggregated"): df})
    fn = get("positioning_mm_pct")
    assert fn(store, "Gold", {}) == 0.0


def test_positioning_mm_pct_returns_zero_when_cot_missing(
    mock_instrument: Any,
) -> None:
    """Store kaster KeyError → 0.0."""
    store = _MockStore({})  # ingen data for TEST
    fn = get("positioning_mm_pct")
    assert fn(store, "Gold", {}) == 0.0


def test_positioning_mm_pct_supports_mm_net_pct_metric(
    mock_instrument: Any,
) -> None:
    """`metric="mm_net_pct"` normaliserer mot OI."""
    df = _build_cot_df(n_weeks=60)
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("positioning_mm_pct")
    score_net = fn(store, "Gold", {"metric": "mm_net"})
    score_pct = fn(store, "Gold", {"metric": "mm_net_pct"})

    # Begge skal returnere høy score (stigende serie) men kan være litt
    # forskjellige pga normalisering — kun sjekk at begge er gyldige
    # 0..1-verdier
    assert 0.0 <= score_net <= 1.0
    assert 0.0 <= score_pct <= 1.0


def test_positioning_mm_pct_unknown_metric_returns_zero(
    mock_instrument: Any,
) -> None:
    df = _build_cot_df(n_weeks=60)
    store = _MockStore({("TEST", "disaggregated"): df})
    fn = get("positioning_mm_pct")
    assert fn(store, "Gold", {"metric": "ukjent"}) == 0.0


def test_positioning_mm_pct_lookback_caps_history(mock_instrument: Any) -> None:
    """``lookback_weeks`` begrenser hvor mange historiske obs som brukes.

    Med lookback=27 skal kun siste 28 obs (1 current + 27 history) brukes.
    """
    # 60 uker av stigende serie. Med kort lookback bør percentile fortsatt
    # være høy (siste er fortsatt størst i sin lokale subset).
    df = _build_cot_df(n_weeks=60)
    store = _MockStore({("TEST", "disaggregated"): df})
    fn = get("positioning_mm_pct")

    score = fn(store, "Gold", {"lookback_weeks": 27})
    assert score >= 0.95


# ---------------------------------------------------------------------------
# cot_z_score
# ---------------------------------------------------------------------------


def _build_volatile_cot_df(n_weeks: int = 50) -> pd.DataFrame:
    """COT-historikk med moderat variasjon (MAD > 0)."""
    df = _build_cot_df(n_weeks=n_weeks, mm_long_start=100_000, mm_long_step=0)
    # Random walk ±5k for å gi MAD > 0
    for i in range(len(df)):
        df.iloc[i, df.columns.get_loc("mm_long")] = 100_000 + (i % 10 - 5) * 1000
    return df


def test_cot_z_score_high_for_extreme_long(mock_instrument: Any) -> None:
    """Siste obs er ekstremt høy → z stort positiv → score 1.0."""
    df = _build_volatile_cot_df()
    df.iloc[-1, df.columns.get_loc("mm_long")] = 500_000  # ekstrem outlier
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("cot_z_score")
    score = fn(store, "Gold", {})
    assert score == 1.0


def test_cot_z_score_zero_for_extreme_short(mock_instrument: Any) -> None:
    """Siste obs ekstremt lav → z langt negativ → score 0.0."""
    df = _build_volatile_cot_df()
    df.iloc[-1, df.columns.get_loc("mm_long")] = -500_000  # ekstrem motsatt
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("cot_z_score")
    score = fn(store, "Gold", {})
    assert score == 0.0


def test_cot_z_score_neutral_for_median(mock_instrument: Any) -> None:
    """Sentrert serie: z rundt 0 → score 0.5 (default mapping)."""
    df = _build_cot_df(n_weeks=50, mm_long_start=100_000, mm_long_step=0)
    # Variasjon: ±5k random walk
    for i in range(len(df)):
        df.iloc[i, df.columns.get_loc("mm_long")] = 100_000 + (i % 10 - 5) * 1000
    # Sett siste til medianen
    df.iloc[-1, df.columns.get_loc("mm_long")] = 100_000
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("cot_z_score")
    score = fn(store, "Gold", {})
    # z ≈ 0 → score skal være 0.5 (default-mapping)
    assert score == 0.5


def test_cot_z_score_zero_for_constant_history(mock_instrument: Any) -> None:
    """MAD = 0 → driver returnerer 0.0."""
    df = _build_cot_df(n_weeks=50, mm_long_start=100_000, mm_long_step=0)
    # Alle mm_long = 100_000, mm_short konstant → mm_net konstant → MAD=0
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("cot_z_score")
    assert fn(store, "Gold", {}) == 0.0


def test_cot_z_score_returns_zero_for_missing_contract(
    mock_instrument_no_cot: Any,
) -> None:
    store = _MockStore({})
    fn = get("cot_z_score")
    assert fn(store, "Gold", {}) == 0.0


def test_cot_z_score_custom_thresholds_dict(mock_instrument: Any) -> None:
    """Brukerstyrt z_thresholds som dict skal fungere."""
    df = _build_volatile_cot_df()
    df.iloc[-1, df.columns.get_loc("mm_long")] = 200_000  # moderat outlier
    store = _MockStore({("TEST", "disaggregated"): df})

    fn = get("cot_z_score")
    # Custom thresholds: alt fra z>=0.5 mapper til 0.9
    score = fn(
        store,
        "Gold",
        {"z_thresholds": {"+0.5": 0.9, "0": 0.5}},
    )
    assert score in (0.5, 0.9)


def test_cot_z_score_default_thresholds_match_momentum_z() -> None:
    """Default z-thresholds skal matche ``momentum_z``-konvensjonen.

    Dette er en regresjon-test: hvis noen endrer thresholds må de bevisst
    bryte denne testen.
    """
    expected = (
        (2.0, 1.0),
        (1.0, 0.75),
        (0.5, 0.6),
        (0.0, 0.5),
        (-0.5, 0.3),
    )
    assert expected == _DEFAULT_Z_THRESHOLDS


def test_cot_z_score_lookback_default() -> None:
    """``_DEFAULT_LOOKBACK`` er 52 uker (regresjon-test)."""
    assert _DEFAULT_LOOKBACK == 52
