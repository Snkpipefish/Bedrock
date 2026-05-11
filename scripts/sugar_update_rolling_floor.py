"""Kvartalsvis oppdatering av sugar.yaml::min_score_publish (rolling 5-yr floor).

Adresserer punkt 4 fra analytiker-peer-review (`docs/sugar_handover_prompt.md`):
statisk floor antar regime-stasjonaritet; sukker har minimum 2 regimer
(oversupply 2017-2020, shortage-press 2023+). Floor-ediskoveri-spread
4.95-8.56 (median 7.03) → statisk floor=5 er upassende i dagens regime.

Kjører:
1. Orchestrator-replay for siste 5 år (BUY + SELL, h=180d). 5 år ≈ 260
   ukentlige signaler per retning.
2. Finner laveste score-terskel der hit-rate ≥ 55% og n ≥ 30 per retning.
3. Skriver ny `min_score_publish` til sugar.yaml hvis Δ > 0.5 vs nåværende.
4. Logger til `data/_meta/sugar_floor_history.jsonl` (audit-trail).
5. Skriver state-fil `data/_meta/sugar_rolling_floor.json` med metadata.

Bruk:
    PYTHONPATH=src python scripts/sugar_update_rolling_floor.py --dry-run
    PYTHONPATH=src python scripts/sugar_update_rolling_floor.py --apply

Designet for kvartalsvis kjøring via systemd-user-timer
(`bedrock-rolling-floor-sugar.timer`).
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bedrock.backtest import BacktestConfig, run_orchestrator_replay
from bedrock.data.store import DataStore

DB_PATH = Path("/home/pc/bedrock/data/bedrock.db")
INSTRUMENTS_DIR = Path("config/instruments")
SUGAR_YAML = Path("config/instruments/sugar.yaml")
STATE_PATH = Path("data/_meta/sugar_rolling_floor.json")
HISTORY_PATH = Path("data/_meta/sugar_floor_history.jsonl")
LOOKBACK_YEARS = 5
HORIZON_DAYS = 180  # sweet-spot fra v6 backtest
TARGET_HIT_RATE = 0.55
MIN_SAMPLES = 30
HIT_THRESHOLD_PCT = 3.0  # |return| ≥ 3% counts as hit
APPLY_THRESHOLD = 0.5  # Δ vs current floor må være > 0.5 for å oppdatere


def find_floor(
    scores: list[float],
    hits: list[bool],
    target_hr: float = TARGET_HIT_RATE,
    min_n: int = MIN_SAMPLES,
) -> float | None:
    """Returner laveste score-terskel der hit-rate ≥ target_hr og n ≥ min_n."""
    if not scores:
        return None
    paired = sorted(zip(scores, hits, strict=True), reverse=True)
    candidates: list[tuple[float, float, int]] = []
    for thresh in sorted({round(s * 2) / 2 for s in scores}, reverse=True):
        sub = [(s, h) for s, h in paired if s >= thresh]
        if len(sub) < min_n:
            continue
        hr = sum(1 for _, h in sub if h) / len(sub)
        candidates.append((float(thresh), hr, len(sub)))
    valid = [c for c in candidates if c[1] >= target_hr]
    if not valid:
        return None
    return min(valid, key=lambda c: c[0])[0]


def compute_floor_for_direction(
    store: DataStore,
    direction: str,
    from_date: date,
    to_date: date,
) -> dict[str, float | int | None]:
    cfg = BacktestConfig(
        instrument="Sugar",
        horizon_days=HORIZON_DAYS,
        from_date=from_date,
        to_date=to_date,
    )
    print(
        f"[{direction.upper()}] orchestrator-replay {from_date} → {to_date}...",
        flush=True,
    )
    result = run_orchestrator_replay(
        store,
        cfg,
        instruments_dir=str(INSTRUMENTS_DIR),
        direction=direction,
        step_days=7,
    )
    if direction.lower() == "buy":
        scores = [float(s.score or 0) for s in result.signals if s.score is not None]
        hits = [float(s.forward_return_pct) >= HIT_THRESHOLD_PCT for s in result.signals]
    else:
        scores = [float(s.score or 0) for s in result.signals if s.score is not None]
        hits = [float(s.forward_return_pct) <= -HIT_THRESHOLD_PCT for s in result.signals]

    floor = find_floor(scores, hits)
    n_total = len(scores)
    n_at_floor = sum(1 for s in scores if floor is not None and s >= floor) if floor else 0
    return {
        "floor": floor,
        "n_total": n_total,
        "n_at_floor": n_at_floor,
        "hit_rate_at_floor": (
            sum(1 for s, h in zip(scores, hits, strict=True) if floor and s >= floor and h)
            / max(n_at_floor, 1)
            if floor
            else None
        ),
    }


def read_current_floor(yaml_path: Path) -> dict[str, float]:
    """Parse min_score_publish fra sugar.yaml. Streng linje-pattern."""
    text = yaml_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("min_score_publish:"):
            payload = s.split(":", 1)[1]
            # Strip trailing YAML-comment ("{...}  # rolling 5y, oppdatert ...").
            comment_idx = payload.find("#")
            if comment_idx >= 0:
                payload = payload[:comment_idx]
            payload = payload.strip()
            if payload.startswith("{") and payload.endswith("}"):
                inner = payload[1:-1]
                out: dict[str, float] = {}
                for part in inner.split(","):
                    k, _, v = part.strip().partition(":")
                    out[k.strip()] = float(v.strip())
                return out
            return {"buy": float(payload), "sell": float(payload)}
    raise ValueError(f"min_score_publish ikke funnet i {yaml_path}")


def write_new_floor(yaml_path: Path, new_buy: float, new_sell: float) -> None:
    """In-place oppdatering av min_score_publish-linjen."""
    text = yaml_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    today = date.today().isoformat()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith("min_score_publish:"):
            indent = line[: len(line) - len(line.lstrip())]
            # Round to 1 decimal — integer when fractional==0.
            buy_str = f"{new_buy:.1f}"
            sell_str = f"{new_sell:.1f}"
            out.append(
                f"{indent}min_score_publish: "
                f"{{buy: {buy_str}, sell: {sell_str}}}  "
                f"# rolling 5y, oppdatert {today}\n"
            )
            replaced = True
        else:
            out.append(line)
    if not replaced:
        raise ValueError(f"min_score_publish-linje ikke funnet i {yaml_path}")
    yaml_path.write_text("".join(out), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Skriv ny floor til sugar.yaml (default: dry-run rapport).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skriv selv om Δ floor < {APPLY_THRESHOLD} (overstyrer dampener).",
    )
    args = parser.parse_args()

    today = date.today()
    from_date = today - timedelta(days=365 * LOOKBACK_YEARS)

    store = DataStore(DB_PATH)
    buy_result = compute_floor_for_direction(store, "buy", from_date, today)
    sell_result = compute_floor_for_direction(store, "sell", from_date, today)

    print()
    print(f"=== Rolling {LOOKBACK_YEARS}yr floor-anbefaling for Sugar ===")
    print(
        f"BUY:  floor={buy_result['floor']!r}  n={buy_result['n_total']}  "
        f"n@floor={buy_result['n_at_floor']}  "
        f"hr@floor={buy_result['hit_rate_at_floor']!r}"
    )
    print(
        f"SELL: floor={sell_result['floor']!r}  n={sell_result['n_total']}  "
        f"n@floor={sell_result['n_at_floor']}  "
        f"hr@floor={sell_result['hit_rate_at_floor']!r}"
    )

    current = read_current_floor(SUGAR_YAML)
    print(f"Nåværende sugar.yaml: {current}")

    new_buy = float(buy_result["floor"]) if buy_result["floor"] is not None else current["buy"]
    new_sell = float(sell_result["floor"]) if sell_result["floor"] is not None else current["sell"]

    delta_buy = new_buy - current["buy"]
    delta_sell = new_sell - current["sell"]

    print(f"Δ buy: {delta_buy:+.2f}, Δ sell: {delta_sell:+.2f}")

    significant = abs(delta_buy) > APPLY_THRESHOLD or abs(delta_sell) > APPLY_THRESHOLD

    state = {
        "as_of": today.isoformat(),
        "lookback_years": LOOKBACK_YEARS,
        "horizon_days": HORIZON_DAYS,
        "target_hit_rate": TARGET_HIT_RATE,
        "min_samples": MIN_SAMPLES,
        "buy_floor": new_buy,
        "sell_floor": new_sell,
        "buy_n_total": buy_result["n_total"],
        "sell_n_total": sell_result["n_total"],
        "buy_n_at_floor": buy_result["n_at_floor"],
        "sell_n_at_floor": sell_result["n_at_floor"],
        "current_yaml_buy": current["buy"],
        "current_yaml_sell": current["sell"],
        "delta_buy": delta_buy,
        "delta_sell": delta_sell,
        "significant": significant,
        "applied": False,
    }

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if args.apply and (significant or args.force):
        write_new_floor(SUGAR_YAML, new_buy, new_sell)
        state["applied"] = True
        print(f"OPPDATERT sugar.yaml: buy={new_buy}, sell={new_sell}")
    else:
        if not significant:
            print(f"Δ < {APPLY_THRESHOLD} — ingen oppdatering (bruk --force for å overstyre).")
        elif not args.apply:
            print("Dry-run: bruk --apply for å skrive til sugar.yaml.")

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"State skrevet: {STATE_PATH}")

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history_entry = {**state, "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history_entry) + "\n")
    print(f"History appended: {HISTORY_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
