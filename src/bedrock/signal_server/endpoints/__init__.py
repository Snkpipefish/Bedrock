"""Endepunkt-grupper for signal-server.

Én Flask Blueprint per gruppe. Registreres av `app.create_app`.
"""

from __future__ import annotations

from bedrock.signal_server.endpoints.signals import signals_bp

__all__ = ["signals_bp"]
