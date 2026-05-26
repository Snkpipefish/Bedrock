#!/usr/bin/env python3
"""Beregn kapitalbehov for bedrock-bot basert på historisk trade-log.

Trekker fra ``data/bot/signal_log.json``:

- Risk per trade (median + p90)
- Max samtidig allokering når flere posisjoner åpne
- Equity-curve og max drawdown
- Snitt vs verste tap
- Anbefalt minimum konto-størrelse

Anbefalingen følger industristandard: konto må tåle (a) verste enkelt-
drawdown × 2x buffer, (b) max samtidig risk × 3-5x buffer, og (c)
minimum lot-størrelse hos broker. Vi rapporterer alle tre så operatør
kan velge.

Bruk:
    .venv/bin/python scripts/analyze_capital_requirement.py
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "signal_log.json"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = raw.replace(" timezone.utc", "+00:00").replace(" ", "T")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _bar(x: float, scale: float = 80.0) -> str:
    """ASCII-bar for risk-distribusjon."""
    n = min(int(x * scale), 80)
    return "█" * n


def main() -> int:
    d = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    entries = d["entries"]

    closed = [e for e in entries if e.get("closed_at")]
    losses = [e for e in closed if e.get("result") == "loss"]
    wins = [e for e in closed if e.get("result") == "win"]

    print("═" * 72)
    print(" BEDROCK BOT — KAPITALANALYSE")
    print("═" * 72)
    print(f" Trade-log:    {LOG_PATH}")
    print(f" Totalt:       {len(entries)} entries ({len(closed)} closed)")
    print(f" Wins / Loss:  {len(wins)} / {len(losses)}")
    print()

    # ── Per trade: risk-størrelse ────────────────────────────────
    # USD-risk ≈ |pnl_usd| for tape (SL-traffet ≈ planlagt risiko).
    # For vinnere bruker vi r:r og avstand som proxy.
    loss_pnls = [abs((e.get("pnl") or {}).get("pnl_usd", 0) or 0) for e in losses]
    loss_pnls = [v for v in loss_pnls if v > 0]
    if not loss_pnls:
        print("Ingen tap-data — kan ikke estimere risk.")
        return 1

    median_risk = statistics.median(loss_pnls)
    mean_risk = statistics.mean(loss_pnls)
    p90_risk = statistics.quantiles(loss_pnls, n=10)[8] if len(loss_pnls) >= 10 else max(loss_pnls)
    max_loss = max(loss_pnls)

    print(" ── PER TRADE: USD-RISK (basert på faktiske tap) ──")
    print(f"   Median risk:    ${median_risk:>8.2f}")
    print(f"   Snitt risk:     ${mean_risk:>8.2f}")
    print(f"   P90 risk:       ${p90_risk:>8.2f}")
    print(f"   Verste tap:     ${max_loss:>8.2f}")
    print()

    # ── Samtidig allokering ──────────────────────────────────────
    # For hver trade har vi opened/closed_at. Sweep over tidslinjen
    # og finn max samtidig (#trades og sum-risk).
    events = []
    for e in closed:
        op = _parse_ts(e.get("timestamp"))
        cl = _parse_ts(e.get("closed_at"))
        risk = abs((e.get("pnl") or {}).get("pnl_usd", 0) or 0)
        if e.get("result") == "win":
            # Vinnere brukte også risk-margin; estimer via median-risk
            risk = median_risk
        if op and cl:
            events.append((op, +1, risk))
            events.append((cl, -1, risk))

    events.sort(key=lambda x: x[0])
    cur_count = 0
    cur_risk = 0.0
    max_count = 0
    max_risk = 0.0
    max_count_time: datetime | None = None
    max_risk_time: datetime | None = None
    for ts, delta, risk in events:
        cur_count += delta
        cur_risk += delta * risk
        if cur_count > max_count:
            max_count = cur_count
            max_count_time = ts
        if cur_risk > max_risk:
            max_risk = cur_risk
            max_risk_time = ts

    print(" ── SAMTIDIG ALLOKERING (over historikken) ──")
    print(
        f"   Max trades åpne samtidig: {max_count}  ({max_count_time.strftime('%Y-%m-%d %H:%M') if max_count_time else '?'})"
    )
    print(
        f"   Max samtidig risk:        ${max_risk:>7.2f}  ({max_risk_time.strftime('%Y-%m-%d %H:%M') if max_risk_time else '?'})"
    )
    print()

    # ── Equity curve + drawdown ──────────────────────────────────
    # Sort closed trades by close-time
    sorted_closed = sorted(
        [(e, _parse_ts(e.get("closed_at"))) for e in closed],
        key=lambda x: x[1] or datetime.min,
    )
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_dt: datetime | None = None
    for e, ts in sorted_closed:
        pnl = (e.get("pnl") or {}).get("pnl_usd", 0) or 0
        eq += pnl
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
            max_dd_dt = ts

    final_eq = eq
    print(" ── EQUITY-CURVE OVER HELE HISTORIKKEN ──")
    print(f"   Slutt-balanse:   ${final_eq:>+8.2f}")
    print(f"   Toppnivå:        ${peak:>+8.2f}")
    print(
        f"   Max drawdown:    ${max_dd:>+8.2f}  ({max_dd_dt.strftime('%Y-%m-%d') if max_dd_dt else '?'})"
    )
    if peak > 0:
        print(f"   Drawdown / peak: {100 * max_dd / peak:.1f} %")
    print()

    # ── Per instrument: top 10 by total PnL ──────────────────────
    by_instr_pnl: dict[str, float] = defaultdict(float)
    by_instr_n: dict[str, int] = defaultdict(int)
    for e in closed:
        instr = (e.get("signal") or {}).get("instrument", "?")
        pnl = (e.get("pnl") or {}).get("pnl_usd", 0) or 0
        by_instr_pnl[instr] += pnl
        by_instr_n[instr] += 1

    print(" ── PER INSTRUMENT (top 8 by |total PnL|) ──")
    items = sorted(by_instr_pnl.items(), key=lambda kv: -abs(kv[1]))[:8]
    for instr, total in items:
        n = by_instr_n[instr]
        sign = "+" if total >= 0 else "-"
        print(
            f"   {instr:12s} n={n:3d}  total ${total:>+8.2f}  ({sign}${abs(total) / n:.0f}/trade snitt)"
        )
    print()

    # ── Anbefaling ───────────────────────────────────────────────
    # Tre regler, vi tar max:
    # 1. Max samtidig risk × 5x buffer (boten kan ha flere tape samtidig)
    # 2. Max drawdown × 2x buffer (må overleve verste streak)
    # 3. Median risk × 100 (= 1 % risk per trade på $X-konto)
    # cTrader demo bruker typisk ingen margin-grense for små lots,
    # men live krever ~1:30 leverage → notional × (1/30).
    rec_a = max_risk * 5
    rec_b = max_dd * 2
    rec_c = median_risk * 100  # risk pct=1% antas
    rec = max(rec_a, rec_b, rec_c, 500.0)  # minimum $500 floor

    print(" ── ANBEFALT KONTO-STØRRELSE ──")
    print(f"   (A) Max samtidig risk × 5×: ${rec_a:>7.0f}")
    print(f"   (B) Max drawdown × 2×:      ${rec_b:>7.0f}")
    print(f"   (C) 1% risk per trade:      ${rec_c:>7.0f}")
    print("   ─────────────────────────────────────")
    print(f"   MIN KONTO (max av A/B/C):   ${rec:>7.0f}")
    print(f"   ANBEFALT (komfort-buffer):  ${rec * 1.5:>7.0f}")
    print()
    print(" Forklaring:")
    print(" - (A) 5× max samtidig risk: dekker scenarier hvor 2-3 trades")
    print("   triggrer SL nær hverandre i samme retning")
    print(" - (B) 2× verste drawdown: må overleve verste observerte streak")
    print("   med margin før daily-loss-gate stenger ned")
    print(" - (C) 1 % risk-policy: $100k konto = $1k risk/trade. Skalering")
    print("   antar bot tar median-risk-størrelse")
    print()
    print("═" * 72)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
