# Snapshot diff — sub-fase 12.10 follow-up Spor A4

**Dato:** 2026-05-02
**Pre-baseline:** post-A3 (commit `282b2e9`, lagret som `/tmp/baseline_pre_a4.json`)
**Post-baseline:** etter A4-replacement

## Hva ble levert

Agri-runde — leverer § 22.2 #30: "erstatt `enso_regime` med `noaa_oni_index`". 1:1 driver-swap i alle 7 ENSO-følsomme agri-instrumenter.

| Instrument | Familie | Endring |
|---|---|---|
| Cocoa, Coffee, Sugar, Cotton, Corn, Soybean, Wheat | enso | `enso_regime@1.0` → `noaa_oni_index@1.0` |

Family-vekt + horisont-filter + bull_when-default uendret. Begge drivere leser identisk NOAA ONI-data (914 rader 1950-2026 i `fundamentals`). Forskjellen er primært implementasjons-detaljer:

| Aspekt | enso_regime (agri.py) | noaa_oni_index (macro_bunke4.py) |
|---|---|---|
| ADR-010 mode-suite | partial (`_horizon` lest, ikke brukt) | full (`pct_12m`, `delta_5d_z`, etc.) |
| Threshold-mapping | `(-1.5, 1.0), (-0.5, 0.75), (0.5, 0.5), (1.0, 0.25)` | `(-1.5, 1.0), (-0.5, 0.75), (0.5, 0.5), (1.5, 0.25)` |
| Series-id | `NOAA_ONI` | `ONI` |

Begge series-IDer eksisterer i DB med identisk innhold (914 rader, 1950-01 → 2026-02).

## Diff vs pre-A4 baseline

- **Score-endringer:** **0**
- **Grade-flips:** **0**

**Bit-identisk** — current ONI=-0.16 (mid-neutral) mapper til 0.5 i begge drivere. Forskjellen i upper-threshold (1.0 vs 1.5) blir kun synlig ved sterk El Niño (ONI ≥ 1.0), som ikke er nåværende regime.

Per asset-class:

| Asset-class | Score-Δ | Grade-flips |
|---|---:|---:|
| Alle (22 instrumenter) | 0 | 0 |

**Stop-criterion ≤5 grade-flips per asset-class:** OK (0 i alle).

## Akkumulert effekt A1 + A2 + A3 + A4

| Spor | Wirings | Grade-flips | Top \|Δ\| |
|---|---:|---:|---:|
| A1 | 8 | 0 | 0.147 |
| A2 | 6 | 0 | < 0.1 |
| A3 | 7 | 0 | < 0.1 |
| A4 | 7 (replacements) | 0 | 0 |
| **Sum** | **21 added + 7 replaced** | **0** | — |

22/22 instrumenter er nå wired med drivere fra 12.10-bunkene. 6/9 bunker har drivere i bruk (3, 4, 6, 7, 8, og 12.10-bunkene-9 som default-bumps).

## Hva noaa_oni_index gir over tid

Selv om scoring er bit-identisk *idag*, gir replacement-en:

1. **ADR-010-konsistens:** noaa_oni_index har full mode-suite (`pct_12m`, `pct_36m`, `delta_5d_z`, `delta_20d_z`, `extreme_high`, `extreme_low`). Senere YAML-konfigurasjoner kan utnytte ulike modes uten driver-omskrivning.
2. **Bunke9 #30-kompletthet:** § 22.2 stop-criterion-leveranse oppfylt.
3. **Nominell tydelighet:** "noaa_oni_index" navngir kilden direkte; "enso_regime" var indirekt.

## Hva som *ikke* ble gjort

- **agri-spesifikke param-overrides** (eks. invert=true for Argentinian wheat ved El Niño) — utsatt; default `bull_when=low` (La Niña bullish) gjelder per ny driver.
- **`enso_regime` driver i `agri.py` er nå død kode** men beholdt for evt. backwardskompatibilitet — kan slettes når 12.10 helt LUKKES (egen oppryddings-commit).

## Neste steg

A5: Bunke3 makro-utvidelser (t10y3m, hy_oas_change, anfci_z, m2_yoy) på indices/FX. Universelle credit/growth-signaler.

**Tag:** `v0.12.10-followup-a4`.
