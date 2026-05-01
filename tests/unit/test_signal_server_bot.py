"""Tester for `/bot/signals` endpoint (sub-fase 12.9 D1b).

Verifiserer at adapter-output leveres korrekt via HTTP og at edge-cases
(tom fil, korrupt JSON, ikke-array-payload) gir riktig respons.
"""

from __future__ import annotations

import json
from pathlib import Path

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig


def _make_app(signals_bot_path: Path) -> object:
    cfg = ServerConfig(signals_bot_path=signals_bot_path)
    return create_app(cfg)


def _make_entry(**overrides):
    base = {
        "instrument": "AUDUSD",
        "direction": "buy",
        "horizon": "makro",
        "score": 4.29,
        "grade": "A",
        "max_score": 5.8,
        "min_score_publish": 3.5,
        "published": True,
        "asset_class": "fx",
        "setup": {
            "setup_id": "abc123",
            "first_seen": "2026-05-01T01:39:34Z",
            "setup": {
                "instrument": "AUDUSD",
                "direction": "buy",
                "horizon": "makro",
                "entry": 0.7178,
                "sl": 0.7167,
                "tp": None,
                "rr": None,
                "atr": 0.00355,
            },
        },
        "skip_reason": None,
        "gates_triggered": [],
        "families": {},
        "active_families": 6,
        "analog": None,
    }
    base.update(overrides)
    return base


def test_missing_file_returns_empty_batch(tmp_path):
    path = tmp_path / "signals_bot.json"
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "2.1"
    assert data["signals"] == []
    assert data["n_total"] == 0


def test_empty_array_returns_empty_signals(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text("[]")
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["signals"] == []


def test_published_entries_included(tmp_path):
    path = tmp_path / "signals_bot.json"
    entries = [_make_entry(), _make_entry(instrument="EURUSD", published=False)]
    path.write_text(json.dumps(entries))
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["n_total"] == 2
    assert data["n_published"] == 1
    assert data["signals"][0]["instrument"] == "AUDUSD"


def test_corrupt_json_returns_500(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text("{not valid json")
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    assert resp.status_code == 500
    data = resp.get_json()
    assert "error" in data


def test_non_array_returns_500(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps({"not": "an array"}))
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    assert resp.status_code == 500
    data = resp.get_json()
    assert "must be a JSON array" in data["error"]


def test_horizon_uppercased_in_response(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry(horizon="swing")]))
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    data = resp.get_json()
    assert data["signals"][0]["horizon"] == "SWING"


def test_signals_have_required_bot_fields(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    app = _make_app(path)
    client = app.test_client()
    resp = client.get("/bot/signals")
    data = resp.get_json()
    sig = data["signals"][0]
    # Felter bedrock-bot's entry.py leser
    for required in (
        "id",
        "instrument",
        "direction",
        "horizon",
        "status",
        "entry_zone",
        "stop",
        "t1",
        "expiry_candles",
        "horizon_config",
        "correlation_group",
        "created_at",
    ):
        assert required in sig, f"missing field: {required}"
