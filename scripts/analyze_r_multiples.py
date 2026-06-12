#!/usr/bin/env python3
"""R-multiple-analyse av signal_log.json — realisert edge per grade/horisont.

Bakgrunn (session 2026-06-12): USD-PnL-aggregater blander lot-størrelser
og instrument-skala, så grade/horisont-sammenligninger på USD er skjeve.
R-multiple normaliserer hver trade mot sin egen planlagte risiko:

    BUY:  R = (close - entry) / (entry - stop)
    SELL: R = (entry - close) / (stop - entry)

Pris-basert (ikke pips/USD) → enhetsfri og uavhengig av pip-konvensjon
per instrument. close hentes fra pnl.close_price i loggen.

Begrensninger:
- Trailing/partial-closes logges som ett close-event; R reflekterer
  siste close-pris, ikke vektet snitt over partials.
- Entries uten entry/stop/close_price (eldre format) skippes og telles.
- SWING-SL-fiksen (15b613b, 2026-06-11) endret stop-geometrien radikalt;
  bruk --since for å skille regimene. Data før fiksen har kunstig trange
  stops → ekstreme |R|-verdier i begge retninger.

Bruk (read-only, trygt mens boten kjører):
    .venv/bin/python scripts/analyze_r_multiples.py
    .venv/bin/python scripts/analyze_r_multiples.py --log data/bot/signal_log.json
    .venv/bin/python scripts/analyze_r_multiples.py --min-n 5 --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "bot" / "signal_log.json"


def compute_r(entry: float, stop: float, close: float, direction: str) -> float | None:
    """Pris-basert R-multiple. None hvis risiko-avstanden er ugyldig (<= 0)."""
    if direction == "BUY":
        risk = entry - stop
        move = close - entry
    elif direction == "SELL":
        risk = stop - entry
        move = entry - close
    else:
        return None
    if risk <= 0:
        return None
    return move / risk


def extract_trades(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Returner (trades med beregnet R, antall skippet)."""
    trades: list[dict[str, Any]] = []
    skipped = 0
    for e in entries:
        if not isinstance(e, dict) or e.get("result") not in ("win", "loss"):
            continue
        sig = e.get("signal") or {}
        pnl = e.get("pnl") if isinstance(e.get("pnl"), dict) else {}
        entry_px = sig.get("entry")
        stop_px = sig.get("stop")
        close_px = pnl.get("close_price")
        direction = str(sig.get("direction") or "").upper()
        if not all(isinstance(v, (int, float)) and v != 0 for v in (entry_px, stop_px, close_px)):
            skipped += 1
            continue
        r = compute_r(float(entry_px), float(stop_px), float(close_px), direction)
        if r is None:
            skipped += 1
            continue
        trades.append(
            {
                "instrument": sig.get("instrument") or "?",
                "direction": direction,
                "horizon": str(sig.get("horizon") or "?").lower(),
                "grade": sig.get("grade") or "?",
                "exit_reason": e.get("exit_reason") or "?",
                "result": e.get("result"),
                "r": r,
                "pnl_usd": float(pnl.get("pnl_usd") or 0.0),
                "timestamp": str(e.get("timestamp") or ""),
            }
        )
    return trades, skipped


def summarize(trades: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    """Aggreger R-statistikk per verdi av `key`."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        groups[str(t[key])].append(t)
    out: dict[str, dict[str, float]] = {}
    for k, ts in groups.items():
        rs = [t["r"] for t in ts]
        wins = sum(1 for t in ts if t["result"] == "win")
        out[k] = {
            "n": len(ts),
            "win_pct": 100.0 * wins / len(ts),
            "avg_r": statistics.mean(rs),
            "median_r": statistics.median(rs),
            "sum_r": sum(rs),
            "pnl_usd": sum(t["pnl_usd"] for t in ts),
        }
    return out


def print_table(title: str, summary: dict[str, dict[str, float]], min_n: int) -> None:
    print(f"\n--- {title} ---")
    print(f"{'gruppe':<22} {'n':>4} {'win%':>6} {'avg R':>7} {'med R':>7} {'sum R':>8} {'USD':>9}")
    for k, s in sorted(summary.items(), key=lambda kv: -kv[1]["sum_r"]):
        flag = "" if s["n"] >= min_n else "  (lav n)"
        print(
            f"{k:<22} {s['n']:>4.0f} {s['win_pct']:>6.1f} {s['avg_r']:>7.2f} "
            f"{s['median_r']:>7.2f} {s['sum_r']:>8.2f} {s['pnl_usd']:>9.2f}{flag}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--min-n", type=int, default=10, help="Flagg grupper under denne n.")
    parser.add_argument("--json", action="store_true", help="Maskinlesbar output.")
    parser.add_argument(
        "--since",
        default=None,
        help="Inkluder kun trades med timestamp >= denne dato (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    raw = json.loads(args.log.read_text())
    entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
    trades, skipped = extract_trades(entries)
    if args.since:
        trades = [t for t in trades if t["timestamp"][:10] >= args.since]
    if not trades:
        print("Ingen trades med komplett entry/stop/close_price.", file=sys.stderr)
        return 1

    dims = ["grade", "horizon", "instrument", "exit_reason", "direction"]
    summaries = {dim: summarize(trades, dim) for dim in dims}
    # Kombinert horisont/grade for gate-beslutninger
    for t in trades:
        t["horizon_grade"] = f"{t['horizon']}/{t['grade']}"
    summaries["horizon_grade"] = summarize(trades, "horizon_grade")

    if args.json:
        print(json.dumps({"n": len(trades), "skipped": skipped, "summaries": summaries}, indent=2))
        return 0

    rs = [t["r"] for t in trades]
    wins = sum(1 for t in trades if t["result"] == "win")
    print(f"Trades med R: {len(trades)}  (skippet: {skipped})")
    print(
        f"Total: win% {100 * wins / len(trades):.1f}  avg R {statistics.mean(rs):.2f}  "
        f"median R {statistics.median(rs):.2f}  sum R {sum(rs):.2f}"
    )
    for dim in ["grade", "horizon", "horizon_grade", "exit_reason", "instrument", "direction"]:
        print_table(dim, summaries[dim], args.min_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
