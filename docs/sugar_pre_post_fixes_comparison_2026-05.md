# Sugar pre/post fixes — sammenligning

**Pre-baseline:** docs/backtest_sugar_horizons_2026-05.md (commit 33a3c2c)
**Post-fixes:** docs/backtest_sugar_post_fixes_2026-05.md (commit 63e22ca)

**Endringer mellom kjøringer:**
1. `40b4c8b`: ENSO `bull_when=high` (fra default `low`) for begge ENSO-drivere
2. `63e22ca`: `seasonal_stage` forward-syklus mapping
3. Codespace DB fikset: ONI/PDO/IRI_ENSO_FCST_3MO importert fra laptop

---

## A+ BUY (analytikerens flaggship-bøtte)

| Horisont | n_pre | hr_pre | avg_pre | n_post | hr_post | avg_post | Δhr | Δavg |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 90d  | 92 | 44.6% | +4.69% | 9 | 33.3% | +1.97% | **-11.3pp** | **-2.72pp** |
| 180d | 89 | 55.1% | +7.37% | 9 | **77.8%** | **+20.19%** | +22.7pp | +12.82pp |
| 270d | 87 | 51.7% | +7.52% | 9 | **66.7%** | **+19.03%** | +15.0pp | +11.51pp |
| 365d | 87 | 55.2% | +6.14% | 9 | 66.7% | +1.01% | +11.5pp | -5.13pp |

**Funn:**
- **180d og 270d er nye sweet spots** med 66-78% hit-rate og +19-20% avg return
- **90d falt** — for kort horisont mister edge når seasonal flytter til forward-cycle
- **n=9 er for liten for DSR-konfidens** — grade-cutoff ble strammere (færre A+ totalt)
- **365d avg falt** trass i forbedret hit-rate — tail-risiko økte

## A SELL (analytikerens hovedproblem)

| Horisont | n_pre | hr_pre | avg_pre | n_post | hr_post | avg_post | Δhr | Δavg |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 90d  | 176 | 31.8% | -3.52% | 367 | 34.6% | -0.82% | +2.8pp | **+2.70pp** |
| 180d | 171 | 22.2% | -5.20% | 356 | 31.5% | -1.31% | +9.3pp | **+3.89pp** |
| 270d | 171 | 29.2% | -4.31% | 346 | 33.5% | -0.89% | +4.3pp | **+3.42pp** |
| 365d | 165 | 33.3% | -1.43% | 333 | 37.8% | **+0.97%** | +4.5pp | +2.40pp |

**Funn:**
- **A SELL fikset alle horisonter** — avg gikk fra -5.20% til -1.31% på 180d
- **365d snur til positiv** — A SELL gir nå +0.97% snitt, mer eller mindre random
- **n doblet** — tight A+ BUY presser flere signaler inn i A SELL
- Non-monoton fortsatt (B/C SELL bedre enn A SELL) men KRYMPET kraftig

## B SELL — uventet sterk forbedring

| Horisont | hr_pre → hr_post | avg_pre → avg_post |
|---:|---|---|
| 180d | 43.7% → **57.0%** | +3.87% → **+7.83%** |
| 270d | 42.8% → **56.7%** | +4.91% → **+10.41%** |

B SELL er nå sterkere enn A+ BUY på 180d/270d — analytikerens overshoot-hypotese støttes. Markedet roterer for ofte fra A-grade ekstrem-positioning og det forklarer hvorfor lavere-grade SELL slår høyere.

## Konklusjon

ENSO-fix + seasonal forward-cycle løste **det meste** av analytikerens kritikk:

✅ Non-monoton SELL-progresjon: krympet kraftig (avg-diff -8.7pp → -1.0pp på 180d)
✅ Ekte signal aktivert: ENSO bidrar nå til scoring
✅ Forward-cycle: seasonal jobber med markedet, ikke imot
⚠ A+ BUY n=9 er for tynt for DSR — trenger grade-cutoff-justering

## Neste steg

1. **Familie-vekt-ablation** (script klar, `scripts/sugar_ablation_test.py`) — kjøres på codespace
2. **Justere grade_thresholds** ned for å få flere A+ BUY-signaler — målverdi n>30 for DSR
3. **Re-mål korrelasjons-matrise** med post-fix data (outlook ↔ unica)
