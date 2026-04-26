# pyright: reportArgumentType=false
# Flask `T_route` rejects tuple[object, int] even for valid (jsonify, status)
# responses. Same pattern across alle signal_server/endpoints/*.

"""Kill-switch endepunkter.

Fase 7 session 36:
- `POST /kill` — legg til (eller oppdater) kill-switch på
  (instrument, horizon). Mens denne eksisterer, ignorerer bot alle
  signaler på den slotten.
- `POST /clear_kills` — tøm alle kills.
- `GET /kills` — les alle aktive kills (for UI-synlighet).

Idempotens: to `/kill`-kall med samme (instrument, horizon) produserer
kun én entry — det nyeste `reason` og `killed_at` vinner.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    KillSwitch,
    SignalStoreError,
)
from bedrock.signal_server.storage import (
    clear_all_kills,
    load_kills,
    upsert_kill,
)

kills_bp = Blueprint("kills", __name__)


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


@kills_bp.post("/kill")
def post_kill() -> tuple[object, int]:
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
        kill = KillSwitch.model_validate(payload)
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

    try:
        upsert_kill(_get_config().kill_switch_path, kill)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(kill.model_dump(mode="json")), 201


@kills_bp.post("/clear_kills")
def clear_kills() -> tuple[object, int]:
    try:
        removed = clear_all_kills(_get_config().kill_switch_path)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"removed": removed}), 200


@kills_bp.get("/kills")
def get_kills() -> tuple[object, int]:
    try:
        kills = load_kills(_get_config().kill_switch_path)
    except SignalStoreError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify([k.model_dump(mode="json") for k in kills]), 200
