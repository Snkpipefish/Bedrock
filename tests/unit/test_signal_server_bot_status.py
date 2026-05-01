"""Tester for `/api/ui/bot_status` endpoint (sub-fase 12.9 D5).

Verifiserer at endpointet leverer service-state + daily-loss + last-trade +
signals_bot.json-alder, og at missing files håndteres tolerant uten 500.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig


def _make_app(*, bot_state_dir: Path, signals_bot_path: Path | None = None) -> object:
    cfg = ServerConfig(
        bot_state_dir=bot_state_dir,
        signals_bot_path=signals_bot_path or (bot_state_dir / "signals_bot.json"),
    )
    return create_app(cfg)


@pytest.fixture
def client(tmp_path: Path):
    bot_dir = tmp_path / "bot"
    bot_dir.mkdir()
    signals_bot = tmp_path / "signals_bot.json"
    app = _make_app(bot_state_dir=bot_dir, signals_bot_path=signals_bot)
    return app.test_client(), bot_dir, signals_bot


def test_bot_status_missing_everything(client) -> None:
    """Ingen state-filer + ingen systemd → endpoint svarer 200 m/ defaults."""
    c, _bot_dir, _signals = client
    with patch("bedrock.signal_server.endpoints.ui._systemctl_user_is_active") as mock:
        mock.return_value = ("inactive", "dead")
        resp = c.get("/api/ui/bot_status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"]["state"] == "inactive"
    assert body["service"]["sub_state"] == "dead"
    assert body["service"]["name"] == "bedrock-bot.service"
    assert body["daily_loss"] == {}
    assert body["last_trade"] is None
    assert body["signals_bot"]["exists"] is False
    assert body["signals_bot"]["age_seconds"] is None
    assert "last_check" in body


def test_bot_status_with_daily_loss_and_trade(client, tmp_path: Path) -> None:
    """Når state-filer finnes, parser endpointet dem korrekt."""
    c, bot_dir, signals = client

    daily = bot_dir / "daily_loss_state.json"
    daily.write_text(json.dumps({"date": "2026-05-01", "daily_loss": 42.50}))

    trade_log = bot_dir / "trade_log.jsonl"
    trade_log.write_text(
        json.dumps({"instrument": "AUDUSD", "direction": "buy"})
        + "\n"
        + json.dumps(
            {
                "instrument": "GOLD",
                "direction": "sell",
                "horizon": "SWING",
                "result": "T1_HIT",
                "pnl_usd": 12.34,
                "closed_at": "2026-05-01T15:30:00Z",
            }
        )
        + "\n"
    )

    signals.write_text("[]")

    with patch("bedrock.signal_server.endpoints.ui._systemctl_user_is_active") as mock:
        mock.return_value = ("active", "running")
        resp = c.get("/api/ui/bot_status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"]["state"] == "active"
    assert body["service"]["sub_state"] == "running"
    assert body["daily_loss"]["date"] == "2026-05-01"
    assert body["daily_loss"]["daily_loss"] == 42.50
    assert body["last_trade"]["instrument"] == "GOLD"
    assert body["last_trade"]["direction"] == "sell"
    assert body["last_trade"]["result"] == "T1_HIT"
    assert body["last_trade"]["pnl_usd"] == 12.34
    assert body["signals_bot"]["exists"] is True
    assert body["signals_bot"]["age_seconds"] is not None
    assert body["signals_bot"]["age_seconds"] >= 0


def test_bot_status_corrupt_daily_loss_tolerated(client) -> None:
    """Korrupt daily_loss_state.json → returneres som tom dict, ikke 500."""
    c, bot_dir, _signals = client
    (bot_dir / "daily_loss_state.json").write_text("not-json")

    with patch("bedrock.signal_server.endpoints.ui._systemctl_user_is_active") as mock:
        mock.return_value = ("inactive", "dead")
        resp = c.get("/api/ui/bot_status")
    assert resp.status_code == 200
    assert resp.get_json()["daily_loss"] == {}


def test_bot_status_empty_trade_log(client) -> None:
    """Tom trade_log.jsonl → last_trade=None, ikke 500."""
    c, bot_dir, _signals = client
    (bot_dir / "trade_log.jsonl").write_text("")

    with patch("bedrock.signal_server.endpoints.ui._systemctl_user_is_active") as mock:
        mock.return_value = ("inactive", "dead")
        resp = c.get("/api/ui/bot_status")
    assert resp.status_code == 200
    assert resp.get_json()["last_trade"] is None


def test_bot_status_systemctl_unavailable_no_proc(client) -> None:
    """systemctl + /proc-fallback begge negative → state=inactive."""
    c, _bot_dir, _signals = client

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch(
            "bedrock.signal_server.endpoints.ui._bedrock_bot_proc_running",
            return_value=False,
        ),
    ):
        resp = c.get("/api/ui/bot_status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"]["state"] == "inactive"
    assert body["service"]["sub_state"] == "dead"


def test_bot_status_proc_fallback_when_systemctl_silent(client) -> None:
    """systemctl gir tomme felter → /proc-fallback rapporterer running hvis bot-pid finnes."""
    c, _bot_dir, _signals = client

    fake_result = type("R", (), {"stdout": "ActiveState=\nSubState=\n", "returncode": 0})()
    with (
        patch("subprocess.run", return_value=fake_result),
        patch(
            "bedrock.signal_server.endpoints.ui._bedrock_bot_proc_running",
            return_value=True,
        ),
    ):
        resp = c.get("/api/ui/bot_status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"]["state"] == "active"
    assert body["service"]["sub_state"] == "running"


def test_pipeline_health_includes_horizons(tmp_path: Path) -> None:
    """`/api/ui/pipeline_health` har `horizons`-felt per § 20.2 mapping."""
    cfg = ServerConfig(
        fetch_config_path=Path("config/fetch.yaml"),
    )
    app = create_app(cfg)
    c = app.test_client()
    resp = c.get("/api/ui/pipeline_health")
    assert resp.status_code == 200
    body = resp.get_json()

    found_known = False
    for grp in body.get("groups", []):
        for src in grp.get("sources", []):
            assert "horizons" in src, f"{src['name']} mangler horizons-felt"
            assert isinstance(src["horizons"], list)
            if src["name"] == "calendar_ff":
                assert src["horizons"] == ["Sw", "Sc"]
                found_known = True
            if src["name"] == "prices":
                assert "M" in src["horizons"]
                assert "Sw" in src["horizons"]
                assert "Sc" in src["horizons"]
            # Per § 20.2: COT er primærkilde alle 3 horisonter
            # (M=percentil, Sw=delta, Sc=fre-release-event)
            if src["name"] == "cot_disaggregated":
                assert src["horizons"] == ["M", "Sw", "Sc"]
            # Crop_progress er mandag-release → scalp-event også
            if src["name"] == "crop_progress":
                assert "Sc" in src["horizons"]
            # Crypto_sentiment: intra-day, ikke macro
            if src["name"] == "crypto_sentiment":
                assert src["horizons"] == ["Sw", "Sc"]
    assert found_known, "calendar_ff burde være i fetch.yaml + horisont-mapping"
