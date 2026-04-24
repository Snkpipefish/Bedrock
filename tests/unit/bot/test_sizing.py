"""Tester for bot.sizing — risk-pct + lot-tier + volume-konvertering."""

from __future__ import annotations

from bedrock.bot.config import RiskPctConfig
from bedrock.bot.sizing import (
    compute_desired_lots,
    get_risk_pct,
    lots_to_volume_units,
    volume_to_lots,
)


def _run(
    *,
    geo: bool = False,
    vix: str = "normal",
    character: str | None = None,
    outside_session: bool = False,
    cfg: RiskPctConfig | None = None,
    rules: dict | None = None,
) -> float:
    cfg = cfg or RiskPctConfig()
    sig: dict = {}
    if character is not None:
        sig["character"] = character
    if outside_session:
        sig["_outside_session"] = True
    gs = {"geo_active": geo, "vix_regime": vix}
    return get_risk_pct(sig, gs, rules or {}, cfg)


def test_default_is_full() -> None:
    assert _run() == 1.0


def test_geo_active_gives_quarter() -> None:
    assert _run(geo=True) == 0.25


def test_character_c_gives_quarter() -> None:
    assert _run(character="C") == 0.25


def test_vix_extreme_gives_quarter() -> None:
    assert _run(vix="extreme") == 0.25


def test_vix_elevated_gives_half() -> None:
    assert _run(vix="elevated") == 0.5


def test_character_b_gives_half() -> None:
    assert _run(character="B") == 0.5


def test_outside_session_gives_half() -> None:
    assert _run(outside_session=True) == 0.5


def test_geo_beats_vix_elevated() -> None:
    """geo_active → quarter tar precedence over elevated VIX → half."""
    assert _run(geo=True, vix="elevated") == 0.25


def test_character_a_normal_full() -> None:
    assert _run(character="A") == 1.0


def test_rules_override_full() -> None:
    # Instrument-YAML kan sette andre defaults via rules
    assert _run(rules={"risk_pct_full": 0.8}) == 0.8


def test_rules_override_half_on_vix_elevated() -> None:
    assert _run(vix="elevated", rules={"risk_pct_half": 0.3}) == 0.3


def test_rules_override_quarter_on_geo() -> None:
    assert _run(geo=True, rules={"risk_pct_quarter": 0.1}) == 0.1


def test_cfg_defaults_respected_without_rules() -> None:
    cfg = RiskPctConfig(full=0.75, half=0.4, quarter=0.2)
    assert _run(cfg=cfg) == 0.75
    assert _run(vix="elevated", cfg=cfg) == 0.4
    assert _run(geo=True, cfg=cfg) == 0.2


# ─────────────────────────────────────────────────────────────
# compute_desired_lots — lot-tier + VIX/agri-nedskalering
# ─────────────────────────────────────────────────────────────


def test_desired_lots_scalp_tier() -> None:
    sig = {"horizon_config": {"sizing_base_risk_usd": 20}, "instrument": "EURUSD"}
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.01


def test_desired_lots_swing_tier() -> None:
    sig = {"horizon_config": {"sizing_base_risk_usd": 40}, "instrument": "EURUSD"}
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.02


def test_desired_lots_makro_tier() -> None:
    sig = {"horizon_config": {"sizing_base_risk_usd": 60}, "instrument": "EURUSD"}
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.03


def test_desired_lots_default_base_risk_is_scalp() -> None:
    """Tom horizon_config → base_risk=20 (SCALP-tier)."""
    sig = {"instrument": "EURUSD"}
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.01


def test_desired_lots_vix_quarter_downsize() -> None:
    """risk_pct < 0.5 → ×0.5, men ikke under 0.01."""
    sig = {"horizon_config": {"sizing_base_risk_usd": 60}, "instrument": "EURUSD"}
    # MAKRO 0.03 × 0.5 = 0.015
    assert compute_desired_lots(sig, risk_pct=0.25) == 0.015


def test_desired_lots_vix_half_downsize() -> None:
    """risk_pct < 1.0 → ×0.75, men ikke under 0.01."""
    sig = {"horizon_config": {"sizing_base_risk_usd": 60}, "instrument": "EURUSD"}
    # MAKRO 0.03 × 0.75 = 0.0225
    assert compute_desired_lots(sig, risk_pct=0.5) == 0.0225


def test_desired_lots_floor_at_min_lot() -> None:
    """Selv aggressiv nedskalering holder gulv på 0.01."""
    sig = {"horizon_config": {"sizing_base_risk_usd": 20}, "instrument": "EURUSD"}
    # SCALP 0.01 × 0.5 = 0.005 → floor 0.01
    assert compute_desired_lots(sig, risk_pct=0.25) == 0.01


def test_desired_lots_agri_halvert() -> None:
    """Agri-instrument → ekstra ×0.5 på slutten, gulv 0.01."""
    sig = {"horizon_config": {"sizing_base_risk_usd": 40}, "instrument": "Corn"}
    # SWING 0.02 × 0.5 (agri) = 0.01
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.01


def test_desired_lots_agri_makro() -> None:
    sig = {"horizon_config": {"sizing_base_risk_usd": 60}, "instrument": "Soybean"}
    # MAKRO 0.03 × 0.5 (agri) = 0.015
    assert compute_desired_lots(sig, risk_pct=1.0) == 0.015


def test_desired_lots_agri_combined_with_vix() -> None:
    sig = {"horizon_config": {"sizing_base_risk_usd": 60}, "instrument": "Wheat"}
    # MAKRO 0.03 × 0.5 (VIX extreme via risk_pct<0.5) × 0.5 (agri) = 0.0075 → 0.01 floor
    assert compute_desired_lots(sig, risk_pct=0.25) == 0.01


# ─────────────────────────────────────────────────────────────
# lots_to_volume_units — stepVolume-avrunding + min_volume-gulv
# ─────────────────────────────────────────────────────────────


def test_lots_to_units_exact_match() -> None:
    info = {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}
    # 0.01 lot = 1000 units. Ingen avrunding nødvendig.
    assert lots_to_volume_units(0.01, info) == 1000


def test_lots_to_units_steps_down_to_valid() -> None:
    info = {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}
    # 0.015 lot = 1500 units → (1500 // 1000) × 1000 = 1000
    assert lots_to_volume_units(0.015, info) == 1000


def test_lots_to_units_enforces_min_volume() -> None:
    info = {"lot_size": 100_000, "min_volume": 2000, "step_volume": 1000}
    # 0.01 lot = 1000 units < min 2000 → løft til 2000
    assert lots_to_volume_units(0.01, info) == 2000


def test_lots_to_units_fallback_without_info() -> None:
    """Uten symbol_info: fallback 1000 enheter."""
    assert lots_to_volume_units(0.01, None) == 1000
    assert lots_to_volume_units(0.05, {}) == 1000


def test_lots_to_units_agri_step_volume() -> None:
    """Agri har typisk større step_volume (f.eks. 100)."""
    info = {"lot_size": 5000, "min_volume": 100, "step_volume": 100}
    # 0.01 lot = 50 units < min 100 → 100
    assert lots_to_volume_units(0.01, info) == 100
    # 0.05 lot = 250 units → (250 // 100) × 100 = 200
    assert lots_to_volume_units(0.05, info) == 200


# ─────────────────────────────────────────────────────────────
# volume_to_lots — invers konvertering for trade-logging
# ─────────────────────────────────────────────────────────────


def test_volume_to_lots_with_info() -> None:
    info = {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}
    assert volume_to_lots(1000, info) == 0.01
    assert volume_to_lots(2000, info) == 0.02


def test_volume_to_lots_zero_returns_none() -> None:
    assert volume_to_lots(0, {"lot_size": 100_000}) is None


def test_volume_to_lots_fallback_fx() -> None:
    """Uten symbol_info: fallback FX-standard (lot_size=100000)."""
    assert volume_to_lots(1000, None) == 0.01
    assert volume_to_lots(10_000, {}) == 0.1
