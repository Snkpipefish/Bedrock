"""Felles hjelpere for CLI-kommandoer som slår opp instrument-config.

Fase 5 session 22: `bedrock backfill *` og `bedrock instruments *` slår
opp `config/instruments/<id>.yaml` for å pre-populate CLI-argumenter.

Design:

- **Case-insensitive lookup**: `--instrument gold` matcher
  `instruments/gold.yaml` selv om `instrument.id: Gold`. Returnerer alltid
  konfigen med ID som YAML-filen spesifiserer (kanonisk form).
- **`click.UsageError` ved manglende/ukjent**: CLI-lag skal vise tydelig
  feil istedenfor tracebacks.
- **Cachet per (instruments_dir, defaults_dir)**: lru_cache på
  `_load_all_cached` slik at gjentatte oppslag i samme prosess (typisk:
  drivere som slår opp cross-asset-config under signals-all) ikke
  trigger 22 YAML-loads per kall. Sub-fase 12.9 D5+ profilering viste
  at `find_instrument` ble kalt 24x for ett `signals-all`-instrument
  uten cache, og hver kall lastet alle 22 YAMLer → 70+ sek/instrument
  bare i YAML-parsing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import click

from bedrock.config.instruments import (
    DEFAULT_DEFAULTS_DIR,
    InstrumentConfig,
    InstrumentConfigError,
    load_all_instruments,
)

DEFAULT_INSTRUMENTS_DIR = Path("config/instruments")


@lru_cache(maxsize=8)
def _load_all_cached(
    instruments_dir: Path,
    defaults_dir: Path | None,
) -> dict[str, InstrumentConfig]:
    """LRU-cachet wrapper over `load_all_instruments`.

    Cache-nøkkel er (Path, Path|None) — begge hashable. maxsize=8
    håndterer typisk én produksjonsmappe + 7 test-tmp-paths uten
    leak. Pydantic-modeller er frozen → trygt å returnere shared
    referanser til samme cfg-objekt fra flere kall.
    """
    return load_all_instruments(instruments_dir, defaults_dir=defaults_dir)


def find_instrument(
    instrument_id: str,
    instruments_dir: Path | str = DEFAULT_INSTRUMENTS_DIR,
    defaults_dir: Path | str | None = None,
) -> InstrumentConfig:
    """Slå opp instrument-config etter ID.

    Prøver først eksakt match, så case-insensitive. Reiser
    `click.UsageError` hvis ingen match eller katalogen mangler.

    `defaults_dir` propages til `load_all_instruments` for `inherits`-
    resolution. Default: `config/defaults/`.
    """
    target_dir = Path(instruments_dir)
    if not target_dir.exists():
        raise click.UsageError(
            f"Instruments directory not found: {target_dir}. "
            f"Opprett config/instruments/<id>.yaml eller bruk --instruments-dir."
        )

    defaults_path = Path(defaults_dir) if defaults_dir is not None else None

    try:
        all_configs = _load_all_cached(target_dir, defaults_path)
    except InstrumentConfigError as exc:
        raise click.UsageError(f"Kunne ikke laste instrument-config: {exc}") from exc

    # Eksakt match
    if instrument_id in all_configs:
        return all_configs[instrument_id]

    # Case-insensitive fallback
    lower_target = instrument_id.lower()
    for inst_id, cfg in all_configs.items():
        if inst_id.lower() == lower_target:
            return cfg

    available = sorted(all_configs.keys())
    raise click.UsageError(
        f"Ukjent instrument {instrument_id!r}. "
        f"Tilgjengelige: {available}. "
        f"Legg til {target_dir}/{instrument_id.lower()}.yaml eller bruk eksplisitte args."
    )


def clear_instrument_cache() -> None:
    """Tøm find_instrument-cachet. Brukes i tester etter YAML-mutasjon."""
    _load_all_cached.cache_clear()


__all__ = [
    "DEFAULT_DEFAULTS_DIR",
    "DEFAULT_INSTRUMENTS_DIR",
    "clear_instrument_cache",
    "find_instrument",
]
