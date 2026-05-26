"""Entry-lag: candle-handling, indikatorer, filters, confirmation, execute.

Portert fra `~/scalp_edge/trading_bot.py` session 43-44 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.2 + 8 punkt 4-5`).

**KRITISK BUG-FIX (SESSION 43):** `_recalibrate_agri_levels` er SLETTET
og kall-stedet i `_on_candle_closed` er fjernet. Agri-signaler passerer
nå uendret gjennom bot-pipelinen — setup-generator-ens reelt-nivå-baserte
SL/T1/T2/entry_zone respekteres. Se `docs/migration/bot_refactor.md § 4`
for full forklaring av bugen.

Ansvaret:
- Eie candle-buffere (15m, 5m, 1h) og indikator-state (EMA9/ATR14)
- Populere buffere fra historical-bars ved oppstart
- Route spot-events → candle-handler
- Ved lukket 15m-candle: evaluere watchlist-signaler → filters →
  confirmation → execute (gates + sizing + ordre-send)
- Evaluere `active_states`-liste (exit-logikken fyres via callback)

Scope NOT i denne session:
- `_manage_open_positions` (P1-P5 exit) — session 45
- Execution-event-handlere (`_on_execution`, `_on_reconcile`,
  `_on_order_error`) — session 45 wirer disse til ExitEngine

Wire-up i `bot/__main__.py` (session 46):
    entry = EntryEngine(client=..., safety=..., config=..., ...)
    exit_engine = ExitEngine(...)  # session 45
    client.callbacks.on_spot = entry.on_spot
    client.callbacks.on_historical_bars = entry.on_historical_bars
    client.callbacks.on_symbols_ready = entry.on_symbols_ready
    client.callbacks.on_execution = exit_engine.on_execution
    client.callbacks.on_reconcile = exit_engine.on_reconcile
    client.callbacks.on_order_error = exit_engine.on_order_error
    comms.on_signals = entry.on_signals
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from bedrock.bot.config import ReloadableConfig
from bedrock.bot.ctrader_client import H1_PERIOD, M5_PERIOD, M15_PERIOD, CtraderClient
from bedrock.bot.instruments import (
    AGRI_INSTRUMENTS,
    AGRI_SUBGROUPS,
    FX_USD_DIRECTION,
    INSTRUMENT_GROUP,
    looks_like_fx_pair,
    net_usd_direction,
)
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.sizing import (
    compute_desired_lots,
    get_risk_pct,
    lots_to_volume_units,
    volume_to_lots,
)
from bedrock.bot.state import Candle, CandleBuffer, TradePhase, TradeState

CET = ZoneInfo("Europe/Oslo")

log = logging.getLogger("bedrock.bot.entry")


DEFAULT_CONFIRMATION_STATS_PATH = (
    Path.home() / "bedrock" / "data" / "bot" / "confirmation_stats.json"
)

DEFAULT_TRADE_LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "signal_log.json"

# ─────────────────────────────────────────────────────────────
# Permanent-disabled-guard (session 2026-05-26)
# ─────────────────────────────────────────────────────────────
# Bot-side last-line-of-defense. Selv om signal-server/whitelist/YAML-
# config skulle slippe disse instrumentene gjennom, blokkeres de her
# før entry-evaluering. For å reaktivere må navn fjernes både her OG
# fra PERMANENTLY_DISABLED i src/bedrock/cli/signals_all.py (synlig
# PR-endring i begge steder).
#
# Bot-navn (uppercase, etter INSTRUMENT_MAP-translasjon).
_PERMANENTLY_DISABLED_BOT_INSTRUMENTS: frozenset[str] = frozenset(
    {
        "PLATINUM",  # negativ swap begge veier + tap-historikk
        "BTC",  # 35% av margin, lav PnL-bidrag
        "ETH",  # 1.5% spread + lav PnL-bidrag
    }
)


def _noop(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
    pass


def _initial_confirmation_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "by_score": {0: 0, 1: 0, 2: 0, 3: 0},
        "passed": 0,
        "failed": 0,
        "strict_required": 0,
    }


# Type-alias for callbacks som bor utenfor entry-modulen
ExecuteTradeCallback = Callable[[dict[str, Any], TradeState, Candle], None]
ManagePositionsCallback = Callable[[int, Candle], None]


class EntryEngine:
    """Signal-evaluering og confirmation-scoring for trading-bot.

    Én instans per bot-prosess. Ikke thread-safe for samtidige writes
    (Twisted reactor-tråden eier state-mutasjoner).
    """

    def __init__(
        self,
        *,
        client: CtraderClient,
        safety: SafetyMonitor,
        config: ReloadableConfig,
        active_states: list[TradeState],
        execute_trade: ExecuteTradeCallback | None = None,
        manage_open_positions: ManagePositionsCallback = _noop,
        stats_path: Path | None = None,
        trade_log_path: Path | None = None,
    ) -> None:
        self._client = client
        self._safety = safety
        self._config = config
        self._active_states = active_states
        # Default: bruk intern _execute_trade_impl. Callback-slot beholdes
        # slik at tester kan stubbe ordre-flyten uten å patch-e metoden.
        self._execute_trade: ExecuteTradeCallback = (
            execute_trade if execute_trade is not None else self._execute_trade_impl
        )
        self._manage_open_positions = manage_open_positions
        self._stats_path = stats_path or DEFAULT_CONFIRMATION_STATS_PATH
        self._trade_log_path = trade_log_path or DEFAULT_TRADE_LOG_PATH

        # Candle-buffere (ikke ctrader_client.symbol-state — de bor der)
        self.candle_buffers: dict[int, CandleBuffer] = {}
        self.m5_candle_buffers: dict[int, CandleBuffer] = {}
        self.h1_candle_buffers: dict[int, CandleBuffer] = {}

        # Indikatorer (rullerende lister hvor -1 = siste lukkede bar)
        self.ema9: dict[int, list[float]] = {}
        self.atr14: dict[int, list[float]] = {}
        self.atr14_5m: dict[int, float] = {}
        self.ema9_h1: dict[int, list[float]] = {}
        self.atr14_h1: dict[int, list[float]] = {}

        # Siste signal-data (satt av on_signals-callback fra comms)
        self.signal_data: dict[str, Any] | None = None

        # Stats for empirisk min_score-kalibrering
        self._confirmation_stats: dict[str, Any] = _initial_confirmation_stats()

        # Spam-vern-set (nullstilles ved restart — bevisst)
        self._usd_dir_missing_logged: set[str] = set()
        self._spread_cold_logged: set[int] = set()
        self._ttl_logged: set[str] = set()
        self._last_expiry_log: datetime | None = None
        self._daily_loss_logged: bool = False
        self._permanently_disabled_logged: set[str] = set()

        # Loss-cooldown: signal_id → tap-tidspunkt (UTC). Blokkerer
        # re-entry på samme signal_id fra orchestrator inntil
        # `config.cooldown.loss_ttl_hours` har passert. Setup-id
        # persisteres på tvers av dager via hysterese — uten cooldown
        # ender vi i loss → re-entry → loss-loop i sideways-marked.
        # Uten TTL ender vi derimot i evig blacklist når orchestrator
        # gjenfinner samme nivå (regresjons-bug commit 6acb609, 2026-05-05;
        # låste FX/indices i 16 dager før detection 2026-05-26).
        # Lastes fra signal_log ved oppstart, oppdateres av ExitEngine
        # via `record_lost_signal()` ved hver loss-close.
        self._lost_signal_ids: dict[str, datetime] = {}
        self._cooldown_logged: set[str] = set()
        self._load_lost_signal_ids_from_log()

        self._lock = Lock()

    # ─────────────────────────────────────────────────────────
    # Callback-hooks fra CtraderClient og SignalComms
    # ─────────────────────────────────────────────────────────

    def on_symbols_ready(self, _client: CtraderClient) -> None:
        """Kalles av CtraderClient etter symbols-list er prosessert.
        Initialiserer candle-buffere og indikator-arrays for hvert sid."""
        for sid in self._client.symbol_map.values():
            self.candle_buffers[sid] = CandleBuffer()
            self.m5_candle_buffers[sid] = CandleBuffer()
            self.h1_candle_buffers[sid] = CandleBuffer()
            self.ema9[sid] = []
            self.atr14[sid] = []
            self.ema9_h1[sid] = []
            self.atr14_h1[sid] = []

    def on_signals(self, data: dict[str, Any]) -> None:
        """Kalles av SignalComms når /signals har gitt fersk respons."""
        self.signal_data = data
        # Cancel + rydd LIMIT-states som ikke lenger finnes i ferske
        # signaler. Forhindrer at gårsdagens MAKRO/SWING-LIMIT-er blir
        # liggende på cTrader-server etter at underliggende setup er
        # forsvunnet eller flyttet til nytt setup_id.
        self._sweep_stale_limit_orders(data.get("signals", []))
        # Reset daily-loss-log-flag når ny dag begynner (via safety-hook,
        # men også her som belte-og-seler)
        # (selve reset-handling er i SafetyMonitor.reset_daily_loss_if_new_day)

    def _sweep_stale_limit_orders(self, fresh_signals: list[dict[str, Any]]) -> None:
        """Cancel og fjern AWAITING_CONFIRMATION-states hvor signal_id
        ikke lenger finnes i ferske signaler.

        Et signal "forsvinner" når orchestrator's setup_id endres (level
        flyttet > hysterese-toleranse, eller score falt under publish-
        floor). Uten cleanup blir gamle LIMIT-ordrer liggende på cTrader-
        server inntil expiry (3t SWING / 24t MAKRO) — og dedup-blokken
        i `_process_watchlist_signal` ville hindre nytt signal på samme
        (instrument, direction, horizon) fra å opprette ny state.

        Krever at state.order_id > 0 (= LIMIT akseptert av server, real
        orderId mottatt via ORDER_ACCEPTED-event). Placeholder -1
        ignoreres — det er en LIMIT som er sendt men ikke akseptert
        ennå; den vil enten fås real orderId eller en
        ORDER_REJECTED-event som rydder staten.
        """
        if not fresh_signals:
            return
        fresh_ids = {s.get("id") for s in fresh_signals if isinstance(s, dict)}
        with self._lock:
            for state in list(self._active_states):
                if state.phase != TradePhase.AWAITING_CONFIRMATION:
                    continue
                if state.order_id is None or state.order_id <= 0:
                    continue
                if state.signal_id in fresh_ids:
                    continue
                # Signal forsvunnet — cancel LIMIT og fjern state
                log.info(
                    "[CLEANUP] %s — signal forsvunnet fra fresh batch, "
                    "kanselerer LIMIT order_id=%d (%s %s).",
                    state.signal_id,
                    state.order_id,
                    state.direction.upper(),
                    state.horizon,
                )
                try:
                    self._client.cancel_order(order_id=state.order_id)
                except Exception as exc:
                    log.warning(
                        "[CLEANUP] cancel_order feilet for %s (orderId=%d): %s. "
                        "Fjerner state likevel — server-side LIMIT utløper på expiry.",
                        state.signal_id,
                        state.order_id,
                        exc,
                    )
                self._active_states.remove(state)

    def on_historical_bars(self, res: Any) -> None:
        """Bootstrap candle_buffers fra historical /15m eller /1H bars."""
        sid = res.symbolId
        digits = self._client.symbol_digits.get(sid, 5)
        div = 10**digits
        period = res.period if res.HasField("period") else M15_PERIOD

        buf = (
            self.h1_candle_buffers.get(sid) if period == H1_PERIOD else self.candle_buffers.get(sid)
        )
        if not buf:
            return

        for bar in res.trendbar:
            low_i = bar.low if bar.HasField("low") else 0
            close_i = low_i + bar.deltaClose if bar.HasField("deltaClose") else low_i
            open_i = low_i + bar.deltaOpen if bar.HasField("deltaOpen") else close_i
            high_i = low_i + bar.deltaHigh if bar.HasField("deltaHigh") else close_i
            low = low_i / div
            close = close_i / div
            open_ = open_i / div
            high = high_i / div
            ts = datetime.fromtimestamp(bar.utcTimestampInMinutes * 60, tz=timezone.utc)
            buf.candles.append(
                Candle(
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=bar.volume,
                    timestamp=ts,
                )
            )

        name = next((k for k, v in self._client.symbol_map.items() if v == sid), str(sid))
        if period == H1_PERIOD:
            self._update_indicators_h1(sid)
            ema_str = f"{self.ema9_h1[sid][-1]:.5f}" if self.ema9_h1.get(sid) else "N/A"
            log.info(
                "[INIT-1H] %s: %d 1H-candles lastet, EMA9=%s",
                name,
                len(buf.candles),
                ema_str,
            )
        else:
            self._update_indicators(sid)
            ema_str = f"{self.ema9[sid][-1]:.5f}" if self.ema9[sid] else "N/A"
            log.info(
                "[INIT] %s: %d historiske candles lastet, EMA9=%s",
                name,
                len(buf.candles),
                ema_str,
            )

    def on_spot(self, event: Any) -> None:
        """Route spot-events — plukker trendbar-data embedded i SpotEvent."""
        sid = event.symbolId
        # Pris-feed-symboler har ingen candles — hopp over trendbar-håndtering
        if sid not in self.candle_buffers:
            return
        for bar in event.trendbar:
            if bar.period == M15_PERIOD:
                self._handle_trendbar(sid, bar, self.candle_buffers, fire_on_close=True)
            elif bar.period == M5_PERIOD:
                self._handle_trendbar(sid, bar, self.m5_candle_buffers, fire_on_close=False)
            elif bar.period == H1_PERIOD:
                self._handle_trendbar_h1(sid, bar)

    # ─────────────────────────────────────────────────────────
    # Trendbar-handling
    # ─────────────────────────────────────────────────────────

    def _handle_trendbar(
        self, sid: int, bar: Any, buffers: dict[int, CandleBuffer], *, fire_on_close: bool
    ) -> None:
        """Prosesserer én trendbar fra SpotEvent.
        fire_on_close=True for 15m (bekreftelse + management)."""
        digits = self._client.symbol_digits.get(sid, 5)
        div = 10**digits

        low_i = bar.low if bar.HasField("low") else 0
        close_i = low_i + bar.deltaClose if bar.HasField("deltaClose") else low_i
        open_i = low_i + bar.deltaOpen if bar.HasField("deltaOpen") else close_i
        high_i = low_i + bar.deltaHigh if bar.HasField("deltaHigh") else close_i

        low = low_i / div
        close = close_i / div
        open_ = open_i / div
        high = high_i / div

        buf = buffers.get(sid)
        if not buf:
            return

        if buf.current_ts is None or bar.utcTimestampInMinutes != buf.current_ts:
            # Lukk forrige candle
            if buf.current_ts is not None:
                prev_ts = datetime.fromtimestamp(buf.current_ts * 60, tz=timezone.utc)
                closed_candle = Candle(
                    open=buf.current_open or 0.0,
                    high=buf.current_high or 0.0,
                    low=buf.current_low or 0.0,
                    close=buf.current_close or 0.0,
                    volume=0,
                    timestamp=prev_ts,
                )
                buf.candles.append(closed_candle)
                if not fire_on_close:
                    self._update_indicators(sid)  # 15m-path oppdaterer EMA9/ATR
                if fire_on_close:
                    self._on_candle_closed(sid, closed_candle)

            buf.current_ts = bar.utcTimestampInMinutes
            buf.current_open = open_
            buf.current_high = high
            buf.current_low = low
            buf.current_close = close
        else:
            buf.current_high = max(buf.current_high or high, high)
            buf.current_low = min(buf.current_low or low, low)
            buf.current_close = close

    def _handle_trendbar_h1(self, sid: int, bar: Any) -> None:
        digits = self._client.symbol_digits.get(sid, 5)
        div = 10**digits
        low_i = bar.low if bar.HasField("low") else 0
        close_i = low_i + bar.deltaClose if bar.HasField("deltaClose") else low_i
        open_i = low_i + bar.deltaOpen if bar.HasField("deltaOpen") else close_i
        high_i = low_i + bar.deltaHigh if bar.HasField("deltaHigh") else close_i
        low, close, open_, high = low_i / div, close_i / div, open_i / div, high_i / div

        buf = self.h1_candle_buffers.get(sid)
        if not buf:
            return
        if buf.current_ts is None or bar.utcTimestampInMinutes != buf.current_ts:
            if buf.current_ts is not None:
                prev_ts = datetime.fromtimestamp(buf.current_ts * 60, tz=timezone.utc)
                buf.candles.append(
                    Candle(
                        open=buf.current_open or 0.0,
                        high=buf.current_high or 0.0,
                        low=buf.current_low or 0.0,
                        close=buf.current_close or 0.0,
                        volume=0,
                        timestamp=prev_ts,
                    )
                )
                self._update_indicators_h1(sid)
            buf.current_ts = bar.utcTimestampInMinutes
            buf.current_open = open_
            buf.current_high = high
            buf.current_low = low
            buf.current_close = close
        else:
            buf.current_high = max(buf.current_high or high, high)
            buf.current_low = min(buf.current_low or low, low)
            buf.current_close = close

    # ─────────────────────────────────────────────────────────
    # Indikatorer
    # ─────────────────────────────────────────────────────────

    def _update_indicators(self, symbol_id: int) -> None:
        """EMA9 + ATR14 (Wilder) fra 15m-candle-buffer."""
        buf = self.candle_buffers.get(symbol_id)
        if buf is None:
            return
        candles = list(buf.candles)
        if len(candles) < 2:
            return

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        k = 2 / (9 + 1)
        ema = closes[0]
        emas = [ema]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
            emas.append(ema)
        self.ema9[symbol_id] = emas

        trs = [
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            for i in range(1, len(candles))
        ]
        if len(trs) >= 14:
            atr = sum(trs[:14]) / 14
            atrs = [atr]
            for tr in trs[14:]:
                atr = (atr * 13 + tr) / 14
                atrs.append(atr)
            self.atr14[symbol_id] = atrs

    def _update_indicators_h1(self, symbol_id: int) -> None:
        buf = self.h1_candle_buffers.get(symbol_id)
        if buf is None:
            return
        candles = list(buf.candles)
        if len(candles) < 14:
            return
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        k = 2 / (9 + 1)
        ema = closes[0]
        emas = [ema]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
            emas.append(ema)
        self.ema9_h1[symbol_id] = emas

        trs = [
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            for i in range(1, len(candles))
        ]
        if len(trs) >= 14:
            atr = sum(trs[:14]) / 14
            atrs = [atr]
            for tr in trs[14:]:
                atr = (atr * 13 + tr) / 14
                atrs.append(atr)
            self.atr14_h1[symbol_id] = atrs

    def _update_atr14_5m(self, symbol_id: int) -> None:
        buf = self.m5_candle_buffers.get(symbol_id)
        if buf is None:
            return
        candles = list(buf.candles)
        if len(candles) < 15:
            return
        trs = [
            max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low - candles[i - 1].close),
            )
            for i in range(1, len(candles))
        ]
        atr = sum(trs[:14]) / 14
        for tr in trs[14:]:
            atr = (atr * 13 + tr) / 14
        self.atr14_5m[symbol_id] = atr

    def get_ema9(self, symbol_id: int, offset: int = 0) -> float | None:
        """offset=0 = siste lukkede bar, offset=1 = nest siste."""
        emas = self.ema9.get(symbol_id, [])
        idx = -(offset + 1)
        return emas[idx] if len(emas) >= abs(idx) else None

    def get_atr14(self, symbol_id: int) -> float | None:
        atrs = self.atr14.get(symbol_id, [])
        return atrs[-1] if atrs else None

    def get_atr14_h1(self, symbol_id: int) -> float | None:
        atrs = self.atr14_h1.get(symbol_id, [])
        return atrs[-1] if atrs else None

    def get_ema9_h1(self, symbol_id: int, offset: int = 0) -> float | None:
        """1H EMA9 — brukes av ExitEngine for SWING/MAKRO P4 (EMA9-kryss)."""
        emas = self.ema9_h1.get(symbol_id, [])
        idx = -(offset + 1)
        return emas[idx] if len(emas) >= abs(idx) else None

    def set_manage_open_positions(self, callback: ManagePositionsCallback) -> None:
        """Sett (eller bytt ut) manage_open_positions-callbacken etter
        konstruksjon. Brukes i `bot/__main__.py` for å koble ExitEngine
        inn etter at begge er instansiert (sirkulær dep: ExitEngine
        trenger EntryEngine-ref, EntryEngine trenger manage-callback)."""
        self._manage_open_positions = callback

    def get_normal_spread(self, symbol_id: int) -> float:
        hist = self._client.spread_history.get(symbol_id, deque())
        return sum(hist) / len(hist) if hist else 0.0

    # ─────────────────────────────────────────────────────────
    # Candle-close — hoved-sløyfe
    # ─────────────────────────────────────────────────────────

    def _on_candle_closed(self, symbol_id: int, candle: Candle) -> None:
        """Ved lukket 15m-candle: evaluere watchlist + manage åpne posisjoner."""
        self._update_atr14_5m(symbol_id)

        # Daily-loss-reset (safety-hook trigger batch-commit ved rollover)
        if self._safety.reset_daily_loss_if_new_day():
            self._daily_loss_logged = False  # ny dag = nytt log-vindu

        # Bot-lås
        if self._safety.bot_locked:
            if (
                self._safety.bot_locked_until is None
                or datetime.now(timezone.utc) < self._safety.bot_locked_until
            ):
                self._manage_open_positions(symbol_id, candle)
                return
            else:
                self._safety.bot_locked = False
                log.info("[LOCK] Bot-lås opphevet.")

        # Server frossen
        if self._safety.server_frozen:
            self._manage_open_positions(symbol_id, candle)
            return

        if not self.signal_data:
            self._manage_open_positions(symbol_id, candle)
            return

        # Signal-fil utløpt
        valid_until = self.signal_data.get("valid_until")
        if valid_until:
            try:
                exp = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp:
                    now_min = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                    if self._last_expiry_log != now_min:
                        log.info("[UTLØPT] Signalfilen er utgått — venter på nye signaler.")
                        self._last_expiry_log = now_min
                    self._manage_open_positions(symbol_id, candle)
                    return
            except (ValueError, TypeError):
                pass  # graceful — neste iterasjon prøver igjen

        # Prosesser watchlist-signaler
        # BUG-FIX Fase 8: IKKE kall _recalibrate_agri_levels på agri-signaler.
        # Setup-generator-ens reelle nivå-baserte SL/T1/T2/entry_zone
        # respekteres nå — gammel bot overstyrte dem med 1.5/2.5/3.5×ATR.
        for sig in self.signal_data.get("signals", []):
            if sig.get("status") != "watchlist":
                continue
            sid_for_sig = self._client.symbol_map.get(sig.get("instrument", ""))
            if sid_for_sig != symbol_id:
                continue
            # Agri-signaler passerer NÅ uendret gjennom bot-pipelinen.
            self._process_watchlist_signal(sig, symbol_id, candle)

        self._manage_open_positions(symbol_id, candle)

    # ─────────────────────────────────────────────────────────
    # Signal-evaluering
    # ─────────────────────────────────────────────────────────

    def _process_watchlist_signal(
        self, sig: dict[str, Any], symbol_id: int, candle: Candle
    ) -> None:
        instrument = sig.get("instrument", "")

        # ── Hard-disabled-guard (session 2026-05-26) ─────────────
        # Selv om signal-server eller bot_whitelist skulle slippe
        # disse igjennom, blokkeres de her som siste line-of-defense.
        # Tilsvarende guard i src/bedrock/cli/signals_all.py:
        # PERMANENTLY_DISABLED. For å reaktivere må navn fjernes
        # FRA BÅDE STEDENE (synlig PR-endring).
        if instrument.upper() in _PERMANENTLY_DISABLED_BOT_INSTRUMENTS:
            if instrument not in self._permanently_disabled_logged:
                log.warning(
                    "[PERM-DISABLED] %s — ignoreres (se entry.py "
                    "_PERMANENTLY_DISABLED_BOT_INSTRUMENTS for hvorfor).",
                    instrument,
                )
                self._permanently_disabled_logged.add(instrument)
            return

        # Varsel hvis FX-par mangler USD-retningsmapping
        if looks_like_fx_pair(instrument) and instrument not in FX_USD_DIRECTION:
            if instrument not in self._usd_dir_missing_logged:
                log.warning(
                    "[USD-DIR] %s mangler i FX_USD_DIRECTION — USD-konflikt-sjekk "
                    "vil ikke fungere for dette paret. Legg til i bot/instruments.py.",
                    instrument,
                )
                self._usd_dir_missing_logged.add(instrument)

        # Tidlig daily-loss-gate
        if self._client.account_balance > 0 and self._safety.daily_loss_exceeded(
            self._client.account_balance, self._config.daily_loss
        ):
            if not self._daily_loss_logged:
                limit = self._safety.daily_loss_limit(
                    self._client.account_balance, self._config.daily_loss
                )
                log.warning(
                    "[DAGLIG TAP] Grense passert (%.0f ≥ %.0f) — "
                    "avviser alle nye signaler resten av dagen.",
                    self._safety.daily_loss,
                    limit,
                )
                self._daily_loss_logged = True
            return

        # Per-signal TTL
        created_at = sig.get("created_at")
        horizon = sig.get("horizon", "SWING")
        if created_at:
            try:
                ca = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - ca).total_seconds()
                ttl = self._horizon_ttl_seconds(horizon)
                if age > ttl:
                    sig_id = sig.get("id", "?")
                    if sig_id not in self._ttl_logged:
                        log.info(
                            "[TTL] Signal %s skippet — alder %.0fs > %ds for %s",
                            sig_id,
                            age,
                            ttl,
                            horizon,
                        )
                        self._ttl_logged.add(sig_id)
                    return
            except (ValueError, TypeError) as e:
                log.warning("[TTL] Kunne ikke parse created_at=%r: %s", created_at, e)

        with self._lock:
            state = next(
                (s for s in self._active_states if s.signal_id == sig.get("id")),
                None,
            )

            bid = self._client.last_bid.get(symbol_id, candle.close)
            ask = self._client.last_ask.get(symbol_id, candle.close)
            price = bid if sig.get("direction") == "sell" else ask

            entry_zone = sig.get("entry_zone") or [0, 0]
            in_zone = entry_zone[0] <= price <= entry_zone[1]

            # Aktiver bekreftelsesvindu
            if in_zone and state is None:
                dirn = sig.get("direction", "")
                sig_id = sig.get("id", "")
                # Loss-cooldown: hvis denne signal_id stengte i tap
                # innenfor TTL-vinduet, ikke ta på nytt. Orchestrator
                # persisterer setup_id via hysterese — i sideways-marked
                # får vi samme signal_id om og om igjen, og uten cooldown
                # ender vi i en loss → re-entry → loss-loop. TTL slipper
                # fri etter `config.cooldown.loss_ttl_hours` slik at
                # cooldown ikke blir evig blacklist når orchestrator
                # gjenfinner samme nivå over uker.
                if sig_id and self._is_in_loss_cooldown(sig_id):
                    if sig_id not in self._cooldown_logged:
                        ttl_h = self._config.cooldown.loss_ttl_hours
                        lost_at = self._lost_signal_ids[sig_id]
                        log.info(
                            "[COOLDOWN] %s [%s] — tap %s; blokkerer re-entry i %dt (TTL).",
                            sig_id,
                            horizon,
                            lost_at.strftime("%Y-%m-%d %H:%M UTC"),
                            ttl_h,
                        )
                        self._cooldown_logged.add(sig_id)
                    return
                # Konflikt-blokk: blokker ny entry hvis det er en MOTSATT
                # direction-state allerede aktiv for samme instrument — på
                # tvers av alle horisonter. Orchestrator's
                # `_resolve_direction_conflicts` filtrerer per signal-batch,
                # men på tvers av tidsepoker kan bot ha BUY åpen fra dag X
                # og SELL signal fra dag Y. Asymmetri-prinsipp: ett
                # instrument = én retning av gangen, uansett horisont.
                # La eksisterende posisjon håndteres av sin manage-logikk;
                # ny signal må vente til motsatt side er stengt.
                opposite_open = next(
                    (
                        s
                        for s in self._active_states
                        if getattr(s, "instrument", "") == instrument
                        and s.direction != dirn
                        and s.phase in (TradePhase.AWAITING_CONFIRMATION, TradePhase.IN_TRADE)
                    ),
                    None,
                )
                if opposite_open:
                    log.info(
                        "[KONFLIKT] %s [%s] %s blokkert — motsatt %s allerede åpen "
                        "(state %s). Venter på at motsatt side stenger.",
                        sig_id,
                        horizon,
                        dirn,
                        opposite_open.direction,
                        opposite_open.signal_id,
                    )
                    return
                # Duplikat-blokk: blokker kun samme (instrument, direction, horizon).
                # SCALP/SWING/MAKRO er uavhengige slots — en åpen scalp-buy
                # skal ikke hindre en swing-buy eller makro-buy på samme
                # instrument (egne stops/TP'er, egne tese-tidsskalaer).
                already = any(
                    s
                    for s in self._active_states
                    if getattr(s, "instrument", "") == instrument
                    and s.direction == dirn
                    and getattr(s, "horizon", "SWING") == horizon
                    and s.phase in (TradePhase.AWAITING_CONFIRMATION, TradePhase.IN_TRADE)
                )
                if already:
                    return

                hcfg_init = sig.get("horizon_config", {})
                if "exit_timeout_partial_candles" in hcfg_init:
                    exp_candles = hcfg_init["exit_timeout_partial_candles"]
                elif "exit_timeout_full_hours" in hcfg_init:
                    exp_candles = int(hcfg_init["exit_timeout_full_hours"] / 0.25)
                else:
                    group = self._config.group_params.get(_group_key(instrument, self._config))
                    default_expiry = group.expiry if group else 32
                    exp_candles = sig.get("expiry_candles", default_expiry)

                log.info(
                    "[ALERT] %s [%s] — pris %.5f i entry_zone %s",
                    sig.get("id"),
                    horizon,
                    price,
                    entry_zone,
                )
                # MAKRO: ingen fast TP, trailing aktiveres fra entry —
                # ingen tids-baserte exits, og T1-hit/giveback/EMA9-grener
                # i ExitEngine slås av via horizon-sjekk.
                is_makro = (horizon or "").upper() == "MAKRO"
                state = TradeState(
                    signal_id=sig.get("id", ""),
                    direction=dirn,
                    instrument=instrument,
                    symbol_id=symbol_id,
                    expiry_candles=exp_candles,
                    t1_price=sig.get("t1", 0.0),
                    stop_price=sig.get("stop", 0.0),
                    horizon=horizon,
                    horizon_config=hcfg_init,
                    correlation_group=sig.get("correlation_group"),
                    trail_active=is_makro,
                )
                self._active_states.append(state)

            if state is None or state.phase != TradePhase.AWAITING_CONFIRMATION:
                return

            # Filtre
            if not self._passes_filters(sig, symbol_id):
                return

            # Bekreftelse
            state.confirmation_candles += 1
            hcfg = sig.get("horizon_config", {})
            min_score = hcfg.get(
                "confirmation_min_score", self._config.confirmation.min_score_default
            )
            strict_score = hcfg.get("confirmation_strict_score", 3)

            if self._check_confirmation(
                sig, symbol_id, candle, min_score=min_score, strict_score=strict_score
            ):
                self._execute_trade(sig, state, candle)
            else:
                confirm_limit = sig.get("confirmation_candle_limit") or hcfg.get(
                    "confirmation_max_candles",
                    self._config.confirmation.max_candles_default,
                )
                if state.confirmation_candles >= confirm_limit:
                    log.info(
                        "[UTLØPT] %s [%s] — %d candles uten bekreftelse.",
                        sig.get("id"),
                        horizon,
                        state.confirmation_candles,
                    )
                    self._active_states.remove(state)

    # ─────────────────────────────────────────────────────────
    # Filters
    # ─────────────────────────────────────────────────────────

    def _passes_filters(self, sig: dict[str, Any], symbol_id: int) -> bool:
        gs = (self.signal_data or {}).get("global_state", {})
        rules = (self.signal_data or {}).get("rules", {})

        is_agri = sig.get("instrument", "") in AGRI_INSTRUMENTS

        # USDA blackout — blokker agri-entry under rapporter
        if is_agri:
            usda_bo = gs.get("usda_blackout") or {}
            instr_bo = usda_bo.get(sig.get("instrument", ""))
            if instr_bo:
                log.info(
                    "[FILTER] %s — USDA blackout: %s om %st",
                    sig.get("id"),
                    instr_bo.get("report"),
                    instr_bo.get("hours_away"),
                )
                return False

        # Spread cold-start-vern
        spread_samples = len(self._client.spread_history.get(symbol_id, ()))
        min_samples = self._config.spread.min_samples
        if spread_samples < min_samples:
            if symbol_id not in self._spread_cold_logged:
                log.info(
                    "[FILTER] %s — utilstrekkelig spread-historikk (%d/%d samples). "
                    "Venter på flere spot-events.",
                    sig.get("id"),
                    spread_samples,
                    min_samples,
                )
                self._spread_cold_logged.add(symbol_id)
            return False

        # Spread-grense
        normal_spread = self.get_normal_spread(symbol_id)
        current_spread = self._client.last_ask.get(symbol_id, 0) - self._client.last_bid.get(
            symbol_id, 0
        )
        if is_agri:
            spread_mult = self._config.spread.agri_multiplier
        else:
            # non_agri_multiplier_of_stop brukes som × stop_multiplier
            # (matcher gammel bot: stop_multiplier × 2)
            spread_mult = (
                rules.get("stop_multiplier", 3.0) * self._config.spread.non_agri_multiplier_of_stop
            )
        max_spread = spread_mult * normal_spread
        if normal_spread > 0 and current_spread > max_spread:
            log.info(
                "[FILTER] %s — spread %.5f > maks %.5f (%s).",
                sig.get("id"),
                current_spread,
                max_spread,
                "agri" if is_agri else "normal",
            )
            return False

        # R:R — horizon-differensiert
        geo = gs.get("geo_active", False)
        horizon = sig.get("horizon", "SWING")
        min_rr = self._horizon_min_rr(horizon)
        if geo:
            min_rr = max(min_rr, rules.get("min_rr_geo", 2.0))
        risk = abs(sig.get("alert_level", 0) - sig.get("stop", 0))
        reward = abs(sig.get("alert_level", 0) - sig.get("t1", 0))
        rr = reward / risk if risk > 0 else 0
        if rr < min_rr:
            log.info(
                "[FILTER] %s [%s] — R:R %.2f < min %.2f.",
                sig.get("id"),
                horizon,
                rr,
                min_rr,
            )
            return False

        return True

    # ─────────────────────────────────────────────────────────
    # Confirmation (3-punkt)
    # ─────────────────────────────────────────────────────────

    def _check_confirmation(
        self,
        sig: dict[str, Any],
        symbol_id: int,
        candle: Candle,
        *,
        min_score: int = 2,
        strict_score: int = 3,
    ) -> bool:
        """3-punkt scoring: body ≥ cfg.body_threshold_atr_pct × 5m-ATR,
        wick-rejection, EMA9-gradient peker riktig vei."""
        ema_curr = self.get_ema9(symbol_id, offset=0)
        ema_prev = self.get_ema9(symbol_id, offset=1)
        if ema_curr is None or ema_prev is None:
            log.debug("[BEKREFT] %s — EMA9 ikke klar ennå.", sig.get("id"))
            return False

        close = candle.close
        open_ = candle.open
        high = candle.high
        low = candle.low
        is_buy = sig.get("direction") == "buy"
        entry_zone = sig.get("entry_zone") or [0, 0]
        zone_lo, zone_hi = entry_zone[0], entry_zone[1]

        # Poeng 1: candle-body ≥ body_threshold × 5m-ATR
        atr_5m = self.atr14_5m.get(symbol_id)
        body = abs(close - open_)
        if atr_5m and atr_5m > 0:
            body_ok = body >= self._config.confirmation.body_threshold_atr_pct * atr_5m
        else:
            body_ok = close != open_  # fallback: ikke doji

        # Poeng 2: wick-rejection
        if is_buy:
            wick_ok = low <= zone_hi and close > (high + low) / 2
        else:
            wick_ok = high >= zone_lo and close < (high + low) / 2

        # Poeng 3: EMA9 gradient
        atr_15m = self.get_atr14(symbol_id) or 1
        gradient = (ema_curr - ema_prev) / atr_15m
        if is_buy:
            ema_ok = gradient >= self._config.confirmation.ema_gradient_buy_min
        else:
            ema_ok = gradient <= self._config.confirmation.ema_gradient_sell_max

        score = sum([body_ok, wick_ok, ema_ok])
        log.info(
            "[BEKREFT] %s score=%d/3 body=%s wick=%s ema=%s (grad=%+.3f)",
            sig.get("id"),
            score,
            "✓" if body_ok else "✗",
            "✓" if wick_ok else "✗",
            "✓" if ema_ok else "✗",
            gradient,
        )

        # Krev strict_score hvis motstridende FX USD-retning med åpne trades
        required = min_score
        new_usd = net_usd_direction(sig.get("instrument", ""), sig.get("direction", ""))
        if new_usd:
            for s in self._active_states:
                if s.phase == TradePhase.IN_TRADE:
                    existing_usd = net_usd_direction(getattr(s, "instrument", ""), s.direction)
                    if existing_usd and existing_usd != new_usd:
                        required = strict_score
                        log.info(
                            "[MOTSTRIDENDE] %s (%s) vs %s (%s) — krever %d/3.",
                            sig.get("id"),
                            new_usd,
                            s.instrument,
                            existing_usd,
                            strict_score,
                        )
                        break

        # Akkumuler statistikk
        passed = score >= required
        self._confirmation_stats["total"] += 1
        bs = self._confirmation_stats["by_score"]
        bs[score] = bs.get(score, 0) + 1
        if passed:
            self._confirmation_stats["passed"] += 1
        else:
            self._confirmation_stats["failed"] += 1
        if required == strict_score:
            self._confirmation_stats["strict_required"] += 1

        # Persist hver 20. evaluering
        if self._confirmation_stats["total"] % 20 == 0:
            self._save_confirmation_stats()

        if passed:
            log.info("[BEKREFTET] %s ✅ (%d/%d)", sig.get("id"), score, required)
            return True
        return False

    def _save_confirmation_stats(self) -> None:
        """Atomic write av confirmation-stats."""
        try:
            stats = dict(self._confirmation_stats)
            stats["last_updated"] = datetime.now(timezone.utc).isoformat()
            if stats["total"] > 0:
                stats["pass_rate"] = round(stats["passed"] / stats["total"], 3)
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix="confirm_", suffix=".json", dir=self._stats_path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=2, default=str)
                os.replace(tmp, self._stats_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            log.warning("[M7] Kunne ikke skrive confirmation_stats: %s", e)

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_log_timestamp(ts: str) -> datetime | None:
        """Parse `_log_trade_closed`-format: "YYYY-MM-DD HH:MM timezone.utc".

        Returnerer None hvis input er tom/uventet — kaller skal da
        behandle entry som "ukjent alder" og normalt skippe den.
        """
        if not isinstance(ts, str) or len(ts) < 16:
            return None
        try:
            return datetime.strptime(ts[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _is_in_loss_cooldown(self, signal_id: str) -> bool:
        """True hvis signal_id har et tap registrert innenfor TTL-vinduet.

        Sjekkes ved hver entry-evaluering så cooldown utløper også uten
        bot-restart. Side-effekt: utløpte entries fjernes fra både
        `_lost_signal_ids` og `_cooldown_logged` slik at en ny info-log
        kan trigges hvis samme id taper igjen senere.
        """
        lost_at = self._lost_signal_ids.get(signal_id)
        if lost_at is None:
            return False
        ttl_h = self._config.cooldown.loss_ttl_hours
        age_h = (datetime.now(timezone.utc) - lost_at).total_seconds() / 3600.0
        if age_h < ttl_h:
            return True
        # Utløpt: rydd opp så neste tap får frisk log + ny TTL-klokke.
        self._lost_signal_ids.pop(signal_id, None)
        self._cooldown_logged.discard(signal_id)
        return False

    def _load_lost_signal_ids_from_log(self) -> None:
        """Last signal_ids med result='loss' fra signal_log.json ved oppstart.

        Sikrer at loss-cooldown overlever bot-restart. Bare entries
        innenfor `loss_ttl_hours` lastes — eldre tap droppes (uten dette
        akkumulerer cooldown evig blacklist; se commit 6acb609 / regress
        2026-05-26). Trygt no-op hvis loggen ikke finnes eller er korrupt.
        """
        path = self._trade_log_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("[COOLDOWN] kunne ikke lese %s: %s", path, exc)
            return
        entries = data.get("entries", []) if isinstance(data, dict) else []
        ttl_h = self._config.cooldown.loss_ttl_hours
        now = datetime.now(timezone.utc)
        loaded = 0
        skipped_old = 0
        skipped_unparsed = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("result") != "loss":
                continue
            sig_id = (entry.get("signal") or {}).get("id")
            if not isinstance(sig_id, str) or not sig_id:
                continue
            closed_at = self._parse_log_timestamp(entry.get("closed_at") or "")
            if closed_at is None:
                # Fallback: prøv timestamp (åpningstidspunkt). Bedre å
                # underestimere alder enn å la et ukjent tap låse i evig.
                closed_at = self._parse_log_timestamp(entry.get("timestamp") or "")
            if closed_at is None:
                skipped_unparsed += 1
                continue
            age_h = (now - closed_at).total_seconds() / 3600.0
            if age_h >= ttl_h:
                skipped_old += 1
                continue
            # Behold yngste tap-tid per signal_id (i tilfelle flere closes).
            prev = self._lost_signal_ids.get(sig_id)
            if prev is None or closed_at > prev:
                self._lost_signal_ids[sig_id] = closed_at
                if prev is None:
                    loaded += 1
        if loaded or skipped_old or skipped_unparsed:
            log.info(
                "[COOLDOWN] Lastet %d aktive tap-signal_ids (TTL=%dt); "
                "droppet %d eldre, %d uten parsbar dato.",
                loaded,
                ttl_h,
                skipped_old,
                skipped_unparsed,
            )

    def record_lost_signal(self, signal_id: str) -> None:
        """Registrer at et signal stengte i tap. ExitEngine kaller denne
        fra `_log_trade_closed` slik at re-entry blokkeres umiddelbart
        — uten å vente på neste log-reload. TTL-klokken starter nå."""
        if signal_id:
            self._lost_signal_ids[signal_id] = datetime.now(timezone.utc)
            self._cooldown_logged.discard(signal_id)

    def _horizon_ttl_seconds(self, horizon: str) -> int:
        ttl_cfg = self._config.horizon_ttl
        return {
            "SCALP": ttl_cfg.scalp,
            "SWING": ttl_cfg.swing,
            "MAKRO": ttl_cfg.makro,
        }.get(horizon, ttl_cfg.swing)

    def _horizon_min_rr(self, horizon: str) -> float:
        rr_cfg = self._config.horizon_min_rr
        return {"SCALP": rr_cfg.scalp, "SWING": rr_cfg.swing, "MAKRO": rr_cfg.makro}.get(
            horizon, rr_cfg.makro
        )

    # ─────────────────────────────────────────────────────────
    # Monday-gap og agri-session (brukes av _execute_trade_impl)
    # ─────────────────────────────────────────────────────────

    def _is_monday_gap(self, symbol_id: int) -> bool:
        """Mandag-gap-gate: blokker entry hvis gap > N×ATR fra fredags close.

        Portert fra `trading_bot.py:_is_monday_gap` (1775-1793). Bruker
        `config.monday_gap.atr_multiplier` i stedet for hardkodet 2.0.
        Gjelder kun første time etter åpning (CET).
        """
        now = datetime.now(CET)
        if now.weekday() != 0 or now.hour >= 1:
            return False
        atr = self.get_atr14_h1(symbol_id) or self.get_atr14(symbol_id)
        if not atr:
            return False
        h1_buf = self.h1_candle_buffers.get(symbol_id)
        if not h1_buf or not h1_buf.candles:
            return False
        friday_close = h1_buf.candles[-1].close
        bid = self._client.last_bid.get(symbol_id, 0)
        if bid and friday_close:
            gap = abs(bid - friday_close)
            mult = self._config.monday_gap.atr_multiplier
            if gap > mult * atr:
                return True
        return False

    def _agri_session_ok(self, instrument: str) -> bool:
        """Sjekk om nåværende CET-tid er innenfor agri-sessionens åpningstider.

        Portert fra `trading_bot.py:_agri_session_ok` (308-321). Session-
        tider hentes fra `config.agri.session_times_cet` — lowercase-
        nøkler (corn/wheat/...) mot capitalized-instrument-navn.
        Ukjent instrument → True (ikke blokkér).
        """
        sessions = self._config.agri.session_times_cet
        session = sessions.get(instrument.lower())
        if session is None:
            return True
        try:
            h_o, m_o = [int(x) for x in session.start.split(":")]
            h_c, m_c = [int(x) for x in session.end.split(":")]
        except (ValueError, AttributeError):
            return True  # Graceful: malformert config → ikke blokkér
        now = datetime.now(CET)
        open_mins = h_o * 60 + m_o
        close_mins = h_c * 60 + m_c
        now_mins = now.hour * 60 + now.minute
        return open_mins <= now_mins <= close_mins

    # ─────────────────────────────────────────────────────────
    # _execute_trade — gates + sizing + ordre-sending
    # ─────────────────────────────────────────────────────────

    def _execute_trade_impl(self, sig: dict[str, Any], state: TradeState, candle: Candle) -> None:
        """Gater, sizer og sender ordre.

        Portert fra `trading_bot.py:_execute_trade` (1491-1732) per
        migrasjons-plan § 3.4. Ingen logikk-endring utover:
        - daily-loss leses fra `SafetyMonitor` + `DailyLossConfig` (ikke
          rules-dict)
        - oil-gate leses fra `config.oil` (ikke rules-dict hardkodet)
        - agri-grenser leses fra `config.agri` (ikke modul-konstanter)
        - sizing delegert til `bedrock.bot.sizing`
        - korrelasjonsgrenser leses fra `global_state.correlation_config`
          (uendret)
        - ordre-send delegert til `CtraderClient.send_new_order`
        - `_log_trade_opened` skriver til `~/bedrock/data/bot/signal_log.json`
          UTEN git-push (gammel bot pushet logg til cot-explorer; Bedrock
          skal ikke gjøre git i hot-path)
        """
        # Idempotency: hvis state allerede har en aktiv LIMIT på server
        # (order_id > 0) eller en in-flight send (order_id == -1), ikke
        # send en ny ordre. Forhindrer at re-publiserte signaler eller
        # gjentatte confirmation-events lager duplikat-LIMITs på cTrader.
        if state.order_id is not None and state.order_id != 0:
            log.debug(
                "[DUP-GUARD] %s — ordre allerede sendt (order_id=%s, phase=%s); "
                "hopper over ny send.",
                sig.get("id"),
                state.order_id,
                state.phase.name,
            )
            return
        if state.phase != TradePhase.AWAITING_CONFIRMATION:
            log.debug(
                "[DUP-GUARD] %s — state phase=%s, ikke AWAITING_CONFIRMATION; "
                "hopper over ordre-send.",
                sig.get("id"),
                state.phase.name,
            )
            return
        # Reservér slot tidlig så samtidige confirmation-events ikke
        # begge kan komme forbi guarden over. Erstattes med ekte orderId
        # i on_execution når server svarer ORDER_ACCEPTED.
        state.order_id = -1

        gs = (self.signal_data or {}).get("global_state", {})
        rules = (self.signal_data or {}).get("rules", {})

        # Entry-pris basert på side
        entry_price = (
            self._client.last_ask.get(state.symbol_id, candle.close)
            if sig["direction"] == "buy"
            else self._client.last_bid.get(state.symbol_id, candle.close)
        )

        # ── Monday gap-gate ───────────────────────────────────
        if self._is_monday_gap(state.symbol_id):
            log.info(
                "[MONDAY GAP] %s — gap > %.1f×ATR, venter på 1H close.",
                sig["id"],
                self._config.monday_gap.atr_multiplier,
            )
            self._remove_state(state)
            return

        risk_per_unit = abs(entry_price - sig["stop"])
        if risk_per_unit <= 0:
            log.error("[FEIL] %s — risk_per_unit=0. Avbryter.", sig["id"])
            self._remove_state(state)
            return

        # ── Oil geo-spread-sjekk ──────────────────────────────
        instr_name = sig.get("instrument", "")
        is_oil = instr_name in ("OIL BRENT", "OIL WTI")
        if is_oil and gs.get("oil_geo_warning", False):
            oil_cfg = self._config.oil
            min_sl_pips = rules.get("oil_min_sl_pips", oil_cfg.min_sl_pips)
            max_spread_m = rules.get("oil_max_spread_mult", oil_cfg.max_spread_mult)
            spread = self._client.last_ask.get(state.symbol_id, 0) - self._client.last_bid.get(
                state.symbol_id, 0
            )
            if risk_per_unit < min_sl_pips * 0.01:
                log.warning(
                    "[GEO-OLJE BLOKKERT] %s — SL for smal (%.3f < %d pips) under geo-advarsel.",
                    sig["id"],
                    risk_per_unit,
                    min_sl_pips,
                )
                self._remove_state(state)
                return
            if spread > 0 and risk_per_unit < max_spread_m * spread:
                log.warning(
                    "[GEO-OLJE BLOKKERT] %s — SL (%.3f) < %.1f× spread (%.3f) under geo-advarsel.",
                    sig["id"],
                    risk_per_unit,
                    max_spread_m,
                    spread,
                )
                self._remove_state(state)
                return

        # ── SL-vs-spread guard (universell) ───────────────────
        # Hindrer at SL ligger så tett på entry at normal bid-ask-
        # spread alene utløser stop (NATGAS-bug 2026-05-14). Oil under
        # geo håndteres av strengere blokk over (skip-condition speiler
        # den så vi ikke dobbel-blokkerer).
        if not (is_oil and gs.get("oil_geo_warning", False)):
            spread_now = self._client.last_ask.get(state.symbol_id, 0) - self._client.last_bid.get(
                state.symbol_id, 0
            )
            horizon = (sig.get("horizon") or "SWING").upper()
            sl_spread_mult = self._config.spread.sl_min_spread_mult_for_horizon(horizon)
            rule_override = rules.get("sl_min_spread_mult")
            if rule_override is not None:
                sl_spread_mult = float(rule_override)
            if spread_now > 0 and risk_per_unit < sl_spread_mult * spread_now:
                log.warning(
                    "[SL-SPREAD BLOKKERT] %s [%s] — risk %.5f < %.2f× spread %.5f "
                    "(eff. SL-avstand etter spread = %.5f).",
                    sig["id"],
                    horizon,
                    risk_per_unit,
                    sl_spread_mult,
                    spread_now,
                    risk_per_unit - spread_now,
                )
                self._remove_state(state)
                return

        # ── Daglig tapsgrense ─────────────────────────────────
        balance = self._client.account_balance
        if balance > 0 and self._safety.daily_loss_exceeded(balance, self._config.daily_loss):
            limit = self._safety.daily_loss_limit(balance, self._config.daily_loss)
            log.warning(
                "[DAGLIG TAP] Grense nådd (%.0f ≥ %.0f). Ingen nye trades i dag.",
                self._safety.daily_loss,
                limit,
            )
            self._remove_state(state)
            return

        # ── Sizing ───────────────────────────────────────────
        risk_pct = get_risk_pct(sig, gs, rules, self._config.risk_pct)
        risk_amount = balance * (risk_pct / 100.0)
        desired_lots = compute_desired_lots(sig, risk_pct)
        symbol_info = self._client.symbol_info.get(state.symbol_id)
        if symbol_info is None:
            log.warning(
                "[VOLUM] Symbol info mangler for %s — bruker 1000",
                state.symbol_id,
            )
        volume_units = lots_to_volume_units(desired_lots, symbol_info)
        lot_size_str = str(symbol_info["lot_size"]) if symbol_info else "?"
        log.info(
            "[VOLUM] %s: %s lot × lotSize=%s = %s enheter",
            instr_name,
            desired_lots,
            lot_size_str,
            volume_units,
        )

        # ── Agri-spesifikke sjekker ───────────────────────────
        if instr_name in AGRI_INSTRUMENTS:
            agri_cfg = self._config.agri
            # 1) Maks samtidige agri-posisjoner
            agri_active = sum(
                1
                for s in self._active_states
                if s.phase == TradePhase.IN_TRADE
                and getattr(s, "instrument", "") in AGRI_INSTRUMENTS
            )
            if agri_active >= agri_cfg.max_concurrent:
                log.info(
                    "[AGRI] %s blokkert — %d/%d agri-posisjoner aktive.",
                    sig["id"],
                    agri_active,
                    agri_cfg.max_concurrent,
                )
                self._remove_state(state)
                return

            # 1b) Sub-gruppe korrelasjon
            this_subgroup = AGRI_SUBGROUPS.get(instr_name, "")
            if this_subgroup:
                subgroup_active = sum(
                    1
                    for s in self._active_states
                    if s.phase == TradePhase.IN_TRADE
                    and AGRI_SUBGROUPS.get(getattr(s, "instrument", ""), "") == this_subgroup
                )
                if subgroup_active >= agri_cfg.max_per_subgroup:
                    log.info(
                        "[AGRI] %s blokkert — subgroup '%s' full (%d/%d).",
                        sig["id"],
                        this_subgroup,
                        subgroup_active,
                        agri_cfg.max_per_subgroup,
                    )
                    self._remove_state(state)
                    return

            # 2) Session-filter
            if not self._agri_session_ok(instr_name):
                sess = agri_cfg.session_times_cet.get(instr_name.lower())
                sess_str = f"{sess.start}–{sess.end}" if sess else "?"
                log.info(
                    "[AGRI] %s blokkert — utenfor session (%s CET).",
                    sig["id"],
                    sess_str,
                )
                self._remove_state(state)
                return

            # 3) Spreadfilter — spread > max_ratio × ATR14
            atr = self.get_atr14(state.symbol_id)
            if atr:
                bid = self._client.last_bid.get(state.symbol_id, 0)
                ask = self._client.last_ask.get(state.symbol_id, 0)
                spread = ask - bid if ask > bid else 0.0
                if spread > agri_cfg.max_spread_atr_ratio * atr:
                    log.info(
                        "[AGRI] %s blokkert — spread for vid: %.5f > %.0f%%×ATR (%.5f).",
                        sig["id"],
                        spread,
                        agri_cfg.max_spread_atr_ratio * 100,
                        atr,
                    )
                    self._remove_state(state)
                    return

        # ── Korrelasjonsgating ────────────────────────────────
        # Makro/swing/scalp behandles uavhengig i samme instrument: kun
        # posisjoner med SAMME horisont teller mot per-gruppe-taket.
        this_horizon = (sig.get("horizon") or "SWING").upper()
        this_group = sig.get("correlation_group") or INSTRUMENT_GROUP.get(instr_name, "")
        corr_cfg = gs.get("correlation_config", {})
        if this_group:
            group_count = 0
            for s in self._active_states:
                s_group = getattr(s, "correlation_group", None) or INSTRUMENT_GROUP.get(
                    getattr(s, "instrument", ""), ""
                )
                s_horizon = str(getattr(s, "horizon", "") or "").upper()
                if (
                    s_group == this_group
                    and s_horizon == this_horizon
                    and s.phase == TradePhase.IN_TRADE
                    and s.signal_id != state.signal_id
                ):
                    group_count += 1
            max_per_grp_cfg = corr_cfg.get("max_per_group", {})
            default_per_group = {
                "precious_metals": 2,
                "us_indices": 1,
                "energy": 1,
                "usd_pairs": 2,
            }.get(this_group, 1)
            if isinstance(max_per_grp_cfg, dict):
                max_in_group = max_per_grp_cfg.get(this_group, default_per_group)
            else:
                max_in_group = int(max_per_grp_cfg)
            if group_count >= max_in_group:
                log.info(
                    "[KORRELASJON] %s blokkert — %d/%d i %s/%s allerede aktiv (regime=%s).",
                    sig["id"],
                    group_count,
                    max_in_group,
                    this_group,
                    this_horizon,
                    gs.get("correlation_regime", "normal"),
                )
                self._remove_state(state)
                return

        # Total posisjonsgrense
        max_total = corr_cfg.get("max_total", 6)
        total_active = sum(1 for s in self._active_states if s.phase == TradePhase.IN_TRADE)
        if total_active >= max_total:
            log.info(
                "[KORRELASJON] %s blokkert — %d/%d total posisjoner aktive (regime=%s).",
                sig["id"],
                total_active,
                max_total,
                gs.get("correlation_regime", "normal"),
            )
            self._remove_state(state)
            return

        # ── SL sanity-guard ───────────────────────────────────
        # Bot må aldri åpne en posisjon uten gyldig SL. MARKET-flowen
        # sender amend_sl_tp etter fill (exit.py:on_execution); hvis
        # stop_loss=0 fester cTrader ingen SL og posisjonen står ubeskyttet.
        # Adapteren (bot_adapter._adapt_one) dropper allerede sl=None,
        # men dette er defense-in-depth for direkte signal-injection
        # eller fremtidige adapter-endringer.
        sig_stop = sig.get("stop")
        if sig_stop is None or float(sig_stop) <= 0:
            log.warning(
                "[ENTRY-GUARD] %s — stop=%r mangler/<=0; nekter å åpne "
                "ubeskyttet posisjon. Fix generator/adapter-pipeline.",
                sig.get("id", "?"),
                sig_stop,
            )
            self._remove_state(state)
            return

        # ── Ordre-sending ─────────────────────────────────────
        trade_side = "SELL" if sig["direction"] == "sell" else "BUY"
        hcfg = sig.get("horizon_config", {})
        # Per-horisont LIMIT-flagg overstyrer global rules. SCALP→MARKET
        # (fart > entry-kvalitet), SWING/MAKRO→LIMIT (entry-kvalitet > fart;
        # SL festes synkront på serveren — ingen unprotected window).
        use_limit = hcfg.get("use_limit_orders", rules.get("use_limit_orders", False))
        price_digits = self._client.symbol_price_digits.get(state.symbol_id, 5)

        order_kwargs: dict[str, Any] = {
            "symbol_id": state.symbol_id,
            "trade_side": trade_side,
            "volume": volume_units,
            "label": f"SE-{sig['id']}",
            "comment": sig["id"],
        }
        if use_limit:
            tf_map = {"5min": 5, "15min": 15, "1H": 60, "D1": 1440}
            tf_min = tf_map.get(hcfg.get("confirmation_tf", "5min"), 5)
            max_c = hcfg.get("confirmation_max_candles", 6)
            import time as _time

            expiration_ms = int(_time.time() * 1000) + (max_c * tf_min * 60 * 1000)
            limit_price = round(sig["alert_level"], price_digits)
            order_kwargs.update(
                {
                    "order_type": "LIMIT",
                    "limit_price": limit_price,
                    "stop_loss": round(sig["stop"], price_digits),
                    "expiration_ms": expiration_ms,
                }
            )
            if sig.get("t1") and sig["t1"] > 0:
                order_kwargs["take_profit"] = round(sig["t1"], price_digits)
            log.info(
                "[LIMIT] %s — limit order @ %s SL=%s expiry=%d×%dmin",
                sig["id"],
                limit_price,
                order_kwargs["stop_loss"],
                max_c,
                tf_min,
            )
        else:
            order_kwargs["order_type"] = "MARKET"
            # SL/TP festes atomisk på ordre-requesten slik at posisjonen
            # er beskyttet fra fill-tidspunkt selv om boten kobles fra.
            # cTrader avviser absolutt SL/TP på MARKET (INVALID_REQUEST);
            # vi sender relative offset som heltall i 1/100000 av price
            # unit (cTrader-konstant uansett price_digits) i stedet.
            # Server beregner absolutt SL/TP fra faktisk fill og fester
            # atomisk. Etterfølgende `amend_sl_tp` i exit.on_execution
            # er idempotent backup som holder trail/BE/giveback-flyt
            # uendret.
            #
            # SL/T1 fra signalet kan ha mer presisjon enn symbolets
            # tick (eks. USDJPY SL=157.29406 mens tick=0.001). Avrund
            # først til price_digits så distansen blir tick-multiplum
            # — ellers avviser cTrader med "Relative stop loss has
            # invalid precision".
            sl_rounded = round(float(sig["stop"]), price_digits)
            entry_rounded = round(entry_price, price_digits)
            sl_dist = abs(sl_rounded - entry_rounded)
            order_kwargs["relative_stop_loss"] = max(1, round(sl_dist * 100000))
            if sig.get("t1") and sig["t1"] > 0:
                t1_rounded = round(float(sig["t1"]), price_digits)
                tp_dist = abs(t1_rounded - entry_rounded)
                order_kwargs["relative_take_profit"] = max(1, round(tp_dist * 100000))
            # MAKRO har trail-active fra entry (ingen T1-pause). Aktiver
            # server-side trailing direkte — cTrader ratchet'er SL videre
            # på server selv om bot/PC slås av. SCALP/SWING er pre-T1
            # statisk; server-trail engasjeres via amend i ExitEngine når
            # bot setter `trail_active=True` etter T1-hit.
            if sig.get("horizon", "SWING").upper() == "MAKRO":
                order_kwargs["trailing_stop_loss"] = True

        state.entry_price = entry_price
        state.full_volume = volume_units
        state.instrument = instr_name or sig.get("id", "")
        state.lots_used = desired_lots
        state.risk_pct_used = risk_pct
        state.horizon = sig.get("horizon", "SWING")
        # Signal-server schema 2.x bruker feltet "grade" (A+/A/B/C).
        # Historisk navn fra scalp_edge-bot var "character"; det er aldri
        # sendt fra bedrock signal_server. Default "B" beholdes som
        # konservativ fallback hvis et eldre format en gang skulle dukke
        # opp (lavere risk-tier enn "A" via sizing.get_risk_pct).
        state.grade = sig.get("grade", "B")
        state.horizon_config = sig.get("horizon_config", {})
        state.correlation_group = sig.get("correlation_group")
        if use_limit:
            state.order_id = -1  # placeholder — settes fra execution event
        # Phase settes til IN_TRADE kun etter bekreftelse i on_execution

        log.info(
            "[ORDRE] %s | %s %d enheter @ %.5f | SL=%.5f | T1=%.5f | Risk=%.2f (%s%%)",
            sig["id"],
            sig["direction"].upper(),
            volume_units,
            entry_price,
            sig["stop"],
            sig.get("t1") or 0.0,
            risk_amount,
            risk_pct,
        )

        self._client.send_new_order(**order_kwargs)

    # ─────────────────────────────────────────────────────────
    # Helpers: remove_state + trade-logging
    # ─────────────────────────────────────────────────────────

    def _remove_state(self, state: TradeState) -> None:
        """Fjern state fra active_states hvis den finnes. Trygt å kalle flere ganger."""
        try:
            self._active_states.remove(state)
        except ValueError:
            pass

    def _log_trade_opened(self, state: TradeState) -> None:
        """Skriv en åpnet trade til `~/bedrock/data/bot/signal_log.json`.

        Portert fra `trading_bot.py:_log_trade_opened` (1805-1835), men
        UTEN `_git_push_log`-kall — Bedrock gjør ikke git-operasjoner
        i hot-path. Atomisk via tempfile + os.replace.

        Kalles fra session 45 (ExitEngine.on_execution ved ORDER_FILLED).
        Inkludert her allerede for at modulen skal eie trade-log-IO.
        """
        try:
            if self._trade_log_path.exists():
                data = json.loads(self._trade_log_path.read_text(encoding="utf-8"))
            else:
                data = {"entries": []}
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M timezone.utc")
            entry = {
                "timestamp": now,
                "closed_at": None,
                "result": None,
                "exit_reason": None,
                "signal": {
                    "id": state.signal_id,
                    "instrument": getattr(state, "instrument", state.signal_id),
                    "direction": state.direction.upper(),
                    "entry": round(state.entry_price, 5),
                    "stop": round(state.stop_price, 5),
                    "t1": round(state.t1_price, 5) if state.t1_price else None,
                    "position_id": state.position_id,
                    "lots": volume_to_lots(
                        state.full_volume,
                        self._client.symbol_info.get(state.symbol_id),
                    ),
                    "risk_pct": getattr(state, "risk_pct_used", None),
                    "horizon": getattr(state, "horizon", "SCALP"),
                    "grade": getattr(state, "grade", None),
                },
            }
            data["entries"] = [entry, *data.get("entries", [])]
            # Samme pyright-smaltype-issue som i bot/exit.py.
            data["last_updated"] = now  # pyright: ignore[reportArgumentType]
            self._trade_log_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix="tradelog_", suffix=".json", dir=self._trade_log_path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._trade_log_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            log.info("[TRADE-LOG] %s åpnet", state.signal_id)
        except Exception as exc:
            log.warning("[TRADE-LOG] Åpning feilet: %s", exc)


def _group_key(instrument: str, _config: ReloadableConfig) -> str:
    """Oppslag via bot.instruments.get_group_name — her fordi vi vil
    unngå sirkulær import ved test av confirm-logikk isolert."""
    from bedrock.bot.instruments import get_group_name

    return get_group_name(instrument)
