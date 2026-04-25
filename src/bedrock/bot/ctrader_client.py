"""cTrader Open API transport-lag for Bedrock trading-bot.

Portert fra `~/scalp_edge/trading_bot.py` session 41 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.1 + 8 punkt 2`). Null
logikk-endring utover:

- Credentials injiseres via konstruktør (i stedet for modul-level env)
- AGRI-symbol-dump bruker Bedrock-sti (`~/bedrock/data/bot/...`) istedenfor
  gammel `~/cot-explorer/data/prices/`. Dette er ikke logikk — det er
  output-plassering, og flytting er nødvendig fordi cot-explorer ikke
  eksisterer som referanse-plass i Bedrock
- Reconnect-budsjett leses fra `StartupOnlyConfig.reconnect` i stedet
  for modul-konstanter
- Callbacks injiseres; transport-laget eier ikke trade-state

Ansvaret:
- Twisted reactor + cTrader Client-livsløp (connect, dispatch, reconnect)
- Protobuf-dispatching til per-payloadType handlers
- Auth-sekvens (app-auth → account-auth → trader-info → symbols-list)
- Symbol-tracking: symbol_map, digits, pip, lot-info, bid/ask, spread-historikk
- Watchdog + heartbeat
- Subscribe-spots + live-trendbar + historical-bars-throttling

Ikke-ansvar (kommer i senere sessions):
- Candle-buffere, EMA/ATR — session 43 (`bot/entry.py`)
- Signal-fetch, price-push — session 42 (`bot/comms.py`)
- Daily-loss, kill-switch — session 42 (`bot/safety.py`)
- Trade-execution, exit-logikk — session 43-44

Callbacks (alle valgfrie, default = no-op):
- `on_spot(event)` — etter at bid/ask/spread er oppdatert internt
- `on_historical_bars(res)` — 15m eller 1h candles fra bootstrap
- `on_execution(event)` — fill/partial/reject
- `on_order_error(event)` — ordrefeil
- `on_error_res(event)` — generell ProtoOAErrorRes
- `on_reconcile(res)` — åpne posisjoner ved oppstart
- `on_symbols_ready(client)` — kalt én gang etter symbols-list er
  prosessert og symbol_map er populert. Bot populerer candle-buffere
  her. Kalles FØR subscribe-spots har begynt å fyre events
- `on_trader_info(balance)` — konto-balanse i kontovaluta
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
    ProtoHeartbeatEvent,
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOACancelOrderReq,
    ProtoOAClosePositionReq,
    ProtoOAErrorRes,
    ProtoOAExecutionEvent,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOANewOrderReq,
    ProtoOAOrderErrorEvent,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOASpotEvent,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOAOrderType,
    ProtoOATradeSide,
    ProtoOATrendbarPeriod,
)
from twisted.internet import reactor, task

from bedrock.bot.config import StartupOnlyConfig
from bedrock.bot.instruments import (
    AGRI_INSTRUMENTS,
    INSTRUMENT_MAP,
    PRICE_FEED_MAP,
)

log = logging.getLogger("bedrock.bot.ctrader")

# ─────────────────────────────────────────────────────────────
# Konstanter — protobuf-enums, fatal-koder
# ─────────────────────────────────────────────────────────────

M15_PERIOD = ProtoOATrendbarPeriod.Value("M15")
M5_PERIOD = ProtoOATrendbarPeriod.Value("M5")
H1_PERIOD = ProtoOATrendbarPeriod.Value("H1")

# cTrader Open API error-koder som indikerer død token / auth-feil.
# Ved disse skal boten FATAL-exite i stedet for å gå i evig reconnect-loop
AUTH_FATAL_ERROR_CODES: frozenset[str] = frozenset(
    {
        "CH_CLIENT_AUTH_FAILURE",
        "CH_ACCESS_TOKEN_INVALID",
        "ACCESS_TOKEN_EXPIRED",
        "CH_ACCESS_TOKEN_EXPIRED",
        "OA_AUTH_TOKEN_EXPIRED",
        "CH_ACCOUNT_NOT_AUTHORIZED",
        "NOT_AUTHENTICATED",
    }
)

# AGRI-symbol-info dump-sti (flyttet fra ~/cot-explorer/data/prices/ til
# Bedrock-repoet så vi ikke skriver utenfor repo-tre).
AGRI_SYMBOL_INFO_PATH = Path.home() / "bedrock" / "data" / "bot" / "agri_symbol_info.json"

# Watchdog-terskler (sekunder)
_WATCHDOG_RECONNECT_SEC = 300  # 5 min uten spot → reconnect
_WATCHDOG_WARN_SEC = 180  # 3 min → varsle
_WATCHDOG_GLOBAL_FRESH_SEC = 120  # per-symbol silence kun hvis global fersk
_SYMBOL_SILENCE_THRESHOLD_SEC = 1800  # 30 min — ikke-agri
_SYMBOL_SILENCE_AGRI_THRESHOLD_SEC = 7200  # 2 t — agri har naturlig off-hours

# Heartbeat og watchdog-intervall (cTrader API-krav, ikke konfigurerbart)
_HEARTBEAT_INTERVAL_SEC = 25
_WATCHDOG_INTERVAL_SEC = 30


# ─────────────────────────────────────────────────────────────
# Callbacks — injiseres fra orchestrator/bot-laget
# ─────────────────────────────────────────────────────────────


def _noop(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
    pass


@dataclass
class CtraderCallbacks:
    """Alle callbacks som transport-laget kan utløse. Default = no-op
    slik at testing og trinnvis integrasjon blir enkelt.

    Callbacks kalles i Twisted reactor-tråden; de må være raske. Tyngre
    prosessering bør legges i task.deferLater eller lignende.
    """

    on_spot: Callable[[Any], None] = _noop
    on_historical_bars: Callable[[Any], None] = _noop
    on_execution: Callable[[Any], None] = _noop
    on_order_error: Callable[[Any], None] = _noop
    on_error_res: Callable[[Any], None] = _noop
    on_reconcile: Callable[[Any], None] = _noop
    # Kalt etter _on_symbols_list har populert symbol_map + lookup-dicts,
    # men FØR subscribe-spots begynner. Bot initialiserer candle-buffere her.
    on_symbols_ready: Callable[[CtraderClient], None] = _noop
    on_trader_info: Callable[[float], None] = _noop


# ─────────────────────────────────────────────────────────────
# CtraderClient
# ─────────────────────────────────────────────────────────────


@dataclass
class CtraderCredentials:
    """cTrader OAuth-credentials. Lastes fra env i `bot/__main__.py`."""

    client_id: str
    client_secret: str
    access_token: str
    account_id: int


class CtraderClient:
    """Transport-wrapper rundt cTrader Open API Client.

    Instansieres én gang per bot-prosess. Eier Twisted-client,
    symbol-lookup-state, bid/ask, spread-historikk, reconnect-budsjett,
    heartbeat og watchdog.

    Callbacks injiseres via `CtraderCallbacks` — bot-laget registrerer
    handlers som muterer handel-state (candle-buffere, trade-states, osv.).
    """

    def __init__(
        self,
        *,
        credentials: CtraderCredentials,
        demo: bool,
        startup_config: StartupOnlyConfig,
        callbacks: CtraderCallbacks | None = None,
    ) -> None:
        self._creds = credentials
        self._demo = demo
        self._startup = startup_config
        self._callbacks = callbacks or CtraderCallbacks()

        self.client: Client | None = None

        # Symbol-lookup og -info — eid av transport
        self.symbol_map: dict[str, int] = {}  # instrument-navn → symbol_id
        self.symbol_digits: dict[int, int] = {}  # symbol_id → 5 (fast)
        self.symbol_price_digits: dict[int, int] = {}  # symbol_id → SL/TP-desimaler
        self.symbol_pip: dict[int, float] = {}
        self.symbol_info: dict[int, dict[str, Any]] = {}
        self.price_feed_sids: dict[str, int] = {}  # prices-nøkkel → symbol_id

        # Live-priser og spread
        self.last_bid: dict[int, float] = {}
        self.last_ask: dict[int, float] = {}
        self.spread_history: dict[int, deque[float]] = {}

        # Konto-info
        self.account_balance: float = 0.0

        # Reconnect-budsjett
        self._reconnect_times: list[float] = []
        self._reconnecting: bool = False

        # Watchdog
        self._last_spot_time: float | None = None
        self._last_spot_per_sid: dict[int, float] = {}
        self._symbol_silent_logged: set[int] = set()
        self._heartbeat_loop: task.LoopingCall | None = None
        self._watchdog_loop: task.LoopingCall | None = None

        # Pending requests (clientMsgId → type) — for debug
        self._pending_requests: dict[str, str] = {}
        self._lock = Lock()

    # ─────────────────────────────────────────────────────────
    #  Oppstart
    # ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Instansier cTrader-klient og start reactor.

        NB: `reactor.run()` blokkerer. Entry-point i `bot/__main__.py`
        er ansvarlig for å registrere signal-handlers (SIGHUP/SIGTERM)
        før denne kalles.
        """
        endpoint = EndPoints.PROTOBUF_DEMO_HOST if self._demo else EndPoints.PROTOBUF_LIVE_HOST
        log.info("═══════════════════════════════════════")
        log.info("  Bedrock trading bot (cTrader transport)")
        log.info("  Modus: %s", "DEMO" if self._demo else "⚠️ LIVE")
        log.info("  Server: %s:%s", endpoint, EndPoints.PROTOBUF_PORT)
        log.info("═══════════════════════════════════════")

        self.client = Client(endpoint, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

        self._heartbeat_loop = task.LoopingCall(self._send_heartbeat)

        reactor.run()  # type: ignore[attr-defined]

    # ─────────────────────────────────────────────────────────
    #  Tilkobling + reconnect
    # ─────────────────────────────────────────────────────────

    def _on_connected(self, client: Client) -> None:
        log.info("[TILKOBLET] Autentiserer applikasjon...")
        self._reconnecting = False
        if self._heartbeat_loop is not None and not self._heartbeat_loop.running:
            self._heartbeat_loop.start(_HEARTBEAT_INTERVAL_SEC)
        if self._watchdog_loop is None or not self._watchdog_loop.running:
            self._watchdog_loop = task.LoopingCall(self._watchdog_check)
            self._watchdog_loop.start(_WATCHDOG_INTERVAL_SEC, now=False)
        req = ProtoOAApplicationAuthReq()
        req.clientId = self._creds.client_id
        req.clientSecret = self._creds.client_secret
        self.send(req)

    def _on_disconnected(self, client: Client, reason: Any) -> None:
        log.warning("[FRAKOBLET] %s — prøver igjen om 10 sek...", reason)
        rc = self._startup.reconnect
        now = time.time()
        # Rydd opp timestamps utenfor vinduet
        self._reconnect_times = [t for t in self._reconnect_times if now - t < rc.window_sec]
        self._reconnect_times.append(now)
        if len(self._reconnect_times) > rc.max_in_window:
            log.error(
                "[FATAL] %d reconnect-forsøk på %ds — indikerer vedvarende "
                "auth/network problem. Avslutter for å unngå evig loop med "
                "åpen posisjon.",
                len(self._reconnect_times),
                rc.window_sec,
            )
            self._fatal_exit(79)
            return
        reactor.callLater(10, self.client.startService)  # type: ignore[attr-defined,union-attr]

    def _fatal_exit(self, code: int = 78) -> None:
        """Stopp reactor og avslutt prosessen med feilkode.

        Signalerer til systemd / operatør at botrestart med nye credentials
        kreves. Ikke bruk for forbigående feil.
        """
        try:
            if reactor.running:  # type: ignore[attr-defined]
                reactor.callLater(0, reactor.stop)  # type: ignore[attr-defined]
        except Exception as e:
            log.warning("[FATAL] reactor.stop feilet: %s", e)

        def _hard_exit() -> None:
            sys.exit(code)

        reactor.callLater(2, _hard_exit)  # type: ignore[attr-defined]

    # ─────────────────────────────────────────────────────────
    #  Meldings-dispatcher
    # ─────────────────────────────────────────────────────────

    def _on_message(self, client: Client, message: Any) -> None:
        msg_type = message.payloadType
        handler = self._handlers().get(msg_type)
        if handler is not None:
            handler(Protobuf.extract(message))
        else:
            log.info("[MELDING] Uhåndtert type: %s", msg_type)

    def _handlers(self) -> dict[int, Callable[[Any], None]]:
        """Bygg dispatcher-mapping. Instansierer engang per kall; billig
        nok, og unngår å holde instanser av prototype-meldinger i live
        når klassen instansieres (noen tester bygger CtraderClient uten
        ctrader-open-api-import å skape)."""
        return {
            ProtoOAApplicationAuthRes().payloadType: self._on_app_auth,
            ProtoOAAccountAuthRes().payloadType: self._on_account_auth,
            ProtoOATraderRes().payloadType: self._on_trader_info,
            ProtoOASymbolsListRes().payloadType: self._on_symbols_list,
            ProtoOASymbolByIdRes().payloadType: self._on_symbol_by_id,
            ProtoOASubscribeSpotsRes().payloadType: self._on_subscribe_spots,
            ProtoOASubscribeLiveTrendbarRes().payloadType: _noop,
            ProtoOASpotEvent().payloadType: self._on_spot,
            ProtoOAGetTrendbarsRes().payloadType: self._on_historical_bars,
            ProtoOAExecutionEvent().payloadType: self._on_execution,
            ProtoOAOrderErrorEvent().payloadType: self._on_order_error,
            ProtoOAErrorRes().payloadType: self._on_error_res,
            ProtoOAReconcileRes().payloadType: self._on_reconcile,
            ProtoOAGetAccountListByAccessTokenRes().payloadType: _noop,
            ProtoHeartbeatEvent().payloadType: _noop,
        }

    # ─────────────────────────────────────────────────────────
    #  Public send + spesialiserte sendere
    # ─────────────────────────────────────────────────────────

    def send(self, message: Any, timeout: int = 30) -> Any:
        """Wrapper rundt client.send med stille errback og økt timeout.

        Returnerer Deferred (eller None ved feil). Caller kan
        addCallback/addErrback hvis de trenger resultat.
        """
        if self.client is None:
            log.debug("[SEND] client ikke initialisert — hopper over")
            return None
        try:
            d = self.client.send(message, responseTimeoutInSeconds=timeout)
            d.addErrback(lambda f: None)
            return d
        except Exception as e:
            log.debug("[SEND] Feil: %s", e)
            return None

    def send_reconcile(self) -> None:
        req = ProtoOAReconcileReq()
        req.ctidTraderAccountId = self._creds.account_id
        self.send(req)

    def request_historical_bars(
        self, symbol_id: int, period: int = M15_PERIOD, bars_back: int = 50
    ) -> None:
        """Hent siste `bars_back` lukkede candles for initialisering.

        Default = 50 × 15m candles. For 1H: kall med period=H1_PERIOD.
        """
        now_ms = int(time.time() * 1000)
        # Beregn minutter-per-bar fra period-enum
        period_minutes = {M15_PERIOD: 15, M5_PERIOD: 5, H1_PERIOD: 60}.get(period, 15)
        from_ms = now_ms - bars_back * period_minutes * 60 * 1000
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.symbolId = symbol_id
        req.period = period
        req.fromTimestamp = from_ms
        req.toTimestamp = now_ms
        self.send(req)

    # ─────────────────────────────────────────────────────────
    #  Ordre-APIs (transport-only; state bor i entry/exit-laget)
    # ─────────────────────────────────────────────────────────

    def send_new_order(
        self,
        *,
        symbol_id: int,
        trade_side: str,
        volume: int,
        label: str = "",
        comment: str = "",
        order_type: str = "MARKET",
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expiration_ms: int | None = None,
    ) -> Any:
        """Send ProtoOANewOrderReq. MARKET eller LIMIT.

        `trade_side` er "BUY" | "SELL"; `order_type` er "MARKET" | "LIMIT".
        SL/TP settes direkte på request for LIMIT; MARKET må bruke
        `amend_sl_tp` etter fill (cTrader tillater ikke SL/TP på
        ProtoOANewOrderReq for MARKET).

        `limit_price` er påkrevd for LIMIT; `expiration_ms` valgfri
        (unix ms). Caller er ansvarlig for å avrunde priser til riktig
        digits via `symbol_price_digits`.
        """
        if order_type == "LIMIT" and limit_price is None:
            raise ValueError("send_new_order: LIMIT-ordre krever limit_price")
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.symbolId = symbol_id
        req.tradeSide = ProtoOATradeSide.Value(trade_side)
        req.volume = volume
        if label:
            req.label = label
        if comment:
            req.comment = comment
        req.orderType = ProtoOAOrderType.Value(order_type)
        if order_type == "LIMIT":
            assert limit_price is not None  # håndheves over
            req.limitPrice = limit_price
            if stop_loss is not None:
                req.stopLoss = stop_loss
            if take_profit is not None:
                req.takeProfit = take_profit
            if expiration_ms is not None:
                req.expirationTimestamp = expiration_ms
        return self.send(req)

    def amend_sl_tp(
        self,
        *,
        position_id: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Any:
        """Endre SL og/eller TP på åpen posisjon."""
        req = ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.positionId = position_id
        if stop_loss is not None:
            req.stopLoss = stop_loss
        if take_profit is not None:
            req.takeProfit = take_profit
        return self.send(req)

    def close_position(self, *, position_id: int, volume: int) -> Any:
        """Lukk posisjon helt eller delvis."""
        req = ProtoOAClosePositionReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.positionId = position_id
        req.volume = volume
        return self.send(req)

    def cancel_order(self, *, order_id: int) -> Any:
        """Kanseller pending (typisk LIMIT) ordre."""
        req = ProtoOACancelOrderReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.orderId = order_id
        return self.send(req)

    # ─────────────────────────────────────────────────────────
    #  Autentisering
    # ─────────────────────────────────────────────────────────

    def _on_app_auth(self, res: Any) -> None:
        log.info("[AUTH] Applikasjon autentisert. Logger inn konto...")
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.accessToken = self._creds.access_token
        self.send(req)

    def _on_account_auth(self, res: Any) -> None:
        log.info("[AUTH] Konto %s autentisert", self._creds.account_id)
        req = ProtoOATraderReq()
        req.ctidTraderAccountId = self._creds.account_id
        self.send(req)

    def _on_trader_info(self, res: Any) -> None:
        # Balanse i cent → kontovaluta
        self.account_balance = res.trader.balance / 100.0
        log.info("[KONTO] Balanse: %.2f", self.account_balance)
        self._callbacks.on_trader_info(self.account_balance)
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self._creds.account_id
        req.includeArchivedSymbols = False
        self.send(req)

    # ─────────────────────────────────────────────────────────
    #  Symboler og abonnering
    # ─────────────────────────────────────────────────────────

    def _on_symbols_list(self, res: Any) -> None:
        log.info("[SYMBOLER] Mottok %d symboler", len(res.symbol))

        # Bygg oppslagstabell: ticker → instrument-navn
        ticker_to_instr: dict[str, str] = {}
        for instr_name, candidates in INSTRUMENT_MAP.items():
            for ticker in candidates:
                ticker_to_instr[ticker] = instr_name

        # Spor hvilke tickere per instrument som finnes hos megleren — bot
        # velger første kandidat i INSTRUMENT_MAP, men vi logger ALLE treff
        # slik at duplikat-risiko blir synlig
        found_tickers: dict[str, list[str]] = {}
        for sym in res.symbol:
            instr_name = ticker_to_instr.get(sym.symbolName)
            if not instr_name:
                continue
            found_tickers.setdefault(instr_name, []).append(sym.symbolName)
            if instr_name not in self.symbol_map:
                sid = sym.symbolId
                digits = 5  # cTrader bruker 10^5 skalering
                self.symbol_map[instr_name] = sid
                self.symbol_digits[sid] = digits
                self.symbol_pip[sid] = 10**-digits / 10
                self.spread_history[sid] = deque(maxlen=20)
                log.debug("[SYMBOL] %s → %s (sid=%s)", instr_name, sym.symbolName, sid)

        # Valider INSTRUMENT_MAP-dekning mot megleren
        missing_instruments = [name for name in INSTRUMENT_MAP if name not in self.symbol_map]
        for name in missing_instruments:
            log.warning(
                "[SYMBOL-MAP] %r har ingen match hos megler — signaler for "
                "dette instrumentet blir ignorert. Kandidater prøvd: %s",
                name,
                INSTRUMENT_MAP[name],
            )
        for name, tickers in found_tickers.items():
            if len(tickers) > 1:
                chosen = next((t for t in INSTRUMENT_MAP[name] if t in tickers), tickers[0])
                log.warning(
                    "[SYMBOL-MAP] %r har flere treff hos megler: %s — valgte %r. "
                    "Bekreft at dette er riktig kontraktspec (CFD/future/spot).",
                    name,
                    tickers,
                    chosen,
                )

        total_expected = len(INSTRUMENT_MAP)
        if total_expected > 0:
            missing_ratio = len(missing_instruments) / total_expected
            if missing_ratio > 0.5:
                log.error(
                    "[FATAL] %d/%d instrumenter mangler hos megler (%.0f%%). "
                    "Sannsynlig feilkonfigurert konto eller symbol-rename.",
                    len(missing_instruments),
                    total_expected,
                    missing_ratio * 100,
                )
                self._fatal_exit(80)
                return

        if not self.symbol_map:
            log.error("Ingen symboler funnet! Sjekk INSTRUMENT_MAP mot megler.")
            try:
                reactor.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
            return

        # Pris-feed-symboler (handles ikke, kun bid/ask-tracking)
        all_names = {sym.symbolName: sym.symbolId for sym in res.symbol}
        for price_key, candidates in PRICE_FEED_MAP.items():
            for ticker in candidates:
                if ticker in all_names:
                    sid = all_names[ticker]
                    self.price_feed_sids[price_key] = sid
                    self.symbol_digits[sid] = 5
                    log.info("[PRIS-FEED] %s → %s (sid=%s)", price_key, ticker, sid)
                    break

        # Kall on_symbols_ready FØR subscribe-throttling starter, slik at
        # bot/entry kan populere candle-buffere før første spot-event ankommer
        try:
            self._callbacks.on_symbols_ready(self)
        except Exception:
            log.exception("[CALLBACK] on_symbols_ready feilet — fortsetter")

        # ── Throttle oppstartsforespørsler (cTrader ~5 req/s) ────────────
        STEP = 0.25  # sekunder mellom hvert symbol
        sids = list(self.symbol_map.values())
        n = len(sids)
        account_id = self._creds.account_id

        def _subscribe_symbol(sid: int) -> None:
            req_spot = ProtoOASubscribeSpotsReq()
            req_spot.ctidTraderAccountId = account_id
            req_spot.symbolId.append(sid)
            self.send(req_spot)

            req_bar = ProtoOASubscribeLiveTrendbarReq()
            req_bar.ctidTraderAccountId = account_id
            req_bar.symbolId = sid
            req_bar.period = M15_PERIOD
            self.send(req_bar)

            req_bar5 = ProtoOASubscribeLiveTrendbarReq()
            req_bar5.ctidTraderAccountId = account_id
            req_bar5.symbolId = sid
            req_bar5.period = M5_PERIOD
            self.send(req_bar5)

        def _subscribe_h1(sid: int) -> None:
            req_bar_h1 = ProtoOASubscribeLiveTrendbarReq()
            req_bar_h1.ctidTraderAccountId = account_id
            req_bar_h1.symbolId = sid
            req_bar_h1.period = H1_PERIOD
            self.send(req_bar_h1)

        for i, sid in enumerate(sids):
            reactor.callLater(i * STEP, _subscribe_symbol, sid)  # type: ignore[attr-defined]

        h1_start = n * STEP + 0.5
        for i, sid in enumerate(sids):
            reactor.callLater(h1_start + i * 0.3, _subscribe_h1, sid)  # type: ignore[attr-defined]

        # Symbol-detaljer (én samlet forespørsel)
        detail_delay = h1_start + n * 0.3 + 0.5

        def _req_symbol_details() -> None:
            req_sym = ProtoOASymbolByIdReq()
            req_sym.ctidTraderAccountId = account_id
            for sid in self.symbol_map.values():
                req_sym.symbolId.append(sid)
            self.send(req_sym)

        reactor.callLater(detail_delay, _req_symbol_details)  # type: ignore[attr-defined]

        # Historiske 15m candles (2 s mellom hvert symbol)
        hist_start = detail_delay + 1.0
        for i, sid in enumerate(sids):
            reactor.callLater(  # type: ignore[attr-defined]
                hist_start + i * 2.0, self.request_historical_bars, sid, M15_PERIOD
            )

        # Historiske 1H candles (2.5 s mellom hvert symbol)
        h1_hist_start = hist_start + n * 2.0 + 1.0
        for i, sid in enumerate(sids):
            reactor.callLater(  # type: ignore[attr-defined]
                h1_hist_start + i * 2.5, self.request_historical_bars, sid, H1_PERIOD
            )

        # Pris-feed spot-subscribe
        feed_start = n * STEP + 0.5
        feed_sids = list(self.price_feed_sids.items())

        def _sub_feed(sid: int) -> None:
            req_pf = ProtoOASubscribeSpotsReq()
            req_pf.ctidTraderAccountId = account_id
            req_pf.symbolId.append(sid)
            self.send(req_pf)

        for j, (_price_key, sid) in enumerate(feed_sids):
            reactor.callLater(feed_start + j * STEP, _sub_feed, sid)  # type: ignore[attr-defined]

        # Reconcile — etter symbol-detaljer
        reactor.callLater(detail_delay + 0.5, self.send_reconcile)  # type: ignore[attr-defined]

        log.info(
            "[KLAR] Transport initialisert — %d trading-symboler, %d feed-symboler",
            len(self.symbol_map),
            len(self.price_feed_sids),
        )

    def _on_subscribe_spots(self, res: Any) -> None:
        pass  # Stille OK

    def _on_symbol_by_id(self, res: Any) -> None:
        """Lagrer lotSize, minVolume, stepVolume, digits per symbol for
        korrekt volum- og SL/TP-avrunding."""
        for sym in res.symbol:
            sid = sym.symbolId
            if sid not in self.symbol_map.values():
                continue
            self.symbol_info[sid] = {
                "lot_size": sym.lotSize,
                "min_volume": sym.minVolume,
                "step_volume": sym.stepVolume,
            }
            self.symbol_price_digits[sid] = sym.digits
            name = next((k for k, v in self.symbol_map.items() if v == sid), str(sid))
            log.info(
                "[SYMBOL INFO] %s: lotSize=%s minVol=%s stepVol=%s digits=%s",
                name,
                sym.lotSize,
                sym.minVolume,
                sym.stepVolume,
                sym.digits,
            )
            if name in AGRI_INSTRUMENTS:
                self._dump_agri_symbol_info(name, sym)

    def _dump_agri_symbol_info(self, name: str, sym: Any) -> None:
        """Lagrer agri symbol-specs til JSON for kalibrering av setup-generator.

        Sti i Bedrock: `~/bedrock/data/bot/agri_symbol_info.json`. Tidligere
        `~/cot-explorer/data/prices/` — endret fordi cot-explorer ikke
        eksisterer i Bedrock-parallell-drift.
        """
        import json as _json

        info_file = AGRI_SYMBOL_INFO_PATH
        existing: dict[str, Any] = {}
        if info_file.exists():
            try:
                existing = _json.loads(info_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing[name] = {
            "symbol_id": sym.symbolId,
            "lot_size": sym.lotSize,
            "min_volume": sym.minVolume,
            "step_volume": sym.stepVolume,
            "digits": sym.digits,
            "description": getattr(sym, "description", ""),
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M timezone.utc"),
        }
        info_file.parent.mkdir(parents=True, exist_ok=True)
        info_file.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("[AGRI SYMBOL] %s info lagret til %s", name, info_file)

    # ─────────────────────────────────────────────────────────
    #  Spot-events (bid/ask/spread — og route-til-callback)
    # ─────────────────────────────────────────────────────────

    def _on_spot(self, event: Any) -> None:
        sid = event.symbolId
        digits = self.symbol_digits.get(sid, 5)
        now = time.time()
        self._last_spot_time = now
        self._last_spot_per_sid[sid] = now
        # Hvis symbol har kommet tilbake etter silence, rydd flagget
        self._symbol_silent_logged.discard(sid)

        if event.HasField("bid"):
            self.last_bid[sid] = event.bid / (10**digits)
        if event.HasField("ask"):
            self.last_ask[sid] = event.ask / (10**digits)

        if sid in self.last_bid and sid in self.last_ask:
            spread = self.last_ask[sid] - self.last_bid[sid]
            if sid in self.spread_history:
                self.spread_history[sid].append(spread)

        # Route til bot-laget (candle-handling + evaluering)
        try:
            self._callbacks.on_spot(event)
        except Exception:
            log.exception("[CALLBACK] on_spot feilet")

    # ─────────────────────────────────────────────────────────
    #  Historical bars + execution + errors + reconcile → callbacks
    # ─────────────────────────────────────────────────────────

    def _on_historical_bars(self, res: Any) -> None:
        try:
            self._callbacks.on_historical_bars(res)
        except Exception:
            log.exception("[CALLBACK] on_historical_bars feilet")

    def _on_execution(self, event: Any) -> None:
        try:
            self._callbacks.on_execution(event)
        except Exception:
            log.exception("[CALLBACK] on_execution feilet")

    def _on_order_error(self, event: Any) -> None:
        try:
            self._callbacks.on_order_error(event)
        except Exception:
            log.exception("[CALLBACK] on_order_error feilet")

    def _on_error_res(self, event: Any) -> None:
        # Auth-fatal-koder gir umiddelbar exit
        err_code = getattr(event, "errorCode", "")
        if err_code in AUTH_FATAL_ERROR_CODES:
            log.error(
                "[FATAL] cTrader auth-feil: %s — token må regenereres og bot restartes",
                err_code,
            )
            self._fatal_exit(78)
            return
        try:
            self._callbacks.on_error_res(event)
        except Exception:
            log.exception("[CALLBACK] on_error_res feilet")

    def _on_reconcile(self, res: Any) -> None:
        try:
            self._callbacks.on_reconcile(res)
        except Exception:
            log.exception("[CALLBACK] on_reconcile feilet")

    # ─────────────────────────────────────────────────────────
    #  Heartbeat + watchdog
    # ─────────────────────────────────────────────────────────

    def _send_heartbeat(self) -> None:
        if self.client is None:
            return
        try:
            d = self.client.send(ProtoHeartbeatEvent(), responseTimeoutInSeconds=10)
            d.addErrback(lambda f: None)
        except Exception:
            pass

    def _watchdog_check(self) -> None:
        """Overvåker at spot-data strømmer inn. Reconnecter ved lang stillhet."""
        if self._last_spot_time is None:
            return
        if self._reconnecting:
            return
        elapsed = time.time() - self._last_spot_time
        if elapsed > _WATCHDOG_RECONNECT_SEC:
            log.warning(
                "[WATCHDOG] Ingen spot-data på %ds — forsøker reconnect.",
                int(elapsed),
            )
            self._reconnecting = True
            try:
                if self.client is not None:
                    self.client.stopService()
            except Exception:
                pass
            if self.client is not None:
                reactor.callLater(5, self.client.startService)  # type: ignore[attr-defined]
        elif elapsed > _WATCHDOG_WARN_SEC:
            log.warning(
                "[WATCHDOG] Ingen spot-data på %ds — stille marked eller tap av tilkobling.",
                int(elapsed),
            )

        if elapsed < _WATCHDOG_GLOBAL_FRESH_SEC:
            self._check_symbol_silence()

    def _check_symbol_silence(self) -> None:
        """Varsle hvis enkelt-symbol har vært stille > 30 min (2 t for agri)
        mens andre symboler fortsatt strømmer. Indikerer rename/delist."""
        now = time.time()
        for instr_name, sid in self.symbol_map.items():
            last = self._last_spot_per_sid.get(sid)
            if last is None:
                continue
            silent_for = now - last
            threshold = (
                _SYMBOL_SILENCE_AGRI_THRESHOLD_SEC
                if instr_name in AGRI_INSTRUMENTS
                else _SYMBOL_SILENCE_THRESHOLD_SEC
            )
            if silent_for > threshold and sid not in self._symbol_silent_logged:
                log.warning(
                    "[SYMBOL-STILLHET] %s (sid=%s) ingen spot-data på %.0f min "
                    "mens global feed er fersk. Sjekk om megler har rename/"
                    "delistet symbolet.",
                    instr_name,
                    sid,
                    silent_for / 60,
                )
                self._symbol_silent_logged.add(sid)


# ─────────────────────────────────────────────────────────────
# Helper: les credentials fra env (brukes av bot/__main__.py i session 45)
# ─────────────────────────────────────────────────────────────


def load_credentials_from_env() -> CtraderCredentials:
    """Les cTrader-credentials fra miljøvariabler. Feiler hardt ved manglende."""
    missing: list[str] = []
    client_id = os.environ.get("CTRADER_CLIENT_ID", "")
    client_secret = os.environ.get("CTRADER_CLIENT_SECRET", "")
    access_token = os.environ.get("CTRADER_ACCESS_TOKEN", "")
    account_id_raw = os.environ.get("CTRADER_ACCOUNT_ID", "")

    if not client_id:
        missing.append("CTRADER_CLIENT_ID")
    if not client_secret:
        missing.append("CTRADER_CLIENT_SECRET")
    if not access_token:
        missing.append("CTRADER_ACCESS_TOKEN")
    if not account_id_raw:
        missing.append("CTRADER_ACCOUNT_ID")

    if missing:
        raise RuntimeError(f"Mangler miljøvariabler: {', '.join(missing)}")

    try:
        account_id = int(account_id_raw)
    except ValueError as exc:
        raise RuntimeError(f"CTRADER_ACCOUNT_ID må være heltall, fikk {account_id_raw!r}") from exc

    return CtraderCredentials(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        account_id=account_id,
    )
