"""Tester for bot.exit — P1-P5 exit-prioritet + cTrader-event-handlere.

Dekker:
- P1 geo-spike: close > entry_price + geo_mult × ATR → STENG
- P2 kill-switch → STENG
- P2.5 weekend-gate (fredag ≥20 CET lukker SCALP; 19 strammer SL)
- P3 T1-hit → partial close + BE + trail-aktiv
- P3.5 trail-stop (ratchet)
- P3.6 give-back (pre-T1)
- P4 EMA9-kryss (post-T1)
- P5a timeout med progress-basert forgrening
- P5b hard close (2× expiry)
- _set_break_even + _compute_weekend_sl + _calc_close_volume + _compute_progress
- _calc_pnl: USD-quote vs USD-base, halv-spread-fratrekk
- _log_trade_closed + _log_reconcile_opened
- on_execution: fill med SL/TP-amend; partial; duplikat-ignorering
- on_order_error: POSITION_NOT_FOUND (TP vs SL-detektering); stuck-state-rydd
- on_reconcile: oppretter TradeState med reconciled=True
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bedrock.bot.config import BotConfig, ReloadableConfig
from bedrock.bot.entry import EntryEngine
from bedrock.bot.exit import ExitEngine
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.state import Candle, TradePhase, TradeState

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


def _make_client_stub(
    *,
    symbol_map: dict[str, int],
    last_bid: dict[int, float] | None = None,
    last_ask: dict[int, float] | None = None,
    symbol_info: dict[int, dict] | None = None,
    symbol_price_digits: dict[int, int] | None = None,
) -> MagicMock:
    stub = MagicMock()
    stub.symbol_map = symbol_map
    stub.last_bid = last_bid or {}
    stub.last_ask = last_ask or {}
    stub.symbol_info = symbol_info or {}
    stub.symbol_price_digits = symbol_price_digits or dict.fromkeys(symbol_map.values(), 5)
    stub.symbol_digits = dict.fromkeys(symbol_map.values(), 5)
    stub.spread_history = {sid: deque(maxlen=20) for sid in symbol_map.values()}
    stub.price_feed_sids = {}
    stub.account_balance = 100_000.0
    return stub


@pytest.fixture
def safety(tmp_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=tmp_path / "daily.json")


@pytest.fixture
def config() -> ReloadableConfig:
    return BotConfig().reloadable


@pytest.fixture
def active_states() -> list[TradeState]:
    return []


@pytest.fixture(autouse=True)
def _freeze_to_thursday(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse: freezer datetime i `bot.exit` til torsdag 12:00 CET slik at
    weekend-guard (fredag 19-20+ CET) ikke triggs utilsiktet. Tester som
    eksplisitt tester weekend-gate overstyrer ved å monkeypatche
    `bot.exit.datetime` direkte — test-lokal patch vinner."""
    from bedrock.bot import exit as exit_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 23, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exit_mod, "datetime", _FrozenDT)


def _make_engines(
    *,
    client: MagicMock,
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> tuple[EntryEngine, ExitEngine]:
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "stats.json",
        trade_log_path=tmp_path / "signal_log.json",
    )
    entry.on_symbols_ready(client)
    exit_engine = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=tmp_path / "signal_log.json",
    )
    entry.set_manage_open_positions(exit_engine.manage_open_positions)
    return entry, exit_engine


def _in_trade_state(
    *,
    symbol_id: int = 1,
    instrument: str = "EURUSD",
    direction: str = "buy",
    entry_price: float = 1.0800,
    stop_price: float = 1.0780,
    t1_price: float = 1.0850,
    full_volume: int = 2000,
    position_id: int = 42,
    horizon: str = "SWING",
) -> TradeState:
    return TradeState(
        signal_id=f"{instrument}-{direction}",
        symbol_id=symbol_id,
        instrument=instrument,
        direction=direction,
        entry_price=entry_price,
        stop_price=stop_price,
        t1_price=t1_price,
        full_volume=full_volume,
        remaining_volume=full_volume,
        position_id=position_id,
        phase=TradePhase.IN_TRADE,
        horizon=horizon,
    )


# ─────────────────────────────────────────────────────────────
# P1 Geo-spike
# ─────────────────────────────────────────────────────────────


def test_p1_geo_spike_closes_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1}, last_bid={1: 1.07}, last_ask={1: 1.07})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0050] * 20  # ATR = 0.0050
    # Ikke SWING → unngå 1H-branch
    state = _in_trade_state(horizon="SCALP")
    active_states.append(state)
    # Move against buy: entry=1.08, close=1.07 → 0.01 > 2.0 × 0.0050 = 0.01? akkurat.
    # Bruk close=1.069 → 0.011 > 0.010
    candle = Candle(
        open=1.08, high=1.08, low=1.069, close=1.069, volume=0, timestamp=datetime.now(timezone.utc)
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


def test_p1_geo_spike_does_not_trigger_in_favor(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0050] * 20
    state = _in_trade_state(horizon="SCALP")
    active_states.append(state)
    # Close 1.082 er i favør for buy (entry=1.08) men UNDER T1=1.0850 → ingen exit
    candle = Candle(
        open=1.08, high=1.083, low=1.08, close=1.082, volume=0, timestamp=datetime.now(timezone.utc)
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_not_called()


# ─────────────────────────────────────────────────────────────
# P2 Kill-switch
# ─────────────────────────────────────────────────────────────


def test_p2_kill_switch_closes(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.001] * 20
    state = _in_trade_state(horizon="SCALP")
    state.kill_switch = True
    active_states.append(state)
    candle = Candle(
        open=1.08,
        high=1.081,
        low=1.079,
        close=1.080,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


# ─────────────────────────────────────────────────────────────
# P3 T1-hit → partial close + BE + trail-aktiv
# ─────────────────────────────────────────────────────────────


def test_p3_t1_hit_partial_close_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.085},
        last_ask={1: 1.0852},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}},
        symbol_price_digits={1: 5},
    )
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    # ATR & EMA for BE-buffer + trail-update (SCALP → 15m)
    entry.atr14[1] = [0.0010] * 20
    entry.ema9[1] = [1.082] * 20
    state = _in_trade_state(horizon="SCALP", full_volume=2000)
    active_states.append(state)
    # Close=1.0851 ≥ T1=1.0850 → T1 reached
    candle = Candle(
        open=1.084,
        high=1.0852,
        low=1.084,
        close=1.0851,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    # Partial close: 50% av 2000 = 1000
    assert any(c.kwargs.get("volume") == 1000 for c in client.close_position.call_args_list)
    assert state.t1_price_reached is True
    assert state.t1_hit is True
    assert state.trail_active is True
    assert state.remaining_volume == 1000
    # BE satt: stop_price ≠ gammelt 1.0780 (flyttet til ~entry)
    assert state.stop_price > 1.0780
    # Trail-level satt
    assert state.trail_level is not None
    # amend_sl_tp kalt (både for BE og trail)
    assert client.amend_sl_tp.called


def test_p3_t1_hit_forced_full_close_when_remaining_below_min(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Hvis 50%-rest < min_vol → steng hele (forced_full)."""
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.085},
        last_ask={1: 1.0852},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1500, "step_volume": 1000}},
        symbol_price_digits={1: 5},
    )
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.001] * 20
    entry.ema9[1] = [1.082] * 20
    state = _in_trade_state(horizon="SCALP", full_volume=2000)
    active_states.append(state)
    # Desired = 1000, men remaining 1000 < min 1500 → steng alt
    candle = Candle(
        open=1.084,
        high=1.0852,
        low=1.084,
        close=1.0851,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    # Pre-create log-entry så _log_trade_closed finner den
    (tmp_path / "signal_log.json").write_text(
        json.dumps(
            {
                "entries": [{"signal": {"id": state.signal_id}, "result": None}],
            }
        )
    )
    ex.manage_open_positions(1, candle)
    assert state not in active_states  # Helt fjernet


# ─────────────────────────────────────────────────────────────
# P3.6 Give-back (pre-T1)
# ─────────────────────────────────────────────────────────────


def test_p36_giveback_closes_when_peak_dropped(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0010] * 20
    state = _in_trade_state(horizon="SCALP")
    state.peak_progress = 0.9  # Allerede nær T1 tidligere
    active_states.append(state)
    # Close=1.0805 (progress = (1.0805-1.08)/(1.0850-1.08) = 0.1) < gb_exit=0.3 for fx
    candle = Candle(
        open=1.081,
        high=1.082,
        low=1.080,
        close=1.0805,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


# ─────────────────────────────────────────────────────────────
# P5a Timeout
# ─────────────────────────────────────────────────────────────


def test_p5a_timeout_negative_progress_closes_loss(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0010] * 20
    state = _in_trade_state(horizon="SCALP")
    state.candles_since_entry = 31  # +1 in loop = 32 = expiry
    state.expiry_candles = 32
    active_states.append(state)
    # Negativ progress (close=1.0795 < entry=1.0800 for buy)
    candle = Candle(
        open=1.08,
        high=1.08,
        low=1.0795,
        close=1.0795,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


def test_p5a_timeout_with_good_progress_activates_trail(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        symbol_price_digits={1: 5},
    )
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0010] * 20
    state = _in_trade_state(horizon="SCALP")
    state.candles_since_entry = 31
    state.expiry_candles = 32
    active_states.append(state)
    # Progress = (1.0840-1.08)/(1.085-1.08) = 0.8 > 0.5 default → trail
    candle = Candle(
        open=1.083,
        high=1.084,
        low=1.083,
        close=1.0840,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_not_called()
    assert state.trail_active is True
    assert state in active_states


# ─────────────────────────────────────────────────────────────
# P5b Hard close
# ─────────────────────────────────────────────────────────────


def test_p5b_hard_close_at_double_expiry(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0010] * 20
    # Post-T1 så P3/P3.6/P5a ikke triggs
    state = _in_trade_state(horizon="SCALP")
    state.t1_price_reached = True
    state.candles_since_entry = 63  # +1 = 64 = 2×32
    state.expiry_candles = 32
    active_states.append(state)
    candle = Candle(
        open=1.084,
        high=1.085,
        low=1.083,
        close=1.084,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def test_compute_progress_buy() -> None:
    safety = SafetyMonitor(state_path=Path("/tmp/x.json"))
    config = BotConfig().reloadable
    client = _make_client_stub(symbol_map={})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=Path("/tmp/s.json"),
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=Path("/tmp/l.json"),
    )
    state = TradeState(signal_id="x", direction="buy", entry_price=1.08, t1_price=1.09)
    assert ex._compute_progress(state, 1.08) == 0.0
    assert ex._compute_progress(state, 1.09) == 1.0
    assert abs(ex._compute_progress(state, 1.085) - 0.5) < 1e-9
    assert ex._compute_progress(state, 1.07) == -1.0


def test_compute_progress_sell() -> None:
    safety = SafetyMonitor(state_path=Path("/tmp/x.json"))
    config = BotConfig().reloadable
    client = _make_client_stub(symbol_map={})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=Path("/tmp/s.json"),
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=Path("/tmp/l.json"),
    )
    state = TradeState(signal_id="x", direction="sell", entry_price=1.09, t1_price=1.08)
    assert ex._compute_progress(state, 1.09) == 0.0
    assert ex._compute_progress(state, 1.08) == 1.0


def test_compute_progress_zero_when_t1_missing() -> None:
    safety = SafetyMonitor(state_path=Path("/tmp/x.json"))
    config = BotConfig().reloadable
    client = _make_client_stub(symbol_map={})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=Path("/tmp/s.json"),
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=Path("/tmp/l.json"),
    )
    state = TradeState(signal_id="x", direction="buy", entry_price=1.08, t1_price=0.0)
    assert ex._compute_progress(state, 1.10) == 0.0


def test_calc_close_volume_partial(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(full_volume=2000)
    state.remaining_volume = 2000
    close_vol, remaining = ex._calc_close_volume(state, 0.5)
    assert close_vol == 1000
    assert remaining == 1000


def test_calc_close_volume_forces_full_when_remaining_below_min(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1500, "step_volume": 1000}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(full_volume=2000)
    state.remaining_volume = 2000
    close_vol, remaining = ex._calc_close_volume(state, 0.5)
    # 50% = 1000, men remaining 1000 < min 1500 → steng alt
    assert close_vol == 2000
    assert remaining == 0


def test_weekend_action_friday_evening(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import exit as exit_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 20, 30, 0, tzinfo=tz)  # Fredag 20:30

    monkeypatch.setattr(exit_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    action = ex._weekend_action()
    assert action["close_scalp"] is True
    assert action["tighten_sl"] is True


def test_weekend_action_friday_late_afternoon(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import exit as exit_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 19, 30, 0, tzinfo=tz)

    monkeypatch.setattr(exit_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    action = ex._weekend_action()
    assert action["close_scalp"] is False
    assert action["tighten_sl"] is True


def test_weekend_action_non_friday(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import exit as exit_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 23, 20, 30, 0, tzinfo=tz)  # Torsdag

    monkeypatch.setattr(exit_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    action = ex._weekend_action()
    assert action == {"close_scalp": False, "tighten_sl": False}


def test_compute_weekend_sl_tightens_for_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", stop_price=1.0700)
    # Close=1.0850, ATR=0.005 → new_sl = 1.0850 - 1.5×0.005 = 1.07750. Strammere enn 1.07.
    new_sl = ex._compute_weekend_sl(state, 1.0850, 0.005)
    assert new_sl is not None
    assert new_sl > 1.07


def test_compute_weekend_sl_none_when_not_tighter(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", stop_price=1.08)  # SL allerede høy
    new_sl = ex._compute_weekend_sl(state, 1.0810, 0.005)  # 1.0735 < 1.08 → ikke strammere
    assert new_sl is None


def test_set_break_even_buy_sends_amend(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0850},
        last_ask={1: 1.0852},
        symbol_price_digits={1: 5},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [0.0010] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", entry_price=1.08, stop_price=1.0780)
    ex._set_break_even(state, 1)
    client.amend_sl_tp.assert_called_once()
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["position_id"] == 42
    assert kwargs["stop_loss"] > 1.0780
    assert kwargs["stop_loss"] < 1.08


def test_update_trail_ratchet_for_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [0.0010] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", horizon="SCALP")
    # Close=1.085, mult=1.5, ATR=0.001 → trail = 1.0835
    ex._update_trail(state, 1.085, 1, mult=1.5)
    trail1 = state.trail_level
    assert trail1 is not None and abs(trail1 - 1.0835) < 1e-9
    # Lavere close → trail skal IKKE falle (ratchet)
    ex._update_trail(state, 1.082, 1, mult=1.5)
    assert state.trail_level == trail1
    # Høyere close → trail skal heve
    ex._update_trail(state, 1.090, 1, mult=1.5)
    assert state.trail_level > trail1


def test_update_trail_respects_tighter_state_stop_price_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Når state.stop_price er strammere enn trail_level (f.eks. etter
    P2.5 weekend-tighten på SWING post-T1), skal amend_sl_tp bruke den
    strammere SL — ikke overskrive den med trail_level.

    Buy: tightere SL = høyere. trail = close − mult×ATR; weekend-SL kan
    være høyere (close − weekend_mult×ATR med lavere mult).
    """
    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [0.0010] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", horizon="SWING", entry_price=1.080, stop_price=1.0780)
    # Simulér: weekend-tighten har satt state.stop_price = 1.0845 (strammere)
    state.stop_price = 1.0845
    # Trail: close=1.085, mult=3.5, ATR=0.001 → trail = 1.0815 (LØSERE enn weekend-SL)
    ex._update_trail(state, 1.085, 1, mult=3.5)
    # Trail-level oppdateres uavhengig (intern state)
    assert state.trail_level == 1.0815
    # Men amend skal bruke max(trail, stop_price) = 1.0845 — strammere SL
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == 1.0845, (
        f"Trail amend skulle bruke strammere weekend-SL 1.0845, men brukte {kwargs['stop_loss']}"
    )


def test_update_trail_respects_tighter_state_stop_price_sell(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Sell-speilbilde: tightere SL = lavere, så amend skal bruke
    min(trail, stop_price).
    """
    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [0.0010] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="sell", horizon="SWING", entry_price=1.080, stop_price=1.0820)
    # Weekend-tighten satte state.stop_price = 1.0775 (strammere for sell = lavere)
    state.stop_price = 1.0775
    # Trail: close=1.075, mult=3.5, ATR=0.001 → trail = 1.0785 (LØSERE: høyere enn weekend-SL)
    ex._update_trail(state, 1.075, 1, mult=3.5)
    assert state.trail_level == 1.0785
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == 1.0775, (
        f"Sell trail skulle bruke strammere weekend-SL 1.0775 (lavere=strammere for sell), "
        f"men brukte {kwargs['stop_loss']}"
    )


def test_update_trail_uses_trail_level_when_it_is_tighter_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Når trail-level rachet høyere enn state.stop_price (forventet i god
    progress), skal amend bruke trail_level — ikke gå tilbake til løsere SL.
    """
    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [0.0010] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", horizon="SCALP", entry_price=1.080, stop_price=1.0780)
    # close=1.090, mult=1.5, ATR=0.001 → trail = 1.0885 (HØYERE = strammere enn 1.0780)
    ex._update_trail(state, 1.090, 1, mult=1.5)
    assert state.trail_level == 1.0885
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == 1.0885, "Trail er strammere enn stop_price → bruk trail"


# ─────────────────────────────────────────────────────────────
# _calc_pnl
# ─────────────────────────────────────────────────────────────


def test_calc_pnl_usd_quote_buy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0850},
        symbol_price_digits={1: 5},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(direction="buy", entry_price=1.08, full_volume=100_000)
    state.remaining_volume = 100_000
    pnl = ex._calc_pnl(state, 1.09)
    # price_diff = 0.01 (BUY), vol = 100000/100 = 1000, pnl_usd = 10.0
    assert pnl["pnl_usd"] == 10.0
    assert pnl["pips"] == 100.0


def test_calc_pnl_usd_base_usdjpy(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"USDJPY": 2},
        symbol_price_digits={2: 3},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = TradeState(
        signal_id="usdjpy-1",
        symbol_id=2,
        instrument="USDJPY",
        direction="buy",
        entry_price=150.00,
        t1_price=151.0,
        full_volume=100_000,
        remaining_volume=100_000,
        position_id=9,
        phase=TradePhase.IN_TRADE,
    )
    pnl = ex._calc_pnl(state, 151.00)
    # USD-base: pnl_jpy / close → USD. price_diff=1.0, vol=1000
    # pnl_usd = 1.0 × 1000 / 151 ≈ 6.62
    assert pnl["pnl_usd"] > 6.5
    assert pnl["pnl_usd"] < 6.7


def test_calc_pnl_empty_when_no_entry(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = TradeState(signal_id="x", entry_price=0.0)
    assert ex._calc_pnl(state, 1.08) == {}


# ─────────────────────────────────────────────────────────────
# _log_trade_closed / reconcile-logging
# ─────────────────────────────────────────────────────────────


def test_log_trade_closed_updates_entry_and_accumulates_daily_loss(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Loss → daily_loss akkumuleres via SafetyMonitor."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "signal": {"id": "sig-1"},
                        "result": None,
                        "closed_at": None,
                        "exit_reason": None,
                    }
                ]
            }
        )
    )
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.07},
        symbol_price_digits={1: 5},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=log_path,
    )
    state = TradeState(
        signal_id="sig-1",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        entry_price=1.08,
        full_volume=100_000,
        remaining_volume=100_000,
        position_id=5,
        phase=TradePhase.IN_TRADE,
    )
    ex._log_trade_closed(state, "SL", 1.07)
    data = json.loads(log_path.read_text())
    e = data["entries"][0]
    assert e["result"] == "loss"
    assert e["exit_reason"] == "SL"
    assert e["pnl"]["pnl_usd"] < 0
    # Daily-loss akkumulert
    assert safety.daily_loss > 0


def test_log_trade_closed_no_op_when_file_missing(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Fil-mangler → logger ikke exception, ingen akkumulering."""
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "missing.json",
    )
    state = _in_trade_state()
    ex._log_trade_closed(state, "SL", 1.07)
    assert safety.daily_loss == 0


def test_log_reconcile_opened_creates_entry(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "signal_log.json"
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=log_path,
    )
    state = _in_trade_state(full_volume=2000)
    ex._log_reconcile_opened(state)
    data = json.loads(log_path.read_text())
    assert data["entries"][0]["signal"]["reconciled"] is True
    assert data["entries"][0]["signal"]["position_id"] == 42


def test_log_reconcile_opened_skips_when_already_present(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Eksisterende åpen entry for signal_id → ikke dupliser."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(json.dumps({"entries": [{"signal": {"id": "EURUSD-buy"}, "result": None}]}))
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=log_path,
    )
    state = _in_trade_state()
    ex._log_reconcile_opened(state)
    data = json.loads(log_path.read_text())
    assert len(data["entries"]) == 1


# ─────────────────────────────────────────────────────────────
# cTrader event-handlers: on_execution, on_order_error, on_reconcile
# ─────────────────────────────────────────────────────────────


def _make_position_event(
    *,
    position_id: int,
    label: str,
    filled_volume: int | None = None,
) -> MagicMock:
    """Mock event med `position` + `deal` fields matching protobuf layout."""
    event = MagicMock()
    event.HasField = lambda fld: fld in ("position", "deal")

    event.position = MagicMock()
    event.position.positionId = position_id
    event.position.HasField = lambda fld: fld == "tradeData"
    event.position.tradeData.label = label

    event.deal = MagicMock()
    event.deal.HasField = lambda fld: False  # no closePositionDetail
    event.deal.dealId = 123
    event.deal.positionId = position_id
    event.deal.dealStatus = 0
    event.deal.moneyDigits = 2
    event.deal.commission = 0
    event.deal.filledVolume = filled_volume
    event.deal.volume = filled_volume
    return event


def _make_order_event(
    *,
    order_id: int,
    label: str,
    execution_type: int,
) -> MagicMock:
    """Mock execution-event for ORDER_ACCEPTED / EXPIRED / CANCELLED / REJECTED."""
    event = MagicMock()
    event.executionType = execution_type
    event.HasField = lambda fld: fld == "order"
    event.order = MagicMock()
    event.order.orderId = order_id
    event.order.HasField = lambda fld: fld == "tradeData"
    event.order.tradeData.label = label
    return event


def test_on_execution_order_accepted_captures_order_id(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """ORDER_ACCEPTED skal sette state.order_id = real orderId fra cTrader.
    Uten dette har vi ingen orderId å kanselle med ved sweep."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    _entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="eur-pending",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        entry_price=1.080,
        stop_price=1.078,
        t1_price=1.085,
        full_volume=2000,
        order_id=-1,  # placeholder
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_order_event(
        order_id=42,
        label="SE-eur-pending",
        execution_type=ProtoOAExecutionType.ORDER_ACCEPTED,
    )
    ex.on_execution(event)
    assert state.order_id == 42
    assert state.phase == TradePhase.AWAITING_CONFIRMATION  # still pending
    assert state in active_states


def test_on_execution_order_accepted_does_not_overwrite_market_state_order_id(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """KRITISK regresjons-vakt: ORDER_ACCEPTED skal IKKE sette order_id på
    MARKET-state. MARKET har order_id=None som default; is_limit-check
    (`state.order_id is not None and state.order_id != 0`) bruker det
    til å bestemme at SL/TP må amendes etter fill. Hvis vi overskriver
    med real orderId, vil MARKET-fill aldri amende SL/TP og posisjonen
    kjører uten beskyttelse.
    """
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    _entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="market-sig",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        order_id=None,  # MARKET — ingen placeholder satt av entry.py
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_order_event(
        order_id=999,
        label="SE-market-sig",
        execution_type=ProtoOAExecutionType.ORDER_ACCEPTED,
    )
    ex.on_execution(event)
    # MARKET-state skal beholde order_id=None — ellers bryter is_limit-checken
    assert state.order_id is None, (
        "ORDER_ACCEPTED på MARKET-state skal IKKE sette order_id "
        "(ville brutt is_limit-check + ført til MARKET-fill uten SL/TP)"
    )


def test_on_execution_order_expired_removes_state(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """ORDER_EXPIRED på en LIMIT skal fjerne AWAITING_CONFIRMATION-state
    så ny signal kan opprette fersk state for samme (instrument, dir, hor)."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    _entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="expired-sig",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        order_id=42,
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_order_event(
        order_id=42,
        label="SE-expired-sig",
        execution_type=ProtoOAExecutionType.ORDER_EXPIRED,
    )
    ex.on_execution(event)
    assert state not in active_states


def test_on_execution_order_rejected_removes_state(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """ORDER_REJECTED (server avviste LIMIT — feil pris/volum/etc.) skal
    fjerne staten så dedup-blokken ikke holder igjen for samme triplet."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    _entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="rejected-sig",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        order_id=-1,  # rejected før real orderId ble allokert
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_order_event(
        order_id=0,
        label="SE-rejected-sig",
        execution_type=ProtoOAExecutionType.ORDER_REJECTED,
    )
    ex.on_execution(event)
    assert state not in active_states


def test_on_execution_order_expired_skips_in_trade_state(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """ORDER_EXPIRED på state som er IN_TRADE (= LIMIT er fylt; expiry-event
    er for et annet pending-LIMIT for samme symbol) skal IKKE fjerne staten."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _make_client_stub(symbol_map={"EURUSD": 1}, symbol_price_digits={1: 5})
    _entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="filled-sig",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        order_id=42,
        phase=TradePhase.IN_TRADE,
    )
    active_states.append(state)
    event = _make_order_event(
        order_id=42,
        label="SE-filled-sig",
        execution_type=ProtoOAExecutionType.ORDER_EXPIRED,
    )
    ex.on_execution(event)
    assert state in active_states  # IN_TRADE-state bevart


def test_on_execution_flips_to_in_trade_and_amends_sl_tp(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0799},
        last_ask={1: 1.0801},
        symbol_price_digits={1: 5},
    )
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    # AWAITING-state med signal_id matching label
    state = TradeState(
        signal_id="eur-1",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        entry_price=1.0801,
        stop_price=1.0780,
        t1_price=1.0850,
        full_volume=2000,
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_position_event(position_id=99, label="SE-eur-1", filled_volume=2000)
    ex.on_execution(event)
    assert state.phase == TradePhase.IN_TRADE
    assert state.position_id == 99
    assert state.remaining_volume == 2000
    # MARKET → SL/TP ammendes etter fill
    client.amend_sl_tp.assert_called_once()
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["position_id"] == 99
    assert abs(kwargs["stop_loss"] - 1.0780) < 1e-9


def test_on_execution_partial_fill_records_actual_volume(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0799},
        last_ask={1: 1.0801},
        symbol_price_digits={1: 5},
    )
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="eur-1",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        entry_price=1.08,
        stop_price=1.07,
        t1_price=1.09,
        full_volume=2000,
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_position_event(position_id=5, label="SE-eur-1", filled_volume=1500)
    ex.on_execution(event)
    assert state.full_volume == 1500
    assert state.remaining_volume == 1500


def test_on_execution_duplicate_event_ignored(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = _in_trade_state()
    active_states.append(state)
    event = _make_position_event(
        position_id=42, label=f"SE-{state.signal_id}", filled_volume=state.full_volume
    )
    ex.on_execution(event)
    # Ingen endring + ikke nytt amend
    client.amend_sl_tp.assert_not_called()


def test_on_execution_non_se_label_ignored(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    state = TradeState(
        signal_id="eur-1",
        symbol_id=1,
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(state)
    event = _make_position_event(position_id=7, label="MANUAL-trade", filled_volume=1000)
    ex.on_execution(event)
    assert state.phase == TradePhase.AWAITING_CONFIRMATION


def test_on_order_error_position_not_found_detects_tp(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """POSITION_NOT_FOUND + last_price nær T1 → reason=TP."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(json.dumps({"entries": [{"signal": {"id": "eur-1"}, "result": None}]}))
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0849},  # nær T1=1.0850
        symbol_price_digits={1: 5},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=log_path,
    )
    state = _in_trade_state()
    state.signal_id = "eur-1"
    active_states.append(state)
    event = MagicMock()
    event.errorCode = "POSITION_NOT_FOUND"
    event.description = "Posisjon stengt eksternt"
    ex.on_order_error(event)
    data = json.loads(log_path.read_text())
    assert data["entries"][0]["exit_reason"] == "TP"
    assert state not in active_states


def test_on_order_error_cleans_stuck_state(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Ikke-POSITION_NOT_FOUND error → rydd stuck states (aldri fikk pos)."""
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    stuck = TradeState(
        signal_id="stuck-1",
        symbol_id=1,
        entry_price=1.08,
        phase=TradePhase.AWAITING_CONFIRMATION,
    )
    active_states.append(stuck)
    event = MagicMock()
    event.errorCode = "MARKET_CLOSED"
    event.description = "market closed"
    ex.on_order_error(event)
    assert stuck not in active_states


def test_on_reconcile_creates_states(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1, "GOLD": 2},
        symbol_info={1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    # Bygg res med 2 posisjoner, én SE og én manuell
    pos_se = MagicMock()
    pos_se.positionId = 100
    pos_se.HasField = lambda fld: fld == "tradeData"
    pos_se.tradeData.label = "SE-eur-reconcile"
    pos_se.tradeData.symbolId = 1
    pos_se.tradeData.tradeSide = 1  # BUY
    pos_se.tradeData.volume = 2000
    pos_se.stopLoss = 1.0780
    pos_se.takeProfit = 1.0850
    pos_se.price = 1.0800

    pos_manual = MagicMock()
    pos_manual.positionId = 200
    pos_manual.HasField = lambda fld: fld == "tradeData"
    pos_manual.tradeData.label = "MANUAL-trade"

    res = MagicMock()
    res.position = [pos_se, pos_manual]
    ex.on_reconcile(res)
    assert len(active_states) == 1
    state = active_states[0]
    assert state.position_id == 100
    assert state.reconciled is True
    assert state.reconciled_sl == 1.0780
    assert state.reconciled_tp == 1.0850
    assert state.t1_price_reached is False  # has_tp=True → ikke short-circuit
    assert state.instrument == "EURUSD"


def test_on_reconcile_skips_duplicates(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Allerede i active_states med samme position_id → skip."""
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    active_states.append(_in_trade_state(position_id=100))
    pos = MagicMock()
    pos.positionId = 100
    pos.HasField = lambda fld: fld == "tradeData"
    pos.tradeData.label = "SE-x"
    pos.tradeData.symbolId = 1
    pos.tradeData.tradeSide = 1
    pos.tradeData.volume = 2000
    pos.stopLoss = 1.07
    pos.takeProfit = 1.08
    pos.price = 1.075
    res = MagicMock()
    res.position = [pos]
    ex.on_reconcile(res)
    assert len(active_states) == 1  # ingen duplikat


def _make_reconcile_pos(
    *,
    position_id: int,
    label: str,
    symbol_id: int,
    side: int,
    volume: int,
    stop_loss: float,
    take_profit: float,
    price: float,
) -> MagicMock:
    """Helper for å bygge en cTrader Position-mock for reconcile-tester."""
    pos = MagicMock()
    pos.positionId = position_id
    pos.HasField = lambda fld: fld == "tradeData"
    pos.tradeData.label = label
    pos.tradeData.symbolId = symbol_id
    pos.tradeData.tradeSide = side
    pos.tradeData.volume = volume
    pos.stopLoss = stop_loss
    pos.takeProfit = take_profit
    pos.price = price
    return pos


def test_on_reconcile_restores_sl_tp_from_signal_log_when_server_has_zero(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Bot restarter ofte; cTrader kan rapportere SL=0 fordi tidligere
    amend-kall feilet. Reconcile må slå opp original SL/TP fra
    signal_log.json og sende amend slik at posisjonen igjen er
    beskyttet — uten å overskrive SL som faktisk ER satt på server."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "timestamp": "2026-05-04 18:00 timezone.utc",
                        "result": None,
                        "signal": {
                            "id": "ce2d898262d0",
                            "instrument": "PLATINUM",
                            "direction": "BUY",
                            "entry": 1972.80,
                            "stop": 1966.0,
                            "t1": 2074.80,
                            "position_id": 16567511,
                            "horizon": "SWING",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _make_client_stub(
        symbol_map={"PLATINUM": 1},
        symbol_info={1: {"lot_size": 100, "min_volume": 100, "step_volume": 100}},
        symbol_price_digits={1: 2},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=log_path,
    )
    pos = _make_reconcile_pos(
        position_id=16567511,
        label="SE-ce2d898262d0",
        symbol_id=1,
        side=1,
        volume=200,
        stop_loss=0.0,
        take_profit=0.0,
        price=1972.80,
    )
    res = MagicMock()
    res.position = [pos]
    ex.on_reconcile(res)

    # Amend må ha blitt sendt for å gjenopprette SL/TP
    client.amend_sl_tp.assert_called_once()
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["position_id"] == 16567511
    assert kwargs["stop_loss"] == 1966.0
    assert kwargs["take_profit"] == 2074.80

    # State skal nå reflektere gjenopprettede verdier
    state = active_states[0]
    assert state.stop_price == 1966.0
    assert state.t1_price == 2074.80
    assert state.t1_hit is False  # Restored TP → ikke trail-only-modus
    assert state.reconciled_sl == 1966.0
    assert state.reconciled_tp == 2074.80


def test_on_reconcile_does_not_overwrite_existing_server_sl(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Hvis server allerede har SL/TP satt, restore-logikken skal IKKE
    sende ekstra amend (no-op). Vi sletter ikke eksisterende beskyttelse."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "result": None,
                        "signal": {
                            "id": "abc123",
                            "stop": 1900.0,
                            "t1": 2100.0,
                            "position_id": 999,
                            "instrument": "PLATINUM",
                            "direction": "BUY",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _make_client_stub(
        symbol_map={"PLATINUM": 1},
        symbol_price_digits={1: 2},
        symbol_info={1: {"lot_size": 100, "min_volume": 100, "step_volume": 100}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=log_path,
    )
    # Server har allerede SL=1950, TP=2050 (ulik fra signal_log) — vi skal IKKE røre den
    pos = _make_reconcile_pos(
        position_id=999,
        label="SE-abc123",
        symbol_id=1,
        side=1,
        volume=200,
        stop_loss=1950.0,
        take_profit=2050.0,
        price=1980.0,
    )
    res = MagicMock()
    res.position = [pos]
    ex.on_reconcile(res)
    client.amend_sl_tp.assert_not_called()
    state = active_states[0]
    assert state.stop_price == 1950.0  # uendret fra server
    assert state.t1_price == 2050.0


def test_p0_sl_breach_closes_buy_when_close_below_stop(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Software-SL-breach-vakt: hvis 15m-close er ≤ SL for BUY, bot
    stenger selv om server-side SL mangler. Beskytter mot scenarioet der
    amend feilet og posisjonen ligger ubeskyttet på cTrader-server."""
    client = _make_client_stub(symbol_map={"PLATINUM": 1}, symbol_price_digits={1: 2})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [3.5] * 20
    state = _in_trade_state(
        instrument="PLATINUM",
        direction="buy",
        horizon="SWING",
        entry_price=1976.05,
        stop_price=1966.68,
        t1_price=2074.80,
    )
    active_states.append(state)
    candle = Candle(
        open=1970.0,
        high=1970.0,
        low=1963.0,
        close=1963.5,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()
    assert state not in active_states


def test_p0_sl_breach_closes_sell_when_close_above_stop(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Speilbilde for SELL: close ≥ SL → stenger."""
    client = _make_client_stub(symbol_map={"AUDUSD": 1}, symbol_price_digits={1: 5})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.001] * 20
    state = _in_trade_state(
        instrument="AUDUSD",
        direction="sell",
        horizon="SWING",
        entry_price=0.71744,
        stop_price=0.71860,
        t1_price=0.71058,
    )
    active_states.append(state)
    candle = Candle(
        open=0.7180,
        high=0.7195,
        low=0.7180,
        close=0.7191,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_called_once()


def test_p0_sl_breach_skipped_when_stop_price_zero(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Hvis state.stop_price=0 (fersk MARKET-fill, amend pending), P0
    skal IKKE prøve å stenge basert på SL — geo-spike kan fortsatt fyre."""
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    entry, ex = _make_engines(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        tmp_path=tmp_path,
    )
    entry.atr14[1] = [0.0010] * 20
    state = _in_trade_state(direction="buy", horizon="SWING")
    state.stop_price = 0.0
    active_states.append(state)
    # Liten move (under geo-spike-terskel) — ingen close skal fyre
    candle = Candle(
        open=1.080,
        high=1.080,
        low=1.0795,
        close=1.0796,
        volume=0,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    client.close_position.assert_not_called()


def test_on_reconcile_logs_warning_when_no_signal_log_match(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SL=0 + ingen match i signal_log → log warning, ikke send amend.
    Posisjonen står ubeskyttet men minst ikke tom-amendet til 0."""
    log_path = tmp_path / "signal_log.json"
    log_path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    client = _make_client_stub(
        symbol_map={"PLATINUM": 1},
        symbol_price_digits={1: 2},
        symbol_info={1: {"lot_size": 100, "min_volume": 100, "step_volume": 100}},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
    )
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        entry=entry,
        trade_log_path=log_path,
    )
    pos = _make_reconcile_pos(
        position_id=42,
        label="SE-orphan",
        symbol_id=1,
        side=1,
        volume=200,
        stop_loss=0.0,
        take_profit=0.0,
        price=1972.0,
    )
    res = MagicMock()
    res.position = [pos]
    with caplog.at_level("WARNING"):
        ex.on_reconcile(res)
    client.amend_sl_tp.assert_not_called()
    assert any(
        "RECONCILE-RESTORE" in r.message and "fant ikke" in r.message for r in caplog.records
    ), "Forventet RECONCILE-RESTORE warning"


# ─────────────────────────────────────────────────────────────
# Price-digits-rounding på amend (cTrader avviser flere desimaler)
# ─────────────────────────────────────────────────────────────


def test_amend_sl_tp_rounds_trail_to_symbol_price_digits(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Trail-amend må runde stop_loss til symbolets price_digits.
    Eksempel: PLATINUM med digits=2 fikk tidligere SL=1966.6750244140626
    fra ATR-aritmetikk (float-presisjon) og cTrader avviste med
    INVALID_REQUEST. Med rounding må verdien bli 1966.68.
    """
    client = _make_client_stub(symbol_map={"PLATINUM": 1}, symbol_price_digits={1: 2})
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [3.5] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(
        instrument="PLATINUM",
        direction="buy",
        horizon="SWING",
        entry_price=1972.80,
        stop_price=1966.0,
    )
    # close=1980 mult=2 ATR=3.5 → trail = 1980 − 7 = 1973.0 (eksakt)
    # Tving en float som har for mange desimaler ved å la state.stop_price
    # være strammere — koden velger max(trail, stop) for buy.
    state.stop_price = 1966.6750244140626
    ex._update_trail(state, 1980.0, 1, mult=2.0)
    kwargs = client.amend_sl_tp.call_args.kwargs
    sent_sl = kwargs["stop_loss"]
    assert sent_sl == round(sent_sl, 2), f"SL {sent_sl} har flere desimaler enn price_digits=2"
    assert sent_sl == 1973.0  # trail vinner; rundet eksakt


def test_amend_sl_tp_rounds_break_even_to_symbol_price_digits(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
) -> None:
    """Break-even-amend må også runde. PLATINUM digits=2."""
    client = _make_client_stub(
        symbol_map={"PLATINUM": 1},
        last_bid={1: 1985.0},
        last_ask={1: 1985.0},
        symbol_price_digits={1: 2},
    )
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        stats_path=tmp_path / "s.json",
    )
    entry.on_symbols_ready(client)
    entry.atr14[1] = [3.5] * 20
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=[],
        entry=entry,
        trade_log_path=tmp_path / "l.json",
    )
    state = _in_trade_state(
        instrument="PLATINUM",
        direction="buy",
        horizon="SWING",
        entry_price=1972.7654321,
        stop_price=1966.0,
    )
    ex._set_break_even(state, 1)
    kwargs = client.amend_sl_tp.call_args.kwargs
    sent_sl = kwargs["stop_loss"]
    assert sent_sl == round(sent_sl, 2), f"BE-SL {sent_sl} har flere desimaler enn price_digits=2"
