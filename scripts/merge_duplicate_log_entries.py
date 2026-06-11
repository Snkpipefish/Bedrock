#!/usr/bin/env python3
"""Merge duplikate position_id-entries i signal_log.json mot ekte deal-data.

Bakgrunn (session 2026-06-11): POSITION_NOT_FOUND-kaskaden (fikset i
exit.py commit 9c8bffc) etterlot 40 position_ids fra 2026-05-04 →
2026-05-29 med 2-14 logg-entries hver — original graded entry pluss
metadata-fattige reconcile-duplikater, alle med gjettede/motstridende
resultater som dobbelteller i statistikk.

Hva skriptet gjør, per duplikat-pid:
1. Velger kanonisk entry: den med grade != None (originalen). Finnes
   ingen graded (posisjoner adoptert via reconcile før metadata fantes),
   velges eldste entry.
2. Henter ALLE close-deals for posisjonen fra cTrader (ProtoOADealListReq
   i 6-dagers bolker), summerer gross/swap/commission over partial closes,
   og overskriver kanonisk entry med ekte closed_at / result / exit_reason
   / pnl (markert backfilled=True, merged_duplicates=N).
3. Fjerner alle øvrige entries for samme pid.

Pids uten close-deal i cTrader-historikken røres IKKE (warning).

Bruk (krever boten stoppet — dual-session-konflikt + bot skriver loggen):
    systemctl --user stop bedrock-bot.service
    .venv/bin/python scripts/merge_duplicate_log_entries.py            # dry-run
    .venv/bin/python scripts/merge_duplicate_log_entries.py --apply
    systemctl --user start bedrock-bot.service

Idempotent: etter merge finnes ingen duplikate pids, så re-kjøring er no-op.
Backup tas automatisk før --apply.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from collections import defaultdict
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
from twisted.internet import reactor

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bedrock.bot.ctrader_client import load_credentials_from_env  # noqa: E402
from bedrock.config.secrets import DEFAULT_SECRETS_PATH, load_secrets  # noqa: E402

log = logging.getLogger("merge_duplicate_log_entries")
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


def _classify_exit_reason(
    close_price: float, entry_price: float, sl: float | None, tp: float | None
) -> str:
    """Samme heuristikk som backfill_lost_close_pnl: close-pris nær SL/TP."""
    if not entry_price or not close_price:
        return "BACKFILL"
    tol = abs(entry_price) * 0.005
    if sl and abs(close_price - sl) <= tol:
        return "SL"
    if tp and abs(close_price - tp) <= tol:
        return "TP"
    return "MANUAL_OR_TRAIL"


def find_duplicates(entries: list[dict]) -> dict[int, list[int]]:
    """Map position_id -> liste av entry-indekser, kun pids med >1 entry."""
    by_pid: dict[int, list[int]] = defaultdict(list)
    for i, e in enumerate(entries):
        pid = (e.get("signal") or {}).get("position_id")
        if pid:
            by_pid[int(pid)].append(i)
    return {p: v for p, v in by_pid.items() if len(v) > 1}


def pick_canonical(entries: list[dict], idxs: list[int]) -> int:
    """Velg kanonisk entry: graded original, ellers eldste."""
    graded = [i for i in idxs if (entries[i].get("signal") or {}).get("grade") is not None]
    if len(graded) == 1:
        return graded[0]
    if len(graded) > 1:
        raise ValueError(f"Flere graded entries for samme pid (idx {graded}) — manuell vurdering")
    return min(
        idxs,
        key=lambda i: (
            _parse_log_ts(entries[i].get("timestamp")) or datetime.max.replace(tzinfo=timezone.utc)
        ),
    )


class DealScanner:
    """Henter alle close-deals for ønskede position_ids i 6-dagers bolker."""

    _CHUNK_DAYS = 6

    def __init__(self, creds, wanted_pids: set[int], oldest: datetime) -> None:
        self.creds = creds
        self.wanted = wanted_pids
        self.client: Client | None = None
        # pid -> liste av close-deal-dicts (en per partial close)
        self.closes: dict[int, list[dict]] = defaultdict(list)
        self.failed = False
        self._chunks: list[tuple[datetime, datetime]] = []
        cur = oldest - timedelta(hours=12)
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        while cur < end:
            chunk_end = min(cur + timedelta(days=self._CHUNK_DAYS), end)
            self._chunks.append((cur, chunk_end))
            cur = chunk_end
        log.info(
            "Scanner %d bolker à %dd for %d pids",
            len(self._chunks),
            self._CHUNK_DAYS,
            len(wanted_pids),
        )

    def start(self) -> None:
        endpoint = EndPoints.PROTOBUF_DEMO_HOST
        log.info("Connecting til %s:%s ...", endpoint, EndPoints.PROTOBUF_PORT)
        self.client = Client(endpoint, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

    def _on_connected(self, client: Client) -> None:
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
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = self.creds.account_id
            req.accessToken = self.creds.access_token
            self.client.send(req)
        elif pt == ProtoOAAccountAuthRes().payloadType:
            log.info("[AUTH] OK — starter deal-scan")
            self._request_next_chunk()
        elif pt == ProtoOADealListRes().payloadType:
            res = ProtoOADealListRes()
            res.ParseFromString(msg.payload)
            self._handle_chunk(res)
            self._request_next_chunk()
        elif pt == ProtoOAErrorRes().payloadType:
            err = ProtoOAErrorRes()
            err.ParseFromString(msg.payload)
            log.error(
                "[ERR] code=%s desc=%s — avbryter uten endringer", err.errorCode, err.description
            )
            self.failed = True
            self._finish()

    def _request_next_chunk(self) -> None:
        if not self._chunks:
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
        log.info("  ← %d deals (hasMore=%s)", len(deals), res.hasMore)
        if res.hasMore:
            log.warning("hasMore=True i bolk — deals kan mangle. Vurder mindre _CHUNK_DAYS.")
        for deal in deals:
            if not deal.HasField("closePositionDetail"):
                continue
            pid = int(deal.positionId)
            if pid not in self.wanted:
                continue
            cpd = deal.closePositionDetail
            money_digits = cpd.moneyDigits if cpd.HasField("moneyDigits") else 2
            divisor = 10**money_digits
            self.closes[pid].append(
                {
                    "deal_id": int(deal.dealId),
                    "ts": datetime.fromtimestamp(deal.executionTimestamp / 1000, tz=timezone.utc),
                    "price": deal.executionPrice,
                    "gross": cpd.grossProfit / divisor,
                    "swap": cpd.swap / divisor,
                    "commission": cpd.commission / divisor,
                }
            )

    def _finish(self) -> None:
        if self.client is not None:
            try:
                self.client.stopService()
            except Exception:
                pass
        if reactor.running:  # type: ignore[attr-defined]
            reactor.callLater(0.5, reactor.stop)  # type: ignore[attr-defined]


def merge(
    entries: list[dict], dups: dict[int, list[int]], closes: dict[int, list[dict]]
) -> tuple[list[dict], list[str], list[int]]:
    """Bygg ny entry-liste. Returnerer (nye entries, rapportlinjer, urørte pids)."""
    drop: set[int] = set()
    report: list[str] = []
    untouched: list[int] = []

    for pid, idxs in sorted(dups.items()):
        deal_closes = closes.get(pid)
        if not deal_closes:
            untouched.append(pid)
            continue
        canon = pick_canonical(entries, idxs)
        e = entries[canon]
        sig = e.get("signal") or {}

        # Dedup på deal_id (samme deal kan komme i overlappende bolker)
        seen: set[int] = set()
        uniq = [
            d
            for d in sorted(deal_closes, key=lambda d: d["ts"])
            if not (d["deal_id"] in seen or seen.add(d["deal_id"]))
        ]
        gross = sum(d["gross"] for d in uniq)
        swap = sum(d["swap"] for d in uniq)
        commission = sum(d["commission"] for d in uniq)
        net = gross + swap + commission
        last = uniq[-1]

        old_pnls = [
            ((entries[i].get("pnl") or {}).get("pnl_usd"), entries[i].get("exit_reason"))
            for i in idxs
        ]
        exit_reason = _classify_exit_reason(
            last["price"], sig.get("entry") or 0.0, sig.get("stop"), sig.get("t1")
        )
        e["closed_at"] = last["ts"].strftime("%Y-%m-%d %H:%M timezone.utc")
        e["result"] = "win" if net > 0 else ("loss" if net < 0 else "managed")
        e["exit_reason"] = exit_reason
        e["pnl"] = {
            "close_price": round(last["price"], 5),
            "pnl_usd": round(net, 2),
            "gross_profit": round(gross, 2),
            "swap": round(swap, 2),
            "commission": round(commission, 2),
            "backfilled": True,
            "merged_duplicates": len(idxs) - 1,
        }
        drop.update(i for i in idxs if i != canon)
        report.append(
            f"pid={pid:<9} {sig.get('instrument', '?'):<10} {len(idxs)} entries -> 1  "
            f"ekte: {e['result']}/{exit_reason} ${net:+.2f} ({len(uniq)} close-deals)  "
            f"gamle pnl: {[p for p, _ in old_pnls]}"
        )

    new_entries = [e for i, e in enumerate(entries) if i not in drop]
    return new_entries, report, untouched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log-path", type=Path, default=LOG_PATH)
    ap.add_argument("--apply", action="store_true", help="Skriv endringer (default dry-run)")
    args = ap.parse_args(argv)

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
    dups = find_duplicates(entries)
    if not dups:
        log.info("Ingen duplikate position_ids — ingenting å gjøre.")
        return 0
    n_dup_entries = sum(len(v) for v in dups.values())
    log.info("Fant %d duplikate pids (%d entries totalt)", len(dups), n_dup_entries)

    # Valider kanonisk-valg FØR vi kontakter broker — feiler heller tidlig
    for idxs in dups.values():
        pick_canonical(entries, idxs)

    oldest = min(
        (
            _parse_log_ts(entries[i].get("timestamp"))
            for v in dups.values()
            for i in v
            if _parse_log_ts(entries[i].get("timestamp"))
        ),
        default=datetime.now(timezone.utc) - timedelta(days=45),
    )
    scanner = DealScanner(creds, set(dups), oldest)
    scanner.start()
    reactor.run()  # type: ignore[attr-defined]

    if scanner.failed:
        log.error("Deal-scan feilet — ingen endringer gjort.")
        return 1

    new_entries, report, untouched = merge(entries, dups, scanner.closes)
    for line in report:
        log.info("  %s", line)
    if untouched:
        log.warning("Pids UTEN close-deal i cTrader-historikk (urørt): %s", untouched)
    log.info(
        "Resultat: %d -> %d entries (%d fjernet, %d pids merget, %d urørt)",
        len(entries),
        len(new_entries),
        len(entries) - len(new_entries),
        len(report),
        len(untouched),
    )

    if not args.apply:
        log.info("DRY-RUN — kjør med --apply for å skrive.")
        return 0

    now = datetime.now(timezone.utc)
    backup = args.log_path.with_suffix(
        args.log_path.suffix + f".bak-premerge-{now.strftime('%Y%m%dT%H%M%S')}"
    )
    shutil.copy2(args.log_path, backup)
    raw["entries"] = new_entries
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
