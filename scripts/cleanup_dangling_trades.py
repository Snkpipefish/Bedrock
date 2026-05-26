#!/usr/bin/env python3
"""Cleanup-script for dangling trade-log-entries.

Finn entries i ``data/bot/signal_log.json`` som mangler ``closed_at``,
kryss-sjekk mot cTrader-state (siste bot RECONCILE-rapport sier "0 åpne
posisjoner"), og marker dangling entries som ``result="lost-close"`` så
log-statistikken blir konsistent.

Bakgrunn (session 2026-05-26): widget viser "7 åpne posisjoner" basert
på entries uten closed_at, men bot's reconcile-pathen sier 0 — det er
historiske entries der close-event aldri ble matchet (bot offline ved
lukking på cTrader). Selve trading er upåvirket; det er kun loggen som
ikke har fanget close-eventene.

Trygt å kjøre flere ganger: idempotent. Endringer skrives via atomisk
tempfile-rename. Lager backup av original-loggen i samme katalog.

Bruk:
    python scripts/cleanup_dangling_trades.py            # dry-run
    python scripts/cleanup_dangling_trades.py --apply    # faktisk skriv
    python scripts/cleanup_dangling_trades.py --apply --min-age-days 1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "signal_log.json"
DEFAULT_BOT_SERVICE = "bedrock-bot.service"

LOST_CLOSE_REASON = "lost-close"
LOST_CLOSE_RESULT = "managed"  # 'managed' brukes når vi ikke vet win/loss


def _parse_log_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = raw.replace(" timezone.utc", "+00:00").replace(" ", "T")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _ctrader_open_count_from_journal() -> int | None:
    """Slå opp siste 'RECONCILE: N åpne posisjoner funnet' i bot-journal.

    Returnerer antall åpne posisjoner per siste reconcile, eller None
    hvis journal ikke kan leses (f.eks. journalctl mangler eller
    user-service ikke kjørt).
    """
    try:
        result = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                DEFAULT_BOT_SERVICE,
                "--since",
                "24 hours ago",
                "--no-pager",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[WARN] journalctl utilgjengelig: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0:
        return None
    # Søk bakover etter siste "RECONCILE: N åpne posisjoner funnet"
    last_count: int | None = None
    for line in result.stdout.splitlines():
        if "[RECONCILE]" in line and "åpne posisjoner funnet" in line:
            try:
                # "[RECONCILE] 0 åpne posisjoner funnet."
                after = line.split("[RECONCILE]")[1].strip()
                n_str = after.split()[0]
                last_count = int(n_str)
            except (ValueError, IndexError):
                continue
    return last_count


def cleanup(
    log_path: Path,
    *,
    min_age_days: int = 1,
    apply: bool = False,
) -> dict:
    """Marker dangling entries som lost-close.

    Args:
        log_path: sti til signal_log.json.
        min_age_days: entries yngre enn dette beholdes som "åpne".
            Default 1 (gir bot tid til å reconcile freshe events).
        apply: hvis False, kjør dry-run uten å skrive.

    Returns:
        Dict med statistikk: scanned, dangling_total, marked,
        kept_recent, ctrader_open_count.
    """
    if not log_path.exists():
        return {"error": f"Log mangler: {log_path}"}

    raw = json.loads(log_path.read_text(encoding="utf-8"))
    entries = raw.get("entries", [])
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=min_age_days)

    ctrader_open = _ctrader_open_count_from_journal()

    dangling = [e for e in entries if not e.get("closed_at")]
    to_mark: list[dict] = []
    kept: list[dict] = []
    for e in dangling:
        ts = _parse_log_ts(e.get("timestamp"))
        if ts is None or ts < cutoff:
            to_mark.append(e)
        else:
            kept.append(e)

    # Sanity: hvis cTrader sier > 0 åpne og vi ville markert ALLE som
    # lost-close, bremse opp. Logg advarsel men fortsett (gamle entries
    # er sjelden tilknyttet aktuelle posisjoner).
    if ctrader_open is not None and ctrader_open > 0:
        print(
            f"[INFO] cTrader rapporterer {ctrader_open} åpne posisjoner "
            f"per siste reconcile. Vi markerer kun entries eldre enn "
            f"{min_age_days}d som lost-close.",
            file=sys.stderr,
        )

    stamp = now.strftime("%Y-%m-%d %H:%M timezone.utc")
    for e in to_mark:
        e["closed_at"] = stamp
        e["result"] = LOST_CLOSE_RESULT
        e["exit_reason"] = LOST_CLOSE_REASON
        # Bevarer original signal-dict + lots/risk_pct/horizon

    summary = {
        "scanned": len(entries),
        "dangling_total": len(dangling),
        "marked": len(to_mark),
        "kept_recent": len(kept),
        "ctrader_open_count": ctrader_open,
        "min_age_days": min_age_days,
    }

    if apply and to_mark:
        backup = log_path.with_suffix(log_path.suffix + f".bak-{now.strftime('%Y%m%dT%H%M%S')}")
        shutil.copy2(log_path, backup)
        raw["last_updated"] = stamp
        # Atomic write
        fd, tmp = tempfile.mkstemp(prefix="signal_log_", suffix=".json", dir=log_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(raw, fp, indent=2, ensure_ascii=False)
            os.replace(tmp, log_path)
            summary["backup"] = str(backup)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    ap.add_argument(
        "--min-age-days",
        type=int,
        default=1,
        help="Marker dangling entries eldre enn dette som lost-close (default 1d)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Skriv endringer til log. Uten denne: dry-run.",
    )
    args = ap.parse_args(argv)

    summary = cleanup(args.log_path, min_age_days=args.min_age_days, apply=args.apply)

    if "error" in summary:
        print(f"FEIL: {summary['error']}", file=sys.stderr)
        return 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Cleanup dangling trades ({mode}) ===")
    print(f"Log:                {args.log_path}")
    print(f"Total entries:      {summary['scanned']}")
    print(f"Dangling (no close): {summary['dangling_total']}")
    print(f"Older than {summary['min_age_days']}d → mark: {summary['marked']}")
    print(f"Younger → keep:     {summary['kept_recent']}")
    ctr = summary["ctrader_open_count"]
    print(
        f"cTrader open (last reconcile): {ctr if ctr is not None else 'ukjent (journal utilgjengelig)'}"
    )
    if args.apply and "backup" in summary:
        print(f"Backup:             {summary['backup']}")
    elif not args.apply and summary["marked"] > 0:
        print()
        print("Kjør med --apply for å faktisk skrive endringer.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
