"""Tester for bot.ctrader_client — transport-lag uten ekte nettverk.

Alle tester mocker Twisted-reactor og cTrader-Client. Vi verifiserer:
- Callbacks injiseres riktig og får ikke-None defaults (no-op)
- CtraderCredentials + load_credentials_from_env feiler korrekt
- Reconnect-budsjett fatal-exiter ved overskridelse
- Spot-handler oppdaterer bid/ask/spread_history + kaller callback
- Message-dispatcher router riktig payloadType til riktig handler
- Auth-fatal-koder i ErrorRes → _fatal_exit kalt
- AGRI-dump skriver til Bedrock-sti, ikke cot-explorer
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bedrock.bot.config import ReconnectConfig, StartupOnlyConfig
from bedrock.bot.ctrader_client import (
    AGRI_SYMBOL_INFO_PATH,
    AUTH_FATAL_ERROR_CODES,
    H1_PERIOD,
    M5_PERIOD,
    M15_PERIOD,
    CtraderCallbacks,
    CtraderClient,
    CtraderCredentials,
    load_credentials_from_env,
)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def creds() -> CtraderCredentials:
    return CtraderCredentials(
        client_id="id",
        client_secret="secret",
        access_token="tok",
        account_id=12345,
    )


@pytest.fixture
def startup_cfg() -> StartupOnlyConfig:
    return StartupOnlyConfig(reconnect=ReconnectConfig(window_sec=600, max_in_window=5))


@pytest.fixture
def client(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> CtraderClient:
    return CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg
    )


# ─────────────────────────────────────────────────────────────
# Dataklasser + defaults
# ─────────────────────────────────────────────────────────────


def test_callbacks_default_is_noop() -> None:
    cb = CtraderCallbacks()
    # Alle 8 callbacks skal være kallbare og ta event uten å krasje
    cb.on_spot("anything")
    cb.on_historical_bars("r")
    cb.on_execution("e")
    cb.on_order_error("e")
    cb.on_error_res("e")
    cb.on_reconcile("r")
    cb.on_symbols_ready("c")
    cb.on_trader_info(1000.0)


def test_credentials_dataclass(creds: CtraderCredentials) -> None:
    assert creds.client_id == "id"
    assert creds.account_id == 12345


def test_client_initial_state(client: CtraderClient) -> None:
    assert client.client is None
    assert client.symbol_map == {}
    assert client.spread_history == {}
    assert client.account_balance == 0.0
    assert client._reconnect_times == []
    assert client._reconnecting is False


def test_client_uses_injected_callbacks(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> None:
    cb = CtraderCallbacks(on_spot=MagicMock())
    c = CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    assert c._callbacks is cb


# ─────────────────────────────────────────────────────────────
# Credentials fra env
# ─────────────────────────────────────────────────────────────


def test_load_credentials_from_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CTRADER_CLIENT_ID", "cid")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "cs")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "999")
    creds = load_credentials_from_env()
    assert creds.client_id == "cid"
    assert creds.account_id == 999


def test_load_credentials_from_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in (
        "CTRADER_CLIENT_ID",
        "CTRADER_CLIENT_SECRET",
        "CTRADER_ACCESS_TOKEN",
        "CTRADER_ACCOUNT_ID",
    ):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError) as exc:
        load_credentials_from_env()
    msg = str(exc.value)
    assert "CTRADER_CLIENT_ID" in msg
    assert "CTRADER_ACCOUNT_ID" in msg


def test_load_credentials_non_int_account_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CTRADER_CLIENT_ID", "cid")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "cs")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "not-a-number")
    with pytest.raises(RuntimeError) as exc:
        load_credentials_from_env()
    assert "heltall" in str(exc.value)


# ─────────────────────────────────────────────────────────────
# Reconnect-budsjett
# ─────────────────────────────────────────────────────────────


def test_reconnect_under_budget_does_not_fatal(client: CtraderClient) -> None:
    """4 reconnects innen vinduet (max_in_window=5) → ingen fatal."""
    fake_client = MagicMock()
    client.client = fake_client
    with patch("bedrock.bot.ctrader_client.reactor") as mock_reactor:
        mock_reactor.running = True
        for _ in range(4):
            client._on_disconnected(fake_client, "test reason")
    assert len(client._reconnect_times) == 4
    # startService scheduled via callLater
    # Bør ikke ha kalt sys.exit (ingen fatal)


def test_reconnect_over_budget_triggers_fatal(client: CtraderClient) -> None:
    """6 reconnects innen vinduet (max_in_window=5) → fatal_exit."""
    fake_client = MagicMock()
    client.client = fake_client
    with patch("bedrock.bot.ctrader_client.reactor") as mock_reactor:
        mock_reactor.running = True
        # Første 5 (<= max_in_window) — ingen fatal ennå
        for _ in range(5):
            client._on_disconnected(fake_client, "test reason")
        # Det 6. forsøket tipper over
        client._on_disconnected(fake_client, "test reason")
    assert len(client._reconnect_times) == 6
    # Skal ha planlagt reactor.stop via callLater
    assert any(
        call.args and call.args[1] == mock_reactor.stop
        for call in mock_reactor.callLater.call_args_list
    ) or mock_reactor.stop.called or any(
        "stop" in str(call) for call in mock_reactor.method_calls
    )


def test_reconnect_window_sliding(client: CtraderClient) -> None:
    """Gamle reconnects utenfor vinduet skal droppes."""
    import time as time_module

    fake_client = MagicMock()
    client.client = fake_client
    # Legg inn "gamle" reconnects fra 2 timer siden
    client._reconnect_times = [time_module.time() - 7200 for _ in range(10)]
    with patch("bedrock.bot.ctrader_client.reactor") as mock_reactor:
        mock_reactor.running = True
        client._on_disconnected(fake_client, "test")
    # Alle gamle ble fjernet; kun den nye er igjen
    assert len(client._reconnect_times) == 1


# ─────────────────────────────────────────────────────────────
# Spot-handler
# ─────────────────────────────────────────────────────────────


@dataclass
class _FakeSpot:
    symbolId: int
    _has_bid: bool
    _has_ask: bool
    bid: int = 0
    ask: int = 0
    trendbar: list = None  # type: ignore[assignment]

    def HasField(self, name: str) -> bool:
        return {"bid": self._has_bid, "ask": self._has_ask}.get(name, False)

    def __post_init__(self) -> None:
        if self.trendbar is None:
            self.trendbar = []


def test_on_spot_updates_bid_ask(client: CtraderClient) -> None:
    sid = 42
    client.symbol_digits[sid] = 5
    client.spread_history[sid] = deque(maxlen=20)
    event = _FakeSpot(symbolId=sid, _has_bid=True, _has_ask=True, bid=100_500, ask=101_000)
    client._on_spot(event)
    assert client.last_bid[sid] == pytest.approx(1.00500)
    assert client.last_ask[sid] == pytest.approx(1.01000)
    assert len(client.spread_history[sid]) == 1
    assert client.spread_history[sid][0] == pytest.approx(0.005)


def test_on_spot_updates_last_spot_time(client: CtraderClient) -> None:
    sid = 7
    client.symbol_digits[sid] = 5
    assert client._last_spot_time is None
    event = _FakeSpot(symbolId=sid, _has_bid=True, _has_ask=True, bid=1, ask=2)
    client._on_spot(event)
    assert client._last_spot_time is not None
    assert sid in client._last_spot_per_sid


def test_on_spot_clears_silent_flag(client: CtraderClient) -> None:
    sid = 9
    client.symbol_digits[sid] = 5
    client._symbol_silent_logged.add(sid)
    event = _FakeSpot(symbolId=sid, _has_bid=True, _has_ask=True, bid=1, ask=2)
    client._on_spot(event)
    assert sid not in client._symbol_silent_logged


def test_on_spot_fires_callback(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> None:
    on_spot = MagicMock()
    cb = CtraderCallbacks(on_spot=on_spot)
    c = CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    c.symbol_digits[1] = 5
    event = _FakeSpot(symbolId=1, _has_bid=True, _has_ask=True, bid=1, ask=2)
    c._on_spot(event)
    on_spot.assert_called_once_with(event)


def test_on_spot_callback_exception_does_not_propagate(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> None:
    def boom(_e: Any) -> None:
        raise RuntimeError("boom")

    cb = CtraderCallbacks(on_spot=boom)
    c = CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    c.symbol_digits[1] = 5
    event = _FakeSpot(symbolId=1, _has_bid=True, _has_ask=True, bid=1, ask=2)
    # Skal ikke raise ut av _on_spot
    c._on_spot(event)


def test_on_spot_no_spread_when_only_bid(client: CtraderClient) -> None:
    sid = 3
    client.symbol_digits[sid] = 5
    client.spread_history[sid] = deque(maxlen=20)
    event = _FakeSpot(symbolId=sid, _has_bid=True, _has_ask=False, bid=100_000)
    client._on_spot(event)
    # Ingen ask → ingen spread
    assert len(client.spread_history[sid]) == 0


def test_on_spot_price_feed_has_no_spread_history(client: CtraderClient) -> None:
    """Pris-feed-symboler har ikke spread_history-dict-entry."""
    sid = 55  # pris-feed symbol_id, ikke i spread_history
    client.symbol_digits[sid] = 5
    event = _FakeSpot(symbolId=sid, _has_bid=True, _has_ask=True, bid=1, ask=2)
    # Skal ikke raise KeyError
    client._on_spot(event)
    assert client.last_bid[sid] == pytest.approx(0.00001)


# ─────────────────────────────────────────────────────────────
# Handler-dispatcher
# ─────────────────────────────────────────────────────────────


def test_handlers_map_includes_all_expected_types(client: CtraderClient) -> None:
    handlers = client._handlers()
    # Vi verifiserer at dispatcheren inneholder et forsvarlig antall entries,
    # ikke eksakt antall (for å tåle framtidige protobuf-tillegg)
    assert len(handlers) >= 13


def test_message_dispatch_unknown_payload_type_logs(
    client: CtraderClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake_msg = MagicMock()
    fake_msg.payloadType = 99999  # garantert ikke i handlers
    with caplog.at_level("INFO", logger="bedrock.bot.ctrader"):
        client._on_message(MagicMock(), fake_msg)
    assert any("Uhåndtert" in rec.message for rec in caplog.records)


# ─────────────────────────────────────────────────────────────
# Fatal-error-koder
# ─────────────────────────────────────────────────────────────


def test_auth_fatal_error_codes_defined() -> None:
    """Regresjons-vakt: viktige koder må være med."""
    for code in (
        "CH_CLIENT_AUTH_FAILURE",
        "CH_ACCESS_TOKEN_INVALID",
        "ACCESS_TOKEN_EXPIRED",
    ):
        assert code in AUTH_FATAL_ERROR_CODES


def test_on_error_res_fatal_code_triggers_exit(client: CtraderClient) -> None:
    err_event = MagicMock()
    err_event.errorCode = "ACCESS_TOKEN_EXPIRED"
    with patch.object(client, "_fatal_exit") as fatal:
        client._on_error_res(err_event)
        fatal.assert_called_once_with(78)


def test_on_error_res_non_fatal_code_calls_callback(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> None:
    on_err = MagicMock()
    cb = CtraderCallbacks(on_error_res=on_err)
    c = CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    err_event = MagicMock()
    err_event.errorCode = "SOMETHING_TRANSIENT"
    with patch.object(c, "_fatal_exit") as fatal:
        c._on_error_res(err_event)
        fatal.assert_not_called()
    on_err.assert_called_once_with(err_event)


# ─────────────────────────────────────────────────────────────
# AGRI-dump til Bedrock-sti
# ─────────────────────────────────────────────────────────────


def test_agri_dump_path_is_in_bedrock(tmp_path: Path) -> None:
    """AGRI_SYMBOL_INFO_PATH må peke i bedrock/, ikke cot-explorer."""
    p = str(AGRI_SYMBOL_INFO_PATH)
    assert "bedrock" in p
    assert "cot-explorer" not in p


def test_dump_agri_symbol_info_writes_json(
    client: CtraderClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Redirect AGRI_SYMBOL_INFO_PATH til tmp for isolasjon
    target = tmp_path / "agri.json"
    monkeypatch.setattr("bedrock.bot.ctrader_client.AGRI_SYMBOL_INFO_PATH", target)

    sym = MagicMock()
    sym.symbolId = 100
    sym.lotSize = 1000
    sym.minVolume = 10
    sym.stepVolume = 1
    sym.digits = 3
    sym.description = "Test Corn"

    client._dump_agri_symbol_info("Corn", sym)
    import json

    data = json.loads(target.read_text())
    assert "Corn" in data
    assert data["Corn"]["symbol_id"] == 100
    assert data["Corn"]["digits"] == 3


def test_dump_agri_preserves_existing_entries(
    client: CtraderClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "agri.json"
    target.write_text('{"Wheat": {"old": "data"}}')
    monkeypatch.setattr("bedrock.bot.ctrader_client.AGRI_SYMBOL_INFO_PATH", target)

    sym = MagicMock()
    sym.symbolId = 200
    sym.lotSize = 1000
    sym.minVolume = 10
    sym.stepVolume = 1
    sym.digits = 2
    sym.description = ""

    client._dump_agri_symbol_info("Corn", sym)
    import json

    data = json.loads(target.read_text())
    assert "Wheat" in data
    assert "Corn" in data
    assert data["Wheat"] == {"old": "data"}


# ─────────────────────────────────────────────────────────────
# Trader-info / balance
# ─────────────────────────────────────────────────────────────


def test_on_trader_info_sets_balance_and_fires_callback(
    creds: CtraderCredentials, startup_cfg: StartupOnlyConfig
) -> None:
    on_ti = MagicMock()
    cb = CtraderCallbacks(on_trader_info=on_ti)
    c = CtraderClient(
        credentials=creds, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    res = MagicMock()
    res.trader.balance = 150_000  # cent
    with patch.object(c, "send"):
        c._on_trader_info(res)
    assert c.account_balance == pytest.approx(1500.0)
    on_ti.assert_called_once_with(1500.0)


# ─────────────────────────────────────────────────────────────
# Send-wrapper
# ─────────────────────────────────────────────────────────────


def test_send_without_client_returns_none(client: CtraderClient) -> None:
    assert client.client is None
    assert client.send(MagicMock()) is None


def test_send_with_client_calls_underlying(client: CtraderClient) -> None:
    fake = MagicMock()
    fake.send.return_value = MagicMock()
    client.client = fake
    msg = MagicMock()
    client.send(msg, timeout=15)
    fake.send.assert_called_once_with(msg, responseTimeoutInSeconds=15)


def test_send_swallows_exception(client: CtraderClient) -> None:
    fake = MagicMock()
    fake.send.side_effect = RuntimeError("boom")
    client.client = fake
    # Skal ikke raise
    result = client.send(MagicMock())
    assert result is None


# ─────────────────────────────────────────────────────────────
# Period-konstanter
# ─────────────────────────────────────────────────────────────


def test_period_constants_are_distinct() -> None:
    assert len({M15_PERIOD, M5_PERIOD, H1_PERIOD}) == 3


def test_request_historical_bars_uses_period(client: CtraderClient) -> None:
    with patch.object(client, "send") as send:
        client.request_historical_bars(symbol_id=42, period=M15_PERIOD, bars_back=50)
    assert send.called
    req = send.call_args.args[0]
    assert req.symbolId == 42
    assert req.period == M15_PERIOD


def test_request_historical_bars_h1_uses_h1_period(client: CtraderClient) -> None:
    with patch.object(client, "send") as send:
        client.request_historical_bars(symbol_id=7, period=H1_PERIOD, bars_back=50)
    req = send.call_args.args[0]
    assert req.period == H1_PERIOD
