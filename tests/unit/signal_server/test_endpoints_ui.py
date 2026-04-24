"""Tester for signal_server/endpoints/ui.py (Fase 9 runde 1 session 47).

Dekker:
- GET / serverer index.html
- GET / returnerer 404 hvis web_root mangler index.html
- GET /assets/<path> serverer statiske filer
- GET /api/ui/trade_log: fersk fil → entries + total_count
- GET /api/ui/trade_log med ?limit=N kutter resultatet
- GET /api/ui/trade_log: manglende fil → tom liste (graceful)
- GET /api/ui/trade_log: ugyldig JSON → tom liste (logger warning)
- GET /api/ui/trade_log/summary: KPI-aggregat riktig regnet
- GET /api/ui/trade_log/summary: wins/losses/managed/open-fordeling
- GET /api/ui/trade_log/summary: total_pnl summerer både positive og negative
- GET /api/ui/trade_log/summary: win_rate regnes på closed-trades
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from bedrock.signal_server.app import create_app
from bedrock.signal_server.config import ServerConfig


@pytest.fixture
def web_root(tmp_path: Path) -> Path:
    """Opprett web_root med minimum index.html + assets/ for tester."""
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("<html><body>Skipsloggen</body></html>")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('hei');")
    (root / "assets" / "style.css").write_text("body { color: red; }")
    return root


@pytest.fixture
def trade_log_path(tmp_path: Path) -> Path:
    return tmp_path / "signal_log.json"


@pytest.fixture
def app_with_config(web_root: Path, trade_log_path: Path):
    cfg = ServerConfig(web_root=web_root, trade_log_path=trade_log_path)
    return create_app(cfg)


@pytest.fixture
def client(app_with_config) -> FlaskClient:
    return app_with_config.test_client()


# ─────────────────────────────────────────────────────────────
# Static: index.html + assets
# ─────────────────────────────────────────────────────────────


def test_index_serves_html(client: FlaskClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert b"Skipsloggen" in r.data


def test_index_404_when_missing(tmp_path: Path) -> None:
    """web_root finnes men index.html mangler → 404."""
    empty = tmp_path / "web_empty"
    empty.mkdir()
    cfg = ServerConfig(web_root=empty, trade_log_path=tmp_path / "x.json")
    app = create_app(cfg)
    r = app.test_client().get("/")
    assert r.status_code == 404


def test_assets_serves_js(client: FlaskClient) -> None:
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert b"console.log" in r.data


def test_assets_serves_css(client: FlaskClient) -> None:
    r = client.get("/assets/style.css")
    assert r.status_code == 200
    assert b"color: red" in r.data


def test_assets_404_for_missing_file(client: FlaskClient) -> None:
    r = client.get("/assets/does-not-exist.js")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────
# /api/ui/trade_log
# ─────────────────────────────────────────────────────────────


def _write_log(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"entries": entries, "last_updated": "2026-04-24 12:00 UTC"}))


def test_trade_log_returns_entries(client: FlaskClient, trade_log_path: Path) -> None:
    _write_log(trade_log_path, [
        {"timestamp": "2026-04-24 10:00 UTC", "signal": {"id": "a", "instrument": "EURUSD"},
         "result": "win", "pnl": {"pnl_usd": 12.5}},
        {"timestamp": "2026-04-24 11:00 UTC", "signal": {"id": "b", "instrument": "GOLD"},
         "result": None},
    ])
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_count"] == 2
    assert len(data["entries"]) == 2
    assert data["entries"][0]["signal"]["id"] == "a"
    assert data["last_updated"] == "2026-04-24 12:00 UTC"


def test_trade_log_limit_truncates(client: FlaskClient, trade_log_path: Path) -> None:
    _write_log(trade_log_path, [
        {"timestamp": f"t{i}", "signal": {"id": f"s{i}"}} for i in range(10)
    ])
    r = client.get("/api/ui/trade_log?limit=3")
    data = r.get_json()
    assert data["total_count"] == 10
    assert len(data["entries"]) == 3


def test_trade_log_invalid_limit_ignored(client: FlaskClient, trade_log_path: Path) -> None:
    _write_log(trade_log_path, [{"signal": {"id": "x"}}])
    r = client.get("/api/ui/trade_log?limit=not-a-number")
    assert r.status_code == 200
    assert len(r.get_json()["entries"]) == 1


def test_trade_log_missing_file_returns_empty(client: FlaskClient) -> None:
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    data = r.get_json()
    assert data["entries"] == []
    assert data["total_count"] == 0
    assert data["last_updated"] is None


def test_trade_log_invalid_json_returns_empty(
    client: FlaskClient, trade_log_path: Path,
) -> None:
    trade_log_path.write_text("{ not valid json")
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    assert r.get_json()["entries"] == []


def test_trade_log_non_dict_toplevel(
    client: FlaskClient, trade_log_path: Path,
) -> None:
    """Top-level array i stedet for dict → graceful tom."""
    trade_log_path.write_text(json.dumps(["a", "b"]))
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    assert r.get_json()["entries"] == []


# ─────────────────────────────────────────────────────────────
# /api/ui/trade_log/summary
# ─────────────────────────────────────────────────────────────


def test_summary_empty_when_no_trades(client: FlaskClient) -> None:
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total"] == 0
    assert data["open"] == 0
    assert data["wins"] == 0
    assert data["losses"] == 0
    assert data["win_rate"] == 0.0
    assert data["total_pnl_usd"] == 0.0


def test_summary_counts_results(
    client: FlaskClient, trade_log_path: Path,
) -> None:
    _write_log(trade_log_path, [
        {"result": "win", "pnl": {"pnl_usd": 10.0}},
        {"result": "win", "pnl": {"pnl_usd": 5.5}},
        {"result": "loss", "pnl": {"pnl_usd": -7.25}},
        {"result": "managed", "pnl": {"pnl_usd": 0.0}},
        {"result": None},  # åpen
    ])
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total"] == 5
    assert data["open"] == 1
    assert data["closed"] == 4
    assert data["wins"] == 2
    assert data["losses"] == 1
    assert data["managed"] == 1
    # PnL-sum: 10 + 5.5 - 7.25 + 0 = 8.25
    assert data["total_pnl_usd"] == 8.25
    # win_rate = 2/4 = 0.5
    assert data["win_rate"] == 0.5


def test_summary_handles_missing_pnl(
    client: FlaskClient, trade_log_path: Path,
) -> None:
    """Entries uten pnl-felt skal ikke krasje."""
    _write_log(trade_log_path, [
        {"result": "win"},  # ingen pnl-dict
        {"result": "loss", "pnl": {}},  # tom pnl
        {"result": "win", "pnl": {"pnl_usd": 2.5}},
    ])
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total"] == 3
    assert data["wins"] == 2
    assert data["total_pnl_usd"] == 2.5


def test_summary_ignores_non_numeric_pnl(
    client: FlaskClient, trade_log_path: Path,
) -> None:
    _write_log(trade_log_path, [
        {"result": "win", "pnl": {"pnl_usd": "not a number"}},
        {"result": "win", "pnl": {"pnl_usd": 3.0}},
    ])
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total_pnl_usd"] == 3.0
