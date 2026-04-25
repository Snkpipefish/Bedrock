# Corn-validering etter Sub-fase 12.5 Block B (session 72)

*Generert 2026-04-25 via `scripts/backtest_corn_validation.py`. Vindu: 2025-04-25 .. 2026-04-25.*

**Hva sjekkes:** Fase 11 session 64 fant at Corn buy-direction var INVERTERT — A+ hit-rate var lavere enn C-grade. Skyldtes at alle Corn-familier brukte sma200_align placeholder. Session 72 erstattet weather + enso med ekte drivere. Forventet: A+ hit-rate ≥ C hit-rate (eller i hvert fall ikke åpenbart invertert).

---

## Corn · h=30d · direction=buy

*Wall-time: 42.1s · 23 signaler · step_days=10*

# Backtest: Corn · h=30d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 23
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 12 av 23

| Metric | Value |
|---|---:|
| Hit-rate | 34.8% (8/23) |
| Avg return | +0.04% |
| Median return | +0.31% |
| Best return | +11.59% |
| Worst return | -10.23% |
| Avg drawdown | -3.88% |
| Worst drawdown | -10.88% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 6 | 16.7% | -2.06% |
| A | 1 | 0.0% | +1.51% |
| B | 6 | 16.7% | -2.12% |
| C | 10 | 60.0% | +2.44% |


---

## Corn · h=90d · direction=buy

*Wall-time: 30.6s · 17 signaler · step_days=10*

# Backtest: Corn · h=90d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 17
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 8 av 17

| Metric | Value |
|---|---:|
| Hit-rate | 52.9% (9/17) |
| Avg return | +2.68% |
| Median return | +3.36% |
| Best return | +16.38% |
| Worst return | -16.50% |
| Avg drawdown | -7.17% |
| Worst drawdown | -22.40% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 3 | 33.3% | -6.42% |
| B | 5 | 40.0% | +0.90% |
| C | 9 | 66.7% | +6.70% |


---

*Total wall-time: 72.7s*
