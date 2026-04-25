"""Tester for bot-config-lasting og SIGHUP-reload-semantikk.

Dekker:
- Defaults når YAML mangler eller er tom
- Roundtrip YAML → Pydantic → YAML → Pydantic
- extra="forbid" fanger ukjente felt
- SIGHUP-reload holder startup_only, bytter reloadable, returnerer diff
- diff_startup_only fanger nested felt-endringer
- Path-oppløsning (arg > env > default)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bedrock.bot.config import (
    DEFAULT_BOT_CONFIG_PATH,
    BotConfig,
    GroupParams,
    ReloadableConfig,
    StartupOnlyConfig,
    diff_startup_only,
    load_bot_config,
    load_bot_config_from_yaml_string,
    reload_bot_config,
    resolve_bot_config_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLED_YAML = REPO_ROOT / "config" / "bot.yaml"


# ─────────────────────────────────────────────────────────────
# Defaults og lasting
# ─────────────────────────────────────────────────────────────


def test_bot_config_default_construction() -> None:
    cfg = BotConfig()
    assert cfg.startup_only.signal_url == "http://localhost:5100"
    assert cfg.startup_only.reconnect.window_sec == 600
    assert cfg.reloadable.risk_pct.full == 1.0
    assert cfg.reloadable.horizon_ttl.scalp == 900
    assert "fx" in cfg.reloadable.group_params
    assert cfg.reloadable.group_params["fx"].trail_atr == 2.5


def test_load_empty_yaml_gives_defaults() -> None:
    cfg = load_bot_config_from_yaml_string("")
    assert cfg == BotConfig()


def test_load_partial_yaml_merges_with_defaults() -> None:
    # Kun overstyre én reloadable-verdi; resten må bruke defaults
    yaml_text = """
reloadable:
  risk_pct:
    full: 0.75
"""
    cfg = load_bot_config_from_yaml_string(yaml_text)
    assert cfg.reloadable.risk_pct.full == 0.75
    # Half/quarter + andre seksjoner = default
    assert cfg.reloadable.risk_pct.half == 0.5
    assert cfg.reloadable.daily_loss.pct_of_balance == 2.0
    assert cfg.startup_only.signal_url == "http://localhost:5100"


def test_load_missing_file_gives_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    assert not missing.exists()
    cfg = load_bot_config(missing)
    assert cfg == BotConfig()


def test_extra_field_forbidden() -> None:
    yaml_text = """
reloadable:
  confirmation:
    unknown_key: 42
"""
    with pytest.raises(ValidationError):
        load_bot_config_from_yaml_string(yaml_text)


def test_top_level_must_be_mapping() -> None:
    with pytest.raises(ValueError):
        load_bot_config_from_yaml_string("- not\n- a\n- mapping")


def test_non_dict_yaml_rejected() -> None:
    with pytest.raises(ValueError):
        load_bot_config_from_yaml_string("42")


# ─────────────────────────────────────────────────────────────
# Bundled bot.yaml må validere
# ─────────────────────────────────────────────────────────────


def test_bundled_bot_yaml_parses() -> None:
    assert BUNDLED_YAML.exists(), f"mangler: {BUNDLED_YAML}"
    cfg = load_bot_config(BUNDLED_YAML)
    assert isinstance(cfg, BotConfig)


def test_bundled_bot_yaml_matches_defaults() -> None:
    """config/bot.yaml skal inneholde samme defaults som Pydantic-modellen
    ved session 40-oppstart. Dette er regresjonstest mot utilsiktet drift
    mellom kode-defaults og YAML."""
    cfg_yaml = load_bot_config(BUNDLED_YAML)
    cfg_default = BotConfig()
    assert cfg_yaml == cfg_default


# ─────────────────────────────────────────────────────────────
# Roundtrip
# ─────────────────────────────────────────────────────────────


def test_roundtrip_yaml_pydantic_yaml() -> None:
    original = BotConfig()
    dumped = yaml.safe_dump(original.model_dump(), sort_keys=False)
    parsed = load_bot_config_from_yaml_string(dumped)
    assert parsed == original


def test_roundtrip_preserves_custom_values() -> None:
    custom = BotConfig(
        startup_only=StartupOnlyConfig(signal_url="http://other:6000"),
        reloadable=ReloadableConfig.model_validate(
            {"risk_pct": {"full": 0.3, "half": 0.15, "quarter": 0.05}}
        ),
    )
    dumped = yaml.safe_dump(custom.model_dump(), sort_keys=False)
    parsed = load_bot_config_from_yaml_string(dumped)
    assert parsed.startup_only.signal_url == "http://other:6000"
    assert parsed.reloadable.risk_pct.full == 0.3


# ─────────────────────────────────────────────────────────────
# SIGHUP-reload-semantikk
# ─────────────────────────────────────────────────────────────


def test_diff_startup_only_identical_is_empty() -> None:
    a = StartupOnlyConfig()
    b = StartupOnlyConfig()
    assert diff_startup_only(a, b) == []


def test_diff_startup_only_top_level_change() -> None:
    a = StartupOnlyConfig()
    b = StartupOnlyConfig(signal_url="http://new:7000")
    diffs = diff_startup_only(a, b)
    assert len(diffs) == 1
    assert "signal_url" in diffs[0]
    assert "localhost:5100" in diffs[0]
    assert "new:7000" in diffs[0]


def test_diff_startup_only_nested_change() -> None:
    a = StartupOnlyConfig()
    b_dict = a.model_dump()
    b_dict["reconnect"]["window_sec"] = 1200
    b = StartupOnlyConfig.model_validate(b_dict)
    diffs = diff_startup_only(a, b)
    assert len(diffs) == 1
    assert "reconnect.window_sec" in diffs[0]
    assert "600" in diffs[0]
    assert "1200" in diffs[0]


def test_reload_holds_startup_only_and_swaps_reloadable(tmp_path: Path) -> None:
    # Start: default config aktiv
    current = BotConfig()

    # Skriv ny YAML med endringer i BÅDE startup_only og reloadable
    new_yaml = """
startup_only:
  signal_url: "http://changed:9000"
  reconnect:
    window_sec: 1800
    max_in_window: 10
reloadable:
  risk_pct:
    full: 0.5
    half: 0.25
    quarter: 0.1
"""
    path = tmp_path / "bot.yaml"
    path.write_text(new_yaml, encoding="utf-8")

    merged, diffs = reload_bot_config(path, current)

    # startup_only = HOLDES (gammel verdi)
    assert merged.startup_only.signal_url == "http://localhost:5100"
    assert merged.startup_only.reconnect.window_sec == 600

    # reloadable = NY verdi
    assert merged.reloadable.risk_pct.full == 0.5
    assert merged.reloadable.risk_pct.half == 0.25

    # Diff-listen gir brukeren forvarsel om hva restart vil aktivere
    assert len(diffs) >= 2
    assert any("signal_url" in d for d in diffs)
    assert any("reconnect.window_sec" in d for d in diffs)


def test_reload_no_change_returns_empty_diff(tmp_path: Path) -> None:
    path = tmp_path / "bot.yaml"
    path.write_text(yaml.safe_dump(BotConfig().model_dump(), sort_keys=False))
    merged, diffs = reload_bot_config(path, BotConfig())
    assert diffs == []
    assert merged == BotConfig()


def test_reload_missing_file_keeps_current(tmp_path: Path) -> None:
    missing = tmp_path / "no.yaml"
    current = BotConfig()
    merged, diffs = reload_bot_config(missing, current)
    # reload_bot_config laster defaults når fil mangler — i så fall
    # vil "proposed == default == current" og diff skal være tom
    assert merged == current
    assert diffs == []


# ─────────────────────────────────────────────────────────────
# Path-oppløsning
# ─────────────────────────────────────────────────────────────


def test_resolve_path_explicit_wins(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.yaml"
    assert resolve_bot_config_path(explicit) == explicit


def test_resolve_path_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "envvar.yaml"))
    assert resolve_bot_config_path() == tmp_path / "envvar.yaml"


def test_resolve_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_BOT_CONFIG", raising=False)
    assert resolve_bot_config_path() == DEFAULT_BOT_CONFIG_PATH


# ─────────────────────────────────────────────────────────────
# GroupParams validation
# ─────────────────────────────────────────────────────────────


def test_group_params_required_fields() -> None:
    with pytest.raises(ValidationError):
        GroupParams.model_validate({"trail_atr": 2.5})  # mangler resten


def test_group_params_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        GroupParams.model_validate(
            {
                "trail_atr": 2.5,
                "gb_peak": 0.85,
                "gb_exit": 0.30,
                "be_atr": 0.10,
                "expiry": 32,
                "ema9_exit": True,
                "bonus_field": "not allowed",
            }
        )
