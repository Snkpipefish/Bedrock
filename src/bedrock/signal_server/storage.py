"""Signal-fil I/O for signal-server.

Fase 7 session 34 — read-only støtte. Atomic write kommer når skriv-
endepunkter legges til (session 35 / /push-alert).

Formatet på signals.json er en JSON-array av `PersistedSignal`-dicts.
Tomt array `[]` og manglende fil behandles likt (returnerer tom liste)
— praktisk default som unngår 500-er før noen signaler er generert.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from bedrock.signal_server.schemas import (
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
