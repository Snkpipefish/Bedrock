# Snapshot diff — sub-fase 12.10 follow-up Spor A2

**Dato:** 2026-05-02
**Pre-baseline:** post-A1 (commit `bf9e5ea`, lagret som `/tmp/baseline_pre_a2.json`)
**Post-baseline:** etter A2-wirings

## Hva ble levert

Andre runde YAML-wirings — utvider A1-mønsteret med komplementerende drivere på samme 5-6 instrumenter. Lav-risiko-batch (vekter 0.05-0.10) for å holde stop-criterion innenfor margin.

| Instrument | Familie | Driver lagt til | Vekt | Bunke | Trimmet ned |
|---|---|---|---|---|---|
| CrudeOil | macro | `eia_distillate_change` | 0.10 | 6 #22 | dxy 0.25→0.20, vix 0.20→0.15 |
| Brent | macro | `eia_distillate_change` | 0.10 | 6 #22 | (samme som CrudeOil) |
| Silver | macro | `gvz_z` | 0.10 | 4 #15 | real_yield 0.20→0.15, etf 0.20→0.15 |
| SP500 | risk | `vvix_z` | 0.05 | 4 #15 | vol_regime 0.39→0.34 |
| Nasdaq | risk | `vvix_z` | 0.05 | 4 #15 | vol_regime 0.39→0.34 |
| Gold | macro | `seismic_m6_global_24h` | 0.05 | 8 #28 | real_yield 0.30→0.25 |

**6 driver-wirings i 6 instrumenter.** Pydantic-load OK (familie-sum=1.00 i alle berørte familier). Total nye drivere wired etter A1+A2: 14 (8 fra A1 + 6 fra A2).

## Diff vs pre-A2 baseline

- **Score-endringer:** 36 av 104 (alle 6 berørte instrumenter × 3 horisonter × 2 retninger)
- **Grade-flips:** **0**
- **Top score-Δ:** ingen over 0.1 (alle 36 endringer er |Δ| < 0.1) — særdeles modest impact

### Per asset-class

| Asset-class | Score-Δ | Grade-flips | Status |
|---|---:|---:|---|
| indices | 12 | 0 | OK |
| energy | 12 | 0 | OK |
| metals | 12 | 0 | OK |
| fx, crypto, softs, grains | 0 | 0 | uendret |

**Stop-criterion ≤5 grade-flips per asset-class:** OK (0 i alle).

## Akkumulert effekt A1 + A2

| Spor | Wirings | Grade-flips | Top \|Δ\| |
|---|---:|---:|---:|
| A1 | 8 | 0 | 0.147 (SP500 SWING) |
| A2 | 6 | 0 | < 0.1 (alle) |
| **Sum** | **14** | **0** | — |

Begge runder under stop-criterion. Trygt å fortsette utvidelse til neste batch instrumenter / flere drivere.

## Hva som *ikke* ble gjort i A2

Per disiplin "lav-impact først, observer, så utvide":

- **Bunke3 macro-utvidelser** (t10y3m, hy_oas_change, anfci_z, m2_yoy, dollar_index_breadth, fomc_decision_distance, initial_claims_z) — utsatt
- **Bunke4 vol-utvidelser** (move_index_z) — utsatt
- **Bunke6 EIA-utvidelser** (propane, refinery_utilization, petroleum_supplied, imports_crude, gasoline_demand) — utsatt
- **Bunke4 #17 noaa_oni_index** (#30-erstatning for `enso_regime`) — utsatt til agri-spesifikk runde
- **Bunke7 AGSI per-land** (germany/netherlands/italy_pct, withdrawal/injection_rate) — utsatt
- **Bunke9 #34** multi-lookback-konsolidering — utsatt

## Neste steg

1. La A1+A2 rulle på live-demo (~1 uke).
2. Hvis ingen anomalier i grade-distribusjon: åpne A3-runde med agri-spesifikke drivere (noaa_oni_index på Cocoa/Coffee/Sugar/Cotton, ev. AGSI per-land på NaturalGas).
3. Hvis indices/energy/metals viser systematisk grade-bias post-A1+A2: pause utvidelse, juster vekter.

**Tag:** `v0.12.10-followup-a2` (settes etter STATE.md-update).
