"""Config for signal-server.

Pydantic-validert config med defaults som matcher Bedrock-konvensjoner.
Alle felt kan overstyres via `ServerConfig(...)` eller load fra env.

`ServerConfig` er med vilje forskjellig fra den gamle scalp_edge-
konfigurasjonen — port 5100 i stedet for 5000 under parallell-drift.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PORT = 5100
DEFAULT_HOST = "127.0.0.1"
DEFAULT_DATA_ROOT = Path("data")


class ServerConfig(BaseModel):
    """Signal-server runtime-config.

    Ikke hardkodet — alle felt kan overstyres. Parallell-drift mot
    eksisterende `scalp_edge.signal_server` på port 5000 krever at
    `port` er annerledes (default 5100).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    # Data-paths (senere endepunkter leser/skriver her)
    data_root: Path = Field(default=DEFAULT_DATA_ROOT)
    signals_path: Path = Field(default=DEFAULT_DATA_ROOT / "signals.json")
    agri_signals_path: Path = Field(
        default=DEFAULT_DATA_ROOT / "agri_signals.json"
    )
    kill_switch_path: Path = Field(default=DEFAULT_DATA_ROOT / "kills.json")

    # DataStore (SQLite)
    db_path: Path = Field(default=DEFAULT_DATA_ROOT / "bedrock.db")

    # Uploads (bilder, pdf-er)
    uploads_root: Path = Field(default=DEFAULT_DATA_ROOT / "uploads")
    upload_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    upload_allowed_exts: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".pdf")

    # Feature-flagge (sanity-check for at vi er i bedrock-versjonen,
    # ikke i gammel scalp_edge)
    server_name: str = "bedrock-signal-server"


def load_from_env(env: dict[str, str] | None = None) -> ServerConfig:
    """Bygg ServerConfig fra environ-variabler med BEDROCK_-prefiks.

    Gir en bekvemmelighets-innfallsvinkel for deployment uten å
    tvinge alle konsumenter til å bruke env-varier.

    Ukjente variabler ignoreres. Ugyldige typer (f.eks. ikke-int port)
    kaster ValidationError.
    """
    source = env if env is not None else dict(os.environ)

    payload: dict[str, object] = {}
    if "BEDROCK_SERVER_HOST" in source:
        payload["host"] = source["BEDROCK_SERVER_HOST"]
    if "BEDROCK_SERVER_PORT" in source:
        payload["port"] = int(source["BEDROCK_SERVER_PORT"])
    if "BEDROCK_DATA_ROOT" in source:
        payload["data_root"] = Path(source["BEDROCK_DATA_ROOT"])

    return ServerConfig(**payload)
