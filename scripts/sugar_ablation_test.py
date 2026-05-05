"""Familie-vekt-ablation for sukker — drop én familie ad gangen, mål Sharpe.

Adresserer analytiker-anbefaling C.2 / D.6: kjør drop-one-out for hver
familie og mål hvilke som faktisk bidrar til A+ BUY 90d-edge. Familier
som ikke gir > 0.15 Sharpe-tap bør tak-reduseres.

Strategi: ladbar — re-bruker samme orchestrator-replay som backtest, men
med modifisert YAML-config (vekt=0 på én familie ad gangen). Kjøres på
codespacen siden hver ablation = en backtest-runde.

Output: docs/sugar_ablation_2026-05.md
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import yaml

DEFAULT_DB = "data/bedrock.db"
INSTRUMENTS_DIR = Path("config/instruments")
SUGAR_YAML = INSTRUMENTS_DIR / "sugar.yaml"
HORIZON = 90  # SWING — analytikerens flaggship
DIRECTION = "buy"
STEP_DAYS = 7
OUT = Path("docs/sugar_ablation_2026-05.md")
SHARPE_PERIODS_PER_YEAR = 365 / 7 / 4  # ukentlig 90d → ~13 obs/år


def annualized_sharpe(returns: list[float]) -> float:
    import statistics

    if len(returns) < 2:
        return 0.0
    std = statistics.stdev(returns)
    if std == 0:
        return 0.0
    return statistics.mean(returns) / std * math.sqrt(SHARPE_PERIODS_PER_YEAR)


def run_ablation(family_to_zero: str | None) -> dict:
    """Last sugar.yaml, sett family weight=0 på `family_to_zero`,
    skriv midlertidig fil, kjør backtest, returner stats for A+ BUY."""
    from bedrock.backtest import (
        BacktestConfig,
        run_orchestrator_replay,
        summary_stats,
    )
    from bedrock.data.store import DataStore

    # Lag temp instrument-dir med modifisert sugar.yaml
    temp_dir = Path(f"/tmp/ablation_{family_to_zero or 'baseline'}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    shutil.copytree(INSTRUMENTS_DIR, temp_dir)

    if family_to_zero is not None:
        with open(temp_dir / "sugar.yaml") as f:
            cfg = yaml.safe_load(f)
        # AgriRules krever weight > 0 (Pydantic gt=0). Setter til 0.001
        # — funksjonelt nær null bidrag i additive_sum, men passerer
        # validering. Også må vi overstyre parent (family_agri.yaml)
        # ved å eksplisitt sette familien i child config.
        cfg.setdefault("families", {})
        if family_to_zero not in cfg["families"]:
            cfg["families"][family_to_zero] = {
                "weight": 0.001,
                "drivers": [{"name": "noaa_oni_index", "weight": 1.0, "params": {}}],
            }
        else:
            cfg["families"][family_to_zero]["weight"] = 0.001
        with open(temp_dir / "sugar.yaml", "w") as f:
            yaml.dump(cfg, f, sort_keys=False, allow_unicode=True)

    today = date.today()
    from_date = today - timedelta(days=365 * 14)

    store = DataStore(Path(DEFAULT_DB))
    bcfg = BacktestConfig(
        instrument="Sugar",
        horizon_days=HORIZON,
        from_date=from_date,
        to_date=today,
    )
    t0 = time.time()
    result = run_orchestrator_replay(
        store, bcfg,
        instruments_dir=str(temp_dir),
        direction=DIRECTION,
        step_days=STEP_DAYS,
    )
    elapsed = time.time() - t0

    a_plus_returns = [s.forward_return_pct for s in result.signals if s.grade == "A_plus"]
    a_returns = [s.forward_return_pct for s in result.signals if s.grade == "A"]
    a_plus_hits = sum(1 for s in result.signals if s.grade == "A_plus" and s.hit)

    return {
        "family_dropped": family_to_zero or "(baseline)",
        "n_a_plus": len(a_plus_returns),
        "hit_rate_a_plus": a_plus_hits / len(a_plus_returns) if a_plus_returns else 0.0,
        "avg_a_plus": sum(a_plus_returns) / len(a_plus_returns) if a_plus_returns else 0.0,
        "sharpe_a_plus": annualized_sharpe(a_plus_returns),
        "n_a": len(a_returns),
        "avg_a": sum(a_returns) / len(a_returns) if a_returns else 0.0,
        "sharpe_a": annualized_sharpe(a_returns),
        "elapsed_s": elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    families = ["outlook", "yield", "positioning", "enso", "unica", "cross", "analog"]

    results = []
    print(f"[{time.strftime('%H:%M:%S')}] kjører baseline...", flush=True)
    results.append(run_ablation(None))
    for f in families:
        print(f"[{time.strftime('%H:%M:%S')}] dropper {f}...", flush=True)
        results.append(run_ablation(f))

    baseline_sharpe = results[0]["sharpe_a_plus"]

    lines: list[str] = []
    lines.append("# Sugar familie-vekt-ablation\n")
    lines.append(f"*Generert {date.today()}. Drop-one-out på A+ BUY 90d-bøtta. "
                 f"Baseline = full sugar.yaml. Vinduet = 14 år.*\n")
    lines.append("## Resultater\n")
    lines.append("| Dropped | n A+ | A+ hit-rate | A+ avg | A+ Sharpe | Δ Sharpe vs baseline | Tolkning |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for r in results:
        delta = r["sharpe_a_plus"] - baseline_sharpe if r["family_dropped"] != "(baseline)" else 0.0
        if r["family_dropped"] == "(baseline)":
            tolk = "ref"
        elif delta < -0.15:
            tolk = "✅ kritisk — hold tak"
        elif delta < -0.05:
            tolk = "⚠ moderat bidrag"
        elif delta < 0.05:
            tolk = "❌ ingen effekt — reduser tak"
        else:
            tolk = "🔥 negativ! drop helt"
        lines.append(
            f"| {r['family_dropped']} | {r['n_a_plus']} | "
            f"{r['hit_rate_a_plus']*100:.1f}% | {r['avg_a_plus']:+.2f}% | "
            f"{r['sharpe_a_plus']:+.2f} | {delta:+.2f} | {tolk} |"
        )
    lines.append("")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(f"Skrevet {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
