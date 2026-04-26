"""`score_instrument` — last InstrumentConfig, kjør Engine.score.

Minimum-integrasjonsfunksjon som bridger Fase 5's YAML-konfig med Fase 1's
Engine. Returnerer `GroupResult` med full explain-trace.

Eksempel:

    from bedrock.data.store import DataStore
    from bedrock.orchestrator import score_instrument

    store = DataStore(Path("data/bedrock.db"))
    result = score_instrument("Gold", store, horizon="SWING")
    print(result.grade, result.score)

For agri-instrumenter angis ikke `horizon` — aggregation=additive_sum
scorer uten horisont-splitt (horisont settes senere av setup-generatoren).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bedrock.config.instruments import (
    InstrumentConfig,
    load_instrument_config,
)
from bedrock.engine.engine import AgriRules, Engine, FinancialRules, GroupResult
from bedrock.setups.generator import Direction

DEFAULT_INSTRUMENTS_DIR = Path("config/instruments")


class OrchestratorError(ValueError):
    """Orkestrerings-feil — manglende YAML, ugyldig horisont, etc."""


def score_instrument(
    instrument_id: str,
    store: Any,
    *,
    horizon: str | None = None,
    instruments_dir: Path | str | None = None,
    defaults_dir: Path | str | None = None,
    engine: Engine | None = None,
    direction: Direction = Direction.BUY,
) -> GroupResult:
    """Last `config/instruments/<id>.yaml` og scoring via Engine.

    - `instrument_id`: matches mot `instrument.id` i YAML.
    - `store`: et `DataStore`-instance (må ha get_prices + drivere-
      relevante getters).
    - `horizon`: påkrevd for financial (weighted_horizon); ignoreres for
      agri (additive_sum).
    - `instruments_dir`: default `config/instruments/`.
    - `defaults_dir`: default `config/defaults/` (brukt til `inherits:`).
    - `engine`: valgfri eksplisitt Engine-instans (default ny tom).
    - `direction`: BUY (default) eller SELL — propageres til Engine.score
      for ADR-006 direction-asymmetric scoring.

    Reiser `OrchestratorError` ved manglende YAML, mismatch mellom
    rules-type og horisont-arg, eller ukjent horisont. Pydantic-
    valideringsfeil fra YAML-lasting propageres.
    """
    resolved_inst_dir = (
        Path(instruments_dir) if instruments_dir is not None else DEFAULT_INSTRUMENTS_DIR
    )
    yaml_path = _find_yaml(instrument_id, resolved_inst_dir)
    cfg: InstrumentConfig = load_instrument_config(yaml_path, defaults_dir=defaults_dir)

    _validate_horizon_arg(cfg, horizon)

    eng = engine or Engine()
    # Engine tar det kanoniske instrument-ID-et fra YAML (ikke request-
    # strengen) — gir konsistens i GroupResult.instrument uansett om
    # caller brukte "gold" eller "Gold"
    return eng.score(cfg.instrument.id, store, cfg.rules, horizon=horizon, direction=direction)


def _find_yaml(instrument_id: str, instruments_dir: Path) -> Path:
    """Finn YAML-fil matchende instrument-id (case-insensitive fallback).

    Ser etter `<id>.yaml` eksakt, så case-insensitive match på filnavn.
    Reiser `OrchestratorError` hvis ingen match.
    """
    if not instruments_dir.exists():
        raise OrchestratorError(f"Instruments directory not found: {instruments_dir}")

    # Eksakt
    exact = instruments_dir / f"{instrument_id}.yaml"
    if exact.exists():
        return exact

    # Case-insensitive filnavn-match
    lower = instrument_id.lower()
    for candidate in instruments_dir.glob("*.yaml"):
        if candidate.stem.lower() == lower:
            return candidate

    available = sorted(p.stem for p in instruments_dir.glob("*.yaml"))
    raise OrchestratorError(
        f"Instrument {instrument_id!r} has no YAML in {instruments_dir}. Available: {available}"
    )


def _validate_horizon_arg(cfg: InstrumentConfig, horizon: str | None) -> None:
    """Sjekk at horisont-arg stemmer med rules-type.

    - FinancialRules: horizon må angis og være blant `rules.horizons.keys()`.
    - AgriRules: horizon må være None (ellers caller-bug).
    """
    if isinstance(cfg.rules, FinancialRules):
        if horizon is None:
            raise OrchestratorError(
                f"Instrument {cfg.instrument.id!r} uses weighted_horizon — "
                f"horizon argument is required. "
                f"Available: {sorted(cfg.rules.horizons.keys())}"
            )
        if horizon not in cfg.rules.horizons:
            raise OrchestratorError(
                f"Horizon {horizon!r} not defined for instrument "
                f"{cfg.instrument.id!r}. "
                f"Available: {sorted(cfg.rules.horizons.keys())}"
            )
        return

    if isinstance(cfg.rules, AgriRules):
        if horizon is not None:
            raise OrchestratorError(
                f"Instrument {cfg.instrument.id!r} uses additive_sum — "
                f"horizon argument must be None (got {horizon!r}). "
                f"Horisont bestemmes senere av setup-generator."
            )
        return

    raise OrchestratorError(f"Unknown rules type: {type(cfg.rules).__name__}")


__all__ = ["OrchestratorError", "score_instrument"]
