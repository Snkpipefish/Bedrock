"""Tester for /admin/rules endepunktene.

Fase 7 session 38.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from textwrap import dedent

import pytest

from bedrock.config.instruments import (
    InstrumentConfigError,
    load_instrument_from_yaml_string,
)
from bedrock.signal_server import create_app
from bedrock.signal_server.config import ServerConfig

ADMIN_CODE = "test-secret-xyz"


@pytest.fixture
def instruments_dir(tmp_path: Path) -> Path:
    """Kopier gold.yaml til tmp slik at vi ikke rører repo-state."""
    src = Path("config/instruments/gold.yaml")
    assert src.exists(), "gold.yaml mangler — repo-invariant brutt"
    target_dir = tmp_path / "instruments"
    target_dir.mkdir()
    shutil.copy(src, target_dir / "gold.yaml")
    return target_dir


@pytest.fixture
def app_with_admin(tmp_path: Path, instruments_dir: Path):
    cfg = ServerConfig(
        data_root=tmp_path,
        signals_path=tmp_path / "signals.json",
        agri_signals_path=tmp_path / "agri_signals.json",
        kill_switch_path=tmp_path / "kills.json",
        instruments_dir=instruments_dir,
        admin_code=ADMIN_CODE,
    )
    return create_app(cfg), instruments_dir


@pytest.fixture
def app_without_admin(tmp_path: Path, instruments_dir: Path):
    """Admin_code = None — endepunktene deaktivert."""
    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=instruments_dir,
        admin_code=None,
    )
    return create_app(cfg)


def _headers(code: str = ADMIN_CODE) -> dict[str, str]:
    return {"X-Admin-Code": code}


# ---------------------------------------------------------------------------
# load_instrument_from_yaml_string
# ---------------------------------------------------------------------------


def test_load_from_string_valid() -> None:
    yaml = _valid_yaml_for("TestSym")
    cfg = load_instrument_from_yaml_string(yaml)
    assert cfg.instrument.id == "TestSym"


def test_load_from_string_invalid_yaml() -> None:
    with pytest.raises(InstrumentConfigError, match="ugyldig YAML"):
        load_instrument_from_yaml_string("{not: valid: yaml: at: all: :")


def test_load_from_string_non_mapping() -> None:
    with pytest.raises(InstrumentConfigError, match="YAML mapping"):
        load_instrument_from_yaml_string("- item\n- another")


def test_load_from_string_missing_instrument_block() -> None:
    with pytest.raises(Exception):  # Config-eller validering-feil
        load_instrument_from_yaml_string("aggregation: weighted_horizon\n")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_list_requires_admin_code(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules")
    assert response.status_code == 401
    assert "X-Admin-Code" in response.get_json()["error"]


def test_list_rejects_wrong_code(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules", headers=_headers("wrong-code"))
    assert response.status_code == 401
    assert "ugyldig" in response.get_json()["error"]


def test_endpoints_disabled_when_admin_code_unset(app_without_admin) -> None:
    app = app_without_admin
    with app.test_client() as client:
        response = client.get("/admin/rules", headers=_headers())
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


def test_list_returns_instruments(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules", headers=_headers())
    assert response.status_code == 200
    body = response.get_json()
    ids = [i["instrument_id"] for i in body["instruments"]]
    assert "gold" in ids
    assert body["instruments"][0]["size_bytes"] > 0


def test_list_missing_dir_returns_empty(tmp_path: Path) -> None:
    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=tmp_path / "does-not-exist",
        admin_code=ADMIN_CODE,
    )
    app = create_app(cfg)
    with app.test_client() as client:
        response = client.get("/admin/rules", headers=_headers())
    assert response.status_code == 200
    assert response.get_json()["instruments"] == []


# ---------------------------------------------------------------------------
# GET detail
# ---------------------------------------------------------------------------


def test_get_detail_returns_raw_yaml(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules/gold", headers=_headers())
    assert response.status_code == 200
    body = response.get_json()
    assert body["instrument_id"] == "gold"
    assert "instrument:" in body["yaml_content"]


def test_get_detail_missing_returns_404(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules/nonexistent", headers=_headers())
    assert response.status_code == 404


def test_get_detail_rejects_path_traversal(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules/..%2fetc%2fpasswd", headers=_headers())
    # Flask avviser URL-encoded slash med 404; om ikke, fanger vår regex
    assert response.status_code in (400, 404)


def test_get_detail_rejects_invalid_id(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/rules/has.dot", headers=_headers())
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# PUT
# ---------------------------------------------------------------------------


def _valid_yaml_for(instrument_id: str) -> str:
    """Minimal gyldig YAML som matcher InstrumentConfig-schema.

    Basert på gold.yaml-struktur: per-horizon family_weights +
    max_score + min_score_publish, og grade_thresholds på root.
    """
    return dedent(
        f"""\
        instrument:
          id: {instrument_id}
          asset_class: metals
          ticker: TEST

        aggregation: weighted_horizon

        horizons:
          SWING:
            family_weights:
              trend: 1.0
            max_score: 1.0
            min_score_publish: 0.5

        families:
          trend:
            drivers:
              - {{name: sma200_align, weight: 1.0, params: {{tf: D1}}}}

        grade_thresholds:
          A_plus:
            min_pct_of_max: 0.75
            min_families: 1
          A:
            min_pct_of_max: 0.55
            min_families: 1
          B:
            min_pct_of_max: 0.35
            min_families: 1
        """
    )


def test_put_writes_validated_yaml(app_with_admin) -> None:
    app, instruments_dir = app_with_admin
    new_yaml = _valid_yaml_for("newsym")
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": new_yaml},
        )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["validated"] is True
    target = instruments_dir / "newsym.yaml"
    assert target.exists()
    assert "instrument:" in target.read_text()


def test_put_rejects_without_admin_code(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            json={"yaml_content": _valid_yaml_for("newsym")},
        )
    assert response.status_code == 401


def test_put_rejects_non_json(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            data="not json",
            content_type="text/plain",
        )
    assert response.status_code == 415


def test_put_requires_yaml_content_field(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"wrong_field": "x"},
        )
    assert response.status_code == 400
    assert "yaml_content" in response.get_json()["error"]


def test_put_rejects_invalid_yaml(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": "{this: is: not: valid: :"},
        )
    assert response.status_code == 400
    assert "validering feilet" in response.get_json()["error"]


def test_put_rejects_schema_violation(app_with_admin) -> None:
    """YAML parses, men mangler påkrevde felter."""
    app, _ = app_with_admin
    bad = "instrument:\n  id: foo\n"
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/foo",
            headers=_headers(),
            json={"yaml_content": bad},
        )
    assert response.status_code == 400


def test_put_rejects_id_mismatch(app_with_admin) -> None:
    """URL-id og YAML-id må matche."""
    app, instruments_dir = app_with_admin
    yaml = _valid_yaml_for("othersym")
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": yaml},
        )
    assert response.status_code == 400
    assert "matcher ikke" in response.get_json()["error"]
    assert not (instruments_dir / "newsym.yaml").exists()


def test_put_overwrites_existing(app_with_admin) -> None:
    app, instruments_dir = app_with_admin
    new_yaml = _valid_yaml_for("gold")
    original = (instruments_dir / "gold.yaml").read_text()

    with app.test_client() as client:
        response = client.put(
            "/admin/rules/gold",
            headers=_headers(),
            json={"yaml_content": new_yaml},
        )
    assert response.status_code == 200

    updated = (instruments_dir / "gold.yaml").read_text()
    assert updated != original
    assert "TEST" in updated


def test_put_atomic_no_tmp_files_left(app_with_admin) -> None:
    app, instruments_dir = app_with_admin
    with app.test_client() as client:
        client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": _valid_yaml_for("newsym")},
        )
    tmp_files = [f for f in instruments_dir.iterdir() if f.name.startswith(".")]
    assert tmp_files == []


def test_put_validation_failure_does_not_write(app_with_admin) -> None:
    app, instruments_dir = app_with_admin
    before = set(instruments_dir.iterdir())
    with app.test_client() as client:
        client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": "not: valid: schema"},
        )
    after = set(instruments_dir.iterdir())
    assert before == after


def test_put_appends_trailing_newline(app_with_admin) -> None:
    app, instruments_dir = app_with_admin
    # YAML uten trailing newline
    yaml = _valid_yaml_for("newsym").rstrip()
    assert not yaml.endswith("\n")
    with app.test_client() as client:
        client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": yaml},
        )
    written = (instruments_dir / "newsym.yaml").read_text()
    assert written.endswith("\n")
