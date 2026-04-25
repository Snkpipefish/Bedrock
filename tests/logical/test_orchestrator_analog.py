"""Logiske tester for analog-trace i SignalEntry (Fase 10 ADR-005, session 61).

Verifiserer at orchestrator.signals.AnalogTrace bygges korrekt fra K-NN-
output, og at SignalEntry får analog-felt populert når instrumentet har
en `analog`-familie i YAML.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.config.instruments import load_instrument_config
from bedrock.data.store import DataStore
from bedrock.orchestrator.signals import (
    AnalogNeighbor,
    AnalogTrace,
    SignalEntry,
    _build_analog_trace,
    generate_signals,
)

# ---------------------------------------------------------------------
# Pydantic-modeller
# ---------------------------------------------------------------------


def test_analog_neighbor_minimal() -> None:
    n = AnalogNeighbor(
        ref_date="2020-01-15",
        similarity=0.95,
        forward_return_pct=2.5,
    )
    assert n.max_drawdown_pct is None


def test_analog_trace_minimal() -> None:
    t = AnalogTrace(
        asset_class="metals",
        horizon_days=30,
        outcome_threshold_pct=3.0,
        n_neighbors=0,
        hit_rate_pct=0.0,
        avg_return_pct=0.0,
    )
    assert t.dims_used == []
    assert t.neighbors == []
    assert t.avg_drawdown_pct is None


def test_analog_trace_full_roundtrip() -> None:
    t = AnalogTrace(
        asset_class="grains",
        horizon_days=90,
        outcome_threshold_pct=5.0,
        n_neighbors=3,
        hit_rate_pct=66.7,
        avg_return_pct=4.2,
        avg_drawdown_pct=-3.1,
        dims_used=["dxy_chg5d", "enso_regime"],
        neighbors=[
            AnalogNeighbor(
                ref_date="2018-06-01",
                similarity=0.88,
                forward_return_pct=8.0,
                max_drawdown_pct=-2.5,
            ),
        ],
    )
    j = t.model_dump_json()
    reconstructed = AnalogTrace.model_validate_json(j)
    assert reconstructed == t


def test_signal_entry_default_analog_is_none() -> None:
    """Bakoverkompatibilitet: eldre kode som lager SignalEntry uten
    `analog` skal fortsatt funke (defaultes til None)."""
    from bedrock.setups.generator import Direction, Horizon

    e = SignalEntry(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        score=2.0,
        grade="A",
        max_score=5.0,
        min_score_publish=1.5,
        published=True,
    )
    assert e.analog is None


# ---------------------------------------------------------------------
# _build_analog_trace
# ---------------------------------------------------------------------


@pytest.fixture
def gold_yaml(tmp_path: Path) -> Path:
    """Skriv en minimal Gold-YAML med analog-familie + base-yaml til defaults."""
    inst_dir = tmp_path / "instruments"
    inst_dir.mkdir()
    (inst_dir / "gold.yaml").write_text(
        """\
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  cot_contract: "GOLD - COMMODITY EXCHANGE INC."
  cot_report: disaggregated
aggregation: weighted_horizon
horizons:
  SCALP:
    family_weights: {trend: 1.0, analog: 0.5}
    max_score: 1.5
    min_score_publish: 0.5
families:
  trend:
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
  analog:
    drivers:
      - name: analog_hit_rate
        weight: 1.0
        params:
          asset_class: metals
          k: 5
          horizon_days: 30
          outcome_threshold_pct: 3.0
          min_history_days: 0
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A: {min_pct_of_max: 0.55, min_families: 1}
  B: {min_pct_of_max: 0.35, min_families: 1}
""",
        encoding="utf-8",
    )
    return inst_dir


@pytest.fixture
def seeded_store_for_analog(tmp_path: Path) -> DataStore:
    """Seed nok data til at K-NN gir 5 naboer for Gold metals."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 600
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DTWEXBGS"] * n,
                "date": dates,
                "value": [100.0 + i * 0.05 for i in range(n)],
            }
        )
    )
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                "forward_return_pct": [5.0 if i % 3 == 0 else -1.0 for i in range(n)],
                "max_drawdown_pct": [-2.0] * n,
            }
        )
    )
    return store


def test_build_analog_trace_populates_fields(
    gold_yaml: Path, seeded_store_for_analog: DataStore
) -> None:
    cfg = load_instrument_config(gold_yaml / "gold.yaml")
    trace = _build_analog_trace(cfg, seeded_store_for_analog)
    assert trace is not None
    assert trace.asset_class == "metals"
    assert trace.horizon_days == 30
    assert trace.outcome_threshold_pct == 3.0
    assert trace.n_neighbors == 5
    assert len(trace.neighbors) == 5
    assert trace.dims_used == ["dxy_chg5d"]  # eneste extractor med data
    # hit-rate: ~33% av seedede outcomes har 5% (over 3% terskel)
    assert 0 <= trace.hit_rate_pct <= 100
    # Hver nabo skal ha ref_date som 'YYYY-MM-DD'-string
    for n in trace.neighbors:
        assert len(n.ref_date) == 10
        assert n.ref_date[4] == "-" and n.ref_date[7] == "-"


def test_build_analog_trace_no_analog_family_returns_none(tmp_path: Path) -> None:
    """Hvis instrumentet ikke har analog-familie i YAML → None."""
    inst_dir = tmp_path / "instruments"
    inst_dir.mkdir()
    (inst_dir / "x.yaml").write_text(
        """\
instrument:
  id: X
  asset_class: metals
  ticker: X
aggregation: weighted_horizon
horizons:
  SCALP:
    family_weights: {trend: 1.0}
    max_score: 1.0
    min_score_publish: 0.5
families:
  trend:
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A: {min_pct_of_max: 0.55, min_families: 1}
  B: {min_pct_of_max: 0.35, min_families: 1}
""",
        encoding="utf-8",
    )
    cfg = load_instrument_config(inst_dir / "x.yaml")
    store = DataStore(tmp_path / "x.db")
    trace = _build_analog_trace(cfg, store)
    assert trace is None


def test_build_analog_trace_no_data_returns_none(gold_yaml: Path, tmp_path: Path) -> None:
    """Hvis K-NN ikke kan kjøre (tom store) → None."""
    cfg = load_instrument_config(gold_yaml / "gold.yaml")
    empty_store = DataStore(tmp_path / "empty.db")
    trace = _build_analog_trace(cfg, empty_store)
    assert trace is None


def test_build_analog_trace_unknown_asset_class_returns_none(tmp_path: Path) -> None:
    """Hvis YAML har asset_class utenfor § 6.5 → None (defensive)."""
    inst_dir = tmp_path / "instruments"
    inst_dir.mkdir()
    (inst_dir / "x.yaml").write_text(
        """\
instrument:
  id: X
  asset_class: cryptos
  ticker: X
aggregation: weighted_horizon
horizons:
  SCALP:
    family_weights: {analog: 1.0}
    max_score: 1.0
    min_score_publish: 0.5
families:
  analog:
    drivers:
      - name: analog_hit_rate
        weight: 1.0
        params: {asset_class: cryptos}
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A: {min_pct_of_max: 0.55, min_families: 1}
  B: {min_pct_of_max: 0.35, min_families: 1}
""",
        encoding="utf-8",
    )
    cfg = load_instrument_config(inst_dir / "x.yaml")
    store = DataStore(tmp_path / "x.db")
    trace = _build_analog_trace(cfg, store)
    assert trace is None


# ---------------------------------------------------------------------
# generate_signals end-to-end (med analog populert)
# ---------------------------------------------------------------------


def test_generate_signals_includes_analog_in_entries(
    gold_yaml: Path, seeded_store_for_analog: DataStore, tmp_path: Path
) -> None:
    """Full pipeline: orchestrator skal populere analog på SignalEntry
    når YAML har analog-familie."""
    # Seed prises slik at orchestrator kan bygge OHLC + setup
    n = 300
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    seeded_store_for_analog.append_prices(
        "Gold",
        "D1",
        pd.DataFrame(
            {
                "ts": dates,
                "open": [1800.0 + i for i in range(n)],
                "high": [1810.0 + i for i in range(n)],
                "low": [1790.0 + i for i in range(n)],
                "close": [1800.0 + i for i in range(n)],
                "volume": [1000] * n,
            }
        ),
    )
    result = generate_signals(
        "Gold",
        seeded_store_for_analog,
        instruments_dir=gold_yaml,
        write_snapshot=False,
    )
    assert len(result.entries) > 0
    # Minst én entry skal ha analog satt (samme analog for alle direction
    # × horizon-kombinasjoner siden K-NN er instrument-bredt)
    with_analog = [e for e in result.entries if e.analog is not None]
    assert len(with_analog) >= 1
    a = with_analog[0].analog
    assert a is not None
    assert a.asset_class == "metals"
    assert a.n_neighbors == 5


def test_signal_entry_analog_serializes_to_json(
    gold_yaml: Path, seeded_store_for_analog: DataStore, tmp_path: Path
) -> None:
    """JSON-roundtrip: analog-felt persisterer riktig (UI-konsumeres)."""
    cfg = load_instrument_config(gold_yaml / "gold.yaml")
    trace = _build_analog_trace(cfg, seeded_store_for_analog)
    assert trace is not None
    j = trace.model_dump_json()
    # Sanity: JSON inneholder forventede toppnivå-felter
    assert '"asset_class":"metals"' in j
    assert '"horizon_days":30' in j
    assert '"neighbors":[' in j
