"""Rene data-beholdere for bot-state.

Portert 1:1 fra `~/scalp_edge/trading_bot.py:335-398` per Fase 8-plan
(`docs/migration/bot_refactor.md § 3.5`). Ingen logikk-endring.

- `TradePhase`: enum for fase i trade-lifecycle
- `Candle`: én lukket candle (brukes for 15m/5m/1h)
- `TradeState`: mutable state per åpen trade — eies av `entry`/`exit`
- `CandleBuffer`: rullerende buffer med siste 50 candles + "current" fields

`TradeState` forblir `@dataclass` (ikke Pydantic) i Fase 8. Endring til
Pydantic krever ADR — mutasjon skjer på mange steder i exit-koden og
Pydantic v2 `validate_assignment` vil legge til overhead som ikke trengs
enda.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class TradePhase(Enum):
    AWAITING_CONFIRMATION = auto()
    IN_TRADE = auto()
    CLOSED = auto()


@dataclass
class Candle:
    """Representerer én lukket candle (15m/5m/1h)."""

    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime


@dataclass
class TradeState:
    """Intern state per åpen trade."""

    signal_id: str
    position_id: int | None = None
    phase: TradePhase = TradePhase.AWAITING_CONFIRMATION
    entry_price: float = 0.0
    t1_price: float = 0.0
    stop_price: float = 0.0
    full_volume: int = 0  # cents/lots × 100
    remaining_volume: int = 0  # etter T1 / 8-candle halvlukk
    t1_hit: bool = False  # første halvlukk gjort (T1 eller 8-candle)
    t1_price_reached: bool = False  # T1-målet faktisk nådd (ekte vinner)
    candles_since_entry: int = 0
    confirmation_candles: int = 0
    expiry_candles: int = 32
    direction: str = "sell"  # "buy" | "sell"
    kill_switch: bool = False
    instrument: str = ""
    symbol_id: int = 0
    # ── Horizon-config (fra signal) ──────────────────────────────
    horizon: str = "SWING"
    grade: str | None = None
    horizon_config: dict = field(default_factory=dict)
    correlation_group: str | None = None
    order_id: int | None = None  # for limit orders
    lots_used: float | None = None  # ønsket lot-størrelse ved entry (før stepVolume)
    risk_pct_used: float | None = None  # risk-% tier brukt (0.25/0.5/1.0)
    # ── Exit-tracking (P3.5 / P3.6) ───────────────────────────────
    peak_progress: float = 0.0  # høyeste urealisert fremgang mot T1 (0–1+)
    trail_level: float | None = None  # nåværende trailing stop-nivå
    trail_active: bool = False  # trailing aktivert (etter T1 eller P5a)
    reconciled: bool = False  # Overtatt via reconcile (grace period for EMA9)
    # M10: Broker-SL/TP ved reconcile-tidspunkt — brukes til å varsle
    # hvis botens trail/BE-logikk overskriver manuelt satte verdier.
    reconciled_sl: float = 0.0
    reconciled_tp: float = 0.0


@dataclass
class CandleBuffer:
    """Holder de siste N lukkede candles per symbol + "current" under-bygging."""

    candles: deque = field(default_factory=lambda: deque(maxlen=50))
    current_open: float | None = None
    current_high: float | None = None
    current_low: float | None = None
    current_close: float | None = None
    current_ts: int | None = None  # Unix ms
