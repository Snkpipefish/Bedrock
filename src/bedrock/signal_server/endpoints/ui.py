"""Web-UI endpoints (Fase 9 runde 1 sessions 47-50).

Serverer `web/index.html` + `web/assets/*` + JSON-APIer som UI-et
fetcher. Inngang:

    GET /                          → index.html
    GET /assets/<path>             → static asset

    # Session 47 — Skipsloggen
    GET /api/ui/trade_log          → liste av trade-entries
    GET /api/ui/trade_log/summary  → KPI-aggregat (trades/wins/pnl/win-rate)

    # Session 48 — Financial setups
    GET /api/ui/setups/financial   → setups fra signals.json, score-sortert

    # Fremtidige (runde 1):
    GET /api/ui/setups/agri        → agri_signals.json (session 49)
    GET /api/ui/pipeline_health    → Kartrommet (session 50)

Data-kilder:
- Skipsloggen: `config.trade_log_path` (ExitEngine-skrevet)
- Financial setups: `config.signals_path` (orchestrator via /push-alert)
- Agri setups: `config.agri_signals_path` (samme men agri)

Fraværende fil behandles graceful som tom liste. Ugyldig JSON logges
som warning og returnerer tom liste — UI må ikke breake ved første
gangs oppstart.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC
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


# ─────────────────────────────────────────────────────────────
# Setups-endepunkter (sessions 48-49)
# ─────────────────────────────────────────────────────────────


# Sortering: grade A+ > A > B > C > D+, så score desc. Ukjente grades
# havner bakerst.
_GRADE_RANK = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4}


def _grade_key(entry: dict) -> int:
    return _GRADE_RANK.get(entry.get("grade") or "", 99)


def _read_signals_list(path: Path) -> list[dict]:
    """Les en signals.json-liste (financial eller agri).

    Returnerer rå dict-liste (ikke Pydantic-validert — UI-laget
    behandler felt som valgfrie). Fraværende eller korrupt fil →
    tom liste + warning-log.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            log.warning("[UI] %s top-level ikke list: %r", path, type(data))
            return []
        return [row for row in data if isinstance(row, dict)]
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("[UI] %s lese-feil: %s", path, exc)
        return []


def _setups_response(entries: list[dict], *, limit_str: str | None) -> Response:
    """Filter invalidated + sorter på (grade, score desc) + valgfri limit.

    Invalidated-signaler skjules alltid fra UI — brukere skal ikke
    kunne handle dem. Sortering: grade-rank asc (A+ først), så score
    desc. Limit default = alle.
    """
    visible = [e for e in entries if not e.get("invalidated")]
    visible.sort(key=lambda e: (_grade_key(e), -float(e.get("score") or 0.0)))

    if limit_str:
        try:
            limit = int(limit_str)
            if limit > 0:
                visible = visible[:limit]
        except ValueError:
            pass

    return jsonify(
        {
            "setups": visible,
            "total_count": len(entries),
            "visible_count": len(visible),
        }
    )


@ui_bp.get("/api/ui/setups/financial")
def setups_financial() -> Response:
    """Financial setups (fx/metals/energy/indices/crypto).

    Leser `config.signals_path` — orchestrator pusher hit via
    `/push-alert`. Hverken filtrering på asset_class eller tidsvindu
    i runde 1 — UI kan sortere/filtrere klientside. Invalidated-
    signaler skjules alltid.
    """
    from flask import request

    entries = _read_signals_list(_config().signals_path)
    return _setups_response(entries, limit_str=request.args.get("limit"))


@ui_bp.get("/api/ui/setups/agri")
def setups_agri() -> Response:
    """Agri setups (grains/softs). Samme kontrakt som financial,
    leser `config.agri_signals_path`."""
    from flask import request

    entries = _read_signals_list(_config().agri_signals_path)
    return _setups_response(entries, limit_str=request.args.get("limit"))


# ─────────────────────────────────────────────────────────────
# Pipeline-helse (Kartrommet, session 50)
# ─────────────────────────────────────────────────────────────


# Hardkodet gruppering av fetchere for UI-visning. Matcher PLAN § 10.4
# (Core / Bot-priser / CFTC / Ekstern COT / Fundamentals / Sektor / Geo).
# Fetchere som ikke finnes i mappingen havner i "Other"-gruppen.
_FETCHER_GROUPS: dict[str, str] = {
    "prices": "Core",
    "cot_disaggregated": "CFTC",
    "cot_legacy": "CFTC",
    "fundamentals": "Fundamentals",
    "weather": "Geo",
}
_DEFAULT_GROUP = "Other"

# Rekkefølge på grupper i UI. Grupper som ikke er i listen havner sist.
_GROUP_ORDER = [
    "Core",
    "Bot-priser",
    "CFTC",
    "Ekstern COT",
    "Fundamentals",
    "Sektor",
    "Geo",
    "Other",
]


def _classify_staleness(has_data: bool, age_hours: float | None, stale_hours: float) -> str:
    """Klassifiser staleness-nivå.

    - missing: ingen observasjoner ennå
    - fresh: under stale_hours
    - aging: mellom 1×stale og 2×stale
    - stale: over 2×stale
    """
    if not has_data or age_hours is None:
        return "missing"
    if age_hours < stale_hours:
        return "fresh"
    if age_hours < 2 * stale_hours:
        return "aging"
    return "stale"


@ui_bp.get("/api/ui/pipeline_health")
def pipeline_health() -> Response:
    """Pipeline-helse per fetch-kilde.

    Laster `config.fetch_config_path` + instansierer DataStore mot
    `config.db_path`, kjører `status_report`, klassifiserer hver
    kilde, grupperer per PLAN § 10.4 og returnerer JSON.

    Feil-tilfeller (graceful, ingen 500):
    - fetch.yaml mangler / ugyldig → `{"groups": [], "error": "..."}`
    - db-feil per fetcher → status="missing" (row_count=0)
    """
    from datetime import datetime

    from bedrock.config.fetch import (
        FetchConfigError,
        load_fetch_config,
        status_report,
    )
    from bedrock.data.store import DataStore

    cfg = _config()
    now = datetime.now(UTC)

    try:
        fetch_cfg = load_fetch_config(cfg.fetch_config_path)
    except FileNotFoundError:
        return jsonify(
            {
                "groups": [],
                "last_check": now.isoformat(),
                "error": f"fetch.yaml ikke funnet: {cfg.fetch_config_path}",
            }
        )
    except FetchConfigError as exc:
        return jsonify(
            {
                "groups": [],
                "last_check": now.isoformat(),
                "error": f"fetch.yaml ugyldig: {exc}",
            }
        )

    try:
        store = DataStore(cfg.db_path)
        statuses = status_report(fetch_cfg, store, now=now)
    except Exception as exc:
        log.warning("[UI] pipeline_health db-feil: %s", exc)
        statuses = []

    # Bygg per-gruppe-liste
    groups: dict[str, list[dict[str, Any]]] = {}
    spec_map = fetch_cfg.fetchers
    for st in statuses:
        group_name = _FETCHER_GROUPS.get(st.name, _DEFAULT_GROUP)
        spec = spec_map.get(st.name)
        source = {
            "name": st.name,
            "module": st.module,
            "table": st.table,
            "status": _classify_staleness(st.has_data, st.age_hours, st.stale_hours),
            "stale_hours": st.stale_hours,
            "age_hours": round(st.age_hours, 2) if st.age_hours is not None else None,
            "latest_observation": (
                st.latest_observation.isoformat() if st.latest_observation is not None else None
            ),
            "cron": spec.cron if spec else None,
        }
        groups.setdefault(group_name, []).append(source)

    # Sorter fetchere innen hver gruppe alfabetisk
    for sources in groups.values():
        sources.sort(key=lambda s: s["name"])

    # Bygg respons-gruppe-liste i _GROUP_ORDER-rekkefølge
    ordered_groups: list[dict[str, Any]] = []
    for group_name in _GROUP_ORDER:
        if group_name in groups:
            ordered_groups.append({"name": group_name, "sources": groups[group_name]})
    # Tilføy grupper som ikke er i _GROUP_ORDER (fremtidige tilskudd)
    for group_name, sources in groups.items():
        if group_name not in _GROUP_ORDER:
            ordered_groups.append({"name": group_name, "sources": sources})

    return jsonify(
        {
            "groups": ordered_groups,
            "last_check": now.isoformat(),
        }
    )
