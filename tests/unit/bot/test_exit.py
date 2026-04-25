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
