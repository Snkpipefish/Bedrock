"""Web-UI endpoints (Fase 9 runde 1 session 47: Skipsloggen).

Serverer `web/index.html` + `web/assets/*` + JSON-APIer som UI-et
fetcher. Inngang:

    GET /                        → index.html
    GET /assets/<path>           → static asset
    GET /api/ui/trade_log        → liste av trade-entries
    GET /api/ui/trade_log/summary → KPI-aggregat (trades/wins/pnl/win-rate)

Fremtidige sessions (runde 1):
    GET /api/ui/setups/financial  → Fase 2 setups (session 48)
    GET /api/ui/setups/agri       → Fase 3 setups (session 49)
    GET /api/ui/pipeline_health   → Kartrommet (session 50)

Data-kilde for Skipsloggen: `config.trade_log_path`. Filen skrives av
`bedrock.bot.exit.ExitEngine._log_trade_closed` og `_log_reconcile_opened`
(og `entry._log_trade_opened`). Fraværende fil behandles graceful som
tom liste.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, send_from_directory

from bedrock.signal_server.config import ServerConfig

log = logging.getLogger("bedrock.signal_server.ui")

ui_bp = Blueprint("ui", __name__)


def _config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _web_root() -> Path:
    return _config().web_root.resolve()


def _read_trade_log() -> dict[str, Any]:
    """Les trade-log-filen. Fraværende eller ugyldig fil → tom struktur.

    Feilen logges, men UI-et får alltid en gyldig respons slik at
    førstegangs-oppstart (før bot har kjørt første trade) ikke breaker
    UI-en.
    """
    path = _config().trade_log_path
    if not path.exists():
        return {"entries": [], "last_updated": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            log.warning("[UI] trade_log top-level ikke dict: %r", type(data))
            return {"entries": [], "last_updated": None}
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            log.warning("[UI] trade_log entries ikke list: %r", type(entries))
            entries = []
        return {
            "entries": entries,
            "last_updated": data.get("last_updated"),
        }
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("[UI] trade_log lese-feil: %s", exc)
        return {"entries": [], "last_updated": None}


# ─────────────────────────────────────────────────────────────
# Static: index.html + assets
# ─────────────────────────────────────────────────────────────


@ui_bp.get("/")
def index() -> Response:
    root = _web_root()
    index_path = root / "index.html"
    if not index_path.exists():
        abort(404, description=f"index.html ikke funnet i {root}")
    return send_from_directory(root, "index.html")


@ui_bp.get("/assets/<path:subpath>")
def assets(subpath: str) -> Response:
    assets_root = _web_root() / "assets"
    if not assets_root.exists():
        abort(404, description="assets-mappe ikke funnet")
    return send_from_directory(assets_root, subpath)


# ─────────────────────────────────────────────────────────────
# API: /api/ui/trade_log (+ /summary)
# ─────────────────────────────────────────────────────────────


@ui_bp.get("/api/ui/trade_log")
def trade_log() -> Response:
    """Returner alle trade-entries, nyeste først.

    Ingen filtrering i runde 1 — UI-et sorterer/filtrerer klientside.
    Query-param `limit` (heltall) kutter listen til første N entries
    (entries er allerede nyeste-først fra log-writer).
    """
    data = _read_trade_log()
    limit_raw = (current_app.test_request_context() if False else None)  # placeholder
    # Bruker Flask request-object for query-param; importer kun her
    from flask import request

    limit_str = request.args.get("limit")
    entries = data["entries"]
    if limit_str:
        try:
            limit = int(limit_str)
            if limit > 0:
                entries = entries[:limit]
        except ValueError:
            pass  # Ignorer ugyldig limit
    return jsonify(
        {
            "entries": entries,
            "last_updated": data["last_updated"],
            "total_count": len(data["entries"]),
        }
    )


@ui_bp.get("/api/ui/trade_log/summary")
def trade_log_summary() -> Response:
    """KPI-aggregat over hele trade-loggen.

    Returnerer antall trades, win/loss/managed-fordeling, total PnL i USD,
    og win-rate. Fersk start → alle null.
    """
    data = _read_trade_log()
    entries = data["entries"]

    total = len(entries)
    open_trades = sum(1 for e in entries if e.get("result") is None)
    closed = [e for e in entries if e.get("result") is not None]
    wins = sum(1 for e in closed if e.get("result") == "win")
    losses = sum(1 for e in closed if e.get("result") == "loss")
    managed = sum(1 for e in closed if e.get("result") == "managed")

    total_pnl = 0.0
    for e in closed:
        pnl = e.get("pnl") or {}
        val = pnl.get("pnl_usd")
        if isinstance(val, (int, float)):
            total_pnl += val

    closed_count = len(closed)
    win_rate = round(wins / closed_count, 3) if closed_count > 0 else 0.0

    return jsonify(
        {
            "total": total,
            "open": open_trades,
            "closed": closed_count,
            "wins": wins,
            "losses": losses,
            "managed": managed,
            "total_pnl_usd": round(total_pnl, 2),
            "win_rate": win_rate,
            "last_updated": data["last_updated"],
        }
    )
