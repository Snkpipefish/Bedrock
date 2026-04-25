# Corn-validering etter Sub-fase 12.5 Block B (session 72)

*Generert 2026-04-25 via `scripts/backtest_corn_validation.py`. Vindu: 2025-04-25 .. 2026-04-25.*

**Hva sjekkes:** Fase 11 session 64 fant at Corn buy-direction var INVERTERT — A+ hit-rate var lavere enn C-grade. Skyldtes at alle Corn-familier brukte sma200_align placeholder. Session 72 erstattet weather + enso med ekte drivere. Forventet: A+ hit-rate ≥ C hit-rate (eller i hvert fall ikke åpenbart invertert).

---

## Corn · h=30d · direction=buy

*Wall-time: 43.6s · 23 signaler · step_days=10*

# Backtest: Corn · h=30d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 23
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 19 av 23

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
| A | 3 | 33.3% | +0.27% |
| B | 17 | 29.4% | -0.37% |
| C | 3 | 66.7% | +2.11% |


---

## Corn · h=90d · direction=buy

*Wall-time: 32.4s · 17 signaler · step_days=10*

# Backtest: Corn · h=90d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 17
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 15 av 17

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
| A | 1 | 0.0% | -8.22% |
| B | 14 | 50.0% | +2.16% |
| C | 2 | 100.0% | +11.71% |


---

*Total wall-time: 76.0s*
