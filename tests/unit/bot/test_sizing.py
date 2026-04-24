"""Tester for bot.sizing.get_risk_pct — matrise geo/VIX/character/session."""

from __future__ import annotations

from bedrock.bot.config import RiskPctConfig
from bedrock.bot.sizing import get_risk_pct


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
