"""Tester for asset-class splitt i `bedrock signals-all` (session 94)."""

from __future__ import annotations

from pathlib import Path

import yaml

from bedrock.cli.signals_all import _AGRI_ASSET_CLASSES, _read_asset_class


def test_agri_asset_classes_includes_grains_and_softs() -> None:
    assert "grains" in _AGRI_ASSET_CLASSES
    assert "softs" in _AGRI_ASSET_CLASSES
    # Financial-kategorier skal IKKE være i agri
    assert "fx" not in _AGRI_ASSET_CLASSES
    assert "metals" not in _AGRI_ASSET_CLASSES
    assert "energy" not in _AGRI_ASSET_CLASSES
    assert "indices" not in _AGRI_ASSET_CLASSES
    assert "crypto" not in _AGRI_ASSET_CLASSES


def test_read_asset_class_reads_grains(tmp_path: Path) -> None:
    yaml_path = tmp_path / "wheat.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {"instrument": {"id": "Wheat", "asset_class": "grains"}, "aggregation": "additive_sum"}
        )
    )
    assert _read_asset_class(yaml_path) == "grains"


def test_read_asset_class_reads_metals(tmp_path: Path) -> None:
    yaml_path = tmp_path / "gold.yaml"
    yaml_path.write_text(yaml.safe_dump({"instrument": {"id": "Gold", "asset_class": "metals"}}))
    assert _read_asset_class(yaml_path) == "metals"


def test_read_asset_class_returns_none_when_missing(tmp_path: Path) -> None:
    yaml_path = tmp_path / "broken.yaml"
    yaml_path.write_text(yaml.safe_dump({"instrument": {"id": "Foo"}}))
    assert _read_asset_class(yaml_path) is None


def test_read_asset_class_returns_none_for_invalid_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("this is: not: valid: yaml: ::")
    assert _read_asset_class(yaml_path) is None


def test_read_asset_class_returns_none_for_missing_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "missing.yaml"
    assert _read_asset_class(yaml_path) is None


def test_read_asset_class_repo_yamls_match_expected() -> None:
    """Verifiser at repo's faktiske YAMLer har forventet asset_class."""
    instruments_dir = Path("config/instruments")
    if not instruments_dir.exists():
        import pytest

        pytest.skip("config/instruments mangler i denne kjøringen")

    expected = {
        "wheat": "grains",
        "corn": "grains",
        "soybean": "grains",
        "cotton": "softs",
        "coffee": "softs",
        "sugar": "softs",
        "cocoa": "softs",
        "gold": "metals",
        "silver": "metals",
        "crudeoil": "energy",
        "brent": "energy",
        "eurusd": "fx",
        "btc": "crypto",
    }
    for stem, expected_class in expected.items():
        path = instruments_dir / f"{stem}.yaml"
        if path.exists():
            assert _read_asset_class(path) == expected_class, f"{stem} har feil asset_class"
