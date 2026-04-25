"""Tester for /push-prices + /prices + /upload.

Fase 7 session 37.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from bedrock.data.store import DataStore
from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig


@pytest.fixture
def app_with_files(tmp_path: Path):
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
        kill_switch_path=tmp_path / "kills.json",
        db_path=tmp_path / "bedrock.db",
        uploads_root=tmp_path / "uploads",
    )
    return create_app(cfg), tmp_path


def _bar(ts: str, close: float) -> dict:
    return {"ts": ts, "close": close}


# ---------------------------------------------------------------------------
# /push-prices
# ---------------------------------------------------------------------------


def test_push_prices_writes_to_datastore(app_with_files) -> None:
    app, tmp_path = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [
            _bar("2026-04-20T00:00:00", 2000.0),
            _bar("2026-04-21T00:00:00", 2010.0),
            _bar("2026-04-22T00:00:00", 2020.0),
        ],
    }
    with app.test_client() as client:
        response = client.post("/push-prices", json=body)

    assert response.status_code == 201
    data = response.get_json()
    assert data["bars_written"] == 3

    # Verifiser via ekte DataStore
    store = DataStore(tmp_path / "bedrock.db")
    series = store.get_prices("Gold", tf="D1", lookback=10)
    assert len(series) == 3


def test_push_prices_ohlc_optional_fields(app_with_files) -> None:
    app, tmp_path = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [
            {
                "ts": "2026-04-20T00:00:00",
                "open": 1995.0,
                "high": 2010.0,
                "low": 1990.0,
                "close": 2000.0,
                "volume": 5000.0,
            }
        ],
    }
    with app.test_client() as client:
        response = client.post("/push-prices", json=body)
    assert response.status_code == 201


def test_push_prices_empty_bars_rejected(app_with_files) -> None:
    app, _ = app_with_files
    body = {"instrument": "Gold", "tf": "D1", "bars": []}
    with app.test_client() as client:
        response = client.post("/push-prices", json=body)
    assert response.status_code == 400


def test_push_prices_missing_close_rejected(app_with_files) -> None:
    app, _ = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [{"ts": "2026-04-20T00:00:00"}],
    }
    with app.test_client() as client:
        response = client.post("/push-prices", json=body)
    assert response.status_code == 400


def test_push_prices_extra_field_rejected(app_with_files) -> None:
    """extra='forbid' på PushPricesRequest."""
    app, _ = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [_bar("2026-04-20T00:00:00", 2000.0)],
        "rogue_field": "ignored",
    }
    with app.test_client() as client:
        response = client.post("/push-prices", json=body)
    assert response.status_code == 400


def test_push_prices_idempotent_same_ts(app_with_files) -> None:
    """Samme (instrument, tf, ts) skrives via INSERT OR REPLACE."""
    app, tmp_path = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [_bar("2026-04-20T00:00:00", 2000.0)],
    }
    body_updated = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [_bar("2026-04-20T00:00:00", 2050.0)],
    }
    with app.test_client() as client:
        client.post("/push-prices", json=body)
        client.post("/push-prices", json=body_updated)

    store = DataStore(tmp_path / "bedrock.db")
    series = store.get_prices("Gold", tf="D1", lookback=10)
    assert len(series) == 1
    assert float(series.iloc[0]) == 2050.0


def test_push_prices_requires_json(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post("/push-prices", data="x", content_type="text/plain")
    assert response.status_code == 415


# ---------------------------------------------------------------------------
# /prices
# ---------------------------------------------------------------------------


def test_prices_requires_instrument(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/prices?tf=D1")
    assert response.status_code == 400
    assert "instrument" in response.get_json()["error"]


def test_prices_requires_tf(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/prices?instrument=Gold")
    assert response.status_code == 400
    assert "tf" in response.get_json()["error"]


def test_prices_empty_store_returns_empty_list(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/prices?instrument=Gold&tf=D1")
    assert response.status_code == 200
    body = response.get_json()
    assert body["bars"] == []


def test_prices_roundtrip_after_push(app_with_files) -> None:
    app, _ = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [
            _bar("2026-04-20T00:00:00", 2000.0),
            _bar("2026-04-21T00:00:00", 2010.0),
        ],
    }
    with app.test_client() as client:
        client.post("/push-prices", json=body)
        response = client.get("/prices?instrument=Gold&tf=D1")

    bars = response.get_json()["bars"]
    assert len(bars) == 2
    assert bars[0]["close"] == 2000.0
    assert bars[1]["close"] == 2010.0


def test_prices_last_n_limits_output(app_with_files) -> None:
    app, _ = app_with_files
    body = {
        "instrument": "Gold",
        "tf": "D1",
        "bars": [_bar(f"2026-04-{d:02d}T00:00:00", 2000.0 + d) for d in range(1, 6)],
    }
    with app.test_client() as client:
        client.post("/push-prices", json=body)
        response = client.get("/prices?instrument=Gold&tf=D1&last_n=2")

    bars = response.get_json()["bars"]
    assert len(bars) == 2


def test_prices_last_n_invalid(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/prices?instrument=Gold&tf=D1&last_n=not-a-number")
    assert response.status_code == 400


def test_prices_last_n_zero_invalid(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/prices?instrument=Gold&tf=D1&last_n=0")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# /upload
# ---------------------------------------------------------------------------


def _png_bytes(size: int = 100) -> bytes:
    """Mini-PNG-header + padding. Server validerer ikke magic bytes."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * (size - 8)


def test_upload_valid_png(app_with_files) -> None:
    app, tmp_path = app_with_files
    data = _png_bytes(500)
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={
                "file": (io.BytesIO(data), "chart.png"),
            },
            content_type="multipart/form-data",
        )
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["filename"] == "chart.png"
    assert body["size_bytes"] == 500

    uploaded = tmp_path / "uploads"
    files = list(uploaded.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".png"
    assert files[0].read_bytes() == data


def test_upload_missing_file_field(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={"no_file": "x"},
            content_type="multipart/form-data",
        )
    assert response.status_code == 400


def test_upload_rejects_disallowed_extension(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={"file": (io.BytesIO(b"x"), "script.exe")},
            content_type="multipart/form-data",
        )
    assert response.status_code == 400
    body = response.get_json()
    assert ".exe" in body["error"]


def test_upload_rejects_empty_file(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={"file": (io.BytesIO(b""), "empty.png")},
            content_type="multipart/form-data",
        )
    assert response.status_code == 400


def test_upload_rejects_too_large(app_with_files) -> None:
    app, tmp_path = app_with_files
    cfg = app.extensions["bedrock_config"]
    big = b"\x00" * (cfg.upload_max_bytes + 1)
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={"file": (io.BytesIO(big), "big.pdf")},
            content_type="multipart/form-data",
        )
    assert response.status_code == 413


def test_upload_accepts_jpeg_jpg_pdf(app_with_files) -> None:
    app, _ = app_with_files
    for name in ("a.jpg", "b.jpeg", "c.pdf"):
        with app.test_client() as client:
            response = client.post(
                "/upload",
                data={"file": (io.BytesIO(b"data1234"), name)},
                content_type="multipart/form-data",
            )
        assert response.status_code == 201, f"{name} failed"


def test_upload_stores_uuid_name(app_with_files) -> None:
    """Filnavnet på disk er uuid + ext, ikke klientens filnavn."""
    app, tmp_path = app_with_files
    with app.test_client() as client:
        response = client.post(
            "/upload",
            data={"file": (io.BytesIO(b"x" * 100), "secret.png")},
            content_type="multipart/form-data",
        )
    stored = response.get_json()["stored_as"]
    assert "secret.png" not in stored
    assert stored.endswith(".png")


# ---------------------------------------------------------------------------
# Status-endepunkt listing
# ---------------------------------------------------------------------------


def test_status_lists_new_endpoints(app_with_files) -> None:
    app, _ = app_with_files
    with app.test_client() as client:
        response = client.get("/status")
    endpoints = response.get_json()["endpoints_registered"]
    for ep in ("/push-prices", "/prices", "/upload"):
        assert ep in endpoints, f"{ep} not in {endpoints}"
