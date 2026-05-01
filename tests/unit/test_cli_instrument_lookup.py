"""Tester for `bedrock.cli._instrument_lookup`.

Sub-fase 12.9 D5+ Fase 2: profilering viste at `find_instrument` ble
kalt 24x for ett `signals-all`-instrument og hver kall lastet 22 YAMLer
fra disk → 70+ sek/instrument. lru_cache på `_load_all_cached`
reduserte signals-all 8m19s → 1m16s (6.5x).

Disse testene er regresjons-vakter for cachet:
- find_instrument returnerer riktig cfg
- Gjentatte kall hopper YAML-load (cache-hit)
- clear_instrument_cache() resetter
- Forskjellig (instruments_dir, defaults_dir) → separate cache-entries
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bedrock.cli._instrument_lookup import (
    _load_all_cached,
    clear_instrument_cache,
    find_instrument,
)

_REAL_YAML = Path("config/instruments/gold.yaml")
_REAL_DEFAULTS = Path("config/defaults")


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    clear_instrument_cache()
    yield
    clear_instrument_cache()


def _write_minimal_instrument(yaml_path: Path, instrument_id: str) -> None:
    """Kopier real gold.yaml + bytt id-felt for å gjenbruke Pydantic-
    validert struktur uten å vedlikeholde inline minimal-YAML.
    """
    if not _REAL_YAML.exists():
        pytest.skip(f"{_REAL_YAML} mangler — kjør fra repo-rot")
    text = _REAL_YAML.read_text()
    # Bytt 'id: Gold' til 'id: <instrument_id>' (case-insensitive
    # match for å treffe begge varianter)
    text = text.replace("id: Gold", f"id: {instrument_id}", 1)
    yaml_path.write_text(text)


def test_find_instrument_basic(tmp_path: Path) -> None:
    """Eksakt match returnerer riktig config."""
    instruments = tmp_path / "instruments"
    instruments.mkdir()
    _write_minimal_instrument(instruments / "gold.yaml", "Gold")
    cfg = find_instrument("Gold", instruments, defaults_dir=_REAL_DEFAULTS)
    assert cfg.instrument.id == "Gold"


def test_find_instrument_case_insensitive(tmp_path: Path) -> None:
    instruments = tmp_path / "instruments"
    instruments.mkdir()
    _write_minimal_instrument(instruments / "gold.yaml", "Gold")
    cfg = find_instrument("gold", instruments, defaults_dir=_REAL_DEFAULTS)
    assert cfg.instrument.id == "Gold"


def test_find_instrument_caches_yaml_loads(tmp_path: Path) -> None:
    """2. kall til samme dir skal ikke trigge ny YAML-load."""
    instruments = tmp_path / "instruments"
    instruments.mkdir()
    _write_minimal_instrument(instruments / "gold.yaml", "Gold")
    _write_minimal_instrument(instruments / "silver.yaml", "Silver")

    info_pre = _load_all_cached.cache_info()
    find_instrument("Gold", instruments, defaults_dir=_REAL_DEFAULTS)
    info_after_first = _load_all_cached.cache_info()
    assert info_after_first.misses == info_pre.misses + 1

    find_instrument("Silver", instruments, defaults_dir=_REAL_DEFAULTS)
    info_after_second = _load_all_cached.cache_info()
    # Andre kall til samme dir → cache hit, ikke ny miss.
    assert info_after_second.misses == info_after_first.misses
    assert info_after_second.hits == info_after_first.hits + 1


def test_find_instrument_different_dirs_separate_cache(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    _write_minimal_instrument(dir_a / "gold.yaml", "Gold")

    dir_b = tmp_path / "b"
    dir_b.mkdir()
    _write_minimal_instrument(dir_b / "gold.yaml", "Gold")

    find_instrument("Gold", dir_a, defaults_dir=_REAL_DEFAULTS)
    info_after_a = _load_all_cached.cache_info()
    find_instrument("Gold", dir_b, defaults_dir=_REAL_DEFAULTS)
    info_after_b = _load_all_cached.cache_info()
    # Ulik dir → ny miss, ikke shared cache.
    assert info_after_b.misses == info_after_a.misses + 1


def test_clear_instrument_cache_resets(tmp_path: Path) -> None:
    instruments = tmp_path / "instruments"
    instruments.mkdir()
    _write_minimal_instrument(instruments / "gold.yaml", "Gold")
    find_instrument("Gold", instruments, defaults_dir=_REAL_DEFAULTS)
    assert _load_all_cached.cache_info().currsize >= 1

    clear_instrument_cache()
    assert _load_all_cached.cache_info().currsize == 0


def test_find_instrument_unknown_raises(tmp_path: Path) -> None:
    import click

    instruments = tmp_path / "instruments"
    instruments.mkdir()
    _write_minimal_instrument(instruments / "gold.yaml", "Gold")
    with pytest.raises(click.UsageError, match="Ukjent instrument"):
        find_instrument("Bogus", instruments, defaults_dir=_REAL_DEFAULTS)
