# Backtest Fase 11 — full 12-mnd orchestrator-replay

*Generert 2026-04-25 via `scripts/backtest_fase11_full.py` mot `data/bedrock.db`. Vindu: 2025-04-25 .. 2026-04-25.*

Replay-modus: full Engine-kjøring as-of-date per ref_date. Look-ahead-strict via `AsOfDateStore` — ingen K-NN-leak.

## Hovedfunn

1. **Gold er dominant og monotont scorende.** Alle 45 (h=30d) / 33 (h=90d) signaler er rangert A+/A. På 90d er hit-rate 100% (+22.4% avg) — speiler 2025-26-bullmarkedet. Gold-scoring er konsistent og har god monotonisitet (A+ ≥ A i hit-rate).
2. **Corn-scoring er invertert for buy-direction.** A+ har 7.7% hit-rate / -2.38% avg på h=30d (verre enn C: 42.9% / +1.68%). På h=90d: A+ -5.67% mens C +6.40%. **Dette er en konfig-feil** — Corn-rules vekter sterkt på sma200_align (placeholder fra Fase 5), som gir høy buy-score under bull-trender, men 2025-26 Corn har vært i mean-reversion. Må fikses før Corn live trading. Hører i Fase 6 (agri-drivere) eller 7 (cross-asset).
3. **Publish-floor virker konservativt for Gold, riktig for Corn.** Gold 30d publiserer 35/45 (78%); 90d 33/33 (100%). Corn 30d publiserer 23/45 (51%); 90d 13/33 (39%). Floor er rimelig kalibrert mot at majoriteten av Corn-signaler er C-grade og bør ikke nås.
4. **Forward 90d er sterkere enn 30d for Gold (+22.4% vs +5.2%), motsatt for Corn (+3.2% vs +0.3%).** Gold-momentum er holdbart; Corn-momentum reverter raskt.
5. **Wall-time er akseptabel.** 4 kjøringer × ~50 iterasjoner (step_days=5) = 4.7 min total. Daglig (step_days=1) ville vært ~25 min, OK for batch-rapporter.

**Anbefalt aksjon før Fase 11-tag:** flagg Corn-konfig-feilen som "kjent issue" i STATE før Fase 11 lukkes med rapporten som dokumentasjon (Corn-fix hører i Fase 6/7-scope, ikke Fase 11-blokker).

---

## Gold · h=30d

*Wall-time: 88.0s · 45 signaler · step_days=5, direction=buy*

# Backtest: Gold · h=30d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 45
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 35 av 45

| Metric | Value |
|---|---:|
| Hit-rate | 60.0% (27/45) |
| Avg return | +5.24% |
| Median return | +5.09% |
| Best return | +19.32% |
| Worst return | -9.07% |
| Avg drawdown | -3.10% |
| Worst drawdown | -15.96% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 45 | 60.0% | +5.24% |


---

## Gold · h=90d

*Wall-time: 64.7s · 33 signaler · step_days=5, direction=buy*

# Backtest: Gold · h=90d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 33
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 33 av 33

| Metric | Value |
|---|---:|
| Hit-rate | 100.0% (33/33) |
| Avg return | +22.38% |
| Median return | +22.85% |
| Best return | +37.97% |
| Worst return | +8.22% |
| Avg drawdown | -1.55% |
| Worst drawdown | -5.49% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 29 | 100.0% | +22.46% |
| A | 4 | 100.0% | +21.80% |


---

## Corn · h=30d

*Wall-time: 73.4s · 45 signaler · step_days=5, direction=buy*

# Backtest: Corn · h=30d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 45
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 23 av 45

| Metric | Value |
|---|---:|
| Hit-rate | 35.6% (16/45) |
| Avg return | +0.26% |
| Median return | +1.51% |
| Best return | +13.84% |
| Worst return | -10.95% |
| Avg drawdown | -3.82% |
| Worst drawdown | -11.55% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 13 | 7.7% | -2.38% |
| A | 3 | 66.7% | +2.69% |
| B | 8 | 50.0% | -0.09% |
| C | 21 | 42.9% | +1.68% |


---

## Corn · h=90d

*Wall-time: 54.5s · 33 signaler · step_days=5, direction=buy*

# Backtest: Corn · h=90d

- **Vindu:** 2025-04-25 .. 2026-04-25
- **Antall signaler:** 33
- **Hit-terskel:** ≥ 3.0%
- **Publisert (score ≥ floor):** 13 av 33

| Metric | Value |
|---|---:|
| Hit-rate | 51.5% (17/33) |
| Avg return | +3.19% |
| Median return | +3.15% |
| Best return | +18.65% |
| Worst return | -16.50% |
| Avg drawdown | -6.88% |
| Worst drawdown | -22.40% |

## Per grade

| Grade | n | Hit-rate | Avg return |
|---|---:|---:|---:|
| A+ | 6 | 16.7% | -5.67% |
| A | 1 | 0.0% | -4.56% |
| B | 6 | 50.0% | +2.65% |
| C | 20 | 65.0% | +6.40% |


---

*Total wall-time: 280.6s (4.7 min)*
