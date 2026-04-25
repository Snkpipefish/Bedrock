"""Tester for `bedrock instruments list/show` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_gold(dir_: Path) -> None:
    (dir_ / "gold.yaml").write_text(
        """\
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  stooq_ticker: xauusd
  cot_contract: "GOLD - COMMODITY EXCHANGE INC."
  cot_report: disaggregated
  fred_series_ids:
    - DGS10
    - DTWEXBGS

aggregation: weighted_horizon
horizons:
  SWING:
    family_weights:
      trend: 1.0
    max_score: 5.0
    min_score_publish: 2.5
families:
  trend:
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 4}
  A:      {min_pct_of_max: 0.55, min_families: 3}
  B:      {min_pct_of_max: 0.35, min_families: 2}
"""
    )


def _write_corn(dir_: Path) -> None:
    (dir_ / "corn.yaml").write_text(
        """\
instrument:
  id: Corn
  asset_class: grains
  ticker: ZC
  weather_region: us_cornbelt
  weather_lat: 40.75
  weather_lon: -96.75

aggregation: additive_sum
max_score: 18
min_score_publish: 7
families:
  outlook:
    weight: 5
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_score: 14, min_families_active: 4}
  A:      {min_score: 10, min_families_active: 3}
  B:      {min_score: 7,  min_families_active: 2}
"""
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_shows_all_instruments(runner: CliRunner, tmp_path: Path) -> None:
    _write_gold(tmp_path)
    _write_corn(tmp_path)

    result = runner.invoke(
        cli,
        ["instruments", "list", "--instruments-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Gold" in result.output
    assert "Corn" in result.output
    assert "metals" in result.output
    assert "grains" in result.output
    assert "us_cornbelt" in result.output
    assert "GOLD - COMMODITY EXCHANGE INC." in result.output


def test_list_empty_dir(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli,
        ["instruments", "list", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "ingen instrumenter" in result.output.lower()


def test_list_missing_dir(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = runner.invoke(
        cli,
        ["instruments", "list", "--instruments-dir", str(missing)],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_list_sorted_output(runner: CliRunner, tmp_path: Path) -> None:
    _write_corn(tmp_path)
    _write_gold(tmp_path)
    result = runner.invoke(
        cli,
        ["instruments", "list", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    # Gold < Corn (G < C? nei, C < G) — men sortering er alfabetisk
    corn_pos = result.output.index("Corn")
    gold_pos = result.output.index("Gold")
    assert corn_pos < gold_pos


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_financial_instrument(runner: CliRunner, tmp_path: Path) -> None:
    _write_gold(tmp_path)
    result = runner.invoke(
        cli,
        ["instruments", "show", "Gold", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Gold" in result.output
    assert "metals" in result.output
    assert "XAUUSD" in result.output
    assert "DGS10" in result.output
    assert "weighted_horizon" in result.output
    assert "SWING" in result.output


def test_show_agri_instrument(runner: CliRunner, tmp_path: Path) -> None:
    _write_corn(tmp_path)
    result = runner.invoke(
        cli,
        ["instruments", "show", "Corn", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Corn" in result.output
    assert "additive_sum" in result.output
    assert "max_score" in result.output.lower() or "max_score: 18" in result.output
    assert "outlook" in result.output
    assert "us_cornbelt" in result.output


def test_show_case_insensitive(runner: CliRunner, tmp_path: Path) -> None:
    _write_gold(tmp_path)
    result = runner.invoke(
        cli,
        ["instruments", "show", "gold", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Gold" in result.output


def test_show_unknown_instrument_errors(runner: CliRunner, tmp_path: Path) -> None:
    _write_gold(tmp_path)
    result = runner.invoke(
        cli,
        ["instruments", "show", "Platinum", "--instruments-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "Ukjent instrument" in result.output or "Platinum" in result.output


def test_show_missing_dir_errors(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = runner.invoke(
        cli,
        ["instruments", "show", "Gold", "--instruments-dir", str(missing)],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_instruments_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["instruments", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "show" in result.output


# ---------------------------------------------------------------------------
# inherits — CLI-integrasjon (session 23)
# ---------------------------------------------------------------------------


def test_show_resolves_inherits_from_defaults_dir(runner: CliRunner, tmp_path: Path) -> None:
    """`bedrock instruments show` skal rulle opp `inherits:` slik at
    et slankt instrument-YAML viser de arvede familiene/horisontene."""
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "family_financial.yaml").write_text(
        """\
aggregation: weighted_horizon
horizons:
  SWING:
    family_weights: {trend: 1.0}
    max_score: 5.0
    min_score_publish: 2.5
families:
  trend:
    drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A:      {min_pct_of_max: 0.55, min_families: 1}
  B:      {min_pct_of_max: 0.35, min_families: 1}
"""
    )
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "gold.yaml").write_text(
        """\
inherits: family_financial
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
"""
    )

    result = runner.invoke(
        cli,
        [
            "instruments",
            "show",
            "Gold",
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Gold" in result.output
    # Arvet fra family_financial
    assert "SWING" in result.output
    assert "trend" in result.output


def test_list_resolves_inherits(runner: CliRunner, tmp_path: Path) -> None:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "family_financial.yaml").write_text(
        """\
aggregation: weighted_horizon
horizons:
  SWING:
    family_weights: {trend: 1.0}
    max_score: 5.0
    min_score_publish: 2.5
families:
  trend:
    drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 1}
  A:      {min_pct_of_max: 0.55, min_families: 1}
  B:      {min_pct_of_max: 0.35, min_families: 1}
"""
    )
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "eurusd.yaml").write_text(
        """\
inherits: family_financial
instrument:
  id: EURUSD
  asset_class: fx
  ticker: EURUSD
"""
    )

    result = runner.invoke(
        cli,
        [
            "instruments",
            "list",
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(defaults),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "EURUSD" in result.output


def test_show_missing_defaults_dir_on_inherits_errors(runner: CliRunner, tmp_path: Path) -> None:
    """Instrument bruker `inherits:` men defaults-dir mangler → tydelig feil."""
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "gold.yaml").write_text(
        "inherits: family_financial\ninstrument: {id: Gold, asset_class: metals, ticker: XAUUSD}\n"
    )

    missing_defaults = tmp_path / "no-defaults"

    result = runner.invoke(
        cli,
        [
            "instruments",
            "show",
            "Gold",
            "--instruments-dir",
            str(insts),
            "--defaults-dir",
            str(missing_defaults),
        ],
    )
    assert result.exit_code != 0
    assert "family_financial" in result.output or "not found" in result.output.lower()
