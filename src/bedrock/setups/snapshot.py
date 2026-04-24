"""Snapshot-I/O for setup-generator.

Skriver/leser `SetupSnapshot` til/fra JSON på disk. Default-sti er
`data/setups/last_run.json` (matcher PLAN § 5.4). Ingen lifecycle-state
lagres — bare forrige kjørings-tilstand som referanse for hysterese.

JSON er valgt fremfor pickle/parquet fordi:
- Menneskelesbart (kan inspiseres ved debugging)
- Versjon-safe (Pydantic v2 håndterer schema-migrering)
- Null binær-avhengighet (passer med SQLite-valget, se ADR-002)

Fil-formatet er `SetupSnapshot.model_dump_json()`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from bedrock.setups.hysteresis import SetupSnapshot

_log = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_PATH = Path("data/setups/last_run.json")


def load_snapshot(path: Path | None = None) -> SetupSnapshot | None:
    """Les snapshot fra JSON. Returnerer `None` hvis fila ikke finnes.

    Brukes ved oppstart av en pipeline-kjøring. `None` er forventet ved
    første gang; caller behandler det som "ingen tidligere historikk".

    Malformert JSON kaster `pydantic.ValidationError` (videresender
    Pydantics egen feil — ikke wrap'et, slik at caller ser hva som er
    feil).
    """
    target = path if path is not None else DEFAULT_SNAPSHOT_PATH
    if not target.exists():
        _log.debug("load_snapshot: no snapshot at %s", target)
        return None

    raw = target.read_text(encoding="utf-8")
    return SetupSnapshot.model_validate_json(raw)


def save_snapshot(snapshot: SetupSnapshot, path: Path | None = None) -> Path:
    """Skriv snapshot atomisk (write-to-temp + rename) til `path`.

    Atomic write hindrer at pipeline leser en halvskrevet fil hvis
    prosessen drepes mid-write. Oppretter parent-dir ved behov.

    Returnerer fullpath-en som ble skrevet.
    """
    target = path if path is not None else DEFAULT_SNAPSHOT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(target)  # atomisk på POSIX

    _log.info("save_snapshot: wrote %d setups to %s", len(snapshot.setups), target)
    return target
