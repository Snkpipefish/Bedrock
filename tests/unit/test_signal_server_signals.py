"""Tester for `/signals` + `/agri-signals` endepunktene + storage-laget.

Fase 7 session 34. Tester både schema-validering, storage-I/O, og
HTTP-endepunktene end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    PersistedSignal,
    SignalStoreError,
)
from bedrock.signal_server.storage import load_signals


# ---------------------------------------------------------------------------
# PersistedSignal schema
# ---------------------------------------------------------------------------


def _valid_signal_dict() -> dict[str, object]:
    return {
        "instrument": "Gold",
        "direction": "BUY",
        "horizon": "SWING",
        "score": 0.73,
        "grade": "A",
    }


def test_persisted_signal_valid() -> None:
    sig = PersistedSignal.model_validate(_valid_signal_dict())
    assert sig.instrument == "Gold"
    assert sig.direction == "BUY"
    assert sig.horizon == "SWING"


def test_persisted_signal_allows_extra_fields() -> None:
    """Ukjente felter (fra orchestrator-fremtid) skal passere gjennom."""
    data = _valid_signal_dict()
    data["extra_new_field"] = {"nested": True}
    sig = PersistedSignal.model_validate(data)
    dumped = sig.model_dump()
    assert dumped["extra_new_field"] == {"nested": True}


def test_persisted_signal_rejects_invalid_direction() -> None:
    data = _valid_signal_dict()
    data["direction"] = "HOLD"
    with pytest.raises(ValidationError, match="BUY/SELL"):
        PersistedSignal.model_validate(data)


def test_persisted_signal_rejects_invalid_horizon() -> None:
    data = _valid_signal_dict()
    data["horizon"] = "INTRADAY"
    with pytest.raises(ValidationError, match="SCALP/SWING/MAKRO"):
        PersistedSignal.model_validate(data)


def test_persisted_signal_rejects_negative_score() -> None:
    data = _valid_signal_dict()
    data["score"] = -0.1
    with pytest.raises(ValidationError, match="score"):
        PersistedSignal.model_validate(data)


def test_persisted_signal_missing_required_field() -> None:
    data = _valid_signal_dict()
    del data["grade"]
    with pytest.raises(ValidationError):
        PersistedSignal.model_validate(data)


# ---------------------------------------------------------------------------
# load_signals — storage-laget
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_signals(tmp_path / "nope.json") == []


def test_load_empty_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("", encoding="utf-8")
    assert load_signals(path) == []


def test_load_whitespace_only_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("   \n  \t\n", encoding="utf-8")
    assert load_signals(path) == []


def test_load_empty_array_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("[]", encoding="utf-8")
    assert load_signals(path) == []


def test_load_valid_array(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps([_valid_signal_dict(), _valid_signal_dict()]),
        encoding="utf-8",
    )
    entries = load_signals(path)
    assert len(entries) == 2
    assert entries[0].instrument == "Gold"


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("{not valid", encoding="utf-8")
    with pytest.raises(SignalStoreError, match="ikke gyldig JSON"):
        load_signals(path)


def test_load_non_array_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text('{"signals": []}', encoding="utf-8")
    with pytest.raises(SignalStoreError, match="JSON-array"):
        load_signals(path)


def test_load_non_object_row_raises(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text('[1, 2, 3]', encoding="utf-8")
    with pytest.raises(SignalStoreError, match="objekt"):
        load_signals(path)


def test_load_invalid_row_includes_index(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    bad = _valid_signal_dict()
    bad["direction"] = "INVALID"
    path.write_text(
        json.dumps([_valid_signal_dict(), bad]),
        encoding="utf-8",
    )
    with pytest.raises(SignalStoreError, match=r"\[1\]"):
        load_signals(path)


# ---------------------------------------------------------------------------
# HTTP-endepunkter
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_files(tmp_path: Path):
    """App med signals_path + agri_signals_path i tmp_path."""
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
    )
    return create_app(cfg), tmp_path


def test_signals_endpoint_missing_file_returns_empty(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/signals")
    assert response.status_code == 200
    assert response.get_json() == []


def test_signals_endpoint_returns_valid_content(app_with_files) -> None:
    app, tmp_path = app_with_files
    signals = [_valid_signal_dict()]
    (tmp_path / "signals.json").write_text(json.dumps(signals))
    with app.test_client() as client:
        response = client.get("/signals")
    body = response.get_json()
    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["instrument"] == "Gold"


def test_signals_endpoint_corrupt_file_returns_500(app_with_files) -> None:
    app, tmp_path = app_with_files
    (tmp_path / "signals.json").write_text("not json at all")
    with app.test_client() as client:
        response = client.get("/signals")
    assert response.status_code == 500
    assert "error" in response.get_json()


def test_signals_endpoint_validation_error_returns_500(app_with_files) -> None:
    app, tmp_path = app_with_files
    bad = _valid_signal_dict()
    bad["direction"] = "NONE"
    (tmp_path / "signals.json").write_text(json.dumps([bad]))
    with app.test_client() as client:
        response = client.get("/signals")
    assert response.status_code == 500


def test_agri_signals_endpoint_reads_separate_file(app_with_files) -> None:
    """agri og financial må være to separate filer, ikke dele state."""
    app, tmp_path = app_with_files
    financial = _valid_signal_dict()
    agri = {**_valid_signal_dict(), "instrument": "Corn"}
    (tmp_path / "signals.json").write_text(json.dumps([financial]))
    (tmp_path / "agri_signals.json").write_text(json.dumps([agri]))

    with app.test_client() as client:
        fin_resp = client.get("/signals")
        agri_resp = client.get("/agri-signals")

    assert fin_resp.get_json()[0]["instrument"] == "Gold"
    assert agri_resp.get_json()[0]["instrument"] == "Corn"


def test_agri_signals_endpoint_missing_file_returns_empty(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/agri-signals")
    assert response.status_code == 200
    assert response.get_json() == []


def test_extra_fields_roundtrip_through_endpoint(app_with_files) -> None:
    """Orchestrator-framtids-felter må bevares i JSON-responsen."""
    app, tmp_path = app_with_files
    sig = {**_valid_signal_dict(), "future_field": "abc"}
    (tmp_path / "signals.json").write_text(json.dumps([sig]))
    with app.test_client() as client:
        response = client.get("/signals")
    assert response.get_json()[0]["future_field"] == "abc"


def test_status_now_lists_signal_endpoints() -> None:
    """Session 34 registrerte nye endepunkter — /status må reflektere dem."""
    app = create_app()
    with app.test_client() as client:
        response = client.get("/status")
    endpoints = response.get_json()["endpoints_registered"]
    assert "/signals" in endpoints
    assert "/agri-signals" in endpoints
