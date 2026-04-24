"""Skriv-endepunkter for signaler.

Fase 7 session 35 — `/push-alert` (financial) og `/push-agri-alert`
(agri). Pydantic-valideres innkommende body, atomic-append til
konfigurert fil.

Status-koder:

- 201 ved vellykket append (ny ressurs opprettet)
- 400 ved valideringsfeil (med feildetaljer)
- 500 hvis fil er korrupt og append derfor umulig (caller bør ikke
  overskrive fil noen annen har skadet)
- 415 hvis Content-Type ikke er application/json
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    PersistedSignal,
    SignalStoreError,
)
from bedrock.signal_server.storage import append_signal

alerts_bp = Blueprint("alerts", __name__)


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _parse_and_append(path: Path) -> tuple[object, int]:
    """Felles flyt for push-alert og push-agri-alert."""
    if not request.is_json:
        return (
            jsonify({"error": "Content-Type må være application/json"}),
            415,
        )

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "body må være gyldig JSON"}), 400
    if not isinstance(payload, dict):
        return (
            jsonify({"error": "body må være et JSON-objekt"}),
            400,
        )

    try:
        signal = PersistedSignal.model_validate(payload)
    except ValidationError as exc:
        # `include_context=False` ekskluderer exception-instanser (ValueError
        # osv.) som ikke er JSON-serialiserbare — vi trenger kun lokalisert
        # feilbeskrivelse til klienten.
        return (
            jsonify(
                {
                    "error": "validering feilet",
                    "details": exc.errors(include_context=False),
                }
            ),
            400,
        )

    try:
        append_signal(path, signal)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(signal.model_dump(mode="json")), 201


@alerts_bp.post("/push-alert")
def push_alert() -> tuple[object, int]:
    return _parse_and_append(_get_config().signals_path)


@alerts_bp.post("/push-agri-alert")
def push_agri_alert() -> tuple[object, int]:
    return _parse_and_append(_get_config().agri_signals_path)
