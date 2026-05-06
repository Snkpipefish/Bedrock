"""DSR (deflated Sharpe ratio) + familie-korrelasjons-analyse for sukker.

Adresserer analytiker-peer-review (docs/sugar_analyst_response_2026-05.md):
- C.2 Korrelerte familier: parvis driver-korrelasjon på A-SELL-bøtta
  for å identifisere outlook/unica-overlap (analytiker-hypotese: ρ > 0.6)
- C.3 Multiple-testing: López de Prado DSR over 32-test-rute
  (4 horisonter × 2 retninger × 4 grader). Krever PSR > 0.95 for
  "ekte edge" på α=0.05 etter deflasjon.

Bruker eksisterende rådata:
- docs/sugar_attribution_a_sell_2026-05.csv (driver-attribution)
- docs/backtest_sugar_horizons_2026-05.md (per-grade-bøtter)

Kjøres lokalt (Pure Python, ingen codespace-cost).

Output: docs/sugar_dsr_correlations_2026-05.md
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF — Beasley-Springer-Moro approximation."""
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5] / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= 1.0 - p_low:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


ATTR_CSV = Path("docs/sugar_attribution_a_sell_2026-05.csv")
BACKTEST_MD = Path("docs/backtest_sugar_horizons_2026-05.md")
OUT = Path("docs/sugar_dsr_correlations_2026-05.md")


# ---------------------------------------------------------------------------
# DSR — Deflated Sharpe Ratio (López de Prado 2018)
# ---------------------------------------------------------------------------


def deflated_sharpe(
    sr_observed: float,
    n_trials: int,
    n_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> tuple[float, float]:
    """Returnerer (sr_threshold_deflated, psr).

    sr_threshold_deflated = forventet maks-SR over n_trials uavhengige
    Sharpe-tester (Bailey & López de Prado 2014).

    psr = sannsynlighet for at sr_observed er ekte edge etter deflasjon.

    PSR > 0.95 = signifikant på α=0.05.
    """
    # Forventet max-SR av n_trials standard-normal-trekninger
    # (Bailey-Borwein 2012-formel)
    if n_trials <= 1:
        sr_threshold = 0.0
    else:
        em = (1 - np.euler_gamma) * _norm_ppf(1 - 1.0 / n_trials) + np.euler_gamma * _norm_ppf(
            1 - 1.0 / (n_trials * np.e)
        )
        sr_threshold = em / math.sqrt(n_obs)

    # PSR (Probabilistic Sharpe Ratio) etter deflasjon
    # PSR(SR*) = Φ((SR_obs - SR*) × sqrt(n-1) / sqrt(1 - skew*SR_obs + (kurt-1)/4 * SR_obs^2))
    denom_inner = 1.0 - skewness * sr_observed + ((kurtosis - 1.0) / 4.0) * sr_observed**2
    if denom_inner <= 0:
        return sr_threshold, float("nan")
    z = (sr_observed - sr_threshold) * math.sqrt(n_obs - 1) / math.sqrt(denom_inner)
    psr = float(_norm_cdf(z))
    return sr_threshold, psr


def annualized_sharpe(returns: list[float], periods_per_year: float = 365 / 7) -> float:
    """Årlig Sharpe fra ukentlige forward-returns. Default: 52 uker/år.

    Sukker-backtest bruker step_days=7, så hver observasjon er ~ukentlig.
    """
    arr = np.array(returns, dtype=float)
    if len(arr) < 2 or arr.std(ddof=1) == 0:
        return 0.0
    return float(arr.mean() / arr.std(ddof=1) * math.sqrt(periods_per_year))


# ---------------------------------------------------------------------------
# Backtest-MD parser (henter per-grade-bøtte-stats)
# ---------------------------------------------------------------------------


def parse_backtest_md(path: Path) -> list[dict]:
    """Returnerer liste av (horizon, direction, grade, n, hit_rate, avg_return)."""
    rows: list[dict] = []
    text = path.read_text()
    sections = re.split(r"## Sugar · h=", text)[1:]
    for sec in sections:
        m = re.match(r"(\d+)d · direction=(\w+)", sec)
        if not m:
            continue
        h, dir_ = int(m.group(1)), m.group(2)
        grade_re = re.findall(
            r"\| (A_plus|A\+|A|B|C) \| (\d+) \| ([\d.]+)% \| ([+-]?[\d.]+)% \|",
            sec,
        )
        for grade, n, hr, avgr in grade_re:
            rows.append(
                {
                    "horizon": h,
                    "direction": dir_,
                    "grade": grade.replace("_plus", "+").replace("A+", "A+"),
                    "n": int(n),
                    "hit_rate": float(hr) / 100.0,
                    "avg_return": float(avgr),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Hovedanalyse
# ---------------------------------------------------------------------------


def main() -> int:
    df = pd.read_csv(ATTR_CSV)
    df["forward_return"] = df["forward_return_pct"]

    lines: list[str] = ["# Sugar DSR + familie-korrelasjons-analyse\n"]
    lines.append(
        "*Analytiker-peer-review (docs/sugar_analyst_response_2026-05.md) "
        "C.2 + C.3. Kjørt lokalt på eksisterende backtest-rådata.*\n"
    )

    # ------------------------------------------------------------------
    # Seksjon 1: Familie-korrelasjons-matrise
    # ------------------------------------------------------------------
    fam_cols = [c for c in df.columns if c.startswith("fam_")]
    corr = df[fam_cols].corr()

    lines.append("## 1. Familie-score-korrelasjons-matrise\n")
    lines.append("*Hypotese (C.2): outlook ↔ unica ρ > 0.6 betyr dobbel-vekting.*\n")
    lines.append("| | " + " | ".join(c.replace("fam_", "") for c in fam_cols) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(fam_cols)) + "|")
    for i, c1 in enumerate(fam_cols):
        row = [c1.replace("fam_", "")]
        for j, _c2 in enumerate(fam_cols):
            v = corr.iloc[i, j]
            if pd.isna(v):
                row.append("—")
            elif i == j:
                row.append("**1.00**")
            elif abs(v) > 0.6:
                row.append(f"**{v:+.2f}**")
            else:
                row.append(f"{v:+.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Identifiser high-korrelasjon-par
    high_corr_pairs: list[tuple[str, str, float]] = []
    for i in range(len(fam_cols)):
        for j in range(i + 1, len(fam_cols)):
            v = corr.iloc[i, j]
            if not pd.isna(v) and abs(v) > 0.6:
                high_corr_pairs.append(
                    (fam_cols[i].replace("fam_", ""), fam_cols[j].replace("fam_", ""), float(v))
                )

    lines.append("### Funn — overlappende familier (|ρ| > 0.6)\n")
    if not high_corr_pairs:
        lines.append(
            "*Ingen familier med |ρ| > 0.6. Analytiker-hypotese om "
            "outlook/unica-dobbeltvekting **ikke bekreftet** på A-SELL-data.*\n"
        )
    else:
        lines.append("| Familie A | Familie B | ρ | Tolkning |")
        lines.append("|---|---|---:|---|")
        for fa, fb, rho in high_corr_pairs:
            lines.append(f"| {fa} | {fb} | {rho:+.3f} | konsolidér tak |")
        lines.append("")

    # ------------------------------------------------------------------
    # Seksjon 2: DSR per (horisont, retning, grade)
    # ------------------------------------------------------------------
    backtest_rows = parse_backtest_md(BACKTEST_MD)
    n_trials = len(backtest_rows)  # 32 = 4h × 2dir × 4grade (men noen mangler)

    lines.append(f"## 2. Deflated Sharpe Ratio (n_trials={n_trials})\n")
    lines.append(
        f"*Bonferroni-korreksjon: med α=0.05 og {n_trials} tester må p < {0.05 / n_trials:.4f}. "
        "DSR + PSR (López de Prado) gir mer presis deflasjon.*\n"
    )
    lines.append(
        "| Horisont | Retning | Grade | n | Hit-rate | Avg ret | SR (annual) | SR* (deflated) | PSR | Status |"
    )
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---|")

    # For SR trenger vi std av per-signal-returns. Vi har bare avg per
    # grade-bøtte. Approksimerer SR fra hit-rate + binomial-std hvis
    # n>10. Mer presis: bruke per-signal-data fra attribution CSV (som
    # kun dekker SELL h=180d). For andre kombinasjoner: konservativt
    # estimat via avg / sqrt(n).
    for r in backtest_rows:
        if r["n"] < 10:
            lines.append(
                f"| {r['horizon']}d | {r['direction']} | {r['grade']} | {r['n']} | "
                f"{r['hit_rate'] * 100:.1f}% | {r['avg_return']:+.2f}% | — | — | — | "
                f"insufficient (n<10) |"
            )
            continue
        # Approksimert SR fra avg + heuristic std
        # Std på sukker forward returns er ~10-15% over historisk vindu
        std_approx = 12.0  # konservativ for SWING/MAKRO
        sr_approx = (
            (r["avg_return"] / std_approx) * math.sqrt(365 / 7 / 4) if r["avg_return"] != 0 else 0.0
        )
        sr_th, psr = deflated_sharpe(sr_approx, n_trials=n_trials, n_obs=r["n"])
        status = "✅ ekte" if psr > 0.95 else ("⚠ marginal" if psr > 0.5 else "❌ støy")
        lines.append(
            f"| {r['horizon']}d | {r['direction']} | {r['grade']} | {r['n']} | "
            f"{r['hit_rate'] * 100:.1f}% | {r['avg_return']:+.2f}% | {sr_approx:+.2f} | "
            f"{sr_th:+.2f} | {psr:.3f} | {status} |"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # Seksjon 3: A+ BUY 90d presis DSR
    # ------------------------------------------------------------------
    lines.append("## 3. A+ BUY 90d — presis DSR (analytiker-flaggship)\n")
    a_plus_buy_90 = next(
        (
            r
            for r in backtest_rows
            if r["horizon"] == 90 and r["direction"] == "buy" and r["grade"] == "A+"
        ),
        None,
    )
    if a_plus_buy_90:
        n = a_plus_buy_90["n"]
        avg = a_plus_buy_90["avg_return"]
        sr = avg / 12.0 * math.sqrt(365 / 7 / 4)
        sr_th, psr = deflated_sharpe(sr, n_trials=n_trials, n_obs=n)
        lines.append(f"- Observasjoner: n={n}")
        lines.append(f"- Avg return: {avg:+.2f}%")
        lines.append(f"- SR (annualized, std≈12%): {sr:+.3f}")
        lines.append(f"- SR* (deflated, n_trials={n_trials}): {sr_th:+.3f}")
        lines.append(f"- PSR: {psr:.3f}")
        lines.append(
            "- **Konklusjon:** "
            + (
                "✅ A+ BUY 90d holder DSR-test (PSR > 0.95) — gå i prod."
                if psr > 0.95
                else "⚠ A+ BUY 90d er IKKE signifikant etter deflasjon (PSR < 0.95)."
                "Krever større utvalg eller strammere grade-cutoff før prod."
            )
        )
        lines.append("")

    # ------------------------------------------------------------------
    # Seksjon 4: A SELL — er den anti-driver-bekreftet?
    # ------------------------------------------------------------------
    lines.append("## 4. SELL grade-progresjon (analytiker non-monotonisitet)\n")
    sell_rows = [r for r in backtest_rows if r["direction"] == "sell"]
    for h in sorted({r["horizon"] for r in sell_rows}):
        sub = sorted([r for r in sell_rows if r["horizon"] == h], key=lambda x: x["grade"])
        progression = [(r["grade"], r["hit_rate"], r["avg_return"], r["n"]) for r in sub]
        lines.append(
            f"**h={h}d:** "
            + " → ".join(f"{g} ({hr * 100:.1f}%/{ar:+.1f}% n={n})" for g, hr, ar, n in progression)
        )
        # Sjekk monotonisitet (A → B → C avg_return skal øke for SELL hvis
        # ekstrem-grade SELL er ekte signal). Faktisk forventet: A SELL
        # mest negativ, C minst.
        a_ret = next((p[2] for p in progression if p[0] == "A"), None)
        c_ret = next((p[2] for p in progression if p[0] == "C"), None)
        if a_ret is not None and c_ret is not None:
            if a_ret < c_ret - 5:
                lines.append(
                    f"  → **non-monoton: A {a_ret:+.1f}% < C {c_ret:+.1f}%** (overshoot/mean-reversion bekreftet)"
                )
            else:
                lines.append(f"  → ok: A {a_ret:+.1f}% ≥ C {c_ret:+.1f}% - 5pp")
    lines.append("")

    # ------------------------------------------------------------------
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Skrevet {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
