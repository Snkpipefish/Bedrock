"""Tester for default-skjul-unpublished i UI-endpoints (session 94)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bedrock.signal_server.app import create_app
from bedrock.signal_server.config import ServerConfig


@pytest.fixture
def app(tmp_path: Path):
    """Lag app med tom data-katalog som vi populerer per test."""
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
    )
    return create_app(cfg)


@pytest.fixture
def client(app):
    return app.test_client()


def _write_signals(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries))


def test_financial_default_hides_unpublished(client, app) -> None:
    """Default skal kun returnere published=True."""
    cfg = app.extensions["bedrock_config"]
    _write_signals(
        cfg.signals_path,
        [
            {"instrument": "Gold", "score": 5.0, "grade": "A", "published": True},
            {"instrument": "Silver", "score": 4.0, "grade": "B", "published": False},
            {"instrument": "Brent", "score": 3.0, "grade": "C", "published": True},
        ],
    )
    resp = client.get("/api/ui/setups/financial")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_count"] == 3
    assert data["visible_count"] == 2  # kun de 2 published
    instruments = {s["instrument"] for s in data["setups"]}
    assert instruments == {"Gold", "Brent"}


def test_financial_include_unpublished_shows_all(client, app) -> None:
    """?include_unpublished=1 skal vise alle (utenom invalidated)."""
    cfg = app.extensions["bedrock_config"]
    _write_signals(
        cfg.signals_path,
        [
            {"instrument": "Gold", "score": 5.0, "grade": "A", "published": True},
            {"instrument": "Silver", "score": 4.0, "grade": "B", "published": False},
        ],
    )
    resp = client.get("/api/ui/setups/financial?include_unpublished=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["visible_count"] == 2


def test_financial_invalidated_always_hidden(client, app) -> None:
    """Invalidated skal alltid skjules — også med include_unpublished."""
    cfg = app.extensions["bedrock_config"]
    _write_signals(
        cfg.signals_path,
        [
            {
                "instrument": "Gold",
                "score": 5.0,
                "grade": "A",
                "published": True,
                "invalidated": True,
            },
            {"instrument": "Silver", "score": 4.0, "grade": "A", "published": True},
        ],
    )
    resp = client.get("/api/ui/setups/financial?include_unpublished=1")
    data = resp.get_json()
    assert data["visible_count"] == 1
    assert data["setups"][0]["instrument"] == "Silver"


def test_agri_endpoint_uses_same_filter(client, app) -> None:
    """Agri-endepunktet skal også default-filtrere unpublished."""
    cfg = app.extensions["bedrock_config"]
    _write_signals(
        cfg.agri_signals_path,
        [
            {"instrument": "Wheat", "score": 8.0, "grade": "A", "published": True},
            {"instrument": "Corn", "score": 6.0, "grade": "B", "published": False},
        ],
    )
    resp = client.get("/api/ui/setups/agri")
    data = resp.get_json()
    assert data["total_count"] == 2
    assert data["visible_count"] == 1
    assert data["setups"][0]["instrument"] == "Wheat"


def test_include_unpublished_accepts_various_truthy_values(client, app) -> None:
    cfg = app.extensions["bedrock_config"]
    _write_signals(
        cfg.signals_path,
        [{"instrument": "Gold", "published": False, "score": 1.0, "grade": "C"}],
    )
    for truthy in ("1", "true", "yes", "TRUE"):
        resp = client.get(f"/api/ui/setups/financial?include_unpublished={truthy}")
        data = resp.get_json()
        assert data["visible_count"] == 1, f"failed for {truthy}"
