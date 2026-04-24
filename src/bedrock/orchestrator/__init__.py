"""Orchestrator — lim mellom YAML-config, DataStore, Engine og setups.

Fase 5 session 24 starter med minimum-API:

- `score_instrument(instrument_id, store, horizon=None, ...) -> GroupResult`
  knytter `InstrumentConfig`-lasting til `Engine.score`. Én kall for å
  få fullt GroupResult inkl. explain-trace for et instrument.

Senere sessions utvider med:

- `generate_signals(instrument_id, store, ...)` som også kjører setup-
  generator + hysterese og returnerer full signal-output med entry/SL/TP
  + stabile IDer (session 25).
"""

from __future__ import annotations

from bedrock.orchestrator.score import OrchestratorError, score_instrument
from bedrock.orchestrator.signals import (
    OrchestratorResult,
    SignalEntry,
    generate_signals,
)

__all__ = [
    "OrchestratorError",
    "OrchestratorResult",
    "SignalEntry",
    "generate_signals",
    "score_instrument",
]
