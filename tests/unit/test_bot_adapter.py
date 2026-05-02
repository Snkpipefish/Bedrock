"""Tester for `bedrock.signal_server.bot_adapter`.

Sub-fase 12.9 D1a. Verifiserer at adapter-output matcher bot's
forventede signal-payload-format.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bedrock.signal_server.bot_adapter import (
    HORIZON_DEFAULTS,
    SCHEMA_VERSION,
    adapt_to_bot_format,
)


def _make_entry(
    *,
    instrument: str = "AUDUSD",
    direction: str = "buy",
    horizon: str = "makro",
    asset_class: str = "fx",
    published: bool = True,
    entry: float = 0.7178,
    sl: float = 0.7167,
    tp: float | None = None,
    atr: float = 0.00355,
    setup_id: str = "abc123",
    score: float = 4.29,
    grade: str = "A",
) -> dict:
    return {
        "instrument": instrument,
        "direction": direction,
        "horizon": horizon,
        "score": score,
        "grade": grade,
        "max_score": 5.8,
        "min_score_publish": 3.5,
        "published": published,
        "asset_class": asset_class,
        "setup": {
            "setup_id": setup_id,
            "first_seen": "2026-05-01T01:39:34Z",
            "setup": {
                "instrument": instrument,
                "direction": direction,
                "horizon": horizon,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "rr": None,
                "atr": atr,
            },
        },
        "skip_reason": None,
        "gates_triggered": [],
        "families": {},
        "active_families": 6,
        "analog": None,
    }


def test_empty_input_yields_valid_payload():
    payload = adapt_to_bot_format([])
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["signals"] == []
    assert payload["n_total"] == 0
    assert payload["n_published"] == 0
    assert "valid_until" in payload
    assert "global_state" in payload


def test_unpublished_entries_are_filtered():
    entries = [_make_entry(published=False), _make_entry(published=True)]
    payload = adapt_to_bot_format(entries)
    assert payload["n_total"] == 2
    assert payload["n_published"] == 1


def test_horizon_normalized_to_uppercase():
    payload = adapt_to_bot_format([_make_entry(horizon="makro")])
    assert payload["signals"][0]["horizon"] == "MAKRO"


def test_signal_fields_present():
    payload = adapt_to_bot_format([_make_entry()])
    sig = payload["signals"][0]
    expected_keys = {
        "id",
        "instrument",
        "direction",
        "horizon",
        "status",
        "entry_zone",
        "alert_level",
        "stop",
        "t1",
        "atr",
        "expiry_candles",
        "confirmation_candle_limit",
        "horizon_config",
        "correlation_group",
        "created_at",
        "score",
        "grade",
        "rr",
    }
    assert expected_keys.issubset(sig.keys())


def test_entry_zone_is_atr_band_around_entry():
    payload = adapt_to_bot_format([_make_entry(entry=100.0, atr=4.0)])
    sig = payload["signals"][0]
    low, high = sig["entry_zone"]
    # ±0.25 * atr
    assert low == 99.0
    assert high == 101.0


def test_entry_zone_fallback_when_no_atr():
    payload = adapt_to_bot_format([_make_entry(entry=100.0, atr=0.0)])
    sig = payload["signals"][0]
    low, high = sig["entry_zone"]
    # 5 bps fallback
    assert low == 99.95
    assert high == 100.05


def test_makro_horizon_has_no_tp():
    payload = adapt_to_bot_format([_make_entry(horizon="makro", tp=None)])
    sig = payload["signals"][0]
    assert sig["t1"] == 0.0
    assert sig["horizon_config"]["tp_atr_mult"] is None


def test_swing_horizon_has_tp_when_set():
    payload = adapt_to_bot_format([_make_entry(horizon="swing", tp=110.5)])
    sig = payload["signals"][0]
    assert sig["t1"] == 110.5
    assert sig["horizon_config"]["tp_atr_mult"] == 3.5


def test_horizon_defaults_for_all_three():
    for hor_in, hor_out in (("scalp", "SCALP"), ("swing", "SWING"), ("makro", "MAKRO")):
        payload = adapt_to_bot_format([_make_entry(horizon=hor_in)])
        sig = payload["signals"][0]
        assert sig["horizon"] == hor_out
        defaults = HORIZON_DEFAULTS[hor_out]
        assert sig["expiry_candles"] == defaults["expiry_candles"]
        assert sig["confirmation_candle_limit"] == defaults["confirmation_candle_limit"]


def test_exit_trail_atr_mult_present_per_horizon_per_group():
    """Hver horisont skal ha exit_trail_atr_mult med per-gruppe-multipliers.

    Boten faller tilbake til group_params.trail_atr i bot.yaml hvis denne
    nøkkelen mangler — vi vil heller eksplisitt diktere trail-distansen
    så MAKRO ikke blir klippet ut av en normal dagssving og SCALP ikke
    bruker den (for romslige) MAKRO-distansen.
    """
    expected_groups = {
        "fx",
        "indices",
        "gold",
        "silver",
        "platinum",
        "copper",
        "oil",
        "natgas",
        "crypto",
        "corn",
        "wheat",
        "soybean",
        "coffee",
        "cocoa",
        "sugar",
        "cotton",
    }
    for hor_in, hor_out in (("scalp", "SCALP"), ("swing", "SWING"), ("makro", "MAKRO")):
        payload = adapt_to_bot_format([_make_entry(horizon=hor_in)])
        sig = payload["signals"][0]
        trail_map = sig["horizon_config"]["exit_trail_atr_mult"]
        assert isinstance(trail_map, dict), f"{hor_out}: exit_trail_atr_mult mangler"
        assert set(trail_map.keys()) == expected_groups, (
            f"{hor_out}: forventet alle 16 grupper, fikk {sorted(trail_map.keys())}"
        )
        # Sanity: alle multipliers er positive floats i fornuftig spenn
        for grp, mult in trail_map.items():
            assert isinstance(mult, int | float)
            assert 1.5 <= mult <= 8.0, f"{hor_out}/{grp}: mult={mult} utenfor [1.5, 8.0]"


def test_trail_mult_widens_with_horizon():
    """MAKRO > SWING > SCALP for hver gruppe — bredere tese krever bredere trail."""
    payload_scalp = adapt_to_bot_format([_make_entry(horizon="scalp")])
    payload_swing = adapt_to_bot_format([_make_entry(horizon="swing")])
    payload_makro = adapt_to_bot_format([_make_entry(horizon="makro")])
    scalp_map = payload_scalp["signals"][0]["horizon_config"]["exit_trail_atr_mult"]
    swing_map = payload_swing["signals"][0]["horizon_config"]["exit_trail_atr_mult"]
    makro_map = payload_makro["signals"][0]["horizon_config"]["exit_trail_atr_mult"]
    for grp in scalp_map:
        assert scalp_map[grp] < swing_map[grp] < makro_map[grp], (
            f"{grp}: scalp={scalp_map[grp]} swing={swing_map[grp]} makro={makro_map[grp]} "
            f"bryter SCALP < SWING < MAKRO-prinsippet"
        )


def test_correlation_group_per_asset_class():
    cases = [
        ("fx", "fx"),
        ("metals", "metals"),
        ("energy", "energy"),
        ("indices", "indices"),
        ("crypto", "crypto"),
        ("grains", "grains"),
        ("softs", "softs"),
    ]
    for asset_class, expected in cases:
        payload = adapt_to_bot_format([_make_entry(asset_class=asset_class)])
        assert payload["signals"][0]["correlation_group"] == expected


def test_unknown_asset_class_falls_back_to_fx():
    payload = adapt_to_bot_format([_make_entry(asset_class="unknown")])
    assert payload["signals"][0]["correlation_group"] == "fx"


def test_missing_setup_skips_entry():
    entry = _make_entry()
    entry["setup"] = None
    payload = adapt_to_bot_format([entry])
    assert payload["n_published"] == 0


def test_missing_setup_inner_skips_entry():
    entry = _make_entry()
    entry["setup"]["setup"] = None
    payload = adapt_to_bot_format([entry])
    assert payload["n_published"] == 0


def test_non_dict_entries_skipped():
    payload = adapt_to_bot_format([None, "string", 42, _make_entry()])
    assert payload["n_published"] == 1


def test_schema_version_is_2_1():
    """Bot's SUPPORTED_SCHEMA_VERSIONS = {1.0, 2.0, 2.1}; output må matche."""
    payload = adapt_to_bot_format([])
    assert payload["schema_version"] == "2.1"


def test_valid_until_uses_provided_now():
    fixed = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    payload = adapt_to_bot_format([], now=fixed, valid_until_minutes=30)
    assert payload["valid_until"].startswith("2026-05-01T12:30:00")


def test_global_state_default_no_geo_risk():
    payload = adapt_to_bot_format([])
    gs = payload["global_state"]
    assert gs["geo_risk_active"] is False
    assert gs["vix_regime"] == "normal"
    assert "correlation_config" in gs


def test_global_state_can_be_overridden():
    custom = {"geo_risk_active": True, "vix_regime": "stress", "extra": 42}
    payload = adapt_to_bot_format([], global_state=custom)
    assert payload["global_state"] == custom


def test_rules_default_has_stop_multiplier():
    payload = adapt_to_bot_format([])
    assert payload["rules"]["stop_multiplier"] == 3.0


def test_setup_id_used_as_signal_id():
    payload = adapt_to_bot_format([_make_entry(setup_id="my-id-42")])
    assert payload["signals"][0]["id"] == "my-id-42"


def test_alert_level_is_inner_entry():
    payload = adapt_to_bot_format([_make_entry(entry=123.45)])
    assert payload["signals"][0]["alert_level"] == 123.45


def test_negative_entry_yields_zero_zone():
    """Defensive: negativ/null entry → tom zone, ikke crash."""
    payload = adapt_to_bot_format([_make_entry(entry=0.0)])
    assert payload["signals"][0]["entry_zone"] == [0.0, 0.0]
