# Engine fundamental review — 2026-05-06

**Triggeret av:** sukker-signal hvor MAKRO BUY 8.276 og MAKRO SELL 9.724 begge er over publish-floor.
**Spørsmål:** finnes det fundamentale design-feil? Inkrementell fix vs restart?

---

## Hovedfunn

System-audit viser **dette er IKKE et sukker-spesifikt problem** — det er systemisk.

- **16 instrument-horisont-konflikter** akkurat nå (BUY+SELL begge over floor)
- **11 instrumenter publiserer samme retning på flere horisonter** (e.g. USDJPY sell på SCALP+SWING+MAKRO)
- **Triple-risk-eksponering** mulig hvis alle setups blir fylt på samme entry-level

---

## 10 fundamentale design-issues

### Issue 1: Same-entry-duplisering på tvers av horisonter (CRITICAL)

Setup-builder bruker SAMME support/resistance + ATR for ALLE horisonter:
```
SETUP SELL SWING entry=18.2900 sl=18.4019 tp=13.2200
SETUP SELL MAKRO entry=18.2900 sl=18.4019 tp=trailing
```
Eneste forskjell: TP. Hvis bot fyller begge → 2× position size, samme entry, samme SL, korrelerer 100%.

**Konsekvens:** Risk-aggregering på instrument-nivå brytes. Daily-cap (2%) hjelper bare delvis.

### Issue 2: Per-direction-uavhengig scoring → kontradiktoriske signaler

Engine beregner BUY og SELL separat (ved å flippe driver-verdier). Resultat: 16 instrumenter har BÅDE retninger over floor:

| Instrument | Horisont | BUY | SELL | Δ |
|---|---|---:|---:|---:|
| Coffee | makro | 6.79 (B) | 10.01 (A) | +3.22 |
| Soybean | makro | 7.98 (B) | 10.02 (A) | +2.04 |
| **Sugar** | **makro** | **8.28 (A)** | **9.72 (A)** | **+1.45** |
| Cocoa | makro | 9.25 (A) | 6.75 (B) | -2.51 |
| Cotton | makro | 8.20 (A) | 7.05 (B) | -1.14 |

Logisk feil: "vi er bullish OG bearish samtidig". Setup-builder redder oss noen ganger ved å returnere None for én side, men det er tilfeldig — ikke design.

### Issue 3: Familie-vekter satt manuelt + additive_sum → fake ortogonalitet

7 familier × manuelle vekter (5/3/2/2/2/2/2 = 18). Vi har målt familie-korrelasjon (max ρ=0.42) på historiske data, men i real-time kan flere familier samtidig svinge samme vei pga underliggende felles regime-faktor (risk-on/off, USD-styrke, sesong).

**Effective ortogonal info-mengde ≈ 3-4 dimensjoner, ikke 7.** Men engine tror den har 7 uavhengige stemmer.

### Issue 4: Score >= floor er sirkulær logikk

- Floor=7.0 satt empirisk fra rolling 5y backtest
- Backtest brukte SAMME drivere som score den evaluerer
- Drivere som "ikke virket" ble tunet/dropped underveis
- Floor reflekterer at drivere VAR kalibrert til ~50% hr over score 7

Dette er overfit ved konstruksjon. Out-of-sample-testen 2023 er det ENESTE som faktisk validerer.

### Issue 5: Forward-pricing mismatch (sukker-spesifikt men generaliserbart)

Sukker no.11 prises 6-12 mnd forward. Vi har 1 driver som forsøker å fange dette (`seasonal_stage` med forward-syklus). Resten leser CURRENT/HISTORICAL data:
- UNICA cum-prod (siste safra)
- USDA PSD årlig (sist publisert)
- ENSO månedlig (current)
- COT ukentlig (current)

Når Green Pool oppjusterer 2026/27 deficit fra 1.66 → 4.3 MMT, **null driver fanger det**. Markedet handler dette; vi gjør ikke.

### Issue 6: Analog-driver er black box med dominant impact

Sukker MAKRO SELL har analog=1.0 (max). Det betyr 5 K-NN-matcher gikk ned > 3% over 30d. Men:
- Hvilke matcher? På hvilken dimensjon-likhet?
- Forrige analytiker sa "K-NN softs typisk lav-signal høy-overfit"
- Når analog=1.0 dominerer (bidrar 1.0 av 7-familie-totalsum), maskerer det reell signal-mangel fra andre familier

### Issue 7: Setup-builder er kontekst-blind

`build_setup` bruker last 90d swing-analyse + round-numbers for entry. Samme nivå returneres for alle 3 horisonter. Ingen variasjon basert på:
- Horisont-typisk volatility
- Trend-modus (trending vs mean-reverting)
- Distance-to-target (MAKRO bør kanskje vente lenger fra current pris)

### Issue 8: Bot-side risk-aggregering på instrument-nivå mangler

Hver setup blir egen position med 0.5-1% risk. 3 horisonter publiserer samtidig → 3 positions × 1% = 3% risk på samme instrument. Daily-cap (2%) saver delvis, men:
- Spread på samme entry = 100% korrelert
- Effective σ-eksponering er 3× planned

### Issue 9: Sekvensiell oppdatering = stale-state

Fetcher kjører → signals-all → bot leser. Hvis flere fetchere kjører i parallell, signals-all kan bli kalt med stale data fra noen. Race conditions kan gi inkonsistente signaler mellom horisonter (sett fra bot-side).

### Issue 10: Vekt-rebalansering er ad-hoc → drift over tid

Vi har 5 drivere i sukker unica-familien nå (35+15+15+10+25=100%). Vekter satt basert på "denne nye driveren bør være middels viktig". Ingen empirisk optimalisering. Når vi legger til ny driver, må vi rebalansere ALLE manuelt — vekter "drifter" gradvis uten styring.

---

## Vurdering: restart vs inkrementell

### Restart (ny v2-engine):

**Pros:**
- Adresserer alle 10 issues med ren design
- Mulig å bygge "1 setup per instrument max"-arkitektur fra start
- Probabilistisk ensemble eller walk-forward learner muliggjøres

**Cons:**
- 12+ måneder arbeid investert (fetchers, drivere, infra, tests)
- 2-3 mnd refactor (ikke uker)
- Risiko for å miste velprøvde subkomponenter (analog backbone, COT-parsing, etc.)
- Backtest-historikk + DSR-validering må regenereres
- Bot-side må re-integreres

### Inkrementell (fix-in-place):

**Pros:**
- 7 av 10 issues løses med < 1 ukes fokusert arbeid
- Beholder all data + driver-bibliotek
- Bot-integrasjon uendret
- Lavere risiko

**Cons:**
- Issue 3 (fake ortogonalitet) og 4 (sirkulær floor) er strukturelle — krever ML-tilnærming
- Issue 6 (analog black box) krever ablation + mulig redesign
- Vil fortsatt være "fokusert lapping" snarere enn redesign

**Min anbefaling: INKREMENTELL i 3 faser.**

---

## Fase-plan (anbefalt)

### Fase A — Coordination layer (1-2 dager, høy ROI)

Adresserer Issue 1, 2, 7, 8 — de mest synlige operasjonelle problemene.

#### A1: Cross-direction net-bias filter (Issue 2)
- Nytt orchestrator-step: etter scoring av begge retninger, beregn `delta = abs(sell_score - buy_score)`
- Hvis `delta < threshold` (e.g. 1.5): NEUTRAL — ingen signal publiseres
- Hvis `delta >= threshold`: kun dominant retning publiseres, motsatt blokkeres med skip-grunn `opposing_direction_dominant`
- Threshold konfigurerbar per asset_class

#### A2: Cross-horizon dedup (Issue 1)
- Etter setup-builder: hvis samme instrument+retning har flere horisonter med samme entry-level (innenfor 0.3% spread):
  - Behold KUN lengste horisont (gir lengst trailing TP)
  - Logg de andre med skip-grunn `subsumed_by_longer_horizon`
- Reduserer USDJPY sell scalp+swing+makro til kun makro (1 setup vs 3)

#### A3: Bot-side per-instrument risk-cap (Issue 8)
- Bot.yaml: `per_instrument_max_risk_pct: 1.0`
- Hvis flere setups for samme instrument: del risk-cap mellom dem
- Prevenerer overlapping positions selv om engine produserer multiple setups

#### A4: Setup-builder horisont-aware entry-distance (Issue 7)
- MAKRO setups krever entry > 1.5×ATR fra current pris (krever bedre fill)
- SWING: > 0.7×ATR
- SCALP: > 0.3×ATR
- Differensierer entry-nivåer per horisont automatisk

**Effekt etter Fase A:** 16 conflicts → forventet 0-3. 11 multi-horizon → ~5 (kun de der entry-nivåer faktisk er forskjellige). Triple-risk eliminert.

### Fase B — Forward-data-feeds (1 uke, middels ROI)

Adresserer Issue 5 — forward-pricing mismatch.

#### B1: Bygg `unica_estimativa_change`-driver
- Parser UNICA's bi-årlige neste-safra-prog (estimativa-rapporter)
- Ny series_id: `UNICA_ESTIMATIVA_NEXT_SAFRA_SUGAR_KMT`
- YoY-endring som directional-driver (lavere prog = bull next-safra = bull)

#### B2: Scrape Green Pool / Czarnikow / Safras / StoneX deficit-revisjoner
- Manuell PDF-parsing eller email-feed-monitoring
- Lagres som `BALANCE_FORECAST_REVISION_<source>`-series
- Driver `forecast_revision_z` som måler magnitude+retning av siste revision

#### B3: USDA FAS GAIN-rapport-parser
- 2-4 PDFs per år per land (India, Brasil, Thailand)
- Forward commentary + tonn-prog
- Lavere ROI enn B1+B2 men supplerer

**Effekt etter Fase B:** Sukker engine fanger 2026/27-deficit-revisjoner. Forward-mismatch reduseres.

### Fase C — Empirisk vekt-optimering (2-3 uker, høy ROI men kompleks)

Adresserer Issue 3, 4, 10 — sirkulær logikk + ad-hoc vekter.

#### C1: Walk-forward gradient-based vekt-tuning
- Per (instrument, horizon): finn optimale familie-vekter via L-BFGS på rolling 3-yr Sharpe
- Re-tune månedlig på sliding window
- Erstatter manuelle vekter med data-driven

#### C2: Driver-deflate basert på k-effective
- Beregn effective k = total drivere / (1 + max(intra-family-corr) × n_families)
- Bruk k_eff i grade-thresholds (e.g. A_plus = top 5% av score-distribusjon, ikke fast 10)

#### C3: Out-of-sample-only floor-kalibrering
- Floor settes på siste 12 mnd som ALDRI har vært brukt til driver-tuning
- Re-kalibreres månedlig
- Eliminerer sirkulær backtest-bias

**Effekt etter Fase C:** Score-systemet blir empirisk forsvarlig (ikke intuisjon-drevet). Kompleks å implementere men eliminerer Issue 4-bias.

---

## Beslutnings-poeng for operatør

1. **Skal vi gå med inkrementell (Fase A → B → C)?** — anbefalt
2. **Eller restart?** — kun hvis du tror Fase C alene ikke kan løse Issue 3 (ortogonalitet-illusjonen)
3. **Hvis inkrementell — kan jeg starte Fase A nå?** — A1+A2 er mest verdifulle, ~4 timer arbeid
4. **Når Fase A er ferdig — vil du ha Fase B (forward-data) eller Fase C (vekt-ML) først?**

---

## Risiko ved status quo

Hvis vi IKKE fikser disse:

- Bot vil produsere "trippel-eksponering" på instrumenter der alle 3 horisonter publiserer samme retning — 11 instrumenter sårbar i dag
- Kontradiktoriske signaler (16 tilfeller nå) signaliserer engine-confusion til operatør → tap av tillit
- Forward-pricing-mismatch betyr backtest-edge på 180-270d horisont kan være delvis luck — out-of-sample 2026/27 vil avsløre
- Vekt-drift over tid uten styring → engine-output kan bli systematisk feil etter 6-12 mnd uten å bli oppdaget

---

*Generert 2026-05-06. Triggert av sukker MAKRO BUY+SELL-konflikt. Branch: main.*
