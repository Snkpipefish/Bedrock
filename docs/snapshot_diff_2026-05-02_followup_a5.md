# Snapshot diff — sub-fase 12.10 follow-up Spor A5

**Dato:** 2026-05-02
**Pre-baseline:** post-A4 (commit `eed0f89`, lagret som `/tmp/baseline_pre_a5.json`)
**Post-baseline:** etter A5-wirings

## Hva ble levert

Femte runde — bunke3 makro-utvidelser (likviditet + recession-leader) på indices + crypto. Fokus på drivere som komplementerer eksisterende NetFedLiq/NFCI-input med M2-vekst og yield-curve-spread.

| Instrument | Familie | Driver lagt til | Vekt | Bunke | Trimmet ned |
|---|---|---|---|---|---|
| SP500 | macro | `m2_yoy` (MAKRO) | 0.05 | 3 #11 | real_yield 0.20→0.15 |
| SP500 | macro | `t10y3m` (MAKRO) | 0.05 | 3 #7 | dxy 0.20→0.15 |
| Nasdaq | macro | `m2_yoy` (MAKRO) | 0.05 | 3 #11 | real_yield 0.25→0.20 |
| Nasdaq | macro | `t10y3m` (MAKRO) | 0.05 | 3 #7 | dxy 0.20→0.15 |
| BTC | macro | `m2_yoy` (MAKRO) | 0.10 | 3 #11 | real_yield 0.20→0.15, dxy 0.20→0.15 |
| ETH | macro | `m2_yoy` (MAKRO) | 0.10 | 3 #11 | real_yield 0.20→0.15, dxy 0.20→0.15 |

**6 driver-wirings i 4 instrumenter.** Crypto får tyngst M2-vekt (0.10) fordi empirisk likviditets-sensitivitet er meget høy (2020-21 bull-fase). Indices får lavere vekt (0.05) fordi NetFedLiq + NFCI allerede dekker likviditets-signal.

## Diff vs pre-A5 baseline

- **Score-endringer:** 24 av 104 (kun de 4 berørte instrumenter × 3 horisonter × 2 retninger)
- **Grade-flips:** **0**
- **Top score-Δ:** ingen over 0.1

### Per asset-class

| Asset-class | Score-Δ | Grade-flips |
|---|---:|---:|
| indices | 12 | 0 |
| crypto | 12 | 0 |
| fx, energy, metals, softs, grains | 0 | 0 |

**Stop-criterion ≤5 grade-flips per asset-class:** OK (0 i alle).

## Akkumulert effekt A1 + A2 + A3 + A4 + A5

| Spor | Wirings | Replacements | Grade-flips |
|---|---:|---:|---:|
| A1 | 8 | 0 | 0 |
| A2 | 6 | 0 | 0 |
| A3 | 7 | 0 | 0 |
| A4 | 0 | 7 | 0 |
| A5 | 6 | 0 | 0 |
| **Sum** | **27 added + 7 replaced** | — | **0** |

22/22 instrumenter wired med 12.10-bunke-drivere. 6/9 bunker har drivere i bruk (3, 4, 6, 7, 8, 9-defaults).

## Live-data sanity

- M2SL: 120 monthly rows 2016-2026 (M2 YoY beregner 12-mnd vekst)
- DGS10 + DGS3MO: 4260 + 2610 daily rows (t10y3m beregner spread internt)
- Live SP500 MAKRO: m2_yoy=0.5 (M2 YoY mid-range), t10y3m=0.75 (curve mildt steep, post-disinversion)

## Hva som *ikke* ble gjort

- **bunke3-resterende drivere** for andre asset-classes:
  - `hy_oas_change` (HY credit, 794 rows fra 2023): kunne wires for SP500/Nasdaq risk, men overlapper credit_spread_change. Utsatt.
  - `initial_claims_z`/`continuing_claims_z` (labor weakness): kunne wires for SP500/Nasdaq risk; svak relevans for FX/metals. Utsatt.
  - `industrial_production_yoy`/`cfnai_3mma`/`umich_sentiment_z`/`jolts_openings_yoy` (growth): bredere scope; egne wirings senere.
  - `anfci_z` (justert NFCI): overlapper nfci_change. Utsatt.
  - `fomc_decision_distance`: overlapper event_distance. Utsatt eller ikke.
  - `t_bill_3mo_yield`: overlapper med t10y3m via DGS3MO. Utsatt.
- **bunke4 move_index_z**: kunne wires til SP500/Nasdaq som bond-vol cross-check.

## Neste steg

Foreløpig 5 spor levert (A1-A5) med konsistent 0 grade-flips. Kan fortsette med:
- A6: bunke6 EIA-resterende drivere (propane, refinery, etc.) for energy
- A7: bunke7 AGSI-resterende (italy, withdrawal, injection_rate, cot_oi_change, cot_commercial_extreme)
- A8: bunke3 labor/growth (initial_claims_z, industrial_production_yoy, etc.)

**Tag:** `v0.12.10-followup-a5`.
