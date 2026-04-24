"""Fil-upload endepunkt.

Fase 7 session 37: `POST /upload` — multipart/form-data med fil-felt
`file`. Lagres til `cfg.uploads_root / <uuid>.<ext>` med ekstensjon
bevart.

Validering:
- Content-Type: `multipart/form-data`
- Filnavn må ha ekstensjon i `cfg.upload_allowed_exts`
- Størrelse ≤ `cfg.upload_max_bytes`

Returverdier:
- 201 + `{filename, stored_as, size_bytes}`
- 400: manglende felt, ugyldig ekstensjon
- 413: Payload too large
"""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from bedrock.signal_server.config import ServerConfig

uploads_bp = Blueprint("uploads", __name__)


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


@uploads_bp.post("/upload")
def upload() -> tuple[object, int]:
    cfg = _get_config()

    if "file" not in request.files:
        return (
            jsonify(
                {"error": "multipart/form-data med 'file'-felt kreves"}
            ),
            400,
        )

    uploaded = request.files["file"]
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "fil mangler eller har ikke navn"}), 400

    ext = _ext_of(uploaded.filename)
    if ext not in cfg.upload_allowed_exts:
        return (
            jsonify(
                {
                    "error": f"ugyldig ekstensjon {ext!r}",
                    "allowed": list(cfg.upload_allowed_exts),
                }
            ),
            400,
        )

    # Les til minne for å kunne rejecte før disk-write. OK for 10MB-cap.
    data = uploaded.read()
    if len(data) > cfg.upload_max_bytes:
        return (
            jsonify(
                {
                    "error": "filen er for stor",
                    "size_bytes": len(data),
                    "max_bytes": cfg.upload_max_bytes,
                }
            ),
            413,
        )
    if len(data) == 0:
        return jsonify({"error": "fil er tom"}), 400

    cfg.uploads_root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    target = cfg.uploads_root / f"{token}{ext}"
    target.write_bytes(data)

    return (
        jsonify(
            {
                "filename": uploaded.filename,
                "stored_as": str(target.resolve()),
                "size_bytes": len(data),
            }
        ),
        201,
    )
