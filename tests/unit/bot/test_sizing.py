"""Tester for bot.sizing — risk-pct + lot-tier + volume-konvertering."""

from __future__ import annotations

import pytest

from bedrock.bot.config import RiskPctConfig
from bedrock.bot.sizing import (
    compute_risk_lots,
    get_risk_pct,
    lots_to_volume_units,
    volume_to_lots,
)


def _run(
    *,
    geo: bool = False,
    vix: str = "normal",
    grade: str | None = None,
    outside_session: bool = False,
    cfg: RiskPctConfig | None = None,
    rules: dict | None = None,
) -> float:
    cfg = cfg or RiskPctConfig()
    sig: dict = {}
    if grade is not None:
        sig["grade"] = grade
    if outside_session:
        sig["_outside_session"] = True
    gs = {"geo_active": geo, "vix_regime": vix}
    return get_risk_pct(sig, gs, rules or {}, cfg)


def test_default_is_full() -> None:
    assert _run() == 1.0


def test_geo_active_gives_quarter() -> None:
    assert _run(geo=True) == 0.25


def test_grade_c_gives_quarter() -> None:
    assert _run(grade="C") == 0.25


def test_vix_extreme_gives_quarter() -> None:
    assert _run(vix="extreme") == 0.25


def test_vix_elevated_gives_half() -> None:
    assert _run(vix="elevated") == 0.5


def test_grade_b_gives_half() -> None:
    assert _run(grade="B") == 0.5


def test_outside_session_gives_half() -> None:
    assert _run(outside_session=True) == 0.5


def test_geo_beats_vix_elevated() -> None:
    """geo_active → quarter tar precedence over elevated VIX → half."""
    assert _run(geo=True, vix="elevated") == 0.25


def test_grade_a_normal_full() -> None:
    assert _run(grade="A") == 1.0


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
# compute_risk_lots — risikobasert volum (tap ved SL ≈ risk_amount)
# ─────────────────────────────────────────────────────────────

_EURUSD = {"lot_size": 10_000_000, "min_volume": 100_000, "step_volume": 100_000}
_NATGAS = {"lot_size": 100_000, "min_volume": 100_000, "step_volume": 100_000}
_GOLD = {"lot_size": 1000, "min_volume": 10, "step_volume": 10}


def test_risk_lots_eurusd_nok_account() -> None:
    """risk 2444 NOK, SL 0.0055, 100k enh/lot, USDNOK 8.5 → 0.52 lot,
    rundet ned til step (0.01 lot = 100_000 cents-enheter)."""
    vol, lots, block = compute_risk_lots(
        risk_amount=2444, sl_distance=0.0055, symbol_info=_EURUSD, quote_to_account=8.5
    )
    assert block is None
    assert lots == 0.52
    assert vol == 5_200_000
    # Faktisk risiko ved SL ≈ planlagt (avrunding ned → litt under)
    assert (vol / 100) * 0.0055 * 8.5 == pytest.approx(2431, abs=1)


def test_risk_lots_rounds_down_to_step() -> None:
    vol, lots, _ = compute_risk_lots(
        risk_amount=100, sl_distance=40.0, symbol_info=_GOLD, quote_to_account=1.0
    )
    # 100 / (40 × 10) = 0.25 lot = 250 enheter → step 10 → 250
    assert vol == 250
    assert lots == 0.25


def test_risk_lots_min_lot_accepted_within_overshoot() -> None:
    """NATGAS min-lot (1000 enh) risikerer 0.09×1000×8.5 = 765 < 1.5×600."""
    vol, lots, block = compute_risk_lots(
        risk_amount=600, sl_distance=0.09, symbol_info=_NATGAS, quote_to_account=8.5
    )
    assert block is None
    assert vol == 100_000
    assert lots == 1.0


def test_risk_lots_min_lot_blocked_when_overshoot_too_big() -> None:
    """Min-lot risikerer 765 > 1.5 × 300 → blokker (NATGAS-tapene 2026-08)."""
    vol, lots, block = compute_risk_lots(
        risk_amount=300, sl_distance=0.09, symbol_info=_NATGAS, quote_to_account=8.5
    )
    assert vol == 0 and lots == 0.0
    assert block is not None and "min-lot" in block


def test_risk_lots_caps_at_max_volume() -> None:
    info = {**_GOLD, "max_volume": 1000}
    vol, _, block = compute_risk_lots(
        risk_amount=100_000, sl_distance=1.0, symbol_info=info, quote_to_account=1.0
    )
    assert block is None
    assert vol == 1000


def test_risk_lots_blocks_on_missing_symbol_info_or_bad_input() -> None:
    assert compute_risk_lots(
        risk_amount=100, sl_distance=1.0, symbol_info=None, quote_to_account=1.0
    )[2]
    assert compute_risk_lots(
        risk_amount=0, sl_distance=1.0, symbol_info=_GOLD, quote_to_account=1.0
    )[2]
    assert compute_risk_lots(
        risk_amount=100, sl_distance=0.0, symbol_info=_GOLD, quote_to_account=1.0
    )[2]
    assert compute_risk_lots(
        risk_amount=100, sl_distance=1.0, symbol_info=_GOLD, quote_to_account=0.0
    )[2]


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
