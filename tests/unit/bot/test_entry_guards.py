"""Tester for vaktene innført 2026-09-05 i `bot.entry`.

- Nivå-basert loss-cooldown (signal_id er slot-hash — blokk kun når
  signalets entry ligger innenfor level_atr_mult × ATR av tapt entry)
- Batch-TTL mot `signals_generated_at` (ikke per-signal created_at)
- Fill-tids-vakt (SL-avstand og R:R målt på faktisk fill-pris)
- Sveip av AWAITING-states uten ordre når signalet forsvinner
- Samme-retning-tak på tvers av horisonter
- Event-blackout-filter og MAKRO uten T1 i R:R-filteret
- USD→kontovaluta-kurs og ATR i åpnings-logg
"""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bedrock.bot.config import BotConfig, ReloadableConfig
from bedrock.bot.entry import EntryEngine, LostLevel
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.state import Candle, TradePhase, TradeState

# ─────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────


def _client(
    *,
    symbol_map: dict[str, int] | None = None,
    bid: float = 1.0800,
    ask: float = 1.0802,
    balance: float = 100_000.0,
) -> MagicMock:
    symbol_map = symbol_map or {"EURUSD": 1}
    stub = MagicMock()
    stub.symbol_map = symbol_map
    stub.last_bid = dict.fromkeys(symbol_map.values(), bid)
    stub.last_ask = dict.fromkeys(symbol_map.values(), ask)
    stub.spread_history = {sid: deque([ask - bid] * 15, maxlen=20) for sid in symbol_map.values()}
    stub.symbol_digits = dict.fromkeys(symbol_map.values(), 5)
    stub.symbol_price_digits = dict.fromkeys(symbol_map.values(), 5)
    stub.symbol_pip = {}
    stub.symbol_info = {
        sid: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}
        for sid in symbol_map.values()
    }
    stub.price_feed_sids = {}
    stub.account_balance = balance
    return stub


@pytest.fixture
def config() -> ReloadableConfig:
    cfg = BotConfig().reloadable
    cfg.sizing.account_currency = "USD"
    return cfg


@pytest.fixture
def safety(tmp_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=tmp_path / "daily.json")


def _engine(
    client: MagicMock,
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    *,
    execute_trade: MagicMock | None = None,
) -> EntryEngine:
    eng = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        execute_trade=execute_trade,
        manage_open_positions=MagicMock(),
        stats_path=tmp_path / "s.json",
        trade_log_path=tmp_path / "signal_log.json",
    )
    eng.on_symbols_ready(client)
    return eng


def _sig(
    *,
    sig_id: str = "eur-buy-swing",
    horizon: str = "SWING",
    alert: float = 1.0801,
    stop: float = 1.0750,
    t1: float | None = 1.0900,
    atr: float = 0.0100,
    direction: str = "buy",
    instrument: str = "EURUSD",
    zone: tuple[float, float] = (1.0798, 1.0804),
) -> dict:
    return {
        "id": sig_id,
        "instrument": instrument,
        "direction": direction,
        "status": "watchlist",
        "alert_level": alert,
        "stop": stop,
        "t1": t1 if t1 is not None else 0.0,
        "atr": atr,
        "entry_zone": list(zone),
        "horizon": horizon,
        "horizon_config": {},
    }


def _candle(close: float = 1.0801) -> Candle:
    return Candle(
        open=close,
        high=close + 0.0001,
        low=close - 0.0001,
        close=close,
        volume=1,
        timestamp=datetime.now(timezone.utc),
    )


def _fresh_batch(*signals: dict, **extra: object) -> dict:
    return {
        "signals": list(signals),
        "global_state": {},
        "rules": {},
        "signals_generated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


# ─────────────────────────────────────────────────────────────
# Nivå-basert cooldown
# ─────────────────────────────────────────────────────────────


def test_cooldown_blocks_only_within_level_tolerance(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    """Tap på 1.0800 med ATR 0.01: entry 1.0805 (0.05 ATR unna) blokkeres,
    entry 1.0950 (1.5 ATR unna) er et nytt nivå og slipper gjennom."""
    eng = _engine(_client(), safety, config, [], tmp_path)
    eng.record_lost_signal("eur-buy-swing", 1.0800)
    assert eng._is_in_loss_cooldown("eur-buy-swing", 1.0805, 0.01) is not None
    assert eng._is_in_loss_cooldown("eur-buy-swing", 1.0950, 0.01) is None
    # Tap-registreringen skal ikke ryddes bort selv om nivået har flyttet seg
    assert "eur-buy-swing" in eng._lost_signal_ids


def test_cooldown_e2e_allows_state_when_level_moved(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states: list[TradeState] = []
    client = _client(bid=1.0950, ask=1.0952)
    eng = _engine(client, safety, config, states, tmp_path)
    eng.record_lost_signal("eur-buy-swing", 1.0800)
    sig = _sig(alert=1.0951, zone=(1.0948, 1.0954), stop=1.0850, t1=1.1200)
    eng.signal_data = _fresh_batch(sig)
    eng._on_candle_closed(1, _candle(1.0951))
    assert len(states) == 1


def test_cooldown_e2e_blocks_state_at_same_level(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states: list[TradeState] = []
    eng = _engine(_client(), safety, config, states, tmp_path)
    eng.record_lost_signal("eur-buy-swing", 1.0800)
    eng.signal_data = _fresh_batch(_sig())
    eng._on_candle_closed(1, _candle())
    assert states == []


def test_cooldown_unknown_level_blocks_regardless(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    eng.record_lost_signal("eur-buy-swing")  # ingen entry-pris (eldre logg)
    assert eng._is_in_loss_cooldown("eur-buy-swing", 1.5000, 0.01) is not None


def test_cooldown_multiple_levels_each_block(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    eng.record_lost_signal("id", 1.0800)
    eng.record_lost_signal("id", 1.1000)
    assert eng._is_in_loss_cooldown("id", 1.0995, 0.005) is not None
    assert eng._is_in_loss_cooldown("id", 1.0803, 0.005) is not None
    assert eng._is_in_loss_cooldown("id", 1.0900, 0.005) is None


def test_cooldown_ttl_mode_drops_expired_levels(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    config.cooldown.permanent_after_loss = False
    eng = _engine(_client(), safety, config, [], tmp_path)
    old = datetime.now(timezone.utc) - timedelta(hours=config.cooldown.loss_ttl_hours + 1)
    eng._lost_signal_ids["id"] = [
        LostLevel(lost_at=old, entry_price=1.0800),
        LostLevel(lost_at=datetime.now(timezone.utc), entry_price=1.1000),
    ]
    assert eng._is_in_loss_cooldown("id", 1.0800, 0.01) is None  # utløpt
    assert [lvl.entry_price for lvl in eng._lost_signal_ids["id"]] == [1.1000]
    assert eng._is_in_loss_cooldown("id", 1.1000, 0.01) is not None


def _log_entry(sig_id: str, closed_at: datetime, entry: float | None, result: str = "loss") -> dict:
    ts = closed_at.strftime("%Y-%m-%d %H:%M timezone.utc")
    signal: dict = {"id": sig_id, "instrument": "EURUSD"}
    if entry is not None:
        signal["entry"] = entry
    return {
        "timestamp": ts,
        "closed_at": ts,
        "result": result,
        "exit_reason": "SL",
        "signal": signal,
    }


def test_load_from_log_reads_entry_price_and_applies_age_cap(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    now = datetime.now(timezone.utc)
    log = tmp_path / "signal_log.json"
    log.write_text(
        json.dumps(
            {
                "entries": [
                    _log_entry("fresh", now - timedelta(days=5), 1.0800),
                    _log_entry("ancient", now - timedelta(days=200), 1.2000),
                    _log_entry("no-entry", now - timedelta(days=1), None),
                    _log_entry("won", now - timedelta(days=1), 1.3, result="win"),
                ]
            }
        )
    )
    eng = _engine(_client(), safety, config, [], tmp_path)
    assert [lvl.entry_price for lvl in eng._lost_signal_ids["fresh"]] == [1.0800]
    assert "ancient" not in eng._lost_signal_ids  # > loss_level_max_age_days (90)
    assert eng._lost_signal_ids["no-entry"][0].entry_price is None
    assert "won" not in eng._lost_signal_ids


def test_load_from_log_age_cap_zero_keeps_everything(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    config.cooldown.loss_level_max_age_days = 0
    now = datetime.now(timezone.utc)
    log = tmp_path / "signal_log.json"
    log.write_text(json.dumps({"entries": [_log_entry("ancient", now - timedelta(days=400), 1.2)]}))
    eng = _engine(_client(), safety, config, [], tmp_path)
    assert "ancient" in eng._lost_signal_ids


def test_record_lost_signal_ignores_nonpositive_entry(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    eng.record_lost_signal("id", 0.0)
    assert eng._lost_signal_ids["id"][0].entry_price is None


# ─────────────────────────────────────────────────────────────
# Batch-TTL
# ─────────────────────────────────────────────────────────────


def test_batch_ttl_ignores_per_signal_created_at(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    """Gammel created_at (first_seen) skal ikke drepe et stabilt setup
    når batchen er fersk."""
    states: list[TradeState] = []
    eng = _engine(_client(), safety, config, states, tmp_path)
    sig = _sig()
    sig["created_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    eng.signal_data = _fresh_batch(sig)
    eng._on_candle_closed(1, _candle())
    assert len(states) == 1


def test_batch_ttl_falls_back_to_generated_at_with_single_warning(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    states: list[TradeState] = []
    eng = _engine(_client(), safety, config, states, tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    eng.signal_data = {
        "signals": [_sig()],
        "global_state": {},
        "rules": {},
        "generated_at": old,  # eldre server uten signals_generated_at
    }
    with caplog.at_level(logging.WARNING, logger="bedrock.bot.entry"):
        eng._on_candle_closed(1, _candle())
        eng._on_candle_closed(1, _candle())
    assert states == []  # 5 t > SWING-TTL 4 t
    assert sum("signals_generated_at mangler" in r.message for r in caplog.records) == 1


def test_batch_ttl_absent_timestamps_means_no_ttl(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states: list[TradeState] = []
    eng = _engine(_client(), safety, config, states, tmp_path)
    eng.signal_data = {"signals": [_sig()], "global_state": {}, "rules": {}}
    eng._on_candle_closed(1, _candle())
    assert len(states) == 1


def test_batch_ttl_logs_once_per_horizon_and_batch(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    eng.signal_data = _fresh_batch(_sig(), signals_generated_at=old)
    with caplog.at_level(logging.INFO, logger="bedrock.bot.entry"):
        assert eng._batch_is_stale("SWING") is True
        assert eng._batch_is_stale("SWING") is True
        assert eng._batch_is_stale("MAKRO") is False  # 24 t TTL
    assert sum("[TTL]" in r.message for r in caplog.records) == 1


# ─────────────────────────────────────────────────────────────
# Fill-tids-vakt
# ─────────────────────────────────────────────────────────────


def test_fill_guard_blocks_sl_too_close(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    sig = _sig(alert=1.0800, stop=1.0780, t1=1.0900, horizon="SCALP")
    # Planlagt 0.0020; fill 1.0790 → 0.0010 = 50 % < 60 %
    assert eng._passes_fill_guard(sig, 1.0790, 0.0010) is False
    # 0.0013 = 65 % → OK (R:R 0.011/0.0013 = 8.5)
    assert eng._passes_fill_guard(sig, 1.0793, 0.0013) is True


def test_fill_guard_blocks_sl_too_far(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    sig = _sig(alert=1.0800, stop=1.0780, t1=None, horizon="MAKRO")
    # Planlagt 0.0020; fill 1.0835 → 0.0055 = 275 % > 150 %
    assert eng._passes_fill_guard(sig, 1.0835, 0.0055) is False
    assert eng._passes_fill_guard(sig, 1.0810, 0.0030) is True  # 150 % grense inkl.


def test_fill_guard_rr_at_fill_per_horizon(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    # Planlagt R:R = 0.0050/0.0020 = 2.5; fill 1.0801 → 0.0049/0.0021 = 2.33
    swing = _sig(alert=1.0800, stop=1.0780, t1=1.0850, horizon="SWING")
    scalp = _sig(alert=1.0800, stop=1.0780, t1=1.0850, horizon="SCALP")
    assert eng._passes_fill_guard(swing, 1.0801, 0.0021) is False
    assert eng._passes_fill_guard(scalp, 1.0801, 0.0021) is True  # gulv 1.5
    config.entry_guard.check_rr_at_fill = False
    assert eng._passes_fill_guard(swing, 1.0801, 0.0021) is True


def test_execute_trade_blocked_by_fill_guard_removes_state_and_resets_flag(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states: list[TradeState] = []
    client = _client(bid=1.0789, ask=1.0790)  # 0.0010 fra SL
    eng = _engine(client, safety, config, states, tmp_path)
    state = TradeState(
        signal_id="s", symbol_id=1, instrument="EURUSD", direction="buy", stop_price=1.0780
    )
    states.append(state)
    sig = _sig(sig_id="s", alert=1.0800, stop=1.0780, t1=1.0900, horizon="SCALP")
    eng.signal_data = _fresh_batch(sig)
    eng._execute_trade_impl(sig, state, _candle(1.0790))
    client.send_new_order.assert_not_called()
    assert state not in states
    assert state.order_sent is False


def test_execute_trade_limit_orders_skip_fill_guard(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    """LIMIT fylles på alert_level → planlagt geometri holder → ingen vakt."""
    states: list[TradeState] = []
    client = _client(bid=1.0800, ask=1.0801)
    eng = _engine(client, safety, config, states, tmp_path)
    state = TradeState(
        signal_id="s", symbol_id=1, instrument="EURUSD", direction="buy", stop_price=1.0780
    )
    states.append(state)
    sig = _sig(sig_id="s", alert=1.0800, stop=1.0780, t1=1.0850, horizon="SWING")  # R:R 2.33@fill
    sig["horizon_config"]["use_limit_orders"] = True
    eng.signal_data = _fresh_batch(sig)
    eng._execute_trade_impl(sig, state, _candle(1.0801))
    assert client.send_new_order.call_args.kwargs["order_type"] == "LIMIT"


def test_execute_trade_refreshes_levels_from_fresh_signal(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    """Staten tok stop/t1 ved ALERT; ordren bruker ferskt signal — staten
    skal følge signalet (P0-breach og logg må matche det som ble sendt)."""
    states: list[TradeState] = []
    client = _client(bid=1.0800, ask=1.0801)
    eng = _engine(client, safety, config, states, tmp_path)
    state = TradeState(
        signal_id="s",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        stop_price=1.0700,  # gammelt nivå
        t1_price=1.0950,
    )
    states.append(state)
    sig = _sig(sig_id="s", alert=1.0800, stop=1.0780, t1=1.0860, horizon="SWING", atr=0.0123)
    eng.signal_data = _fresh_batch(sig)
    eng._execute_trade_impl(sig, state, _candle(1.0801))
    client.send_new_order.assert_called_once()
    assert state.stop_price == 1.0780
    assert state.t1_price == 1.0860
    assert state.atr_d1 == 0.0123
    assert state.order_sent is True
    assert state.order_id is None  # MARKET: ingen placeholder


# ─────────────────────────────────────────────────────────────
# Sveip av AWAITING-states
# ─────────────────────────────────────────────────────────────


def _awaiting(sig_id: str, *, order_sent: bool = False, order_id: int | None = None) -> TradeState:
    return TradeState(
        signal_id=sig_id,
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        horizon="SWING",
        phase=TradePhase.AWAITING_CONFIRMATION,
        order_sent=order_sent,
        order_id=order_id,
    )


def test_sweep_removes_awaiting_state_without_order_when_signal_gone(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states = [_awaiting("gone"), _awaiting("still-here")]
    client = _client()
    eng = _engine(client, safety, config, states, tmp_path)
    eng.on_signals(_fresh_batch(_sig(sig_id="still-here")))
    assert [s.signal_id for s in states] == ["still-here"]
    client.cancel_order.assert_not_called()


def test_sweep_keeps_in_flight_market_and_placeholder_limit(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states = [_awaiting("mkt", order_sent=True), _awaiting("lim", order_sent=True, order_id=-1)]
    client = _client()
    eng = _engine(client, safety, config, states, tmp_path)
    eng.on_signals(_fresh_batch(_sig(sig_id="other")))
    assert {s.signal_id for s in states} == {"mkt", "lim"}
    client.cancel_order.assert_not_called()


def test_sweep_cancels_accepted_limit_when_signal_gone(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states = [_awaiting("lim", order_sent=True, order_id=77)]
    client = _client()
    eng = _engine(client, safety, config, states, tmp_path)
    eng.on_signals(_fresh_batch(_sig(sig_id="other")))
    assert states == []
    client.cancel_order.assert_called_once_with(order_id=77)


# ─────────────────────────────────────────────────────────────
# Samme retning på tvers av horisonter
# ─────────────────────────────────────────────────────────────


def test_same_direction_counts_in_flight_orders_but_not_plain_awaiting(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    states: list[TradeState] = [
        TradeState(
            signal_id="scalp-buy",
            symbol_id=1,
            instrument="EURUSD",
            direction="buy",
            horizon="SCALP",
            phase=TradePhase.AWAITING_CONFIRMATION,
        )
    ]
    eng = _engine(_client(), safety, config, states, tmp_path)
    eng.signal_data = _fresh_batch(_sig(sig_id="swing-buy", horizon="SWING"))
    eng._on_candle_closed(1, _candle())
    assert {s.signal_id for s in states} == {"scalp-buy", "swing-buy"}

    states[0].order_sent = True  # nå teller scalp-en som eksponering
    states.pop(1)
    eng.signal_data = _fresh_batch(_sig(sig_id="makro-buy", horizon="MAKRO", t1=None))
    eng._on_candle_closed(1, _candle())
    assert {s.signal_id for s in states} == {"scalp-buy"}


def test_same_direction_zero_disables_gate(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    config.entry_guard.max_same_direction_per_instrument = 0
    states: list[TradeState] = [
        TradeState(
            signal_id="scalp-buy",
            symbol_id=1,
            instrument="EURUSD",
            direction="buy",
            horizon="SCALP",
            phase=TradePhase.IN_TRADE,
        )
    ]
    eng = _engine(_client(), safety, config, states, tmp_path)
    eng.signal_data = _fresh_batch(_sig(sig_id="swing-buy", horizon="SWING"))
    eng._on_candle_closed(1, _candle())
    assert len(states) == 2


# ─────────────────────────────────────────────────────────────
# Filtre: event-blackout og MAKRO uten T1
# ─────────────────────────────────────────────────────────────


def test_filter_event_blackout_blocks_listed_instrument(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    blackout = {"EURUSD": {"event": "Non-Farm Payrolls", "country": "USD", "minutes_away": 35}}
    eng.signal_data = _fresh_batch(global_state={"event_blackout": blackout})
    ok_sig = _sig(t1=1.0950)  # R:R 2.92 ≥ SWING-gulv 2.5 — passerer uten blackout
    with caplog.at_level(logging.INFO, logger="bedrock.bot.entry"):
        assert eng._passes_filters(ok_sig, 1) is False
        assert eng._passes_filters(ok_sig, 1) is False
    assert sum("event-blackout" in r.message for r in caplog.records) == 1
    eng.signal_data = _fresh_batch(global_state={"event_blackout": {"GOLD": {"event": "x"}}})
    assert eng._passes_filters(ok_sig, 1) is True


def test_filter_makro_without_t1_skips_rr(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    eng.signal_data = _fresh_batch()
    assert eng._passes_filters(_sig(horizon="MAKRO", t1=None), 1) is True
    # Med eksplisitt T1 gjelder gulvet (2.0): 0.0049/0.0051 < 2.0
    assert eng._passes_filters(_sig(horizon="MAKRO", t1=1.0850), 1) is False


# ─────────────────────────────────────────────────────────────
# Valutakurs + åpnings-logg
# ─────────────────────────────────────────────────────────────


def test_usd_to_account_rate(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client()
    eng = _engine(client, safety, config, [], tmp_path)
    assert eng.usd_to_account_rate() == 1.0  # USD-konto
    config.sizing.account_currency = "NOK"
    assert eng.usd_to_account_rate() is None  # ingen USDNOK-feed
    client.price_feed_sids = {"USDNOK": 99}
    client.last_bid[99] = 10.5
    assert eng.usd_to_account_rate() == 10.5


def test_log_trade_opened_includes_atr(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    eng = _engine(_client(), safety, config, [], tmp_path)
    state = TradeState(
        signal_id="s",
        symbol_id=1,
        instrument="EURUSD",
        direction="buy",
        entry_price=1.08,
        stop_price=1.07,
        full_volume=1000,
        position_id=5,
        atr_d1=0.0123,
    )
    eng._log_trade_opened(state)
    entry = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]
    assert entry["signal"]["atr"] == 0.0123
