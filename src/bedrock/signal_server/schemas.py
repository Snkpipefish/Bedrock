"""Schema for signal-persistence i signal-server.

Fase 7 session 34 — minimum felter for at serveren skal kunne validere
at filen ikke er totalt korrupt, med `extra='allow'` slik at ny felter
kan legges til i orchestrator-output uten å bryte serveren.

Vi *gjenbruker ikke* `SignalEntry` fra `bedrock.orchestrator.signals`
direkte. Grunnene:

1. Signal-filene er et transport-snitt mellom orchestrator og server;
   at de er strukturelt like i dag betyr ikke at de skal være det for
   alltid (f.eks. kan serveren legge til `published_at`-timestamp).
2. Orchestrator bruker Direction/Horizon-enum-typer som er riktig der,
   men JSON-serialisering gjør dem uansett til strenger når de skrives
   til fil. Serveren arbeider med strings + valideringsregel.
3. `StableSetup` (en del av `SignalEntry.setup`) er et tungt schema
   fulla av klyngeinfo som serveren ikke trenger å riste på — pass-
   through som dict er tilstrekkelig.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_DIRECTIONS = {"BUY", "SELL"}
_VALID_HORIZONS = {"SCALP", "SWING", "MAKRO"}


class PersistedSignal(BaseModel):
    """Ett signal slik det ligger på disk.

    Minimumsfelter valideres; alt annet passerer gjennom via
    `extra='allow'`. Validering begrenses til eksistens + enum-domener
    — vi antar at orchestrator har gjort tyngre validering ved
    skrivetid.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    instrument: str
    direction: str
    horizon: str
    score: float
    grade: str
    setup: dict | None = Field(default=None)

    @field_validator("direction")
    @classmethod
    def _direction_must_be_valid(cls, value: str) -> str:
        if value not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction må være BUY/SELL, fikk {value!r}"
            )
        return value

    @field_validator("horizon")
    @classmethod
    def _horizon_must_be_valid(cls, value: str) -> str:
        if value not in _VALID_HORIZONS:
            raise ValueError(
                f"horizon må være SCALP/SWING/MAKRO, fikk {value!r}"
            )
        return value

    @field_validator("score")
    @classmethod
    def _score_must_be_nonneg(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"score må være >= 0, fikk {value}")
        return value


class KillSwitch(BaseModel):
    """Kill-switch: fryser en (instrument, horizon)-slot for bot-handling.

    Mens en kill-switch er aktiv skal bot ignorere signaler på den
    slotten. Flere kills på samme slot behandles som idempotent —
    lagringen deduper på (instrument, horizon).
    """

    model_config = ConfigDict(extra="forbid")

    instrument: str
    horizon: str
    killed_at: datetime = Field(default_factory=datetime.utcnow)
    reason: str = ""

    @field_validator("horizon")
    @classmethod
    def _horizon_must_be_valid(cls, value: str) -> str:
        if value not in _VALID_HORIZONS:
            raise ValueError(
                f"horizon må være SCALP/SWING/MAKRO, fikk {value!r}"
            )
        return value

    @property
    def slot(self) -> tuple[str, str]:
        """Dedupe-nøkkel: ett kill per (instrument, horizon)."""
        return (self.instrument, self.horizon)


class InvalidationRequest(BaseModel):
    """Payload for `POST /invalidate` — markerer matchende signaler."""

    model_config = ConfigDict(extra="forbid")

    instrument: str
    direction: str
    horizon: str
    reason: str = ""

    @field_validator("direction")
    @classmethod
    def _direction_must_be_valid(cls, value: str) -> str:
        if value not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction må være BUY/SELL, fikk {value!r}"
            )
        return value

    @field_validator("horizon")
    @classmethod
    def _horizon_must_be_valid(cls, value: str) -> str:
        if value not in _VALID_HORIZONS:
            raise ValueError(
                f"horizon må være SCALP/SWING/MAKRO, fikk {value!r}"
            )
        return value


class PriceBarIn(BaseModel):
    """Ett pris-bar slik klienten sender det inn.

    Close er påkrevd (minimum-kontrakt med DataStore.append_prices).
    OHLV er valgfritt — NULL persistere fint i SQLite.
    """

    model_config = ConfigDict(extra="forbid")

    ts: datetime
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None


class PushPricesRequest(BaseModel):
    """Payload for POST /push-prices."""

    model_config = ConfigDict(extra="forbid")

    instrument: str
    tf: str
    bars: list[PriceBarIn] = Field(min_length=1)


class SignalStoreError(Exception):
    """Signal-fil er korrupt eller har feil struktur."""
