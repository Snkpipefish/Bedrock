"""Tester for `inherits`-inheritance i `bedrock.config.instruments`.

Fase 5 session 23: `inherits: family_financial` (og transitivt
`inherits: base`) resolves rekursivt. Shallow merge på top-level keys —
barnets felter vinner.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from bedrock.config.instruments import (
    InstrumentConfigError,
    load_instrument_config,
)
from bedrock.engine.engine import AgriRules, FinancialRules
from bedrock.setups.generator import SetupConfig

# ---------------------------------------------------------------------------
# Hjelpere
# ---------------------------------------------------------------------------


def _write_defaults_dir(tmp_path: Path) -> Path:
    """Minimale defaults-filer for kontrollerte tester.

    Strukturen speiler `config/defaults/` men er selvstendig — tester
    skal ikke avhenge av innholdet i checked-in defaults.
    """
    d = tmp_path / "defaults"
    d.mkdir()
    (d / "base.yaml").write_text(
        dedent(
            """\
            hysteresis:
              sl_stability_atr: 0.3
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.99, min_families: 10}
              A:      {min_pct_of_max: 0.80, min_families: 5}
              B:      {min_pct_of_max: 0.60, min_families: 2}
            """
        )
    )
    (d / "family_financial.yaml").write_text(
        dedent(
            """\
            inherits: base
            aggregation: weighted_horizon
            horizons:
              SWING:
                family_weights: {trend: 1.0, positioning: 1.0}
                max_score: 5.0
                min_score_publish: 2.5
            families:
              trend:
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
              positioning:
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.75, min_families: 2}
              A:      {min_pct_of_max: 0.55, min_families: 2}
              B:      {min_pct_of_max: 0.35, min_families: 1}
            """
        )
    )
    (d / "family_agri.yaml").write_text(
        dedent(
            """\
            inherits: base
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


# ---------------------------------------------------------------------------
# Grunnleggende inheritance-tilfelle
# ---------------------------------------------------------------------------


def test_inherits_family_financial_fills_in_defaults(tmp_path: Path) -> None:
    """Instrument med kun metadata arver alt fra family_financial."""
    defaults = _write_defaults_dir(tmp_path)
    inst = tmp_path / "gold.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
            """
        )
    )

    cfg = load_instrument_config(inst, defaults_dir=defaults)

    assert isinstance(cfg.rules, FinancialRules)
    assert cfg.instrument.id == "Gold"
    # Arvet fra family_financial
    assert "SWING" in cfg.rules.horizons
    assert "trend" in cfg.rules.families
    assert "positioning" in cfg.rules.families
    # grade_thresholds arvet fra family_financial (ikke base — siden
    # family_financial overstyrer)
    assert cfg.rules.grade_thresholds.a_plus.min_pct_of_max == pytest.approx(0.75)


def test_child_overrides_parent_on_top_level_key(tmp_path: Path) -> None:
    """Barn som definerer `grade_thresholds` overstyrer family_financial's."""
    defaults = _write_defaults_dir(tmp_path)
    inst = tmp_path / "gold.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.90, min_families: 2}
              A:      {min_pct_of_max: 0.70, min_families: 2}
              B:      {min_pct_of_max: 0.50, min_families: 1}
            """
        )
    )

    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, FinancialRules)
    assert cfg.rules.grade_thresholds.a_plus.min_pct_of_max == pytest.approx(0.90)


def test_child_horizons_replaces_parent_horizons(tmp_path: Path) -> None:
    """Barn som definerer horizons erstatter hele blokken (shallow merge)."""
    defaults = _write_defaults_dir(tmp_path)
    inst = tmp_path / "btc.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: BTC
              asset_class: crypto
              ticker: BTCUSD
            horizons:
              SCALP:
                family_weights: {trend: 2.0, positioning: 0.5}
                max_score: 3.0
                min_score_publish: 1.0
            """
        )
    )

    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, FinancialRules)
    # Bare SCALP, ikke SWING fra parent
    assert list(cfg.rules.horizons.keys()) == ["SCALP"]


# ---------------------------------------------------------------------------
# Agri-inheritance
# ---------------------------------------------------------------------------


def test_inherits_family_agri_fills_in_defaults(tmp_path: Path) -> None:
    defaults = _write_defaults_dir(tmp_path)
    inst = tmp_path / "corn.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_agri
            instrument:
              id: Corn
              asset_class: grains
              ticker: ZC
            """
        )
    )

    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, AgriRules)
    assert cfg.rules.max_score == 10
    assert "outlook" in cfg.rules.families


# ---------------------------------------------------------------------------
# Rekursjon: base ← family_* ← instrument
# ---------------------------------------------------------------------------


def test_transitive_inheritance_uses_base_when_family_does_not_override(
    tmp_path: Path,
) -> None:
    """Hvis family_financial IKKE har grade_thresholds, arves det fra base."""
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "base.yaml").write_text(
        dedent(
            """\
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.99, min_families: 1}
              A:      {min_pct_of_max: 0.80, min_families: 1}
              B:      {min_pct_of_max: 0.60, min_families: 1}
            """
        )
    )
    (defaults / "family_financial.yaml").write_text(
        dedent(
            """\
            inherits: base
            aggregation: weighted_horizon
            horizons:
              SWING:
                family_weights: {trend: 1.0}
                max_score: 5.0
                min_score_publish: 2.5
            families:
              trend:
                drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
            """
        )
    )
    inst = tmp_path / "x.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: X
              asset_class: fx
              ticker: X
            """
        )
    )

    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, FinancialRules)
    # Terskelen kommer fra base (0.99) siden family_financial ikke
    # overstyrte den i denne oppsettet
    assert cfg.rules.grade_thresholds.a_plus.min_pct_of_max == pytest.approx(0.99)


# ---------------------------------------------------------------------------
# Feil-scenarioer
# ---------------------------------------------------------------------------


def test_missing_parent_errors_clearly(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    inst = tmp_path / "gold.yaml"
    inst.write_text(
        "inherits: nope\ninstrument: {id: X, asset_class: fx, ticker: X}\n"
        "aggregation: weighted_horizon\n"
        "horizons:\n  SWING: {family_weights: {t: 1}, max_score: 2, min_score_publish: 0}\n"
        "families: {t: {drivers: [{name: sma200_align, weight: 1, params: {tf: D1}}]}}\n"
        "grade_thresholds:\n  A_plus: {min_pct_of_max: 0.9, min_families: 1}\n"
        "  A: {min_pct_of_max: 0.7, min_families: 1}\n"
        "  B: {min_pct_of_max: 0.5, min_families: 1}\n"
    )

    with pytest.raises(InstrumentConfigError, match="nope"):
        load_instrument_config(inst, defaults_dir=defaults)


def test_circular_inherits_detected(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "a.yaml").write_text("inherits: b\n")
    (defaults / "b.yaml").write_text("inherits: a\n")
    inst = tmp_path / "x.yaml"
    inst.write_text("inherits: a\ninstrument: {id: X, asset_class: fx, ticker: X}\n")

    with pytest.raises(InstrumentConfigError, match="circular"):
        load_instrument_config(inst, defaults_dir=defaults)


def test_non_string_inherits_errors(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    inst = tmp_path / "x.yaml"
    inst.write_text("inherits: [a, b]\ninstrument: {id: X, asset_class: fx, ticker: X}\n")
    with pytest.raises(InstrumentConfigError, match="inherits.*must be a string"):
        load_instrument_config(inst, defaults_dir=defaults)


# ---------------------------------------------------------------------------
# `setup:`-blokk → InstrumentConfig.setup (session 2026-09-05)
# ---------------------------------------------------------------------------


def _write_gold_child(tmp_path: Path, extra: str = "") -> Path:
    inst = tmp_path / "gold.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
            """
        )
        + extra
    )
    return inst


def test_setup_block_absent_yields_none(tmp_path: Path) -> None:
    """Ingen `setup:` noe sted i kjeden → `cfg.setup is None` (orchestrator
    faller tilbake til `SetupConfig()`)."""
    defaults = _write_defaults_dir(tmp_path)
    cfg = load_instrument_config(_write_gold_child(tmp_path), defaults_dir=defaults)
    assert cfg.setup is None


def test_setup_block_on_child_parsed_into_setup_config(tmp_path: Path) -> None:
    defaults = _write_defaults_dir(tmp_path)
    inst = _write_gold_child(tmp_path, "setup:\n  min_rr_swing: 9.0\n")
    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.setup, SetupConfig)
    assert cfg.setup.min_rr_swing == pytest.approx(9.0)
    # Øvrige felter = defaults
    assert cfg.setup.min_rr_scalp == SetupConfig().min_rr_scalp


def test_setup_block_inherited_from_family_default(tmp_path: Path) -> None:
    """`setup:` i family_financial.yaml bæres gjennom til barnet."""
    defaults = _write_defaults_dir(tmp_path)
    family = defaults / "family_financial.yaml"
    family.write_text(family.read_text() + "setup:\n  sl_atr_multiplier_swing: 1.2\n")

    cfg = load_instrument_config(_write_gold_child(tmp_path), defaults_dir=defaults)
    assert cfg.setup is not None
    assert cfg.setup.sl_atr_multiplier_swing == pytest.approx(1.2)


def test_child_setup_block_replaces_parent_setup_block(tmp_path: Path) -> None:
    """Shallow top-level merge: barnets `setup:` erstatter HELE blokken
    (barnet vinner) — parent-felt bæres ikke med under blokk-nivå,
    konsistent med `families`/`horizons`."""
    defaults = _write_defaults_dir(tmp_path)
    family = defaults / "family_financial.yaml"
    family.write_text(family.read_text() + "setup:\n  sl_atr_multiplier_swing: 1.2\n")
    inst = _write_gold_child(tmp_path, "setup:\n  min_rr_swing: 9.0\n")

    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert cfg.setup is not None
    assert cfg.setup.min_rr_swing == pytest.approx(9.0)
    assert cfg.setup.sl_atr_multiplier_swing == SetupConfig().sl_atr_multiplier_swing


def test_setup_block_unknown_key_is_hard_fail(tmp_path: Path) -> None:
    """`extra="forbid"` på SetupConfig — skrivefeil skal ikke passere stille."""
    defaults = _write_defaults_dir(tmp_path)
    inst = _write_gold_child(tmp_path, "setup:\n  min_rr_swng: 9.0\n")
    with pytest.raises(ValidationError, match="min_rr_swng"):
        load_instrument_config(inst, defaults_dir=defaults)


def test_setup_block_non_mapping_errors(tmp_path: Path) -> None:
    defaults = _write_defaults_dir(tmp_path)
    inst = _write_gold_child(tmp_path, "setup: [1, 2]\n")
    with pytest.raises(InstrumentConfigError, match="must be a mapping"):
        load_instrument_config(inst, defaults_dir=defaults)


def test_setup_block_does_not_leak_into_rules(tmp_path: Path) -> None:
    """`setup:` er ikke en rules-nøkkel — Engine skal ikke se den."""
    defaults = _write_defaults_dir(tmp_path)
    inst = _write_gold_child(tmp_path, "setup:\n  min_rr_swing: 9.0\n")
    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, FinancialRules)
    assert not hasattr(cfg.rules, "setup")


# ---------------------------------------------------------------------------
# Agri-spesifikke felter arves men ignoreres fortsatt (til de implementeres)
# ---------------------------------------------------------------------------


def test_usda_blackout_inherited_but_deferred(tmp_path: Path) -> None:
    """family_agri.yaml kan ha usda_blackout. Skal arves stille til
    eksplisitt scoring-integrasjon implementeres."""
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "family_agri.yaml").write_text(
        dedent(
            """\
            aggregation: additive_sum
            max_score: 10
            min_score_publish: 4
            families:
              outlook:
                weight: 5
                drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
            grade_thresholds:
              A_plus: {min_score: 8, min_families_active: 1}
              A:      {min_score: 6, min_families_active: 1}
              B:      {min_score: 4, min_families_active: 1}
            usda_blackout:
              pre_hours: 3
              post_hours: 3
              sources: [WASDE]
            """
        )
    )
    inst = tmp_path / "corn.yaml"
    inst.write_text(
        dedent(
            """\
            inherits: family_agri
            instrument:
              id: Corn
              asset_class: grains
              ticker: ZC
            """
        )
    )
    # Skal ikke kaste — usda_blackout er stille-skippet
    cfg = load_instrument_config(inst, defaults_dir=defaults)
    assert isinstance(cfg.rules, AgriRules)
