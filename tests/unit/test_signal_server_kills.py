"""Tester for kill-switch + /invalidate endepunkter.

Fase 7 session 36.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.schemas import (
    InvalidationRequest,
    KillSwitch,
    PersistedSignal,
    SignalStoreError,
)
from bedrock.signal_server.storage import (
    append_signal,
    clear_all_kills,
    invalidate_matching,
    load_kills,
    load_signals,
    upsert_kill,
)


def _valid_kill_dict() -> dict[str, object]:
    return {
        "instrument": "Gold",
        "horizon": "SWING",
        "reason": "manual override",
    }


def _valid_signal_dict() -> dict[str, object]:
    return {
        "instrument": "Gold",
        "direction": "BUY",
        "horizon": "SWING",
        "score": 0.73,
        "grade": "A",
    }


# ---------------------------------------------------------------------------
# KillSwitch schema
# ---------------------------------------------------------------------------


def test_kill_schema_valid() -> None:
    k = KillSwitch.model_validate(_valid_kill_dict())
    assert k.instrument == "Gold"
    assert k.slot == ("Gold", "SWING")


def test_kill_schema_rejects_invalid_horizon() -> None:
    with pytest.raises(Exception):
        KillSwitch.model_validate({"instrument": "Gold", "horizon": "OTHER"})


def test_kill_schema_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        KillSwitch.model_validate({**_valid_kill_dict(), "extra": "x"})


def test_kill_schema_default_timestamp() -> None:
    """killed_at skal auto-settes hvis ikke oppgitt."""
    k = KillSwitch.model_validate(
        {"instrument": "Gold", "horizon": "SWING"}
    )
    assert k.killed_at is not None


# ---------------------------------------------------------------------------
# InvalidationRequest schema
# ---------------------------------------------------------------------------


def test_invalidation_schema_valid() -> None:
    req = InvalidationRequest.model_validate(
        {
            "instrument": "Gold",
            "direction": "BUY",
            "horizon": "SWING",
            "reason": "stop-out risk",
        }
    )
    assert req.direction == "BUY"


def test_invalidation_schema_rejects_invalid_direction() -> None:
    with pytest.raises(Exception):
        InvalidationRequest.model_validate(
            {
                "instrument": "Gold",
                "direction": "HOLD",
                "horizon": "SWING",
            }
        )


# ---------------------------------------------------------------------------
# Kill storage
# ---------------------------------------------------------------------------


def test_load_kills_missing_file_empty(tmp_path: Path) -> None:
    assert load_kills(tmp_path / "kills.json") == []


def test_upsert_kill_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "kills.json"
    kill = KillSwitch.model_validate(_valid_kill_dict())
    upsert_kill(path, kill)
    assert path.exists()
    assert load_kills(path)[0].instrument == "Gold"


def test_upsert_kill_deduplicates_by_slot(tmp_path: Path) -> None:
    path = tmp_path / "kills.json"
    first = KillSwitch.model_validate(
        {**_valid_kill_dict(), "reason": "first"}
    )
    second = KillSwitch.model_validate(
        {**_valid_kill_dict(), "reason": "second"}
    )
    upsert_kill(path, first)
    upsert_kill(path, second)
    kills = load_kills(path)
    assert len(kills) == 1
    assert kills[0].reason == "second"


def test_upsert_kill_different_slots_coexist(tmp_path: Path) -> None:
    path = tmp_path / "kills.json"
    upsert_kill(
        path,
        KillSwitch.model_validate({**_valid_kill_dict(), "horizon": "SWING"}),
    )
    upsert_kill(
        path,
        KillSwitch.model_validate({**_valid_kill_dict(), "horizon": "SCALP"}),
    )
    kills = load_kills(path)
    assert len(kills) == 2
    assert {k.horizon for k in kills} == {"SWING", "SCALP"}


def test_clear_all_kills_returns_count(tmp_path: Path) -> None:
    path = tmp_path / "kills.json"
    upsert_kill(path, KillSwitch.model_validate(_valid_kill_dict()))
    upsert_kill(
        path,
        KillSwitch.model_validate({**_valid_kill_dict(), "horizon": "SCALP"}),
    )
    removed = clear_all_kills(path)
    assert removed == 2
    assert load_kills(path) == []


def test_load_kills_corrupt_raises(tmp_path: Path) -> None:
    path = tmp_path / "kills.json"
    path.write_text("{not json")
    with pytest.raises(SignalStoreError):
        load_kills(path)


# ---------------------------------------------------------------------------
# invalidate_matching
# ---------------------------------------------------------------------------


def test_invalidate_matching_no_file_returns_zero(tmp_path: Path) -> None:
    count = invalidate_matching(
        tmp_path / "signals.json",
        instrument="Gold",
        direction="BUY",
        horizon="SWING",
        reason="",
        now="2026-04-24T00:00:00",
    )
    assert count == 0


def test_invalidate_matching_marks_only_matching(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    # Tre signaler, bare én matcher
    append_signal(
        path,
        PersistedSignal.model_validate(_valid_signal_dict()),
    )
    append_signal(
        path,
        PersistedSignal.model_validate(
            {**_valid_signal_dict(), "direction": "SELL"}
        ),
    )
    append_signal(
        path,
        PersistedSignal.model_validate(
            {**_valid_signal_dict(), "horizon": "SCALP"}
        ),
    )

    count = invalidate_matching(
        path,
        instrument="Gold",
        direction="BUY",
        horizon="SWING",
        reason="test",
        now="2026-04-24T00:00:00",
    )
    assert count == 1

    # Sjekk at kun den matchende har invalidated-felter
    raw = json.loads(path.read_text())
    assert raw[0]["invalidated"] is True
    assert raw[0]["invalidated_reason"] == "test"
    assert "invalidated" not in raw[1]
    assert "invalidated" not in raw[2]


def test_invalidate_matching_no_match_leaves_file_untouched(
    tmp_path: Path,
) -> None:
    path = tmp_path / "signals.json"
    append_signal(path, PersistedSignal.model_validate(_valid_signal_dict()))
    original = path.read_text()

    count = invalidate_matching(
        path,
        instrument="Silver",
        direction="BUY",
        horizon="SWING",
        reason="",
        now="2026-04-24T00:00:00",
    )
    assert count == 0
    assert path.read_text() == original


# ---------------------------------------------------------------------------
# HTTP-endepunkter
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_files(tmp_path: Path):
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
        kill_switch_path=tmp_path / "kills.json",
    )
    return create_app(cfg), tmp_path


def test_post_kill_creates_kill(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        response = client.post("/kill", json=_valid_kill_dict())
    assert response.status_code == 201
    kills = load_kills(tmp_path / "kills.json")
    assert len(kills) == 1


def test_post_kill_idempotent_same_slot(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        client.post("/kill", json=_valid_kill_dict())
        client.post(
            "/kill", json={**_valid_kill_dict(), "reason": "updated"}
        )
    kills = load_kills(tmp_path / "kills.json")
    assert len(kills) == 1
    assert kills[0].reason == "updated"


def test_post_kill_rejects_bad_horizon(app_with_files) -> None:
    app, _ = app_with_files
    bad = {**_valid_kill_dict(), "horizon": "BAD"}
    with app.test_client() as client:
        response = client.post("/kill", json=bad)
    assert response.status_code == 400


def test_post_kill_requires_json(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/kill", data="hello", content_type="text/plain"
        )
    assert response.status_code == 415


def test_get_kills_returns_list(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        client.post("/kill", json=_valid_kill_dict())
        client.post(
            "/kill", json={**_valid_kill_dict(), "horizon": "SCALP"}
        )
        response = client.get("/kills")
    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2


def test_get_kills_empty(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/kills")
    assert response.status_code == 200
    assert response.get_json() == []


def test_clear_kills_returns_count(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        client.post("/kill", json=_valid_kill_dict())
        client.post(
            "/kill", json={**_valid_kill_dict(), "horizon": "SCALP"}
        )
        response = client.post("/clear_kills")
    assert response.status_code == 200
    assert response.get_json()["removed"] == 2


def test_clear_kills_on_empty_returns_zero(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post("/clear_kills")
    assert response.status_code == 200
    assert response.get_json()["removed"] == 0


# ---------------------------------------------------------------------------
# /invalidate
# ---------------------------------------------------------------------------


def test_invalidate_marks_matching_signal(app_with_files) -> None:
    app, tmp_path = app_with_files
    with app.test_client() as client:
        client.post("/push-alert", json=_valid_signal_dict())
        client.post(
            "/push-alert",
            json={**_valid_signal_dict(), "direction": "SELL"},
        )

        response = client.post(
            "/invalidate",
            json={
                "instrument": "Gold",
                "direction": "BUY",
                "horizon": "SWING",
                "reason": "stop-out risk",
            },
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["financial_matched"] == 1
    assert body["agri_matched"] == 0
    assert body["total"] == 1

    # Verifiser at SELL-signalet ikke er markert
    signals = load_signals(tmp_path / "signals.json")
    matched = [s.model_dump() for s in signals]
    invalidated = [s for s in matched if s.get("invalidated")]
    untouched = [s for s in matched if not s.get("invalidated")]
    assert len(invalidated) == 1
    assert invalidated[0]["direction"] == "BUY"
    assert len(untouched) == 1
    assert untouched[0]["direction"] == "SELL"


def test_invalidate_also_checks_agri_file(app_with_files) -> None:
    app, _ = app_with_files
    agri = {**_valid_signal_dict(), "instrument": "Corn"}
    with app.test_client() as client:
        client.post("/push-agri-alert", json=agri)
        response = client.post(
            "/invalidate",
            json={
                "instrument": "Corn",
                "direction": "BUY",
                "horizon": "SWING",
            },
        )
    assert response.get_json()["agri_matched"] == 1


def test_invalidate_no_match_returns_zero(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        client.post("/push-alert", json=_valid_signal_dict())
        response = client.post(
            "/invalidate",
            json={
                "instrument": "Silver",
                "direction": "BUY",
                "horizon": "SWING",
            },
        )
    assert response.status_code == 200
    assert response.get_json()["total"] == 0


def test_invalidate_rejects_bad_direction(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/invalidate",
            json={
                "instrument": "Gold",
                "direction": "BAD",
                "horizon": "SWING",
            },
        )
    assert response.status_code == 400


def test_invalidate_requires_json(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/invalidate", data="x", content_type="text/plain"
        )
    assert response.status_code == 415


def test_status_lists_new_endpoints(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/status")
    endpoints = response.get_json()["endpoints_registered"]
    for ep in ("/kill", "/kills", "/clear_kills", "/invalidate"):
        assert ep in endpoints, f"{ep} not in {endpoints}"
