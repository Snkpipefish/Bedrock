"""`bedrock server` — start Flask-basert signal_server + web-UI.

Session 93. Tidligere måtte signal_server startes manuelt via et test-
script eller importert programmatisk. Denne kommandoen gir en
førsteklasses CLI-entry slik at UI kan kjøres som systemd-service:

    bedrock server                                # default port 5100
    bedrock server --host 0.0.0.0 --port 5100     # eksponert på LAN
    bedrock server --debug                        # Flask-debug + auto-reload

For produksjon (systemd) anbefales waitress eller gunicorn som WSGI-
server. Default ``--use-flask-dev`` bruker Flask's innebygde server
som er tilstrekkelig for lokal utvikling og lavtraffikk-produksjon.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
import structlog

from bedrock.signal_server.app import create_app
from bedrock.signal_server.config import ServerConfig, load_from_env

_log = structlog.get_logger(__name__)


@click.command(name="server")
@click.option(
    "--host",
    default=None,
    help="Bind-host (default fra BEDROCK_SERVER_HOST eller 127.0.0.1).",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Bind-port (default fra BEDROCK_SERVER_PORT eller 5100).",
)
@click.option(
    "--data-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Path til data-katalog (default: ./data).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Flask debug-mode (auto-reload + traceback). Skal aldri brukes i prod.",
)
@click.option(
    "--use-waitress/--use-flask-dev",
    default=True,
    help="Bruk waitress (prod) eller Flask-dev-server. Default: waitress.",
)
def server_cmd(
    host: str | None,
    port: int | None,
    data_root: Path | None,
    debug: bool,
    use_waitress: bool,
) -> None:
    """Start signal_server + UI.

    Lytter på ``host:port`` (default 127.0.0.1:5100). UI er tilgjengelig
    på ``http://<host>:<port>/``.

    Konfigurasjon hentes i prioritert rekkefølge:
    1. CLI-flagg (--host, --port, --data-root)
    2. ENV-variabler (BEDROCK_SERVER_HOST, BEDROCK_SERVER_PORT, BEDROCK_DATA_ROOT)
    3. Default (127.0.0.1, 5100, ./data)
    """
    # Last ENV-default først
    cfg = load_from_env()

    # Override fra CLI-flagg
    overrides: dict = {}
    if host is not None:
        overrides["host"] = host
    if port is not None:
        overrides["port"] = port
    if data_root is not None:
        overrides["data_root"] = data_root
        # Re-derive default-path-er fra ny data_root
        overrides["signals_path"] = data_root / "signals.json"
        overrides["agri_signals_path"] = data_root / "agri_signals.json"
    if overrides:
        cfg = ServerConfig(**{**cfg.model_dump(), **overrides})

    # Sjekk at data-root finnes — UI feiler graceful uten, men bedre
    # å advare opp-front.
    if not cfg.data_root.exists():
        click.echo(
            f"WARN: data_root {cfg.data_root} finnes ikke. UI vil vise tomme lister.",
            err=True,
        )

    app = create_app(cfg)

    click.echo(f"Bedrock signal_server starter på http://{cfg.host}:{cfg.port}/")
    click.echo(f"  data_root:     {cfg.data_root}")
    click.echo(f"  signals_path:  {cfg.signals_path}")
    click.echo(f"  agri_path:     {cfg.agri_signals_path}")

    if debug:
        # Flask-dev med auto-reload
        app.run(host=cfg.host, port=cfg.port, debug=True)
    elif use_waitress:
        try:
            from waitress import serve
        except ImportError:
            click.echo(
                "waitress ikke installert — fallback til Flask-dev. Kjør "
                "`uv pip install waitress` for prod-WSGI.",
                err=True,
            )
            app.run(host=cfg.host, port=cfg.port, debug=False)
        else:
            # Reduser noise — WSGI-loggene går via Python logging
            logging.getLogger("waitress").setLevel(logging.WARNING)
            serve(app, host=cfg.host, port=cfg.port, threads=4)
    else:
        app.run(host=cfg.host, port=cfg.port, debug=False)
