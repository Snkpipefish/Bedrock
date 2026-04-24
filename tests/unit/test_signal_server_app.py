"""Tester for signal-server app-factory + meta-endepunkter.

Fase 7 session 33 — skeleton-nivå: kun `/health` og `/status` finnes.
Endepunkt-spesifikke tester kommer i senere sessions per
ENDPOINTS.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask

from bedrock.signal_server import create_app
from bedrock.signal_server.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ServerConfig,
    load_from_env,
)


# ---------------------------------------------------------------------------
# ServerConfig
# ---------------------------------------------------------------------------


def test_server_config_defaults() -> None:
    cfg = ServerConfig()
    assert cfg.host == DEFAULT_HOST
    assert cfg.port == DEFAULT_PORT
    assert cfg.port != 5000  # må avvike fra gammel scalp_edge under parallell
    assert cfg.server_name == "bedrock-signal-server"
    assert str(cfg.signals_path).endswith("signals.json")


def test_server_config_frozen() -> None:
    """Config skal være immutable — forhindrer at endepunkter muterer den."""
    cfg = ServerConfig()
    with pytest.raises(Exception):  # Pydantic frozen -> ValidationError
        cfg.port = 1234  # type: ignore[misc]


def test_server_config_rejects_unknown_field() -> None:
    with pytest.raises(Exception):
        ServerConfig(random_field="x")  # type: ignore[call-arg]


def test_server_config_custom_values() -> None:
    cfg = ServerConfig(
        port=6000, data_root=Path("/tmp/bedrock-test")
    )
    assert cfg.port == 6000
    assert cfg.data_root == Path("/tmp/bedrock-test")


def test_load_from_env_overrides() -> None:
    cfg = load_from_env(
        {
            "BEDROCK_SERVER_HOST": "0.0.0.0",
            "BEDROCK_SERVER_PORT": "5200",
            "BEDROCK_DATA_ROOT": "/opt/bedrock",
        }
    )
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 5200
    assert cfg.data_root == Path("/opt/bedrock")


def test_load_from_env_empty_uses_defaults() -> None:
    cfg = load_from_env({})
    assert cfg.port == DEFAULT_PORT


def test_load_from_env_invalid_port_raises() -> None:
    with pytest.raises(ValueError):
        load_from_env({"BEDROCK_SERVER_PORT": "not-a-number"})


# ---------------------------------------------------------------------------
# create_app — app-factory
# ---------------------------------------------------------------------------


def test_create_app_returns_flask() -> None:
    app = create_app()
    assert isinstance(app, Flask)


def test_create_app_uses_default_config_when_none() -> None:
    app = create_app()
    cfg = app.extensions["bedrock_config"]
    assert isinstance(cfg, ServerConfig)
    assert cfg.port == DEFAULT_PORT


def test_create_app_uses_custom_config() -> None:
    custom = ServerConfig(port=5999)
    app = create_app(custom)
    assert app.extensions["bedrock_config"].port == 5999


def test_create_app_returns_new_instance_each_call() -> None:
    """Forhindrer at tester deler state utilsiktet."""
    a = create_app()
    b = create_app()
    assert a is not b


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok() -> None:
    app = create_app()
    with app.test_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["server"] == "bedrock-signal-server"


def test_health_is_get_only() -> None:
    app = create_app()
    with app.test_client() as client:
        response = client.post("/health")
    assert response.status_code == 405  # Method Not Allowed


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


def test_status_returns_config_summary() -> None:
    app = create_app(ServerConfig(port=5123, host="0.0.0.0"))
    with app.test_client() as client:
        response = client.get("/status")
    assert response.status_code == 200
    body = response.get_json()
    assert body["server"] == "bedrock-signal-server"
    assert body["port"] == 5123
    assert body["host"] == "0.0.0.0"


def test_status_lists_registered_endpoints() -> None:
    app = create_app()
    with app.test_client() as client:
        response = client.get("/status")
    endpoints = response.get_json()["endpoints_registered"]
    # Meta-endepunkter fra session 33
    assert "/health" in endpoints
    assert "/status" in endpoints
    # Disse kommer i senere sessions — sjekk at de IKKE er her ennå
    assert "/admin/rules" not in endpoints


# ---------------------------------------------------------------------------
# 404 for ikke-eksisterende endepunkter (robust-sjekk)
# ---------------------------------------------------------------------------


def test_unknown_endpoint_returns_404() -> None:
    app = create_app()
    with app.test_client() as client:
        response = client.get("/this-does-not-exist")
    assert response.status_code == 404
