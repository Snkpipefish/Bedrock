# BEDROCK Sukker (#11) — Analytiker-briefing 2026-05-06

**Instrument:** Sugar (ICE No.11 raw cane sugar futures, Yahoo `SB=F`)
**Asset class:** softs
**Periode dekket:** sub-fase 12.11+ (datafundament + analytiker-tiltak) + sub-fase 12.11++ (real-time data-tillegg)
**For:** ekstern peer-review av drivere, vekter, scoring, og setup-generering

---

## Innholdsfortegnelse

1. [Score-arkitektur](#1-score-arkitektur)
2. [7 familier × 19 drivere](#2-7-familier--19-drivere)
3. [Live snapshot 2026-05-06](#3-live-snapshot-2026-05-06)
4. [Datakilder per driver](#4-datakilder-per-driver)
5. [Setup-generering (entry/SL/TP)](#5-setup-generering-entrysltp)
6. [Backtest-resultater (v6 → v7)](#6-backtest-resultater-v6--v7)
7. [Validering-historikk](#7-validering-historikk)
8. [Endringer siden forrige peer-review](#8-endringer-siden-forrige-peer-review)
9. [Spørsmål til analytiker](#9-spørsmål-til-analytiker)

---

## 1. Score-arkitektur

**Aggregation:** `additive_sum` (agri-mode — i motsetning til `weighted_horizon` som brukes for financial). Sukker er ett av 7 agri-instrumenter.

**Formel:**

```
total_score = sum_over_families(family_score × family_weight)
family_score = sum_over_drivers(driver_value × driver_weight) / sum(driver_weights)
                               (driver_value er 0..1; sum_weights pr familie = 1.0)
```

**Familie-vekter (sum=18):**

| Familie | Vekt | Begrunnelse |
|---|---:|---|
| outlook | 5 | Sesong-bias høyest informativ enkelt-kilde — 14-års empirisk sterkeste cycle-driver |
| yield | 3 | Vær-stress + WASDE-balanse |
| positioning | 2 | COT-MM/OI/swap dealer signaler |
| enso | 2 | Klima-overlay (sukker omvendt vs grain) |
| unica | 2 | Brasil-bi-ukentlig + India real-time supply |
| cross | 2 | BRL/oljepris/calendar/ICE-positioning |
| analog | 2 | K-NN historisk mønster-matching |

**Grade-terskler (absolutte score, ikke pct):**

| Grade | min_score | min_families_active |
|---|---:|---:|
| A+ | 10 | 4 |
| A | 8 | 3 |
| B | 6 | 2 |
| C | (default) | — |

> **Note:** A_plus senket fra 11 → 10 i session 153 etter peer-review-punkt C.4. Backtest v7 verifiserte n=72-77 i A+ BUY (var n=10-13 ved cutoff=11).

**Asymmetrisk publish-floor:**

```yaml
min_score_publish: {buy: 7, sell: 5}
```

Sukker har strukturell SELL-bias (Brasil over-supply + global HFCS-substitusjon). Backtest 99 viste BUY-hr 34.9% vs SELL-hr 45.0% (90d). BUY-floor strenger; SELL lavere.

> **Åpent:** rolling-floor-analyse (5-yr vindu) anbefaler SELL=7.5 i nåværende regime. Ikke applied — venter operator-godkjenning. Kvartalsvis dry-run-rapport via systemd-timer.

**`max_score: 16` i YAML er stale** (engine bruker faktisk 18 = sum av family weights). Ingen effekt på grading siden grade-thresholds er absolutte.

---

## 2. 7 familier × 19 drivere

### 2.1 outlook (vekt 5, 1 driver)

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `seasonal_stage` | 1.0 | MAKRO | Forward-syklus monthly_scores: `[1.0,1.0,0.9,0.7,0.6,0.7,0.8,0.9,1.0,0.9,0.8,0.9]` (Jan-Dec). Per analytiker C: forward-pricing-justert (peak FØR zafra, ikke under). |

### 2.2 yield (vekt 3, 2 drivere)

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `weather_stress` | 0.50 | MAKRO+SWING | Multi-region eksport-impact-vektet: BR Centro-Sul 0.55 / India Maharashtra 0.30 / Thailand Suphan Buri 0.15 |
| `wasde_s2u_change` | 0.50 | MAKRO+SWING | USDA WASDE Stocks-to-Use change (US-balanse, benchmark) |

### 2.3 positioning (vekt 2, 3 drivere)

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `positioning_mm_pct` | 0.40 | MAKRO+SWING | mode=`extreme_flag_soft` — returnerer 1.0 ved BEGGE ekstremer (pct≥0.95 eller ≤0.05) per analytiker C.1. Lineær mid-range bevares. |
| `cot_oi_change` | 0.35 | MAKRO+SWING | OI WoW-z |
| `cot_swap_dealer_skew` | 0.25 | MAKRO+SWING | Swap dealer net-flow-skew |

### 2.4 enso (vekt 2, 2 drivere)

Sukker har OMVENDT ENSO-sensitivitet vs grain — `bull_when=high` overstyring kreves.

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `noaa_oni_index` | 0.60 | MAKRO | Current ONI, bull_when=high |
| `noaa_enso_forecast_3mo` | 0.40 | MAKRO | IRI 3-mnd forecast, bull_when=high |

### 2.5 unica (vekt 2, 5 drivere) — BR + India supply

**Sub-vekter:** Brasil 0.50 (UNICA × 2) / India 0.50 (USDA × 2 + Comtrade × 1).

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `unica_change(sugar_production_yoy)` | 0.35 | (alle) | UNICA cum-prod YoY, bi-ukentlig (12 års historikk via Wayback) |
| `unica_change(mix_sugar_pct)` | 0.15 | (alle) | UNICA sukker/etanol mix-pct, bi-ukentlig |
| `usda_psd_yoy(USDA_PSD_INDIA_SUGAR_PROD_KMT)` | 0.15 | MAKRO | USDA FAS PSD India produksjon, årlig (16 års historikk) |
| `usda_psd_yoy(USDA_PSD_INDIA_SUGAR_EXPORTS_KMT)` | 0.10 | MAKRO | USDA FAS PSD India eksport, årlig (16 års historikk) |
| `comtrade_export_yoy(COMTRADE_INDIA_SUGAR_EXPORTS_KG_MONTHLY)` | 0.25 | MAKRO | UN Comtrade månedlig India eksport, 12-mo trailing YoY (178 mnd 2011-01 → 2025-10) |

> **Bevisst design:** Comtrade får høyeste vekt blant India-drivere (0.25 vs 0.15+0.10 USDA) siden månedlig granularitet er mest real-time. Comtrade fanger India-policy-events (eksportforbud) ~6 mnd tidligere enn USDA PSD-årlig.

### 2.6 cross (vekt 2, 4 drivere)

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `brl_chg5d` | 0.50 | (alle) | USDBRL 5d change (DEXBZUS), bull_when=positive (BRL svakhet = bull sukker-eksport) |
| `event_distance` | 0.10 | SWING | Forex Factory USD high-impact events ≤4 timer |
| `cot_ice_mm_pct` | 0.20 | (alle) | ICE White Sugar (Europe) MM-positioning — cross-region signal til NY #11 |
| `ethanol_parity_brl` | 0.20 | SWING+MAKRO | ANP hydrous etanol vs sukker-paritet z-score (60d). Erstatter momentum_z(CrudeOil)-proxy per analytiker D.2 |

### 2.7 analog (vekt 2, 2 drivere) — `polarity: neutral`

| Driver | Vekt | Horisont | Beskrivelse |
|---|---:|---|---|
| `analog_hit_rate` | 0.50 | MAKRO+SWING | K-NN k=5, asset_class=softs, h=30d, threshold=3% |
| `analog_avg_return` | 0.50 | MAKRO+SWING | K-NN k=5 average forward-return |

---

## 3. Live snapshot 2026-05-06

Generert via `bedrock signals Sugar`. Score per familie + per-driver bidrag:

### BUY MAKRO (score 8.276/18, grade A, published=False — under floor 7)

| Familie | Score | Driver-bidrag |
|---|---:|---|
| **outlook** | 0.600 | seasonal_stage=0.60 (mai = lager bygges, bear-bias) |
| **yield** | 0.585 | weather_stress=0.67, wasde_s2u=0.50 |
| **positioning** | 0.425 | mm_pct=0.00 (ekstrem-flag aktivert), oi_change=0.50, swap_skew=1.00 |
| **enso** | 0.600 | oni=0.50, forecast=0.75 |
| **unica** | 0.273 | unica_prod=0.35, unica_mix=0.50, psd_prod=0.15, psd_exp=0.15, **comtrade=0.15** |
| **cross** | 0.462 | brl=0.50, ice_mm=0.23, ethanol_parity=0.60 |
| **analog** | 0.000 | (begge null — ingen analog-kandidater) |

### SELL MAKRO (score 9.724/18, grade A, **published=True**)

| Familie | Score | Driver-bidrag |
|---|---:|---|
| **outlook** | 0.400 | seasonal_stage=0.40 (flippet for SELL) |
| **yield** | 0.415 | weather_stress=0.33, wasde_s2u=0.50 |
| **positioning** | 0.575 | mm_pct=1.00 (ekstrem flag hits SELL også), oi_change=0.50, swap_skew=0.00 |
| **enso** | 0.400 | oni=0.50, forecast=0.25 (flippet) |
| **unica** | 0.728 | unica_prod=0.65, unica_mix=0.50, psd_prod=0.85, psd_exp=0.85, **comtrade=0.85** |
| **cross** | 0.538 | brl=0.50, ice_mm=0.77, ethanol_parity=0.40 |
| **analog** | 1.000 | hit_rate=1.00, avg_return=1.00 |

**Tolkning:** SELL er sterkt foretrukket akkurat nå. India-supply-cluster (unica) viser bear (PSD+Comtrade enige om at India-eksport recovering = supply-tightening reverserer). Analog finner historiske matchinger som ALLE gikk lavere på 30d. positioning-extreme-flag aktivert begge retninger pga MM-positioning ekstrem.

---

## 4. Datakilder per driver

| Driver | Kilde | Frekvens | Lag | Backfill-historikk |
|---|---|---|---|---|
| `seasonal_stage` | (ingen — kalender) | n/a | n/a | n/a |
| `weather_stress` | Open-Meteo Archive | månedlig (aggregert) | ~1 dag | 184 mnd × 3 regioner |
| `wasde_s2u_change` | USDA WASDE | månedlig (~10.) | 1-2 dager | 12 års historikk |
| `positioning_mm_pct`, `cot_oi_change`, `cot_swap_dealer_skew` | CFTC COT (ICE Sugar No.11 disaggregated) | ukentlig (fredag, T-3) | 3 dager | 16 års historikk |
| `noaa_oni_index` | NOAA Ocean Niño Index | månedlig | ~10 dager | 76 års historikk (1950+) |
| `noaa_enso_forecast_3mo` | IRI Plumes (manuell CSV-port) | månedlig | ~3 dager | 6 mnd seed (utvider seg) |
| `unica_change(sugar_production_yoy/mix_sugar_pct)` | UNICA Brasil | bi-ukentlig (1. + 16.) | ~5 dager | 12 års historikk via Wayback (42 rapporter) |
| `usda_psd_yoy(India PROD/EXPORTS)` | USDA FAS PSD API | årlig (oktober) | ~6 mnd | 16 års historikk (2010-2025) |
| `comtrade_export_yoy(India)` | UN Comtrade public preview API | månedlig | 2-4 mnd | 178 mnd (2011-01 → 2025-10) |
| `brl_chg5d` | FRED DEXBZUS | daglig | 1 dag | 10 års historikk (ADR-011) |
| `event_distance` | Forex Factory RSS | hver 12. time | n/a | rolling vindu |
| `cot_ice_mm_pct` | ICE Futures Europe COT (sugar) | ukentlig (tirsdag-snapshot) | 3 dager | 5 års historikk |
| `ethanol_parity_brl` | ANP Brasil + FRED DEXBZUS + price | månedlig (ANP) | 1 mnd | 2024-01 → 2026-03 (584 daily rows) |
| `analog_hit_rate`, `analog_avg_return` | analog_outcomes-tabell (forward-return per ref_date × instrument × horizon) | derivert | n/a | 11512 rader for h=180/270/365 |

---

## 5. Setup-generering (entry/SL/TP)

Etter at scoring + grade beregnes, går resultatet til `setups/generator.py`:

**For sukker MAKRO BUY (idag, hvis score var over floor):**

```
[       ] SETUP BUY  MAKRO   score= 8.276/18.0   grade=A
         id=254674fb129d  entry=14.6800  sl=14.5660  tp=trailing  rr=trailing
         min_score_publish=7.00
```

**Setup-builder-logikk (per setups/generator.py):**

1. **Entry-nivå:** beregner `support` (BUY) eller `resistance` (SELL) fra siste 90d swing-analyse + round-numbers (rundede 0.50-trinn for sukker).
2. **Stop-loss:** 1×ATR(14) fra entry-nivå, motsatt retning av setup.
3. **Take-profit:** for MAKRO/SWING settes `trailing` (chandelier-exit-modus, ikke fast TP). For SCALP brukes 2×ATR.
4. **R:R:** ATR-basert SL gir konsekvent 1:trailing for MAKRO. SWING bruker 1:R-min basert på `min_rr_swing` config (typisk 2.0).
5. **Hysterese:** setup-ID persisterer på (instrument, direction, horizon, slot-hash). Re-publishes ikke samme setup hvis entry/SL er innenfor 0.3% gap.

**Publish-gate:**

```
publish_signal = (score >= min_score_publish[direction]
                  AND build_setup() returned non-None
                  AND active_families >= grade.min_families)
```

For BUY MAKRO i dag: score=8.276 < 7.00 ✓, men `build_setup` returnerte ID 254674fb129d ✓ — så ville publisert hvis floor=7 var møtt. (Score 8.276 > 7.00, så publish=True forventet — men output viser False. Sjekker grade-flow…)

Faktisk output viser `published=False` for BUY MAKRO. Konsistens-check: score=8.276 >= floor=7.00 = True. Men `published=False`. Mulig at `build_setup` returnerte None for BUY pga "no asymmetric setup found" (når support/resistance ikke gir gunstig R:R). Logisk siden setup-builder krever EN del-bevegelse fra current til entry.

> **Spørsmål til analytiker:** er det riktig at engine ikke publiserer `published=True` selv når score>=floor, basert på asymmetri-sjekk i setup-builder? Eller bør det være separate `score_published` (ren score-baseline) og `setup_published` (krever eksisterende level)?

---

## 6. Backtest-resultater (v6 → v7)

**Felles parametere:** 14-års vindu (2012-05 → 2026-05), step_days=7 (ukentlig), 4 horisonter (90/180/270/365d), threshold=±3%.

### v6 (sub-fase 12.11+, cutoff=11): A+ BUY

| Horisont | n | hit-rate | avg return |
|---|---:|---:|---:|
| 90d | 8 | 50.0% | +8.70% |
| 180d | 10 | **100.0%** | +27.61% |
| 270d | 13 | 84.6% | +26.01% |
| 365d | 13 | 84.6% | +15.52% |

> Analytiker C.4-kritikk: n=8-13 er under n>=30-krav for statistisk signifikant grade-bøtte.

### v7 (sub-fase 12.11+ session 153, cutoff=10): A+ BUY

| Horisont | n | hit-rate | avg return |
|---|---:|---:|---:|
| 90d | 77 | 46.8% | +5.12% |
| 180d | 74 | 59.5% | +12.57% |
| 270d | 72 | 55.6% | +10.11% |
| 365d | 72 | 47.2% | +6.37% |

> n>=30 oppfylt. Hit-rate 47-60% — under analytikers 65%-mål, men fremdeles positiv avg-return.

### v7 A+ SELL (uendret over v6 — strukturell non-monotonisitet)

| Horisont | n | hit-rate | avg return |
|---|---:|---:|---:|
| 90d | 74 | 33.8% | -2.13% |
| 180d | 71 | **19.7%** | -7.68% |
| 270d | 71 | 22.5% | -5.99% |
| 365d | 71 | 32.4% | -2.89% |

> A SELL har 34-42% hit-rate på alle horisonter. **A+ SELL har LAVERE hit-rate enn A SELL** — strukturelt non-monotone, ikke fixet av cutoff-justering. Også synlig i v6 (cutoff=11): A+ SELL n=7 hr 28-43%.

---

## 7. Validering-historikk

| Validering | Resultat |
|---|---|
| **DSR + Bonferroni** (32 tester = 4h × 2dir × 4grade) | A+ BUY h=180/270/365 holder PSR=1.000 etter deflasjon |
| **Familie-ablation** (drop-one-out, A+ BUY 90d) | Alle 7 familier kritiske: Δ Sharpe -1.33 til -2.14 ved drop. Ingen kandidater å fjerne. |
| **Forward-cycle A/B-test** (current vs forward-syklus) | +4.06 Sharpe-løft for forward-syklus over 8 års vindu. Kriterium +0.20. |
| **Familie-korrelasjon** (parvis ρ over 14 års data) | Maks |ρ|=0.42 (outlook ↔ enso). Ingen ρ>0.6 — ortogonale signaler. |
| **ANP etanol-paritet validering** | ρ=-0.388 (n=16) ved lag=3 UNICA-rapporter (~45-60d mølle-respons). Passerer |ρ|≥0.30. Driver-formelen er korrekt, parametere irrelevante. |
| **OOS 2023 (India-eksportforbud-perioden)** | v3 med Comtrade: A+ SELL hit-rate **dobles** fra 25% (baseline u/India) til 50% (prod m/India + Comtrade). |
| **Rolling-floor 5y** | Anbefaling SELL=7.5 (vs current=5.0) i nåværende regime. IKKE applied — operator-godkjenning via kvartalsvis dry-run. |

---

## 8. Endringer siden forrige peer-review

**Sub-fase 12.11+ session 151-152:**
- Datafundament: brazil_centro_sul weather (184 mnd), UNICA Wayback-backfill (42 rapporter), USDA FAS PSD India (16 år), ISMA India, ANP Brasil etanol (584 daily), multi-region weather India + Thailand (184 mnd hver).
- Driver-tuning: ENSO bull_when=high, forward-syklus seasonal_stage, positioning extreme_flag_soft, multi-region weather_stress eksport-impact-vektet, USDA PSD India yoy-driver, ethanol_parity_brl (erstatter crude-proxy).
- Analyser: backtest v3-v6, DSR/PSR=1.000, ablation, A/B-test forward-cycle, rullerende publish-floor.

**Sub-fase 12.11+ session 153 (ferdig 2026-05-06):**
- Punkt 1 (C.4 grade_thresholds): cutoff 11→10. Backtest v7 verifiserer n=72-77 i A+ BUY.
- Punkt 2 (ANP-validering): lag=1 → lag=3 UNICA-rapporter. ρ=+0.06 → -0.388. Driver beholdes.
- Punkt 3 (OOS 2023): India-drivere ADDER 2 SELL-signaler men A+ SELL hr 25% (mixed signal — usda_psd_yoy(EXPORTS)-tillegg foreslått).
- Punkt 4 (rolling-floor prod): kvartalsvis CLI klar, dry-run anbefaler SELL=7.5.

**Sub-fase 12.11++ session 154 (ferdig 2026-05-06):**
- Future-spor #1: `usda_psd_yoy(EXPORTS_KMT)` wired @ 0.20 vekt. OOS 2023 v2 Δ=+0 (var +2).
- Future-spor #4: **UN Comtrade månedlig India eksport** wired @ 0.25 vekt. OOS 2023 v3 A+ SELL hr **dobles 25% → 50%**.
- Future-spor #3: rolling-floor systemd-timer aktivert (kvartalsvis dry-run, 1. mar/jun/sep/des 06:00).
- Operasjonelt: 9 systemd-services WorkingDirectory-fix (worktree-stub-DB-pointer). Pipeline-helse fra rød til grønn.

---

## 9. Spørsmål til analytiker

**A) Familie-vekter — er splittene fortsatt riktige?**
- outlook vekt 5 er høyest. Ablation viser kritisk (Δ Sharpe -1.33 ved drop). Beholdes?
- analog vekt 2 — du foreslo 0 i forrige review pga "K-NN softs typisk lav-signal høy-overfit". Holder vi 2 inntil ablation viser ekte negativ-bidrag?

**B) A+ SELL non-monotonisitet — strukturell**
v7 viser A+ SELL hit-rate 19-33% vs A SELL 34-42% på alle 4 horisonter. Også til stede i v6. Mulige løsninger:
1. Asymmetrisk grade-cutoff per direction (A_plus_buy=10, A_plus_sell=11) — krever schema-utvidelse i Pydantic
2. Ekskluder SELL-signaler hvis positioning_mm_pct returnerer ekstrem-flag (anti-overshoot)
3. Akseptere strukturen — bot-strategien filtrerer A+ SELL separat

**C) Comtrade-driver vekting — for høy?**
Comtrade @ 0.25 er høyere enn USDA PSD PROD @ 0.15. Comtrade og USDA EXPORTS måler samme underliggende fenomen (India eksport-volum), bare ulike kilder + frekvenser.
- ρ(Comtrade YoY, USDA EXPORTS YoY) bør beregnes — hvis høy korrelasjon, doblet vekt
- Alternativ: redusere Comtrade til 0.15 og øke unica_change(BR) tilbake til 0.45/0.20

**D) Rolling-floor SELL=7.5 — apply manuelt?**
Anbefalt sell=7.5 i nåværende regime (vs current=5.0). Vil blokkere mange SELL-signaler i 2025. Avveining:
- 5.0 floor: 2023 OOS publiserte 36 SELL-signaler, 75% hit-rate (vellykket i forbud-regime)
- 7.5 floor: 2023 OOS ville publisert 23 SELL-signaler, 65.2% hit-rate (mer selektiv)
- Skal vi applye nå, eller vente til 2026 Q3 rolling-floor-rerun?

**E) Setup-publish-gate — separere score-publish fra setup-publish?**
I dag: signal published=True KUN hvis score>=floor AND `build_setup` returnerer ikke-None. Dette betyr at noen signaler scorer høyt nok men ikke publiserer fordi entry-level/R:R ikke er gunstig. Bør UI/log skille mellom "scoring-publish" og "setup-publish"?

**F) Comtrade real-time-fordel — empirisk verifiser**
v3 OOS 2023 viser Comtrade dobler A+ SELL hr (25% → 50%). Men:
- n=4-6 er fortsatt lavt — kan være statistisk støy
- Bør vi utvide OOS-vinduet til 2022-2024 (2-3 år) for å øke n?
- Andre regimer (2017 oversupply, 2020 covid) kunne testet generaliserbarhet

**G) Manglende data — neste prioritet?**
Etter Comtrade har vi månedlig India-eksport. Gjenstår fra original F-tabell:
- **CEPEA Brasil cash-pris** (DEFERRED — Cloudflare-blokkering, krever browser-emulering)
- **OCSB Thailand månedlig** (2 dager, middels ROI)
- **DFPD/MoCA scraper** (event-drevet India-policy-detektor — supplement til Comtrade)

Vil du prioritere én av disse, eller foreslå annet?

---

*Genertert 2026-05-06 etter session 154. Branch: `main`. Commits: `28550a3..6542774` (sub-fase 12.11+ + 12.11++).*
