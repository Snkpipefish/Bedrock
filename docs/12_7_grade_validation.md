# Sub-fase 12.7 grade-validering — 12 mnd × 22 instrumenter

Generert: session 135, D3-finale.

- Pre-12.7-anker: `/tmp/baseline_pre_d_spor.json` (= tag `v0.12.7-r4-finish`,
  siste commit i R-spor; R-spor var bit-identisk per ADR-010,
  så denne baseline er numerisk equivalent med pre-R1-tilstand)
- Post-D3-baseline: `/home/pc/bedrock/tests/snapshot/expected/score_baseline.json` (= post-12.7, etter D0..D3)

Per § 19.6 kvalitetskrav. Per session 134-presedens (D2-rapport):
snapshot-baseline-diff fanger samme spørsmål som 12-mnd-backtest-rerun
til en brøkdel av kostnaden (samme DB-state ved hver leveranse).

## 12.7 D-spor leveranser som påvirker baseline

**D0 (smoke-tests):** ingen baseline-effekt.
**D1 (Tier 1):** A2 AGSI (NaturalGas), A3 FAS (Corn/Soybean/Wheat/Cotton —
levert D2 session 133), A4 TFF + C1 (cot_tff for finansielle), B1
yield-diff/credit/NFCI/NetFedLiq (FX/indices/crypto), B3 DXY-bytte.
**D2 (Tier 2):** A5 GLD (Gold), A6 SLV (Silver, proxy), A9 USDM
(Corn/Soybean/Wheat/Cotton), A12 AAII (Nasdaq/SP500), B2 VIX-term
(Nasdaq/SP500), B4 HDD/CDD (NaturalGas), C3 drop shipping (Cotton/Cocoa).
**D3 (Tier 3):** A10 Cecafé (Coffee).

**Droppede:** A1 Baker Hughes, A7 PPLT, A8 NOPA, A11 ICE, A14 Eskom, C2 Platinum.
**Deferred til Plan-S:** B5 calendar spreads (energi+metaller+korn).

## Per-instrument tabell

| Instrument | Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A | Flag |
|---|---|---|---|---|---|---|
| AUDUSD | fx | 0/3/0/3 | 0/2/3/1 | +0 | -1 |  |
| BTC | crypto | 0/0/5/1 | 0/0/6/0 | +0 | +0 |  |
| Brent | energy | 0/3/3/0 | 1/2/2/1 | +1 | -1 | FLAG |
| Cocoa | softs | 0/1/1/0 | 0/0/2/0 | +0 | -1 |  |
| Coffee | softs | 0/1/1/0 | 1/0/1/0 | +1 | -1 | FLAG |
| Copper | metals | 0/1/4/1 | 0/0/6/0 | +0 | -1 |  |
| Corn | grains | 0/1/1/0 | 0/0/2/0 | +0 | -1 |  |
| Cotton | softs | 0/0/2/0 | 0/1/1/0 | +0 | +1 |  |
| CrudeOil | energy | 1/2/3/0 | 1/2/2/1 | +0 | +0 |  |
| ETH | crypto | 0/1/2/3 | 0/2/1/3 | +0 | +1 |  |
| EURUSD | fx | 0/0/6/0 | 0/1/2/3 | +0 | +1 |  |
| GBPUSD | fx | 0/0/6/0 | 0/0/6/0 | +0 | +0 |  |
| Gold | metals | 0/2/4/0 | 0/2/3/1 | +0 | +0 |  |
| Nasdaq | indices | 0/0/5/1 | 0/1/4/1 | +0 | +1 |  |
| NaturalGas | energy | 0/1/2/3 | 0/3/0/3 | +0 | +2 |  |
| Platinum | metals | 0/1/5/0 | 0/1/5/0 | +0 | +0 |  |
| SP500 | indices | 0/1/2/3 | 0/1/5/0 | +0 | +0 |  |
| Silver | metals | 1/2/0/3 | 0/3/0/3 | -1 | +1 | FLAG |
| Soybean | grains | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Sugar | softs | 0/2/0/0 | 0/2/0/0 | +0 | +0 |  |
| USDJPY | fx | 0/0/6/0 | 0/1/5/0 | +0 | +1 |  |
| Wheat | grains | 0/1/0/1 | 0/1/0/1 | +0 | +0 |  |

## Per asset-class

| Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A |
|---|---|---|---|---|
| crypto | 0/1/7/4 | 0/2/7/3 | +0 | +1 |
| energy | 1/6/8/3 | 2/7/4/5 | +1 | +1 |
| fx | 0/3/18/3 | 0/4/16/4 | +0 | +1 |
| grains | 0/3/2/1 | 0/2/3/1 | +0 | -1 |
| indices | 0/1/7/4 | 0/2/9/1 | +0 | +1 |
| metals | 1/6/13/4 | 0/6/14/4 | -1 | +0 |
| softs | 0/4/4/0 | 1/3/4/0 | +1 | -1 |

## Flaggede instrumenter (relative ≥50 % endring i A+-andel)

- **Brent**: A+ 0 → 1 (+inf%)
- **Coffee**: A+ 0 → 1 (+inf%)
- **Silver**: A+ 1 → 0 (-100%)

## Eskalerings-vurdering (per session 135-prompt)

OK: 3 instrumenter flagget (≤5 = under eskalerings-terskel).
Per session 135-prompt: ingen umiddelbar terskel-rekalibrering nødvendig.
Grade-distribusjon innenfor forventet for D-spor med 17 nye drivere på 22 inst.

## Brent A+-stabilisering (oppfølging av D2-rapport)

D2-rapporten flagget Brent A+ 0→2. Status post-D3: A+ 0 → 1.
Brent A+ er stabilt på 1 (D2-funn opprettholdt eller redusert);
ikke videre dyp-analyse nødvendig i 12.7-finale.

## Vurdering

Rapporten er informativ — ikke gating for 12.7-finale-tag. Per § 19.6 sier
eksplisitt: terskler rekalibreres ikke i 12.7, men distribusjons-drift
dokumenteres for senere kalibrering i sub-fase 12.6 (data-driven rebalansering).
