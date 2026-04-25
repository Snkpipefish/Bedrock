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


# ---------------------------------------------------------------------------
# Fase 9 runde 3 session 55: dry-run + git-commit + logs
# ---------------------------------------------------------------------------


def test_dry_run_valid_yaml_does_not_write(app_with_admin) -> None:
    """Dry-run skal validere uten å røre disk."""
    app, instruments_dir = app_with_admin
    before = set(instruments_dir.iterdir())
    with app.test_client() as client:
        response = client.post(
            "/admin/rules/newsym/dry-run",
            headers=_headers(),
            json={"yaml_content": _valid_yaml_for("newsym")},
        )
    after = set(instruments_dir.iterdir())
    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is True
    assert body["instrument_id"] == "newsym"
    assert body["config_summary"]["id"] == "newsym"
    assert before == after  # ingenting skrevet


def test_dry_run_invalid_yaml_returns_400_with_details(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.post(
            "/admin/rules/newsym/dry-run",
            headers=_headers(),
            json={"yaml_content": "instrument:\n  id: bad"},  # mangler resten
        )
    assert response.status_code == 400
    body = response.get_json()
    assert body["valid"] is False
    assert "details" in body or "error" in body


def test_dry_run_requires_auth(app_with_admin) -> None:
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.post(
            "/admin/rules/newsym/dry-run",
            json={"yaml_content": "anything"},
        )
    assert response.status_code == 401


def test_dry_run_id_mismatch_returns_400(app_with_admin) -> None:
    """URL-id må matche config.instrument.id."""
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.post(
            "/admin/rules/foo/dry-run",
            headers=_headers(),
            json={"yaml_content": _valid_yaml_for("bar")},
        )
    assert response.status_code == 400


# ─── Git-commit-on-save ────────────────────────────────────────


@pytest.fixture
def app_with_git(tmp_path: Path, instruments_dir: Path):
    """ServerConfig med admin_git_root pekende på et lite test-repo."""
    import subprocess as sp

    # Initialiser git-repo i tmp_path og kommitt instruments-mappen
    sp.run(["git", "init", "-q", str(tmp_path)], check=True)
    sp.run(["git", "-C", str(tmp_path), "config", "user.email", "test@bedrock"], check=True)
    sp.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    sp.run(["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"], check=True)
    # Flytt instruments-dir inn i repo-rota og symlink ikke krevd —
    # vi konfigurerer cfg.instruments_dir til den nye stien.
    repo_instruments = tmp_path / "config" / "instruments"
    repo_instruments.mkdir(parents=True)
    shutil.copy(instruments_dir / "gold.yaml", repo_instruments / "gold.yaml")
    sp.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    sp.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)

    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=repo_instruments,
        admin_code=ADMIN_CODE,
        admin_git_root=tmp_path,
    )
    return create_app(cfg), repo_instruments, tmp_path


def test_put_with_git_commits_change(app_with_git) -> None:
    """Etter PUT skal det ligge en ny commit på HEAD med config(<id>)-melding."""
    import subprocess as sp

    app, repo_instruments, repo_root = app_with_git
    new_yaml = _valid_yaml_for("gold")  # samme id, annet innhold
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/gold",
            headers=_headers(),
            json={"yaml_content": new_yaml},
        )
    assert response.status_code == 200
    body = response.get_json()
    assert "git" in body
    assert body["git"]["committed"] is True
    assert body["git"]["sha"]
    # Verifiser via git log
    log_msg = sp.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log_msg == "config(gold): admin-edit via /admin/rules"


def test_put_with_git_skips_commit_when_no_change(app_with_git) -> None:
    """Hvis YAML er identisk med disk-versjon, ingen commit."""
    import subprocess as sp

    app, repo_instruments, repo_root = app_with_git
    existing = (repo_instruments / "gold.yaml").read_text()
    head_before = sp.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/gold",
            headers=_headers(),
            json={"yaml_content": existing},
        )
    assert response.status_code == 200
    body = response.get_json()
    assert body["git"]["committed"] is False
    head_after = sp.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head_before == head_after


def test_put_without_git_root_skips_git(app_with_admin) -> None:
    """admin_git_root=None → response har ikke `git`-felt."""
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.put(
            "/admin/rules/newsym",
            headers=_headers(),
            json={"yaml_content": _valid_yaml_for("newsym")},
        )
    assert response.status_code == 200
    body = response.get_json()
    assert "git" not in body


# ─── Logs-endpoint ────────────────────────────────────────────


def test_logs_404_when_not_configured(app_with_admin) -> None:
    """admin_log_path=None → 404."""
    app, _ = app_with_admin
    with app.test_client() as client:
        response = client.get("/admin/logs", headers=_headers())
    assert response.status_code == 404


def test_logs_returns_tail(tmp_path: Path, instruments_dir: Path) -> None:
    log_path = tmp_path / "pipeline.log"
    log_path.write_text("\n".join(f"line-{i}" for i in range(500)) + "\n")
    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=instruments_dir,
        admin_code=ADMIN_CODE,
        admin_log_path=log_path,
    )
    app = create_app(cfg)
    with app.test_client() as client:
        response = client.get("/admin/logs?tail=10", headers=_headers())
    assert response.status_code == 200
    body = response.get_json()
    assert body["total_lines"] == 500
    assert body["returned"] == 10
    assert body["lines"][0] == "line-490"
    assert body["lines"][-1] == "line-499"


def test_logs_default_tail_200(tmp_path: Path, instruments_dir: Path) -> None:
    log_path = tmp_path / "pipeline.log"
    log_path.write_text("\n".join(f"L{i}" for i in range(50)) + "\n")
    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=instruments_dir,
        admin_code=ADMIN_CODE,
        admin_log_path=log_path,
    )
    app = create_app(cfg)
    with app.test_client() as client:
        response = client.get("/admin/logs", headers=_headers())
    assert response.status_code == 200
    body = response.get_json()
    # Filen har bare 50 linjer; default tail=200 → returnerer alle 50
    assert body["returned"] == 50


def test_logs_requires_auth(tmp_path: Path, instruments_dir: Path) -> None:
    cfg = ServerConfig(
        data_root=tmp_path,
        instruments_dir=instruments_dir,
        admin_code=ADMIN_CODE,
        admin_log_path=tmp_path / "any.log",
    )
    app = create_app(cfg)
    with app.test_client() as client:
        response = client.get("/admin/logs")
    assert response.status_code == 401
