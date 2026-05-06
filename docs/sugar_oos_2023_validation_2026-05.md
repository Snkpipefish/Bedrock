# Sugar OOS 2023 India-forbud-validering

*Generert 2026-05-06 via `scripts/sugar_oos_2023_validation.py`. Vindu: 2023-01-01 → 2023-09-30 (Q1-Q3 2023, India-eksportforbud).*

**Kontrast:** prod-config (gjeldende `sugar.yaml`) vs. baseline-config der India-drivere er null-vektet:
- `weather_stress.regions.india_maharashtra: 0.30 → 0.0` (BR/Thailand re-vektet 0.79/0.21)
- `usda_psd_yoy(India)`: weight `0.30 → 0.0` (unica re-vektet 0.64/0.36)

**Suksess-kriterium:** India-drivere skal ha SVEKKET A SELL-signaler i 2023 (India-eksportforbud løftet supply-frykt → SELL-bias er feil-spesifisert i den perioden). Forventet: prod har færre A SELL eller lavere avg_score for SELL.

---

## SELL-distribusjon (India-forbud-perioden)

### h=180d SELL
| Grade | n (prod) | hr (prod) | avg_score (prod) | n (baseline) | hr (baseline) | avg_score (baseline) |
|---|---:|---:|---:|---:|---:|---:|
| A+ | 6 | 50.0% | 10.37 | 4 | 25.0% | 10.42 |
| A | 17 | 70.6% | 8.88 | 19 | 73.7% | 8.86 |
| B | 4 | 75.0% | 7.75 | 4 | 75.0% | 7.55 |

## BUY-distribusjon (kontrastsjekk)

### h=180d BUY
| Grade | n (prod) | hr (prod) | avg_score (prod) | n (baseline) | hr (baseline) | avg_score (baseline) |
|---|---:|---:|---:|---:|---:|---:|
| A+ | 2 | 0.0% | 10.06 | 2 | 0.0% | 10.26 |
| A | 11 | 36.4% | 8.87 | 15 | 33.3% | 8.81 |
| B | 14 | 35.7% | 7.71 | 10 | 40.0% | 7.70 |

## Konklusjon

- A+/A SELL-antall (prod): 23
- A+/A SELL-antall (baseline u/India): 23
- Δ (prod − baseline): +0

**RESULTAT: India-drivere endret ikke A SELL-antall.** Marginalt — sjekk avg_score endringer.
