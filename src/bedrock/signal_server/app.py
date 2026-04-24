"""Flask-app-factory for bedrock signal-server.

Fase 7 session 33: skeleton. Kun `/health` er implementert. Endepunkt-
grupper (alerts, signals, kills, prices, rules) plugges inn i senere
sessions via `app.register_blueprint(...)`.

`create_app` er rent deterministisk og side-effekt-fri (ingen I/O,
ingen lytting). Selve `app.run()` håndteres av caller — CLI eller
test-klient.
"""

from __future__ import annotations

from flask import Flask

from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.endpoints import (
    alerts_bp,
    kills_bp,
    prices_bp,
    signals_bp,
    uploads_bp,
)


def create_app(config: ServerConfig | None = None) -> Flask:
    """Lag en ny Flask-app med gitt config.

    Tom config → bruker defaults (`ServerConfig()`). Hver kall returnerer
    en fresh app-instans — viktig for tester som ikke skal dele state.
    """
    cfg = config if config is not None else ServerConfig()

    app = Flask(cfg.server_name)
    # Config tilgjengelig for endepunkter via `current_app.extensions["bedrock_config"]`
    app.extensions["bedrock_config"] = cfg

    _register_meta_endpoints(app, cfg)
    app.register_blueprint(signals_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(kills_bp)
    app.register_blueprint(prices_bp)
    app.register_blueprint(uploads_bp)
    return app


def _register_meta_endpoints(app: Flask, cfg: ServerConfig) -> None:
    """Helse- og identitets-endepunkter. Ingen state, ingen I/O."""

    @app.get("/health")
    def health() -> tuple[dict[str, object], int]:
        return (
            {
                "ok": True,
                "server": cfg.server_name,
            },
            200,
        )

    @app.get("/status")
    def status() -> tuple[dict[str, object], int]:
        """Basis-status. Utvides i senere sessions med kills/uptime/counter."""
        return (
            {
                "server": cfg.server_name,
                "port": cfg.port,
                "host": cfg.host,
                "endpoints_registered": sorted(
                    rule.rule
                    for rule in app.url_map.iter_rules()
                    if rule.endpoint != "static"
                ),
            },
            200,
        )
