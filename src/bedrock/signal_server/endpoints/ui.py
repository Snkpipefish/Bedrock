# pyright: reportAttributeAccessIssue=false
# pandas-stubs har dårlig dekning av itertuples() (NamedTuple med dynamiske
# attributter). Konsekvent false-positive.

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
from datetime import timezone
from pathlib import Path
from typing import Any

import pandas as pd
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


@ui_bp.get("/admin")
def admin() -> Response:
    """Admin-rule-editor (Fase 9 runde 3 session 54).

    Skjult URL — ikke linket fra index.html. Bruker når den via direkte
    URL og oppgir `BEDROCK_ADMIN_CODE` i kode-gaten. Selve HTML-en er
    public; alle skrive-handlinger går mot `/admin/rules`-endepunktene
    som krever `X-Admin-Code`-header. PLAN § 10.5.
    """
    root = _web_root()
    admin_path = root / "admin.html"
    if not admin_path.exists():
        abort(404, description=f"admin.html ikke funnet i {root}")
    return send_from_directory(root, "admin.html")


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


def _setups_response(
    entries: list[dict],
    *,
    limit_str: str | None,
    include_unpublished: bool = False,
) -> Response:
    """Filter invalidated + (default) unpublished + sorter + valgfri limit.

    Invalidated-signaler skjules alltid fra UI. Default skjules også
    `published=False` — disse er signaler hvor scoring ikke møtte
    publish-terskel. UI viser kun publiserte (handelsbare) signaler.
    Send `?include_unpublished=1` for å se alt (debug/admin-bruk).

    Sortering: grade-rank asc (A+ først), så score desc.
    """
    visible = [e for e in entries if not e.get("invalidated")]
    if not include_unpublished:
        # Default: skjul ikke-publiserte (de møtte ikke score-floor).
        visible = [e for e in visible if e.get("published") is True]
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

    Leser `config.signals_path`. Default skjuler ikke-publiserte
    setups (`published=False`); send `?include_unpublished=1` for
    debug-visning. Invalidated-signaler skjules alltid.
    """
    from flask import request

    entries = _read_signals_list(_config().signals_path)
    include_unpub = request.args.get("include_unpublished", "").lower() in ("1", "true", "yes")
    return _setups_response(
        entries,
        limit_str=request.args.get("limit"),
        include_unpublished=include_unpub,
    )


@ui_bp.get("/api/ui/setups/agri")
def setups_agri() -> Response:
    """Agri setups (grains/softs). Samme kontrakt som financial,
    leser `config.agri_signals_path`."""
    from flask import request

    entries = _read_signals_list(_config().agri_signals_path)
    include_unpub = request.args.get("include_unpublished", "").lower() in ("1", "true", "yes")
    return _setups_response(
        entries,
        limit_str=request.args.get("limit"),
        include_unpublished=include_unpub,
    )


# ─────────────────────────────────────────────────────────────
# News intel (Sentiment-fane, sub-fase 12.5+ session 114)
# ─────────────────────────────────────────────────────────────


@ui_bp.get("/api/ui/news_intel")
def news_intel() -> Response:
    """Returner siste news_intel-artikler gruppert per kategori.

    Query-params:
        category: 'gold'/'silver'/etc — filter til én kategori.
        days: int (default 7) — kun artikler nyere enn N dager.
        limit: int (default 60) — total cap på rader returnert.

    Response:
        {
          "categories": [
            {"id": "gold", "label": "Gull", "count": N, "articles": [...]},
            ...
          ],
          "total": <int>,
          "as_of": "<iso>"
        }
    """
    from datetime import datetime, timedelta, timezone

    from flask import jsonify, request

    from bedrock.data.store import DataStore

    cfg = _config()
    store = DataStore(cfg.db_path)

    days_str = request.args.get("days", "7")
    limit_str = request.args.get("limit", "60")
    category = request.args.get("category")
    try:
        days = max(1, int(days_str))
    except (TypeError, ValueError):
        days = 7
    try:
        limit = max(1, int(limit_str))
    except (TypeError, ValueError):
        limit = 60

    from_ts = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")

    df = store.get_news_intel(
        category=category,
        from_event_ts=from_ts,
        last_n=limit,
    )

    # Norske labels for kategorier (UI-visning)
    _category_labels = {
        "gold": "Gull",
        "silver": "Sølv",
        "copper": "Kobber",
        "oil": "Olje",
        "gas": "Gass",
        "grains": "Korn",
        "softs": "Bløte råvarer",
        "geopolitics": "Geopolitikk",
        "agri_weather": "Landbruk & vær",
    }

    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in _category_labels}
    if not df.empty:
        for row in df.itertuples(index=False):
            cat = str(row.category)
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(
                {
                    "url": row.url,
                    "title": row.title,
                    "source": row.source if not pd.isna(row.source) else None,
                    "event_ts": row.event_ts.isoformat()
                    if hasattr(row.event_ts, "isoformat")
                    else str(row.event_ts),
                    "category": cat,
                    "query_id": row.query_id,
                    "sentiment_label": (
                        row.sentiment_label if not pd.isna(row.sentiment_label) else None
                    ),
                    "disruption_score": (
                        float(row.disruption_score) if not pd.isna(row.disruption_score) else None
                    ),
                }
            )

    categories = [
        {
            "id": cat_id,
            "label": _category_labels.get(cat_id, cat_id),
            "count": len(grouped[cat_id]),
            "articles": grouped[cat_id],
        }
        for cat_id in _category_labels
    ]

    return jsonify(
        {
            "categories": categories,
            "total": len(df) if not df.empty else 0,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    )


@ui_bp.get("/api/ui/crypto_sentiment")
def crypto_sentiment() -> Response:
    """Returner siste crypto-sentiment-snapshot + F&G-historikk.

    Query-params:
        history_days: int (default 30) — historikk-vindu for F&G-trend.

    Response:
        {
          "as_of": "<iso>",
          "fng": {"latest": <int>, "label": <str>, "history": [int, ...]},
          "market": {
            "btc_dominance": <float>,
            "eth_dominance": <float>,
            "total_mcap_usd": <float>,
            "total_mcap_chg24h_pct": <float>
          },
          "available": <bool>
        }

    Felter er null hvis indikator mangler i DB (tom DB → available=False).
    """
    from datetime import datetime, timezone

    from flask import jsonify, request

    from bedrock.data.store import DataStore

    cfg = _config()
    store = DataStore(cfg.db_path)

    history_str = request.args.get("history_days", "30")
    try:
        history_days = max(7, min(int(history_str), 365))
    except (TypeError, ValueError):
        history_days = 30

    available = store.has_crypto_sentiment()

    # F&G — siste verdi + history_days dagers serie
    fng_latest: float | None = None
    fng_history: list[float] = []
    fng_label: str | None = None
    try:
        fng_series = store.get_crypto_sentiment("crypto_fng", last_n=history_days)
        if not fng_series.empty:
            fng_latest = float(fng_series.iloc[-1])
            fng_history = [float(v) for v in fng_series.values]
            # Klassifisering basert på alternative.me-buckets
            fng_label = _classify_fng(fng_latest)
    except KeyError:
        pass

    # Market dominance + mcap — kun siste verdi
    def _latest(indicator: str) -> float | None:
        try:
            s = store.get_crypto_sentiment(indicator, last_n=1)
            return float(s.iloc[-1]) if not s.empty else None
        except KeyError:
            return None

    market = {
        "btc_dominance": _latest("btc_dominance"),
        "eth_dominance": _latest("eth_dominance"),
        "total_mcap_usd": _latest("total_mcap_usd"),
        "total_mcap_chg24h_pct": _latest("total_mcap_chg24h_pct"),
    }

    return jsonify(
        {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "available": available,
            "fng": {
                "latest": fng_latest,
                "label": fng_label,
                "history": fng_history,
            },
            "market": market,
        }
    )


def _classify_fng(value: float) -> str:
    """Klassifiser Fear & Greed-verdi (0..100) per alternative.me-buckets."""
    if value < 25:
        return "Extreme Fear"
    if value < 45:
        return "Fear"
    if value < 55:
        return "Neutral"
    if value < 75:
        return "Greed"
    return "Extreme Greed"


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
    "enso": "Fundamentals",
    "weather": "Geo",
    "wasde": "USDA",
    "crop_progress": "USDA",
    # Sub-fase 12.5+ session 113: bdi → shipping (Baltic-suite-rebrand)
    "shipping": "Shipping",
    # Sub-fase 12.5+ session 105 (ADR-007/008):
    "calendar_ff": "Calendar",
    # Sub-fase 12.5+ session 106 (ADR-007/008): ICE COT.
    "cot_ice": "Ekstern COT",
    # Sub-fase 12.5+ session 107 (ADR-007/008): EIA weekly inventories.
    "eia_inventories": "Sektor",
    # Sub-fase 12.5+ session 108 (ADR-007/008): COMEX warehouse-inventories.
    "comex": "Sektor",
    # Sub-fase 12.5+ session 109 (ADR-007/008): USGS seismic events.
    "seismic": "Sektor",
    # Sub-fase 12.5+ session 110 (ADR-007/008): Euronext MiFID II COT.
    "cot_euronext": "Ekstern COT",
    # Sub-fase 12.5+ session 111 (ADR-007/008): Conab Brazil crop estimates.
    "conab": "USDA",
    # Sub-fase 12.5+ session 112 (ADR-007/008): UNICA Brazil sugar/ethanol.
    "unica": "Sektor",
    # Sub-fase 12.5+ session 114 (ADR-007/008): Google News RSS sentiment.
    "news_intel": "Sentiment",
    # Sub-fase 12.5+ session 115 (ADR-007/008): Crypto F&G + CoinGecko.
    "crypto_sentiment": "Sentiment",
}
_DEFAULT_GROUP = "Other"

# Rekkefølge på grupper i UI. Grupper som ikke er i listen havner sist.
_GROUP_ORDER = [
    "Core",
    "Bot-priser",
    "CFTC",
    "Ekstern COT",
    "Fundamentals",
    "Calendar",
    "USDA",
    "Shipping",
    "Sektor",
    "Sentiment",
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


# Mapping: agri-instrument → primær weather-region. Holdt på Python-
# siden (ikke YAML) for å unngå konflikt med harvest som leser YAML
# per iterasjon. Senere kan vi flytte dette til config/instruments
# når 12.6 er ferdig og instrument-filer kan oppdateres trygt.
_AGRI_REGION_MAP: dict[str, str] = {
    "Corn": "us_cornbelt",
    "Soybean": "us_cornbelt",
    "Wheat": "us_great_plains",
    "Cotton": "us_delta_cotton",
    "Coffee": "brazil_coffee",
    "Sugar": "brazil_mato_grosso",
    "Cocoa": "west_africa_cocoa",
    # Energi-kort som lever i agri-fanen kan også scenes (hvis aktuelt):
    "NaturalGas": "us_ng_midwest",
    "NatGas": "us_ng_midwest",
}


def _classify_enso(oni: float) -> str:
    if oni <= -0.5:
        return "la_nina"
    if oni >= 0.5:
        return "el_nino"
    return "neutral"


def _enso_label(cls: str) -> str:
    return {"la_nina": "La Niña", "el_nino": "El Niño", "neutral": "Nøytral"}.get(cls, cls)


def _classify_drought(none_pct: float) -> str:
    drought_pct = 100.0 - none_pct
    if drought_pct < 20:
        return "low"
    if drought_pct < 40:
        return "moderate"
    if drought_pct < 60:
        return "high"
    return "severe"


@ui_bp.get("/api/ui/agri_weather")
def agri_weather() -> Response:
    """Vær-/klima-kontekst for agri-instrumenter.

    Aggregerer (read-only fra DB):
      - global: NOAA ONI (ENSO-indeks) + klassifisering
      - per instrument: primær weather-region, siste weather_monthly-rad,
        og US Drought Monitor-status (kun hvis region er amerikansk).

    Returnerer alt på én gang slik at agri-fanen ikke trenger N
    parallelle kall. Ukjente instrumenter får tom kontekst-blokk.
    WAL-trygg under harvest.
    """
    from datetime import datetime

    from bedrock.data.store import DataStore

    cfg = _config()
    now = datetime.now(timezone.utc)

    try:
        store = DataStore(cfg.db_path)
        with store._connect() as con:
            con.execute("PRAGMA query_only = 1")

            oni_row = con.execute(
                "SELECT date, value FROM fundamentals "
                "WHERE series_id = 'NOAA_ONI' ORDER BY date DESC LIMIT 1"
            ).fetchone()

            wm_rows = con.execute(
                """
                SELECT region, month, temp_mean, precip_mm, hot_days, dry_days, wet_days, water_bal
                FROM weather_monthly wm
                INNER JOIN (
                    SELECT region AS r, MAX(month) AS m
                    FROM weather_monthly GROUP BY region
                ) latest ON wm.region = latest.r AND wm.month = latest.m
                """
            ).fetchall()
            weather_by_region = {
                row[0]: {
                    "month": row[1],
                    "temp_mean": float(row[2]) if row[2] is not None else None,
                    "precip_mm": float(row[3]) if row[3] is not None else None,
                    "hot_days": int(row[4]) if row[4] is not None else None,
                    "dry_days": int(row[5]) if row[5] is not None else None,
                    "wet_days": int(row[6]) if row[6] is not None else None,
                    "water_bal": float(row[7]) if row[7] is not None else None,
                }
                for row in wm_rows
            }

            drought_row = con.execute(
                "SELECT map_date, none_pct, d0_pct, d1_pct, d2_pct, d3_pct, d4_pct "
                "FROM drought_monitor WHERE aoi = 'us' ORDER BY map_date DESC LIMIT 1"
            ).fetchone()
    except Exception as exc:
        log.warning("[UI] agri_weather db-feil: %s", exc)
        return jsonify(
            {
                "available": False,
                "reason": f"db-feil: {exc}",
                "last_check": now.isoformat(),
            }
        )

    enso: dict[str, Any] | None = None
    if oni_row is not None:
        oni_val = float(oni_row[1])
        cls = _classify_enso(oni_val)
        enso = {
            "value": round(oni_val, 2),
            "class": cls,
            "label": _enso_label(cls),
            "as_of": oni_row[0],
        }

    drought_us: dict[str, Any] | None = None
    if drought_row is not None:
        none_pct = float(drought_row[1]) if drought_row[1] is not None else 100.0
        drought_us = {
            "as_of": drought_row[0],
            "none_pct": round(none_pct, 1),
            "drought_pct": round(100.0 - none_pct, 1),
            "d0_pct": round(float(drought_row[2] or 0), 1),
            "d1_pct": round(float(drought_row[3] or 0), 1),
            "d2_pct": round(float(drought_row[4] or 0), 1),
            "d3_pct": round(float(drought_row[5] or 0), 1),
            "d4_pct": round(float(drought_row[6] or 0), 1),
            "class": _classify_drought(none_pct),
        }

    # Per-instrument-pakker — en for hvert kjent agri-instrument.
    instruments: dict[str, dict[str, Any]] = {}
    for inst, region in _AGRI_REGION_MAP.items():
        wm = weather_by_region.get(region)
        is_us = region.startswith("us_")
        instruments[inst] = {
            "region": region,
            "weather_monthly": wm,
            "drought": drought_us if is_us else None,
        }

    return jsonify(
        {
            "available": True,
            "enso": enso,
            "instruments": instruments,
            "last_check": now.isoformat(),
        }
    )


@ui_bp.get("/api/ui/risk_indicators")
def risk_indicators() -> Response:
    """Aggregerte risk-indikatorer for Markedspuls-fanen.

    Sammenstiller (fra `bedrock.db`):
      - vix_term_spread: VIXCLS minus VIX3M. Negativ = contango (normal),
        positiv = backwardation (akutt stress).
      - aaii_bull_bear:  AAII bull/bear-spread (siste ukerapport).
      - nfci:            Chicago Fed NFCI. < 0 = looser, > 0 = tighter.
      - credit_spread:   BAA10Y (Moody's BAA over 10Y treasury, %-poeng).
      - real_yield:      DGS10 - T10YIE (10Y nominal - breakeven, %-poeng).

    For hver: returnerer siste verdi + dato + klassifisering
    (calm/normal/elevated/stress) basert på enkle terskler.

    Read-only mot DB — WAL-trygg under harvest.
    """
    from datetime import datetime

    from bedrock.data.store import DataStore

    cfg = _config()
    now = datetime.now(timezone.utc)

    try:
        store = DataStore(cfg.db_path)
        # Hent siste verdi per series_id i fundamentals (én rundtur).
        with store._connect() as con:
            con.execute("PRAGMA query_only = 1")
            fund_rows = con.execute(
                """
                SELECT f.series_id, f.date, f.value
                FROM fundamentals f
                INNER JOIN (
                    SELECT series_id, MAX(date) AS d
                    FROM fundamentals
                    WHERE series_id IN (
                        'VIXCLS','VIX3M','NFCI','BAA10Y','DGS10','T10YIE','DTWEXBGS'
                    )
                    GROUP BY series_id
                ) m ON f.series_id = m.series_id AND f.date = m.d
                """
            ).fetchall()
            fund = {row[0]: {"date": row[1], "value": float(row[2])} for row in fund_rows}

            aaii_row = con.execute(
                "SELECT date, bullish_pct, bearish_pct, bull_bear_spread "
                "FROM aaii_sentiment ORDER BY date DESC LIMIT 1"
            ).fetchone()
    except Exception as exc:
        log.warning("[UI] risk_indicators db-feil: %s", exc)
        return jsonify(
            {
                "available": False,
                "reason": f"db-feil: {exc}",
                "last_check": now.isoformat(),
                "indicators": [],
            }
        )

    def _val(series: str) -> tuple[float | None, str | None]:
        d = fund.get(series)
        return (d["value"], d["date"]) if d else (None, None)

    indicators: list[dict[str, Any]] = []

    # VIX term-spread: VIXCLS - VIX3M
    vix1, d1 = _val("VIXCLS")
    vix3, d3 = _val("VIX3M")
    if vix1 is not None and vix3 is not None:
        spread = vix1 - vix3
        # Backwardation (positiv) = akutt stress; flat ~ 0; sterkt contango ≤ -3
        if spread >= 0.5:
            cls = "stress"
        elif spread >= -0.5:
            cls = "elevated"
        elif spread >= -2.0:
            cls = "normal"
        else:
            cls = "calm"
        indicators.append(
            {
                "key": "vix_term",
                "name": "VIX term-spread",
                "value": round(spread, 2),
                "unit": "pt",
                "as_of": max(d1 or "", d3 or "") or None,
                "class": cls,
                "context": f"VIX 1m {vix1:.2f} − 3m {vix3:.2f}",
                "guide": "Positiv = backwardation (akutt stress). Sterkt negativ = roen.",
            }
        )

    # AAII bull/bear-spread.
    # Merk: kolonnen `bull_bear_spread` i DB er feilskrevet av fetcher
    # (lagrer bull + neutral + bear ≈ 100). Vi regner derfor direkte
    # fra bull% − bear% her — bypass av kjent fetcher-bug for å unngå
    # endringer i fetch/-laget under live harvest.
    if aaii_row is not None:
        a_date, a_bull, a_bear, _ = aaii_row
        spread = float(a_bull) - float(a_bear)
        # Klassiske terskler: > +20 = grådighet, < -20 = frykt (kontrarisk)
        if spread >= 20:
            cls = "stress"  # ekstrem grådighet → kontra-bearish
        elif spread >= 10:
            cls = "elevated"
        elif spread >= -10:
            cls = "normal"
        elif spread >= -20:
            cls = "elevated"
        else:
            cls = "stress"  # ekstrem frykt → kontra-bullish
        indicators.append(
            {
                "key": "aaii_bull_bear",
                "name": "AAII bull-bear",
                "value": round(spread, 1),
                "unit": "pp",
                "as_of": a_date,
                "class": cls,
                "context": f"bull {float(a_bull):.1f}% / bear {float(a_bear):.1f}%",
                "guide": "Klassisk kontra-indikator: ekstreme verdier signaliserer flokk-atferd.",
            }
        )

    # NFCI
    nfci, nfci_d = _val("NFCI")
    if nfci is not None:
        if nfci >= 0.5:
            cls = "stress"
        elif nfci >= 0:
            cls = "elevated"
        elif nfci >= -0.5:
            cls = "normal"
        else:
            cls = "calm"
        indicators.append(
            {
                "key": "nfci",
                "name": "NFCI",
                "value": round(nfci, 3),
                "unit": "z",
                "as_of": nfci_d,
                "class": cls,
                "context": "Chicago Fed financial conditions",
                "guide": "Negativ = lettere finansforhold (lav risk-aversjon). Positiv = strammere.",
            }
        )

    # Credit spread (BAA10Y)
    baa, baa_d = _val("BAA10Y")
    if baa is not None:
        if baa >= 3.0:
            cls = "stress"
        elif baa >= 2.0:
            cls = "elevated"
        elif baa >= 1.5:
            cls = "normal"
        else:
            cls = "calm"
        indicators.append(
            {
                "key": "credit_spread",
                "name": "Credit-spread (BAA-10Y)",
                "value": round(baa, 2),
                "unit": "pp",
                "as_of": baa_d,
                "class": cls,
                "context": "Moody's BAA over 10Y treasury",
                "guide": "Bredere spread = økt credit-risk-pris. Snitt ~ 2.0; > 3.0 = stress.",
            }
        )

    # Real yield = DGS10 - T10YIE
    dgs10, d_dgs = _val("DGS10")
    bei, d_bei = _val("T10YIE")
    if dgs10 is not None and bei is not None:
        ry = dgs10 - bei
        if ry >= 2.5:
            cls = "stress"
        elif ry >= 1.5:
            cls = "elevated"
        elif ry >= 0.5:
            cls = "normal"
        else:
            cls = "calm"
        indicators.append(
            {
                "key": "real_yield",
                "name": "10Y real yield",
                "value": round(ry, 2),
                "unit": "%",
                "as_of": max(d_dgs or "", d_bei or "") or None,
                "class": cls,
                "context": f"DGS10 {dgs10:.2f}% − T10YIE {bei:.2f}%",
                "guide": "Høy real yield = strammere policy / negativt for gull og lange varigheter.",
            }
        )

    return jsonify(
        {
            "available": True,
            "indicators": indicators,
            "last_check": now.isoformat(),
        }
    )


@ui_bp.get("/api/ui/system_health")
def system_health() -> Response:
    """Daglig systemsjekk — siste monitor-rapport.

    Leser nyeste `data/_meta/monitor_YYYY-MM-DD.json` (skrevet av
    `scripts/daily_monitor.py` via systemd-timer). Hver rapport har
    en `overall_ok`-flagg + en liste med `checks` (fetcher_freshness,
    pipeline_log_errors, agri_tp_override, signal_diff).

    Fraværende meta-katalog → `{"available": False, ...}`. UI viser
    da bare en placeholder-melding.
    """
    from datetime import datetime

    cfg = _config()
    meta_dir = cfg.data_root / "_meta"
    now = datetime.now(timezone.utc)

    if not meta_dir.exists():
        return jsonify(
            {
                "available": False,
                "reason": f"meta-katalog mangler: {meta_dir}",
                "last_check": now.isoformat(),
            }
        )

    candidates = sorted(meta_dir.glob("monitor_????-??-??.json"))
    if not candidates:
        return jsonify(
            {
                "available": False,
                "reason": "ingen monitor-rapporter funnet",
                "last_check": now.isoformat(),
            }
        )

    latest = candidates[-1]
    try:
        report = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("[UI] system_health parse-feil %s: %s", latest, exc)
        return jsonify(
            {
                "available": False,
                "reason": f"kunne ikke lese {latest.name}: {exc}",
                "last_check": now.isoformat(),
            }
        )

    return jsonify(
        {
            "available": True,
            "report_file": latest.name,
            "generated_utc": report.get("generated_utc"),
            "overall_ok": bool(report.get("overall_ok")),
            "checks": report.get("checks") or [],
            "last_check": now.isoformat(),
        }
    )


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
    now = datetime.now(timezone.utc)

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
