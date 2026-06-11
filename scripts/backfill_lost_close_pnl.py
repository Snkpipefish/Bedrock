#!/usr/bin/env python3
"""Backfill ekte PnL for lost-close-entries via cTrader Deal-API.

Henter ProtoOADealListByPositionIdRes for hver entry i ``signal_log.json``
med ``exit_reason="lost-close"`` og fyller inn faktisk close_price /
pnl / exit_reason fra cTrader-side. Erstatter "managed" + "lost-close"
med ekte resultat (win/loss + SL/TP/MANUAL/STOP_OUT).

Hvorfor: cleanup_dangling_trades.py markerer entries der bot mistet
close-event som "managed" (statistikk-nøytral). Men cTrader har den
faktiske trade-historikken; vi kan hente den og få ekte tall.

Bruk (krever boten stoppet for å unngå dual-session-konflikt):
    systemctl --user stop bedrock-bot.service
    .venv/bin/python scripts/backfill_lost_close_pnl.py            # dry-run
    .venv/bin/python scripts/backfill_lost_close_pnl.py --apply
    systemctl --user start bedrock-bot.service

Med ``--position-ids`` (session 2026-06-11): målrett spesifikke
fortsatt-åpne-i-logg-entries (result=None) i stedet for lost-close-
seleksjonen. Brukes når loggen har stale åpne entries der posisjonen
er reelt lukket hos broker, men close-eventet aldri ble logget:
    .venv/bin/python scripts/backfill_lost_close_pnl.py \\
        --position-ids 123,456 --apply
NB: cleanup_dangling_trades.py er IKKE trygg for dette — den markerer
alle dangling eldre enn min-age og kan treffe reelt åpne posisjoner.

Trygt å kjøre flere ganger: idempotent. Backup tas før --apply.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ctrader_open_api import Client, EndPoints, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOADealListReq,
    ProtoOADealListRes,
    ProtoOAErrorRes,
)

# Twisted-imports først så ctrader_open_api kan velge async-reactor
from twisted.internet import reactor

# Sett opp PYTHONPATH så bedrock-modulen kan importeres
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bedrock.bot.ctrader_client import load_credentials_from_env  # noqa: E402
from bedrock.config.secrets import DEFAULT_SECRETS_PATH, load_secrets  # noqa: E402

log = logging.getLogger("backfill_lost_close")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "signal_log.json"


def _parse_log_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = raw.replace(" timezone.utc", "+00:00").replace(" ", "T")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _ts_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _find_close_deal(deals: list, entry_pos_id: int) -> dict | None:
    """Finn close-deal-en for en posisjon.

    cTrader returnerer både opening og closing deals for samme positionId.
    Closing-deal har ``closePositionDetail`` fylt; opening har ikke.
    """
    closes = [d for d in deals if d.HasField("closePositionDetail")]
    if not closes:
        return None
    # Hvis flere partial-closes, ta den siste (utfullende close)
    closes.sort(key=lambda d: d.executionTimestamp, reverse=True)
    return closes[0]


def _classify_exit_reason(
    close_price: float, entry_price: float, side: str, sl: float | None, tp: float | None
) -> str:
    """Best-effort klassifisering av exit-årsak basert på close-pris vs SL/TP.

    cTrader Deal-meldingen har ikke en eksplisitt "closed_by"-felt vi kan
    lese (bare orderType). Heuristikk: er close nær SL → "SL"; nær TP → "TP";
    ellers "MANUAL/CLOSE".
    """
    if not entry_price or not close_price:
        return "BACKFILL"
    # Tolerance ~0.5 % for SL/TP match
    tol = abs(entry_price) * 0.005
    if sl and abs(close_price - sl) <= tol:
        return "SL"
    if tp and abs(close_price - tp) <= tol:
        return "TP"
    # Hvis loss-side, sjekk om close gikk under entry (sell stop hit fra rev)
    return "MANUAL_OR_TRAIL"


class BackfillRunner:
    """Twisted-driven scanner. Henter deals i 7-dagers bolker (cTrader-grense)
    og matcher mot lost-close-entries via position_id.
    """

    # cTrader DealList max range. Spotware-dokumentasjon: 1 uke per
    # request. Mindre vinduer = trygt, så vi bruker 6 dager for buffer.
    _CHUNK_DAYS = 6

    def __init__(self, creds, lost_entries: list[dict], apply: bool) -> None:
        self.creds = creds
        self.lost_by_pos: dict[int, dict] = {}
        for e in lost_entries:
            pid = (e.get("signal") or {}).get("position_id")
            if pid:
                self.lost_by_pos[int(pid)] = e
        self.apply = apply
        self.client: Client | None = None
        self.results: list[dict] = []  # entries med oppdaterte felt
        # Beregn tidsvindu: fra eldste lost-close til nå
        self._oldest = min(
            (_parse_log_ts(e.get("timestamp")) for e in lost_entries),
            default=datetime.now(timezone.utc) - timedelta(days=30),
        )
        if self._oldest is None:
            self._oldest = datetime.now(timezone.utc) - timedelta(days=30)
        # Kø av (from, to)-vinduer å spørre
        self._chunks: list[tuple[datetime, datetime]] = []
        cur = self._oldest - timedelta(hours=12)  # buffer for åpning
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        while cur < end:
            chunk_end = min(cur + timedelta(days=self._CHUNK_DAYS), end)
            self._chunks.append((cur, chunk_end))
            cur = chunk_end
        log.info(
            "Vil hente %d bolker à %dd fra %s til %s",
            len(self._chunks),
            self._CHUNK_DAYS,
            self._oldest.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )

    def start(self) -> None:
        endpoint = EndPoints.PROTOBUF_DEMO_HOST  # tillater demo-only for nå
        log.info("Connecting til %s:%s ...", endpoint, EndPoints.PROTOBUF_PORT)
        self.client = Client(endpoint, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

    def _on_connected(self, client: Client) -> None:
        log.info("[CONN] sender app-auth")
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.creds.client_id
        req.clientSecret = self.creds.client_secret
        self.client.send(req)

    def _on_disconnected(self, client: Client, reason) -> None:
        log.warning("[DISCONN] %s", reason)
        if reactor.running:  # type: ignore[attr-defined]
            reactor.stop()  # type: ignore[attr-defined]

    def _on_message(self, client: Client, msg) -> None:
        pt = msg.payloadType

        if pt == ProtoOAApplicationAuthRes().payloadType:
            log.info("[AUTH] app OK, sender account-auth")
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = self.creds.account_id
            req.accessToken = self.creds.access_token
            self.client.send(req)

        elif pt == ProtoOAAccountAuthRes().payloadType:
            log.info(
                "[AUTH] account OK — starter scan av %d position_ids over %d bolker",
                len(self.lost_by_pos),
                len(self._chunks),
            )
            self._request_next_chunk()

        elif pt == ProtoOADealListRes().payloadType:
            res = ProtoOADealListRes()
            res.ParseFromString(msg.payload)
            self._handle_chunk(res)
            self._request_next_chunk()

        elif pt == ProtoOAErrorRes().payloadType:
            err = ProtoOAErrorRes()
            err.ParseFromString(msg.payload)
            log.error("[ERR] code=%s desc=%s", err.errorCode, err.description)
            # Hopp over denne entry'en og prøv neste
            self._request_next()

    def _request_next_chunk(self) -> None:
        if not self._chunks:
            unmatched = [
                pid
                for pid in self.lost_by_pos
                if not any(r.get("signal", {}).get("position_id") == pid for r in self.results)
            ]
            log.info(
                "[DONE] %d bolker scannet — %d entries oppdatert, %d uten match",
                0,
                len(self.results),
                len(unmatched),
            )
            if unmatched:
                log.warning("Position_id uten close-deal i cTrader-historikk: %s", unmatched)
            self._finish()
            return

        from_dt, to_dt = self._chunks.pop(0)
        req = ProtoOADealListReq()
        req.ctidTraderAccountId = self.creds.account_id
        req.fromTimestamp = _ts_ms(from_dt)
        req.toTimestamp = _ts_ms(to_dt)
        req.maxRows = 1000
        log.info(
            "→ DealList %s..%s",
            from_dt.strftime("%Y-%m-%d %H:%M"),
            to_dt.strftime("%Y-%m-%d %H:%M"),
        )
        self.client.send(req)

    def _handle_chunk(self, res: ProtoOADealListRes) -> None:
        deals = list(res.deal)
        log.info("  ← %d deals i bolken (hasMore=%s)", len(deals), res.hasMore)
        # Match close-deals mot lost-by-pos
        for deal in deals:
            if not deal.HasField("closePositionDetail"):
                continue
            pid = int(deal.positionId)
            entry = self.lost_by_pos.get(pid)
            if entry is None:
                continue
            # Allerede behandlet i tidligere chunk (partial close osv.)?
            sig = entry.get("signal") or {}
            already = any(r is entry for r in self.results)
            if already:
                continue

            cpd = deal.closePositionDetail
            money_digits = cpd.moneyDigits if cpd.HasField("moneyDigits") else 2
            divisor = 10**money_digits
            gross = cpd.grossProfit / divisor
            swap = cpd.swap / divisor
            commission = cpd.commission / divisor
            net_pnl = gross + swap + commission

            close_dt = datetime.fromtimestamp(deal.executionTimestamp / 1000, tz=timezone.utc)
            close_price = deal.executionPrice

            entry_price = sig.get("entry") or 0.0
            sl = sig.get("stop") or None
            tp = sig.get("t1") or None
            side = (sig.get("direction") or "").upper()
            exit_reason = _classify_exit_reason(close_price, entry_price, side, sl, tp)
            result = "win" if net_pnl > 0 else ("loss" if net_pnl < 0 else "managed")

            entry["closed_at"] = close_dt.strftime("%Y-%m-%d %H:%M timezone.utc")
            entry["result"] = result
            entry["exit_reason"] = exit_reason
            entry["pnl"] = {
                "close_price": round(close_price, 5),
                "pnl_usd": round(net_pnl, 2),
                "gross_profit": round(gross, 2),
                "swap": round(swap, 2),
                "commission": round(commission, 2),
                "backfilled": True,
            }
            self.results.append(entry)
            log.info(
                "  ✓ pos_id=%-9d  %s %s  close=%.5f  pnl=$%+.2f  reason=%s  (%s)",
                pid,
                sig.get("instrument", "?"),
                side,
                close_price,
                net_pnl,
                exit_reason,
                close_dt.strftime("%Y-%m-%d %H:%M"),
            )

    def _finish(self) -> None:
        if self.client is not None:
            try:
                self.client.stopService()
            except Exception:
                pass
        if reactor.running:  # type: ignore[attr-defined]
            reactor.callLater(0.5, reactor.stop)  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log-path", type=Path, default=LOG_PATH)
    ap.add_argument("--apply", action="store_true", help="Skriv endringer (default dry-run)")
    ap.add_argument(
        "--position-ids",
        type=str,
        default=None,
        help=(
            "Komma-separerte position_ids. Velger åpne-i-logg-entries "
            "(result=None) med disse id-ene i stedet for lost-close-seleksjonen."
        ),
    )
    args = ap.parse_args(argv)

    # Load secrets så env-vars er satt. load_secrets returnerer dict
    # uten å mutere os.environ — sett selv (samme mønster som bot startup).
    if DEFAULT_SECRETS_PATH.exists():
        secrets = load_secrets(DEFAULT_SECRETS_PATH)
        for k, v in secrets.items():
            os.environ.setdefault(k, v)
    creds = load_credentials_from_env()

    if not args.log_path.exists():
        log.error("Log mangler: %s", args.log_path)
        return 1

    raw = json.loads(args.log_path.read_text(encoding="utf-8"))
    entries = raw.get("entries", [])
    if args.position_ids:
        wanted = {int(p.strip()) for p in args.position_ids.split(",") if p.strip()}
        lost = [
            e
            for e in entries
            if e.get("result") is None and (e.get("signal") or {}).get("position_id") in wanted
        ]
        found_ids = {(e.get("signal") or {}).get("position_id") for e in lost}
        missing = wanted - found_ids
        if missing:
            log.warning("Position_ids uten åpen logg-entry (hopper over): %s", sorted(missing))
        log.info("Fant %d åpne entries som matcher --position-ids", len(lost))
    else:
        lost = [
            e
            for e in entries
            if e.get("exit_reason") == "lost-close" and (e.get("signal") or {}).get("position_id")
        ]
        log.info("Fant %d lost-close-entries med position_id", len(lost))
    if not lost:
        return 0

    runner = BackfillRunner(creds, lost, apply=args.apply)
    runner.start()
    reactor.run()  # type: ignore[attr-defined]

    # Etter reactor.stop(): skriv loggen hvis --apply og noe ble endret
    if args.apply and runner.results:
        now = datetime.now(timezone.utc)
        backup = args.log_path.with_suffix(
            args.log_path.suffix + f".bak-{now.strftime('%Y%m%dT%H%M%S')}"
        )
        shutil.copy2(args.log_path, backup)
        raw["last_updated"] = now.strftime("%Y-%m-%d %H:%M timezone.utc")

        fd, tmp = tempfile.mkstemp(prefix="signal_log_", suffix=".json", dir=args.log_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(raw, fp, indent=2, ensure_ascii=False)
            os.replace(tmp, args.log_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        log.info("Skrev oppdatert log. Backup: %s", backup)
    elif not args.apply and runner.results:
        log.info(
            "DRY-RUN — %d entries ville blitt oppdatert. Kjør med --apply.", len(runner.results)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
