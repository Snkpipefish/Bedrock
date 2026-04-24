"""Read-endepunkter for signaler.

Fase 7 session 34 — `/signals` (financial) og `/agri-signals` (agri).
Skriv-path kommer i session 35 (`/push-alert`).

Kontrakt:

- Returnerer JSON-liste av persisterte signaler
- Tom fil / manglende fil → `[]` + 200
- Korrupt fil (ugyldig JSON, feil struktur, feilet validering) →
  `{"error": "..."}` + 500. Dette er bevisst en hard feil:
  konsumerende UI bør vite at serveren har et data-problem heller
  enn å vise tom liste og lure brukeren

Filene bestemmes av `ServerConfig.signals_path` og
`agri_signals_path`. Flask-config kan overstyres i test.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import SignalStoreError
from bedrock.signal_server.storage import load_signals

signals_bp = Blueprint("signals", __name__)


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


@signals_bp.get("/signals")
def get_signals() -> tuple[object, int]:
    cfg = _get_config()
    try:
        entries = load_signals(cfg.signals_path)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify([entry.model_dump(mode="json") for entry in entries]), 200


@signals_bp.get("/agri-signals")
def get_agri_signals() -> tuple[object, int]:
    cfg = _get_config()
    try:
        entries = load_signals(cfg.agri_signals_path)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify([entry.model_dump(mode="json") for entry in entries]), 200
