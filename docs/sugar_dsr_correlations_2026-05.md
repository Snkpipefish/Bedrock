# Sugar DSR + familie-korrelasjons-analyse

*Analytiker-peer-review (docs/sugar_analyst_response_2026-05.md) C.2 + C.3. Kjørt lokalt på eksisterende backtest-rådata.*

## 1. Familie-score-korrelasjons-matrise

*Hypotese (C.2): outlook ↔ unica ρ > 0.6 betyr dobbel-vekting.*

| | outlook | yield | positioning | enso | unica | cross | analog |
|---|---:|---:|---:|---:|---:|---:|---:|
| outlook | — | — | — | — | — | — | — |
| yield | — | **1.00** | -0.11 | — | -0.18 | -0.03 | +0.19 |
| positioning | — | -0.11 | **1.00** | — | +0.03 | -0.06 | +0.06 |
| enso | — | — | — | — | — | — | — |
| unica | — | -0.18 | +0.03 | — | **1.00** | -0.11 | -0.02 |
| cross | — | -0.03 | -0.06 | — | -0.11 | **1.00** | -0.01 |
| analog | — | +0.19 | +0.06 | — | -0.02 | -0.01 | **1.00** |

### Funn — overlappende familier (|ρ| > 0.6)

*Ingen familier med |ρ| > 0.6. Analytiker-hypotese om outlook/unica-dobbeltvekting **ikke bekreftet** på A-SELL-data.*

## 2. Deflated Sharpe Ratio (n_trials=24)

*Bonferroni-korreksjon: med α=0.05 og 24 tester må p < 0.0021. DSR + PSR (López de Prado) gir mer presis deflasjon.*

| Horisont | Retning | Grade | n | Hit-rate | Avg ret | SR (annual) | SR* (deflated) | PSR | Status |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 90d | buy | A+ | 92 | 44.6% | +4.69% | +1.41 | +0.21 | 1.000 | ✅ ekte |
| 90d | buy | A | 395 | 34.9% | -0.84% | -0.25 | +0.10 | 0.000 | ❌ støy |
| 90d | buy | B | 3 | 0.0% | -5.09% | — | — | — | insufficient (n<10) |
| 180d | buy | A+ | 89 | 55.1% | +7.37% | +2.22 | +0.21 | 1.000 | ✅ ekte |
| 180d | buy | A | 385 | 33.0% | -0.77% | -0.23 | +0.10 | 0.000 | ❌ støy |
| 180d | buy | B | 3 | 0.0% | -6.92% | — | — | — | insufficient (n<10) |
| 270d | buy | A+ | 87 | 51.7% | +7.52% | +2.26 | +0.21 | 1.000 | ✅ ekte |
| 270d | buy | A | 374 | 35.6% | +0.32% | +0.10 | +0.10 | 0.453 | ❌ støy |
| 270d | buy | B | 3 | 0.0% | -7.12% | — | — | — | insufficient (n<10) |
| 365d | buy | A+ | 87 | 55.2% | +6.14% | +1.85 | +0.21 | 1.000 | ✅ ekte |
| 365d | buy | A | 361 | 38.0% | +2.04% | +0.61 | +0.10 | 1.000 | ✅ ekte |
| 365d | buy | B | 3 | 33.3% | +6.61% | — | — | — | insufficient (n<10) |
| 90d | sell | A | 176 | 31.8% | -3.52% | -1.06 | +0.15 | 0.000 | ❌ støy |
| 90d | sell | B | 285 | 39.6% | +2.06% | +0.62 | +0.12 | 1.000 | ✅ ekte |
| 90d | sell | C | 29 | 34.5% | +4.00% | +1.20 | +0.37 | 1.000 | ✅ ekte |
| 180d | sell | A | 171 | 22.2% | -5.20% | -1.56 | +0.15 | 0.000 | ❌ støy |
| 180d | sell | B | 277 | 43.7% | +3.87% | +1.16 | +0.12 | 1.000 | ✅ ekte |
| 180d | sell | C | 29 | 58.6% | +5.36% | +1.61 | +0.37 | 1.000 | ✅ ekte |
| 270d | sell | A | 171 | 29.2% | -4.31% | -1.30 | +0.15 | 0.000 | ❌ støy |
| 270d | sell | B | 264 | 42.8% | +4.91% | +1.48 | +0.12 | 1.000 | ✅ ekte |
| 270d | sell | C | 29 | 51.7% | +6.71% | +2.02 | +0.37 | 1.000 | ✅ ekte |
| 365d | sell | A | 165 | 33.3% | -1.43% | -0.43 | +0.15 | 0.000 | ❌ støy |
| 365d | sell | B | 257 | 45.1% | +5.48% | +1.65 | +0.12 | 1.000 | ✅ ekte |
| 365d | sell | C | 29 | 51.7% | +4.06% | +1.22 | +0.37 | 1.000 | ✅ ekte |

## 3. A+ BUY 90d — presis DSR (analytiker-flaggship)

- Observasjoner: n=92
- Avg return: +4.69%
- SR (annualized, std≈12%): +1.411
- SR* (deflated, n_trials=24): +0.206
- PSR: 1.000
- **Konklusjon:** ✅ A+ BUY 90d holder DSR-test (PSR > 0.95) — gå i prod.

## 4. SELL grade-progresjon (analytiker non-monotonisitet)

**h=90d:** A (31.8%/-3.5% n=176) → B (39.6%/+2.1% n=285) → C (34.5%/+4.0% n=29)
  → **non-monoton: A -3.5% < C +4.0%** (overshoot/mean-reversion bekreftet)
**h=180d:** A (22.2%/-5.2% n=171) → B (43.7%/+3.9% n=277) → C (58.6%/+5.4% n=29)
  → **non-monoton: A -5.2% < C +5.4%** (overshoot/mean-reversion bekreftet)
**h=270d:** A (29.2%/-4.3% n=171) → B (42.8%/+4.9% n=264) → C (51.7%/+6.7% n=29)
  → **non-monoton: A -4.3% < C +6.7%** (overshoot/mean-reversion bekreftet)
**h=365d:** A (33.3%/-1.4% n=165) → B (45.1%/+5.5% n=257) → C (51.7%/+4.1% n=29)
  → **non-monoton: A -1.4% < C +4.1%** (overshoot/mean-reversion bekreftet)
