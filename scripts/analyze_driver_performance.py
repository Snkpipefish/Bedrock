"""Analyse av per-driver-prediksjonskraft mot forward_return.

Leser `driver_observations`-tabellen (skrevet av
`harvest_driver_observations.py`) og beregner per
(driver, instrument, horizon, direction):

- n: antall observasjoner
- avg_value: gjennomsnittlig driver-verdi
- IC (Information Coefficient): Spearman-korr mellom driver_value og
  forward_return_pct (direction-aware: positiv IC for BUY, negativ for
  SELL ⇒ driver predikerer riktig retning).
- hit_rate_high: andel hits når driver_value er i top-25%-kvartilen
- hit_rate_low: andel hits når driver_value er i bunn-25%-kvartilen
- monotonisitet: hit_rate ved kvartil 1 → 4 (bør stige for BUY-rettet
  bull-of-instrument-driver hvis prediktiv)

Hit-definisjon (matcher session 99 + analog-driver):
- BUY hit: forward_return_pct ≥ +threshold (default 3% for 30d, 5% for 90d)
- SELL hit: forward_return_pct ≤ -threshold

Output: `docs/driver_performance_<dato>.md` med tre seksjoner:
1. Top-IC-drivere på tvers av (inst, hor, dir)
2. Per-driver detaljert tabell
3. Worst performers (kandidater for vekt-reduksjon)

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/analyze_driver_performance.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import argparse
import itertools
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.signal_server.config import load_from_env

THRESHOLDS_PCT: dict[int, float] = {30: 3.0, 90: 5.0}

OUTPUT_PATH_TEMPLATE = "docs/driver_performance_{date}.md"


def _load_observations(db_path: Path) -> pd.DataFrame:
    """Last hele driver_observations-tabellen som DataFrame."""
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM driver_observations", con)
    except Exception as e:
        con.close()
        raise RuntimeError(
            f"Kunne ikke lese driver_observations: {e}. "
            f"Har du kjørt harvest_driver_observations.py?"
        ) from e
    con.close()
    return df


def _direction_aware_hit(forward_return_pct: float, threshold_pct: float, direction: str) -> bool:
    if direction == "buy":
        return forward_return_pct >= threshold_pct
    return forward_return_pct <= -threshold_pct


def _compute_ic_per_combo(df_combo: pd.DataFrame, direction: str) -> dict[str, Any]:
    """For én (driver, instrument, horizon, direction)-undergruppe:
    beregn n, avg_value, IC, kvartil-hit-rates.
    """
    n = len(df_combo)
    if n < 10:
        return {
            "n": n,
            "avg_value": df_combo["driver_value"].mean() if n > 0 else None,
            "ic": None,
            "hit_rate_q4": None,
            "hit_rate_q1": None,
            "monotonic": None,
        }

    horizon_days = int(df_combo["horizon_days"].iloc[0])
    threshold = THRESHOLDS_PCT.get(horizon_days, 3.0)
    fwd = df_combo["forward_return_pct"].astype(float)
    val = df_combo["driver_value"].astype(float)

    # Hit-flag per rad
    hits = fwd.apply(lambda r: _direction_aware_hit(r, threshold, direction))

    # Spearman IC: korrelasjon mellom rangert driver_value og forward_return.
    # For SELL-retning vil en bull-of-instrument-driver vise NEGATIV IC,
    # som er korrekt — vi rapporterer rå-verdien så fortegn-tolkning er
    # explicit.
    try:
        ic = float(val.corr(fwd, method="spearman"))
    except Exception:
        ic = None

    # Kvartil-hit-rates: del observasjoner i 4 like store grupper basert
    # på driver_value, mål hit-rate i hver. For predikiv driver:
    # BUY → hit_rate stiger fra Q1 til Q4. SELL → faller.
    try:
        quartiles = pd.qcut(val, 4, labels=["q1", "q2", "q3", "q4"], duplicates="drop")
        hit_by_q = hits.groupby(quartiles, observed=False).mean() * 100.0
        q1 = float(hit_by_q.get("q1", float("nan")))
        q4 = float(hit_by_q.get("q4", float("nan")))
        # Monotonisitet: 1.0 = perfekt stigende q1<q2<q3<q4 (for BUY)
        monotonic = None
        try:
            seq = [hit_by_q.get(f"q{i}", float("nan")) for i in [1, 2, 3, 4]]
            seq_clean = [float(x) for x in seq if pd.notna(x)]
            if len(seq_clean) == 4:
                # Antall trinn-monotone par
                pairs = list(itertools.pairwise(seq_clean))
                if direction == "buy":
                    mono_pairs = sum(1 for a, b in pairs if b >= a)
                else:
                    mono_pairs = sum(1 for a, b in pairs if b <= a)
                monotonic = mono_pairs / 3.0
        except Exception:
            pass
    except (ValueError, IndexError):
        q1 = q4 = float("nan")
        monotonic = None

    return {
        "n": n,
        "avg_value": float(val.mean()),
        "ic": ic,
        "hit_rate_q1": q1,
        "hit_rate_q4": q4,
        "monotonic": monotonic,
    }


def _build_per_driver_table(df: pd.DataFrame) -> pd.DataFrame:
    """Bygg per-(driver, instrument, horizon, direction)-tabell."""
    rows: list[dict] = []
    grp = df.groupby(["driver_name", "family_name", "instrument", "horizon_days", "direction"])
    for (drv, fam, inst, hor, direction), sub in grp:
        stats = _compute_ic_per_combo(sub, direction)
        rows.append(
            {
                "driver": drv,
                "family": fam,
                "instrument": inst,
                "horizon": hor,
                "direction": direction,
                **stats,
            }
        )
    return pd.DataFrame(rows)


def _format_optional_float(v: Any, fmt: str = ".3f") -> str:
    if v is None or pd.isna(v):
        return "  -  "
    return format(v, fmt)


def _render_top_ic_table(perf: pd.DataFrame, top_n: int = 30) -> str:
    """Topp-N drivere på abs(IC), filtrert til n ≥ 30."""
    qualified = perf[(perf["n"] >= 30) & perf["ic"].notna()].copy()
    qualified["abs_ic"] = qualified["ic"].abs()
    top = qualified.sort_values("abs_ic", ascending=False).head(top_n)
    lines = [
        "| Driver | Family | Instrument | Hor | Dir | n | IC | Hit Q1 | Hit Q4 | Mono |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in top.iterrows():
        lines.append(
            f"| {r['driver']} | {r['family']} | {r['instrument']} "
            f"| {int(r['horizon'])}d | {r['direction']} | {int(r['n'])} "
            f"| {_format_optional_float(r['ic'])} "
            f"| {_format_optional_float(r['hit_rate_q1'], '.1f')}% "
            f"| {_format_optional_float(r['hit_rate_q4'], '.1f')}% "
            f"| {_format_optional_float(r['monotonic'], '.2f')} |"
        )
    return "\n".join(lines)


def _render_worst_performers_table(perf: pd.DataFrame, top_n: int = 30) -> str:
    """Drivere med dårligst monotonisitet (kandidater for vekt-reduksjon)."""
    qualified = perf[(perf["n"] >= 30) & perf["monotonic"].notna()].copy()
    worst = qualified.sort_values("monotonic", ascending=True).head(top_n)
    lines = [
        "| Driver | Family | Instrument | Hor | Dir | n | IC | Hit Q1 | Hit Q4 | Mono |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in worst.iterrows():
        lines.append(
            f"| {r['driver']} | {r['family']} | {r['instrument']} "
            f"| {int(r['horizon'])}d | {r['direction']} | {int(r['n'])} "
            f"| {_format_optional_float(r['ic'])} "
            f"| {_format_optional_float(r['hit_rate_q1'], '.1f')}% "
            f"| {_format_optional_float(r['hit_rate_q4'], '.1f')}% "
            f"| {_format_optional_float(r['monotonic'], '.2f')} |"
        )
    return "\n".join(lines)


def _render_per_driver_summary(perf: pd.DataFrame) -> str:
    """Aggregert per driver: median IC + median monotonisitet over alle (inst, hor, dir)."""
    qualified = perf[(perf["n"] >= 30) & perf["ic"].notna()]
    summary = (
        qualified.groupby("driver")
        .agg(
            n_combos=("instrument", "count"),
            median_ic=("ic", "median"),
            min_ic=("ic", "min"),
            max_ic=("ic", "max"),
            median_mono=("monotonic", "median"),
            avg_n=("n", "mean"),
        )
        .reset_index()
        .sort_values("median_ic", ascending=False, key=lambda s: s.abs())
    )
    lines = [
        "| Driver | # kombos | Median IC | Min IC | Max IC | Median mono | Avg n |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['driver']} | {int(r['n_combos'])} "
            f"| {_format_optional_float(r['median_ic'])} "
            f"| {_format_optional_float(r['min_ic'])} "
            f"| {_format_optional_float(r['max_ic'])} "
            f"| {_format_optional_float(r['median_mono'], '.2f')} "
            f"| {r['avg_n']:.0f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="Override output-sti")
    parser.add_argument("--db", default=None, help="Override DB-sti")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else load_from_env().db_path
    output_path = (
        Path(args.output)
        if args.output
        else Path(OUTPUT_PATH_TEMPLATE.format(date=date.today().isoformat()))
    )

    print(f"Laster driver_observations fra {db_path}...")
    df = _load_observations(db_path)
    print(
        f"  {len(df):,} rader, {df['instrument'].nunique()} instrumenter, "
        f"{df['driver_name'].nunique()} drivere"
    )

    if df.empty:
        print("Tom tabell — ingen analyse å gjøre.")
        return

    print("Beregner IC + kvartil-hit-rate per (driver, instrument, horizon, direction)...")
    perf = _build_per_driver_table(df)

    n_qualified = (perf["n"] >= 30).sum()
    n_total = len(perf)
    print(f"  {n_qualified}/{n_total} kombinasjoner med n ≥ 30 (kvalifisert for analyse)")

    out_lines: list[str] = [
        f"# Driver-performance-analyse — {date.today().isoformat()}",
        "",
        "Per-driver IC + kvartil-hit-rate-analyse fra `driver_observations`-",
        "tabellen. Genereres av `scripts/analyze_driver_performance.py`.",
        "",
        "## Kontekst",
        "",
        f"- Total observasjoner: {len(df):,}",
        f"- Instrumenter: {df['instrument'].nunique()}",
        f"- Drivere: {df['driver_name'].nunique()}",
        f"- Tidsspenn: {df['ref_date'].min()} til {df['ref_date'].max()}",
        f"- Kombinasjoner med n ≥ 30 (kvalifisert): {n_qualified}/{n_total}",
        "",
        "## Metrikker",
        "",
        "- **IC (Information Coefficient)**: Spearman-korr mellom driver_value",
        "  og forward_return_pct. Positiv IC for BUY-retning betyr driver",
        "  predikerer riktig (høy verdi → høy fwd-return). For SELL er korrekt",
        "  IC negativ (høy bull-confidence → lav/negativ fwd-return).",
        "- **Hit Q1/Q4**: hit-rate i bunn-/topp-kvartil av driver-verdier.",
        "- **Monotonisitet**: andel av kvartil-par (Q1→Q2, Q2→Q3, Q3→Q4) der",
        "  hit-rate beveger seg riktig vei. 1.0 = perfekt prediktiv.",
        "",
        "## Top-IC-drivere (alle (inst, hor, dir)-kombinasjoner)",
        "",
        _render_top_ic_table(perf, top_n=30),
        "",
        "## Per-driver-sammendrag (median over alle kombinasjoner)",
        "",
        _render_per_driver_summary(perf),
        "",
        "## Verste monotonisitet (kandidater for vekt-reduksjon)",
        "",
        _render_worst_performers_table(perf, top_n=30),
        "",
        "## Anbefalinger",
        "",
        "Generert som datapunkt for ADR-009 cutover-readiness-audit (session 117).",
        "Konkrete vekt-justeringer vurderes manuelt; tabellene over flagger",
        "kandidater. Drivere med median monotonisitet < 0.4 og median |IC| < 0.05",
        "bør vurderes for vekt-reduksjon eller fjerning. Drivere med median",
        "monotonisitet > 0.7 og |IC| > 0.1 er sterke prediktorer som kan",
        "vekt-økes.",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(out_lines))
    print(f"\nSkrevet: {output_path}")


if __name__ == "__main__":
    main()
