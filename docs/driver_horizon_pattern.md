# Driver-horisont-mønster — sub-fase 12.7 R2

Dato: 2026-04-28
Session: 120 (R2)
Status: levert (R2, ren-doc — ingen kode-endringer)
Refererer til: PLAN § 19, ADR-006 (direction-asymmetric scoring),
ADR-010 (horisont-bevisst driver-pattern), ADR-011 (backfill-policy),
`docs/horizon_refactor_audit.md`, `docs/driver_authoring.md`,
`docs/rule_authoring.md`

## Hensikt og scope

ADR-010 låser at engine setter en `_horizon`-key i driver-`params`, analogt
med ADR-006s `_direction`. Drivere som er horisont-bevisste leser
`params["_horizon"]` og velger feature; alle andre ignorerer keyen og kjører
bit-identisk som før.

Dette dokumentet låser **konvensjonen** R3 og R4 forholder seg til når
horisont-bevissthet faktisk implementeres i driver-koden:

1. Hvilke standard feature-typer drivere kan produsere
2. Hvilke tester en horisont-bevisst driver må passere
3. Hvordan sesong- og mean-reversion-spesialiseringer holder seg innenfor
   eksisterende polarity-system
4. Hvordan hele bildet henger sammen i to ende-til-ende-eksempler
5. En sjekkliste for driver-forfattere i R3 / R4 / D-fasene

Trading-logikk er låst per PLAN § 19.3 (12m + 36m percentil-vinduer; 2/98
hard og 5/95 soft ekstrem-terskler; cocoa GHS/XOF droppet; cotton ENSO
uendret). Dette dokumentet **omtolker ikke** noen av disse — det formaliserer
hvordan låsene materialiserer seg i driver-konvensjon.

R2 er ren dokumentasjon. Ingen drivere, tester eller YAML endres her.
Implementasjon starter i R3.

---

## 1. Feature-typer

En *feature* er en navngitt skalar `[0..1]` som en driver kan produsere.
Driver-funksjons-signaturen er fortsatt `(store, instrument, params) ->
float` (ADR-010 + driver-kontrakten fra Fase 1) — driveren returnerer én
skalar per kall. Featuren bestemmes av driver-koden, evt. valgt via
`params["_horizon"]` eller en YAML-`mode`-param.

To kategorier: tids-serie-typer (R3-R4 + D-faser implementerer disse) og
event-baserte typer (Plan-S — ikke i 12.7 D-fasen).

### 1.1 Tids-serie-typer

#### `pct_12m` — 12-måneders rolling percentile

- **Formel:** rank av siste observasjon mot rolling 12-måneders historikk
  (≈252 dager for daglige serier, ≈52 obs for ukentlige) → mappet
  lineært til `[0..1]`. Underliggende implementasjon kan bruke
  `_stats.rank_percentile` med `lookback_weeks=52` (presedens i
  `positioning_mm_pct`).
- **Primær horisont:** MAKRO (regime-klassifisering). 12m fanger
  sesong-syklus + matcher eksisterende 52w-bruk.
- **Polarity-bruk:** familie-`polarity: directional` (engine flipper
  `1 - value` for SELL); driver returnerer "1.0 = ekstrem long-of-
  instrument".
- **Min historikk:** ≥27 obs (engine `MIN_OBS_FOR_PCTILE` + 1 — se
  `_stats.py`).
- **Eksempel:** TFF MM net positioning i Gold = 850k kontrakter, 12m-rang
  = 0.92 → driver returnerer `0.92`. På SELL-side flipper engine til
  `0.08` (svak SELL-confluence).

#### `pct_36m` — 36-måneders rolling percentile

- **Formel:** identisk med `pct_12m` men med ≥156 ukentlig-obs (eller
  ≈756 dager for daglige). Ved utilstrekkelig historikk: fall-back til
  `pct_12m` (med log; ikke 0.0 — det ville maskere at instrumentet er
  yngre enn vinduet, ikke at MM er nøytral).
- **Primær horisont:** MAKRO langtids-regime (fanger fed-syklus + multi-
  commodity-cykler).
- **Polarity:** directional, samme som `pct_12m`.
- **Eksempel:** Real yield = −0.4 % på 36m-rang = 0.05 ⇒ `real_yield`-
  driver med `bull_when=low` returnerer høyt (`pct_36m`-feature kan
  brukes inn i terskel-trapp-mappingen i stedet for absolutt nivå).
- **Backfill-avhengighet:** krever ≥36m historikk per ADR-011 (2010-
  cutoff dekker dette med god margin for de fleste fetchere).

#### `delta_5d_z` — 5-dagers z-score-endring

- **Formel:** `(value_t − value_{t−5}) / σ_5d`, der `σ_5d` er rolling-std
  av samme 5-dagers diff over 252-dagers vindu. Returneres mappet til
  `[0..1]` via terskel-trapp `(z ≥ 2 → 1.0, z ≥ 1 → 0.75, z ≥ 0.5 → 0.6,
  z ≥ 0 → 0.5, z ≥ −0.5 → 0.3, ellers → 0.0)`. Trappen følger
  `momentum_z`-konvensjonen (presedens i `positioning.cot_z_score`).
- **Primær horisont:** SWING (1-2 ukers momentum/positioning-shift).
- **Polarity:** directional. `1.0 = sterk bullish-bevegelse siste 5 dager`
  for instrumentet. Engine flipper for SELL.
- **Eksempel:** MM-net-positioning økte 50k kontrakter siste 5d, σ_5d-
  rolling = 25k ⇒ z = 2.0 ⇒ feature = 1.0 (sterk SWING-confluence-
  trigger).

#### `delta_20d_z` — 20-dagers z-score-endring

- **Formel:** identisk struktur, vindu = 20d. Mer stabil signal,
  fanger 4-ukers trend-confirmation.
- **Primær horisont:** SWING + MAKRO grenseflate (trend-confirmation).
- **Eksempel-bruk:** Baker Hughes 4-8w break (PLAN § 19.6) materialiseres
  som `delta_20d_z` på rig-count-serien.

#### `extreme_flag_hard` — 2/98-percentile-flagg

- **Formel:** returnerer `1.0` når underliggende `pct_12m` (eller
  `pct_36m`, valgt via param) er `≥ 0.98` eller `≤ 0.02`, ellers `0.0`.
  Dette er en boolean uttrykt som skalar slik at driver-kontrakten
  bevares.
- **Primær horisont:** SWING mean-reversion-trigger (hard).
- **Polarity-bruk:** familie-`polarity: directional` opprettholdes.
  Featuren betyr "ekstrem nådd, mean-reversion sannsynlig"; tolkningen
  bull/bear avgjøres av driver-koden via `_direction`-mønstret eller av
  hvordan familien er sammensatt (ofte sammen med `pct_*`-feature i
  samme YAML-driver-entry, ulike weights).
- **Eksempel:** AAII bull-share-percentile = 0.99 ⇒ `extreme_flag_hard =
  1.0`. AAII er typisk contrarian (se § 3.2) ⇒ driveren inverterer
  internt og returnerer `1.0 = bear-of-SP500` for BUY-direction —
  engine flipper til 0.0 på BUY, beholder 1.0 på SELL. Familien får
  da SELL-confluence-bidraget.

#### `extreme_flag_soft` — 5/95-percentile-flagg

- **Formel:** identisk men med 0.95 / 0.05-tersklene. "Approaching
  ekstrem" — earlier warning før hard flag triggrer.
- **Primær horisont:** SWING (pre-positioning før hard flag).
- **YAML-konvensjon:** PLAN § 19.3 sier "begge eksponert; YAML-vekting
  velger". I praksis betyr dette at driver-funksjonen tar `mode`-param
  (`"pct"` / `"flag_hard"` / `"flag_soft"`) og YAML kan velge mellom
  dem som tre separate driver-entries i samme familie hvis ønskelig.
  Default-mode er `"pct"` for å matche dagens output.

### 1.2 Event-baserte (Plan-S — ikke i 12.7 D-fasen)

Disse feature-typene dokumenteres her slik at vokabularet er på plass når
Plan-S kommer (PLAN § 19.10 — egen syklus etter D2). De krever schema-
endringer som ikke er gjort: structured surprise-vs-consensus, event-
outcomes-tabell, sentralisert release-clock. **Implementeres ikke i 12.7
D-fasen** (selv om enkelte fetchere som leverer rådata-grunnlaget — FAS,
NOPA, EIA — kommer i D1/D2).

#### `surprise_z`

- **Formel:** `(actual − consensus) / σ_surprise_history`, der σ er
  rolling-std av tidligere surprise-magnitudes for samme release.
- **Primær horisont:** SWING (post-release katalysator) + SCALP (ved
  release-tidspunkt).
- **Schema-krav:** wasde/eia/fas-fetchere må lagre forventning per
  release. Ikke på plass i dag.

#### `time_to_release_min`

- **Formel:** minutter til neste scheduled release for relevant kalender-
  event (FAS tor 8:30 ET, NOPA mnd ~15., EIA ons 10:30 ET, WASDE mnd
  12:00 ET, NFP, FOMC, CPI). Mappet til `[0..1]` (f.eks. 1.0 i
  ±15-min-vindu rundt release, 0.0 ellers).
- **Primær horisont:** SCALP (vol-ekspansjon rundt release).
- **Schema-krav:** sentralisert release-clock-orchestrator.

#### `post_release_drift_3d`

- **Formel:** retning + magnitude av price-drift de første 3 dagene
  etter siste release (sign-aware, mappet til `[0..1]` der 1.0 = sterk
  bullish drift).
- **Primær horisont:** SWING.
- **Schema-krav:** event_outcomes-tabell.

### 1.3 Konvensjon: én feature per driver-kall, valgt via `_horizon` eller `mode`

En horisont-bevisst driver implementerer typisk to-tre features internt
og velger basert på:

1. `params["_horizon"]` (engine-injisert per ADR-010) — "default-mapping"
   som kombinerer flere features mot horisont:
   - SCALP → `time_to_release_min` (når Plan-S aktiverer) eller fall-back
   - SWING → `delta_5d_z` eller `delta_20d_z` eller `extreme_flag_*`
   - MAKRO → `pct_12m` eller `pct_36m`
2. Eksplisitt `params["mode"]` (YAML-styrt override) — kan tvinge
   feature-valg uavhengig av horisont. Brukes når samme driver listes
   to ganger i en familie med ulike modes (eks. `pct_12m` + `delta_5d_z`
   som to separate driver-entries med egne weights).

Driver-koden velger `mode` først (eksplisitt YAML), faller så tilbake til
`_horizon`-mapping, og til slutt til en hardkodet default. Default for
**alle eksisterende drivere** er den featuren driveren produserer i dag —
det er bit-identisk-garantien fra R1 (snapshot-baseline 104 rader).

---

## 2. Per-horisont test-strategi

Tre test-typer eksplisitt. Hver horisont-bevisst driver må ha minst Type
A. Type B og C anvendes der relevant (typisk for `pct_*` og `delta_*`-
features).

### 2.1 Type A — Snapshot (score-uendret per inst × horisont × retning)

- **Hensikt:** R1-baseline (`tests/snapshot/expected/score_baseline.json`,
  104 rader) garanterer bit-identisk score etter hver driver-refactor i
  R3, batch i R4, og er regresjons-anker også gjennom D-fasene.
- **Mønster:** ny test (`tests/snapshot/test_score_baseline.py` — eller
  hva R1 navnga den, sjekkes ved første R3-driver) re-genererer scores
  for alle (inst, horizon, direction)-kombinasjoner og sammenligner mot
  expected. Diff = 0 er hard kriteriet.
- **Eksempel-assertion:**
  > "For (Brent, SWING, BUY): score, grade, family_scores er bit-
  > identisk med expected-baseline."
- **Når R3-driveren refactor-es:** YAML uendret. Default-feature i
  driver-koden er den driveren produserte før refactor (per § 1.3). Det
  er den eksplisitte garantien. Kjør baseline-script PRE-refactor for å
  fange evt. DB-drift; refactor; kjør POST-refactor — diff må være 0.
- **Sårbarhet:** baseline mot live-DB drifter når DB endres mellom
  PRE- og POST-kjøring. R1-presedens (commit `6c81a5b`) viste at
  pytest-suite kan skrive til `data/bedrock.db`. Mitigasjon: kjør
  PRE-baseline rett før refactor, isolér POST-snapshot fra annen
  test-aktivitet, og sammenlign innenfor samme DB-state. R1 etablerte
  dette som workflow i `tests/snapshot/README.md`.

### 2.2 Type B — Monotonisitet ved gradvis data-tilkomst

- **Hensikt:** verifiser at percentil-typer (`pct_12m`, `pct_36m`) er
  monotont stigende på en monotont stigende serie, og likedan for
  fallende.
- **Mønster:** synthetic data via en in-memory mock-store (eller
  `pd.Series`-fixture). Kjør driveren ved t, t+1, ..., t+n med en
  serie der hver ny observasjon er strengt høyere enn forrige. Assert
  at `pct_12m`-output ved hver tidssteg er ≥ output ved forrige
  tidssteg. Det fanger bug der percentil-vinduet er feil glide-vindu
  eller indeks-misalignment.
- **Eksempel-input:** `series = [0.1, 0.2, ..., 1.0]` (10 obs strigende).
  Etter MIN_OBS_FOR_PCTILE er nådd, alle `pct_12m`-outputs ved hver
  tidssteg er monotont stigende.
- **Eksempel-assertion:**
  > "For en strengt stigende synthetic-serie x[0..n]: `pct_12m(x[i])`
  > ≤ `pct_12m(x[i+1])` for alle i ≥ MIN_OBS_FOR_PCTILE."
- **Skip-vilkår:** drivere som ikke produserer `pct_*`-features (f.eks.
  ren-event-drivere) trenger ikke type B.

### 2.3 Type C — Regime-shift fanger delta

- **Hensikt:** verifiser at `delta_*_z`-features faktisk reagerer på
  step-changes i underliggende serie.
- **Mønster:** synthetic-serie med kontant verdi i 20 obs, så et stort
  hopp (5σ over rolling-std), så kontant igjen. Kjør driveren rett før
  og rett etter hoppet. Assert at `delta_5d_z` (eller relevant feature)
  går fra ~0.5 (nøytral) til ≥0.9 over et 5-dagers vindu og deretter
  faller tilbake mot 0.5 etter 10-15d.
- **Eksempel-input:** `series = [100]*20 + [110]*20` (5σ-hopp ved t=20).
- **Eksempel-assertion:**
  > "Ved t=24 (4 dager etter hopp): `delta_5d_z` ≥ 0.9. Ved t=35: `< 0.7`
  > (z har normalisert)."
- **Skip-vilkår:** drivere uten `delta_*`-feature.

### 2.4 Hva test-strategien IKKE dekker

- Tester av YAML-validering (Pydantic-schema) — det dekkes av `rule_*`-
  testene, ikke driver-tester.
- Tester av aggregator-logikk (weighted_horizon, additive_sum) — egne
  tests i `tests/unit/test_aggregators.py`.
- Tester av engine-injeksjon av `_direction` / `_horizon` — egne tests
  i `tests/unit/test_engine_*.py` (R1 leverte
  `test_engine_horizon_propagation.py`).

---

## 3. Driver-intern logikk uten ny polarity

Polarity-systemet (`directional` / `neutral` på familie-nivå) er låst per
PLAN § 19.2. To eksempel-mønstre i 12.7 D-fasen krever spesialisert
driver-intern logikk uten å introdusere ny polarity-type.

### 3.1 Sesong-modulert mønster — `hdd_cdd_anomaly` (NaturalGas)

For NaturalGas er `hdd_cdd_anomaly` (heating-degree-days / cooling-degree-
days vs sesong-normal) en bull-driver, men hva som er "bull" avhenger av
kalender-måned:

- **Vinter (Nov–Mar, primært DJF):** HDD over normal ⇒ heating-demand
  ⇒ bull NG.
- **Sommer (Jun–Aug):** CDD over normal ⇒ AC-demand ⇒ gas-fired-power
  ⇒ bull NG.
- **Skuldermåneder (Apr–May, Sep–Oct):** lav demand-følsomhet ⇒
  driver returnerer ~0.5 (nøytral).

Driveren leser system-tid (eller `params["as_of"]` for testbarhet — samme
mønster som `seasonal_stage` i `seasonal.py`, som er presedens). Velger
HDD- eller CDD-aggregering basert på måned. Returnerer "demand-pressure-
score" `[0..1]` som er **bull-of-NG uansett sesong**.

YAML-polarity forblir `directional`. Driver-funksjonen tar `_horizon` som
den ignorerer (default), eller bruker den til å justere lookback-vindu
(MAKRO = 30d-anomaly, SWING = 5-7d-anomaly).

#### Pseudokode-skisse

```
@register("hdd_cdd_anomaly")
def hdd_cdd_anomaly(store, instrument, params) -> float:
    as_of = params.get("as_of") or date.today()
    month = as_of.month
    horizon = params.get("_horizon")  # MAKRO | SWING | None

    if month in (11, 12, 1, 2, 3):     # vinter
        agg = compute_hdd_anomaly(store, region, lookback_for(horizon))
    elif month in (6, 7, 8):           # sommer
        agg = compute_cdd_anomaly(store, region, lookback_for(horizon))
    else:                              # skuldermåneder
        return 0.5                     # nøytral demand-pressure

    return map_anomaly_to_score(agg)   # 1.0 = sterk anomaly = bull NG
```

#### Eksempel: bull/bear per sesong

- **15. januar, HDD = +25 % over 30d-normal i NE-USA** ⇒ vinter-grenen ⇒
  driver returnerer 0.9 (sterk bull NG). YAML directional ⇒ engine flipper
  til 0.1 for SELL-direction.
- **15. juli, CDD = +18 % over normal i TX/LA** ⇒ sommer-grenen ⇒ driver
  returnerer 0.85 (bull NG, AC-demand). Samme polaritets-håndtering.
- **15. april, skuldermåned** ⇒ driver returnerer 0.5 ⇒ familien får
  nøytralt bidrag.

#### Hvorfor dette mønsteret holder rammen ren

Alternativet ville være å introdusere en ny polarity-type (`seasonal_directional`
eller lignende) som engine måtte forstå. Det ville:

- Endre engine-koden (bryte score-uendret-garantien fra R1).
- Spre kalender-logikk fra driver-laget (hvor data og kontekst er) til
  engine-laget (hvor det ikke har noe å gjøre).
- Komplikere YAML-validering (Pydantic-schema må kjenne ny polarity).

Driver-intern logikk holder kalender-bevisstheten der dataen er, og
engine forblir ren skalar-aggregator. Samme mønster brukes i R3-presedens
(`seasonal_stage` i Corn outlook-familien — `monthly_scores`-array er
allerede driver-intern kalender-logikk uten ny polarity).

### 3.2 Mean-reversion-mønster — `extreme_contrarian_score` (AAII, F&G)

AAII bull-share-survey er en kontra-indikator: ekstremt høy bullish-
sentiment historisk → mean-reversion → bearish for SP500/Nasdaq.

**Driver-intern konvensjon:**
- Beregn underliggende `pct_12m` (rank av siste bullish-share-pct mot
  siste 12 mnd survey-historikk) ⇒ rå percentile `p ∈ [0..1]`.
- Returnér **`1 − p`** som driver-output når familien er definert med
  `directional` polarity og `1.0` skal bety "bull-of-instrument".
- Ekstremer (98. eller 2. percentil) gir ekstrem invertert score (~0.0
  eller ~1.0).

Det invertert-percentil-mønstret kalles **"extreme_contrarian_score"**.
Det er en **driver-intern output-konvensjon**, ikke en ny standard
feature-type — derfor listet i § 3, ikke § 1. Andre kontra-indikator-
drivere (F&G hvis det blir scoring-driver senere, BSI-spørringer hvis
implementert) følger samme mønster.

**Hva YAML ser:** ingen forskjell — `polarity: directional`, samme
weighted-aggregation som vanlig directional-driver. Engine flipper for
SELL som vanlig.

**Hvorfor ikke ny polarity:** samme begrunnelse som § 3.1. Inversjonen
hører til driver-koden (det er der vi kjenner at AAII er kontra-indikator);
engine-laget er agnostisk om hva som er bull eller bear for hvilket
instrument.

#### Eksempel: AAII bull-share = 60 % i SP500-positioning-familie

- AAII 12m-historikk-rang: `p = 0.97` (i topp 3 % av siste års obs).
- Driver returnerer `1 − 0.97 = 0.03` for BUY-direction (svakt bear-of-
  SP500-from-contrarian-perspective, ⇒ liten bull-confluence).
- Engine flipper for SELL: `1 − 0.03 = 0.97` (sterk SELL-confluence).
- Familien får "AAII er på contrarian-extreme nivå, hint mot
  mean-reversion-down" som SELL-side bidrag.

---

## 4. Ende-til-ende-eksempler

To konkrete eksempler som viser at hele kjeden — engine-flow + horisont-
propagering + feature-valg + familie-veiing + grade-beregning — henger
sammen.

### 4.1 Eksempel A — Brent SWING onsdag 10:30 ET (post-EIA-release)

#### Kontekst

- Instrument: Brent (financial, energy).
- Tidspunkt: onsdag 2026-XX-XX 10:30 ET, like etter EIA Weekly Petroleum
  Status Report-release.
- Kall: `engine.score("Brent", store, brent_rules, horizon="SWING",
  direction=Direction.BUY)`.

#### YAML (referanse: `config/instruments/brent.yaml`)

Brent har 6 familier i `weighted_horizon`-aggregering. SWING-vektene er:
`{trend: 1.0, positioning: 1.2, macro: 1.0, structure: 1.0, risk: 1.0,
analog: 0.6}` med `max_score = 5.8` og `min_score_publish = 2.5`.

Familier og drivere som faktisk evalueres (utdrag fra `brent.yaml`):

```
positioning:
  - cot_ice_mm_pct: 0.6  (ICE Brent COT, mm_net_pct, lookback 52w)
  - cot_z_score:    0.4  (CFTC mm_net_pct, lookback 52w)

macro:
  - real_yield:        0.15  (bull_when=low)
  - dxy_chg5d:         0.35  (bull_when=negative, window=5)
  - vix_regime:        0.20  (invert=true)
  - eia_stock_change:  0.30  (series_id=WCESTUS1)

risk: (polarity: neutral)
  - vol_regime:    0.7  (period=14, lookback=252, mode=high_is_bull)
  - event_distance: 0.3 (countries=[USD], impact=High, min_hours=4)
```

(trend / structure / analog tilsvarende — se YAML.)

#### Engine-flow

1. `Engine.score()` ⇒ `_score_financial(rules, horizon="SWING",
   direction=BUY, store, instrument)`.
2. `_score_financial` slår opp `horizon_spec = rules.horizons["SWING"]`,
   henter `family_weights` og `max_score` fra spec, og kaller
   `_score_families(store, "Brent", families, direction=BUY,
   horizon="SWING")`.
3. `_score_families` (ADR-010-patch) bygger
   `params_with_dir = {**driver.params, "_direction": "BUY",
   "_horizon": "SWING"}` for hver driver og kaller driver-funksjonen.

#### Driver-utfall (hypotetisk, illustrativ)

| Familie | Driver | `_horizon` lest | Feature | Råverdi | Vektet |
|---|---|---|---|---|---|
| positioning | cot_ice_mm_pct | "SWING" | `pct_12m` (default) | 0.78 | 0.468 |
| positioning | cot_z_score | "SWING" | z-trapp (default) | 0.75 | 0.300 |
| macro | real_yield | "SWING" | terskel-trapp (ignorerer `_horizon`) | 0.50 | 0.075 |
| macro | dxy_chg5d | "SWING" | `delta_5d_z`-mappet | 0.75 | 0.263 |
| macro | vix_regime | "SWING" | regime-trapp (invert=true) | 0.60 | 0.120 |
| macro | eia_stock_change | "SWING" | post-release surprise-proxy | 0.85 | 0.255 |
| ... | (resten beregnes tilsvarende) | | | | |

Family-scores etter weighted-sum innen familien (eks. positioning =
0.468 + 0.300 = 0.768; macro = 0.075 + 0.263 + 0.120 + 0.255 = 0.713;
osv.).

#### Aggregering

`_score_financial` aggregerer via `aggregators.weighted_horizon`:

```
total = Σ family_score * family_weight   (alle familier)
score = min(total, max_score=5.8)
```

Hypotetisk total = 4.2 ⇒ score ≤ 5.8, publish-cutoff 2.5 ⇒ publiseres.

#### Grade

`grade_thresholds` for Brent: A_plus = `min_pct_of_max=0.75, min_families=4`,
A = `0.55, 3`, B = `0.35, 2`. Med score = 4.2 og max_score = 5.8 er
`pct = 0.724` ⇒ A (under A_plus-terskel 0.75, over A-terskel 0.55), og
hvis ≥3 familier scoret > 0 (de fleste vil med denne data-konfigurasjonen)
⇒ grade = "A".

#### Hva R3/R4/D vil endre i dette eksemplet

- **R3 refactor** av `positioning_mm_pct` (analogt for `cot_ice_mm_pct`):
  driver-koden får `mode`-param og bruker `_horizon`-fallback. YAML
  uendret. Default-feature er fortsatt `pct_12m`. Score er bit-identisk.
- **R4 batch positioning-familien:** kan introdusere `delta_5d_z`-mode
  som ekstra driver-entry hvis YAML ønsker det. PLAN § 19.4 R4-rad
  krever snapshot grønn etter hver batch.
- **D1 (TFF-utvidelse):** ny driver `positioning_lev_funds_pct` legges
  til positioning-familien. Vekter justeres (f.eks. 0.6 → 0.45 for
  cot_ice_mm_pct, 0.4 → 0.30 for cot_z_score, 0.25 nytt for lev_funds).
  Familie-sum = 1.0-validering må passere (PLAN § 19.8).

### 4.2 Eksempel B — Corn yield-familie i juli (vekstsesong)

#### Kontekst

- Instrument: Corn (agri, grains).
- Tidspunkt: 15. juli (silking/yield-determinerende periode for US
  cornbelt).
- Kall: `engine.score("Corn", store, corn_rules, horizon=None,
  direction=Direction.BUY)`. (Agri har ingen horizon-arg per ADR-010 —
  driver-`_horizon` settes til `None`.)

#### YAML (referanse: `config/instruments/corn.yaml`)

Corn har 7 familier i `additive_sum`-aggregering. Family-`weight` er
absolutt cap per familie:

```
outlook:  weight 5  (seasonal_stage)
yield:    weight 3  (weather_stress 0.5, crop_progress_stage 0.5)
weather:  weight 2  (weather_stress)
enso:     weight 2  (enso_regime)
conab:    weight 2  (wasde_s2u_change 0.7, conab_yoy 0.3)
cross:    weight 2  (dxy_chg5d 0.55, shipping_pressure 0.2,
                     event_distance 0.1, cot_euronext_mm_pct 0.15)
analog:   weight 2  (analog_hit_rate 0.5, analog_avg_return 0.5)
                    (polarity: neutral)
```

`max_score = 20`, `min_score_publish = 7`.

#### Engine-flow

1. `Engine.score()` ⇒ `_score_agri(rules, direction=BUY, store, instrument)`.
2. `_score_agri` kaller `_score_families(..., horizon=None,
   direction=BUY)` ⇒ `params_with_dir["_horizon"] = None` for alle
   driver-kall.
3. Drivere som er horisont-bevisste (`weather_stress`, `crop_progress_stage`,
   evt. `seasonal_stage` i fremtiden) ser `_horizon = None` og bruker
   default-feature.

#### Yield-familien — driver-utfall (hypotetisk)

- `weather_stress` (lookback_months=1):
  - I juli for cornbelt: temperatur +2.5 σ over 30y-normal, nedbør
    −40 % under normal ⇒ vær-stress-aggregat = 0.85.
- `crop_progress_stage` (metric=GOOD_EXCELLENT, mode=low_is_bull):
  - NASS uke 28: GOOD_EXCELLENT = 58 % (siste 10 års rank: 0.30 ⇒ låg
    GE-pct = stigning av yield-risk). `low_is_bull` ⇒ driver returnerer
    `1 − 0.30 = 0.70`.

#### Yield-familie-score-beregning

```
yield_raw = weather_stress * 0.5 + crop_progress_stage * 0.5
          = 0.85 * 0.5 + 0.70 * 0.5
          = 0.425 + 0.350
          = 0.775   (skalar 0..1, family-internal weighted-avg)
```

`additive_sum` skalerer dette med family-weight og caper:
```
yield_contribution = min(yield_raw * family_weight, family_weight)
                   = min(0.775 * 3, 3)
                   = 2.325   (under cap = 3)
```

Cap = 3 ville bare slått inn hvis `yield_raw > 1.0` (ikke mulig i
praksis siden drivere returnerer `[0..1]`), eller hvis future driver-
sammensetning gir interne weights > 1.0. I dagens YAML er weights innen
familien 0.5 + 0.5 = 1.0, så cap er en safety-net.

#### Aggregering på instrument-nivå

`additive_sum(family_scores, family_caps)` (engine.py:312-313):
```
total = Σ min(family_raw_i * cap_i, cap_i)
```

Hypotetisk per-familie-bidrag:
- outlook: 1.0 (juli = peak silking) * 5 = 5.0
- yield: 2.325 (over)
- weather: 0.85 * 2 = 1.7
- enso: 0.7 * 2 = 1.4
- conab: 0.6 * 2 = 1.2
- cross: 0.5 * 2 = 1.0
- analog: 0.65 * 2 = 1.3
Total = 13.93 ⇒ score = min(13.93, max_score=20) = 13.93.

`min_score_publish = 7` ⇒ publiseres. `min_score=14` for A_plus,
`min_score=10` for A ⇒ med 13.93 og ≥4 aktive familier (alle 7 her ≥0):
**grade = A** (under A_plus-min, over A-min, families_active ≥ 3).

#### Hva D2 vil endre

PLAN § 19.5 + § 19.8: D2 legger `nopa_crush@0.20` til Soybean yield-
familien (Corn ikke direkte berørt for NOPA, men weather-familien får
`drought_monitor` lagt til):

- `weather_stress` 0.55 (var 1.00 i Corn weather-familie)
- `drought_monitor` 0.45 (ny)

Familie-sum = 1.0-validering må passere ved YAML-lasting (Pydantic-
schema). Snapshot-baseline regenereres som **nytt anker etter D2** (per
§ 5.3 nedenfor).

---

## 5. Driver-forfatter-sjekkliste

Operativ sjekkliste R3, R4 og D-fasene følger. **Tre ulike snapshot-
disipliner per fase-type — les § 5.3 før du starter.**

### 5.1 Per ny eller refactored driver

- [ ] **Feature-typer:** hvilken/hvilke standard typer fra § 1 produseres?
  Dokumenter i driver-docstring. Hvis ingen standard type passer:
  flagg til arkitekt før implementasjon (utvidelse av § 1 krever ADR).
- [ ] **Horisont(er):** hvilken horisont er hver feature primært for?
  Hvis driveren er horisont-bevisst: dokumenter `_horizon` ⇒ feature-
  mapping i docstring. Hvis horisont-uavhengig: si det eksplisitt
  ("ignorerer `_horizon`").
- [ ] **Polarity-erklæring:** familie-polarity i YAML er låst per PLAN
  § 19.2. Driveren returnerer `1.0 = bull-of-instrument` (eller invertert
  internt per § 3.2 hvis kontra-indikator). Aldri ny polarity-type.
- [ ] **Defensive feilhåndtering:** alle feil ⇒ 0.0 + structlog-warning,
  aldri kast (driver-kontrakten).
- [ ] **Tester (jf. § 2):**
  - [ ] Type A snapshot grønn (alltid).
  - [ ] Type B monotonisitet (hvis `pct_*`-feature produseres).
  - [ ] Type C regime-shift (hvis `delta_*`-feature produseres).
- [ ] **Backfill-historikk:** krever driveren ≥36m historikk for
  `pct_36m`? Sjekk at fetcheren har 2010-cutoff per ADR-011.

### 5.2 Per YAML-endring (D-faser)

- [ ] **Familie-sum = 1.0** validerer Pydantic-schema (PLAN § 19.8).
  Hvis ikke: STOP og spør — ikke fix stille.
- [ ] **Vekt-redistribusjon dokumentert** i commit-meldingen — hvilken
  driver mistet hvilken vekt.
- [ ] **PLAN § 19.8-verifikasjons-checklist** krysset av (om relevant).

### 5.3 Tre snapshot-disipliner

| Fase | Krav | Hva som er normalt | Hva som er rødt lys |
|---|---|---|---|
| **R3** | Bit-identisk score garantert kontraktuelt | Driver-refactor til å produsere flere features internt; YAML uendret; default-feature uendret; snapshot-diff = 0 | YAML-endring foreslås for å holde score uendret ⇒ stopp, du er ute av R3-scope |
| **R4** | Bit-identisk score garantert kontraktuelt (samme som R3, batch-vis utvidelse) | Mode-infrastruktur (`_horizon`-lesing per ADR-010 + valgfri mode-dispatcher) legges til alle gjenstående drivere; YAML uendret; default-output uendret; snapshot-diff = 0 per batch. Mode-aktivering på eksisterende drivere er etter R4 (egen senere syklus eller D-fase). | YAML-endring foreslås innen R4 ⇒ stopp, du er ute av R4-scope (R3-rødt-lys-kriteriet gjelder fortsatt) |
| **D** | Score endres forventet (nye drivere ⇒ ny score) | Snapshot-baseline regenereres som **nytt anker etter hver D-leveranse** (D0/D1/D2/D3 hver for seg). Diff dokumenteres per inst × horisont × retning i commit | Ingen score-endring etter D-leveranse ⇒ sannsynligvis driver returnerer 0.0 (defensive) eller er feilkonfigurert i YAML |

**R1-presedens (commit `6c81a5b`):** baseline kan drifte fra DB-aktivitet
i tester. Workflow: kjør PRE-baseline rett før refactor-commit, isolér
POST-snapshot fra annen test-aktivitet, sammenlign innenfor samme DB-
state. `tests/snapshot/README.md` (R1-leveranse) dokumenterer detaljer.

### 5.4 Når i tvil

- Refactor som krever YAML-endring i R3 eller R4 ⇒ **stopp, flagg, vent på
  beslutning**. Per CLAUDE.md "bestem og kjør" gjelder ikke når en
  fase-kontrakt risikeres. YAML-aktivering av modes hører til etter R4.
- Score-uendret-garantien brytes utilsiktet ⇒ **stopp, ikke commit**.
  Diagnostisér om det er DB-drift (ufarlig) eller faktisk algoritme-
  endring (kontrakts-brudd).
- Ny standard feature-type virker nødvendig ⇒ **flagg til ADR-prosessen**;
  utvidelse av § 1 krever oppdatert ADR-010 eller ny ADR.

---

## 6. Referanser

- PLAN § 19 (sub-fase 12.7 master-plan), særlig § 19.2 (uendret), § 19.3
  (låste beslutninger), § 19.4 (fase-tabell), § 19.6 (per-horisont-
  mapping), § 19.7 (Alt γ).
- ADR-006 — direction-asymmetric scoring (presedens for engine-injisert
  kontekst-key).
- ADR-010 — horisont-bevisst driver-pattern (Alt 1).
- ADR-011 — backfill-policy.
- `docs/horizon_refactor_audit.md` — R1-audit.
- `docs/driver_authoring.md` — driver-kontrakten.
- `docs/rule_authoring.md` — YAML-regler og polarity-system.
- `src/bedrock/engine/engine.py:345-401` — `_score_families` (post-R1).
- `src/bedrock/engine/drivers/_stats.py` — `rank_percentile`,
  `rolling_z`, `MIN_OBS_FOR_PCTILE`.
- `src/bedrock/engine/drivers/seasonal.py` — kalender-aware-presedens
  (`as_of`-override for testbarhet).
- `src/bedrock/engine/drivers/positioning.py` — `pct_12m`-presedens
  (`positioning_mm_pct`).
- `src/bedrock/engine/drivers/macro.py` — terskel-trapp-presedens
  (`real_yield`, `dxy_chg5d`).
- `src/bedrock/engine/drivers/agronomy.py` — agri-rank-presedens
  (`crop_progress_stage`).
- `tests/snapshot/expected/score_baseline.json` — R1-baseline (104
  rader).
- `tests/snapshot/README.md` — snapshot-workflow (R1-leveranse).
