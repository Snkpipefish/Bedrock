"""State-dataclasses bør konstrueres uten argumenter og ha riktige defaults.

Ren port-test — samme invarianter som ~/scalp_edge/trading_bot.py:335-398.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from bedrock.bot.state import Candle, CandleBuffer, TradePhase, TradeState


def test_trade_phase_values() -> None:
    # Enum-verdiene er auto, vi sjekker bare at de tre forventede
    # medlemmene er definert og distinkte.
    assert {
        TradePhase.AWAITING_CONFIRMATION,
        TradePhase.IN_TRADE,
        TradePhase.CLOSED,
    } == set(TradePhase)


def test_candle_construction() -> None:
    ts = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    c = Candle(open=100.0, high=101.5, low=99.5, close=101.0, volume=500, timestamp=ts)
    assert c.open == 100.0
    assert c.close == 101.0
    assert c.timestamp == ts


def test_trade_state_defaults() -> None:
    s = TradeState(signal_id="sig-1")
    assert s.signal_id == "sig-1"
    assert s.phase is TradePhase.AWAITING_CONFIRMATION
    assert s.direction == "sell"
    assert s.horizon == "SWING"
    assert s.expiry_candles == 32
    assert s.peak_progress == 0.0
    assert s.trail_level is None
    assert s.trail_active is False
    assert s.reconciled is False
    assert s.horizon_config == {}
    # Hvert nytt objekt må ha eget dict (default_factory)
    s2 = TradeState(signal_id="sig-2")
    s.horizon_config["x"] = 1
    assert "x" not in s2.horizon_config


def test_candle_buffer_defaults() -> None:
    b = CandleBuffer()
    assert isinstance(b.candles, deque)
    assert b.candles.maxlen == 50
    assert len(b.candles) == 0
    assert b.current_open is None
    assert b.current_close is None
    assert b.current_ts is None


def test_candle_buffer_independent_deques() -> None:
    """default_factory må gi hver instans sin egen deque."""
    b1 = CandleBuffer()
    b2 = CandleBuffer()
    ts = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    b1.candles.append(Candle(1, 2, 0, 1, 10, ts))
    assert len(b2.candles) == 0
