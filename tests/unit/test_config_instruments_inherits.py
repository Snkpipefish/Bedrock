"""Tester for `inherits`-inheritance i `bedrock.config.instruments`.

Fase 5 session 23: `inherits: family_financial` (og transitivt
`inherits: base`) resolves rekursivt. Shallow merge på top-level keys —
barnets felter vinner.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from bedrock.config.instruments import (
    InstrumentConfigError,
    load_instrument_config,
)
from bedrock.engine.engine import AgriRules, FinancialRules

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
