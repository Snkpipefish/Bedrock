# Backtest-validering: 17 whitelist-instrumenter

Dato: 2026-04-26 (session 99). Kilde: `analog_outcomes`-tabellen
(2010-01-04 .. 2026-03-12 for 30d, .. 2025-12-12 for 90d).

Hit-rate måler andel av historiske dager der forward-return krysser
absolutt-tersklen (BUY: ≥ +X%; SELL: ≤ -X%). Threshold matcher
`analog`-driverens `outcome_threshold_pct`-default.

| Horisont | Threshold |
|---|---|
| 30d | ±3.0% |
| 90d | ±5.0% |

## Horisont 30d (terskel ±3.0%)

| Instrument | n | BUY hit-rate | SELL hit-rate | Avg return | Stdev | Avg DD | Worst DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD       |  4217 |  12.7% |  12.2% | -0.10% |  2.75% | -1.93% | -11.08% |
| USDJPY       |  4217 |  18.4% |  12.0% | +0.45% |  3.14% | -1.86% | -10.45% |
| GBPUSD       |  4217 |  11.5% |  13.3% | -0.09% |  2.76% | -2.02% | -12.67% |
| AUDUSD       |  4216 |  16.7% |  18.8% | -0.12% |  3.34% | -2.46% | -14.72% |
| Gold         |  4071 |  34.5% |  20.7% | +1.21% |  5.35% | -3.07% | -17.36% |
| Silver       |  4071 |  37.9% |  35.1% | +1.68% | 11.19% | -6.02% | -37.80% |
| CrudeOil     |  4071 |  41.4% |  36.3% | +1.18% | 15.73% | -9.42% | -305.97% |
| Brent        |  4041 |  40.5% |  34.6% | +1.03% | 12.70% | -7.23% | -61.66% |
| SP500        |  4073 |  40.6% |  14.3% | +1.47% |  4.92% | -3.17% | -34.45% |
| Nasdaq       |  4073 |  47.3% |  17.0% | +2.13% |  5.98% | -3.74% | -28.24% |
| Corn         |  4069 |  36.6% |  32.6% | +0.58% |  9.42% | -5.67% | -36.48% |
| Wheat        |  4071 |  34.4% |  37.3% | +0.63% | 10.44% | -6.41% | -33.88% |
| Soybean      |  4071 |  33.1% |  30.4% | +0.41% |  7.22% | -4.54% | -28.79% |
| Coffee       |  4071 |  38.8% |  38.3% | +1.20% | 11.48% | -6.76% | -30.80% |
| Cotton       |  4072 |  36.3% |  30.1% | +0.49% |  9.71% | -5.76% | -41.24% |
| Sugar        |  4072 |  33.8% |  39.0% | +0.11% | 10.93% | -6.91% | -39.81% |
| Cocoa        |  4071 |  38.5% |  35.5% | +0.74% | 12.42% | -6.95% | -51.16% |


## Horisont 90d (terskel ±5.0%)

| Instrument | n | BUY hit-rate | SELL hit-rate | Avg return | Stdev | Avg DD | Worst DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD       |  4157 |  12.4% |  15.4% | -0.22% |  4.86% | -3.61% | -16.45% |
| USDJPY       |  4157 |  22.7% |  12.0% | +1.35% |  5.97% | -3.22% | -14.75% |
| GBPUSD       |  4157 |  12.4% |  17.1% | -0.20% |  4.60% | -3.80% | -17.67% |
| AUDUSD       |  4156 |  13.6% |  18.1% | -0.44% |  5.42% | -4.69% | -18.19% |
| Gold         |  4011 |  44.0% |  19.1% | +3.72% |  9.48% | -4.97% | -25.00% |
| Silver       |  4011 |  39.1% |  29.3% | +5.30% | 21.31% | -9.89% | -37.80% |
| CrudeOil     |  4011 |  41.7% |  36.4% | +2.36% | 23.71% | -17.25% | -305.97% |
| Brent        |  3981 |  38.9% |  36.2% | +2.19% | 21.12% | -13.31% | -71.95% |
| SP500        |  4013 |  50.5% |  11.0% | +4.39% |  7.54% | -5.31% | -34.45% |
| Nasdaq       |  4013 |  59.7% |  11.5% | +6.41% |  9.51% | -5.90% | -28.24% |
| Corn         |  4009 |  35.1% |  37.0% | +1.84% | 17.41% | -10.21% | -41.33% |
| Wheat        |  4011 |  31.8% |  35.2% | +1.36% | 15.30% | -10.67% | -45.50% |
| Soybean      |  4011 |  31.4% |  31.8% | +1.23% | 13.61% | -7.98% | -40.07% |
| Coffee       |  4011 |  40.1% |  39.2% | +3.83% | 20.51% | -11.31% | -39.12% |
| Cotton       |  4012 |  35.9% |  34.5% | +1.32% | 18.71% | -10.24% | -53.51% |
| Sugar        |  4012 |  34.9% |  45.0% | +0.84% | 19.00% | -12.30% | -54.28% |
| Cocoa        |  4011 |  41.0% |  34.5% | +2.63% | 22.63% | -11.10% | -57.61% |


## Direksjonell asymmetri

Forskjellen mellom BUY og SELL hit-rate forteller om instrumentet er strukturelt biased opp eller ned i hold-perioden. Hvis BUY-hit-rate er høyere enn SELL-hit-rate, har instrumentet hatt netto upside (passende for BUY-først-strategi). Symmetri er nær 50/50.

| Instrument | 30d BUY-SELL | 90d BUY-SELL | Tolkning |
|---|---:|---:|---|
| EURUSD       |  +0.5pp |  -3.0pp | symmetrisk |
| USDJPY       |  +6.4pp | +10.7pp | **BUY-bias** |
| GBPUSD       |  -1.8pp |  -4.7pp | symmetrisk |
| AUDUSD       |  -2.1pp |  -4.5pp | symmetrisk |
| Gold         | +13.8pp | +24.9pp | **BUY-bias** |
| Silver       |  +2.8pp |  +9.8pp | blandet |
| CrudeOil     |  +5.1pp |  +5.3pp | **BUY-bias** |
| Brent        |  +5.9pp |  +2.7pp | blandet |
| SP500        | +26.3pp | +39.5pp | **BUY-bias** |
| Nasdaq       | +30.2pp | +48.2pp | **BUY-bias** |
| Corn         |  +4.0pp |  -1.9pp | symmetrisk |
| Wheat        |  -2.9pp |  -3.4pp | symmetrisk |
| Soybean      |  +2.8pp |  -0.3pp | symmetrisk |
| Coffee       |  +0.5pp |  +0.9pp | symmetrisk |
| Cotton       |  +6.2pp |  +1.4pp | blandet |
| Sugar        |  -5.3pp | -10.1pp | **SELL-bias** |
| Cocoa        |  +3.0pp |  +6.5pp | blandet |

## Live signals-distribusjon (fra signals.json + signals_bot.json)

| Instrument | Total | Published | Grades | Bot-published |
|---|---:|---:|---|---|
| EURUSD       | 6 | 4 | A:2, B:3, C:1 | 4 |
| USDJPY       | 6 | 0 | A:1, B:3, C:2 | 0 |
| GBPUSD       | 6 | 0 | A:1, B:5 | 0 |
| AUDUSD       | 6 | 2 | A:3, B:2, C:1 | 2 |
| Gold         | 6 | 4 | A:2, B:4 | 4 |
| Silver       | 6 | 5 | A:2, B:4 | 5 |
| CrudeOil     | 6 | 3 | A:3, B:3 | 0 |
| Brent        | 6 | 3 | A:3, B:3 | 0 |
| SP500        | 6 | 1 | A:2, A+:1, B:2, C:1 | 0 |
| Nasdaq       | 6 | 0 | A:3, B:3 | 0 |
| Corn         | 6 | 6 | A:3, B:3 | 6 |
| Wheat        | 6 | 4 | A:3, B:3 | 4 |
| Soybean      | 6 | 6 | A:3, B:3 | 6 |
| Coffee       | 6 | 2 | A+:3, C:3 | 2 |
| Cotton       | 6 | 6 | A:3, B:3 | 6 |
| Sugar        | 6 | 5 | A:3, B:3 | 5 |
| Cocoa        | 6 | 3 | A:3, C:3 | 3 |

## Sammendrag

**Cutover-evaluering (PLAN § 12.3):**

**Flagg for review før cutover:**

- CrudeOil: høy stdev (15.7%) — exotisk
- SP500: sterk asymmetri (BUY 40.6% vs SELL 14.3%) — mulig structural bias
- Nasdaq: sterk asymmetri (BUY 47.3% vs SELL 17.0%) — mulig structural bias

**Anbefaling:** instrumenter med sterk strukturell bias bør vurderes for direction-spesifikk publish-floor-justering, eller fjernes fra whitelist hvis bias er pga thin data.
