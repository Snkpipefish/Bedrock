"""Tester for `/bot/signals` endpoint (sub-fase 12.9 D1b).

Verifiserer at adapter-output leveres korrekt via HTTP og at edge-cases
(tom fil, korrupt JSON, ikke-array-payload) gir riktig respons.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from flask import Flask

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig


def _make_app(signals_bot_path: Path, **overrides) -> Flask:
    # db_path pekes på en ikke-eksisterende fil så global_state fail-opener
    # deterministisk (ingen avhengighet til repoets data/bedrock.db).
    cfg_kwargs = {
        "signals_bot_path": signals_bot_path,
        "db_path": signals_bot_path.parent / "missing.db",
    }
    cfg_kwargs.update(overrides)
    cfg = ServerConfig(**cfg_kwargs)  # pyright: ignore[reportArgumentType]
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


# ---------------------------------------------------------------------------
# signals_generated_at (batch-ferskhet, session 2026-09-05)
# ---------------------------------------------------------------------------


def test_signals_generated_at_from_sidecar(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    sidecar = Path(str(path) + ".last_run.json")
    sidecar.write_text(
        json.dumps(
            {
                "run_ts": "2026-09-05T06:06:00+00:00",
                "written": False,
                "n_entries": 1,
                "n_instruments_ok": 19,
                "n_instruments_failed": 0,
            }
        )
    )
    app = _make_app(path)
    resp = app.test_client().get("/bot/signals")
    data = resp.get_json()
    assert data["signals_generated_at"] == "2026-09-05T06:06:00+00:00"
    # HTTP-tidspunkt er fortsatt separat og nyere enn batchen
    assert data["generated_at"] > data["signals_generated_at"]


def test_signals_generated_at_falls_back_to_mtime(tmp_path):
    import os

    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    fixed = 1_788_000_000
    os.utime(path, (fixed, fixed))
    expected = datetime.fromtimestamp(fixed, tz=timezone.utc).isoformat(timespec="seconds")
    app = _make_app(path)
    data = app.test_client().get("/bot/signals").get_json()
    assert data["signals_generated_at"] == expected
    assert expected.endswith("+00:00")


def test_signals_generated_at_corrupt_sidecar_falls_back_to_mtime(tmp_path):
    import os

    path = tmp_path / "signals_bot.json"
    path.write_text("[]")
    Path(str(path) + ".last_run.json").write_text("{corrupt")
    fixed = 1_788_000_000
    os.utime(path, (fixed, fixed))
    expected = datetime.fromtimestamp(fixed, tz=timezone.utc).isoformat(timespec="seconds")
    app = _make_app(path)
    data = app.test_client().get("/bot/signals").get_json()
    assert data["signals_generated_at"] == expected


def test_signals_generated_at_none_when_file_missing(tmp_path):
    path = tmp_path / "signals_bot.json"
    app = _make_app(path)
    data = app.test_client().get("/bot/signals").get_json()
    assert data["signals_generated_at"] is None


# ---------------------------------------------------------------------------
# global_state (event-blackout, session 2026-09-05)
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def get_econ_events(self, countries=None, impact_levels=None, from_ts=None, to_ts=None):
        df = pd.DataFrame(self.rows)
        if not df.empty:
            df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
        return df


def test_global_state_contains_event_blackout_and_geo_active(tmp_path, monkeypatch):
    from datetime import timedelta

    import bedrock.signal_server.endpoints.bot as bot_mod

    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    db = tmp_path / "bedrock.db"
    db.touch()  # eksisterer → endpoint prøver DataStore(db)
    wl = tmp_path / "bot_whitelist.yaml"
    wl.write_text(yaml.safe_dump({"mapping": {"Gold": "GOLD", "EURUSD": "EURUSD"}}))
    cal = tmp_path / "usda.yaml"
    cal.write_text("prospective_plantings: []\n")

    ev_ts = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {
            "event_ts": ev_ts,
            "country": "USD",
            "title": "Non-Farm Employment Change",
            "impact": "High",
            "forecast": None,
            "previous": None,
            "actual": None,
            "fetched_at": ev_ts,
        }
    ]
    monkeypatch.setattr(bot_mod, "DataStore", lambda _p: _FakeStore(rows))

    app = _make_app(path, db_path=db, bot_whitelist_path=wl, usda_calendar_path=cal)
    resp = app.test_client().get("/bot/signals")
    assert resp.status_code == 200
    gs = resp.get_json()["global_state"]
    assert gs["geo_active"] is False
    assert gs["geo_risk_active"] is False
    assert set(gs["event_blackout"]) == {"GOLD", "EURUSD"}
    assert gs["event_blackout"]["GOLD"]["event"] == "Non-Farm Employment Change"
    assert gs["event_blackout"]["GOLD"]["minutes_away"] == 30
    assert gs["usda_blackout"] == {}
    assert "event_blackout_error" not in gs


def test_global_state_fail_open_when_db_missing(tmp_path):
    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    app = _make_app(path)  # db_path → missing.db
    resp = app.test_client().get("/bot/signals")
    assert resp.status_code == 200
    gs = resp.get_json()["global_state"]
    assert gs["event_blackout"] == {}
    assert gs["usda_blackout"] == {}
    assert "db missing" in gs["event_blackout_error"]
    assert gs["geo_active"] is False
    assert gs["correlation_config"]["max_total"] == 20


def test_global_state_never_500s_when_store_raises(tmp_path, monkeypatch):
    import bedrock.signal_server.endpoints.bot as bot_mod

    path = tmp_path / "signals_bot.json"
    path.write_text(json.dumps([_make_entry()]))
    db = tmp_path / "bedrock.db"
    db.touch()

    def _boom(_p):
        raise RuntimeError("cannot open db")

    monkeypatch.setattr(bot_mod, "DataStore", _boom)
    app = _make_app(path, db_path=db)
    resp = app.test_client().get("/bot/signals")
    assert resp.status_code == 200
    gs = resp.get_json()["global_state"]
    assert gs["event_blackout"] == {}
    assert "cannot open db" in gs["event_blackout_error"]
    assert resp.get_json()["n_published"] == 1


def test_global_state_disabled_has_no_error_and_no_db_access(tmp_path, monkeypatch):
    import bedrock.signal_server.endpoints.bot as bot_mod

    path = tmp_path / "signals_bot.json"
    path.write_text("[]")
    db = tmp_path / "bedrock.db"
    db.touch()

    def _should_not_be_called(_p):
        raise AssertionError("DataStore skal ikke åpnes når blackout er av")

    monkeypatch.setattr(bot_mod, "DataStore", _should_not_be_called)
    app = _make_app(path, db_path=db, event_blackout_enabled=False)
    gs = app.test_client().get("/bot/signals").get_json()["global_state"]
    assert gs["event_blackout"] == {}
    assert gs["usda_blackout"] == {}
    assert "event_blackout_error" not in gs
