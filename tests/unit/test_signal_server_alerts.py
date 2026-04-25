"""Tester for /push-alert + /push-agri-alert + append_signal.

Fase 7 session 35.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    PersistedSignal,
    SignalStoreError,
)
from bedrock.signal_server.storage import append_signal, load_signals


def _valid_signal_dict() -> dict[str, object]:
    return {
        "instrument": "Gold",
        "direction": "BUY",
        "horizon": "SWING",
        "score": 0.73,
        "grade": "A",
    }


# ---------------------------------------------------------------------------
# append_signal — storage
# ---------------------------------------------------------------------------


def test_append_to_missing_file_creates_it(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    sig = PersistedSignal.model_validate(_valid_signal_dict())
    append_signal(path, sig)
    assert path.exists()
    loaded = load_signals(path)
    assert len(loaded) == 1
    assert loaded[0].instrument == "Gold"


def test_append_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "signals.json"
    sig = PersistedSignal.model_validate(_valid_signal_dict())
    append_signal(path, sig)
    assert path.exists()


def test_append_to_existing_preserves_order(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    first = PersistedSignal.model_validate({**_valid_signal_dict(), "instrument": "Gold"})
    second = PersistedSignal.model_validate({**_valid_signal_dict(), "instrument": "Silver"})
    append_signal(path, first)
    append_signal(path, second)

    loaded = load_signals(path)
    assert [s.instrument for s in loaded] == ["Gold", "Silver"]


def test_append_refuses_corrupt_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("{not json", encoding="utf-8")
    sig = PersistedSignal.model_validate(_valid_signal_dict())
    with pytest.raises(SignalStoreError):
        append_signal(path, sig)


def test_append_atomic_no_tmp_files_left_behind(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    sig = PersistedSignal.model_validate(_valid_signal_dict())
    append_signal(path, sig)

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".signals")]
    assert leftovers == []


def test_append_preserves_extra_fields(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    data = {**_valid_signal_dict(), "extra_field": "future_value"}
    sig = PersistedSignal.model_validate(data)
    append_signal(path, sig)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["extra_field"] == "future_value"


def test_append_concurrent_safe_under_sequential_access(tmp_path: Path) -> None:
    """Sekvensielle appends skal ikke miste data under låsing.

    Ikke en sann konkurranse-test (det krever fil-låsing), men verifiserer
    at hver append leser forrige og bevarer alle oppføringer.
    """
    path = tmp_path / "signals.json"
    signals = [
        PersistedSignal.model_validate({**_valid_signal_dict(), "instrument": f"Sym{i}"})
        for i in range(20)
    ]

    def _worker(sig: PersistedSignal) -> None:
        append_signal(path, sig)

    # Sekvensielle calls i thread (ikke ekte parallell pga GIL + file-I/O;
    # dette er en sanity-check snarere enn en race-test).
    for sig in signals:
        t = threading.Thread(target=_worker, args=(sig,))
        t.start()
        t.join()

    loaded = load_signals(path)
    assert len(loaded) == 20


# ---------------------------------------------------------------------------
# /push-alert + /push-agri-alert
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_files(tmp_path: Path):
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
    )
    return create_app(cfg), tmp_path


def test_push_alert_creates_signal(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/push-alert",
            json=_valid_signal_dict(),
        )

    assert response.status_code == 201
    body = response.get_json()
    assert body["instrument"] == "Gold"

    # Persistert på disk
    loaded = load_signals(tmp_path / "signals.json")
    assert len(loaded) == 1


def test_push_alert_rejects_non_json(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/push-alert",
            data="not json",
            content_type="text/plain",
        )
    assert response.status_code == 415
    assert "application/json" in response.get_json()["error"]


def test_push_alert_rejects_invalid_json(app_with_files) -> None:
    """Gyldig content-type men ugyldig JSON-body."""
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/push-alert",
            data="not json at all",
            content_type="application/json",
        )
    assert response.status_code == 400


def test_push_alert_rejects_array_body(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post("/push-alert", json=[1, 2])
    assert response.status_code == 400
    assert "JSON-objekt" in response.get_json()["error"]


def test_push_alert_rejects_invalid_direction(app_with_files) -> None:
    app, _ = app_with_files
    bad = {**_valid_signal_dict(), "direction": "HOLD"}
    with app.test_client() as client:
        response = client.post("/push-alert", json=bad)
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "validering feilet"
    assert any("direction" in str(d) for d in body["details"])


def test_push_alert_rejects_negative_score(app_with_files) -> None:
    app, _ = app_with_files
    bad = {**_valid_signal_dict(), "score": -0.5}
    with app.test_client() as client:
        response = client.post("/push-alert", json=bad)
    assert response.status_code == 400


def test_push_alert_rejects_missing_required_field(app_with_files) -> None:
    app, _ = app_with_files
    bad = _valid_signal_dict()
    del bad["grade"]
    with app.test_client() as client:
        response = client.post("/push-alert", json=bad)
    assert response.status_code == 400


def test_push_alert_returns_500_on_corrupt_existing_file(app_with_files) -> None:
    """Hvis fil er korrupt får vi 500 — ikke overskriv andres data."""
    app, tmp_path = app_with_files
    (tmp_path / "signals.json").write_text("{corrupt")
    with app.test_client() as client:
        response = client.post("/push-alert", json=_valid_signal_dict())
    assert response.status_code == 500


def test_push_alert_multiple_appends_preserve_order(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        client.post(
            "/push-alert",
            json={**_valid_signal_dict(), "instrument": "Gold"},
        )
        client.post(
            "/push-alert",
            json={**_valid_signal_dict(), "instrument": "Silver"},
        )
    loaded = load_signals(tmp_path / "signals.json")
    assert [s.instrument for s in loaded] == ["Gold", "Silver"]


def test_push_agri_alert_writes_to_agri_file(app_with_files) -> None:
    app, tmp_path = app_with_files
    agri = {**_valid_signal_dict(), "instrument": "Corn"}
    with app.test_client() as client:
        response = client.post("/push-agri-alert", json=agri)
    assert response.status_code == 201

    assert not (tmp_path / "signals.json").exists()
    assert (tmp_path / "agri_signals.json").exists()
    loaded = load_signals(tmp_path / "agri_signals.json")
    assert loaded[0].instrument == "Corn"


def test_financial_and_agri_kept_separate(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        client.post(
            "/push-alert",
            json={**_valid_signal_dict(), "instrument": "Gold"},
        )
        client.post(
            "/push-agri-alert",
            json={**_valid_signal_dict(), "instrument": "Corn"},
        )

    fin = load_signals(tmp_path / "signals.json")
    agri = load_signals(tmp_path / "agri_signals.json")
    assert [s.instrument for s in fin] == ["Gold"]
    assert [s.instrument for s in agri] == ["Corn"]


def test_push_alert_then_get_signals_roundtrip(app_with_files) -> None:
    """End-to-end: POST → GET leser tilbake samme data."""
    app, _ = app_with_files
    with app.test_client() as client:
        post_resp = client.post("/push-alert", json=_valid_signal_dict())
        get_resp = client.get("/signals")

    assert post_resp.status_code == 201
    assert get_resp.status_code == 200
    signals = get_resp.get_json()
    assert len(signals) == 1
    assert signals[0]["instrument"] == "Gold"


def test_push_alert_does_not_accept_get(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/push-alert")
    assert response.status_code == 405


def test_status_lists_alerts_endpoints(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/status")
    endpoints = response.get_json()["endpoints_registered"]
    assert "/push-alert" in endpoints
    assert "/push-agri-alert" in endpoints
