# Sugar driver-attribution: A-SELL underperformance

*Generert 2026-05-05 via `scripts/sugar_attribution_a_sell.py`. Vindu: 2012-05-08 → 2025-08-07. n=477 SELL-entries på h=180d.*

## 1. Per grade-bøtte

| Grade | n | Hit-rate | Avg fwd_return | Avg score |
|---|---:|---:|---:|---:|
| A | 171 | 22.2% | -5.20% | 8.77 |
| B | 277 | 43.7% | +3.87% | 6.99 |
| C | 29 | 58.6% | +5.36% | 5.64 |

## 2. Median familie-score per grade-bøtte

| Grade | n | outlook | yield | positioning | enso | unica | cross | analog |
|---|---|---|---|---|---|---|---|---|
| A | 171 | 0.00 | 0.59 | 0.53 | 1.00 | 0.50 | 0.64 | 1.00 |
| B | 277 | 0.00 | 0.53 | 0.49 | 1.00 | 0.50 | 0.59 | 0.00 |
| C | 29 | 0.00 | 0.47 | 0.30 | 1.00 | 0.21 | 0.56 | 0.00 |

## 3. Korrelasjon familie-score vs forward-return (alle SELL)

*Negativ korrelasjon = familien fungerer som SELL-signal (høy score → fallende pris). Positiv korrelasjon = familien **virker mot retningen** og kan være anti-driver.*

| Familie | Pearson ρ | n | Tolkning |
|---|---:|---:|---|
| outlook | +nan | 477 | **ANTI-DRIVER** (overshoot/mean-reversion) |
| yield | +0.016 | 477 | ingen relasjon |
| positioning | -0.171 | 477 | OK (sell-signal fungerer) |
| enso | +nan | 477 | **ANTI-DRIVER** (overshoot/mean-reversion) |
| unica | -0.268 | 477 | OK (sell-signal fungerer) |
| cross | -0.050 | 477 | OK (sell-signal fungerer) |
| analog | -0.092 | 477 | OK (sell-signal fungerer) |

## 4. A-grade SELL: hit vs miss familie-snitt

*Hvilke familier scoret høyere når A-SELL bommet? Disse drar opp scoren feilaktig.*

| Familie | Avg score (HIT) | Avg score (MISS) | Diff (M-H) |
|---|---:|---:|---:|
| outlook | 0.000 | 0.000 | +0.000 |
| yield | 0.572 | 0.574 | +0.002 |
| positioning | 0.435 | 0.520 | +0.086 **⚠** |
| enso | 1.000 | 1.000 | +0.000 |
| unica | 0.423 | 0.467 | +0.044 |
| cross | 0.622 | 0.661 | +0.039 |
| analog | 0.934 | 0.906 | -0.028 |
