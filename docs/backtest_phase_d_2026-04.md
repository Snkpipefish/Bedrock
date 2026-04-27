# Backtest Phase D — session 116

Dato: 2026-04-27. Sub-fase 12.5+ Phase D-validering etter 11/11
fetcher-porter (sessions 105-115). Baseline: session 99
(`docs/backtest_whitelist_2026-04-26.md`).

## Metode

**Baseline-aggregering**: re-kjøring av session 99-script på
`analog_outcomes`-tabellen. Tom-til-toms-bekreftelse på at
datagrunnlaget er uendret. Phase A-C-fetchere skriver ikke til
outcomes; baseline skal være identisk med session 99.

**Orchestrator-replay**: `run_orchestrator_replay` kjøres for
12 instrumenter × {30d, 90d} × {buy, sell} på 12-måneders vindu
med step_days=21 (3-ukentlig sampling) — gir ~12 ref_dates per
(inst, hor, dir). Per ref_date kalles `generate_signals` med
AsOfDateStore som klipper alle datakilder til ref_date.

**Sub-fase 12.5+ AsOfDateStore-utvidelse (gjort i denne session)**:
9 nye proxy-getters lagt til for å støtte clipping av Phase A-C
tabeller (econ_events, cot_ice, eia_inventory, comex_inventory,
seismic_events, cot_euronext, conab_estimates, unica_reports,
shipping_indices). Uten denne utvidelsen falt drivere stille
tilbake til 0.0-default fordi underlying-getterne kastet
AttributeError. Dette var en kritisk blokker for backtest-validity.

**Flagging-terskel**: ≥3.0pp Δhit_rate eller
≥2 grade-flips per (instrument, horizon, dir).

## Begrensninger

- Phase A-C-data er fersk (1-2 dagers backfill ved session 116).
  For backtest-window 12 mnd er nye drivere mest 'data_missing'
  for de eldste ref_dates → score = defensive 0.0. Effekten på
  scoring er kun målbar de siste få ref_dates der Phase A-C-data
  faktisk eksisterer.
- Empirisk validering av Phase A-C-driverbidrag krever ≥1 mnd
  data-akkumulering (per ADR-007 § 5). Session 117 / ADR-009
  cutover-readiness-audit forventes å re-vurdere når mer data
  finnes.

## Baseline-bekreftelse (session 99-reprise)

Kilde: `data/_meta/backtest_phase_d_baseline.json`

Aggregering på `analog_outcomes`-tabellen for 17 whitelist-
instrumenter × 2 horisonter × 2 retninger. Skal være identisk
med session 99 — Phase A-C har ikke endret outcomes-data.

| Instrument | Hor | Dir | n | hit-rate | avg return | stdev |
|---|---:|---|---:|---:|---:|---:|
| EURUSD       |  30d | buy  |  4217 |  12.7% | -0.10% |  2.75% |
| EURUSD       |  30d | sell |  4217 |  12.2% | -0.10% |  2.75% |
| EURUSD       |  90d | buy  |  4157 |  12.4% | -0.22% |  4.86% |
| EURUSD       |  90d | sell |  4157 |  15.4% | -0.22% |  4.86% |
| USDJPY       |  30d | buy  |  4217 |  18.4% | +0.45% |  3.14% |
| USDJPY       |  30d | sell |  4217 |  12.0% | +0.45% |  3.14% |
| USDJPY       |  90d | buy  |  4157 |  22.7% | +1.35% |  5.97% |
| USDJPY       |  90d | sell |  4157 |  12.0% | +1.35% |  5.97% |
| GBPUSD       |  30d | buy  |  4217 |  11.5% | -0.09% |  2.76% |
| GBPUSD       |  30d | sell |  4217 |  13.3% | -0.09% |  2.76% |
| GBPUSD       |  90d | buy  |  4157 |  12.4% | -0.20% |  4.60% |
| GBPUSD       |  90d | sell |  4157 |  17.1% | -0.20% |  4.60% |
| AUDUSD       |  30d | buy  |  4216 |  16.7% | -0.12% |  3.34% |
| AUDUSD       |  30d | sell |  4216 |  18.8% | -0.12% |  3.34% |
| AUDUSD       |  90d | buy  |  4156 |  13.6% | -0.44% |  5.42% |
| AUDUSD       |  90d | sell |  4156 |  18.1% | -0.44% |  5.42% |
| Gold         |  30d | buy  |  4071 |  34.5% | +1.21% |  5.35% |
| Gold         |  30d | sell |  4071 |  20.7% | +1.21% |  5.35% |
| Gold         |  90d | buy  |  4011 |  44.0% | +3.72% |  9.48% |
| Gold         |  90d | sell |  4011 |  19.1% | +3.72% |  9.48% |
| Silver       |  30d | buy  |  4071 |  37.9% | +1.68% | 11.19% |
| Silver       |  30d | sell |  4071 |  35.1% | +1.68% | 11.19% |
| Silver       |  90d | buy  |  4011 |  39.1% | +5.30% | 21.31% |
| Silver       |  90d | sell |  4011 |  29.3% | +5.30% | 21.31% |
| CrudeOil     |  30d | buy  |  4071 |  41.4% | +1.18% | 15.73% |
| CrudeOil     |  30d | sell |  4071 |  36.3% | +1.18% | 15.73% |
| CrudeOil     |  90d | buy  |  4011 |  41.7% | +2.36% | 23.71% |
| CrudeOil     |  90d | sell |  4011 |  36.4% | +2.36% | 23.71% |
| Brent        |  30d | buy  |  4041 |  40.5% | +1.03% | 12.70% |
| Brent        |  30d | sell |  4041 |  34.6% | +1.03% | 12.70% |
| Brent        |  90d | buy  |  3981 |  38.9% | +2.19% | 21.12% |
| Brent        |  90d | sell |  3981 |  36.2% | +2.19% | 21.12% |
| SP500        |  30d | buy  |  4073 |  40.6% | +1.47% |  4.92% |
| SP500        |  30d | sell |  4073 |  14.3% | +1.47% |  4.92% |
| SP500        |  90d | buy  |  4013 |  50.5% | +4.39% |  7.54% |
| SP500        |  90d | sell |  4013 |  11.0% | +4.39% |  7.54% |
| Nasdaq       |  30d | buy  |  4073 |  47.3% | +2.13% |  5.98% |
| Nasdaq       |  30d | sell |  4073 |  17.0% | +2.13% |  5.98% |
| Nasdaq       |  90d | buy  |  4013 |  59.7% | +6.41% |  9.51% |
| Nasdaq       |  90d | sell |  4013 |  11.5% | +6.41% |  9.51% |
| Corn         |  30d | buy  |  4069 |  36.6% | +0.58% |  9.42% |
| Corn         |  30d | sell |  4069 |  32.6% | +0.58% |  9.42% |
| Corn         |  90d | buy  |  4009 |  35.1% | +1.84% | 17.41% |
| Corn         |  90d | sell |  4009 |  37.0% | +1.84% | 17.41% |
| Wheat        |  30d | buy  |  4071 |  34.4% | +0.63% | 10.44% |
| Wheat        |  30d | sell |  4071 |  37.3% | +0.63% | 10.44% |
| Wheat        |  90d | buy  |  4011 |  31.8% | +1.36% | 15.30% |
| Wheat        |  90d | sell |  4011 |  35.2% | +1.36% | 15.30% |
| Soybean      |  30d | buy  |  4071 |  33.1% | +0.41% |  7.22% |
| Soybean      |  30d | sell |  4071 |  30.4% | +0.41% |  7.22% |
| Soybean      |  90d | buy  |  4011 |  31.4% | +1.23% | 13.61% |
| Soybean      |  90d | sell |  4011 |  31.8% | +1.23% | 13.61% |
| Coffee       |  30d | buy  |  4071 |  38.8% | +1.20% | 11.48% |
| Coffee       |  30d | sell |  4071 |  38.3% | +1.20% | 11.48% |
| Coffee       |  90d | buy  |  4011 |  40.1% | +3.83% | 20.51% |
| Coffee       |  90d | sell |  4011 |  39.2% | +3.83% | 20.51% |
| Cotton       |  30d | buy  |  4072 |  36.3% | +0.49% |  9.71% |
| Cotton       |  30d | sell |  4072 |  30.1% | +0.49% |  9.71% |
| Cotton       |  90d | buy  |  4012 |  35.9% | +1.32% | 18.71% |
| Cotton       |  90d | sell |  4012 |  34.5% | +1.32% | 18.71% |
| Sugar        |  30d | buy  |  4072 |  33.8% | +0.11% | 10.93% |
| Sugar        |  30d | sell |  4072 |  39.0% | +0.11% | 10.93% |
| Sugar        |  90d | buy  |  4012 |  34.9% | +0.84% | 19.00% |
| Sugar        |  90d | sell |  4012 |  45.0% | +0.84% | 19.00% |
| Cocoa        |  30d | buy  |  4071 |  38.5% | +0.74% | 12.42% |
| Cocoa        |  30d | sell |  4071 |  35.5% | +0.74% | 12.42% |
| Cocoa        |  90d | buy  |  4011 |  41.0% | +2.63% | 22.63% |
| Cocoa        |  90d | sell |  4011 |  34.5% | +2.63% | 22.63% |

## Orchestrator-replay (current state)

Kilde: `data/_meta/backtest_phase_d_orchestrator.json`

Vindu: 2025-04-27 til 2026-04-27
Step: 21 dager

| Instrument | Hor | Dir | n | hit-rate | publish-rate | avg score | avg pub.score |
|---|---:|---|---:|---:|---:|---:|---:|
| Gold         |  30d | buy  |  11 |  54.5% |  81.8% | 2.879 | 2.718 |
| Gold         |  30d | sell |  11 |   9.1% |  81.8% | 2.377 | 2.549 |
| Gold         |  90d | buy  |   8 | 100.0% |  12.5% | 2.514 | 3.019 |
| Gold         |  90d | sell |   8 |   0.0% |   0.0% | 3.431 |   -   |
| Brent        |  30d | buy  |  11 |  36.4% |  63.6% | 2.165 | 2.376 |
| Brent        |  30d | sell |  11 |  27.3% |  72.7% | 2.826 | 2.630 |
| Brent        |  90d | buy  |   8 |  25.0% |   0.0% | 2.123 |   -   |
| Brent        |  90d | sell |   8 |  25.0% |  12.5% | 3.600 | 3.772 |
| CrudeOil     |  30d | buy  |  11 |  45.5% |  54.5% | 1.993 | 2.252 |
| CrudeOil     |  30d | sell |  11 |  27.3% |  72.7% | 2.943 | 2.832 |
| CrudeOil     |  90d | buy  |   8 |  25.0% |   0.0% | 2.130 |   -   |
| CrudeOil     |  90d | sell |   8 |  37.5% |  12.5% | 3.583 | 4.248 |
| Corn         |  30d | buy  |  11 |  27.3% |  45.5% | 6.804 | 7.493 |
| Corn         |  30d | sell |  11 |  36.4% | 100.0% | 10.718 | 10.718 |
| Corn         |  90d | buy  |   8 |  37.5% |  25.0% | 6.536 | 7.454 |
| Corn         |  90d | sell |   8 |  25.0% | 100.0% | 11.082 | 11.082 |
| Wheat        |  30d | buy  |  11 |  18.2% |  90.9% | 8.247 | 8.150 |
| Wheat        |  30d | sell |  11 |   9.1% |  81.8% | 6.903 | 7.128 |
| Wheat        |  90d | buy  |   8 |  25.0% |  87.5% | 8.297 | 8.166 |
| Wheat        |  90d | sell |   8 |   0.0% | 100.0% | 7.034 | 7.034 |
| Soybean      |  30d | buy  |  11 |  27.3% |  54.5% | 6.313 | 7.012 |
| Soybean      |  30d | sell |  11 |  27.3% |  63.6% | 11.359 | 10.828 |
| Soybean      |  90d | buy  |   8 |  50.0% |  37.5% | 5.843 | 6.456 |
| Soybean      |  90d | sell |   8 |   0.0% |  50.0% | 11.782 | 11.275 |
| Sugar        |  30d | buy  |  11 |   0.0% |  81.8% | 9.913 | 10.055 |
| Sugar        |  30d | sell |  11 |  63.6% |  90.9% | 7.796 | 7.970 |
| Sugar        |  90d | buy  |   8 |   0.0% |  87.5% | 10.635 | 10.476 |
| Sugar        |  90d | sell |   8 |  75.0% | 100.0% | 6.965 | 6.965 |
| Coffee       |  30d | buy  |  11 |  27.3% |  45.5% | 6.777 | 7.426 |
| Coffee       |  30d | sell |  11 |  45.5% |  72.7% | 11.114 | 11.263 |
| Coffee       |  90d | buy  |   8 |  37.5% | 100.0% | 7.323 | 7.323 |
| Coffee       |  90d | sell |   8 |  62.5% |  62.5% | 10.527 | 10.414 |
| Cocoa        |  30d | buy  |  11 |  27.3% |  81.8% | 8.262 | 8.897 |
| Cocoa        |  30d | sell |  11 |  72.7% |  81.8% | 7.565 | 7.986 |
| Cocoa        |  90d | buy  |   8 |   0.0% | 100.0% | 9.208 | 9.208 |
| Cocoa        |  90d | sell |   8 | 100.0% |  75.0% | 6.698 | 7.039 |
| SP500        |  30d | buy  |  11 |  45.5% |   9.1% | 3.366 | 3.187 |
| SP500        |  30d | sell |  11 |   9.1% |   0.0% | 1.499 |   -   |
| SP500        |  90d | buy  |   8 |  62.5% |  75.0% | 3.236 | 3.371 |
| SP500        |  90d | sell |   8 |   0.0% |   0.0% | 1.733 |   -   |
| EURUSD       |  30d | buy  |  11 |   9.1% |  63.6% | 2.985 | 3.016 |
| EURUSD       |  30d | sell |  11 |   0.0% |  36.4% | 1.812 | 2.130 |
| EURUSD       |  90d | buy  |   9 |   0.0% |  33.3% | 3.326 | 3.787 |
| EURUSD       |  90d | sell |   9 |   0.0% |   0.0% | 1.888 |   -   |
| USDJPY       |  30d | buy  |  11 |  27.3% |   9.1% | 2.186 | 2.720 |
| USDJPY       |  30d | sell |  11 |   0.0% |   0.0% | 2.490 |   -   |
| USDJPY       |  90d | buy  |   9 |  22.2% |   0.0% | 2.388 |   -   |
| USDJPY       |  90d | sell |   9 |   0.0% |   0.0% | 2.614 |   -   |

## Grade-distribusjon (orchestrator-replay)

| Instrument | Hor | Dir | A+ | A | B | C | D | ? |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Gold         |  30d | buy  | 1 | 6 | 4 | 0 | 0 | 0 |
| Gold         |  30d | sell | 0 | 5 | 4 | 2 | 0 | 0 |
| Gold         |  90d | buy  | 0 | 0 | 7 | 1 | 0 | 0 |
| Gold         |  90d | sell | 0 | 5 | 3 | 0 | 0 | 0 |
| Brent        |  30d | buy  | 0 | 2 | 7 | 2 | 0 | 0 |
| Brent        |  30d | sell | 1 | 6 | 4 | 0 | 0 | 0 |
| Brent        |  90d | buy  | 0 | 0 | 5 | 3 | 0 | 0 |
| Brent        |  90d | sell | 1 | 6 | 1 | 0 | 0 | 0 |
| CrudeOil     |  30d | buy  | 0 | 2 | 6 | 3 | 0 | 0 |
| CrudeOil     |  30d | sell | 2 | 4 | 5 | 0 | 0 | 0 |
| CrudeOil     |  90d | buy  | 0 | 0 | 5 | 3 | 0 | 0 |
| CrudeOil     |  90d | sell | 0 | 5 | 3 | 0 | 0 | 0 |
| Corn         |  30d | buy  | 0 | 0 | 5 | 6 | 0 | 0 |
| Corn         |  30d | sell | 0 | 7 | 4 | 0 | 0 | 0 |
| Corn         |  90d | buy  | 0 | 0 | 2 | 6 | 0 | 0 |
| Corn         |  90d | sell | 0 | 7 | 1 | 0 | 0 | 0 |
| Wheat        |  30d | buy  | 0 | 5 | 6 | 0 | 0 | 0 |
| Wheat        |  30d | sell | 0 | 2 | 8 | 1 | 0 | 0 |
| Wheat        |  90d | buy  | 0 | 4 | 4 | 0 | 0 | 0 |
| Wheat        |  90d | sell | 0 | 2 | 6 | 0 | 0 | 0 |
| Soybean      |  30d | buy  | 0 | 0 | 6 | 5 | 0 | 0 |
| Soybean      |  30d | sell | 6 | 5 | 0 | 0 | 0 | 0 |
| Soybean      |  90d | buy  | 0 | 0 | 3 | 5 | 0 | 0 |
| Soybean      |  90d | sell | 6 | 2 | 0 | 0 | 0 | 0 |
| Sugar        |  30d | buy  | 5 | 3 | 3 | 0 | 0 | 0 |
| Sugar        |  30d | sell | 1 | 3 | 5 | 2 | 0 | 0 |
| Sugar        |  90d | buy  | 5 | 2 | 1 | 0 | 0 | 0 |
| Sugar        |  90d | sell | 0 | 2 | 4 | 2 | 0 | 0 |
| Coffee       |  30d | buy  | 0 | 3 | 5 | 3 | 0 | 0 |
| Coffee       |  30d | sell | 7 | 4 | 0 | 0 | 0 | 0 |
| Coffee       |  90d | buy  | 0 | 3 | 5 | 0 | 0 | 0 |
| Coffee       |  90d | sell | 4 | 4 | 0 | 0 | 0 | 0 |
| Cocoa        |  30d | buy  | 0 | 7 | 2 | 2 | 0 | 0 |
| Cocoa        |  30d | sell | 0 | 4 | 5 | 2 | 0 | 0 |
| Cocoa        |  90d | buy  | 0 | 7 | 1 | 0 | 0 | 0 |
| Cocoa        |  90d | sell | 0 | 1 | 5 | 2 | 0 | 0 |
| SP500        |  30d | buy  | 3 | 7 | 1 | 0 | 0 | 0 |
| SP500        |  30d | sell | 0 | 1 | 1 | 9 | 0 | 0 |
| SP500        |  90d | buy  | 0 | 3 | 5 | 0 | 0 | 0 |
| SP500        |  90d | sell | 0 | 0 | 2 | 6 | 0 | 0 |
| EURUSD       |  30d | buy  | 2 | 6 | 2 | 1 | 0 | 0 |
| EURUSD       |  30d | sell | 0 | 1 | 5 | 5 | 0 | 0 |
| EURUSD       |  90d | buy  | 0 | 6 | 3 | 0 | 0 | 0 |
| EURUSD       |  90d | sell | 0 | 0 | 2 | 7 | 0 | 0 |
| USDJPY       |  30d | buy  | 0 | 3 | 6 | 2 | 0 | 0 |
| USDJPY       |  30d | sell | 0 | 4 | 6 | 1 | 0 | 0 |
| USDJPY       |  90d | buy  | 0 | 0 | 8 | 1 | 0 | 0 |
| USDJPY       |  90d | sell | 0 | 1 | 8 | 0 | 0 | 0 |

## Diff orchestrator vs session 99-baseline

Kvalitativ sammenligning. Orchestrator-hit-rate reflekterer
scoring-publishe ref_dates; baseline er full-history forward-
return-distribusjon. Store avvik kan indikere enten:
(a) scoring-edge på den retningen, eller (b) data-coverage-
skjevhet (orch sample er liten).

| Instrument | Hor | Dir | Orch hit | Base hit | ∆hit (pp) | Flagg |
|---|---:|---|---:|---:|---:|---|
| Gold         |  30d | buy  |  54.5% |  34.5% | +20.1pp | **FLAGG** |
| Gold         |  30d | sell |   9.1% |  20.7% | -11.6pp | **FLAGG** |
| Gold         |  90d | buy  | 100.0% |  44.0% | +56.0pp | **FLAGG** |
| Gold         |  90d | sell |   0.0% |  19.1% | -19.1pp | **FLAGG** |
| Brent        |  30d | buy  |  36.4% |  40.5% |  -4.1pp | **FLAGG** |
| Brent        |  30d | sell |  27.3% |  34.6% |  -7.3pp | **FLAGG** |
| Brent        |  90d | buy  |  25.0% |  38.9% | -13.9pp | **FLAGG** |
| Brent        |  90d | sell |  25.0% |  36.2% | -11.2pp | **FLAGG** |
| CrudeOil     |  30d | buy  |  45.5% |  41.4% |  +4.1pp | **FLAGG** |
| CrudeOil     |  30d | sell |  27.3% |  36.3% |  -9.0pp | **FLAGG** |
| CrudeOil     |  90d | buy  |  25.0% |  41.7% | -16.7pp | **FLAGG** |
| CrudeOil     |  90d | sell |  37.5% |  36.4% |  +1.1pp |  |
| Corn         |  30d | buy  |  27.3% |  36.6% |  -9.3pp | **FLAGG** |
| Corn         |  30d | sell |  36.4% |  32.6% |  +3.8pp | **FLAGG** |
| Corn         |  90d | buy  |  37.5% |  35.1% |  +2.4pp |  |
| Corn         |  90d | sell |  25.0% |  37.0% | -12.0pp | **FLAGG** |
| Wheat        |  30d | buy  |  18.2% |  34.4% | -16.3pp | **FLAGG** |
| Wheat        |  30d | sell |   9.1% |  37.3% | -28.2pp | **FLAGG** |
| Wheat        |  90d | buy  |  25.0% |  31.8% |  -6.8pp | **FLAGG** |
| Wheat        |  90d | sell |   0.0% |  35.2% | -35.2pp | **FLAGG** |
| Soybean      |  30d | buy  |  27.3% |  33.1% |  -5.9pp | **FLAGG** |
| Soybean      |  30d | sell |  27.3% |  30.4% |  -3.1pp | **FLAGG** |
| Soybean      |  90d | buy  |  50.0% |  31.4% | +18.6pp | **FLAGG** |
| Soybean      |  90d | sell |   0.0% |  31.8% | -31.8pp | **FLAGG** |
| Sugar        |  30d | buy  |   0.0% |  33.8% | -33.8pp | **FLAGG** |
| Sugar        |  30d | sell |  63.6% |  39.0% | +24.6pp | **FLAGG** |
| Sugar        |  90d | buy  |   0.0% |  34.9% | -34.9pp | **FLAGG** |
| Sugar        |  90d | sell |  75.0% |  45.0% | +30.0pp | **FLAGG** |
| Coffee       |  30d | buy  |  27.3% |  38.8% | -11.5pp | **FLAGG** |
| Coffee       |  30d | sell |  45.5% |  38.3% |  +7.2pp | **FLAGG** |
| Coffee       |  90d | buy  |  37.5% |  40.1% |  -2.6pp |  |
| Coffee       |  90d | sell |  62.5% |  39.2% | +23.3pp | **FLAGG** |
| Cocoa        |  30d | buy  |  27.3% |  38.5% | -11.2pp | **FLAGG** |
| Cocoa        |  30d | sell |  72.7% |  35.5% | +37.2pp | **FLAGG** |
| Cocoa        |  90d | buy  |   0.0% |  41.0% | -41.0pp | **FLAGG** |
| Cocoa        |  90d | sell | 100.0% |  34.5% | +65.5pp | **FLAGG** |
| SP500        |  30d | buy  |  45.5% |  40.6% |  +4.8pp | **FLAGG** |
| SP500        |  30d | sell |   9.1% |  14.3% |  -5.2pp | **FLAGG** |
| SP500        |  90d | buy  |  62.5% |  50.5% | +12.0pp | **FLAGG** |
| SP500        |  90d | sell |   0.0% |  11.0% | -11.0pp | **FLAGG** |
| EURUSD       |  30d | buy  |   9.1% |  12.7% |  -3.6pp | **FLAGG** |
| EURUSD       |  30d | sell |   0.0% |  12.2% | -12.2pp | **FLAGG** |
| EURUSD       |  90d | buy  |   0.0% |  12.4% | -12.4pp | **FLAGG** |
| EURUSD       |  90d | sell |   0.0% |  15.4% | -15.4pp | **FLAGG** |
| USDJPY       |  30d | buy  |  27.3% |  18.4% |  +8.8pp | **FLAGG** |
| USDJPY       |  30d | sell |   0.0% |  12.0% | -12.0pp | **FLAGG** |
| USDJPY       |  90d | buy  |  22.2% |  22.7% |  -0.5pp |  |
| USDJPY       |  90d | sell |   0.0% |  12.0% | -12.0pp | **FLAGG** |

### Flagged kombinasjoner

- Gold 30d buy: orch 54.5% vs base 34.5% (Δ +20.1pp)
- Gold 30d sell: orch 9.1% vs base 20.7% (Δ -11.6pp)
- Gold 90d buy: orch 100.0% vs base 44.0% (Δ +56.0pp)
- Gold 90d sell: orch 0.0% vs base 19.1% (Δ -19.1pp)
- Brent 30d buy: orch 36.4% vs base 40.5% (Δ -4.1pp)
- Brent 30d sell: orch 27.3% vs base 34.6% (Δ -7.3pp)
- Brent 90d buy: orch 25.0% vs base 38.9% (Δ -13.9pp)
- Brent 90d sell: orch 25.0% vs base 36.2% (Δ -11.2pp)
- CrudeOil 30d buy: orch 45.5% vs base 41.4% (Δ +4.1pp)
- CrudeOil 30d sell: orch 27.3% vs base 36.3% (Δ -9.0pp)
- CrudeOil 90d buy: orch 25.0% vs base 41.7% (Δ -16.7pp)
- Corn 30d buy: orch 27.3% vs base 36.6% (Δ -9.3pp)
- Corn 30d sell: orch 36.4% vs base 32.6% (Δ +3.8pp)
- Corn 90d sell: orch 25.0% vs base 37.0% (Δ -12.0pp)
- Wheat 30d buy: orch 18.2% vs base 34.4% (Δ -16.3pp)
- Wheat 30d sell: orch 9.1% vs base 37.3% (Δ -28.2pp)
- Wheat 90d buy: orch 25.0% vs base 31.8% (Δ -6.8pp)
- Wheat 90d sell: orch 0.0% vs base 35.2% (Δ -35.2pp)
- Soybean 30d buy: orch 27.3% vs base 33.1% (Δ -5.9pp)
- Soybean 30d sell: orch 27.3% vs base 30.4% (Δ -3.1pp)
- Soybean 90d buy: orch 50.0% vs base 31.4% (Δ +18.6pp)
- Soybean 90d sell: orch 0.0% vs base 31.8% (Δ -31.8pp)
- Sugar 30d buy: orch 0.0% vs base 33.8% (Δ -33.8pp)
- Sugar 30d sell: orch 63.6% vs base 39.0% (Δ +24.6pp)
- Sugar 90d buy: orch 0.0% vs base 34.9% (Δ -34.9pp)
- Sugar 90d sell: orch 75.0% vs base 45.0% (Δ +30.0pp)
- Coffee 30d buy: orch 27.3% vs base 38.8% (Δ -11.5pp)
- Coffee 30d sell: orch 45.5% vs base 38.3% (Δ +7.2pp)
- Coffee 90d sell: orch 62.5% vs base 39.2% (Δ +23.3pp)
- Cocoa 30d buy: orch 27.3% vs base 38.5% (Δ -11.2pp)
- Cocoa 30d sell: orch 72.7% vs base 35.5% (Δ +37.2pp)
- Cocoa 90d buy: orch 0.0% vs base 41.0% (Δ -41.0pp)
- Cocoa 90d sell: orch 100.0% vs base 34.5% (Δ +65.5pp)
- SP500 30d buy: orch 45.5% vs base 40.6% (Δ +4.8pp)
- SP500 30d sell: orch 9.1% vs base 14.3% (Δ -5.2pp)
- SP500 90d buy: orch 62.5% vs base 50.5% (Δ +12.0pp)
- SP500 90d sell: orch 0.0% vs base 11.0% (Δ -11.0pp)
- EURUSD 30d buy: orch 9.1% vs base 12.7% (Δ -3.6pp)
- EURUSD 30d sell: orch 0.0% vs base 12.2% (Δ -12.2pp)
- EURUSD 90d buy: orch 0.0% vs base 12.4% (Δ -12.4pp)
- EURUSD 90d sell: orch 0.0% vs base 15.4% (Δ -15.4pp)
- USDJPY 30d buy: orch 27.3% vs base 18.4% (Δ +8.8pp)
- USDJPY 30d sell: orch 0.0% vs base 12.0% (Δ -12.0pp)
- USDJPY 90d sell: orch 0.0% vs base 12.0% (Δ -12.0pp)

## Per-driver-bidrag (spike-mode)

Hver spike kopierer YAMLs til temp-dir og setter den navngitte driverens vekt = 0.0, deretter re-kjør orchestrator-replay. ∆ mellom full-sweep og spike isolerer driverens bidrag.

### Driver-bidrag: conab_yoy

| Instrument | Hor | Dir | Full pub-rate | Spike pub-rate | ∆pub-rate | Full avg score | Spike avg score | ∆score |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Corn         |  30d | buy  |  45.5% |  45.5% |  +0.0pp | 6.804 | 6.804 | +0.000 |
| Corn         |  30d | sell | 100.0% | 100.0% |  +0.0pp | 10.718 | 10.118 | +0.600 |
| Corn         |  90d | buy  |  25.0% |  25.0% |  +0.0pp | 6.536 | 6.536 | +0.000 |
| Corn         |  90d | sell | 100.0% | 100.0% |  +0.0pp | 11.082 | 10.482 | +0.600 |
| Soybean      |  30d | buy  |  54.5% |  54.5% |  +0.0pp | 6.313 | 6.313 | +0.000 |
| Soybean      |  30d | sell |  63.6% |  63.6% |  +0.0pp | 11.359 | 9.359 | +2.000 |
| Soybean      |  90d | buy  |  37.5% |  37.5% |  +0.0pp | 5.843 | 5.843 | +0.000 |
| Soybean      |  90d | sell |  50.0% |  50.0% |  +0.0pp | 11.782 | 9.782 | +2.000 |
| Coffee       |  30d | buy  |  45.5% |  45.5% |  +0.0pp | 6.777 | 6.777 | +0.000 |
| Coffee       |  30d | sell |  72.7% |  72.7% |  +0.0pp | 11.114 | 9.114 | +2.000 |
| Coffee       |  90d | buy  | 100.0% | 100.0% |  +0.0pp | 7.323 | 7.323 | +0.000 |
| Coffee       |  90d | sell |  62.5% |  62.5% |  +0.0pp | 10.527 | 8.527 | +2.000 |

_Påvirket instrumenter: Coffee, Corn, Soybean_

### Driver-bidrag: cot_ice_mm_pct

| Instrument | Hor | Dir | Full pub-rate | Spike pub-rate | ∆pub-rate | Full avg score | Spike avg score | ∆score |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Brent        |  30d | buy  |  63.6% |  54.5% |  +9.1pp | 2.165 | 2.072 | +0.094 |
| Brent        |  30d | sell |  72.7% |  72.7% |  +0.0pp | 2.826 | 2.620 | +0.206 |
| Brent        |  90d | buy  |   0.0% |   0.0% |  +0.0pp | 2.123 | 1.915 | +0.208 |
| Brent        |  90d | sell |  12.5% |   0.0% | +12.5pp | 3.600 | 2.908 | +0.692 |

_Påvirket instrumenter: Brent, NaturalGas_

### Driver-bidrag: unica_change

| Instrument | Hor | Dir | Full pub-rate | Spike pub-rate | ∆pub-rate | Full avg score | Spike avg score | ∆score |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Sugar        |  30d | buy  |  81.8% |  81.8% |  +0.0pp | 9.913 | 9.913 | +0.000 |
| Sugar        |  30d | sell |  90.9% |  45.5% | +45.5pp | 7.796 | 5.796 | +2.000 |
| Sugar        |  90d | buy  |  87.5% |  87.5% |  +0.0pp | 10.635 | 10.635 | +0.000 |
| Sugar        |  90d | sell | 100.0% |  25.0% | +75.0pp | 6.965 | 4.965 | +2.000 |

_Påvirket instrumenter: Sugar_

## Konklusjon

44 (instrument, horizon, direction)-kombinasjoner har Δhit_rate over flagging-terskel. Disse skal vurderes i session 117 / ADR-009 cutover-readiness-audit.

**Phase D-status:**

- AsOfDateStore utvidet med 9 nye proxy-getters — kritisk fix.
- Backtest-runner er nå funksjonelt orchestrator-replay-aware
  for hele Phase A-C-driver-suiten.
- Baseline-bekreftelse OK — analog_outcomes-data er uendret.
- Empirisk validering av Phase A-C-driverbidrag utsettes til ≥1 mnd data-akkumulering (session 117 / ADR-009).
