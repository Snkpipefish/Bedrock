# D1 grade-distribusjons-rapport (sub-fase 12.7, session 130)

Pre-D1 baseline: /tmp/baseline_pre_d1.json
Post-D1 baseline: /home/pc/bedrock/tests/snapshot/expected/score_baseline.json

Per § 19.6 kvalitetskrav. Forskyvning vs pre-D1 baseline (commit `b67fc86`,
session 127 close — siste commit før session 128 leverte første D1-commits).

## Per-instrument tabell

| Instrument | Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A | Flag |
|---|---|---|---|---|---|---|
| AUDUSD | fx | 0/0/5/1 | 0/1/4/1 | +0 | +1 |  |
| BTC | crypto | 0/0/4/2 | 0/0/6/0 | +0 | +0 |  |
| Brent | energy | 0/3/3/0 | 0/3/3/0 | +0 | +0 |  |
| Cocoa | softs | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Coffee | softs | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Copper | metals | 0/0/4/2 | 0/0/5/1 | +0 | +0 |  |
| Corn | grains | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Cotton | softs | 0/0/2/0 | 0/0/2/0 | +0 | +0 |  |
| CrudeOil | energy | 0/3/3/0 | 1/2/2/1 | +1 | -1 | 🚩 |
| ETH | crypto | 0/0/5/1 | 0/1/2/3 | +0 | +1 |  |
| EURUSD | fx | 0/1/3/2 | 0/1/2/3 | +0 | +0 |  |
| GBPUSD | fx | 0/0/4/2 | 0/0/6/0 | +0 | +0 |  |
| Gold | metals | 0/2/4/0 | 0/2/3/1 | +0 | +0 |  |
| Nasdaq | indices | 0/0/5/1 | 0/0/5/1 | +0 | +0 |  |
| NaturalGas | energy | 0/0/4/2 | 0/1/2/3 | +0 | +1 |  |
| Platinum | metals | 0/1/5/0 | 0/1/5/0 | +0 | +0 |  |
| SP500 | indices | 0/0/4/2 | 0/0/6/0 | +0 | +0 |  |
| Silver | metals | 0/3/1/2 | 0/3/0/3 | +0 | +0 |  |
| Soybean | grains | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Sugar | softs | 0/2/0/0 | 0/2/0/0 | +0 | +0 |  |
| USDJPY | fx | 0/1/4/1 | 0/2/1/3 | +0 | +1 |  |
| Wheat | grains | 0/1/0/1 | 0/1/0/1 | +0 | +0 |  |

## Per asset-class

| Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A |
|---|---|---|---|---|
| crypto | 0/0/9/3 | 0/1/8/3 | +0 | +1 |
| energy | 0/6/10/2 | 1/6/7/4 | +1 | +0 |
| fx | 0/2/16/6 | 0/4/13/7 | +0 | +2 |
| grains | 0/3/2/1 | 0/3/2/1 | +0 | +0 |
| indices | 0/0/9/3 | 0/0/11/1 | +0 | +0 |
| metals | 0/6/14/4 | 0/6/13/5 | +0 | +0 |
| softs | 0/4/4/0 | 0/4/4/0 | +0 | +0 |

## Flaggede instrumenter (relative ≥50% endring i A+-andel)

- **CrudeOil**: A+ 0 → 1

## Vurdering

Rapporten er informativ — ikke gating for D1-tag. Hvis dramatisk skifte er
flagget, eskaler som åpent spørsmål til neste session for mulig terskel-
rekalibrering. § 19.6 sier eksplisitt: terskler rekalibreres ikke i 12.7,
men distribusjons-drift dokumenteres for senere kalibrering.
