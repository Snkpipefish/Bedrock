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
    # Fortsatt aktive fra observasjons-vinduet
    assert mapping.get("Copper") == "COPPER"
    assert mapping.get("NaturalGas") == "NATGAS"
    # Permanent disabled (session 2026-05-26): skal IKKE være i mapping —
    # PERMANENTLY_DISABLED-guarden filtrerer dem selv om YAML skulle
    # inneholde dem.
    assert mapping.get("BTC") is None
    assert mapping.get("ETH") is None
    assert mapping.get("Platinum") is None


# ─────────────────────────────────────────────────────────────
# Grade-gates (session 2026-06-11)
# ─────────────────────────────────────────────────────────────


def test_load_bot_gates_missing_section_returns_empty(tmp_path) -> None:
    """Manglende `gates:` → ingen gating (bakoverkompatibelt)."""
    from bedrock.cli.signals_all import _load_bot_gates

    wl = tmp_path / "wl.yaml"
    wl.write_text(yaml.safe_dump({"mapping": {"Gold": "GOLD"}}))
    gates = _load_bot_gates(wl)
    assert gates.min_grade_by_horizon == {}


def test_load_bot_gates_parses_and_normalizes(tmp_path) -> None:
    from bedrock.cli.signals_all import _load_bot_gates

    wl = tmp_path / "wl.yaml"
    wl.write_text(
        yaml.safe_dump(
            {
                "mapping": {"Gold": "GOLD"},
                "gates": {"min_grade_by_horizon": {"SCALP": "a", "swing": "B"}},
            }
        )
    )
    gates = _load_bot_gates(wl)
    assert gates.min_grade_by_horizon == {"scalp": "A", "swing": "B"}


def test_load_bot_gates_invalid_grade_raises(tmp_path) -> None:
    import click

    from bedrock.cli.signals_all import _load_bot_gates

    wl = tmp_path / "wl.yaml"
    wl.write_text(
        yaml.safe_dump(
            {
                "mapping": {"Gold": "GOLD"},
                "gates": {"min_grade_by_horizon": {"scalp": "S"}},
            }
        )
    )
    with pytest.raises(click.ClickException, match="ugyldig 'gates:'"):
        _load_bot_gates(wl)


def test_load_bot_gates_invalid_horizon_raises(tmp_path) -> None:
    import click

    from bedrock.cli.signals_all import _load_bot_gates

    wl = tmp_path / "wl.yaml"
    wl.write_text(
        yaml.safe_dump(
            {
                "mapping": {"Gold": "GOLD"},
                "gates": {"min_grade_by_horizon": {"intradag": "A"}},
            }
        )
    )
    with pytest.raises(click.ClickException, match="ugyldig 'gates:'"):
        _load_bot_gates(wl)


def test_passes_grade_gate_filters_below_minimum() -> None:
    from bedrock.cli.signals_all import BotGates, _passes_grade_gate

    gates = BotGates(min_grade_by_horizon={"scalp": "A", "swing": "B", "makro": "B"})

    # SCALP: kun A/A+ slipper gjennom
    assert _passes_grade_gate({"horizon": "scalp", "grade": "A+"}, gates)
    assert _passes_grade_gate({"horizon": "scalp", "grade": "A"}, gates)
    assert not _passes_grade_gate({"horizon": "scalp", "grade": "B"}, gates)
    assert not _passes_grade_gate({"horizon": "scalp", "grade": "C"}, gates)

    # SWING/MAKRO: B og bedre
    assert _passes_grade_gate({"horizon": "swing", "grade": "B"}, gates)
    assert not _passes_grade_gate({"horizon": "swing", "grade": "C"}, gates)
    assert _passes_grade_gate({"horizon": "makro", "grade": "A"}, gates)
    assert not _passes_grade_gate({"horizon": "makro", "grade": "C"}, gates)


def test_passes_grade_gate_unknown_grade_blocked() -> None:
    """Ukjent/manglende grade blokkeres når horisonten har minimum."""
    from bedrock.cli.signals_all import BotGates, _passes_grade_gate

    gates = BotGates(min_grade_by_horizon={"swing": "B"})
    assert not _passes_grade_gate({"horizon": "swing", "grade": None}, gates)
    assert not _passes_grade_gate({"horizon": "swing"}, gates)
    assert not _passes_grade_gate({"horizon": "swing", "grade": "X"}, gates)


def test_passes_grade_gate_unlisted_horizon_passes() -> None:
    from bedrock.cli.signals_all import BotGates, _passes_grade_gate

    gates = BotGates(min_grade_by_horizon={"scalp": "A"})
    assert _passes_grade_gate({"horizon": "swing", "grade": "C"}, gates)


def test_repo_whitelist_yaml_gates_are_valid() -> None:
    """Den faktiske bot_whitelist.yaml skal ha gyldige gates (A/B/B)."""
    from pathlib import Path

    from bedrock.cli.signals_all import _load_bot_gates

    repo_wl = Path("config/bot_whitelist.yaml")
    if not repo_wl.exists():
        pytest.skip("config/bot_whitelist.yaml mangler i denne kjøringen")

    gates = _load_bot_gates(repo_wl)
    assert gates.min_grade_by_horizon == {"scalp": "A", "swing": "B", "makro": "B"}
