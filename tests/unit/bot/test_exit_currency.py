"""Tester for 2026-09-05-endringene i `bot.exit` + `bot.safety`.

- Estimert PnL føres i kontovaluta (USD→NOK) og daglig tap korrigeres
  når ekte deal patches inn
- Weekend-stramming på SWING bruker ATR(D1) fra staten, hopper over
  uten kjent D1-ATR
- Fill: server-SL er autoritativ (synk state, ingen amend); amend kun
  når server mangler SL, med trailing for MAKRO
- ORDER_ACCEPTED erstatter kun placeholder -1
- Reconcile gjenoppretter atr_d1 fra signal_log
- SafetyMonitor.adjust_loss
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


def _client(*, usdnok: float | None = 10.0) -> MagicMock:
    stub = MagicMock()
    stub.symbol_map = {"EURUSD": 1}
    stub.last_bid = {1: 1.0800}
    stub.last_ask = {1: 1.0802}
    stub.symbol_info = {1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}}
    stub.symbol_price_digits = {1: 5}
    stub.symbol_digits = {1: 5}
    stub.spread_history = {1: deque(maxlen=20)}
    stub.price_feed_sids = {}
    if usdnok is not None:
        stub.price_feed_sids = {"USDNOK": 99}
        stub.last_bid[99] = usdnok
    stub.account_balance = 500_000.0
    return stub


@pytest.fixture
def safety(tmp_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=tmp_path / "daily.json")


@pytest.fixture
def config() -> ReloadableConfig:
    return BotConfig().reloadable  # NOK-konto (prod-default)


@pytest.fixture(autouse=True)
def _freeze_thursday(monkeypatch: pytest.MonkeyPatch) -> None:
    from bedrock.bot import exit as exit_mod

    class _Thu(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 23, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exit_mod, "datetime", _Thu)


def _engines(
    client: MagicMock,
    safety: SafetyMonitor,
    config: ReloadableConfig,
    states: list[TradeState],
    tmp_path: Path,
) -> tuple[EntryEngine, ExitEngine]:
    entry = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=states,
        stats_path=tmp_path / "stats.json",
        trade_log_path=tmp_path / "signal_log.json",
    )
    entry.on_symbols_ready(client)
    ex = ExitEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=states,
        entry=entry,
        trade_log_path=tmp_path / "signal_log.json",
    )
    return entry, ex


def _state(**kw: object) -> TradeState:
    base: dict = {
        "signal_id": "eur-buy",
        "symbol_id": 1,
        "instrument": "EURUSD",
        "direction": "buy",
        "entry_price": 1.0800,
        "stop_price": 1.0700,
        "t1_price": 1.1000,
        "full_volume": 2000,
        "remaining_volume": 2000,
        "position_id": 42,
        "phase": TradePhase.IN_TRADE,
        "horizon": "SWING",
    }
    base.update(kw)
    return TradeState(**base)


def _open_log(path: Path, state: TradeState, **sig: object) -> None:
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "timestamp": "2026-04-23 10:00 timezone.utc",
                        "closed_at": None,
                        "result": None,
                        "exit_reason": None,
                        "signal": {
                            "id": state.signal_id,
                            "instrument": "EURUSD",
                            "direction": "BUY",
                            "entry": state.entry_price,
                            "stop": state.stop_price,
                            "t1": state.t1_price,
                            "position_id": state.position_id,
                            **sig,
                        },
                    }
                ]
            }
        )
    )


# ─────────────────────────────────────────────────────────────
# Estimert PnL i kontovaluta + daglig tap
# ─────────────────────────────────────────────────────────────


def test_est_loss_converted_to_account_currency(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client(usdnok=10.0)
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state()
    states.append(state)
    _open_log(tmp_path / "signal_log.json", state)
    # 2000 enheter = 20 units; close 1.0780 → -0.0020 × 20 = -0.04 USD → -0.4 NOK
    ex._close_all(state, 1.0780, "TRAIL")
    pnl = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]["pnl"]
    assert pnl["pnl_ccy"] == "NOK"
    assert pnl["pnl_est_usd"] == pytest.approx(-0.04)
    assert pnl["pnl_usd"] == pytest.approx(-0.4)
    assert pnl["daily_loss_added"] == pytest.approx(0.4)
    assert safety.daily_loss == pytest.approx(0.4)


def test_est_loss_without_rate_stays_usd_and_is_tagged(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client(usdnok=None)
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state()
    states.append(state)
    _open_log(tmp_path / "signal_log.json", state)
    ex._close_all(state, 1.0780, "TRAIL")
    pnl = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]["pnl"]
    assert pnl["pnl_ccy"] == "USD"
    assert pnl["pnl_usd"] == pytest.approx(-0.04)
    assert safety.daily_loss == pytest.approx(0.04)


def test_patch_real_close_corrects_daily_loss(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client(usdnok=10.0)
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state()
    states.append(state)
    _open_log(tmp_path / "signal_log.json", state)
    ex._close_all(state, 1.0780, "TRAIL")
    assert safety.daily_loss == pytest.approx(0.4)
    # Ekte deal: -3.0 NOK (spread/slippage større enn estimert)
    ex._patch_log_real_close(42, -3.0, 1.0779)
    pnl = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]["pnl"]
    assert pnl["pnl_real"] is True
    assert pnl["pnl_usd"] == pytest.approx(-3.0)
    assert pnl["daily_loss_added"] == pytest.approx(3.0)
    assert safety.daily_loss == pytest.approx(3.0)
    # Idempotent: ny patch endrer ingenting
    ex._patch_log_real_close(42, -3.0, 1.0779)
    assert safety.daily_loss == pytest.approx(3.0)


def test_patch_real_close_win_reverses_estimated_loss(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client(usdnok=10.0)
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state()
    states.append(state)
    _open_log(tmp_path / "signal_log.json", state)
    ex._close_all(state, 1.0780, "TRAIL")
    assert safety.daily_loss == pytest.approx(0.4)
    ex._patch_log_real_close(42, 2.0, 1.0810)
    e = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]
    assert e["result"] == "win"
    assert e["pnl"]["daily_loss_added"] == 0.0
    assert safety.daily_loss == 0.0


def test_server_close_real_pnl_keeps_account_currency(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client(usdnok=10.0)
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state()
    states.append(state)
    _open_log(tmp_path / "signal_log.json", state)
    state._real_pnl = -130.36  # type: ignore[attr-defined]
    ex._on_server_close(state, 1.0700)
    pnl = json.loads((tmp_path / "signal_log.json").read_text())["entries"][0]["pnl"]
    assert pnl["pnl_real"] is True
    assert pnl["pnl_ccy"] == "NOK"
    assert pnl["pnl_usd"] == pytest.approx(-130.36)
    assert safety.daily_loss == pytest.approx(130.36)
    assert state not in states


# ─────────────────────────────────────────────────────────────
# SafetyMonitor.adjust_loss
# ─────────────────────────────────────────────────────────────


def test_adjust_loss_clamps_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "daily.json"
    m = SafetyMonitor(state_path=path)
    m.add_loss(100.0)
    m.adjust_loss(-30.0)
    assert m.daily_loss == pytest.approx(70.0)
    m.adjust_loss(-500.0)
    assert m.daily_loss == 0.0
    m.adjust_loss(12.5)
    assert SafetyMonitor(state_path=path).daily_loss == pytest.approx(12.5)


# ─────────────────────────────────────────────────────────────
# Weekend-stramming med ATR(D1)
# ─────────────────────────────────────────────────────────────


def _friday_evening(monkeypatch: pytest.MonkeyPatch) -> None:
    from bedrock.bot import exit as exit_mod

    class _Fri(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 19, 30, 0, tzinfo=tz)

    monkeypatch.setattr(exit_mod, "datetime", _Fri)


def test_weekend_tighten_uses_d1_atr(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _friday_evening(monkeypatch)
    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state(atr_d1=0.0100, t1_price=1.2000)
    states.append(state)
    candle = Candle(
        open=1.09,
        high=1.091,
        low=1.089,
        close=1.0900,
        volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    # 1.09 − 1.5 × 0.01 = 1.0750 (strammere enn 1.07)
    assert state.stop_price == pytest.approx(1.0750)
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == pytest.approx(1.0750)


def test_weekend_tighten_skipped_without_d1_atr(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uten kjent ATR(D1) må vi ikke falle tilbake til 1H-ATR — det ga
    scalp-stops på SWING hver fredag."""
    _friday_evening(monkeypatch)
    client = _client()
    states: list[TradeState] = []
    entry, ex = _engines(client, safety, config, states, tmp_path)
    entry.atr14_h1[1] = [0.0010]  # 1H-ATR finnes, men skal ikke brukes
    state = _state(atr_d1=0.0, t1_price=1.2000)
    states.append(state)
    candle = Candle(
        open=1.09,
        high=1.091,
        low=1.089,
        close=1.0900,
        volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    ex.manage_open_positions(1, candle)
    assert state.stop_price == 1.0700
    client.amend_sl_tp.assert_not_called()


# ─────────────────────────────────────────────────────────────
# Fill: server-SL autoritativ
# ─────────────────────────────────────────────────────────────


def _fill_event(*, label: str, position_id: int, sl: float, tp: float) -> MagicMock:
    event = MagicMock()
    event.executionType = 3  # ORDER_FILLED
    event.HasField = lambda fld: fld in ("position", "deal")
    event.position = MagicMock()
    event.position.positionId = position_id
    event.position.stopLoss = sl
    event.position.takeProfit = tp
    event.position.HasField = lambda fld: fld == "tradeData"
    event.position.tradeData.label = label
    event.deal = MagicMock()
    event.deal.HasField = lambda fld: False
    event.deal.dealId = 1
    event.deal.positionId = position_id
    event.deal.moneyDigits = 2
    event.deal.commission = 0
    event.deal.filledVolume = 2000
    event.deal.volume = 2000
    return event


def test_fill_syncs_server_sl_and_skips_amend(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state(phase=TradePhase.AWAITING_CONFIRMATION, position_id=None, order_sent=True)
    states.append(state)
    ex.on_execution(_fill_event(label="SE-eur-buy", position_id=7, sl=1.07755, tp=1.09950))
    assert state.phase == TradePhase.IN_TRADE
    assert state.position_id == 7
    assert state.stop_price == pytest.approx(1.07755)
    assert state.t1_price == pytest.approx(1.09950)
    client.amend_sl_tp.assert_not_called()


def test_fill_without_server_sl_amends_with_trailing_for_makro(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state(
        phase=TradePhase.AWAITING_CONFIRMATION,
        position_id=None,
        order_sent=True,
        horizon="MAKRO",
        t1_price=0.0,
        trail_active=True,
    )
    states.append(state)
    ex.on_execution(_fill_event(label="SE-eur-buy", position_id=7, sl=0.0, tp=0.0))
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == pytest.approx(1.0700)
    assert kwargs["take_profit"] is None
    assert kwargs["trailing_stop_loss"] is True
    assert state.stop_price == pytest.approx(1.0700)


def test_fill_without_server_sl_amends_without_trailing_for_swing(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state(phase=TradePhase.AWAITING_CONFIRMATION, position_id=None, order_sent=True)
    states.append(state)
    ex.on_execution(_fill_event(label="SE-eur-buy", position_id=7, sl=0.0, tp=0.0))
    kwargs = client.amend_sl_tp.call_args.kwargs
    assert kwargs["stop_loss"] == pytest.approx(1.0700)
    assert kwargs["take_profit"] == pytest.approx(1.1000)
    assert kwargs["trailing_stop_loss"] is None


def test_order_accepted_only_replaces_placeholder(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType

    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    state = _state(phase=TradePhase.AWAITING_CONFIRMATION, position_id=None, order_id=42)
    states.append(state)
    event = MagicMock()
    event.executionType = ProtoOAExecutionType.ORDER_ACCEPTED
    event.HasField = lambda fld: fld == "order"
    event.order = MagicMock()
    event.order.orderId = 99  # f.eks. SL/TP-ordre på samme label
    event.order.HasField = lambda fld: fld == "tradeData"
    event.order.tradeData.label = "SE-eur-buy"
    ex.on_execution(event)
    assert state.order_id == 42


# ─────────────────────────────────────────────────────────────
# Reconcile: atr_d1 fra signal_log
# ─────────────────────────────────────────────────────────────


def test_reconcile_restores_atr_d1_from_signal_log(
    safety: SafetyMonitor, config: ReloadableConfig, tmp_path: Path
) -> None:
    client = _client()
    states: list[TradeState] = []
    _, ex = _engines(client, safety, config, states, tmp_path)
    logged = _state(position_id=7)
    _open_log(tmp_path / "signal_log.json", logged, horizon="SWING", atr=0.0123)
    pos = MagicMock()
    pos.positionId = 7
    pos.HasField = lambda fld: fld == "tradeData"
    pos.tradeData.label = "SE-eur-buy"
    pos.tradeData.symbolId = 1
    pos.tradeData.tradeSide = 1
    pos.tradeData.volume = 2000
    pos.stopLoss = 1.0700
    pos.takeProfit = 1.1000
    pos.price = 1.0800
    res = MagicMock()
    res.position = [pos]
    ex.on_reconcile(res)
    assert len(states) == 1
    assert states[0].atr_d1 == pytest.approx(0.0123)
    assert states[0].horizon == "SWING"
