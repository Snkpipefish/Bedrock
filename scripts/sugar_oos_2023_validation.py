"""OOS 2023 India-eksportforbud-validering for sukker (analytiker-punkt 3).

Adresserer punkt 3 fra analytiker-peer-review (`docs/sugar_handover_prompt.md`):
2023 var India-eksportforbud-regime — Modi-regjeringen forbød eksport av
sukker fra Q2 2023 (etter monsun-svikt). Vi har lagt til:
- `usda_psd_yoy(USDA_PSD_INDIA_SUGAR_PROD_KMT)` (yield-familien, vekt 0.30)
- multi-region `weather_stress` med India 0.30-vekt (yield-familien)

Suksess-kriterium fra handover: India-driver må ha gitt mindre A SELL-
signaler i 2023 enn baseline (uten India-drivere).

Dette skriptet:
1. Re-kjører orchestrator-replay for 2023 Q1-Q3 (jan → sep) BUY + SELL
   med GJELDENDE sugar.yaml (har India-drivere wired).
2. Re-kjører samme periode med en alternativ sugar.yaml hvor India-
   drivere er fjernet/null-vektet ("baseline 2023").
3. Sammenligner SELL-grade-distribusjon (A+ / A / B / C) og snitt-score.
4. Verifiserer at India-drivere SVEKKET A SELL i 2023 (færre A SELL-
   signaler eller lavere SELL-score).

Bruk:
    PYTHONPATH=src python scripts/sugar_oos_2023_validation.py
"""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from bedrock.backtest import BacktestConfig, run_orchestrator_replay
from bedrock.data.store import DataStore

DB_PATH = Path("/home/pc/bedrock/data/bedrock.db")
INSTRUMENTS_DIR = Path("config/instruments")
SUGAR_YAML = Path("config/instruments/sugar.yaml")
OUT_MD = Path("docs/sugar_oos_2023_validation_2026-05.md")
HORIZON_DAYS = 180  # sweet-spot fra v6 backtest
FROM_DATE = date(2023, 1, 1)
TO_DATE = date(2023, 9, 30)  # Q1-Q3 fanger India-forbud-event Q2-Q3
STEP_DAYS = 7


def make_baseline_yaml(src_yaml: Path, dst_yaml: Path) -> None:
    """Lag en kopi av sugar.yaml hvor India-drivere er null-vektet.

    Konkrete endringer:
    1. weather_stress.params.regions.india_maharashtra: 0.30 → 0.0,
       brazil_centro_sul re-vektet 0.55 → 0.79, thailand 0.15 → 0.21
       (sum=1.0)
    2. usda_psd_yoy India: weight 0.30 → 0.0, unica vekter re-balansert
       (sugar_production_yoy 0.45 → 0.64, mix_sugar_pct 0.25 → 0.36).
    """
    text = src_yaml.read_text(encoding="utf-8")

    # 1. Multi-region weather: dropp india, redistribuer til BR/Thailand
    text = re.sub(
        r"(\s+brazil_centro_sul:\s+)0\.55",
        r"\g<1>0.79",
        text,
    )
    text = re.sub(
        r"(\s+india_maharashtra:\s+)0\.30",
        r"\g<1>0.0",
        text,
    )
    text = re.sub(
        r"(\s+thailand_suphan_buri:\s+)0\.15",
        r"\g<1>0.21",
        text,
    )

    # 2. unica-familien: re-balanser usda_psd_yoy India 0.30 → 0.0
    # Først finn unica-driver-blokken og rebalanser.
    text = re.sub(
        r"(\s+- name: unica_change\n\s+weight:\s+)0\.45(\n\s+params:\n\s+metric: sugar_production_yoy)",
        r"\g<1>0.64\g<2>",
        text,
    )
    text = re.sub(
        r"(\s+- name: unica_change\n\s+weight:\s+)0\.25(\n\s+params:\n\s+metric: mix_sugar_pct)",
        r"\g<1>0.36\g<2>",
        text,
    )
    text = re.sub(
        r"(\s+- name: usda_psd_yoy\n\s+weight:\s+)0\.30",
        r"\g<1>0.0",
        text,
    )

    dst_yaml.write_text(text, encoding="utf-8")


def grade_breakdown(signals: list, direction: str) -> dict[str, dict]:
    """Aggreger {grade: {n, hit_rate, avg_return, avg_score}} for signaler."""
    out: dict[str, dict] = {}
    for s in signals:
        g = s.grade or "C"
        bucket = out.setdefault(g, {"n": 0, "hits": 0, "ret_sum": 0.0, "score_sum": 0.0})
        bucket["n"] += 1
        if direction.lower() == "buy":
            hit = float(s.forward_return_pct) >= 3.0
        else:
            hit = float(s.forward_return_pct) <= -3.0
        if hit:
            bucket["hits"] += 1
        bucket["ret_sum"] += float(s.forward_return_pct)
        bucket["score_sum"] += float(s.score or 0)
    for g, b in out.items():
        n = b["n"]
        b["hit_rate"] = b["hits"] / n if n else 0.0
        b["avg_return"] = b["ret_sum"] / n if n else 0.0
        b["avg_score"] = b["score_sum"] / n if n else 0.0
    return out


def fmt_table(prod: dict, base: dict, title: str) -> str:
    lines = [f"### {title}\n"]
    lines.append("| Grade | n (prod) | hr (prod) | avg_score (prod) | n (baseline) | hr (baseline) | avg_score (baseline) |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
    grades = sorted(set(prod.keys()) | set(base.keys()))
    for g in ["A+", "A", "B", "C"]:
        if g not in grades:
            continue
        p = prod.get(g, {})
        b = base.get(g, {})
        lines.append(
            f"| {g} | {p.get('n', 0)} | {p.get('hit_rate', 0)*100:.1f}% | "
            f"{p.get('avg_score', 0):.2f} | {b.get('n', 0)} | "
            f"{b.get('hit_rate', 0)*100:.1f}% | {b.get('avg_score', 0):.2f} |\n"
        )
    lines.append("\n")
    return "".join(lines)


def main() -> int:
    store = DataStore(DB_PATH)

    # Kjør prod (gjeldende sugar.yaml med India-drivere wired)
    print(f"=== Kjører prod (med India-drivere) for h={HORIZON_DAYS}d ===", flush=True)
    prod_buy = run_orchestrator_replay(
        store,
        BacktestConfig(instrument="Sugar", horizon_days=HORIZON_DAYS, from_date=FROM_DATE, to_date=TO_DATE),
        instruments_dir=str(INSTRUMENTS_DIR),
        direction="buy",
        step_days=STEP_DAYS,
    )
    prod_sell = run_orchestrator_replay(
        store,
        BacktestConfig(instrument="Sugar", horizon_days=HORIZON_DAYS, from_date=FROM_DATE, to_date=TO_DATE),
        instruments_dir=str(INSTRUMENTS_DIR),
        direction="sell",
        step_days=STEP_DAYS,
    )
    print(f"prod buy={len(prod_buy.signals)} sell={len(prod_sell.signals)}", flush=True)

    # Lag baseline (ingen India-drivere) i temp-mappe
    with tempfile.TemporaryDirectory() as tmp_dir:
        baseline_dir = Path(tmp_dir)
        # Kopier hele instruments-dir, overskrive sugar.yaml med baseline
        for f in INSTRUMENTS_DIR.iterdir():
            shutil.copy(f, baseline_dir / f.name)
        baseline_sugar = baseline_dir / "sugar.yaml"
        make_baseline_yaml(SUGAR_YAML, baseline_sugar)

        # Kopier defaults også
        defaults_src = INSTRUMENTS_DIR / "_defaults"
        if defaults_src.exists():
            (baseline_dir / "_defaults").mkdir(exist_ok=True)
            for f in defaults_src.iterdir():
                shutil.copy(f, baseline_dir / "_defaults" / f.name)

        print(f"=== Kjører baseline (uten India-drivere) for h={HORIZON_DAYS}d ===", flush=True)
        base_buy = run_orchestrator_replay(
            store,
            BacktestConfig(instrument="Sugar", horizon_days=HORIZON_DAYS, from_date=FROM_DATE, to_date=TO_DATE),
            instruments_dir=str(baseline_dir),
            direction="buy",
            step_days=STEP_DAYS,
        )
        base_sell = run_orchestrator_replay(
            store,
            BacktestConfig(instrument="Sugar", horizon_days=HORIZON_DAYS, from_date=FROM_DATE, to_date=TO_DATE),
            instruments_dir=str(baseline_dir),
            direction="sell",
            step_days=STEP_DAYS,
        )
    print(f"baseline buy={len(base_buy.signals)} sell={len(base_sell.signals)}", flush=True)

    prod_buy_grades = grade_breakdown(prod_buy.signals, "buy")
    base_buy_grades = grade_breakdown(base_buy.signals, "buy")
    prod_sell_grades = grade_breakdown(prod_sell.signals, "sell")
    base_sell_grades = grade_breakdown(base_sell.signals, "sell")

    md: list[str] = []
    md.append("# Sugar OOS 2023 India-forbud-validering\n\n")
    md.append(
        f"*Generert {date.today()} via `scripts/sugar_oos_2023_validation.py`. "
        f"Vindu: {FROM_DATE} → {TO_DATE} (Q1-Q3 2023, India-eksportforbud).*\n\n"
    )
    md.append(
        "**Kontrast:** prod-config (gjeldende `sugar.yaml`) vs. baseline-config "
        "der India-drivere er null-vektet:\n"
        "- `weather_stress.regions.india_maharashtra: 0.30 → 0.0` (BR/Thailand re-vektet 0.79/0.21)\n"
        "- `usda_psd_yoy(India)`: weight `0.30 → 0.0` (unica re-vektet 0.64/0.36)\n\n"
    )
    md.append(
        "**Suksess-kriterium:** India-drivere skal ha SVEKKET A SELL-signaler i 2023 "
        "(India-eksportforbud løftet supply-frykt → SELL-bias er feil-spesifisert i den perioden). "
        "Forventet: prod har færre A SELL eller lavere avg_score for SELL.\n\n"
    )
    md.append("---\n\n")

    md.append("## SELL-distribusjon (India-forbud-perioden)\n\n")
    md.append(fmt_table(prod_sell_grades, base_sell_grades, "h=180d SELL"))

    md.append("## BUY-distribusjon (kontrastsjekk)\n\n")
    md.append(fmt_table(prod_buy_grades, base_buy_grades, "h=180d BUY"))

    # Sammendrag
    prod_a_sell_n = prod_sell_grades.get("A+", {}).get("n", 0) + prod_sell_grades.get("A", {}).get("n", 0)
    base_a_sell_n = base_sell_grades.get("A+", {}).get("n", 0) + base_sell_grades.get("A", {}).get("n", 0)
    delta = prod_a_sell_n - base_a_sell_n

    md.append("## Konklusjon\n\n")
    md.append(f"- A+/A SELL-antall (prod): {prod_a_sell_n}\n")
    md.append(f"- A+/A SELL-antall (baseline u/India): {base_a_sell_n}\n")
    md.append(f"- Δ (prod − baseline): {delta:+d}\n\n")
    if delta < 0:
        md.append("**RESULTAT: India-drivere svekket A SELL-signaler (færre A+/A SELL i 2023).** Suksess-kriterium oppfylt.\n")
    elif delta == 0:
        md.append("**RESULTAT: India-drivere endret ikke A SELL-antall.** Marginalt — sjekk avg_score endringer.\n")
    else:
        md.append("**RESULTAT: India-drivere ØKTE A SELL-signaler.** Mot-intuitivt — verifiser bull_when-konfig.\n")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\nRapport skrevet: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
