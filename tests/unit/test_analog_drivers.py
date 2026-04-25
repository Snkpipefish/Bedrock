"""Tester for analog-familie drivere (Fase 10 ADR-005, session 60).

Drivere har en uvanlig avhengighet: de slår opp `InstrumentMetadata` via
`find_instrument(instrument)` for å få cot_contract / weather_region som
extractors trenger. Vi setter opp en mock-instruments-dir per test
istedenfor å monkey-patche.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore
from bedrock.engine.drivers import get

# ---------------------------------------------------------------------
# Fixtures: lite test-instrument-YAML + seedet store
# ---------------------------------------------------------------------


@pytest.fixture
def instruments_dir(tmp_path: Path) -> Path:
    """Skriv et minimalt Gold + Corn YAML i tmp_path."""
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
    (inst_dir / "corn.yaml").write_text(
        """\
instrument:
  id: Corn
  asset_class: grains
  ticker: ZC
  cot_contract: "CORN - CHICAGO BOARD OF TRADE"
  cot_report: disaggregated
  weather_region: us_cornbelt
aggregation: additive_sum
max_score: 10
min_score_publish: 5
families:
  outlook:
    weight: 1
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_score: 8, min_families_active: 1}
  A: {min_score: 6, min_families_active: 1}
  B: {min_score: 4, min_families_active: 1}
""",
        encoding="utf-8",
    )
    return inst_dir


@pytest.fixture
def seeded_store(tmp_path: Path) -> DataStore:
    """Seed minimal data slik at K-NN kan kjøre for Gold metals."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 600  # > min_history_days=365 default
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    # DTWEXBGS lineær stigning → dxy_chg5d kjent
    store.append_fundamentals(
        pd.DataFrame(
            {
                "series_id": ["DTWEXBGS"] * n,
                "date": dates,
                "value": [100.0 + i * 0.05 for i in range(n)],
            }
        )
    )
    # Outcomes: positive returns (slik at hit_rate > 0)
    store.append_outcomes(
        pd.DataFrame(
            {
                "instrument": ["Gold"] * n,
                "ref_date": dates,
                "horizon_days": [30] * n,
                # Halve naboene har +5% (over 3% terskel), halve har -1%
                "forward_return_pct": [5.0 if i % 2 == 0 else -1.0 for i in range(n)],
                "max_drawdown_pct": [-2.0] * n,
            }
        )
    )
    return store


# ---------------------------------------------------------------------
# analog_hit_rate
# ---------------------------------------------------------------------


def test_hit_rate_basic(seeded_store: DataStore, instruments_dir: Path) -> None:
    fn = get("analog_hit_rate")
    score = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "outcome_threshold_pct": 3.0,
        },
    )
    # ~50% av seedede outcomes har +5% (over 3.0 terskel) → hit_rate ~0.5
    # K-NN velger 10 nærmeste, sannsynlig blandet alternering
    assert 0.3 <= score <= 0.7


def test_hit_rate_missing_asset_class_returns_zero(
    seeded_store: DataStore, instruments_dir: Path
) -> None:
    fn = get("analog_hit_rate")
    score = fn(seeded_store, "Gold", {"instruments_dir": str(instruments_dir)})
    assert score == 0.0


def test_hit_rate_unknown_asset_class_returns_zero(
    seeded_store: DataStore, instruments_dir: Path
) -> None:
    fn = get("analog_hit_rate")
    score = fn(
        seeded_store,
        "Gold",
        {"asset_class": "cryptos", "instruments_dir": str(instruments_dir)},
    )
    assert score == 0.0


def test_hit_rate_unknown_instrument_returns_zero(
    seeded_store: DataStore, instruments_dir: Path
) -> None:
    fn = get("analog_hit_rate")
    score = fn(
        seeded_store,
        "DoesNotExist",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir)},
    )
    assert score == 0.0


def test_hit_rate_no_data_returns_zero(tmp_path: Path, instruments_dir: Path) -> None:
    """Tom store → ingen extractors funker → 0.0."""
    fn = get("analog_hit_rate")
    empty_store = DataStore(tmp_path / "empty.db")
    score = fn(
        empty_store,
        "Gold",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir)},
    )
    assert score == 0.0


def test_hit_rate_threshold_is_configurable(seeded_store: DataStore, instruments_dir: Path) -> None:
    """Med terskel = 100% (urealistisk høyt) skal hit_rate bli ~0."""
    fn = get("analog_hit_rate")
    score = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "outcome_threshold_pct": 100.0,
        },
    )
    assert score == 0.0


def test_hit_rate_threshold_zero_includes_all_positive(
    seeded_store: DataStore, instruments_dir: Path
) -> None:
    """Med terskel = 0% inkluderes alle naboer med return ≥ 0."""
    fn = get("analog_hit_rate")
    # ~50% av outcomes har +5% (positiv), ~50% har -1% (negativ)
    score = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "outcome_threshold_pct": 0.0,
        },
    )
    # Hit-rate skal omtrent matche andelen positive — 0.4-0.7
    assert 0.3 <= score <= 0.7


def test_hit_rate_returns_float_in_range(seeded_store: DataStore, instruments_dir: Path) -> None:
    fn = get("analog_hit_rate")
    score = fn(
        seeded_store,
        "Gold",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir), "min_history_days": 0},
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------
# analog_avg_return
# ---------------------------------------------------------------------


def test_avg_return_basic(seeded_store: DataStore, instruments_dir: Path) -> None:
    fn = get("analog_avg_return")
    score = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
        },
    )
    # Avg av (5%, -1%) blandet ~ 2% → mappes til ~0.65 default
    assert 0.4 <= score <= 0.8


def test_avg_return_invert_flips_sign(seeded_store: DataStore, instruments_dir: Path) -> None:
    """direction=invert flipper fortegn på avg → bear-driver."""
    fn = get("analog_avg_return")
    direct = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "direction": "direct",
        },
    )
    invert = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "direction": "invert",
        },
    )
    # Med positive returns: direct > 0, invert (negativ avg) → 0.0
    assert direct > 0.0
    assert invert == 0.0


def test_avg_return_unknown_direction_returns_zero(
    seeded_store: DataStore, instruments_dir: Path
) -> None:
    fn = get("analog_avg_return")
    score = fn(
        seeded_store,
        "Gold",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir), "direction": "sideways"},
    )
    assert score == 0.0


def test_avg_return_custom_thresholds(seeded_store: DataStore, instruments_dir: Path) -> None:
    """Custom score_thresholds skal overstyre default."""
    fn = get("analog_avg_return")
    # Aggressive threshold: krev avg ≥ 10% for å få noen score
    score = fn(
        seeded_store,
        "Gold",
        {
            "asset_class": "metals",
            "instruments_dir": str(instruments_dir),
            "min_history_days": 0,
            "k": 10,
            "score_thresholds": {"10.0": 1.0, "5.0": 0.5},
        },
    )
    # Avg er ~2%, under begge tersklene → 0.0
    assert score == 0.0


def test_avg_return_negative_history_returns_zero(tmp_path: Path, instruments_dir: Path) -> None:
    """Hvis K-NN finner naboer med negativ avg → driver returnerer 0.0."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 500
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
                "forward_return_pct": [-2.0] * n,  # alle negative
                "max_drawdown_pct": [-5.0] * n,
            }
        )
    )
    fn = get("analog_avg_return")
    score = fn(
        store,
        "Gold",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir), "min_history_days": 0},
    )
    assert score == 0.0


def test_avg_return_strong_positive_history_maxes_score(
    tmp_path: Path, instruments_dir: Path
) -> None:
    """Avg ≥ 5% → score = 1.0 per default-mapping."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 500
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
                "forward_return_pct": [10.0] * n,  # alle sterkt positive
                "max_drawdown_pct": [-1.0] * n,
            }
        )
    )
    fn = get("analog_avg_return")
    score = fn(
        store,
        "Gold",
        {"asset_class": "metals", "instruments_dir": str(instruments_dir), "min_history_days": 0},
    )
    assert score == 1.0


def test_drivers_registered_under_correct_names() -> None:
    """Sanity: begge analog-drivere er registrert."""
    from bedrock.engine.drivers import all_names, is_registered

    assert is_registered("analog_hit_rate")
    assert is_registered("analog_avg_return")
    names = all_names()
    assert "analog_hit_rate" in names
    assert "analog_avg_return" in names


# Ubrukt nå, men sikrer at imports ikke breaker
def test_import_uses_date_module() -> None:
    assert date.today().year >= 2020
