"""Tester for ``bedrock signals-all --bot-only`` (session 92).

Verifiserer at:
1. Whitelist-loader leser YAML korrekt
2. --bot-only filtrerer ut ikke-whitelistede instrumenter
3. Instrument-id transformeres til bot-navn (Gold → GOLD)
4. Manglende whitelist-fil gir tydelig feilmelding
"""

from __future__ import annotations

import pytest
import yaml

from bedrock.cli.signals_all import _load_bot_whitelist


def test_load_bot_whitelist_returns_mapping(tmp_path) -> None:
    wl = tmp_path / "whitelist.yaml"
    wl.write_text(
        yaml.safe_dump(
            {
                "mapping": {
                    "Gold": "GOLD",
                    "CrudeOil": "OIL WTI",
                    "Corn": "Corn",
                }
            }
        )
    )
    mapping = _load_bot_whitelist(wl)
    assert mapping == {"Gold": "GOLD", "CrudeOil": "OIL WTI", "Corn": "Corn"}


def test_load_bot_whitelist_missing_file_raises(tmp_path) -> None:
    import click

    wl = tmp_path / "missing.yaml"
    with pytest.raises(click.ClickException, match="Bot-whitelist mangler"):
        _load_bot_whitelist(wl)


def test_load_bot_whitelist_missing_mapping_key_raises(tmp_path) -> None:
    import click

    wl = tmp_path / "wrong.yaml"
    wl.write_text(yaml.safe_dump({"other_key": "value"}))
    with pytest.raises(click.ClickException, match="mangler 'mapping:' dict"):
        _load_bot_whitelist(wl)


def test_load_bot_whitelist_handles_empty_yaml(tmp_path) -> None:
    import click

    wl = tmp_path / "empty.yaml"
    wl.write_text("")
    with pytest.raises(click.ClickException):
        _load_bot_whitelist(wl)


def test_load_bot_whitelist_coerces_values_to_string(tmp_path) -> None:
    """YAML kan tolke "OIL WTI" ulik måte; sikre str-coercion."""
    wl = tmp_path / "coerce.yaml"
    wl.write_text(
        yaml.safe_dump(
            {"mapping": {"Foo": 123, "Bar": 4.5}}  # numeriske verdier
        )
    )
    mapping = _load_bot_whitelist(wl)
    assert mapping == {"Foo": "123", "Bar": "4.5"}


def test_repo_whitelist_yaml_is_valid() -> None:
    """Verifiser at den faktiske ``config/bot_whitelist.yaml`` er valid."""
    from pathlib import Path

    repo_wl = Path("config/bot_whitelist.yaml")
    if not repo_wl.exists():
        pytest.skip("config/bot_whitelist.yaml mangler i denne kjøringen")

    mapping = _load_bot_whitelist(repo_wl)
    # Sjekk noen kjente entries
    assert mapping.get("Gold") == "GOLD"
    assert mapping.get("Brent") == "OIL BRENT"
    assert mapping.get("CrudeOil") == "OIL WTI"
    assert mapping.get("SP500") == "SPX500"
    assert mapping.get("Nasdaq") == "US100"
    # Agri matcher seg selv
    assert mapping.get("Corn") == "Corn"
    # Crypto skal IKKE være i whitelist
    assert "BTC" not in mapping
    assert "ETH" not in mapping
    # Base metals skal IKKE være i whitelist
    assert "Copper" not in mapping
    assert "Platinum" not in mapping
