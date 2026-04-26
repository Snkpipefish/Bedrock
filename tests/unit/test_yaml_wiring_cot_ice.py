"""Tester at cot_ice_mm_pct er wiret i Brent + NaturalGas YAML
(sub-fase 12.5+ session 106)."""

from __future__ import annotations

import pytest

from bedrock.config.instruments import load_all_instruments


@pytest.fixture(scope="module")
def configs():
    return load_all_instruments("config/instruments")


# ---------------------------------------------------------------------------
# Brent: ICE er primær (CFTC mini-Brent kun cross-validering via cot_z_score)
# ---------------------------------------------------------------------------


def test_brent_positioning_uses_cot_ice_mm_pct(configs) -> None:
    pos = configs["Brent"].rules.families["positioning"]
    names = [d.name for d in pos.drivers]
    assert "cot_ice_mm_pct" in names
    # positioning_mm_pct (CFTC) ble erstattet av cot_ice_mm_pct
    assert "positioning_mm_pct" not in names


def test_brent_cot_ice_mm_pct_targets_brent_contract(configs) -> None:
    pos = configs["Brent"].rules.families["positioning"]
    ice = next(d for d in pos.drivers if d.name == "cot_ice_mm_pct")
    assert ice.params["contract"] == "ice brent crude"
    assert ice.params["metric"] == "mm_net_pct"


def test_brent_keeps_cot_z_score_as_cross_validation(configs) -> None:
    """CFTC's cot_z_score beholdes som cross-validering selv om Brent
    primært handles på ICE."""
    pos = configs["Brent"].rules.families["positioning"]
    names = [d.name for d in pos.drivers]
    assert "cot_z_score" in names


def test_brent_positioning_weights_sum_to_one(configs) -> None:
    pos = configs["Brent"].rules.families["positioning"]
    total = sum(d.weight for d in pos.drivers)
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# NaturalGas: 0.7 CFTC / 0.3 ICE-TTF
# ---------------------------------------------------------------------------


def test_naturalgas_positioning_has_all_three_drivers(configs) -> None:
    pos = configs["NaturalGas"].rules.families["positioning"]
    names = [d.name for d in pos.drivers]
    assert sorted(names) == sorted(["positioning_mm_pct", "cot_z_score", "cot_ice_mm_pct"])


def test_naturalgas_cot_ice_targets_ttf_gas(configs) -> None:
    pos = configs["NaturalGas"].rules.families["positioning"]
    ice = next(d for d in pos.drivers if d.name == "cot_ice_mm_pct")
    assert ice.params["contract"] == "ice ttf gas"


def test_naturalgas_split_is_70_cftc_30_ttf(configs) -> None:
    """Vekt-split: 0.42 (positioning_mm_pct) + 0.28 (cot_z_score) = 0.7
    CFTC-side. cot_ice_mm_pct = 0.3 TTF-side."""
    pos = configs["NaturalGas"].rules.families["positioning"]
    cftc_total = sum(
        d.weight for d in pos.drivers if d.name in ("positioning_mm_pct", "cot_z_score")
    )
    ice_total = sum(d.weight for d in pos.drivers if d.name == "cot_ice_mm_pct")
    assert abs(cftc_total - 0.7) < 1e-9
    assert abs(ice_total - 0.3) < 1e-9


def test_naturalgas_positioning_weights_sum_to_one(configs) -> None:
    pos = configs["NaturalGas"].rules.families["positioning"]
    total = sum(d.weight for d in pos.drivers)
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Sanity: andre instrumenter er IKKE wiret med cot_ice (ingen leak)
# ---------------------------------------------------------------------------


def test_other_instruments_not_using_cot_ice(configs) -> None:
    """Kun Brent + NaturalGas skal bruke cot_ice_mm_pct i session 106."""
    using_ice: list[str] = []
    for inst_id, cfg in configs.items():
        for fam_name, fam in cfg.rules.families.items():
            for d in fam.drivers:
                if d.name == "cot_ice_mm_pct":
                    using_ice.append(f"{inst_id}/{fam_name}")
    assert sorted({s.split("/")[0] for s in using_ice}) == ["Brent", "NaturalGas"]
