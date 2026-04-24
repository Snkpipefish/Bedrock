"""Tester for bot.__main__ — wire-up, signal-handlere, polling-loop.

Dekker:
- build_bot: instansierer alle moduler og wirer callbacks uten feil
- _apply_kill_ids: setter kill_switch på matching IN_TRADE-states
- SIGHUP-handler: kaller reload_bot_config + apply_reloadable_inplace
- Shutdown-handler: kaller reactor.stop via callFromThread
- _schedule_polling_loop: første callLater registreres umiddelbart
- main(): live-mode uten 'JA' → avbryter
- apply_reloadable_inplace: muterer alle felter fra ny config
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bedrock.bot.__main__ import (
    _apply_kill_ids,
    _make_shutdown_handler,
    _make_sighup_handler,
    _schedule_polling_loop,
    build_bot,
    main,
    register_signal_handlers,
)
from bedrock.bot.config import (
    BotConfig,
    ReloadableConfig,
    apply_reloadable_inplace,
)
from bedrock.bot.state import TradePhase, TradeState


# ─────────────────────────────────────────────────────────────
# _apply_kill_ids
# ─────────────────────────────────────────────────────────────


def test_apply_kill_ids_sets_flag_on_in_trade() -> None:
    s1 = TradeState(signal_id="a", phase=TradePhase.IN_TRADE)
    s2 = TradeState(signal_id="b", phase=TradePhase.IN_TRADE)
    s3 = TradeState(signal_id="c", phase=TradePhase.AWAITING_CONFIRMATION)
    _apply_kill_ids([s1, s2, s3], ["a", "c"])
    assert s1.kill_switch is True
    # AWAITING-state ignoreres (kun IN_TRADE får kill)
    assert s3.kill_switch is False
    assert s2.kill_switch is False


def test_apply_kill_ids_no_op_when_empty() -> None:
    s = TradeState(signal_id="a", phase=TradePhase.IN_TRADE)
    _apply_kill_ids([s], [])
    assert s.kill_switch is False


# ─────────────────────────────────────────────────────────────
# apply_reloadable_inplace
# ─────────────────────────────────────────────────────────────


def test_apply_reloadable_inplace_mutates_current() -> None:
    """SIGHUP-flyten er avhengig av at reloadable-config kan muteres
    in-place slik at alle moduler med ref til samme instans ser nye
    verdier."""
    current = ReloadableConfig()
    new = ReloadableConfig()
    new.confirmation.min_score_default = 99
    new.risk_pct.full = 1.5

    # Før apply: nåværende har defaults
    assert current.confirmation.min_score_default == 2
    assert current.risk_pct.full == 1.0

    apply_reloadable_inplace(current, new)

    # Samme instans, men oppdatert til new sine verdier
    assert current.confirmation.min_score_default == 99
    assert current.risk_pct.full == 1.5


# ─────────────────────────────────────────────────────────────
# build_bot: wire-up uten nettverk
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def env_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CTRADER_CLIENT_ID", "id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "12345")
    monkeypatch.setenv("SCALP_API_KEY", "test-api-key")


def test_build_bot_wires_all_modules(
    env_with_credentials: None, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_bot skal instansiere alle moduler og koble callbacks."""
    # Peker BEDROCK_BOT_CONFIG mot en ikke-eksisterende fil → defaults
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "missing.yaml"))

    client, comms, entry, exit_engine, bot_config, active_states = build_bot(
        demo=True
    )

    assert client is not None
    assert comms is not None
    assert entry is not None
    assert exit_engine is not None
    assert bot_config.startup_only.signal_url.startswith("http")
    assert active_states == []

    # Callback-wiring: client-callbacks peker til entry/exit-metoder
    # (sammenlign underliggende metode-referanse — MagicMock-identitet
    # funker ikke på bound methods direkte, men "im_func"/"__func__" gjør)
    assert client._callbacks.on_spot == entry.on_spot
    assert client._callbacks.on_historical_bars == entry.on_historical_bars
    assert client._callbacks.on_symbols_ready == entry.on_symbols_ready
    assert client._callbacks.on_execution == exit_engine.on_execution
    assert client._callbacks.on_order_error == exit_engine.on_order_error
    assert client._callbacks.on_reconcile == exit_engine.on_reconcile

    # Entry manage-callback peker til exit.manage_open_positions
    assert entry._manage_open_positions == exit_engine.manage_open_positions

    # comms on_signals peker til entry.on_signals
    assert comms._on_signals == entry.on_signals


def test_build_bot_warns_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("CTRADER_CLIENT_ID", "id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "12345")
    monkeypatch.delenv("SCALP_API_KEY", raising=False)
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "missing.yaml"))

    with caplog.at_level("WARNING"):
        build_bot(demo=True)
    assert any("SCALP_API_KEY" in rec.message for rec in caplog.records)


def test_build_bot_raises_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Fjern alle credentials
    for var in (
        "CTRADER_CLIENT_ID",
        "CTRADER_CLIENT_SECRET",
        "CTRADER_ACCESS_TOKEN",
        "CTRADER_ACCOUNT_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "missing.yaml"))

    with pytest.raises(RuntimeError, match="Mangler miljøvariabler"):
        build_bot(demo=True)


# ─────────────────────────────────────────────────────────────
# SIGHUP-handler
# ─────────────────────────────────────────────────────────────


def test_sighup_handler_applies_new_reloadable(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "bot.yaml"
    yaml_path.write_text("""
reloadable:
  confirmation:
    min_score_default: 3
    max_candles_default: 8
    body_threshold_atr_pct: 0.4
    ema_gradient_buy_min: -0.05
    ema_gradient_sell_max: 0.05
""".strip())
    bot_config = BotConfig()
    handler = _make_sighup_handler(bot_config, str(yaml_path))

    assert bot_config.reloadable.confirmation.min_score_default == 2  # default
    handler(1, None)
    assert bot_config.reloadable.confirmation.min_score_default == 3
    assert bot_config.reloadable.confirmation.max_candles_default == 8


def test_sighup_handler_logs_startup_only_diff(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """Endring i startup_only skal logges som warning, ikke aktiveres."""
    yaml_path = tmp_path / "bot.yaml"
    yaml_path.write_text("""
startup_only:
  signal_url: http://other:9999
""".strip())
    bot_config = BotConfig()
    old_url = bot_config.startup_only.signal_url
    handler = _make_sighup_handler(bot_config, str(yaml_path))

    with caplog.at_level("WARNING"):
        handler(1, None)
    # signal_url IKKE endret i aktiv config
    assert bot_config.startup_only.signal_url == old_url
    # Men advarsel logget
    assert any("signal_url" in r.message for r in caplog.records)


def test_sighup_handler_swallows_exceptions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """Ugyldig YAML → handler logger exception, bot fortsetter."""
    yaml_path = tmp_path / "bot.yaml"
    yaml_path.write_text("reloadable: not-a-dict")
    bot_config = BotConfig()
    old_val = bot_config.reloadable.confirmation.min_score_default
    handler = _make_sighup_handler(bot_config, str(yaml_path))
    with caplog.at_level("ERROR"):
        handler(1, None)
    # Config uendret
    assert bot_config.reloadable.confirmation.min_score_default == old_val


# ─────────────────────────────────────────────────────────────
# Shutdown-handler
# ─────────────────────────────────────────────────────────────


def test_shutdown_handler_calls_reactor_stop() -> None:
    handler = _make_shutdown_handler("SIGTERM")
    mock_reactor = MagicMock()
    mock_reactor.running = True
    with patch.dict(
        "sys.modules", {"twisted.internet": MagicMock(reactor=mock_reactor)}
    ):
        handler(15, None)
    mock_reactor.callFromThread.assert_called_once_with(mock_reactor.stop)


def test_shutdown_handler_when_reactor_not_running() -> None:
    """Reactor ikke i gang → ingen feil, ingen callFromThread."""
    handler = _make_shutdown_handler("SIGINT")
    mock_reactor = MagicMock()
    mock_reactor.running = False
    with patch.dict(
        "sys.modules", {"twisted.internet": MagicMock(reactor=mock_reactor)}
    ):
        handler(2, None)
    mock_reactor.callFromThread.assert_not_called()


# ─────────────────────────────────────────────────────────────
# Polling-loop
# ─────────────────────────────────────────────────────────────


def test_schedule_polling_loop_registers_initial_call() -> None:
    comms = MagicMock()
    config = ReloadableConfig()
    reactor_mock = MagicMock()
    _schedule_polling_loop(comms, config, reactor_mock)
    # Første callLater(0, _tick) for å starte loopen
    reactor_mock.callLater.assert_called_once()
    delay, fn = reactor_mock.callLater.call_args.args[:2]
    assert delay == 0


def test_schedule_polling_loop_tick_uses_adaptive_interval() -> None:
    """Etter fetch_once skal neste callLater bruke adaptive_poll_interval."""
    comms = MagicMock()
    # Fersk SCALP-watchlist → scalp_active_seconds (default 20)
    comms.latest_signals = {
        "signals": [{"horizon": "SCALP", "status": "watchlist"}]
    }
    config = ReloadableConfig()
    reactor_mock = MagicMock()
    _schedule_polling_loop(comms, config, reactor_mock)
    # Kjør _tick manuelt (andre arg til første callLater)
    _tick = reactor_mock.callLater.call_args.args[1]
    _tick()
    comms.fetch_once.assert_called_once()
    # Andre callLater fra _tick: scalp_active_seconds
    second_call = reactor_mock.callLater.call_args_list[1]
    assert second_call.args[0] == config.polling.scalp_active_seconds


def test_schedule_polling_loop_tick_uses_default_when_no_scalp() -> None:
    comms = MagicMock()
    comms.latest_signals = None
    config = ReloadableConfig()
    reactor_mock = MagicMock()
    _schedule_polling_loop(comms, config, reactor_mock)
    _tick = reactor_mock.callLater.call_args.args[1]
    _tick()
    second_call = reactor_mock.callLater.call_args_list[1]
    assert second_call.args[0] == config.polling.default_seconds


def test_schedule_polling_loop_swallows_fetch_exception() -> None:
    """Exception i fetch_once skal ikke stoppe polling-loopen."""
    comms = MagicMock()
    comms.fetch_once.side_effect = RuntimeError("network down")
    comms.latest_signals = None
    config = ReloadableConfig()
    reactor_mock = MagicMock()
    _schedule_polling_loop(comms, config, reactor_mock)
    _tick = reactor_mock.callLater.call_args.args[1]
    _tick()  # skal IKKE raise
    # Neste tick schedulert uansett
    assert reactor_mock.callLater.call_count == 2


# ─────────────────────────────────────────────────────────────
# register_signal_handlers
# ─────────────────────────────────────────────────────────────


def test_register_signal_handlers_binds_all_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGHUP, SIGTERM, SIGINT skal alle bli satt."""
    import signal as signal_mod

    calls: dict[int, Any] = {}

    def _capture(signum: int, handler: Any) -> None:
        calls[signum] = handler

    monkeypatch.setattr(signal_mod, "signal", _capture)
    register_signal_handlers(BotConfig(), None)
    assert signal_mod.SIGHUP in calls
    assert signal_mod.SIGTERM in calls
    assert signal_mod.SIGINT in calls


# ─────────────────────────────────────────────────────────────
# main(): live-mode uten JA
# ─────────────────────────────────────────────────────────────


def test_main_live_without_ja_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    env_with_credentials: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Live-mode uten 'JA'-bekreftelse avbryter returnerer 0."""
    monkeypatch.setattr("builtins.input", lambda _: "NEI")
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "missing.yaml"))
    result = main(["--live"])
    assert result == 0
    out = capsys.readouterr().out
    assert "Avbrutt" in out


def test_main_returns_1_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for var in (
        "CTRADER_CLIENT_ID",
        "CTRADER_CLIENT_SECRET",
        "CTRADER_ACCESS_TOKEN",
        "CTRADER_ACCOUNT_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BEDROCK_BOT_CONFIG", str(tmp_path / "missing.yaml"))
    with caplog.at_level("ERROR"):
        result = main(["--demo"])
    assert result == 1
    assert any(
        "Mangler miljøvariabler" in r.message for r in caplog.records
    )
