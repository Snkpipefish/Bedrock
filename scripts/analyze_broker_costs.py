#!/usr/bin/env python3
"""Hent margin + live demo-spreads fra cTrader for alle 22 instrumenter.

For hvert instrument i ``bot.instruments.INSTRUMENT_MAP``:
- Henter ekte margin-krav via ``ProtoOAExpectedMarginReq`` for 0.03 lot
  (bot's max-volum per posisjon, se ``sizing.compute_desired_lots``)
- Lytter på ``ProtoOASpotEvent`` i 25 sek for å beregne snitt-spread
- Rapporterer: symbol, lotSize, 0.03-lot volume i units, buy/sell-margin,
  snitt-spread, og estimert max samtidig margin hvis bot er åpen i alle 22

Hvorfor: operatør spurte hvor mye penger som trengs for å finansiere
boten. Risk per trade (USD-tap ved SL) er én ting; margin (USD låst hos
broker for at posisjonen overhodet eksisterer) er en annen. Forrige
analyse var risk-basert; denne er margin-basert med ekte broker-tall.

Bruk:
    systemctl --user stop bedrock-bot.service
    .venv/bin/python scripts/analyze_broker_costs.py
    systemctl --user start bedrock-bot.service

Output: tekst-tabell + JSON ved siden av (data/_meta/broker_costs.json).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ctrader_open_api import Client, EndPoints, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAExpectedMarginReq,
    ProtoOAExpectedMarginRes,
    ProtoOASpotEvent,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from twisted.internet import reactor

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bedrock.bot.ctrader_client import load_credentials_from_env  # noqa: E402
from bedrock.bot.instruments import INSTRUMENT_MAP  # noqa: E402
from bedrock.config.secrets import DEFAULT_SECRETS_PATH, load_secrets  # noqa: E402

log = logging.getLogger("analyze_broker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_LOT = 0.03  # bot.sizing.compute_desired_lots cap
SPREAD_SAMPLE_SEC = 25
OUTPUT_JSON = REPO_ROOT / "data" / "_meta" / "broker_costs.json"


class BrokerCostScanner:
    """Twisted-pipeline: connect -> auth -> symbols-list -> margin
    per instrument -> subscribe spots -> samle spreads -> exit + skriv.
    """

    def __init__(self, creds) -> None:
        self.creds = creds
        self.client: Client | None = None
        self.results: dict[str, dict] = {}
        self.bedrock_to_sid: dict[str, int] = {}
        self.spread_bid_ask: dict[int, list[tuple[float, float]]] = defaultdict(list)
        self._phase = "init"
        self._margin_queue: list[tuple[str, int, int]] = []
        self._pending_margin: tuple[str, int, int] | None = None

    def start(self) -> None:
        endpoint = EndPoints.PROTOBUF_DEMO_HOST
        log.info("Connecting til %s:%s", endpoint, EndPoints.PROTOBUF_PORT)
        self.client = Client(endpoint, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

    def _on_connected(self, client: Client) -> None:
        log.info("[CONN] app-auth")
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.creds.client_id
        req.clientSecret = self.creds.client_secret
        self.client.send(req)

    def _on_disconnected(self, client: Client, reason) -> None:
        log.warning("[DISCONN] %s", reason)
        if reactor.running:
            reactor.stop()

    def _on_message(self, client: Client, msg) -> None:
        pt = msg.payloadType
        if pt == ProtoOAApplicationAuthRes().payloadType:
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = self.creds.account_id
            req.accessToken = self.creds.access_token
            self.client.send(req)
        elif pt == ProtoOAAccountAuthRes().payloadType:
            log.info("[AUTH] account OK — henter symbols-liste")
            self._phase = "symbols"
            req = ProtoOASymbolsListReq()
            req.ctidTraderAccountId = self.creds.account_id
            self.client.send(req)
        elif pt == ProtoOASymbolsListRes().payloadType:
            self._handle_symbols(msg.payload)
        elif pt == ProtoOASymbolByIdRes().payloadType:
            self._handle_symbol_detail(msg.payload)
        elif pt == ProtoOAExpectedMarginRes().payloadType:
            self._handle_margin(msg.payload)
        elif pt == ProtoOASubscribeSpotsRes().payloadType:
            pass
        elif pt == ProtoOASpotEvent().payloadType:
            self._handle_spot(msg.payload)
        elif pt == ProtoOAErrorRes().payloadType:
            err = ProtoOAErrorRes()
            err.ParseFromString(msg.payload)
            log.warning("[ERR] %s: %s", err.errorCode, err.description)
            if self._phase == "margin":
                self._request_next_margin()

    def _handle_symbols(self, payload: bytes) -> None:
        res = ProtoOASymbolsListRes()
        res.ParseFromString(payload)
        name_to_sid: dict[str, int] = {s.symbolName: s.symbolId for s in res.symbol}
        for bedrock_name, candidates in INSTRUMENT_MAP.items():
            for cand in candidates:
                if cand in name_to_sid:
                    self.bedrock_to_sid[bedrock_name] = name_to_sid[cand]
                    self.results[bedrock_name] = {
                        "symbol_name": cand,
                        "symbol_id": name_to_sid[cand],
                    }
                    break
            else:
                log.warning("Ingen match for %s i symbols-list", bedrock_name)
        log.info(
            "Matchet %d/%d instrumenter — henter symbol-detaljer",
            len(self.bedrock_to_sid),
            len(INSTRUMENT_MAP),
        )
        sids = list(self.bedrock_to_sid.values())
        req = ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = self.creds.account_id
        for sid in sids:
            req.symbolId.append(sid)
        self._phase = "symbol_detail"
        self.client.send(req)

    def _handle_symbol_detail(self, payload: bytes) -> None:
        res = ProtoOASymbolByIdRes()
        res.ParseFromString(payload)
        sid_to_lotsize: dict[int, int] = {s.symbolId: s.lotSize for s in res.symbol}
        for bedrock_name, sid in self.bedrock_to_sid.items():
            lot_size = sid_to_lotsize.get(sid, 0)
            volume_units = int(MAX_LOT * lot_size)
            if bedrock_name not in self.results:
                continue
            self.results[bedrock_name]["lot_size"] = lot_size
            self.results[bedrock_name]["volume_at_0_03_lot"] = volume_units
            if lot_size > 0 and volume_units > 0:
                self._margin_queue.append((bedrock_name, sid, volume_units))
        log.info("[MARGIN] henter ExpectedMargin for %d symboler", len(self._margin_queue))
        self._phase = "margin"
        self._request_next_margin()

    def _request_next_margin(self) -> None:
        if not self._margin_queue:
            log.info("[MARGIN] ferdig — starter spread-sampling i %d sek", SPREAD_SAMPLE_SEC)
            self._start_spread_sampling()
            return
        name, sid, vol = self._margin_queue.pop(0)
        self._pending_margin = (name, sid, vol)
        req = ProtoOAExpectedMarginReq()
        req.ctidTraderAccountId = self.creds.account_id
        req.symbolId = sid
        req.volume.append(vol)
        self.client.send(req)

    def _handle_margin(self, payload: bytes) -> None:
        res = ProtoOAExpectedMarginRes()
        res.ParseFromString(payload)
        if self._pending_margin is None:
            return
        name, sid, vol = self._pending_margin
        if not res.margin:
            log.warning("Ingen margin-data for %s", name)
            self._request_next_margin()
            return
        m = res.margin[0]
        money_digits = res.moneyDigits if res.moneyDigits else 2
        divisor = 10**money_digits
        buy_margin = m.buyMargin / divisor
        sell_margin = m.sellMargin / divisor
        self.results[name]["buy_margin_usd"] = round(buy_margin, 2)
        self.results[name]["sell_margin_usd"] = round(sell_margin, 2)
        log.info(
            "  %-12s vol=%-12d  buy=$%-7.2f sell=$%-7.2f",
            name,
            vol,
            buy_margin,
            sell_margin,
        )
        self._request_next_margin()

    def _start_spread_sampling(self) -> None:
        self._phase = "spreads"
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.creds.account_id
        for sid in self.bedrock_to_sid.values():
            req.symbolId.append(sid)
        self.client.send(req)
        reactor.callLater(SPREAD_SAMPLE_SEC, self._finish_spread_sampling)

    def _handle_spot(self, payload: bytes) -> None:
        ev = ProtoOASpotEvent()
        ev.ParseFromString(payload)
        if ev.bid and ev.ask:
            self.spread_bid_ask[ev.symbolId].append((ev.bid, ev.ask))

    def _finish_spread_sampling(self) -> None:
        log.info("[SPREAD] sampling ferdig — beregner snitt")
        sid_to_name = {sid: name for name, sid in self.bedrock_to_sid.items()}
        for sid, samples in self.spread_bid_ask.items():
            if not samples:
                continue
            spreads_pct = [
                (ask - bid) / ((ask + bid) / 2) * 100.0 for bid, ask in samples if (ask + bid) > 0
            ]
            if not spreads_pct:
                continue
            avg = sum(spreads_pct) / len(spreads_pct)
            name = sid_to_name.get(sid, str(sid))
            if name in self.results:
                self.results[name]["spread_pct_avg"] = round(avg, 5)
                self.results[name]["spread_samples"] = len(samples)
        self._finish()

    def _finish(self) -> None:
        if self.client is not None:
            try:
                self.client.stopService()
            except Exception:
                pass
        if reactor.running:
            reactor.callLater(0.5, reactor.stop)


def _print_report(results: dict[str, dict]) -> None:
    print()
    print("=" * 100)
    print(" BEDROCK BOT — BROKER-KOSTNADER (cTrader demo, 0.03 lot per posisjon)")
    print("=" * 100)
    print(
        f" {'Instrument':<12} {'Symbol':<14} {'LotSize':>12} {'Vol@0.03':>10}"
        f" {'BuyMargin':>11} {'SellMargin':>11} {'Spread%':>10}"
    )
    print(" " + "-" * 95)

    total_buy = 0.0
    total_sell = 0.0
    for name, info in sorted(results.items()):
        sym = info.get("symbol_name", "?")
        lot = info.get("lot_size", 0)
        vol = info.get("volume_at_0_03_lot", 0)
        bm = info.get("buy_margin_usd")
        sm = info.get("sell_margin_usd")
        sp = info.get("spread_pct_avg")
        bm_str = f"${bm:>7.2f}" if bm is not None else "    —  "
        sm_str = f"${sm:>7.2f}" if sm is not None else "    —  "
        sp_str = f"{sp:>6.4f}%" if sp is not None else "    —  "
        print(f" {name:<12} {sym:<14} {lot:>12} {vol:>10} {bm_str:>11} {sm_str:>11} {sp_str:>10}")
        if bm is not None:
            total_buy += bm
        if sm is not None:
            total_sell += sm
    print(" " + "-" * 95)
    print(
        f" {'TOTALT (alle 22 åpne samtidig)':<39}{'':>12}{'':>10}"
        f"  ${total_buy:>8.2f}  ${total_sell:>8.2f}"
    )
    print()
    print(" Forklaring:")
    print(" - Vol@0.03: faktisk volum-tall sendt til broker for 0.03 lot")
    print(" - BuyMargin: USD låst av broker for at en BUY-posisjon eksisterer (0.03 lot)")
    print(" - SellMargin: tilsvarende for SELL")
    print(" - Spread%: relativ spread (ask-bid)/midpoint × 100, snitt over ~25 sek")
    print(" - TOTALT: max samtidig margin hvis bot åpner i alle 22 samtidig")
    print()
    print(" NB: Tall er fra cTrader DEMO. Skilling live har typisk:")
    print(" - 10-30 %% bredere spreads på CFDs (oil, indices, commodities)")
    print(" - Strammere spreads på majors FX")
    print(" - Samme margin-krav (basert på cTrader leverage-tiers)")
    print()
    print(" For live-konto: budsjetter ~120 %% av total-margin pluss risk-buffer.")
    print("=" * 100)


def main() -> int:
    if DEFAULT_SECRETS_PATH.exists():
        for k, v in load_secrets(DEFAULT_SECRETS_PATH).items():
            os.environ.setdefault(k, v)
    creds = load_credentials_from_env()

    scanner = BrokerCostScanner(creds)
    scanner.start()
    reactor.run()

    _print_report(scanner.results)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "max_lot_per_trade": MAX_LOT,
                "results": scanner.results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f" Skrev: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
