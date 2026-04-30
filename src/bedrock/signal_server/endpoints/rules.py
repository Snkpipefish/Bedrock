# pyright: reportArgumentType=false
# Flask `T_route` rejects tuple[object, int] even for valid (jsonify, status)
# responses. Same pattern across alle signal_server/endpoints/*.

"""Admin rule-editor endepunkter.

Fase 7 session 38 — PLAN § 8.3.

Endepunkter:
- `GET  /admin/rules` — liste over tilgjengelige instrument-YAML
- `GET  /admin/rules/<instrument_id>` — rå YAML-innhold
- `PUT  /admin/rules/<instrument_id>` — valider + skriv ny YAML

Auth: alle endepunktene krever header `X-Admin-Code` med verdi som
matcher `cfg.admin_code`. Hvis `admin_code` ikke er konfigurert
(None), deaktiveres endepunktene med 503 Service Unavailable —
bevisst valg: vi vil ikke at en nyinstallert bedrock skal eksponere
editor uten at admin har satt et passord.

**Dry-run-diff og git-commit** (resten av PLAN § 8.3) er bevisst
utsatt til senere session. De krever henholdsvis orchestrator-
snapshot-kobling og git-integrasjon som er vesentlig større scope.
Session 38 leverer minimum-viable: read + validate + atomic write.

**Sikkerhet**: instrument-ID saniteres strengt mot path-traversal.
Kun `[a-zA-Z0-9_-]` tillatt — ingen `..`, `/`, eller annet.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from bedrock.config.instruments import (
    InstrumentConfigError,
    load_instrument_from_yaml_string,
)
from bedrock.signal_server.config import ServerConfig

log = logging.getLogger(__name__)

rules_bp = Blueprint("rules", __name__)

_INSTRUMENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_config() -> ServerConfig:
    return current_app.extensions["bedrock_config"]


def _check_auth() -> tuple[object, int] | None:
    """Returnerer en (error, status)-tuple hvis auth feiler, ellers None."""
    cfg = _get_config()
    if cfg.admin_code is None:
        return (
            jsonify({"error": "admin-endepunkter er ikke konfigurert"}),
            503,
        )
    header = request.headers.get("X-Admin-Code")
    if not header:
        return (
            jsonify({"error": "X-Admin-Code-header kreves"}),
            401,
        )
    if header != cfg.admin_code:
        return jsonify({"error": "ugyldig X-Admin-Code"}), 401
    return None


def _validate_instrument_id(instrument_id: str) -> tuple[object, int] | None:
    """Sanitize mot path-traversal. None hvis OK."""
    if not _INSTRUMENT_ID_RE.match(instrument_id):
        return (
            jsonify(
                {
                    "error": (
                        "ugyldig instrument-id: kun bokstaver, tall, "
                        "underscore og bindestrek er tillatt"
                    )
                }
            ),
            400,
        )
    return None


def _yaml_path(cfg: ServerConfig, instrument_id: str) -> Path:
    return cfg.instruments_dir / f"{instrument_id}.yaml"


def _git_commit_yaml(git_root: Path, yaml_path: Path, instrument_id: str) -> dict:
    """Auto-commit YAML-en hvis `admin_git_root` er konfigurert.

    Stille no-op hvis ingen endring (git-output tomt). Bruker `git -C
    <root>` så vi ikke endrer global cwd. Auto-push-hook
    (`.githooks/post-commit`) håndterer push videre.

    Returnerer info-dict for response: `{committed: bool, sha?: str,
    error?: str}`. Kaster ikke; feil blir logget og returnert som
    `committed: false`.
    """
    try:
        rel = yaml_path.resolve().relative_to(git_root.resolve())
    except ValueError:
        msg = f"yaml_path {yaml_path} ligger ikke i git_root {git_root}"
        log.warning("[ADMIN-GIT] %s", msg)
        return {"committed": False, "error": msg}

    rel_str = str(rel)
    try:
        # Sjekk om filen faktisk har endringer i staging eller working tree
        result = subprocess.run(
            ["git", "-C", str(git_root), "status", "--porcelain", rel_str],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if not result.stdout.strip():
            log.info("[ADMIN-GIT] Ingen endring i %s — hopper over commit", rel_str)
            return {"committed": False, "reason": "ingen endring"}

        # Stage + commit
        subprocess.run(
            ["git", "-C", str(git_root), "add", rel_str],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        msg = f"config({instrument_id}): admin-edit via /admin/rules"
        subprocess.run(
            ["git", "-C", str(git_root), "commit", "-m", msg],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        sha = subprocess.run(
            ["git", "-C", str(git_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        log.info("[ADMIN-GIT] Committet %s som %s", rel_str, sha)
        return {"committed": True, "sha": sha, "message": msg}
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        log.warning("[ADMIN-GIT] git-feil: %s", err)
        return {"committed": False, "error": err}
    except subprocess.TimeoutExpired:
        log.warning("[ADMIN-GIT] git timeout på %s", rel_str)
        return {"committed": False, "error": "git timeout"}
    except Exception as exc:
        log.warning("[ADMIN-GIT] uventet feil: %s", exc)
        return {"committed": False, "error": str(exc)}


@rules_bp.get("/admin/rules")
def list_rules() -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    cfg = _get_config()
    if not cfg.instruments_dir.exists():
        return jsonify({"instruments": []}), 200

    instruments = [
        {
            "instrument_id": path.stem,
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(cfg.instruments_dir.glob("*.yaml"))
    ]
    return jsonify({"instruments": instruments}), 200


@rules_bp.get("/admin/rules/<instrument_id>")
def get_rule(instrument_id: str) -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    id_err = _validate_instrument_id(instrument_id)
    if id_err is not None:
        return id_err

    cfg = _get_config()
    path = _yaml_path(cfg, instrument_id)
    if not path.exists():
        return (
            jsonify({"error": f"instrument {instrument_id!r} finnes ikke"}),
            404,
        )

    return (
        jsonify(
            {
                "instrument_id": instrument_id,
                "yaml_content": path.read_text(encoding="utf-8"),
            }
        ),
        200,
    )


@rules_bp.put("/admin/rules/<instrument_id>")
def put_rule(instrument_id: str) -> tuple[object, int]:
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    id_err = _validate_instrument_id(instrument_id)
    if id_err is not None:
        return id_err

    if not request.is_json:
        return (
            jsonify({"error": "Content-Type må være application/json"}),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return jsonify({"error": "body må være et JSON-objekt"}), 400

    yaml_content = payload.get("yaml_content")
    if not isinstance(yaml_content, str):
        return (
            jsonify({"error": "yaml_content-felt (string) kreves"}),
            400,
        )

    cfg = _get_config()

    # Valider via Pydantic + inherits-resolver
    try:
        config = load_instrument_from_yaml_string(
            yaml_content,
            source_name=f"admin-put:{instrument_id}",
        )
    except InstrumentConfigError as exc:
        return jsonify({"error": "validering feilet", "detail": str(exc)}), 400
    except ValidationError as exc:
        return (
            jsonify(
                {
                    "error": "validering feilet",
                    "details": exc.errors(include_context=False),
                }
            ),
            400,
        )

    # Valgfri sanity: instrument-id i URL matcher config.instrument.id
    if config.instrument.id.lower() != instrument_id.lower():
        return (
            jsonify(
                {
                    "error": (
                        f"instrument-id i URL ({instrument_id}) "
                        f"matcher ikke config.instrument.id "
                        f"({config.instrument.id})"
                    )
                }
            ),
            400,
        )

    # Atomic write (samme mønster som signals-storage)
    target = _yaml_path(cfg, instrument_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(yaml_content)
            if not yaml_content.endswith("\n"):
                fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    # Fase 9 runde 3 session 55: auto-commit til git hvis konfigurert
    git_info = None
    if cfg.admin_git_root is not None:
        git_info = _git_commit_yaml(cfg.admin_git_root, target, instrument_id)

    response: dict = {
        "instrument_id": instrument_id,
        "written_to": str(target.resolve()),
        "validated": True,
    }
    if git_info is not None:
        response["git"] = git_info
    return jsonify(response), 200


@rules_bp.get("/admin/logs")
def get_logs() -> tuple[object, int]:
    """Returner siste N linjer av `cfg.admin_log_path`.

    Fase 9 runde 3 session 55. Lett UI-vindu inn i pipeline-loggen.
    Ingen følsom data forventes (logs filtrerer ut secrets), men
    endepunktet er bak admin-auth uansett.

    Query: `?tail=N` (default 200, max 2000).
    Respons: `{path, lines: [...]}` eller 404 hvis ikke konfigurert
    eller fil mangler.
    """
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    cfg = _get_config()
    log_path = cfg.admin_log_path
    if log_path is None:
        return (
            jsonify({"error": "admin_log_path er ikke konfigurert"}),
            404,
        )
    if not log_path.exists():
        return (
            jsonify({"error": f"log-fil {log_path} finnes ikke"}),
            404,
        )

    raw_tail = request.args.get("tail", "200")
    try:
        tail = max(1, min(int(raw_tail), 2000))
    except ValueError:
        tail = 200

    try:
        # Lese hele filen, ta siste N linjer. For svært store logs
        # er dette suboptimalt — men 2000 linjer på en typisk pipeline-
        # log er < 1 MB å lese, og endepunktet er manuelt brukt.
        with log_path.open("r", encoding="utf-8", errors="replace") as fp:
            all_lines = fp.readlines()
        tail_lines = [line.rstrip("\n") for line in all_lines[-tail:]]
        return (
            jsonify(
                {
                    "path": str(log_path.resolve()),
                    "total_lines": len(all_lines),
                    "returned": len(tail_lines),
                    "lines": tail_lines,
                }
            ),
            200,
        )
    except OSError as exc:
        return jsonify({"error": f"klarte ikke lese log: {exc}"}), 500


@rules_bp.post("/admin/rules/<instrument_id>/dry-run")
def dry_run_rule(instrument_id: str) -> tuple[object, int]:
    """Validate proposed YAML uten å skrive til disk.

    Fase 9 runde 3 session 55: lightweight dry-run. Kjører Pydantic +
    inherits-resolver mot innsendt yaml_content og returnerer 200
    {valid: true, instrument_id, ...} hvis OK, 400 med detaljer hvis
    valideringsfeil.

    Heavyweight dry-run (score-diff mot siste 7 dager) er separat
    task — krever DataStore-injeksjon + dobbelt Engine-kjøring.
    """
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err
    id_err = _validate_instrument_id(instrument_id)
    if id_err is not None:
        return id_err

    if not request.is_json:
        return (
            jsonify({"error": "Content-Type må være application/json"}),
            415,
        )
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return jsonify({"error": "body må være et JSON-objekt"}), 400

    yaml_content = payload.get("yaml_content")
    if not isinstance(yaml_content, str):
        return jsonify({"error": "yaml_content-felt (string) kreves"}), 400

    try:
        config = load_instrument_from_yaml_string(
            yaml_content,
            source_name=f"admin-dry-run:{instrument_id}",
        )
    except InstrumentConfigError as exc:
        return jsonify({"valid": False, "error": str(exc)}), 400
    except ValidationError as exc:
        return (
            jsonify(
                {
                    "valid": False,
                    "error": "validering feilet",
                    "details": exc.errors(include_context=False),
                }
            ),
            400,
        )

    if config.instrument.id.lower() != instrument_id.lower():
        return (
            jsonify(
                {
                    "valid": False,
                    "error": (
                        f"instrument-id i URL ({instrument_id}) "
                        f"matcher ikke config.instrument.id "
                        f"({config.instrument.id})"
                    ),
                }
            ),
            400,
        )

    return (
        jsonify(
            {
                "valid": True,
                "instrument_id": instrument_id,
                "config_summary": {
                    "id": config.instrument.id,
                    "asset_class": getattr(config.instrument, "asset_class", None),
                    "families": list(config.rules.families.keys())
                    if hasattr(config.rules, "families")
                    else [],
                },
            }
        ),
        200,
    )


@rules_bp.get("/admin/drivers")
def list_drivers() -> tuple[object, int]:
    """Driver-utforsker — alle registrerte drivere + observation-stats.

    Etappe 6: lar admin se hvilke drivere som faktisk har data i
    `driver_observations` (harvest-output) vs. de som er registrert
    men "stille". Stille drivere er typisk symptom på enten manglende
    data-kilde eller at instrumenter som triggerer dem ikke er i drift.

    Read-only mot DB — WAL-trygg under harvest.
    """
    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    cfg = _get_config()

    # Hent registrerte driver-navn fra in-process registry.
    try:
        from bedrock.engine.drivers import all_names

        registered = list(all_names())
    except Exception as exc:
        log.warning("[ADMIN] driver-registry-import feilet: %s", exc)
        registered = []

    # Aggreger observation-stats per driver fra DB.
    import sqlite3

    stats: dict[str, dict[str, object]] = {}
    family_by_driver: dict[str, str] = {}
    try:
        con = sqlite3.connect(cfg.db_path)
        try:
            con.execute("PRAGMA query_only = 1")
            rows = con.execute(
                """
                SELECT driver_name,
                       MAX(family_name) AS family,
                       COUNT(*) AS n_obs,
                       COUNT(DISTINCT instrument) AS n_instruments,
                       COUNT(DISTINCT driver_value) AS n_distinct_values,
                       MAX(ref_date) AS latest_ref_date,
                       MIN(ref_date) AS earliest_ref_date
                FROM driver_observations
                GROUP BY driver_name
                """
            ).fetchall()
            for r in rows:
                name = r[0]
                family_by_driver[name] = r[1] or ""
                stats[name] = {
                    "n_obs": int(r[2] or 0),
                    "n_instruments": int(r[3] or 0),
                    "n_distinct_values": int(r[4] or 0),
                    "latest_ref_date": r[5],
                    "earliest_ref_date": r[6],
                }
        finally:
            con.close()
    except Exception as exc:
        log.warning("[ADMIN] driver-observations db-feil: %s", exc)

    # Fra YAML-config: bygg tentativ driver→familie-mapping for
    # registrerte drivere som ikke har observasjoner ennå (gir oss
    # en familie-grupperinghint selv for stille drivere).
    yaml_family_by_driver: dict[str, str] = {}
    try:
        import yaml

        for path in sorted(cfg.instruments_dir.glob("*.yaml")):
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            rules = doc.get("rules") or {}
            families = rules.get("families") or {}
            if not isinstance(families, dict):
                continue
            for fam_name, fam_block in families.items():
                if not isinstance(fam_block, dict):
                    continue
                drivers = fam_block.get("drivers") or []
                if not isinstance(drivers, list):
                    continue
                for d in drivers:
                    if isinstance(d, dict):
                        dname = d.get("name")
                    elif isinstance(d, str):
                        dname = d
                    else:
                        dname = None
                    if dname and dname not in yaml_family_by_driver:
                        yaml_family_by_driver[dname] = fam_name
    except Exception as exc:
        log.warning("[ADMIN] yaml driver-family-map feilet: %s", exc)

    # Bygg unionssett: alle registrerte + alle observert (kan finnes
    # i DB som "deprecated" og ikke lenger registrert).
    all_names_set = set(registered) | set(stats.keys())
    drivers: list[dict[str, object]] = []
    for name in sorted(all_names_set):
        s = stats.get(name) or {}
        family = family_by_driver.get(name) or yaml_family_by_driver.get(name) or "(ingen)"
        is_registered = name in registered
        n_obs = int(s.get("n_obs") or 0)
        n_distinct = int(s.get("n_distinct_values") or 0)
        # "Stille" = registrert men ingen observasjoner ennå.
        # "Kvasi-stille" = har observasjoner, men ≤ 1 distinkt verdi
        # (driver returnerer alltid samme tall — typisk placeholder).
        if not is_registered:
            status = "deprecated"
        elif n_obs == 0:
            status = "silent"
        elif n_distinct <= 1:
            status = "monotone"
        else:
            status = "active"
        drivers.append(
            {
                "name": name,
                "family": family,
                "registered": is_registered,
                "status": status,
                "n_obs": n_obs,
                "n_instruments": int(s.get("n_instruments") or 0),
                "n_distinct_values": n_distinct,
                "latest_ref_date": s.get("latest_ref_date"),
                "earliest_ref_date": s.get("earliest_ref_date"),
            }
        )

    summary = {
        "total": len(drivers),
        "active": sum(1 for d in drivers if d["status"] == "active"),
        "monotone": sum(1 for d in drivers if d["status"] == "monotone"),
        "silent": sum(1 for d in drivers if d["status"] == "silent"),
        "deprecated": sum(1 for d in drivers if d["status"] == "deprecated"),
    }

    return jsonify({"drivers": drivers, "summary": summary}), 200
