"""ANP etanol-paritet parameter-sweep (analytiker punkt 2).

Forrige validering ga ρ=-0.143 (krav |ρ| ≥ 0.5). Sweeper:
- anhydrous_factor: 1.00, 1.05, 1.10, 1.15, 1.20
- sugar_kg_per_liter: 1.700, 1.800, 1.852, 1.900, 2.000
- lag_offset: 0, 1, 2, 4 UNICA-rapporter (mølle-respons-treghet)

Hvis ingen kombinasjon når ρ ≤ -0.30 → dropp driveren fra cross-familien.

Bruk:
    PYTHONPATH=src python scripts/sugar_anp_sweep.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore

DEFAULT_DB = "/home/pc/bedrock/data/bedrock.db"
OUT = Path("docs/sugar_anp_sweep_2026-05.md")

ANHYD_FACTORS = [1.00, 1.05, 1.10, 1.15, 1.20]
SUGAR_KG_PER_L = [1.700, 1.800, 1.852, 1.900, 2.000]
LAG_OFFSETS = [0, 1, 2, 4]
LOOKBACK = 60


def compute_signal_z(
    eth: pd.Series, brl: pd.Series, sb: pd.Series, anhyd_factor: float, kg_per_l: float
) -> pd.Series:
    common = pd.DataFrame({"eth": eth, "brl": brl, "sb": sb}).ffill().dropna()
    anhyd = common["eth"] * anhyd_factor
    paritet_cents_lb = (anhyd / common["brl"]) * (1.0 / kg_per_l) * 2.20462 * 100.0
    delta = paritet_cents_lb - common["sb"]
    z = (delta - delta.rolling(LOOKBACK).mean()) / delta.rolling(LOOKBACK).std()
    return z.dropna()


def main() -> int:
    store = DataStore(Path(DEFAULT_DB))
    eth = store.get_fundamentals("ANP_ETANOL_HIDR_CS_BRL_LITER")
    brl = store.get_fundamentals("DEXBZUS")
    sugar_df = store.get_prices("Sugar", tf="D1")
    sugar = sugar_df if isinstance(sugar_df, pd.Series) else sugar_df["close"]
    sugar.index = pd.to_datetime(sugar.index)
    eth.index = pd.to_datetime(eth.index)
    brl.index = pd.to_datetime(brl.index)

    unica = store.get_unica_reports()
    unica = unica.set_index(pd.to_datetime(unica["report_date"])).sort_index()
    print(f"UNICA: {len(unica)} reports, {unica.index.min().date()} → {unica.index.max().date()}")

    md: list[str] = []
    md.append("# ANP etanol-paritet — parameter-sweep\n\n")
    md.append(
        f"*Generert {date.today()} via `scripts/sugar_anp_sweep.py`. "
        f"UNICA: {len(unica)} reports.*\n\n"
    )
    md.append("**Krav:** ρ ≤ -0.30 (anbefalt -0.5). Ellers dropp driveren.\n\n")
    md.append("---\n\n")
    md.append("## Sweep-resultater\n\n")
    md.append("| anhyd_factor | sugar_kg_per_l | lag | n | ρ |\n")
    md.append("|---:|---:|---:|---:|---:|\n")

    best = (1.0, 1.852, 0, 0, 0.0)  # anhyd, kg, lag, n, rho
    rho_min = 0.0  # most-negative

    for anhyd in ANHYD_FACTORS:
        for kgpl in SUGAR_KG_PER_L:
            z = compute_signal_z(eth, brl, sugar, anhyd, kgpl)
            for lag in LAG_OFFSETS:
                pairs: list[tuple[float, float]] = []
                unica_dates = unica.index.tolist()
                for i, ud in enumerate(unica_dates):
                    target_idx = i + 1 + lag  # current + lag periods ahead
                    if target_idx >= len(unica_dates):
                        continue
                    target_ud = unica_dates[target_idx]
                    # signal z på/før ud
                    if ud in z.index:
                        z_signal = z.loc[ud]
                    else:
                        idx = z.index.searchsorted(ud) - 1
                        if idx < 0 or idx >= len(z):
                            continue
                        z_signal = z.iloc[idx]
                    if pd.isna(z_signal):
                        continue
                    target_mix = unica.loc[target_ud, "mix_sugar_pct"]
                    if pd.isna(target_mix):
                        continue
                    pairs.append((float(z_signal), float(target_mix)))
                if len(pairs) < 5:
                    md.append(f"| {anhyd:.2f} | {kgpl:.3f} | {lag} | {len(pairs)} | n/a |\n")
                    continue
                df = pd.DataFrame(pairs, columns=["z", "mix"])
                rho = float(df["z"].corr(df["mix"]))
                md.append(f"| {anhyd:.2f} | {kgpl:.3f} | {lag} | {len(df)} | {rho:+.3f} |\n")
                if rho < rho_min:
                    rho_min = rho
                    best = (anhyd, kgpl, lag, len(df), rho)

    md.append("\n## Beste kombinasjon\n\n")
    md.append(
        f"- anhyd_factor: **{best[0]:.2f}**\n"
        f"- sugar_kg_per_l: **{best[1]:.3f}**\n"
        f"- lag (UNICA-rapporter frem): **{best[2]}**\n"
        f"- n: {best[3]}\n"
        f"- ρ: **{best[4]:+.3f}**\n\n"
    )

    if best[4] <= -0.30:
        md.append(
            f"## ✅ Aksept\n\n"
            f"ρ={best[4]:+.3f} ≤ -0.30 → driver-formel kan kalibreres med "
            f"anhyd_factor={best[0]}, sugar_kg_per_l={best[1]}, "
            f"lag={best[2]} UNICA-rapporter frem.\n\n"
            f"**Tiltak:** oppdater `config/instruments/sugar.yaml` med "
            f"params for cross-familiens `ethanol_parity_brl`.\n"
        )
    else:
        md.append(
            f"## ❌ Aksept feiler\n\n"
            f"Beste ρ={best[4]:+.3f} > -0.30 → ingen kombinasjon når kravet. "
            f"**Anbefaling: dropp driver fra `cross`-familien i sugar.yaml.** "
            f"ANP-paritet via hydrous-pris × statisk faktor er for grov "
            f"approksimasjon — krever wholesale anhydrous-data eller direkte "
            f"mølle-mix-statistikk for å validere.\n"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(md), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Best: anhyd={best[0]}, kg/l={best[1]}, lag={best[2]}, n={best[3]}, ρ={best[4]:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
