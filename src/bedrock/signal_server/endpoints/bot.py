# pyright: reportArgumentType=false
"""Bot-vendt signal-endpoint.

Sub-fase 12.9 D1b (PLAN § 21 / docs/bedrock_bot_cutover.md). Bedrock-bot
(`src/bedrock/bot/`) henter signals via HTTP — `comms.py:fetch_signals()`
gjør GET `<signal_url>/signals`. Når bot peker på `<base>/bot`, blir
endelig path `<base>/bot/signals` og treffer denne route-en.

Output er adapter-format produsert av `bedrock.signal_server.bot_adapter`
slik at bedrock-bot's `entry.py` kan parse det uten endring.
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, current_app, jsonify, request

from bedrock.signal_server.bot_adapter import adapt_to_bot_format
from bedrock.signal_server.config import ServerConfig

log = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__, url_prefix="/bot")


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


@bot_bp.get("/signals")
def get_bot_signals() -> tuple[object, int]:
    """Returner bot-format-payload basert på `signals_bot.json`.

    Tom fil / manglende fil → adapter med tom signals[]-list + 200.
    JSON-parse-feil → 500 (data-problem som bot bør oppdage).

    `include_unpublished`-flagg styrer hvorvidt entries med
    published=False også sendes:
    - ServerConfig.bot_include_unpublished = True → alltid alle
      (typisk demo-deployment)
    - Query-param `?include_unpublished=1` overstyrer config (operatør-
      override; eks. for å teste fra browser)
    Default på live-konto: kun publishable entries går til bot.
    """
    cfg = _get_config()
    path = cfg.signals_bot_path

    # Resolve include_unpublished: query > config-default
    qp = request.args.get("include_unpublished", "").lower()
    if qp in ("1", "true", "yes"):
        include_unpublished = True
    elif qp in ("0", "false", "no"):
        include_unpublished = False
    else:
        include_unpublished = cfg.bot_include_unpublished

    if not path.exists():
        log.warning("[bot/signals] %s mangler — returnerer tom batch", path)
        payload = adapt_to_bot_format([], include_unpublished=include_unpublished)
        return jsonify(payload), 200

    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        log.error("[bot/signals] %s er korrupt: %s", path, exc)
        return jsonify({"error": f"signals_bot.json corrupt: {exc}"}), 500
    except OSError as exc:
        log.error("[bot/signals] kunne ikke lese %s: %s", path, exc)
        return jsonify({"error": f"signals_bot.json read failed: {exc}"}), 500

    if not isinstance(raw, list):
        log.error("[bot/signals] %s må være JSON-array, fikk %s", path, type(raw).__name__)
        return jsonify({"error": "signals_bot.json must be a JSON array"}), 500

    payload = adapt_to_bot_format(raw, include_unpublished=include_unpublished)
    return jsonify(payload), 200
