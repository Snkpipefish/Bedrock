# Snapshot diff — sub-fase 12.10 follow-up Spor A1

**Dato:** 2026-05-02
**Pre-baseline:** post-12.10-LUKKET (commit `1a9befd`, baseline lagret som `/tmp/baseline_pre_a1.json`)
**Post-baseline:** etter A1-wirings (4 commits + denne)

## Hva ble levert

Første runde YAML-wirings av drivere registrert i sub-fase 12.10 men ikke wired. Per § 22.1 PRIMÆR-spor (live-demo-validering først, så utvide).

| Instrument | Familie | Driver lagt til | Vekt | Bunke | Trimmet ned |
|---|---|---|---|---|---|
| SP500 | risk | `cboe_skew_z` | 0.10 | 4 #16 | vol_regime 0.59→0.39 |
| SP500 | risk | `vix9d_vix_ratio` | 0.10 (SCALP/SWING) | 3 #12 | (samme) |
| Nasdaq | risk | `cboe_skew_z` | 0.10 | 4 #16 | vol_regime 0.59→0.39 |
| Nasdaq | risk | `vix9d_vix_ratio` | 0.10 (SCALP/SWING) | 3 #12 | (samme) |
| CrudeOil | macro | `ovx_z` | 0.15 | 4 #15 | real_yield 0.15→0.10, dxy 0.35→0.25 |
| Brent | macro | `ovx_z` | 0.15 | 4 #15 | (samme som CrudeOil) |
| Gold | macro | `gvz_z` | 0.10 | 4 #15 | real_yield 0.35→0.30, etf 0.15→0.10 |
| Copper | macro | `seismic_chile_peru_copper` | 0.10 | 8 #28 | real_yield 0.25→0.20, mining 0.15→0.10 |

**8 driver-wirings i 6 instrumenter.** Alle Pydantic-validert (familie-sum=1.00 holder, 22/22 instrumenter laster uten feil).

## Diff vs pre-A1 baseline

- **Score-endringer (>1e-6):** 36 av 104 rader (alle 6 berørte instrumenter × 3 horisonter × 2 retninger)
- **Grade-flips:** **0**
- **Andre 16 instrumenter:** uendret (ingen analog-cross-effekter siden analog-familien ikke berøres)

### Per asset-class

| Asset-class | Score-endringer | Grade-flips | Status |
|---|---:|---:|---|
| indices | 12 | 0 | OK |
| energy | 12 | 0 | OK |
| metals | 12 | 0 | OK |
| fx | 0 | 0 | uendret |
| crypto | 0 | 0 | uendret |
| softs | 0 | 0 | uendret |
| grains | 0 | 0 | uendret |

**Stop-criterion ≤5 grade-flips per asset-class:** OK (0 i alle).

### Topp score-endringer (|Δ| > 0.1)

| Key | Pre | Post | Δ |
|---|---:|---:|---:|
| SP500\|SWING\|sell | 1.553 | 1.700 | +0.147 |
| SP500\|SWING\|buy | 2.942 | 3.089 | +0.147 |
| SP500\|SCALP\|sell | 1.233 | 1.351 | +0.118 |
| SP500\|SCALP\|buy | 2.962 | 3.080 | +0.118 |

Resterende 32 endringer er |Δ| < 0.1 — modest impact, som forventet for 1-2 nye drivere per familie med vekt 0.10-0.15.

## Live-driver-verifisering (2026-05-02 09:30 UTC)

| Driver | Live-verdi | Tolkning |
|---|---:|---|
| `cboe_skew_z` | 0.6 | SKEW=140.59, z+0.4σ — mid-range tail-bekymring |
| `vix9d_vix_ratio` | 0.6 | VIX9D/VIX=0.96 — front-end stabilitet |
| `ovx_z` | 0.0 | OVX z>2σ — oljevol elevert (geopolitisk) |
| `gvz_z` | 0.3 | GVZ z>0σ — mild gull-vol-bekymring |
| `seismic_chile_peru_copper` | 0.75 | 1 M ≥ 5.5 i Chile/Peru siste 7d |

Alle 5 nye drivere returnerer ikke-default-verdier — signaler er aktive, ikke konstant 0.5.

## Hva som *ikke* ble gjort i denne runden

Per § 22.1 (live-demo-validering først, ikke big-bang):

- **EIA-utvidelser** (eia_distillate_change, eia_propane_change, eia_refinery_utilization_z, eia_petroleum_supplied, eia_imports_crude, eia_gasoline_demand) — utsatt til neste A-runde
- **Bunke3 macro-utvidelser** (t10y3m, hy_oas_change, initial_claims_z, anfci_z, m2_yoy, etc.) — utsatt
- **noaa_oni_index** (#30 erstatning for enso_regime) — utsatt
- **dollar_index_breadth, fomc_decision_distance** — utsatt
- **Bunke7 AGSI-utvidelser** (agsi_germany_pct etc.) — utsatt
- **#34 multi-lookback-konsolidering** — utsatt

Strategi: vente og se hvordan A1-wirings oppfører seg på live-demo (1-2 uker), så utvide til neste batch instrumenter/drivere hvis ingen systematisk bias.

## Neste steg

1. La A1-wirings rulle på live-demo. Følge med signals_bot.json + faktiske trades.
2. Hvis ingen anomalier etter ~1 uke: åpne neste runde (A2 — utvid til metaler + FX med tilsvarende low-impact-batch).
3. Hvis grade-distribusjonen viser anomalier på A1-instrumenter: justere vekter eller revertere før utvidelse.

**Tag:** `v0.12.10-followup-a1` (settes på siste A1-commit etter STATE.md-update).
