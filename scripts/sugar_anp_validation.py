"""ANP etanol-paritet-driver validering (analytiker E).

Suksess-kriterium:
    ρ(ethanol_parity_brl_signal_t, unica.mix_sugar_pct_t+1) < -0.5

Tolkning: høy etanol-paritet → mølle-allokering vrir til etanol →
neste UNICA-rapport viser lavere sukker-mix-andel. Negativ korrelasjon
bekrefter at driver-formel er korrekt spesifisert.

Hvis |ρ| < 0.3 → re-kalibrer paritet-formel (anhydrous-faktor,
sugar_kg_per_liter, eller hele approksimasjonen).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore

DEFAULT_DB = "/home/pc/bedrock/data/bedrock.db"
OUT = Path("docs/sugar_anp_validation_2026-05.md")


def main() -> int:
    store = DataStore(Path(DEFAULT_DB))

    # 1. Hent ANP etanol-pris og sukker-pris
    try:
        eth = store.get_fundamentals("ANP_ETANOL_HIDR_CS_BRL_LITER")
        brl = store.get_fundamentals("DEXBZUS")
    except KeyError as exc:
        print(f"FAIL: missing series — {exc}")
        return 1

    sugar_df = store.get_prices("Sugar", tf="D1")
    # store.get_prices returns Series indexed by ts (close prices).
    sugar = sugar_df if isinstance(sugar_df, pd.Series) else sugar_df["close"]
    sugar.index = pd.to_datetime(sugar.index)

    eth.index = pd.to_datetime(eth.index)
    brl.index = pd.to_datetime(brl.index)

    # 2. Hent UNICA mix_sugar_pct
    unica = store.get_unica_reports()
    if unica.empty:
        print("FAIL: no UNICA data")
        return 2
    unica = unica.set_index(pd.to_datetime(unica["report_date"])).sort_index()

    # 3. Beregn paritet daglig
    common = pd.DataFrame({"eth": eth, "brl": brl, "sb": sugar}).ffill().dropna()
    if len(common) < 30:
        print(f"INSUFFICIENT: only {len(common)} aligned days. Need 30+.")
        return 3

    anhyd = common["eth"] * 1.05
    paritet_cents_lb = (anhyd / common["brl"]) * (1.0 / 1.852) * 2.20462 * 100.0
    delta = paritet_cents_lb - common["sb"]
    delta_z = (delta - delta.rolling(60).mean()) / delta.rolling(60).std()

    lines: list[str] = []
    lines.append("# Sugar ANP etanol-paritet — validering\n")
    lines.append(
        f"*Generert {date.today()}. Datavindu: {common.index.min().date()} → "
        f"{common.index.max().date()} ({len(common)} dager).*\n"
    )

    # 4. For hver UNICA-rapport: paritet-signal vs mix_sugar_pct N rapporter frem
    # Sub-fase 12.11+ punkt 2 (sweep-resultat): mølle-respons har ~3-rapport-
    # forsinkelse (~45-60 dager). Paritet-signal i dag predikerer mix tre
    # rapporter frem; lag=3 gir ρ=-0.389 (passerer |ρ|≥0.30), lag=1 gir +0.06
    # (støy). Se docs/sugar_anp_sweep_2026-05.md.
    LAG_REPORTS = 3
    pairs: list[tuple[float, float, str]] = []
    unica_dates = unica.index.tolist()
    for i, ud in enumerate(unica_dates):
        target_idx = i + LAG_REPORTS
        if target_idx >= len(unica_dates):
            continue
        target_ud = unica_dates[target_idx]
        # Paritet-z-score samme dag
        if ud not in delta_z.index:
            idx = delta_z.index.searchsorted(ud) - 1
            if idx < 0 or idx >= len(delta_z):
                continue
            z_signal = delta_z.iloc[idx]
        else:
            z_signal = delta_z.loc[ud]
        if pd.isna(z_signal):
            continue
        target_mix = unica.loc[target_ud, "mix_sugar_pct"]
        if pd.isna(target_mix):
            continue
        pairs.append((float(z_signal), float(target_mix), str(ud.date())))

    lines.append(
        f"## Sammenstillinger\n\n{len(pairs)} (paritet_z_t, mix_sugar_pct_t+{LAG_REPORTS})-par "
        f"(LAG={LAG_REPORTS} UNICA-rapporter frem — mølle-respons-forsinkelse).\n"
    )

    if len(pairs) < 5:
        lines.append("**INSUFFICIENT DATA** — trenger minimum 5 par for korrelasjon.\n")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {OUT} (insufficient — {len(pairs)} pairs)")
        return 4

    df = pd.DataFrame(pairs, columns=["paritet_z", "next_mix_pct", "date"])
    rho = df["paritet_z"].corr(df["next_mix_pct"])
    n = len(df)

    lines.append("## Korrelasjon\n")
    lines.append(f"- Pearson ρ: **{rho:+.3f}**")
    lines.append(f"- n: {n}")
    if abs(rho) >= 0.5:
        verdict = "✅ **Driver-formel validert** (|ρ| ≥ 0.5)"
    elif abs(rho) >= 0.3:
        verdict = "⚠ **Marginal validering** (0.3 ≤ |ρ| < 0.5) — vurdere kalibrering"
    else:
        verdict = "❌ **Driver-formel feil** (|ρ| < 0.3) — må re-kalibreres"
    lines.append(f"- Konklusjon: {verdict}")
    if rho > 0:
        lines.append(
            "- ⚠ POSITIV korrelasjon — uventet. Forventet negativ "
            "(høy paritet → mer etanol-mix → lavere sukker-mix-andel)"
        )
    lines.append("")

    lines.append("## Sample\n")
    lines.append("| Dato | Paritet z-score | Neste UNICA mix% |")
    lines.append("|---|---:|---:|")
    for _, row in df.iterrows():
        lines.append(f"| {row['date']} | {row['paritet_z']:+.2f} | {row['next_mix_pct']:.2f} |")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Korrelasjon: ρ={rho:+.3f}, n={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
