"""Signal-fil I/O for signal-server.

Fase 7 sessions 34-35. Read + append. Atomic write via `.tmp + rename`
sørger for at en samtidig lesing enten ser forrige fil eller den nye —
aldri halvskrevet innhold.

Formatet på signals.json er en JSON-array av `PersistedSignal`-dicts.
Tomt array `[]` og manglende fil behandles likt (returnerer tom liste)
— praktisk default som unngår 500-er før noen signaler er generert.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from bedrock.signal_server.schemas import (
    KillSwitch,
    PersistedSignal,
    SignalStoreError,
)


def load_signals(path: Path) -> list[PersistedSignal]:
    """Les signals fra JSON-fil. Tom/manglende fil → `[]`.

    Ugyldig JSON eller ikke-liste-root: `SignalStoreError`.
    Enkelte rad som feiler Pydantic-validering: `SignalStoreError`
    med index + feilmelding.
    """
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SignalStoreError(f"kan ikke lese {path}: {exc}") from exc

    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SignalStoreError(
            f"{path} er ikke gyldig JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise SignalStoreError(
            f"{path} må ha en JSON-array som top-level element, "
            f"fikk {type(data).__name__}"
        )

    signals: list[PersistedSignal] = []
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            raise SignalStoreError(
                f"{path}[{idx}] må være objekt, fikk {type(row).__name__}"
            )
        try:
            signals.append(PersistedSignal.model_validate(row))
        except ValidationError as exc:
            raise SignalStoreError(
                f"{path}[{idx}] feiler validering: {exc}"
            ) from exc

    return signals


def _atomic_write_json(path: Path, payload: list[dict]) -> None:
    """Skriv JSON-liste til `path` atomisk (tmp + rename).

    Same-filesystem tmp-fil (viktig for at `rename` skal være atomisk
    på POSIX). Parent-dir opprettes ved behov. Partial write på feil
    rydder opp tmp-fila.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def append_signal(path: Path, signal: PersistedSignal) -> None:
    """Append ett signal til `path`. Atomic read-modify-write.

    Eksisterende innhold (hvis noe) lastes og valideres via
    `load_signals` først — korrupt fil fører til `SignalStoreError`
    slik at caller kan avvise oppdateringen heller enn å overskrive
    noen andres skadede data.

    Manglende fil opprettes. Parent-dir opprettes ved behov.
    """
    existing = load_signals(path)
    existing.append(signal)
    payload = [entry.model_dump(mode="json") for entry in existing]
    _atomic_write_json(path, payload)


# ---------------------------------------------------------------------------
# Kill-switch I/O
# ---------------------------------------------------------------------------


def load_kills(path: Path) -> list[KillSwitch]:
    """Les aktive kill-switches. Tom/manglende fil → `[]`.

    Samme feilsemantikk som `load_signals`: struktur-feil → SignalStoreError.
    """
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SignalStoreError(f"kan ikke lese {path}: {exc}") from exc

    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SignalStoreError(f"{path} er ikke gyldig JSON: {exc}") from exc

    if not isinstance(data, list):
        raise SignalStoreError(
            f"{path} må ha JSON-array som top-level, fikk {type(data).__name__}"
        )

    kills: list[KillSwitch] = []
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            raise SignalStoreError(
                f"{path}[{idx}] må være objekt, fikk {type(row).__name__}"
            )
        try:
            kills.append(KillSwitch.model_validate(row))
        except ValidationError as exc:
            raise SignalStoreError(
                f"{path}[{idx}] feiler validering: {exc}"
            ) from exc
    return kills


def upsert_kill(path: Path, kill: KillSwitch) -> None:
    """Legg til eller oppdater et kill. Dedupe på (instrument, horizon).

    Nyeste vinner: eksisterende entry på samme slot erstattes.
    """
    existing = load_kills(path)
    dedupe = {k.slot: k for k in existing}
    dedupe[kill.slot] = kill
    payload = [k.model_dump(mode="json") for k in dedupe.values()]
    _atomic_write_json(path, payload)


def clear_all_kills(path: Path) -> int:
    """Fjern alle kills. Returnerer antall som ble fjernet."""
    existing = load_kills(path)
    count = len(existing)
    _atomic_write_json(path, [])
    return count


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


def invalidate_matching(
    path: Path,
    *,
    instrument: str,
    direction: str,
    horizon: str,
    reason: str,
    now: str,
) -> int:
    """Marker matchende signaler i `path` som invalidated.

    Match: eksakt (instrument, direction, horizon). Setter felter
    `invalidated=True`, `invalidated_at=<now>`, `invalidated_reason=<reason>`
    på hver matchende entry via `model_dump` + dict-update (siden
    PersistedSignal har `extra='allow'`).

    Returnerer antall signaler som ble markert. 0 hvis ingen match.
    Tom/manglende fil → 0.
    """
    existing = load_signals(path)
    if not existing:
        return 0

    count = 0
    payload: list[dict] = []
    for entry in existing:
        dumped = entry.model_dump(mode="json")
        if (
            dumped["instrument"] == instrument
            and dumped["direction"] == direction
            and dumped["horizon"] == horizon
        ):
            dumped["invalidated"] = True
            dumped["invalidated_at"] = now
            dumped["invalidated_reason"] = reason
            count += 1
        payload.append(dumped)

    if count:
        _atomic_write_json(path, payload)
    return count
