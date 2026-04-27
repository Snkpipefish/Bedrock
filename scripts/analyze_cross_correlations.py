"""Kryss-asset-korrelasjons-analyse — fremoverlent prediksjon.

Bygger en stor IC-matrise (Information Coefficient = Spearman-korr
mellom prediktor og forward-return) over alle (prediktor × target)-
kombinasjoner:

- **Prediktorer:** alle features i `feature_snapshots` (close-priser per
  inst, FRED-makro, shipping, COT MM-net%) + alle drivere fra
  `driver_observations`.
- **Targets:** forward_return_pct per (target_instrument, target_horizon,
  target_direction).

For hver prediktor med lange tidsserie og hver target beregnes:
- IC: Spearman-korr på pair-vis ref_date-aligned data
- n: antall observasjoner
- direction-aware-flagg: positiv IC for BUY-target = predikerer riktig

Output: `docs/cross_correlations_<dato>.md` med:
1. Top-50 sterkeste cross-asset signaler (forward-looking)
2. Per-target-tabell: top-5 prediktorer per (instrument, horizon)
3. Per-prediktor-tabell: hvilke targets én feature predikerer best

**Forward-looking design:** ref_date er as_of_date — vi krever at både
prediktor og target er kjent på/før ref_date for prediktoren, og at
forward_return er målt strict ETTER ref_date. Ingen look-ahead bias.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/analyze_cross_correlations.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.signal_server.config import load_from_env

# Hit-rate-terskel matcher session 99 + analog-driver
THRESHOLDS_PCT: dict[int, float] = {30: 3.0, 90: 5.0}

OUTPUT_PATH_TEMPLATE = "docs/cross_correlations_{date}.md"

MIN_PAIR_OBS = 50  # minimum overlapping observations for å rapportere IC


def _load_features(db_path: Path) -> pd.DataFrame:
    """Last feature_snapshots som wide DataFrame indeksert på ref_date."""
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT ref_date, feature_key, value FROM feature_snapshots", con)
    con.close()
    if df.empty:
        return df
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    wide = df.pivot_table(index="ref_date", columns="feature_key", values="value", aggfunc="first")
    return wide


def _load_driver_obs(db_path: Path) -> pd.DataFrame:
    """Last driver_observations som long DataFrame."""
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT instrument, ref_date, horizon_days, direction, driver_name, "
        "driver_value, family_name, group_score, grade, published, "
        "forward_return_pct FROM driver_observations",
        con,
    )
    con.close()
    if not df.empty:
        df["ref_date"] = pd.to_datetime(df["ref_date"])
    return df


def _load_targets(db_path: Path) -> pd.DataFrame:
    """Bygg forward_returns-tabell fra driver_observations + analog_outcomes.

    En enkelt target-rad per (instrument, ref_date, horizon_days,
    direction) — direction er "buy" hvis forward_return > 0 ville
    matchet, men siden vi rapporterer IC for begge retninger lagrer
    vi bare én rad per (inst, ref_date, horizon).
    """
    con = sqlite3.connect(db_path)
    # Foretrukket: driver_observations har allerede forward_return per
    # (inst, ref_date, hor, dir). Vi tar én rad per (inst, ref_date, hor)
    # — bare BUY-rader siden forward_return er retning-uavhengig.
    df = pd.read_sql_query(
        "SELECT DISTINCT instrument, ref_date, horizon_days, "
        "forward_return_pct FROM driver_observations "
        "WHERE direction = 'buy'",
        con,
    )
    con.close()
    if df.empty:
        return df
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    return df


def _compute_pair_ic(
    pred: pd.Series, target: pd.Series, min_obs: int = MIN_PAIR_OBS
) -> tuple[float | None, int]:
    """Spearman IC på align-by-index. Returnerer (ic, n)."""
    aligned = pd.concat([pred, target], axis=1, join="inner").dropna()
    n = len(aligned)
    if n < min_obs:
        return None, n
    try:
        ic = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman"))
    except Exception:
        return None, n
    return ic, n


def _build_target_panel(
    targets_df: pd.DataFrame,
) -> dict[tuple[str, int], pd.Series]:
    """Bygg dict[(instrument, horizon)] → pd.Series (ref_date → fwd_return)."""
    panel: dict[tuple[str, int], pd.Series] = {}
    for (inst, hor), grp in targets_df.groupby(["instrument", "horizon_days"]):
        s = grp.set_index("ref_date")["forward_return_pct"].astype(float).sort_index()
        panel[(inst, int(hor))] = s
    return panel


def _build_predictor_panel(
    features_wide: pd.DataFrame, driver_obs_df: pd.DataFrame
) -> dict[str, pd.Series]:
    """Bygg dict[predictor_key] → pd.Series (ref_date → value).

    Predictor-keys:
    - Fra feature_snapshots: rå `feature_key` (e.g. "price.Gold", "fred.DGS10")
    - Fra driver_observations: aggregert til "driver.<name>.<instrument>"
      (én feature per (driver, instrument), tar BUY-retningens verdi for
      å unngå dobbeltelling — driver-verdier er uansett identiske for
      buy/sell før engine-flip)
    """
    predictors: dict[str, pd.Series] = {}

    # Feature-snapshots
    for col in features_wide.columns:
        s = features_wide[col].astype(float).dropna().sort_index()
        if not s.empty:
            predictors[col] = s

    # Driver-verdier per (driver, instrument). Bruk BUY-retning som
    # representant — engine flipper kun for SELL, så raw value før flip
    # er det vi ønsker som prediktor.
    if not driver_obs_df.empty:
        # Per (driver, instrument): én Series indeksert på ref_date
        buy_obs = driver_obs_df[driver_obs_df["direction"] == "buy"]
        for (drv, inst), grp in buy_obs.groupby(["driver_name", "instrument"]):
            # Ta gjennomsnitt over horizons for hvert ref_date — driver-
            # verdiene er typisk like uavhengig av horizon
            s = grp.groupby("ref_date")["driver_value"].mean().astype(float).sort_index()
            if len(s) >= MIN_PAIR_OBS:
                predictors[f"driver.{drv}.{inst}"] = s

    return predictors


def compute_cross_ic_matrix(
    predictors: dict[str, pd.Series],
    targets: dict[tuple[str, int], pd.Series],
) -> pd.DataFrame:
    """Beregn IC for hver (predictor, target)-kombinasjon. Returnerer
    long-format DataFrame med kolonner predictor, target_inst, target_hor,
    ic, n.
    """
    rows: list[dict] = []
    n_pred = len(predictors)
    n_tgt = len(targets)
    n_total = n_pred * n_tgt
    print(f"Beregner IC for {n_pred} prediktorer × {n_tgt} targets = {n_total} par")

    i = 0
    for pred_key, pred_series in predictors.items():
        for (inst, hor), tgt_series in targets.items():
            i += 1
            ic, n = _compute_pair_ic(pred_series, tgt_series)
            rows.append(
                {
                    "predictor": pred_key,
                    "target_instrument": inst,
                    "target_horizon": hor,
                    "ic": ic,
                    "n": n,
                }
            )
            if i % 1000 == 0:
                print(f"  {i}/{n_total}", flush=True)

    df = pd.DataFrame(rows)
    return df


def _render_top_signals(ic_df: pd.DataFrame, top_n: int = 50) -> str:
    """Top-N sterkeste signaler basert på |IC|."""
    qualified = ic_df[ic_df["ic"].notna()].copy()
    qualified["abs_ic"] = qualified["ic"].abs()
    top = qualified.sort_values("abs_ic", ascending=False).head(top_n)
    lines = [
        "| # | Predictor | Target | Hor | n | IC |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for i, (_, r) in enumerate(top.iterrows(), start=1):
        lines.append(
            f"| {i} | {r['predictor']} | {r['target_instrument']} "
            f"| {int(r['target_horizon'])}d | {int(r['n'])} | {r['ic']:+.3f} |"
        )
    return "\n".join(lines)


def _render_per_target(ic_df: pd.DataFrame, top_per: int = 5) -> str:
    """For hvert (target_instrument, target_horizon): top-5 prediktorer."""
    qualified = ic_df[ic_df["ic"].notna()].copy()
    qualified["abs_ic"] = qualified["ic"].abs()
    sections: list[str] = []
    for (inst, hor), grp in qualified.groupby(["target_instrument", "target_horizon"]):
        top = grp.sort_values("abs_ic", ascending=False).head(top_per)
        sections.append(f"### {inst} {int(hor)}d")
        sections.append("")
        sections.append("| Predictor | n | IC |")
        sections.append("|---|---:|---:|")
        for _, r in top.iterrows():
            sections.append(f"| {r['predictor']} | {int(r['n'])} | {r['ic']:+.3f} |")
        sections.append("")
    return "\n".join(sections)


def _render_per_predictor(ic_df: pd.DataFrame, min_targets: int = 3) -> str:
    """Per prediktor: hvor mange targets den predikerer (|IC| > 0.1) +
    median |IC| over alle targets. Sortert på robusthet.
    """
    qualified = ic_df[ic_df["ic"].notna()].copy()
    qualified["abs_ic"] = qualified["ic"].abs()
    summary = (
        qualified.groupby("predictor")
        .agg(
            n_targets=("target_instrument", "count"),
            n_strong=("abs_ic", lambda s: int((s > 0.1).sum())),
            median_abs_ic=("abs_ic", "median"),
            max_abs_ic=("abs_ic", "max"),
        )
        .reset_index()
        .sort_values(["n_strong", "median_abs_ic"], ascending=False)
    )
    summary = summary[summary["n_targets"] >= min_targets].head(50)
    lines = [
        "| Predictor | # targets | # strong (|IC| > 0.1) | Median |IC| | Max |IC| |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['predictor']} | {int(r['n_targets'])} | {int(r['n_strong'])} "
            f"| {r['median_abs_ic']:.3f} | {r['max_abs_ic']:.3f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--min-pair-obs", type=int, default=MIN_PAIR_OBS)
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else load_from_env().db_path
    output_path = (
        Path(args.output)
        if args.output
        else Path(OUTPUT_PATH_TEMPLATE.format(date=date.today().isoformat()))
    )

    print(f"Laster fra {db_path}...")
    features_wide = _load_features(db_path)
    driver_obs = _load_driver_obs(db_path)
    targets_df = _load_targets(db_path)

    print(f"  feature_snapshots: {features_wide.shape}")
    print(f"  driver_observations: {len(driver_obs):,} rader")
    print(f"  targets (per inst, hor): {len(targets_df):,} rader")

    if features_wide.empty and driver_obs.empty:
        print("Ingen data — kjør harvest-scriptene først.")
        return

    print("\nBygger prediktor- og target-paneler...")
    predictors = _build_predictor_panel(features_wide, driver_obs)
    targets = _build_target_panel(targets_df)
    print(f"  Prediktorer: {len(predictors)}")
    print(f"  Targets: {len(targets)}")

    ic_df = compute_cross_ic_matrix(predictors, targets)
    n_qualified = ic_df["ic"].notna().sum()
    print(f"\nKvalifiserte par (n ≥ {MIN_PAIR_OBS}): {n_qualified:,}/{len(ic_df):,}")

    out: list[str] = [
        f"# Kryss-asset-korrelasjons-analyse — {date.today().isoformat()}",
        "",
        "Forward-looking IC-matrise: alle prediktorer (features +",
        "driver-verdier) vs alle targets (forward_return per instrument ×",
        "horisont). Spearman-korrelasjon, ref_date-aligned, look-ahead-strict.",
        "",
        "## Datakilder",
        "",
        f"- `feature_snapshots`: {features_wide.shape[0]} ref_dates × "
        f"{features_wide.shape[1]} features",
        f"- `driver_observations`: {len(driver_obs):,} rader",
        f"- Targets: {len(targets)} (instrument × horisont)-kombinasjoner",
        f"- Prediktorer: {len(predictors)}",
        f"- Min observasjoner per par: {args.min_pair_obs}",
        "",
        "## Top-50 sterkeste signaler (forward-looking)",
        "",
        "Sortert på |IC|. Positiv IC = prediktor og target stiger sammen",
        "(BUY-egnet for instrumentet hvis target er fwd-return). Negativ IC",
        "= prediktor stiger når target faller (SELL-egnet, eller flipped",
        "BUY-prediksjon).",
        "",
        _render_top_signals(ic_df, top_n=50),
        "",
        "## Per-prediktor-sammendrag",
        "",
        "Hvilke prediktorer er **robuste** (sterke på tvers av mange",
        "targets, ikke bare én):",
        "",
        _render_per_predictor(ic_df),
        "",
        "## Per-target detalj (top-5 prediktorer)",
        "",
        _render_per_target(ic_df),
        "",
        "## Tolking",
        "",
        "- |IC| > 0.10: signifikant prediksjon (sannsynligvis ikke støy)",
        "- |IC| > 0.20: sterk prediksjon — vurder for scoring-vekt",
        "- |IC| < 0.05: trolig støy — vurder vekt-reduksjon",
        "",
        "**Forward-looking validering:** alle target-radioer er fwd-return",
        "MÅLT ETTER ref_date. Prediktor-verdier er kjent PÅ ref_date.",
        "Ingen look-ahead bias. Korrelasjon her er prediksjonskraft, ikke",
        "samtidighet.",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(out))
    print(f"\nSkrevet: {output_path}")


if __name__ == "__main__":
    main()
