"""Entry-lag: candle-handling, indikatorer, filters, confirmation.

Portert fra `~/scalp_edge/trading_bot.py` session 43 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.2 + 8 punkt 4`).

**KRITISK BUG-FIX I DENNE SESSION:** `_recalibrate_agri_levels` er SLETTET
og kall-stedet i `_on_candle_closed` er fjernet. Agri-signaler passerer
nå uendret gjennom bot-pipelinen — setup-generator-ens reelt-nivå-baserte
SL/T1/T2/entry_zone respekteres. Se `docs/migration/bot_refactor.md § 4`
for full forklaring av bugen.

Ansvaret:
- Eie candle-buffere (15m, 5m, 1h) og indikator-state (EMA9/ATR14)
- Populere buffere fra historical-bars ved oppstart
- Route spot-events → candle-handler
- Ved lukket 15m-candle: evaluere watchlist-signaler → filters →
  confirmation → execute_trade-callback
- Evaluere `active_states`-liste (exit-logikken fyres via callback)

Scope NOT i denne session:
- `_execute_trade` (ordre-sending) — session 44 (wirer CtraderClient
  send_new_order)
- `_manage_open_positions` (P1-P5 exit) — session 44

Wire-up i `bot/__main__.py` (session 45):
    entry = EntryEngine(client=..., safety=..., config=..., ...)
    client.callbacks.on_spot = entry.on_spot
    client.callbacks.on_historical_bars = entry.on_historical_bars
    client.callbacks.on_symbols_ready = entry.on_symbols_ready
    comms.on_signals = entry.on_signals
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional

from bedrock.bot.config import ReloadableConfig
from bedrock.bot.ctrader_client import CtraderClient, H1_PERIOD, M15_PERIOD, M5_PERIOD
from bedrock.bot.instruments import (
    AGRI_INSTRUMENTS,
    FX_USD_DIRECTION,
    looks_like_fx_pair,
    net_usd_direction,
)
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.state import Candle, CandleBuffer, TradePhase, TradeState

log = logging.getLogger("bedrock.bot.entry")


DEFAULT_CONFIRMATION_STATS_PATH = (
    Path.home() / "bedrock" / "data" / "bot" / "confirmation_stats.json"
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
        execute_trade: ExecuteTradeCallback = _noop,
        manage_open_positions: ManagePositionsCallback = _noop,
        stats_path: Optional[Path] = None,
    ) -> None:
        self._client = client
        self._safety = safety
        self._config = config
        self._active_states = active_states
        self._execute_trade = execute_trade
        self._manage_open_positions = manage_open_positions
        self._stats_path = stats_path or DEFAULT_CONFIRMATION_STATS_PATH

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
        self.signal_data: Optional[dict[str, Any]] = None

        # Stats for empirisk min_score-kalibrering
        self._confirmation_stats: dict[str, Any] = _initial_confirmation_stats()

        # Spam-vern-set (nullstilles ved restart — bevisst)
        self._usd_dir_missing_logged: set[str] = set()
        self._spread_cold_logged: set[int] = set()
        self._ttl_logged: set[str] = set()
        self._last_expiry_log: Optional[datetime] = None
        self._daily_loss_logged: bool = False

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
        # Reset daily-loss-log-flag når ny dag begynner (via safety-hook,
        # men også her som belte-og-seler)
        # (selve reset-handling er i SafetyMonitor.reset_daily_loss_if_new_day)

    def on_historical_bars(self, res: Any) -> None:
        """Bootstrap candle_buffers fra historical /15m eller /1H bars."""
        sid = res.symbolId
        digits = self._client.symbol_digits.get(sid, 5)
        div = 10**digits
        period = res.period if res.HasField("period") else M15_PERIOD

        buf = (
            self.h1_candle_buffers.get(sid)
            if period == H1_PERIOD
            else self.candle_buffers.get(sid)
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

        name = next(
            (k for k, v in self._client.symbol_map.items() if v == sid), str(sid)
        )
        if period == H1_PERIOD:
            self._update_indicators_h1(sid)
            ema_str = (
                f"{self.ema9_h1[sid][-1]:.5f}" if self.ema9_h1.get(sid) else "N/A"
            )
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
                self._handle_trendbar(
                    sid, bar, self.m5_candle_buffers, fire_on_close=False
                )
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

    def get_ema9(self, symbol_id: int, offset: int = 0) -> Optional[float]:
        """offset=0 = siste lukkede bar, offset=1 = nest siste."""
        emas = self.ema9.get(symbol_id, [])
        idx = -(offset + 1)
        return emas[idx] if len(emas) >= abs(idx) else None

    def get_atr14(self, symbol_id: int) -> Optional[float]:
        atrs = self.atr14.get(symbol_id, [])
        return atrs[-1] if atrs else None

    def get_atr14_h1(self, symbol_id: int) -> Optional[float]:
        atrs = self.atr14_h1.get(symbol_id, [])
        return atrs[-1] if atrs else None

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
        if (
            self._client.account_balance > 0
            and self._safety.daily_loss_exceeded(
                self._client.account_balance, self._config.daily_loss
            )
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
                # Duplikat-blokk
                already = any(
                    s
                    for s in self._active_states
                    if getattr(s, "instrument", "") == instrument
                    and s.direction == dirn
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
                    group = self._config.group_params.get(
                        _group_key(instrument, self._config)
                    )
                    default_expiry = group.expiry if group else 32
                    exp_candles = sig.get("expiry_candles", default_expiry)

                log.info(
                    "[ALERT] %s [%s] — pris %.5f i entry_zone %s",
                    sig.get("id"),
                    horizon,
                    price,
                    entry_zone,
                )
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
                rules.get("stop_multiplier", 3.0)
                * self._config.spread.non_agri_multiplier_of_stop
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
                    existing_usd = net_usd_direction(
                        getattr(s, "instrument", ""), s.direction
                    )
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


def _group_key(instrument: str, _config: ReloadableConfig) -> str:
    """Oppslag via bot.instruments.get_group_name — her fordi vi vil
    unngå sirkulær import ved test av confirm-logikk isolert."""
    from bedrock.bot.instruments import get_group_name

    return get_group_name(instrument)
