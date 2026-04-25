"""Tester for `bedrock.config.instruments`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from bedrock.config.instruments import (
    InstrumentConfig,
    InstrumentConfigError,
    InstrumentMetadata,
    load_all_instruments,
    load_instrument_config,
)
from bedrock.engine.engine import AgriRules, FinancialRules

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_financial_yaml() -> str:
    return dedent(
        """\
        instrument:
          id: Test
          asset_class: fx
          ticker: TEST

        aggregation: weighted_horizon

        horizons:
          SWING:
            family_weights: {trend: 1.0}
            max_score: 2.0
            min_score_publish: 0.5

        families:
          trend:
            drivers:
              - {name: sma200_align, weight: 1.0, params: {tf: D1}}

        grade_thresholds:
          A_plus: {min_pct_of_max: 0.75, min_families: 1}
          A: {min_pct_of_max: 0.55, min_families: 1}
          B: {min_pct_of_max: 0.35, min_families: 1}
        """
    )


def _minimal_agri_yaml() -> str:
    return dedent(
        """\
        instrument:
          id: TestAgri
          asset_class: grains
          ticker: TST

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
          A: {min_score: 6, min_families_active: 1}
          B: {min_score: 4, min_families_active: 1}
        """
    )


# ---------------------------------------------------------------------------
# Financial YAML
# ---------------------------------------------------------------------------


def test_load_financial_config(tmp_path: Path) -> None:
    path = tmp_path / "test.yaml"
    path.write_text(_minimal_financial_yaml())

    cfg = load_instrument_config(path)
    assert isinstance(cfg, InstrumentConfig)
    assert isinstance(cfg.rules, FinancialRules)
    assert cfg.instrument.id == "Test"
    assert cfg.instrument.asset_class == "fx"
    assert cfg.rules.aggregation == "weighted_horizon"


def test_load_agri_config(tmp_path: Path) -> None:
    path = tmp_path / "testagri.yaml"
    path.write_text(_minimal_agri_yaml())

    cfg = load_instrument_config(path)
    assert isinstance(cfg.rules, AgriRules)
    assert cfg.rules.max_score == 10
    assert cfg.instrument.asset_class == "grains"


# ---------------------------------------------------------------------------
# Optional metadata felter
# ---------------------------------------------------------------------------


def test_metadata_optional_fields_accepted(tmp_path: Path) -> None:
    yaml_txt = dedent(
        """\
        instrument:
          id: Gold
          asset_class: metals
          ticker: XAUUSD
          cfd_ticker: Gold
          yahoo_ticker: GC=F
          cot_contract: "GOLD - COMMODITY EXCHANGE INC."
          cot_report: disaggregated
          weather_region: global
          weather_lat: 0.0
          weather_lon: 0.0
          fred_series_ids:
            - DGS10
            - DTWEXBGS

        aggregation: weighted_horizon

        horizons:
          SWING:
            family_weights: {trend: 1.0}
            max_score: 2.0
            min_score_publish: 0.5

        families:
          trend:
            drivers:
              - {name: sma200_align, weight: 1.0, params: {tf: D1}}

        grade_thresholds:
          A_plus: {min_pct_of_max: 0.75, min_families: 1}
          A: {min_pct_of_max: 0.55, min_families: 1}
          B: {min_pct_of_max: 0.35, min_families: 1}
        """
    )
    path = tmp_path / "gold.yaml"
    path.write_text(yaml_txt)
    cfg = load_instrument_config(path)

    assert cfg.instrument.cot_contract == "GOLD - COMMODITY EXCHANGE INC."
    assert cfg.instrument.cot_report == "disaggregated"
    assert cfg.instrument.fred_series_ids == ["DGS10", "DTWEXBGS"]


def test_metadata_unknown_field_rejected(tmp_path: Path) -> None:
    """`extra='forbid'` skal fange typos i metadata."""
    yaml_txt = dedent(
        """\
        instrument:
          id: X
          asset_class: fx
          ticker: X
          unkown_typo_field: nope

        aggregation: weighted_horizon
        horizons: {SWING: {family_weights: {trend: 1.0}, max_score: 2.0, min_score_publish: 0.5}}
        families: {trend: {drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]}}
        grade_thresholds:
          A_plus: {min_pct_of_max: 0.75, min_families: 1}
          A: {min_pct_of_max: 0.55, min_families: 1}
          B: {min_pct_of_max: 0.35, min_families: 1}
        """
    )
    path = tmp_path / "bad.yaml"
    path.write_text(yaml_txt)
    with pytest.raises(Exception, match="unkown_typo_field"):
        load_instrument_config(path)


# ---------------------------------------------------------------------------
# Validerings-feil
# ---------------------------------------------------------------------------


def test_missing_instrument_block_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("aggregation: weighted_horizon\n")
    with pytest.raises(InstrumentConfigError, match="missing.*instrument"):
        load_instrument_config(path)


def test_unknown_aggregation_raises(tmp_path: Path) -> None:
    yaml_txt = dedent(
        """\
        instrument:
          id: X
          asset_class: fx
          ticker: X

        aggregation: bogus_aggregation
        horizons: {}
        families: {}
        grade_thresholds: {A_plus: {min_pct_of_max: 0.75, min_families: 1}, A: {min_pct_of_max: 0.55, min_families: 1}, B: {min_pct_of_max: 0.35, min_families: 1}}
        """
    )
    path = tmp_path / "bad.yaml"
    path.write_text(yaml_txt)
    with pytest.raises(InstrumentConfigError, match="aggregation"):
        load_instrument_config(path)


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    """Typos i toppnivå-nøkler skal fanges (unngår stille feilkonfigurasjon)."""
    yaml_txt = _minimal_financial_yaml() + "random_unknown_field: 42\n"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml_txt)
    with pytest.raises(InstrumentConfigError, match="random_unknown_field"):
        load_instrument_config(path)


def test_nonexistent_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_instrument_config(tmp_path / "does_not_exist.yaml")


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(InstrumentConfigError, match="YAML mapping"):
        load_instrument_config(path)


# ---------------------------------------------------------------------------
# Deferred keys (silent skip)
# ---------------------------------------------------------------------------


def test_inherits_key_ignored_silently(tmp_path: Path) -> None:
    """`inherits: family_financial` skal ikke crashe — behandles i senere session."""
    yaml_txt = "inherits: family_financial\n" + _minimal_financial_yaml()
    path = tmp_path / "ok.yaml"
    path.write_text(yaml_txt)
    cfg = load_instrument_config(path)  # skal bare funke
    assert cfg.instrument.id == "Test"


def test_gates_key_parsed_into_rules(tmp_path: Path) -> None:
    """Session 25: gates parses nå inn i rules (ikke stille-skipped).

    Ny syntaks: `{name, params, cap_grade}`. Gammel PLAN-syntaks
    `{when: "..."}` feiler nå tydelig (se ADR-003)."""
    yaml_txt = _minimal_financial_yaml() + dedent(
        """\
        gates:
          - {name: min_active_families, params: {min_count: 3}, cap_grade: A}
        """
    )
    path = tmp_path / "ok.yaml"
    path.write_text(yaml_txt)
    cfg = load_instrument_config(path)
    assert cfg.instrument.id == "Test"
    assert len(cfg.rules.gates) == 1
    assert cfg.rules.gates[0].name == "min_active_families"
    assert cfg.rules.gates[0].cap_grade == "A"
    assert cfg.rules.gates[0].params == {"min_count": 3}


def test_usda_blackout_ignored_silently(tmp_path: Path) -> None:
    yaml_txt = _minimal_agri_yaml() + dedent(
        """\
        usda_blackout:
          pre_hours: 3
          post_hours: 3
        """
    )
    path = tmp_path / "ok.yaml"
    path.write_text(yaml_txt)
    cfg = load_instrument_config(path)
    assert cfg.rules.max_score == 10


# ---------------------------------------------------------------------------
# load_all_instruments
# ---------------------------------------------------------------------------


def test_load_all_returns_dict_by_id(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_minimal_financial_yaml())
    agri = _minimal_agri_yaml()
    (tmp_path / "b.yaml").write_text(agri)

    out = load_all_instruments(tmp_path)
    assert set(out.keys()) == {"Test", "TestAgri"}


def test_load_all_duplicate_id_raises(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_minimal_financial_yaml())
    (tmp_path / "b.yaml").write_text(_minimal_financial_yaml())  # samme ID "Test"

    with pytest.raises(InstrumentConfigError, match="Duplicate"):
        load_all_instruments(tmp_path)


def test_load_all_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_all_instruments(tmp_path) == {}


def test_load_all_skips_non_yaml_files(tmp_path: Path) -> None:
    (tmp_path / "ok.yaml").write_text(_minimal_financial_yaml())
    (tmp_path / "ignore.txt").write_text("not yaml")
    (tmp_path / "ignore.md").write_text("# not yaml")
    out = load_all_instruments(tmp_path)
    assert set(out.keys()) == {"Test"}


def test_load_all_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_all_instruments(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# Checked-in config/instruments/ eksempler
# ---------------------------------------------------------------------------


def test_checked_in_gold_yaml_parses() -> None:
    """`config/instruments/gold.yaml` skal parse uten feil."""
    gold_path = REPO_ROOT / "config" / "instruments" / "gold.yaml"
    if not gold_path.exists():
        pytest.skip("config/instruments/gold.yaml not present")
    cfg = load_instrument_config(gold_path)
    assert cfg.instrument.id == "Gold"
    assert cfg.instrument.asset_class == "metals"
    assert isinstance(cfg.rules, FinancialRules)
    assert "SWING" in cfg.rules.horizons


def test_checked_in_corn_yaml_parses() -> None:
    corn_path = REPO_ROOT / "config" / "instruments" / "corn.yaml"
    if not corn_path.exists():
        pytest.skip("config/instruments/corn.yaml not present")
    cfg = load_instrument_config(corn_path)
    assert cfg.instrument.id == "Corn"
    assert isinstance(cfg.rules, AgriRules)
    assert cfg.instrument.weather_region == "us_cornbelt"


def test_load_all_on_checked_in_dir() -> None:
    inst_dir = REPO_ROOT / "config" / "instruments"
    if not inst_dir.exists():
        pytest.skip("config/instruments/ dir not present")
    result = load_all_instruments(inst_dir)
    # Forvent Gold + Corn lastet
    assert "Gold" in result
    assert "Corn" in result


def test_instrument_metadata_is_pydantic_not_typed_dict() -> None:
    """Sanity: InstrumentMetadata er et Pydantic-objekt, ikke en dict."""
    metadata = InstrumentMetadata(id="X", asset_class="fx", ticker="X")
    assert metadata.id == "X"
    assert metadata.cot_contract is None
    # model_dump skal funke
    assert metadata.model_dump()["id"] == "X"
