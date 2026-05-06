# Sugar full-historikk-backtest (sub-fase 12.11+)

*Generert 2026-05-05 via `scripts/backtest_sugar_full.py`. Vindu: 2012-05-08 → 2026-05-05 (14 år).*

**Hva validerer:** UNICA-familie med 42 historiske rapporter (backfilled via Wayback Machine), brazil_centro_sul weather-region (184 mnd), og asymmetrisk publish-floor buy=7/sell=5. Forventet: monotonisk grade-progresjon (A+ > A > B > C hit-rate), og BUY-bias ≤ SELL-bias (sukker er strukturelt SELL-favorisert per session 99-backtest).

---

## Sugar · h=30d · direction=buy

*Wall-time: 71.2s · 498 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=30d

- **Vindu:** 2012-05-08 .. 2026-05-05
- **Antall signaler:** 498
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 0 av 498

| Metric | Value |
|---|---:|
| Hit-rate | 31.7% (158/498) |
| Avg return | +0.07% |
| Median return | -0.67% |
| Best return | +38.24% |
| Worst return | -29.89% |
| Avg drawdown | -6.42% |
| Worst drawdown | -32.12% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| C | 498 | 31.7% | +0.07% |


## Sugar · h=90d · direction=buy

*Wall-time: 189.0s · 489 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=90d

- **Vindu:** 2012-05-08 .. 2026-05-05
- **Antall signaler:** 489
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 387 av 489

| Metric | Value |
|---|---:|
| Hit-rate | 36.6% (179/489) |
| Avg return | +0.18% |
| Median return | -2.52% |
| Best return | +65.11% |
| Worst return | -35.80% |
| Avg drawdown | -11.46% |
| Worst drawdown | -38.84% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 92 | 44.6% | +4.69% |
| A | 394 | 35.0% | -0.83% |
| B | 3 | 0.0% | -5.09% |


## Sugar · h=180d · direction=buy

*Wall-time: 0.0s · 0 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=180d

Vindu: 2012-05-08 .. 2026-05-05

**Ingen outcomes funnet.** Sjekk at `analog_outcomes` er backfilt for instrument='Sugar' horizon_days=180.

## Sugar · h=30d · direction=sell

*Wall-time: 71.4s · 498 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=30d

- **Vindu:** 2012-05-08 .. 2026-05-05
- **Antall signaler:** 498
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 0 av 498

| Metric | Value |
|---|---:|
| Hit-rate | 31.7% (158/498) |
| Avg return | +0.07% |
| Median return | -0.67% |
| Best return | +38.24% |
| Worst return | -29.89% |
| Avg drawdown | -6.42% |
| Worst drawdown | -32.12% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| C | 498 | 31.7% | +0.07% |


## Sugar · h=90d · direction=sell

*Wall-time: 186.3s · 489 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=90d

- **Vindu:** 2012-05-08 .. 2026-05-05
- **Antall signaler:** 489
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 102 av 489

| Metric | Value |
|---|---:|
| Hit-rate | 36.6% (179/489) |
| Avg return | +0.18% |
| Median return | -2.52% |
| Best return | +65.11% |
| Worst return | -35.80% |
| Avg drawdown | -11.46% |
| Worst drawdown | -38.84% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A | 175 | 32.0% | -3.51% |
| B | 285 | 39.6% | +2.06% |
| C | 29 | 34.5% | +4.00% |


## Sugar · h=180d · direction=sell

*Wall-time: 0.0s · 0 signaler · step_days=7 · vindu: 2012-05-08 → 2026-05-05*

# Backtest: Sugar · h=180d

Vindu: 2012-05-08 .. 2026-05-05

**Ingen outcomes funnet.** Sjekk at `analog_outcomes` er backfilt for instrument='Sugar' horizon_days=180.

---

*Total wall-time: 8.6 min*
