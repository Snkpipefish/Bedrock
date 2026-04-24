"""Bedrock signal-server.

Fase 7 (PLAN § 8) — refaktor av `~/scalp_edge/signal_server.py` (974
linjer Flask) til modul-struktur. Parallell-bygg: gammel server kjører
uendret på port 5000 inntil Fase 13 cutover. Denne bedrock-varianten
kjører på egen port (default 5100) under utvikling + demo.

Public API:

- `create_app(config=None) -> Flask` — app-factory. Bruk `config` til å
  overstyre defaults (port, data-paths, kill-switch-fil osv.)

Endepunkter implementeres gruppevis i `bedrock.signal_server.endpoints.*`.
Se `ENDPOINTS.md` i samme katalog for inventar.
"""

from __future__ import annotations

from bedrock.signal_server.app import create_app

__all__ = ["create_app"]
