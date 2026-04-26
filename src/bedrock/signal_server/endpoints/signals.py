# pyright: reportArgumentType=false
# Flask `T_route` rejects tuple[object, int] even for valid (jsonify, status)
# responses. Same pattern across alle signal_server/endpoints/*.

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

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    InvalidationRequest,
    SignalStoreError,
)
from bedrock.signal_server.storage import (
    invalidate_matching,
    load_signals,
)

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


@signals_bp.post("/invalidate")
def invalidate() -> tuple[object, int]:
    """Marker matchende signaler i begge fil-settene som invalidated.

    Body: `{instrument, direction, horizon, reason?}`. Sjekker BÅDE
    signals.json og agri_signals.json — orchestrator vet hvilken
    fil signalet ligger i, men klienten trenger ikke vite det.
    Returnerer telling per fil.
    """
    if not request.is_json:
        return (
            jsonify({"error": "Content-Type må være application/json"}),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "body må være gyldig JSON"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "body må være et JSON-objekt"}), 400

    try:
        req = InvalidationRequest.model_validate(payload)
    except ValidationError as exc:
        return (
            jsonify(
                {
                    "error": "validering feilet",
                    "details": exc.errors(include_context=False),
                }
            ),
            400,
        )

    cfg = _get_config()
    now = datetime.utcnow().isoformat()

    try:
        financial_count = invalidate_matching(
            cfg.signals_path,
            instrument=req.instrument,
            direction=req.direction,
            horizon=req.horizon,
            reason=req.reason,
            now=now,
        )
        agri_count = invalidate_matching(
            cfg.agri_signals_path,
            instrument=req.instrument,
            direction=req.direction,
            horizon=req.horizon,
            reason=req.reason,
            now=now,
        )
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500

    return (
        jsonify(
            {
                "financial_matched": financial_count,
                "agri_matched": agri_count,
                "total": financial_count + agri_count,
            }
        ),
        200,
    )
