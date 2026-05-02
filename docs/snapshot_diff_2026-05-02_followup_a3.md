# Snapshot diff — sub-fase 12.10 follow-up Spor A3

**Dato:** 2026-05-02
**Pre-baseline:** post-A2 (commit `453c012`, lagret som `/tmp/baseline_pre_a3.json`)
**Post-baseline:** etter A3-wirings

## Hva ble levert

Tredje runde YAML-wirings — utvider scope til ikke-berørte asset-classes: Platinum (siste metals), 4 FX, og NaturalGas (per-land AGSI). Lav-vekt-batch (0.05-0.10) konsistent med A1+A2-disiplin.

| Instrument | Familie | Driver lagt til | Vekt | Bunke | Trimmet ned |
|---|---|---|---|---|---|
| Platinum | macro | `gvz_z` | 0.10 | 4 #15 | dxy 0.35→0.30, mining_disruption 0.30→0.25 |
| EURUSD | macro | `dollar_index_breadth` | 0.10 | 3 #13 | real_yield 0.25→0.20, dxy 0.30→0.25 |
| GBPUSD | macro | `dollar_index_breadth` | 0.10 | 3 #13 | real_yield 0.25→0.20, dxy 0.30→0.25 |
| USDJPY | macro | `dollar_index_breadth` | 0.10 (bull_when=high) | 3 #13 | real_yield 0.25→0.20, dxy 0.30→0.25 |
| AUDUSD | macro | `dollar_index_breadth` | 0.10 | 3 #13 | dxy 0.30→0.25, vix 0.25→0.20 |
| NaturalGas | macro | `agsi_germany_pct` | 0.05 | 7 #23 | agsi_storage_pct 0.10→0.05 |
| NaturalGas | macro | `agsi_netherlands_pct` | 0.05 | 7 #23 | dxy 0.20→0.15 |

**7 driver-wirings i 6 instrumenter.** Dollar-index-breadth-driveren er deterministisk (samme 8 DEX-pairs uavhengig av instrumentet) men differensieres via `bull_when` per FX-par (low for non-USD-pairs, high for USDJPY).

## Diff vs pre-A3 baseline

- **Score-endringer:** 36 av 104
- **Grade-flips:** **0**
- **Top score-Δ:** ingen over 0.1

### Per asset-class

| Asset-class | Score-Δ | Grade-flips | Status |
|---|---:|---:|---|
| fx | 24 | 0 | OK (4 inst × 3 hor × 2 dir) |
| metals | 6 | 0 | OK (Platinum × 6) |
| energy | 6 | 0 | OK (NaturalGas × 6) |
| indices, crypto, softs, grains | 0 | 0 | uendret |

**Stop-criterion ≤5 grade-flips per asset-class:** OK (0 i alle).

## Akkumulert effekt A1 + A2 + A3

| Spor | Wirings | Grade-flips | Top \|Δ\| |
|---|---:|---:|---:|
| A1 | 8 | 0 | 0.147 |
| A2 | 6 | 0 | < 0.1 |
| A3 | 7 | 0 | < 0.1 |
| **Sum** | **21** | **0** | — |

21 nye driver-wirings akkumulert. Tre av §22.2-bunkenes drivere er nå i bruk: bunke3 (dollar_index_breadth, vix9d_vix_ratio), bunke4 (cboe_skew_z, vvix_z, gvz_z, ovx_z), bunke6 (eia_distillate_change), bunke7 (agsi_germany_pct, agsi_netherlands_pct), bunke8 (seismic_chile_peru_copper, seismic_m6_global_24h).

## Coverage etter A3

15 av 22 instrumenter har nå fått minst én ny driver fra 12.10-bunkene wired. Resterende 7:

- BTC, ETH (crypto)
- Cocoa, Coffee, Sugar, Cotton (softs)
- Corn, Soybean, Wheat (grains)

Disse trenger agri/crypto-spesifikke drivere (noaa_oni_index for ENSO-følsomme softs/grains; crypto_sentiment_extreme er DEFERRED til ~juli 2026 per § 22.2 #29).

## Hva som *ikke* ble gjort i A3

- **noaa_oni_index** (#30) for Cocoa/Coffee/Sugar/Cotton/Corn/Wheat — utsatt til A4 (agri-spesifikk runde)
- **Bunke3 macro-utvidelser** (t10y3m, hy_oas_change, anfci_z, m2_yoy, fomc_decision_distance, initial_claims_z, etc.) — utsatt
- **Bunke4 move_index_z** (treasury vol z-score) — utsatt
- **Bunke6 EIA-resterende** (propane, refinery_utilization, petroleum_supplied, imports_crude, gasoline_demand) — utsatt

## Neste steg

A4: agri-runde med `noaa_oni_index` på ENSO-følsomme softs + grains. Lav-impact (0.05-0.10 vekter), separate per asset-class for å holde grade-flips innen margin.

**Tag:** `v0.12.10-followup-a3`.
