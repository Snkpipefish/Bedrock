"""Tester for scripts/backtest_phase_d_session116.py.

Dekker:
- _direction_aware_hit (BUY/SELL hit-semantikk)
- _zero_driver_in_yaml (YAML-mutering for spike-mode)
- _build_spike_instruments_dir (full kopi + zero-out + impact-detektering)
- Sanity: hvis baseline-JSON finnes, Gold 30d BUY-hit > 30% (matcher
  session 99-tall — ikke 50% per opprinnelig brief, fordi session 99
  rapporterte 34.5% for Gold 30d BUY, ikke 100%. Beskytter mot regresjon
  i analog_outcomes-tabellen).
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "backtest_phase_d_session116.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("phase_d_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase_d_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


# ---------------------------------------------------------------------
# Direction-aware hit
# ---------------------------------------------------------------------


def test_buy_hit_above_positive_threshold(script) -> None:
    assert script._direction_aware_hit(5.0, 3.0, "buy") is True
    assert script._direction_aware_hit(2.5, 3.0, "buy") is False


def test_sell_hit_below_negative_threshold(script) -> None:
    assert script._direction_aware_hit(-5.0, 3.0, "sell") is True
    assert script._direction_aware_hit(-2.5, 3.0, "sell") is False


def test_sell_hit_with_positive_return_is_miss(script) -> None:
    """SELL skal kun hits hvis forward_return ≤ -terskel."""
    assert script._direction_aware_hit(5.0, 3.0, "sell") is False


def test_buy_hit_with_negative_return_is_miss(script) -> None:
    assert script._direction_aware_hit(-5.0, 3.0, "buy") is False


# ---------------------------------------------------------------------
# YAML-mutering for spike-mode
# ---------------------------------------------------------------------


def test_zero_driver_in_yaml_zeroes_named_driver(script, tmp_path: Path) -> None:
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "instrument": {"id": "Test"},
                "families": {
                    "trend": {
                        "drivers": [
                            {"name": "sma200_align", "weight": 0.5},
                            {"name": "event_distance", "weight": 0.3},
                        ],
                    },
                    "risk": {
                        "drivers": [
                            {"name": "event_distance", "weight": 0.4},
                        ],
                    },
                },
            }
        )
    )
    n = script._zero_driver_in_yaml(yaml_path, "event_distance")
    assert n == 2

    # Re-les og verifiser
    data = yaml.safe_load(yaml_path.read_text())
    assert data["families"]["trend"]["drivers"][0]["weight"] == 0.5
    assert data["families"]["trend"]["drivers"][1]["weight"] == 0.0
    assert data["families"]["risk"]["drivers"][0]["weight"] == 0.0


def test_zero_driver_in_yaml_no_match_is_noop(script, tmp_path: Path) -> None:
    yaml_path = tmp_path / "test.yaml"
    original_content = yaml.safe_dump(
        {
            "instrument": {"id": "Test"},
            "families": {
                "trend": {
                    "drivers": [{"name": "sma200_align", "weight": 0.5}],
                }
            },
        }
    )
    yaml_path.write_text(original_content)
    n = script._zero_driver_in_yaml(yaml_path, "event_distance")
    assert n == 0


def test_build_spike_instruments_dir_copies_and_zeros(script, tmp_path: Path) -> None:
    src = tmp_path / "src_yamls"
    dst_root = tmp_path / "dst"
    src.mkdir()

    # Lag tre instrument-YAMLs: én bruker driveren, to gjør ikke
    (src / "alpha.yaml").write_text(
        yaml.safe_dump(
            {
                "instrument": {"id": "Alpha"},
                "families": {
                    "trend": {
                        "drivers": [{"name": "event_distance", "weight": 0.3}],
                    }
                },
            }
        )
    )
    (src / "beta.yaml").write_text(
        yaml.safe_dump(
            {
                "instrument": {"id": "Beta"},
                "families": {
                    "trend": {"drivers": [{"name": "sma200_align", "weight": 0.5}]},
                },
            }
        )
    )
    (src / "gamma.yaml").write_text(
        yaml.safe_dump(
            {
                "instrument": {"id": "Gamma"},
                "families": {
                    "trend": {"drivers": [{"name": "sma200_align", "weight": 0.5}]},
                    "risk": {
                        "drivers": [{"name": "event_distance", "weight": 0.4}],
                    },
                },
            }
        )
    )

    spike_dir, impacted = script._build_spike_instruments_dir(src, "event_distance", dst_root)
    assert spike_dir.exists()
    assert sorted(impacted) == ["Alpha", "Gamma"]

    # Alpha: vekt skal være 0 i kopi, men 0.3 i original
    alpha_copy = yaml.safe_load((spike_dir / "alpha.yaml").read_text())
    alpha_orig = yaml.safe_load((src / "alpha.yaml").read_text())
    assert alpha_copy["families"]["trend"]["drivers"][0]["weight"] == 0.0
    assert alpha_orig["families"]["trend"]["drivers"][0]["weight"] == 0.3


# ---------------------------------------------------------------------
# Sanity-test mot session 99-baseline (Gold 30d BUY hit-rate)
# ---------------------------------------------------------------------


def test_baseline_gold_30d_buy_matches_session99() -> None:
    """Verifiser at baseline-JSON (om generert) reproducerer session 99
    Gold 30d BUY hit-rate (~34.5%). Beskytter mot regresjon i
    `analog_outcomes`-tabellen.

    Hopper testen hvis baseline-JSON ikke finnes (lokal dev-miljø før
    første kjøring).
    """
    baseline_path = REPO_ROOT / "data" / "_meta" / "backtest_phase_d_baseline.json"
    if not baseline_path.exists():
        pytest.skip(f"Baseline-JSON mangler ({baseline_path}); kjør --mode baseline først")

    payload = json.loads(baseline_path.read_text())
    rows = payload.get("rows", [])
    gold_30d_buy = next(
        (
            r
            for r in rows
            if r["instrument"] == "Gold"
            and int(r["horizon_days"]) == 30
            and r["direction"] == "buy"
        ),
        None,
    )
    assert gold_30d_buy is not None, "Gold 30d BUY mangler i baseline-output"
    hit = gold_30d_buy["hit_rate_pct"]
    assert hit is not None
    # Session 99 rapporterte 34.5%. Tillat ±2pp slack pga rounding/data-mikro-endringer.
    assert 32.0 <= hit <= 37.0, f"Gold 30d BUY hit-rate {hit:.1f}% utenfor session 99-baseline ±2pp"
