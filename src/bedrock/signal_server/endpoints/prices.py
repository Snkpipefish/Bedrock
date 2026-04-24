"""Pris-endepunkter.

Fase 7 session 37:
- `POST /push-prices` — bot sender tick/bar-oppdateringer
- `GET /prices?instrument=X&tf=Y&last_n=N` — UI/bot leser siste N bars

Lagring: `bedrock.data.store.DataStore` (SQLite) — samme lag som
backfill-CLI og driver-laget bruker. Idempotent INSERT OR REPLACE
på (instrument, tf, ts).
"""

from __future__ import annotations

import pandas as pd
from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.data.store import DataStore
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import PushPricesRequest

prices_bp = Blueprint("prices", __name__)


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _get_store() -> DataStore:
    """Åpner DataStore mot cfg.db_path. Fersk instans per request.

    SQLite-tilkoblinger er rimelige å opprette; ingen grunn til
    pooling her. Thread-safety diskuteres senere hvis Flask skal
    kjøres multi-worker.
    """
    return DataStore(_get_config().db_path)


@prices_bp.post("/push-prices")
def push_prices() -> tuple[object, int]:
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
        req = PushPricesRequest.model_validate(payload)
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

    # Bygg DataFrame i schemaet DataStore forventer
    df = pd.DataFrame(
        [
            {
                "ts": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in req.bars
        ]
    )

    store = _get_store()
    written = store.append_prices(req.instrument, req.tf, df)
    return (
        jsonify(
            {
                "instrument": req.instrument,
                "tf": req.tf,
                "bars_written": written,
            }
        ),
        201,
    )


@prices_bp.get("/prices")
def get_prices() -> tuple[object, int]:
    instrument = request.args.get("instrument")
    tf = request.args.get("tf")
    last_n_arg = request.args.get("last_n")

    if not instrument:
        return jsonify({"error": "instrument-parameter kreves"}), 400
    if not tf:
        return jsonify({"error": "tf-parameter kreves"}), 400

    last_n: int | None = None
    if last_n_arg is not None:
        try:
            last_n = int(last_n_arg)
        except ValueError:
            return (
                jsonify({"error": "last_n må være et heltall"}),
                400,
            )
        if last_n <= 0:
            return jsonify({"error": "last_n må være > 0"}), 400

    store = _get_store()
    try:
        series = store.get_prices(instrument, tf=tf, lookback=last_n or 500)
    except KeyError:
        # Ingen data for denne (instrument, tf) — returner tom liste.
        # DataStore kaster KeyError; serveren oversetter til tom 200.
        return (
            jsonify({"instrument": instrument, "tf": tf, "bars": []}),
            200,
        )

    if series is None or len(series) == 0:
        return (
            jsonify({"instrument": instrument, "tf": tf, "bars": []}),
            200,
        )

    bars = [
        {"ts": ts.isoformat(), "close": float(close)}
        for ts, close in series.items()
    ]
    return (
        jsonify(
            {
                "instrument": instrument,
                "tf": tf,
                "bars": bars,
            }
        ),
        200,
    )
