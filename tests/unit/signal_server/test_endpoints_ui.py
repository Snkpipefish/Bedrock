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
from datetime import timezone
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
    (root / "admin.html").write_text("<html><body>Admin rule editor</body></html>")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('hei');")
    (root / "assets" / "style.css").write_text("body { color: red; }")
    return root


@pytest.fixture
def trade_log_path(tmp_path: Path) -> Path:
    return tmp_path / "signal_log.json"


@pytest.fixture
def signals_path(tmp_path: Path) -> Path:
    return tmp_path / "signals.json"


@pytest.fixture
def agri_signals_path(tmp_path: Path) -> Path:
    return tmp_path / "agri_signals.json"


@pytest.fixture
def fetch_config_path(tmp_path: Path) -> Path:
    """Minimal fetch.yaml for Kartrommet-tester."""
    path = tmp_path / "fetch.yaml"
    path.write_text(
        """
fetchers:
  prices:
    module: bedrock.fetch.prices
    cron: "40 * * * 1-5"
    stale_hours: 30
    on_failure: retry_with_backoff
    table: prices
    ts_column: ts
  cot_disaggregated:
    module: bedrock.fetch.cot_cftc
    cron: "0 22 * * 5"
    stale_hours: 168
    on_failure: log_and_skip
    table: cot_disaggregated
    ts_column: report_date
  weather:
    module: bedrock.fetch.weather
    cron: "0 3 * * *"
    stale_hours: 30
    on_failure: retry_with_backoff
    table: weather
    ts_column: date
  unknown_fetcher:
    module: bedrock.fetch.custom
    cron: "0 * * * *"
    stale_hours: 12
    on_failure: log_and_skip
    table: custom
    ts_column: ts
""".strip()
    )
    return path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def app_with_config(
    web_root: Path,
    trade_log_path: Path,
    signals_path: Path,
    agri_signals_path: Path,
    fetch_config_path: Path,
    db_path: Path,
):
    cfg = ServerConfig(
        web_root=web_root,
        trade_log_path=trade_log_path,
        signals_path=signals_path,
        agri_signals_path=agri_signals_path,
        fetch_config_path=fetch_config_path,
        db_path=db_path,
    )
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


def test_admin_serves_html(client: FlaskClient) -> None:
    """Fase 9 runde 3 session 54: /admin serverer admin.html. Ikke
    linket fra index.html — bruker når den via direkte URL + kode-gate."""
    r = client.get("/admin")
    assert r.status_code == 200
    assert b"Admin rule editor" in r.data


def test_admin_404_when_missing(tmp_path: Path) -> None:
    """web_root finnes men admin.html mangler → 404."""
    empty = tmp_path / "web_no_admin"
    empty.mkdir()
    (empty / "index.html").write_text("<html></html>")
    cfg = ServerConfig(web_root=empty, trade_log_path=tmp_path / "x.json")
    app = create_app(cfg)
    r = app.test_client().get("/admin")
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
    path.write_text(
        json.dumps({"entries": entries, "last_updated": "2026-04-24 12:00 timezone.utc"})
    )


def test_trade_log_returns_entries(client: FlaskClient, trade_log_path: Path) -> None:
    _write_log(
        trade_log_path,
        [
            {
                "timestamp": "2026-04-24 10:00 timezone.utc",
                "signal": {"id": "a", "instrument": "EURUSD"},
                "result": "win",
                "pnl": {"pnl_usd": 12.5},
            },
            {
                "timestamp": "2026-04-24 11:00 timezone.utc",
                "signal": {"id": "b", "instrument": "GOLD"},
                "result": None,
            },
        ],
    )
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_count"] == 2
    assert len(data["entries"]) == 2
    assert data["entries"][0]["signal"]["id"] == "a"
    assert data["last_updated"] == "2026-04-24 12:00 timezone.utc"


def test_trade_log_limit_truncates(client: FlaskClient, trade_log_path: Path) -> None:
    _write_log(
        trade_log_path, [{"timestamp": f"t{i}", "signal": {"id": f"s{i}"}} for i in range(10)]
    )
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
    client: FlaskClient,
    trade_log_path: Path,
) -> None:
    trade_log_path.write_text("{ not valid json")
    r = client.get("/api/ui/trade_log")
    assert r.status_code == 200
    assert r.get_json()["entries"] == []


def test_trade_log_non_dict_toplevel(
    client: FlaskClient,
    trade_log_path: Path,
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
    client: FlaskClient,
    trade_log_path: Path,
) -> None:
    _write_log(
        trade_log_path,
        [
            {"result": "win", "pnl": {"pnl_usd": 10.0}},
            {"result": "win", "pnl": {"pnl_usd": 5.5}},
            {"result": "loss", "pnl": {"pnl_usd": -7.25}},
            {"result": "managed", "pnl": {"pnl_usd": 0.0}},
            {"result": None},  # åpen
        ],
    )
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
    client: FlaskClient,
    trade_log_path: Path,
) -> None:
    """Entries uten pnl-felt skal ikke krasje."""
    _write_log(
        trade_log_path,
        [
            {"result": "win"},  # ingen pnl-dict
            {"result": "loss", "pnl": {}},  # tom pnl
            {"result": "win", "pnl": {"pnl_usd": 2.5}},
        ],
    )
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total"] == 3
    assert data["wins"] == 2
    assert data["total_pnl_usd"] == 2.5


def test_summary_ignores_non_numeric_pnl(
    client: FlaskClient,
    trade_log_path: Path,
) -> None:
    _write_log(
        trade_log_path,
        [
            {"result": "win", "pnl": {"pnl_usd": "not a number"}},
            {"result": "win", "pnl": {"pnl_usd": 3.0}},
        ],
    )
    r = client.get("/api/ui/trade_log/summary")
    data = r.get_json()
    assert data["total_pnl_usd"] == 3.0


# ─────────────────────────────────────────────────────────────
# /api/ui/setups/financial (session 48)
# /api/ui/setups/agri (session 49 — endepunktet finnes allerede)
# ─────────────────────────────────────────────────────────────


def _write_signals(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


def test_setups_financial_empty_when_file_missing(client: FlaskClient) -> None:
    r = client.get("/api/ui/setups/financial")
    assert r.status_code == 200
    data = r.get_json()
    assert data["setups"] == []
    assert data["total_count"] == 0
    assert data["visible_count"] == 0


def test_setups_financial_returns_entries(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    _write_signals(
        signals_path,
        [
            {
                "instrument": "EURUSD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 3.5,
                "grade": "B",
            },
            {
                "instrument": "GOLD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 4.2,
                "grade": "A",
            },
        ],
    )
    r = client.get("/api/ui/setups/financial")
    data = r.get_json()
    assert data["total_count"] == 2
    assert data["visible_count"] == 2
    assert len(data["setups"]) == 2


def test_setups_financial_sorts_by_grade_then_score(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    """A+ før A før B; innen samme grade: høyere score først."""
    _write_signals(
        signals_path,
        [
            {
                "instrument": "X1",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 3.0,
                "grade": "B",
            },
            {
                "instrument": "X2",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 4.5,
                "grade": "A+",
            },
            {
                "instrument": "X3",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 4.0,
                "grade": "A",
            },
            {
                "instrument": "X4",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 5.0,
                "grade": "A",
            },
        ],
    )
    r = client.get("/api/ui/setups/financial")
    setups = r.get_json()["setups"]
    assert [s["instrument"] for s in setups] == ["X2", "X4", "X3", "X1"]


def test_setups_financial_hides_invalidated(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    _write_signals(
        signals_path,
        [
            {
                "instrument": "EURUSD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 3.0,
                "grade": "A",
                "invalidated": True,
            },
            {
                "instrument": "GOLD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 2.5,
                "grade": "B",
            },
        ],
    )
    r = client.get("/api/ui/setups/financial")
    data = r.get_json()
    assert data["total_count"] == 2
    assert data["visible_count"] == 1
    assert data["setups"][0]["instrument"] == "GOLD"


def test_setups_financial_limit_truncates(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    _write_signals(
        signals_path,
        [
            {
                "instrument": f"X{i}",
                "direction": "BUY",
                "horizon": "SWING",
                "score": float(10 - i),
                "grade": "A",
            }
            for i in range(10)
        ],
    )
    r = client.get("/api/ui/setups/financial?limit=3")
    data = r.get_json()
    assert data["visible_count"] == 3
    # Høyeste score først → X0, X1, X2
    assert [s["instrument"] for s in data["setups"]] == ["X0", "X1", "X2"]


def test_setups_financial_invalid_limit_returns_all(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    _write_signals(
        signals_path,
        [{"instrument": "X", "direction": "BUY", "horizon": "SWING", "score": 3.0, "grade": "A"}],
    )
    r = client.get("/api/ui/setups/financial?limit=abc")
    assert len(r.get_json()["setups"]) == 1


def test_setups_financial_corrupt_file_returns_empty(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    signals_path.write_text("{ not valid json")
    r = client.get("/api/ui/setups/financial")
    assert r.status_code == 200
    assert r.get_json()["setups"] == []


def test_setups_financial_non_list_toplevel(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    signals_path.write_text(json.dumps({"foo": "bar"}))
    r = client.get("/api/ui/setups/financial")
    assert r.get_json()["setups"] == []


def test_setups_financial_skips_non_dict_rows(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    """Ugyldige rader (ikke-dict) filtreres ut."""
    signals_path.write_text(
        json.dumps(
            [
                "not a dict",
                {
                    "instrument": "OK",
                    "direction": "BUY",
                    "horizon": "SWING",
                    "score": 3.0,
                    "grade": "A",
                },
                None,
            ]
        )
    )
    r = client.get("/api/ui/setups/financial")
    data = r.get_json()
    assert data["total_count"] == 1
    assert len(data["setups"]) == 1


def test_setups_agri_reads_agri_path(
    client: FlaskClient,
    agri_signals_path: Path,
    signals_path: Path,
) -> None:
    """Agri-endepunktet leser fra agri_signals_path, ikke signals_path."""
    _write_signals(
        signals_path,
        [
            {
                "instrument": "EURUSD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 3.0,
                "grade": "A",
            }
        ],
    )
    _write_signals(
        agri_signals_path,
        [
            {
                "instrument": "Corn",
                "direction": "BUY",
                "horizon": "MAKRO",
                "score": 4.0,
                "grade": "A",
            },
            {
                "instrument": "Wheat",
                "direction": "SELL",
                "horizon": "SWING",
                "score": 2.5,
                "grade": "B",
            },
        ],
    )
    r = client.get("/api/ui/setups/agri")
    data = r.get_json()
    assert data["total_count"] == 2
    assert [s["instrument"] for s in data["setups"]] == ["Corn", "Wheat"]


def test_setups_agri_empty_when_file_missing(client: FlaskClient) -> None:
    r = client.get("/api/ui/setups/agri")
    assert r.status_code == 200
    assert r.get_json()["setups"] == []


def test_setups_passes_through_setup_dict(
    client: FlaskClient,
    signals_path: Path,
) -> None:
    """`setup`-dict passerer uendret til frontend."""
    _write_signals(
        signals_path,
        [
            {
                "instrument": "GOLD",
                "direction": "BUY",
                "horizon": "SWING",
                "score": 4.0,
                "grade": "A",
                "setup": {"entry": 2050.25, "stop_loss": 2040.0, "target_1": 2070.0, "rr_t1": 2.5},
            },
        ],
    )
    r = client.get("/api/ui/setups/financial")
    setup = r.get_json()["setups"][0]["setup"]
    assert setup["entry"] == 2050.25
    assert setup["stop_loss"] == 2040.0
    assert setup["target_1"] == 2070.0
    assert setup["rr_t1"] == 2.5


# ─────────────────────────────────────────────────────────────
# /api/ui/pipeline_health (session 50 — Kartrommet)
# ─────────────────────────────────────────────────────────────


def test_pipeline_health_empty_db_all_missing(client: FlaskClient) -> None:
    """Tom database (ingen observasjoner) → alle kilder status='missing'."""
    r = client.get("/api/ui/pipeline_health")
    assert r.status_code == 200
    data = r.get_json()
    assert "groups" in data
    # Alle fetchere fra fetch_config_path skal være "missing"
    all_sources = [s for g in data["groups"] for s in g["sources"]]
    assert len(all_sources) == 4  # prices, cot_disaggregated, weather, unknown_fetcher
    for src in all_sources:
        assert src["status"] == "missing"
        assert src["age_hours"] is None
        assert src["latest_observation"] is None


def test_pipeline_health_groups_by_plan_categories(client: FlaskClient) -> None:
    """Fetchere grupperes per PLAN § 10.4."""
    r = client.get("/api/ui/pipeline_health")
    data = r.get_json()
    group_names = [g["name"] for g in data["groups"]]
    # Core kommer før CFTC, før Geo, før Other (per _GROUP_ORDER)
    assert group_names.index("Core") < group_names.index("CFTC")
    assert group_names.index("CFTC") < group_names.index("Geo")
    assert group_names.index("Geo") < group_names.index("Other")


def test_pipeline_health_unknown_fetcher_in_other_group(
    client: FlaskClient,
) -> None:
    """Fetchere som ikke er i _FETCHER_GROUPS havner i 'Other'."""
    r = client.get("/api/ui/pipeline_health")
    data = r.get_json()
    other = next(g for g in data["groups"] if g["name"] == "Other")
    assert any(s["name"] == "unknown_fetcher" for s in other["sources"])


def test_pipeline_health_fresh_status_under_stale_threshold(
    client: FlaskClient,
    db_path: Path,
) -> None:
    """Observasjon nyere enn stale_hours → status='fresh'."""
    import sqlite3
    from datetime import datetime, timedelta

    # Tvang DataStore til å opprette schema først (ellers er db tom)
    from bedrock.data.store import DataStore

    DataStore(db_path)  # initialiserer schema

    # Sett inn en prises-observasjon som er 1 time gammel (stale_hours=30)
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO prices (instrument, tf, ts, close) VALUES (?, ?, ?, ?)",
            ("Gold", "D1", one_hour_ago, 2050.0),
        )
        conn.commit()

    r = client.get("/api/ui/pipeline_health")
    data = r.get_json()
    prices = next(s for g in data["groups"] for s in g["sources"] if s["name"] == "prices")
    assert prices["status"] == "fresh"
    assert prices["age_hours"] is not None
    assert prices["age_hours"] < 2
    assert prices["latest_observation"] is not None


def test_pipeline_health_aging_between_1x_and_2x_stale(
    client: FlaskClient,
    db_path: Path,
) -> None:
    """Observasjon 1×-2×stale_hours gammel → status='aging'."""
    import sqlite3
    from datetime import datetime, timedelta

    from bedrock.data.store import DataStore

    DataStore(db_path)

    # 45 timer gammel (1.5 × 30)
    aging = (datetime.now(timezone.utc) - timedelta(hours=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO prices (instrument, tf, ts, close) VALUES (?, ?, ?, ?)",
            ("Gold", "D1", aging, 2050.0),
        )
        conn.commit()

    r = client.get("/api/ui/pipeline_health")
    prices = next(s for g in r.get_json()["groups"] for s in g["sources"] if s["name"] == "prices")
    assert prices["status"] == "aging"


def test_pipeline_health_stale_above_2x(
    client: FlaskClient,
    db_path: Path,
) -> None:
    """Observasjon > 2×stale_hours gammel → status='stale'."""
    import sqlite3
    from datetime import datetime, timedelta

    from bedrock.data.store import DataStore

    DataStore(db_path)

    # 100 timer gammel (> 2 × 30)
    old = (datetime.now(timezone.utc) - timedelta(hours=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO prices (instrument, tf, ts, close) VALUES (?, ?, ?, ?)",
            ("Gold", "D1", old, 2050.0),
        )
        conn.commit()

    r = client.get("/api/ui/pipeline_health")
    prices = next(s for g in r.get_json()["groups"] for s in g["sources"] if s["name"] == "prices")
    assert prices["status"] == "stale"


def test_pipeline_health_missing_fetch_config(
    tmp_path: Path,
    web_root: Path,
) -> None:
    """fetch.yaml ikke funnet → 200 + error-melding, tom groups."""
    cfg = ServerConfig(
        web_root=web_root,
        fetch_config_path=tmp_path / "does-not-exist.yaml",
        db_path=tmp_path / "x.db",
        trade_log_path=tmp_path / "log.json",
        signals_path=tmp_path / "s.json",
        agri_signals_path=tmp_path / "a.json",
    )
    client = create_app(cfg).test_client()
    r = client.get("/api/ui/pipeline_health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["groups"] == []
    assert "error" in data
    assert "ikke funnet" in data["error"]


def test_pipeline_health_includes_cron_and_stale_hours(
    client: FlaskClient,
) -> None:
    """Svar skal inkludere cron-streng + stale_hours per fetcher."""
    r = client.get("/api/ui/pipeline_health")
    prices = next(s for g in r.get_json()["groups"] for s in g["sources"] if s["name"] == "prices")
    assert prices["cron"] == "40 * * * 1-5"
    assert prices["stale_hours"] == 30
    assert prices["table"] == "prices"
    assert prices["module"] == "bedrock.fetch.prices"
