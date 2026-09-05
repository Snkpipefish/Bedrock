# pyright: reportArgumentType=false
"""Bot-vendt signal-endpoint.

Sub-fase 12.9 D1b (PLAN § 21 / docs/bedrock_bot_cutover.md). Bedrock-bot
(`src/bedrock/bot/`) henter signals via HTTP — `comms.py:fetch_signals()`
gjør GET `<signal_url>/signals`. Når bot peker på `<base>/bot`, blir
endelig path `<base>/bot/signals` og treffer denne route-en.

Output er adapter-format produsert av `bedrock.signal_server.bot_adapter`
slik at bedrock-bot's `entry.py` kan parse det uten endring.

Session 2026-09-05:
- `signals_generated_at` (batch-ferskhet) leses fra sidecar
  ``<signals_bot_path>.last_run.json`` skrevet av `bedrock signals-all`
  ved hver kjøring — også når selve signals_bot.json ble hoppet over som
  uendret. Fallback: filens mtime; None hvis filen mangler.
- `global_state` bygges av `bedrock.signal_server.global_state` med
  event-/USDA-blackout per instrument. Fail-open: DB-feil gir defaults,
  aldri 500.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from bedrock.data.store import DataStore
from bedrock.signal_server.bot_adapter import adapt_to_bot_format, default_global_state
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.global_state import build_global_state, fail_open_global_state

log = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__, url_prefix="/bot")

# Må matche `bedrock.cli.signals_all.LAST_RUN_SIDECAR_SUFFIX` (skriver-
# siden). Duplisert her for å slippe å importere CLI-modulen (click +
# orchestrator) inn i serveren; test i tests/unit/signal_server/
# test_global_state.py låser at de to er like.
LAST_RUN_SIDECAR_SUFFIX = ".last_run.json"


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _sidecar_path(signals_path: Path) -> Path:
    return Path(str(signals_path) + LAST_RUN_SIDECAR_SUFFIX)


def read_source_generated_at(signals_path: Path) -> str | None:
    """Når signal-batchen sist ble generert, som ISO-8601-UTC-streng.

    1. Sidecar ``<signals_path>.last_run.json`` → ``run_ts`` (skrives av
       signals-all ved hver kjøring, også ved uendret output).
    2. Fallback: mtime på ``signals_path`` (oppdateres kun ved faktisk
       skriving — kan undervurdere ferskheten, men er aldri løgn om at
       data er *minst* så gammel).
    3. None hvis filen mangler.
    """
    sidecar = _sidecar_path(signals_path)
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            run_ts = meta.get("run_ts") if isinstance(meta, dict) else None
            if isinstance(run_ts, str) and run_ts:
                # Valider at det er parsebart før vi sender det til boten.
                datetime.fromisoformat(run_ts.replace("Z", "+00:00"))
                return run_ts
            log.warning("[bot/signals] %s mangler gyldig run_ts — bruker mtime", sidecar)
        except (OSError, json.JSONDecodeError, ValueError, AttributeError) as exc:
            log.warning("[bot/signals] kunne ikke lese %s (%s) — bruker mtime", sidecar, exc)
    if signals_path.exists():
        try:
            mtime = signals_path.stat().st_mtime
        except OSError as exc:
            log.warning("[bot/signals] stat %s feilet: %s", signals_path, exc)
            return None
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return None


def _global_state_for(cfg: ServerConfig, now: datetime) -> dict[str, Any]:
    """Bygg global_state fail-open: blackout av → rene defaults; DB
    mangler / åpning feiler → defaults + `event_blackout_error`."""
    if not cfg.event_blackout_enabled:
        return default_global_state()
    if not cfg.db_path.exists():
        log.warning("[bot/signals] DB %s mangler — global_state uten blackout", cfg.db_path)
        return fail_open_global_state(f"db missing: {cfg.db_path}")
    try:
        store = DataStore(cfg.db_path)
        return build_global_state(store, now, cfg)
    except Exception as exc:
        log.warning("[bot/signals] global_state feilet (fail-open): %s", exc)
        return fail_open_global_state(str(exc))


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
    now = datetime.now(timezone.utc)

    # Resolve include_unpublished: query > config-default
    qp = request.args.get("include_unpublished", "").lower()
    if qp in ("1", "true", "yes"):
        include_unpublished = True
    elif qp in ("0", "false", "no"):
        include_unpublished = False
    else:
        include_unpublished = cfg.bot_include_unpublished

    source_generated_at = read_source_generated_at(path)
    global_state = _global_state_for(cfg, now)

    if not path.exists():
        log.warning("[bot/signals] %s mangler — returnerer tom batch", path)
        payload = adapt_to_bot_format(
            [],
            now=now,
            include_unpublished=include_unpublished,
            global_state=global_state,
            source_generated_at=source_generated_at,
        )
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

    payload = adapt_to_bot_format(
        raw,
        now=now,
        include_unpublished=include_unpublished,
        global_state=global_state,
        source_generated_at=source_generated_at,
    )
    return jsonify(payload), 200
