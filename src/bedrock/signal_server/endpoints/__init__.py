"""Endepunkt-grupper for signal-server.

Én Flask Blueprint per gruppe. Registreres av `app.create_app`.
"""

from __future__ import annotations

from bedrock.signal_server.endpoints.alerts import alerts_bp
from bedrock.signal_server.endpoints.kills import kills_bp
from bedrock.signal_server.endpoints.prices import prices_bp
from bedrock.signal_server.endpoints.rules import rules_bp
from bedrock.signal_server.endpoints.signals import signals_bp
from bedrock.signal_server.endpoints.uploads import uploads_bp

__all__ = [
    "alerts_bp",
    "kills_bp",
    "prices_bp",
    "rules_bp",
    "signals_bp",
    "uploads_bp",
]
