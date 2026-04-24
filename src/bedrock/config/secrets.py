"""Secrets-lasting fra `~/.bedrock/secrets.env` eller env-vars.

Design: hemmeligheter lagres på tre måter, i prioritert rekkefølge:

1. **Miljø-variabel** — f.eks. `FRED_API_KEY=... python -m bedrock.cli ...`.
   Overstyrer alt annet; nyttig for CI, systemd og ad-hoc kjøringer.
2. **Secrets-fil** — `~/.bedrock/secrets.env` (default). KEY=VALUE per linje,
   `#`-kommentarer OK. Aldri committet (gitignore).
3. Ingenting.

Per PLAN § 2 prinsipp 10: hemmeligheter blir *aldri* i repo, *aldri* i YAML,
*aldri* i UI. Ingen endpoint-eksponering.

Brukes foreløpig kun av FRED-fetcher (Fase 3 session 14). Senere: CFTC-
admin-kode, signal_server-key, etc.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_SECRETS_PATH = Path("~/.bedrock/secrets.env").expanduser()
"""Standard-lokasjon for secrets-fila. Per PLAN § 2 prinsipp 10."""


class SecretNotFoundError(KeyError):
    """Hemmelighet ikke funnet i env-var eller secrets-fil."""


def load_secrets(path: Path | None = None) -> dict[str, str]:
    """Les secrets-fila til en dict. Ikke-eksisterende fil → tom dict.

    `python-dotenv`'s `dotenv_values()` parser KEY=VALUE-linjer uten å
    mutere `os.environ`. Kommentarlinjer og tomme linjer skippes.
    """
    target = path if path is not None else DEFAULT_SECRETS_PATH
    if not target.exists():
        return {}

    # dotenv_values returnerer Dict[str, Optional[str]] — filtrer None.
    values = dotenv_values(target)
    return {k: v for k, v in values.items() if v is not None}


def get_secret(
    name: str,
    path: Path | None = None,
    default: str | None = None,
) -> str | None:
    """Slå opp en hemmelighet. Env-var overstyrer fil.

    Returnerer `default` hvis hverken env eller fil har nøkkelen.
    Bruk `require_secret` hvis manglende secret skal være feil.
    """
    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value

    return load_secrets(path).get(name, default)


def require_secret(name: str, path: Path | None = None) -> str:
    """Slå opp en hemmelighet; kast `SecretNotFoundError` hvis manglende."""
    value = get_secret(name, path=path)
    if value is None:
        target = path if path is not None else DEFAULT_SECRETS_PATH
        raise SecretNotFoundError(
            f"Secret {name!r} not found in environment or {target}. "
            f"Set the env-var or add '{name}=...' to the secrets file."
        )
    return value
