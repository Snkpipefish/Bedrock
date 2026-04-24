"""Logiske tester for `bedrock.orchestrator.score_instrument`.

Integrasjonstest: YAML-lasting + Engine henger sammen. Bruker minimal
in-memory store + en ekte driver (sma200_align) slik at vi kjører full
stack uten å mocke Engine.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pandas as pd
import pytest

from bedrock.data.store import DataStore
from bedrock.engine.engine import AgriRules, FinancialRules

# Importeres som side-effekt: registrerer sma200_align og momentum_z
import bedrock.engine.drivers  # noqa: F401
from bedrock.orchestrator import score_instrument
from bedrock.orchestrator.score import OrchestratorError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store_with_prices(tmp_path: Path) -> DataStore:
    """DataStore med 250 daglige barer for 'Gold' over SMA200."""
    store = DataStore(tmp_path / "bedrock.db")
    ts = pd.date_range("2020-01-01", periods=250, freq="D")
    # Monotont stigende pris → close klart over SMA200
    close = pd.Series(range(100, 350), dtype=float).values
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": [1000.0] * 250,
        }
    )
    store.append_prices("Gold", "D1", df)
    store.append_prices("Corn", "D1", df)
    return store


@pytest.fixture
def minimal_defaults(tmp_path: Path) -> Path:
    """Minimale defaults slik at `inherits: family_financial/family_agri`
    kan brukes i instrument-YAML."""
    d = tmp_path / "defaults"
    d.mkdir()
    (d / "family_financial.yaml").write_text(
        dedent(
            """\
            aggregation: weighted_horizon
            horizons:
              SWING:
                family_weights: {trend: 1.0}
                max_score: 5.0
                min_score_publish: 2.0
            families:
              trend:
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.75, min_families: 1}
              A:      {min_pct_of_max: 0.55, min_families: 1}
              B:      {min_pct_of_max: 0.35, min_families: 1}
            """
        )
    )
    (d / "family_agri.yaml").write_text(
        dedent(
            """\
            aggregation: additive_sum
            max_score: 10
            min_score_publish: 4
            families:
              outlook:
                weight: 5
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_score: 8, min_families_active: 1}
              A:      {min_score: 6, min_families_active: 1}
              B:      {min_score: 4, min_families_active: 1}
            """
        )
    )
    return d


@pytest.fixture
def instruments_dir(tmp_path: Path) -> Path:
    d = tmp_path / "instruments"
    d.mkdir()
    return d


def _write_financial_yaml(dir_: Path, inst_id: str = "Gold") -> None:
    (dir_ / f"{inst_id.lower()}.yaml").write_text(
        dedent(
            f"""\
            inherits: family_financial
            instrument:
              id: {inst_id}
              asset_class: metals
              ticker: XAUUSD
            """
        )
    )


def _write_agri_yaml(dir_: Path, inst_id: str = "Corn") -> None:
    (dir_ / f"{inst_id.lower()}.yaml").write_text(
        dedent(
            f"""\
            inherits: family_agri
            instrument:
              id: {inst_id}
              asset_class: grains
              ticker: ZC
            """
        )
    )


# ---------------------------------------------------------------------------
# Financial (weighted_horizon)
# ---------------------------------------------------------------------------


def test_score_financial_instrument_end_to_end(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    _write_financial_yaml(instruments_dir)
    result = score_instrument(
        "Gold",
        store_with_prices,
        horizon="SWING",
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert result.instrument == "Gold"
    assert result.horizon == "SWING"
    assert result.aggregation == "weighted_horizon"
    assert result.score > 0
    assert "trend" in result.families
    assert result.grade in {"A_plus", "A", "B", "C"}


def test_score_financial_case_insensitive_id(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    """Caller kan bruke lowercase, men GroupResult.instrument er kanonisk
    fra YAML."""
    _write_financial_yaml(instruments_dir, inst_id="Gold")
    result = score_instrument(
        "gold",  # lowercase
        store_with_prices,
        horizon="SWING",
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert result.instrument == "Gold"


def test_score_financial_missing_horizon_errors(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    _write_financial_yaml(instruments_dir)
    with pytest.raises(OrchestratorError, match="horizon argument is required"):
        score_instrument(
            "Gold",
            store_with_prices,
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )


def test_score_financial_unknown_horizon_errors(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    _write_financial_yaml(instruments_dir)
    with pytest.raises(OrchestratorError, match="not defined"):
        score_instrument(
            "Gold",
            store_with_prices,
            horizon="SCALP",
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )


# ---------------------------------------------------------------------------
# Agri (additive_sum)
# ---------------------------------------------------------------------------


def test_score_agri_instrument_end_to_end(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    _write_agri_yaml(instruments_dir)
    result = score_instrument(
        "Corn",
        store_with_prices,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert result.instrument == "Corn"
    assert result.horizon is None  # agri har ingen horisont på scoring-siden
    assert result.aggregation == "additive_sum"
    assert result.score > 0
    assert "outlook" in result.families


def test_score_agri_with_horizon_arg_errors(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    _write_agri_yaml(instruments_dir)
    with pytest.raises(OrchestratorError, match="horizon argument must be None"):
        score_instrument(
            "Corn",
            store_with_prices,
            horizon="SWING",
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )


# ---------------------------------------------------------------------------
# Feil-scenarioer
# ---------------------------------------------------------------------------


def test_score_missing_instrument_file(
    store_with_prices: DataStore, minimal_defaults: Path, instruments_dir: Path
) -> None:
    # Ingen YAML skrevet
    with pytest.raises(OrchestratorError, match="no YAML"):
        score_instrument(
            "Platinum",
            store_with_prices,
            horizon="SWING",
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )


def test_score_missing_instruments_dir(
    store_with_prices: DataStore, tmp_path: Path
) -> None:
    with pytest.raises(OrchestratorError, match="not found"):
        score_instrument(
            "Gold",
            store_with_prices,
            horizon="SWING",
            instruments_dir=tmp_path / "nope",
        )
