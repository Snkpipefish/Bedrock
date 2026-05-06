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
| A+ | 4 | 25.0% | 10.20 | 3 | 33.3% | 10.27 |
| A | 19 | 73.7% | 8.72 | 18 | 72.2% | 8.80 |
| B | 4 | 75.0% | 7.52 | 6 | 66.7% | 7.51 |

## BUY-distribusjon (kontrastsjekk)

### h=180d BUY
| Grade | n (prod) | hr (prod) | avg_score (prod) | n (baseline) | hr (baseline) | avg_score (baseline) |
|---|---:|---:|---:|---:|---:|---:|
| A+ | 3 | 33.3% | 10.17 | 5 | 20.0% | 10.27 |
| A | 18 | 22.2% | 8.66 | 17 | 35.3% | 8.56 |
| B | 6 | 66.7% | 7.84 | 5 | 40.0% | 7.75 |

## Konklusjon

- A+/A SELL-antall (prod): 23
- A+/A SELL-antall (baseline u/India): 21
- Δ (prod − baseline): +2

**RESULTAT: India-drivere ØKTE A SELL-signaler.** Mot-intuitivt — verifiser bull_when-konfig.
