"""Bot entry-point — instansierer alle moduler og starter reactor.

Portert fra `~/scalp_edge/trading_bot.py:2962` session 46 per
migrasjons-plan (`docs/migration/bot_refactor.md § 3.6 + 8 punkt 6`).
Siste modul i Fase 8 bot-refaktor.

Kjøring:
    python -m bedrock.bot --demo      # mot cTrader demo-konto
    python -m bedrock.bot --live      # mot live-konto (krever 'JA'-bekreftelse)

Miljøvariabler (påkrevd):
    CTRADER_CLIENT_ID
    CTRADER_CLIENT_SECRET
    CTRADER_ACCESS_TOKEN
    CTRADER_ACCOUNT_ID

Miljøvariabler (valgfrie):
    BEDROCK_BOT_CONFIG — sti til bot.yaml (default: ./config/bot.yaml)
    SCALP_API_KEY (eller env-var-navnet fra startup_only.signal_api_key_env)

Signaler:
    SIGHUP  — reload reloadable config (startup_only-diffs logges, ikke aktivert)
    SIGTERM — clean shutdown (stopper reactor, exit 0)
    SIGINT  — samme som SIGTERM (Ctrl+C)

Wire-up-rekkefølge:
  1. argparse --demo/--live, live-bekreftelse
  2. Load credentials fra env (feiler hardt ved mangler)
  3. Load BotConfig
  4. Instansier SafetyMonitor → laster persistert daily_loss
  5. Instansier CtraderClient med callbacks = CtraderCallbacks()
  6. Instansier SignalComms
  7. Instansier EntryEngine
  8. Instansier ExitEngine med entry-ref
  9. Wire: entry.set_manage_open_positions(exit.manage_open_positions)
 10. Wire client.callbacks (on_spot/on_historical_bars/on_symbols_ready
     → entry; on_execution/on_order_error/on_reconcile → exit)
 11. Wire comms-callbacks: on_signals → entry.on_signals,
     on_kill_ids → helper som setter state.kill_switch
 12. Registrer signal-handlers (SIGHUP/SIGTERM/SIGINT)
 13. Start comms polling-loop via reactor.callLater
 14. client.start() — blokkerer i reactor.run()
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from typing import Any

from bedrock.bot.comms import (
    SignalComms,
    adaptive_poll_interval,
)
from bedrock.bot.config import (
    BotConfig,
    apply_reloadable_inplace,
    load_bot_config,
    reload_bot_config,
    resolve_bot_config_path,
)
from bedrock.bot.ctrader_client import (
    CtraderCallbacks,
    CtraderClient,
    load_credentials_from_env,
)
from bedrock.bot.entry import EntryEngine
from bedrock.bot.exit import ExitEngine
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.state import TradePhase, TradeState

log = logging.getLogger("bedrock.bot.main")


def _apply_kill_ids(active_states: list[TradeState], kill_ids: list[str]) -> None:
    """Sett `kill_switch=True` på alle IN_TRADE-states med matching signal_id.

    ExitEngine.manage_open_positions P2 plukker opp flagget og lukker
    posisjonen ved neste candle-close. Bevisst å ikke lukke her —
    reactor-tråden skal ikke gjøre ordre-sending fra HTTP-callback.
    """
    kill_set = set(kill_ids)
    for state in active_states:
        if state.phase == TradePhase.IN_TRADE and state.signal_id in kill_set:
            if not state.kill_switch:
                log.warning(
                    "[KILL] Signal %s markert for kill via /kill-endpoint",
                    state.signal_id,
                )
                state.kill_switch = True


def build_bot(
    *, demo: bool, config_path: str | None = None
) -> tuple[CtraderClient, SignalComms, EntryEngine, ExitEngine, BotConfig, list[TradeState]]:
    """Konstruer og wire opp alle bot-moduler.

    Returnerer alle instanser slik at tester kan inspisere dem uten å
    starte reactor. Wire-up er 1:1 med `main()` unntatt signal-handlere
    og reactor-start.
    """
    creds = load_credentials_from_env()
    bot_config = load_bot_config(config_path)

    active_states: list[TradeState] = []
    safety = SafetyMonitor()

    callbacks = CtraderCallbacks()
    client = CtraderClient(
        credentials=creds,
        demo=demo,
        startup_config=bot_config.startup_only,
        callbacks=callbacks,
    )

    api_key_env = bot_config.startup_only.signal_api_key_env
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        log.warning(
            "[COMMS] Env-var %s ikke satt — signal-server-kall går uten API-nøkkel",
            api_key_env,
        )

    comms = SignalComms(
        startup_cfg=bot_config.startup_only,
        api_key=api_key,
        safety=safety,
    )

    entry = EntryEngine(
        client=client,
        safety=safety,
        config=bot_config.reloadable,
        active_states=active_states,
    )

    exit_engine = ExitEngine(
        client=client,
        safety=safety,
        config=bot_config.reloadable,
        active_states=active_states,
        entry=entry,
    )

    # Wire: entry manage-callback → exit.manage_open_positions
    entry.set_manage_open_positions(exit_engine.manage_open_positions)

    # Wire: CtraderClient-callbacks
    callbacks.on_spot = entry.on_spot
    callbacks.on_historical_bars = entry.on_historical_bars
    callbacks.on_symbols_ready = entry.on_symbols_ready
    callbacks.on_execution = exit_engine.on_execution
    callbacks.on_order_error = exit_engine.on_order_error
    callbacks.on_reconcile = exit_engine.on_reconcile

    # Wire: SignalComms-callbacks
    comms._on_signals = entry.on_signals  # type: ignore[attr-defined]
    comms._on_kill_ids = (  # type: ignore[attr-defined]
        lambda kill_ids: _apply_kill_ids(active_states, kill_ids)
    )

    return client, comms, entry, exit_engine, bot_config, active_states


def _make_sighup_handler(bot_config: BotConfig, config_path: str | None) -> Any:
    """Returner SIGHUP-handler som oppdaterer reloadable-delen in-place.

    Startup_only-diffs logges som warning — krever prosess-restart.
    """

    def _handle_sighup(signum: int, frame: Any) -> None:
        log.info("[SIGHUP] Reload bot-config…")
        try:
            new_config, diffs = reload_bot_config(config_path, bot_config)
            apply_reloadable_inplace(bot_config.reloadable, new_config.reloadable)
            if diffs:
                for diff_line in diffs:
                    log.warning(
                        "[SIGHUP] startup_only-felt endret i YAML men ikke "
                        "aktivert (krever restart): %s",
                        diff_line,
                    )
            else:
                log.info("[SIGHUP] Reload fullført — %d reloadable-felter aktive", 1)
        except Exception as exc:
            log.exception("[SIGHUP] Reload feilet: %s — beholder gammel config", exc)

    return _handle_sighup


def _make_shutdown_handler(signal_name: str) -> Any:
    """Returner SIGTERM/SIGINT-handler som stopper reactor og exit-er."""

    def _handle_shutdown(signum: int, frame: Any) -> None:
        log.info("[%s] Mottatt signal — stopper reactor…", signal_name)
        try:
            from twisted.internet import reactor

            if reactor.running:  # type: ignore[attr-defined]
                reactor.callFromThread(reactor.stop)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("[%s] reactor.stop feilet: %s", signal_name, exc)
            sys.exit(0)

    return _handle_shutdown


def _schedule_polling_loop(comms: SignalComms, config: Any, reactor_module: Any) -> None:
    """Planlegg gjentatt fetch_once via reactor.callLater med adaptiv intervall.

    Adaptiv: default_seconds normalt, scalp_active_seconds hvis SCALP-
    watchlist-signaler er aktive (flere signal-evalueringer per minutt).
    """

    def _tick() -> None:
        try:
            comms.fetch_once()
        except Exception:
            log.exception("[POLL] fetch_once feilet — fortsetter polling")
        delay = adaptive_poll_interval(comms.latest_signals, config.polling)
        reactor_module.callLater(delay, _tick)

    # Første fetch umiddelbart etter reactor-start
    reactor_module.callLater(0, _tick)


def register_signal_handlers(bot_config: BotConfig, config_path: str | None) -> None:
    """Registrer SIGHUP/SIGTERM/SIGINT-handlere. Må kalles før reactor.run()."""
    signal.signal(signal.SIGHUP, _make_sighup_handler(bot_config, config_path))
    signal.signal(signal.SIGTERM, _make_shutdown_handler("SIGTERM"))
    signal.signal(signal.SIGINT, _make_shutdown_handler("SIGINT"))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Bedrock trading bot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Kjør mot demo-konto")
    group.add_argument(
        "--live", action="store_true", help="Kjør mot live-konto (krever 'JA'-bekreftelse)"
    )
    parser.add_argument(
        "--config",
        help="Sti til bot.yaml (overrider BEDROCK_BOT_CONFIG)",
        default=None,
    )
    args = parser.parse_args(argv)

    if args.live:
        confirm = input("⚠️  LIVE-MODUS. Skriv 'JA' for å fortsette: ")
        if confirm.strip() != "JA":
            print("Avbrutt.")
            return 0

    try:
        client, comms, entry, exit_engine, bot_config, active_states = build_bot(
            demo=args.demo, config_path=args.config
        )
    except RuntimeError as exc:
        log.error("[OPPSTART] %s", exc)
        log.error("Se docs/bot_running.md for env-var-oppsett.")
        return 1

    config_path_str = (
        str(resolve_bot_config_path(args.config)) if args.config is None else args.config
    )
    register_signal_handlers(bot_config, config_path_str)

    # Polling-loop må schedules via reactor (ikke umiddelbart — reactor
    # må kjøre først)
    from twisted.internet import reactor

    _schedule_polling_loop(comms, bot_config.reloadable, reactor)

    log.info("═══════════════════════════════════════")
    log.info("  Bedrock trading bot — %s-modus", "DEMO" if args.demo else "LIVE")
    log.info("  Config: %s", config_path_str)
    log.info(
        "  %d instrumenter, %d pris-feeds", len(client.symbol_map), len(client.price_feed_sids)
    )
    log.info("═══════════════════════════════════════")

    # Blokkerende — kjører til reactor.stop() via SIGTERM/SIGINT/fatal
    client.start()

    log.info("[SHUTDOWN] Reactor stoppet — exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
