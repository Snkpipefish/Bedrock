"""Forward-syklus vs current-syklus A/B-test for sukker outlook-familie.

Analytiker E-validering: forward-syklus skal gi høyere score-utslag
i feb-mar enn current-syklus. Hvis ikke, er driver-implementasjonen feil.

Sammenligner outlook-familien isolert mellom:
- A) current-cycle: [0.7,0.7,0.8,0.9,1.0,1.0,1.0,1.0,0.9,0.7,0.6,0.6]
- B) forward-cycle: [1.0,1.0,0.9,0.7,0.6,0.7,0.8,0.9,1.0,0.9,0.8,0.9]

Walk-forward 2018-2026 på A+ BUY h=180d (sweet spot fra backtest 5).
Suksess: forward-cycle Sharpe-løft ≥ 0.20.
"""

from __future__ import annotations

import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import yaml

from bedrock.backtest import BacktestConfig, run_orchestrator_replay
from bedrock.data.store import DataStore

DEFAULT_DB = "data/bedrock.db"
INSTRUMENTS_DIR = Path("config/instruments")
HORIZON = 180
DIRECTION = "buy"
STEP_DAYS = 7
OUT = Path("docs/sugar_seasonal_ab_2026-05.md")

CURRENT_CYCLE = [0.7, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 0.9, 0.7, 0.6, 0.6]
FORWARD_CYCLE = [1.0, 1.0, 0.9, 0.7, 0.6, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.9]


def run_with_seasonal(monthly_scores: list[float], label: str) -> dict:
    """Lag temp config med spesifikk seasonal mapping og kjør backtest."""
    temp_dir = Path(f"/tmp/seasonal_ab_{label}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    shutil.copytree(INSTRUMENTS_DIR, temp_dir)

    yaml_path = temp_dir / "sugar.yaml"
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    # Erstatt monthly_scores i seasonal_stage-driveren
    families = cfg.get("families", {})
    outlook = families.get("outlook", {})
    drivers = outlook.get("drivers", [])
    for d in drivers:
        if d.get("name") == "seasonal_stage":
            d.setdefault("params", {})["monthly_scores"] = list(monthly_scores)

    with open(yaml_path, "w") as f:
        yaml.dump(cfg, f, sort_keys=False, allow_unicode=True)

    today = date.today()
    from_date = today - timedelta(days=365 * 8)  # 8 års vindu

    store = DataStore(Path(DEFAULT_DB))
    bcfg = BacktestConfig(
        instrument="Sugar",
        horizon_days=HORIZON,
        from_date=from_date,
        to_date=today,
    )
    t0 = time.time()
    result = run_orchestrator_replay(
        store,
        bcfg,
        instruments_dir=str(temp_dir),
        direction=DIRECTION,
        step_days=STEP_DAYS,
    )
    elapsed = time.time() - t0

    a_plus = [s for s in result.signals if s.grade == "A+"]
    a_grade = [s for s in result.signals if s.grade == "A"]
    a_plus_returns = [s.forward_return_pct for s in a_plus]
    a_returns = [s.forward_return_pct for s in a_grade]

    import math
    import statistics

    def sharpe(rets: list[float]) -> float:
        if len(rets) < 2:
            return 0.0
        std = statistics.stdev(rets)
        if std == 0:
            return 0.0
        return statistics.mean(rets) / std * math.sqrt(365 / 7 / 4)

    return {
        "label": label,
        "n_a_plus": len(a_plus),
        "hr_a_plus": sum(1 for s in a_plus if s.hit) / len(a_plus) if a_plus else 0,
        "avg_a_plus": statistics.mean(a_plus_returns) if a_plus_returns else 0,
        "sharpe_a_plus": sharpe(a_plus_returns),
        "n_a": len(a_grade),
        "hr_a": sum(1 for s in a_grade if s.hit) / len(a_grade) if a_grade else 0,
        "avg_a": statistics.mean(a_returns) if a_returns else 0,
        "sharpe_a": sharpe(a_returns),
        "elapsed_s": elapsed,
    }


def main() -> int:
    print(f"[{time.strftime('%H:%M:%S')}] A/B-test: current vs forward-syklus")
    a = run_with_seasonal(CURRENT_CYCLE, "current_cycle")
    print(
        f"[{time.strftime('%H:%M:%S')}] A done: n={a['n_a_plus']} A+, sharpe={a['sharpe_a_plus']:.2f}"
    )
    b = run_with_seasonal(FORWARD_CYCLE, "forward_cycle")
    print(
        f"[{time.strftime('%H:%M:%S')}] B done: n={b['n_a_plus']} A+, sharpe={b['sharpe_a_plus']:.2f}"
    )

    delta_sharpe = b["sharpe_a_plus"] - a["sharpe_a_plus"]
    delta_avg = b["avg_a_plus"] - a["avg_a_plus"]
    delta_hr = b["hr_a_plus"] - a["hr_a_plus"]

    lines: list[str] = []
    lines.append("# Sugar seasonal_stage A/B-test\n")
    lines.append(f"*Generert {date.today()}. 8 års vindu (h={HORIZON}d, BUY, A+ BUY-bøtte).*\n")

    lines.append("## Resultater\n")
    lines.append("| Variant | n A+ | hit-rate | avg ret | Sharpe |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in (a, b):
        lines.append(
            f"| {r['label']} | {r['n_a_plus']} | "
            f"{r['hr_a_plus'] * 100:.1f}% | {r['avg_a_plus']:+.2f}% | "
            f"{r['sharpe_a_plus']:+.2f} |"
        )
    lines.append("")

    lines.append("## Forward-syklus vs current-syklus\n")
    lines.append(f"- Δ Sharpe: **{delta_sharpe:+.2f}** (suksess-kriterium: ≥ +0.20)")
    lines.append(f"- Δ hit-rate: {delta_hr * 100:+.1f}pp")
    lines.append(f"- Δ avg return: {delta_avg:+.2f}pp")
    if delta_sharpe >= 0.20:
        lines.append("- **Konklusjon: ✅ Forward-syklus validert** — beholdes.")
    elif delta_sharpe >= 0:
        lines.append("- **Konklusjon: ⚠ Marginal forbedring** — forward-syklus gir lite gain.")
    else:
        lines.append("- **Konklusjon: ❌ Forward-syklus underperformer** — vurder å re-vurdere.")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
