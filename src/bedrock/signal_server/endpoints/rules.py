"""Admin rule-editor endepunkter.

Fase 7 session 38 — PLAN § 8.3.

Endepunkter:
- `GET  /admin/rules` — liste over tilgjengelige instrument-YAML
- `GET  /admin/rules/<instrument_id>` — rå YAML-innhold
- `PUT  /admin/rules/<instrument_id>` — valider + skriv ny YAML

Auth: alle endepunktene krever header `X-Admin-Code` med verdi som
matcher `cfg.admin_code`. Hvis `admin_code` ikke er konfigurert
(None), deaktiveres endepunktene med 503 Service Unavailable —
bevisst valg: vi vil ikke at en nyinstallert bedrock skal eksponere
editor uten at admin har satt et passord.

**Dry-run-diff og git-commit** (resten av PLAN § 8.3) er bevisst
utsatt til senere session. De krever henholdsvis orchestrator-
snapshot-kobling og git-integrasjon som er vesentlig større scope.
Session 38 leverer minimum-viable: read + validate + atomic write.

**Sikkerhet**: instrument-ID saniteres strengt mot path-traversal.
Kun `[a-zA-Z0-9_-]` tillatt — ingen `..`, `/`, eller annet.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.config.instruments import (
    InstrumentConfigError,
    load_instrument_from_yaml_string,
)
from bedrock.signal_server.config import ServerConfig

rules_bp = Blueprint("rules", __name__)

_INSTRUMENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _check_auth() -> tuple[object, int] | None:
    """Returnerer en (error, status)-tuple hvis auth feiler, ellers None."""
    cfg = _get_config()
    if cfg.admin_code is None:
        return (
            jsonify({"error": "admin-endepunkter er ikke konfigurert"}),
            503,
        )
    header = request.headers.get("X-Admin-Code")
    if not header:
        return (
            jsonify({"error": "X-Admin-Code-header kreves"}),
            401,
        )
    if header != cfg.admin_code:
        return jsonify({"error": "ugyldig X-Admin-Code"}), 401
    return None


def _validate_instrument_id(instrument_id: str) -> tuple[object, int] | None:
    """Sanitize mot path-traversal. None hvis OK."""
    if not _INSTRUMENT_ID_RE.match(instrument_id):
        return (
            jsonify(
                {
                    "error": (
                        "ugyldig instrument-id: kun bokstaver, tall, "
                        "underscore og bindestrek er tillatt"
                    )
                }
            ),
            400,
        )
    return None


def _yaml_path(cfg: ServerConfig, instrument_id: str) -> Path:
    return cfg.instruments_dir / f"{instrument_id}.yaml"


@rules_bp.get("/admin/rules")
def list_rules() -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    cfg = _get_config()
    if not cfg.instruments_dir.exists():
        return jsonify({"instruments": []}), 200

    instruments = [
        {
            "instrument_id": path.stem,
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(cfg.instruments_dir.glob("*.yaml"))
    ]
    return jsonify({"instruments": instruments}), 200


@rules_bp.get("/admin/rules/<instrument_id>")
def get_rule(instrument_id: str) -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    id_err = _validate_instrument_id(instrument_id)
    if id_err is not None:
        return id_err

    cfg = _get_config()
    path = _yaml_path(cfg, instrument_id)
    if not path.exists():
        return (
            jsonify({"error": f"instrument {instrument_id!r} finnes ikke"}),
            404,
        )

    return (
        jsonify(
            {
                "instrument_id": instrument_id,
                "yaml_content": path.read_text(encoding="utf-8"),
            }
        ),
        200,
    )


@rules_bp.put("/admin/rules/<instrument_id>")
def put_rule(instrument_id: str) -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    id_err = _validate_instrument_id(instrument_id)
    if id_err is not None:
        return id_err

    if not request.is_json:
        return (
            jsonify({"error": "Content-Type må være application/json"}),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return jsonify({"error": "body må være et JSON-objekt"}), 400

    yaml_content = payload.get("yaml_content")
    if not isinstance(yaml_content, str):
        return (
            jsonify({"error": "yaml_content-felt (string) kreves"}),
            400,
        )

    cfg = _get_config()

    # Valider via Pydantic + inherits-resolver
    try:
        config = load_instrument_from_yaml_string(
            yaml_content,
            source_name=f"admin-put:{instrument_id}",
        )
    except InstrumentConfigError as exc:
        return jsonify({"error": "validering feilet", "detail": str(exc)}), 400
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

    # Valgfri sanity: instrument-id i URL matcher config.instrument.id
    if config.instrument.id.lower() != instrument_id.lower():
        return (
            jsonify(
                {
                    "error": (
                        f"instrument-id i URL ({instrument_id}) "
                        f"matcher ikke config.instrument.id "
                        f"({config.instrument.id})"
                    )
                }
            ),
            400,
        )

    # Atomic write (samme mønster som signals-storage)
    target = _yaml_path(cfg, instrument_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(yaml_content)
            if not yaml_content.endswith("\n"):
                fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return (
        jsonify(
            {
                "instrument_id": instrument_id,
                "written_to": str(target.resolve()),
                "validated": True,
            }
        ),
        200,
    )
