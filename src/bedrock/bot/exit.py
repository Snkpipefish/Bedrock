"""Exit-lag: P1-P5 posisjons-styring + cTrader execution/reconcile/order-error.

Portert fra `~/scalp_edge/trading_bot.py` session 45 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.4 + 8 punkt 5`).

Ansvaret:
- `manage_open_positions(symbol_id, candle)` — kalles fra EntryEngine
  ved hver lukket 15m-candle. Itererer IN_TRADE-states for symbolet og
  kjører P1-P5 exit-prioritet.
- cTrader-event-handlere som wires til `CtraderClient.callbacks`:
  - `on_execution(event)`: fill/partial-fill → flipp state til IN_TRADE
    + amend SL/TP for MARKET. Close-details → faktisk PnL fra cTrader.
  - `on_reconcile(res)`: ved oppstart tar over åpne SE-posisjoner og
    oppretter TradeState med `reconciled=True`.
  - `on_order_error(event)`: POSITION_NOT_FOUND → detekter TP vs SL;
    andre errors → rydd stuck states.
- Trade-close-logging til `~/bedrock/data/bot/signal_log.json`, og
  akkumulering av daily_loss i SafetyMonitor ved negative PnL.

Ikke-ansvar:
- Candle-handling / indikatorer — bor i EntryEngine. ExitEngine leser
  dem via `entry.get_*`-helpers.
- Signal-evaluering / confirmation — EntryEngine.

Wire-up (session 46 `bot/__main__.py`):
    exit_engine = ExitEngine(
        client=client, safety=safety, config=config,
        active_states=active_states, entry=entry,
    )
    entry.set_manage_open_positions(exit_engine.manage_open_positions)
    client.callbacks.on_execution = exit_engine.on_execution
    client.callbacks.on_reconcile = exit_engine.on_reconcile
    client.callbacks.on_order_error = exit_engine.on_order_error

Exit-prioritet (P1 → P5):
  P1  Geo-spike: move_against > geo_mult × ATR → STENG
  P2  Kill-switch: state.kill_switch satt → STENG
  P2.5 Weekend: fredag ≥20 CET → SCALP-lukk + SWING/MAKRO SL-stram
  P3  T1 nådd → partial-close (t1_close_pct) + break-even + trail-aktiv
  P3.5 Trailing-stop (post-T1) → close < trail_level → STENG
  P3.6 Give-back (pre-T1): peak ≥ gb_peak og progress ≤ gb_exit → STENG
  P4  EMA9-kryss (post-T1): close brøt EMA9 → STENG (hvis gp.ema9_exit)
  P5a Timeout (candles_since_entry ≥ expiry): progress-basert sortering
  P5b Hard close (candles_since_entry ≥ 2×expiry) → STENG
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from bedrock.bot.config import ReloadableConfig
from bedrock.bot.ctrader_client import CtraderClient
from bedrock.bot.instruments import INSTRUMENT_GROUP, get_group_name
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.sizing import volume_to_lots
from bedrock.bot.state import Candle, TradePhase, TradeState

if TYPE_CHECKING:
    from bedrock.bot.entry import EntryEngine

log = logging.getLogger("bedrock.bot.exit")

CET = ZoneInfo("Europe/Oslo")

DEFAULT_TRADE_LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "signal_log.json"

# PnL-kategorisering — portert fra trading_bot.py:1887-1894
_USD_BASE: frozenset[str] = frozenset({"USDJPY", "USDCHF", "USDCAD", "USDNOK"})

# Pip-størrelse pr digit fra cTrader symbol-metadata
_PIP_MAP: dict[int, float] = {5: 0.0001, 3: 0.01, 2: 0.01, 1: 0.1, 0: 1}


class ExitEngine:
    """Posisjons-styring + cTrader-event-handlere.

    Én instans per bot-prosess. Ikke thread-safe for samtidige writes;
    Twisted-reactor-tråden eier state-mutasjoner.
    """

    def __init__(
        self,
        *,
        client: CtraderClient,
        safety: SafetyMonitor,
        config: ReloadableConfig,
        active_states: list[TradeState],
        entry: EntryEngine,
        trade_log_path: Path | None = None,
    ) -> None:
        self._client = client
        self._safety = safety
        self._config = config
        self._active_states = active_states
        self._entry = entry
        self._trade_log_path = trade_log_path or DEFAULT_TRADE_LOG_PATH
        self._lock = Lock()

    # ─────────────────────────────────────────────────────────
    # P1-P5: manage_open_positions (kalles fra EntryEngine pr candle)
    # ─────────────────────────────────────────────────────────

    def manage_open_positions(self, symbol_id: int, candle: Candle) -> None:
        """Iterer IN_TRADE-states for symbolet og kjør P1-P5 exit-prioritet.

        Portert fra `trading_bot.py:_manage_open_positions` (2304-2510).
        Null logikk-endring utover at indikatorer leses fra `self._entry`
        og `CtraderClient.send_new_order`/`amend_sl_tp`/`close_position`
        brukes som transport.
        """
        remove: list[TradeState] = []
        states_for_sid = [
            s
            for s in self._active_states
            if s.phase == TradePhase.IN_TRADE and s.symbol_id == symbol_id
        ]
        for state in states_for_sid:
            if state.position_id is None:
                continue

            state.candles_since_entry += 1
            close = candle.close
            horizon = state.horizon or "SCALP"
            # SWING/MAKRO bruker 1H ATR/EMA; SCALP bruker 15m
            if horizon in ("SWING", "MAKRO"):
                atr = self._entry.get_atr14_h1(symbol_id) or self._entry.get_atr14(symbol_id)
                ema_c = self._entry.get_ema9_h1(symbol_id, 0) or self._entry.get_ema9(symbol_id, 0)
            else:
                atr = self._entry.get_atr14(symbol_id)
                ema_c = self._entry.get_ema9(symbol_id, 0)
            is_sell = state.direction == "sell"
            rules = (self._entry.signal_data or {}).get("rules", {})
            hcfg = state.horizon_config or {}
            geo_mult = hcfg.get(
                "exit_geo_spike_atr_mult",
                rules.get("geo_spike_atr_multiplier", 2.0),
            )

            # ── P1: Geo-spike ────────────────────────────────
            if atr:
                move_against = close - state.entry_price if is_sell else state.entry_price - close
                if move_against > geo_mult * atr:
                    log.warning(
                        "[GEO-SPIKE] %s — %.5f > %.2f×ATR. STENGER.",
                        state.signal_id,
                        move_against,
                        geo_mult,
                    )
                    self._close_all(state, close, "GEO-SPIKE")
                    remove.append(state)
                    continue

            # ── P2: Kill-switch ──────────────────────────────
            if state.kill_switch:
                log.warning("[KILL] %s — stenger.", state.signal_id)
                self._close_all(state, close, "KILL")
                remove.append(state)
                continue

            # ── P2.5: Weekend-gate ───────────────────────────
            weekend = self._weekend_action()
            if weekend["close_scalp"] and horizon == "SCALP":
                log.info("[WEEKEND] %s SCALP — stenger før helg.", state.signal_id)
                self._close_all(state, close, "WEEKEND-CLOSE")
                remove.append(state)
                continue
            if weekend["tighten_sl"] and horizon in ("SWING", "MAKRO") and atr is not None:
                tighter_sl = self._compute_weekend_sl(state, close, atr)
                if tighter_sl is not None:
                    old_sl = state.stop_price
                    state.stop_price = tighter_sl
                    self._client.amend_sl_tp(position_id=state.position_id, stop_loss=tighter_sl)
                    log.info(
                        "[WEEKEND] %s SL strammet: %.5f → %.5f (%.1f×ATR)",
                        state.signal_id,
                        old_sl,
                        tighter_sl,
                        self._config.weekend.sl_atr_mult,
                    )

            gp = self._config.group_params.get(get_group_name(state.instrument or ""))
            if gp is None:
                gp = self._config.group_params["fx"]
            progress = self._compute_progress(state, close)
            state.peak_progress = max(state.peak_progress, progress)

            log.debug(
                "[EXIT-EVAL] %s progress=%.2f peak=%.2f trail=%s candles=%d",
                state.signal_id,
                progress,
                state.peak_progress,
                state.trail_level,
                state.candles_since_entry,
            )

            # ── P3: T1 nådd (partial close + BE + trail-aktiv) ──
            if not state.t1_price_reached:
                t1_reached = close <= state.t1_price if is_sell else close >= state.t1_price
                if t1_reached:
                    t1_close_pct = hcfg.get("exit_t1_close_pct", 0.50)
                    close_vol, remaining = self._calc_close_volume(state, t1_close_pct)
                    forced_full = remaining == 0
                    pnl_vol = close_vol
                    self._client.close_position(position_id=state.position_id, volume=close_vol)
                    state.remaining_volume = remaining
                    self._set_break_even(state, symbol_id)
                    state.t1_price_reached = True
                    state.t1_hit = True
                    state.trail_active = True
                    trail_mult = self._resolve_trail_mult(state, hcfg, rules, gp)
                    self._update_trail(state, close, symbol_id, trail_mult)
                    log.info(
                        "[T1] %s — T1 nådd. Stengte %d enheter (%s). Trail aktivert.",
                        state.signal_id,
                        close_vol,
                        "hele" if forced_full else "50%",
                    )
                    if forced_full:
                        state.remaining_volume = pnl_vol
                        self._log_trade_closed(state, "T1", state.t1_price)
                        state.remaining_volume = 0
                        remove.append(state)
                    continue

            # ── P3.5: Trailing stop (post-T1) ─────────────────
            if state.trail_active and state.trail_level is not None:
                trail_mult = self._resolve_trail_mult(state, hcfg, rules, gp)
                self._update_trail(state, close, symbol_id, trail_mult)
                trail_hit = close < state.trail_level if not is_sell else close > state.trail_level
                if trail_hit:
                    log.info(
                        "[TRAIL STOP] %s — close %.5f brøt trail %.5f. Stenger.",
                        state.signal_id,
                        close,
                        state.trail_level,
                    )
                    self._close_all(state, close, "TRAIL")
                    remove.append(state)
                    continue

            # ── P3.6: Give-back beskyttelse (pre-T1) ──────────
            if not state.t1_price_reached:
                gb_peak = rules.get("giveback_peak_threshold", gp.gb_peak)
                gb_exit = rules.get("giveback_exit_threshold", gp.gb_exit)
                if state.peak_progress >= gb_peak and progress <= gb_exit:
                    log.info(
                        "[GIVE-BACK] %s — peak=%.0f%% nå=%.0f%%. Stenger.",
                        state.signal_id,
                        state.peak_progress * 100,
                        progress * 100,
                    )
                    self._close_all(state, close, "GIVE-BACK")
                    remove.append(state)
                    continue

            # ── P4: EMA9-kryss (post-T1) ──────────────────────
            ema9_exit_enabled = gp.ema9_exit
            if hcfg.get("exit_ema_tf") == "D1":
                ema9_exit_enabled = False  # D1-EMA ikke implementert
            reconcile_grace = 3 if state.reconciled else 0
            if (
                state.t1_price_reached
                and ema_c
                and ema9_exit_enabled
                and state.candles_since_entry > reconcile_grace
            ):
                ema_crossed = close > ema_c if is_sell else close < ema_c
                if ema_crossed:
                    log.info("[EMA9 KRYSS] %s — stenger rest.", state.signal_id)
                    self._close_all(state, close, "EMA9")
                    remove.append(state)
                    continue

            # ── P5a: Timeout ──────────────────────────────────
            exp = state.expiry_candles
            timeout_partial_pct = hcfg.get("exit_timeout_partial_pct", 0.50)
            if not state.t1_price_reached and state.candles_since_entry >= exp:
                if progress > timeout_partial_pct:
                    base_trail = self._resolve_trail_mult(state, hcfg, rules, gp)
                    log.info(
                        "[TIMEOUT] %s — progress=%.0f%% > %.0f%%. Aktiverer trailing, gir mer tid.",
                        state.signal_id,
                        progress * 100,
                        timeout_partial_pct * 100,
                    )
                    state.trail_active = True
                    self._update_trail(state, close, symbol_id, base_trail * (2 / 3))
                elif progress > 0.0:
                    log.info(
                        "[8-CANDLE] %s — progress=%.0f%% marginalt. Stenger.",
                        state.signal_id,
                        progress * 100,
                    )
                    self._close_all(state, close, "8-CANDLE-MARGINAL")
                    remove.append(state)
                    continue
                else:
                    log.info(
                        "[8-CANDLE] %s — progress=%.0f%% i tap. Stenger.",
                        state.signal_id,
                        progress * 100,
                    )
                    self._close_all(state, close, "8-CANDLE-LOSS")
                    remove.append(state)
                    continue

            # ── P5b: Hard close ───────────────────────────────
            if state.candles_since_entry >= exp * 2:
                log.info("[16-CANDLE] %s — hard close.", state.signal_id)
                self._close_all(state, close, "16-CANDLE")
                remove.append(state)
                continue

        for s in remove:
            if s in self._active_states:
                self._active_states.remove(s)

    # ─────────────────────────────────────────────────────────
    # Helpers: weekend, progress, trail, BE, close-volume
    # ─────────────────────────────────────────────────────────

    def _weekend_action(self) -> dict[str, bool]:
        """Fredag-lukkevindu CET: 19-20 strammer SL, ≥20 lukker SCALP.

        Portert fra `trading_bot.py:_weekend_action` (1750-1760).
        """
        now = datetime.now(CET)
        if now.weekday() != 4:
            return {"close_scalp": False, "tighten_sl": False}
        if now.hour >= 20:
            return {"close_scalp": True, "tighten_sl": True}
        if now.hour >= 19:
            return {"close_scalp": False, "tighten_sl": True}
        return {"close_scalp": False, "tighten_sl": False}

    def _compute_weekend_sl(self, state: TradeState, close: float, atr: float) -> float | None:
        """Returnerer strammere weekend-SL (mult×ATR fra nåpris), eller None
        hvis ny SL ikke er strammere enn nåværende. Portert fra
        `trading_bot.py:_compute_weekend_sl` (1762-1773)."""
        if not atr:
            return None
        mult = self._config.weekend.sl_atr_mult
        if state.direction == "sell":
            new_sl = close + mult * atr
            return round(new_sl, 5) if new_sl < state.stop_price else None
        new_sl = close - mult * atr
        return round(new_sl, 5) if new_sl > state.stop_price else None

    def _compute_progress(self, state: TradeState, close: float) -> float:
        """Fremgang mot T1: 0.0=entry, 1.0=T1-nådd, negativ=mot SL.
        Portert fra `trading_bot.py:_compute_progress` (2604-2615)."""
        if not state.t1_price or state.t1_price == state.entry_price:
            return 0.0
        t1_dist = abs(state.t1_price - state.entry_price)
        if state.direction == "buy":
            return (close - state.entry_price) / t1_dist
        return (state.entry_price - close) / t1_dist

    def _update_trail(self, state: TradeState, close: float, symbol_id: int, mult: float) -> None:
        """Ratchet trail-level og send amend til cTrader hvis forbedret.
        Portert fra `trading_bot.py:_update_trail` (2617-2659)."""
        horizon = state.horizon or "SCALP"
        if horizon in ("SWING", "MAKRO"):
            atr = self._entry.get_atr14_h1(symbol_id) or self._entry.get_atr14(symbol_id) or 0.0
        else:
            atr = self._entry.get_atr14(symbol_id) or 0.0
        if not atr:
            return
        trail_dist = mult * atr
        pd = self._client.symbol_price_digits.get(symbol_id, 5)

        if state.direction == "buy":
            new_trail = round(close - trail_dist, pd)
            if state.trail_level is None or new_trail > state.trail_level:
                state.trail_level = new_trail
        else:
            new_trail = round(close + trail_dist, pd)
            if state.trail_level is None or new_trail < state.trail_level:
                state.trail_level = new_trail

        # M10: Advar hvis trail betydelig overskriver reconciled-SL
        if state.reconciled and state.reconciled_sl and atr and state.trail_level is not None:
            divergence = abs(state.trail_level - state.reconciled_sl)
            if divergence > atr and not getattr(state, "_m10_trail_logged", False):
                log.warning(
                    "[M10] %s — trail overskriver reconciled-SL %.5f → %.5f "
                    "(avvik %.5f > 1×ATR). Logger én gang per state.",
                    state.signal_id,
                    state.reconciled_sl,
                    state.trail_level,
                    divergence,
                )
                state._m10_trail_logged = True  # type: ignore[attr-defined]

        # state.position_id er Optional[int] under konstruksjon, men er
        # garantert satt før vi trail-er SL (kalles kun fra T1-/M10-logikk
        # som krever åpen posisjon).
        assert state.position_id is not None
        self._client.amend_sl_tp(position_id=state.position_id, stop_loss=state.trail_level)

    def _set_break_even(self, state: TradeState, symbol_id: int) -> None:
        """Flytt SL til break-even + ATR-buffer (post-T1).
        Portert fra `trading_bot.py:_set_break_even` (2531-2584)."""
        rules = (self._entry.signal_data or {}).get("rules", {})
        gp = (
            self._config.group_params.get(get_group_name(state.instrument or ""))
            or self._config.group_params["fx"]
        )
        ratio = rules.get("be_buffer_atr_ratio", gp.be_atr)
        atr = self._entry.get_atr14(symbol_id) or 0.0
        spread = self._client.last_ask.get(symbol_id, 0) - self._client.last_bid.get(symbol_id, 0)
        buffer_ = spread + ratio * atr

        if state.direction == "sell":
            be_stop = state.entry_price + buffer_
        else:
            be_stop = state.entry_price - buffer_

        pd = self._client.symbol_price_digits.get(symbol_id, 5)
        pip_size = 10**-pd
        be_stop = round(be_stop, pd)

        bid = self._client.last_bid.get(symbol_id, 0)
        ask = self._client.last_ask.get(symbol_id, 0)
        if state.direction == "buy" and bid and be_stop >= bid:
            be_stop = round(bid - pip_size, pd)
        if state.direction == "sell" and ask and be_stop <= ask:
            be_stop = round(ask + pip_size, pd)

        # Flytt kun hvis bedre enn nåværende SL
        if state.direction == "sell" and state.stop_price and be_stop >= state.stop_price:
            return
        if state.direction == "buy" and state.stop_price and be_stop <= state.stop_price:
            return

        # M10: Advar hvis BE betydelig overskriver reconciled-SL
        if state.reconciled and state.reconciled_sl:
            atr_cmp = atr or 1.0
            divergence = abs(be_stop - state.reconciled_sl)
            if divergence > atr_cmp:
                log.warning(
                    "[M10] %s — BE overskriver reconciled-SL %.5f → %.5f "
                    "(avvik %.5f > 1×ATR). Verifiser manuelt satt broker-SL.",
                    state.signal_id,
                    state.reconciled_sl,
                    be_stop,
                    divergence,
                )

        # state.position_id satt før BE-flytting (krever åpen posisjon).
        assert state.position_id is not None
        self._client.amend_sl_tp(position_id=state.position_id, stop_loss=be_stop)
        state.stop_price = be_stop
        log.info(
            "[BE] %s — stop til %s (buffer=%.5f spread=%.5f atr=%.5f)",
            state.signal_id,
            be_stop,
            buffer_,
            spread,
            atr,
        )

    def _calc_close_volume(self, state: TradeState, fraction: float) -> tuple[int, int]:
        """Returnerer (close_volume, remaining). Hvis remaining < min_volume:
        steng hele. Portert fra `trading_bot.py:_calc_close_volume` (2586-2602)."""
        info = self._client.symbol_info.get(state.symbol_id, {})
        min_vol = info.get("min_volume", 1) or 1
        step = info.get("step_volume", min_vol) or min_vol

        desired = int(state.remaining_volume * fraction)
        desired = (desired // step) * step
        desired = max(desired, min_vol)

        remaining = state.remaining_volume - desired
        if remaining < min_vol:
            return (state.remaining_volume, 0)
        return (desired, remaining)

    def _resolve_trail_mult(
        self,
        state: TradeState,
        hcfg: dict[str, Any],
        rules: dict[str, Any],
        gp: Any,
    ) -> float:
        """horizon_config.exit_trail_atr_mult[group] overstyrer
        rules.trail_atr_multiplier som overstyrer gp.trail_atr."""
        instr_group = INSTRUMENT_GROUP.get(state.instrument or "", "fx")
        trail_atr_map = hcfg.get("exit_trail_atr_mult", {}) or {}
        return trail_atr_map.get(instr_group, rules.get("trail_atr_multiplier", gp.trail_atr))

    def _close_all(self, state: TradeState, close_price: float, reason: str) -> None:
        """Lukk hele resten av posisjonen og logg. position_id må være satt."""
        if state.position_id is not None:
            self._client.close_position(
                position_id=state.position_id, volume=state.remaining_volume
            )
        self._log_trade_closed(state, reason, close_price)

    # ─────────────────────────────────────────────────────────
    # PnL-beregning (estimert, overskrives av cTrader-deal hvis mulig)
    # ─────────────────────────────────────────────────────────

    def _calc_pnl(self, state: TradeState, close_price: float) -> dict[str, Any]:
        """Estimert PnL i USD + pips. Portert fra
        `trading_bot.py:_calc_pnl` (1896-1959).

        Fallback til siste bid/ask hvis close_price=0."""
        if not state.entry_price:
            return {}
        if not close_price:
            close_price = self._client.last_bid.get(
                state.symbol_id, 0
            ) or self._client.last_ask.get(state.symbol_id, 0)
        if not close_price:
            return {}

        instr = state.instrument or ""
        direction_mult = 1 if state.direction == "buy" else -1
        price_diff = (close_price - state.entry_price) * direction_mult
        pd = self._client.symbol_price_digits.get(state.symbol_id, 5)
        pip_size = _PIP_MAP.get(pd, 0.01)
        pips = round(price_diff / pip_size, 1) if pip_size else 0

        vol = (state.remaining_volume or 0) / 100.0
        if instr in _USD_BASE:
            pnl_usd = round(price_diff * vol / close_price, 2) if close_price else 0.0
        else:
            pnl_usd = round(price_diff * vol, 2)

        # Trekk fra halv-spread (entry) — real commission legges til hvis registrert
        spread = getattr(state, "_entry_spread", 0) or 0
        if spread and vol:
            if instr in _USD_BASE:
                spread_cost = round(spread * vol / close_price, 4) if close_price else 0
            else:
                spread_cost = round(spread * vol, 4)
            pnl_usd = round(pnl_usd - spread_cost, 2)

        commission = getattr(state, "_real_commission", 0) or 0
        if commission:
            pnl_usd = round(pnl_usd + commission, 2)  # commission negativ

        return {
            "close_price": round(close_price, pd),
            "pips": pips,
            "pnl_usd": pnl_usd,
        }

    # ─────────────────────────────────────────────────────────
    # Trade-close-logging + reconcile-logging
    # ─────────────────────────────────────────────────────────

    def _log_trade_closed(self, state: TradeState, reason: str, close_price: float = 0.0) -> None:
        """Oppdater siste åpne entry for signal-id med close-data + PnL.

        Portert fra `trading_bot.py:_log_trade_closed` (1961-2008), men
        UTEN `_git_push_log`-kall. Akkumulerer daily_loss via
        `SafetyMonitor.add_loss` ved negativ PnL.
        """
        try:
            if not self._trade_log_path.exists():
                return
            data = json.loads(self._trade_log_path.read_text(encoding="utf-8"))
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M timezone.utc")
            pnl = self._calc_pnl(state, close_price)
            real = getattr(state, "_real_pnl", None)
            if real is not None and pnl:
                pnl["pnl_usd"] = real
                pnl["pnl_real"] = True
            pnl_val = pnl.get("pnl_usd", 0) if pnl else 0
            if reason in ("GEO-SPIKE", "KILL", "SL"):
                result = "loss"
            elif pnl_val > 0:
                result = "win"
            elif pnl_val < 0:
                result = "loss"
            else:
                result = "managed"
            for e in data.get("entries", []):
                if e.get("signal", {}).get("id") == state.signal_id and e.get("result") is None:
                    e["closed_at"] = now
                    e["result"] = result
                    e["exit_reason"] = reason
                    if pnl:
                        e["pnl"] = pnl
                    break
            data["last_updated"] = now
            self._atomic_write_json(data)
            real_tag = " [cTrader]" if pnl.get("pnl_real") else " [est]"
            pnl_str = (
                f"  {pnl['pnl_usd']:+.2f} USD ({pnl['pips']:+.1f} pips){real_tag}" if pnl else ""
            )
            log.info(
                "[TRADE-LOG] %s stengt: %s (%s)%s",
                state.signal_id,
                result,
                reason,
                pnl_str,
            )
            if pnl and pnl.get("pnl_usd", 0) < 0:
                self._safety.add_loss(abs(pnl["pnl_usd"]))
                log.info(
                    "[DAGLIG TAP] Akkumulert: %.0f",
                    self._safety.daily_loss,
                )
        except Exception as exc:
            log.warning("[TRADE-LOG] Lukking feilet: %s", exc)

    def _log_reconcile_opened(self, state: TradeState) -> None:
        """Legg til RECONCILE-state i signal_log hvis ikke allerede der.
        Portert fra `trading_bot.py:_log_reconcile_opened` (1847-1884)."""
        try:
            if self._trade_log_path.exists():
                data = json.loads(self._trade_log_path.read_text(encoding="utf-8"))
            else:
                data = {"entries": []}
            for e in data.get("entries", []):
                if e.get("signal", {}).get("id") == state.signal_id and e.get("result") is None:
                    log.info(
                        "[TRADE-LOG] %s allerede i logg (reconcile)",
                        state.signal_id,
                    )
                    return
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M timezone.utc")
            entry = {
                "timestamp": now,
                "closed_at": None,
                "result": None,
                "exit_reason": None,
                "signal": {
                    "id": state.signal_id,
                    "instrument": state.instrument or state.signal_id,
                    "direction": state.direction.upper(),
                    "entry": round(state.entry_price, 5),
                    "stop": round(state.stop_price, 5),
                    "t1": None,
                    "position_id": state.position_id,
                    "lots": volume_to_lots(
                        state.full_volume,
                        self._client.symbol_info.get(state.symbol_id),
                    ),
                    "risk_pct": None,
                    "reconciled": True,
                },
            }
            data["entries"] = [entry, *data.get("entries", [])]
            # Pyright smal-typer data-verdi til list[Unknown] etter forrige
            # tilordning; reell type er dict[str, Any] (json-blob).
            data["last_updated"] = now  # pyright: ignore[reportArgumentType]
            self._atomic_write_json(data)
            log.info("[TRADE-LOG] %s lagt til via reconcile", state.signal_id)
        except Exception as exc:
            log.warning("[TRADE-LOG] Reconcile-logging feilet: %s", exc)

    def _atomic_write_json(self, data: dict[str, Any]) -> None:
        """Atomisk skriving av signal_log.json via tempfile + os.replace."""
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

    # ─────────────────────────────────────────────────────────
    # cTrader event-handlere (wires to CtraderCallbacks)
    # ─────────────────────────────────────────────────────────

    def on_execution(self, event: Any) -> None:
        """ORDER_FILLED / PARTIAL / deal-close. Portert fra
        `trading_bot.py:_on_execution` (2074-2180)."""
        # Deal-info: lagre commission, evt. gross/swap/commission fra close
        if event.HasField("deal"):
            deal = event.deal
            log.info(
                "[DEAL] dealId=%s posId=%s dealStatus=%s moneyDigits=%s commission=%s",
                getattr(deal, "dealId", "?"),
                getattr(deal, "positionId", "?"),
                getattr(deal, "dealStatus", "?"),
                getattr(deal, "moneyDigits", "?"),
                getattr(deal, "commission", "?"),
            )
            commission = getattr(deal, "commission", None)
            money_digits = getattr(deal, "moneyDigits", 2)
            if commission is not None and money_digits:
                comm_real = round(commission / (10**money_digits), 4)
                pos_id = getattr(deal, "positionId", None)
                if pos_id and comm_real != 0:
                    matched = next(
                        (s for s in self._active_states if s.position_id == pos_id),
                        None,
                    )
                    if matched is not None:
                        matched._real_commission = (  # type: ignore[attr-defined]
                            getattr(matched, "_real_commission", 0.0) + comm_real
                        )
                        log.info(
                            "[DEAL] Kommisjon: %s USD for pos #%s",
                            comm_real,
                            pos_id,
                        )
            if deal.HasField("closePositionDetail"):
                cpd = deal.closePositionDetail
                gross = getattr(cpd, "grossProfit", None)
                if gross is not None:
                    pnl_real = round(gross / (10**money_digits), 2)
                    swap = getattr(cpd, "swap", 0) or 0
                    swap_real = round(swap / (10**money_digits), 4) if swap else 0
                    comm_cpd = getattr(cpd, "commission", 0) or 0
                    comm_real2 = round(comm_cpd / (10**money_digits), 4) if comm_cpd else 0
                    net_real = round(pnl_real + swap_real + comm_real2, 2)
                    pos_id = getattr(deal, "positionId", None)
                    if pos_id:
                        matched = next(
                            (s for s in self._active_states if s.position_id == pos_id),
                            None,
                        )
                        if matched is not None:
                            matched._real_pnl = (  # type: ignore[attr-defined]
                                getattr(matched, "_real_pnl", 0.0) + net_real
                            )
                            log.info(
                                "[DEAL-CLOSE] Real PnL: gross=%s swap=%s comm=%s "
                                "net=%s for pos #%s",
                                pnl_real,
                                swap_real,
                                comm_real2,
                                net_real,
                                pos_id,
                            )

        if not event.HasField("position"):
            return
        pos = event.position
        label = pos.tradeData.label if pos.HasField("tradeData") else ""
        if not label.startswith("SE-"):
            return
        sig_id = label[3:]
        state = next((s for s in self._active_states if s.signal_id == sig_id), None)
        if state is None:
            return
        if state.phase == TradePhase.IN_TRADE:
            return  # duplikat-event

        state.position_id = pos.positionId
        state.phase = TradePhase.IN_TRADE
        # M1: Bruk faktisk filled volume (kan være < full_volume ved partial)
        filled: int | None = None
        if event.HasField("deal"):
            d = event.deal
            filled = getattr(d, "filledVolume", None) or getattr(d, "volume", None)
        if filled and filled < state.full_volume:
            log.warning(
                "[PARTIAL-FILL] %s — fikk %d/%d (%.1f%%). Fortsetter med "
                "faktisk volum; risiko = mindre enn planlagt.",
                sig_id,
                filled,
                state.full_volume,
                filled / state.full_volume * 100,
            )
            state.full_volume = filled
            state.remaining_volume = filled
        elif filled:
            state.remaining_volume = filled
        else:
            state.remaining_volume = state.full_volume

        bid = self._client.last_bid.get(state.symbol_id, 0)
        ask = self._client.last_ask.get(state.symbol_id, 0)
        state._entry_spread = (  # type: ignore[attr-defined]
            round(ask - bid, 6) if bid and ask else 0
        )
        log.info(
            "[UTFØRT] %s — posisjon #%d åpnet (vol=%d spread=%s)",
            sig_id,
            pos.positionId,
            state.remaining_volume,
            getattr(state, "_entry_spread", 0),
        )

        # LIMIT har SL/TP allerede på ordren; MARKET må ammendes
        is_limit = state.order_id is not None and state.order_id != 0
        if not is_limit:
            pd = self._client.symbol_price_digits.get(state.symbol_id, 5)
            sl = round(state.stop_price, pd)
            tp = round(state.t1_price, pd) if state.t1_price > 0 else None
            self._client.amend_sl_tp(position_id=pos.positionId, stop_loss=sl, take_profit=tp)
            log.info("[AMEND] SL=%s TP=%s (digits=%d)", sl, tp if tp else 0, pd)
        else:
            log.info("[LIMIT FILL] SL/TP allerede satt på limit order")

        # Trade-log-åpning eies av EntryEngine (hot-path)
        self._entry._log_trade_opened(state)

    def on_order_error(self, event: Any) -> None:
        """Ordre-feil. POSITION_NOT_FOUND → detekter TP/SL eksternt lukket.
        Portert fra `trading_bot.py:_on_order_error` (2182-2215)."""
        code = getattr(event, "errorCode", "?")
        desc = getattr(event, "description", "?")
        log.error("[ORDRE FEIL] %s (kode %s)", desc, code)
        with self._lock:
            if code == "POSITION_NOT_FOUND":
                closed = [s for s in list(self._active_states) if s.phase == TradePhase.IN_TRADE]
                for s in closed:
                    is_tp = s.t1_price_reached
                    if not is_tp and s.t1_price:
                        bid = self._client.last_bid.get(s.symbol_id, 0)
                        ask = self._client.last_ask.get(s.symbol_id, 0)
                        last_price = bid or ask or 0.0
                        if last_price:
                            dist_t1 = abs(last_price - s.t1_price)
                            dist_stop = (
                                abs(last_price - s.stop_price) if s.stop_price else float("inf")
                            )
                            if dist_t1 < dist_stop:
                                is_tp = True
                    reason = "TP" if is_tp else "SL"
                    exit_prc = s.t1_price if is_tp else s.stop_price
                    log.info(
                        "[STENGT EKSTERNT] %s — %s truffet. Fjerner.",
                        s.signal_id,
                        reason,
                    )
                    self._log_trade_closed(s, reason, exit_prc)
                    if s in self._active_states:
                        self._active_states.remove(s)
                return
            # Rydd stuck states (aldri fikk posisjon)
            stuck = [
                s
                for s in list(self._active_states)
                if s.phase != TradePhase.IN_TRADE and s.position_id is None and s.entry_price > 0
            ]
            for s in stuck:
                log.warning("[ORDRE FEIL] Fjerner stuck state: %s", s.signal_id)
                if s in self._active_states:
                    self._active_states.remove(s)

    def on_reconcile(self, res: Any) -> None:
        """Ta over åpne SE-posisjoner ved oppstart.
        Portert fra `trading_bot.py:_on_reconcile` (2235-2298)."""
        log.info("[RECONCILE] %d åpne posisjoner funnet.", len(res.position))
        for pos in res.position:
            label = pos.tradeData.label if pos.HasField("tradeData") else ""
            log.info("  → #%s %s", pos.positionId, label)
            if not label.startswith("SE-"):
                continue
            sym_id = pos.tradeData.symbolId if pos.HasField("tradeData") else None
            if not sym_id:
                continue
            if any(s.position_id == pos.positionId for s in self._active_states):
                continue

            direction = "sell" if pos.tradeData.tradeSide == 2 else "buy"
            stop = pos.stopLoss if pos.stopLoss else 0.0
            tp = pos.takeProfit if pos.takeProfit else 0.0
            entry = pos.price if pos.price else 0.0
            has_tp = tp > 0.0
            vol = pos.tradeData.volume if pos.HasField("tradeData") else 0

            state = TradeState(
                signal_id=label[3:],
                position_id=pos.positionId,
                phase=TradePhase.IN_TRADE,
                entry_price=entry,
                stop_price=stop,
                t1_price=tp,
                full_volume=vol,
                remaining_volume=vol,
                direction=direction,
                symbol_id=sym_id,
                expiry_candles=32,
                t1_hit=not has_tp,
                t1_price_reached=not has_tp,
            )
            instr_name = next(
                (k for k, v in self._client.symbol_map.items() if v == sym_id),
                label[3:].split("-")[0],
            )
            state.instrument = instr_name
            state.reconciled = True
            state.reconciled_sl = stop
            state.reconciled_tp = tp

            self._active_states.append(state)
            tp_str = f"T1={tp:.5f}" if has_tp else "T1=ukjent"
            log.info(
                "[RECONCILE] Tok over posisjon %s #%d %s @ %.5f SL=%.5f %s",
                label,
                pos.positionId,
                direction,
                entry,
                stop,
                tp_str,
            )
            self._log_reconcile_opened(state)
