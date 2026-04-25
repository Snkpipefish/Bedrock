"""Felles hjelpere for CLI-kommandoer som slår opp instrument-config.

Fase 5 session 22: `bedrock backfill *` og `bedrock instruments *` slår
opp `config/instruments/<id>.yaml` for å pre-populate CLI-argumenter.

Design:

- **Case-insensitive lookup**: `--instrument gold` matcher
  `instruments/gold.yaml` selv om `instrument.id: Gold`. Returnerer alltid
  konfigen med ID som YAML-filen spesifiserer (kanonisk form).
- **`click.UsageError` ved manglende/ukjent**: CLI-lag skal vise tydelig
  feil istedenfor tracebacks.
- **Cachet i én CLI-invokasjon**: `load_all_instruments` kjøres én gang
  per `find_instrument`-kall; for flere oppslag i samme kommando er det
  bedre å kalle `load_all_instruments` selv.
"""

from __future__ import annotations

from pathlib import Path

import click

from bedrock.config.instruments import (
    DEFAULT_DEFAULTS_DIR,
    InstrumentConfig,
    InstrumentConfigError,
    load_all_instruments,
)

DEFAULT_INSTRUMENTS_DIR = Path("config/instruments")


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

    try:
        all_configs = load_all_instruments(target_dir, defaults_dir=defaults_dir)
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


__all__ = ["DEFAULT_DEFAULTS_DIR", "DEFAULT_INSTRUMENTS_DIR", "find_instrument"]
