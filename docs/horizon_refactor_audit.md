# Horizon-refactor audit — sub-fase 12.7 R1

Dato: 2026-04-28
Session: 119 (R1)
Status: levert (R1)
Refererer til: PLAN § 19, ADR-006, ADR-010 (horisont-pattern), ADR-011 (backfill-policy)

## 1. Hensikt

R1 åpner sub-fase 12.7 (horisont-refactor + data-utvidelse) per Alt γ
(PLAN § 19.7). Dette dokumentet er auditen som ADR-010 og ADR-011 låses
mot. Gjennomgang av dagens engine-flow + driver-pattern, sammenligning
av tre kandidat-arkitekturer for å gjøre drivere horisont-bevisste, og
begrunnelse for valgt arkitektur (Alt 1).

R1 leverer:

1. Denne audit-en (`docs/horizon_refactor_audit.md`).
2. ADR-010 — Horisont-bevisst driver-pattern.
3. ADR-011 — Backfill-policy for sub-fase 12.7-fetchere.
4. Engine-patch (`src/bedrock/engine/engine.py`) som propagerer
   `_horizon` i `params_with_dir`, analogt til ADR-006s `_direction`.
5. Micro-test (`tests/unit/test_engine_horizon_propagation.py`) som
   bekrefter at engine setter key korrekt og at eksisterende driver er
   bit-identisk uavhengig av om `_horizon` er satt.
6. Snapshot-baseline (`tests/snapshot/expected/score_baseline.json`)
   for alle 22 instrumenter × relevante horisonter × 2 retninger,
   tatt PRE-patch og verifisert uendret POST-patch. Dette er
   regresjons-ankeret R3 og R4 vil sjekke mot.

## 2. Dagens engine-flow

### 2.1 Driver-kontrakt

Alle drivere er registrert via `@register("navn")` i
`src/bedrock/engine/drivers/__init__.py` med signatur:

    (store: StoreLike, instrument: str, params: dict[str, Any]) -> float

Kontrakten er låst (PLAN § 4 + STATE invariants). Drivere er rene
funksjoner: ingen side-effekter, deterministisk, returnerer 0..1
(eller -1..1 for bi-direksjonale), feil → 0.0 + log.

`params` er driver-spesifikk YAML-config samt en utvidelse fra
ADR-006:

- `_direction` (lagt til av engine): `"BUY"` eller `"SELL"`.
  Drivere som er direction-aware (analog-familien) leser dette;
  andre ignorerer det.

`_direction`-mønstret er presedensen R1 viderefører til `_horizon`.

### 2.2 Engine-flow

`Engine.score(instrument, store, rules, horizon=None,
direction=Direction.BUY) -> GroupResult` (engine.py:219-244):

1. Slår opp i `rules` (FinancialRules eller AgriRules) og dispatcher
   til `_score_financial` (krever horizon-streng) eller `_score_agri`
   (ignorerer horizon).
2. Begge dispatchere kaller `_score_families(store, instrument,
   families, direction)` (engine.py:345-401) som er felles.
3. `_score_families` itererer alle drivere i alle familier, beriker
   driver-params med `_direction`, kaller driver-funksjonen, flipper
   verdien til `1 - value` for `direction=SELL` på familier med
   `polarity="directional"`, akkumulerer family-score.
4. Returverdiene aggregeres (`weighted_horizon` for financial,
   `additive_sum` for agri) og graden beregnes.

**Kritisk observasjon for R1:** I `_score_families` er kun
`direction` i scope; horizon er allerede konsumert av
`_score_financial` (via `horizon_spec = rules.horizons.get(horizon)`)
og kastet bort før driverne kjører. Drivere har derfor i dag ingen
måte å vite hvilken horisont scoring-en gjelder for.

### 2.3 Score-fan-out per session

Orchestrator (`generate_signals` i `signals.py`) kaller
`engine.score()` med:

- 15 financial instrumenter × 3 horisonter × 2 retninger = **90 kall**
- 7 agri instrumenter × 1 (horizon=None) × 2 retninger = **14 kall**
- Totalt **104 kall per signals-regenerering**.

PLAN § 19 sier "22 inst × 3 horisonter × 2 retninger = 132". Det
abstrakte tallet 132 inkluderer agri × 3 horisonter slik orchestrator
materialiserer dem på signal-output-siden (én signal-entry per
horisont selv om engine.score() bare ble kalt én gang). For
score-uendret-garantien er det 104 engine-side-kall som er den
naturlige enheten — det er det dette dokumentet og snapshot-baseline
bruker.

## 3. Hvorfor horisont må inn i driver-laget

### 3.1 Data-kilder med ulik signal-verdi per horisont

Flere planlagte og eksisterende data-kilder produserer **forskjellige
features** av samme rådata avhengig av tidshorisont:

| Kilde | MAKRO-feature | SWING-feature | SCALP-feature |
|---|---|---|---|
| CFTC TFF (positioning) | 12m percentil | ukentlig delta-z | mandag-gap-z |
| Baker Hughes (rig count) | 13w trend | 4-8w break | (n/a) |
| VIX termstruktur | regime (^VIX/^VIX3M) | regime-switch-z | VIX9D/VIX-ratio |
| AAII sentiment | 12m percentil | 5d delta-z | (n/a) |
| FAS Export Sales | 26w trend | ukentlig surprise | release-time-distanse |

Dagens arkitektur tvinger fram tre uavhengige drivere per kilde for å
dekke de tre horisontene — feature-engineering dupliseres i tre filer,
driver-registry vokser 3×, og YAML må vedlikeholde tre navn der ett
kunne dekke alle horisonter.

### 3.2 Symmetri med direction-asymmetric scoring

ADR-006 (session 95a/95b) etablerte at engine kan injisere kontekst
(retning) i driver-params via en intern `_direction`-key uten å bryte
driver-kontrakten. De fleste drivere ignorerer denne; et fåtall
(analog-familien) leser den og returnerer ulike scores per retning.

Samme mønster fungerer for horisont. R1 leverer engine-siden av denne
mekanismen; R2-R4 vil oppdatere konkrete drivere til å lese
`_horizon` der relevant.

## 4. Tre arkitektur-alternativer

### 4.1 Alt 1 — YAML-styrt `_horizon`-param via engine-propagering (anbefalt)

Engine setter `_horizon` i en kopi av driver-params, analogt med
`_direction`. Driver-funksjons-signaturen er uendret. Drivere som er
horisont-uavhengige ignorerer key-en og kjører som før (bit-identisk).
Drivere som er horisont-bevisste leser `params["_horizon"]` og velger
feature.

**Pro:**

- Minimal engine-endring (~5 linjer i `_score_families`).
- Driver-kontrakten er uendret. Eksisterende ~22 drivere trenger
  ingen signature-endring.
- Snapshot-tester gir bit-identisk score for alle horisont-uavhengige
  drivere ut av boksen.
- Konsistent med ADR-006 — neste utvikler ser umiddelbart at
  `_horizon` følger samme mønster som `_direction`.
- YAML er lesbar: én driver-entry per familie per instrument, og hvis
  en driver oppfører seg ulikt per horisont skjer det inni driver-
  funksjonen (reproducible feature-pipeline).
- For agri (no horizon på engine-siden) settes `_horizon` til None;
  agri-drivere som trenger horisont-info kan ta det som vanlig
  YAML-param i tillegg.

**Con:**

- Driver-koden må eksplisitt sjekke `params.get("_horizon")` der det er
  relevant. Dette gjør det implisitt at horizon er tilgjengelig — ikke
  selv-dokumenterende på signaturen. Mitigeres ved konvensjon:
  `docs/driver_authoring.md` oppdateres til å nevne både `_direction`
  og `_horizon` som engine-injiserte kontekst-keys.

### 4.2 Alt 2 — Per-horisont driver-instans i YAML

YAML får tre driver-entries per kilde, én per horisont, med ulike
navn (eks. `tff_positioning_makro`, `tff_positioning_swing`,
`tff_positioning_scalp`). Hver driver implementerer én horisont
hardkodet.

**Pro:**

- Selv-dokumenterende: navnet sier hvilken horisont.
- Ingen engine-endring overhodet.
- Horisont er statisk kjent ved YAML-tid (ingen runtime-disambiguation
  i driver-koden).

**Con:**

- Driver-registry tredobles for hver multi-horisont-kilde. ~13 nye
  fetchere × ~3 horisonter = potensielt ~30-40 nye driver-navn.
- Feature-engineering dupliseres tre ganger eller tvinger fram en
  privat helper i samme fil — komplikasjon Alt 1 unngår.
- YAML blir lengre og mer feilutsatt: hver familie må peke på riktig
  horisont-variant per instrument.
- Forhindrer ikke det Alt 1 forhindrer: engine-laget er fortsatt blind
  for horisont, så nye scoring-features (f.eks. en horisont-vekting på
  driver-output) kan ikke implementeres uten engine-endring senere.

### 4.3 Alt 3 — Endret driver-signatur

Driver-kontrakten utvides til
`(store, instrument, params, horizon: str | None) -> float`.

**Pro:**

- Selv-dokumenterende på signaturen.
- Eliminerer den implisitte naturen til Alt 1.

**Con:**

- Bryter alle ~22 eksisterende drivere + alle eksisterende driver-
  tester (~150 test-cases per ADR-006). Sub-fase 12.7 ville bruke en
  hel session bare på pro-forma signature-endringer.
- ADR-006 eksplisitt forkastet samme mønster (Alt A i ADR-006) for
  `_direction` med samme begrunnelse.
- STATE invariants låser driver-kontrakten "fra Fase 1" — endring
  krever en egen ADR for selve kontrakts-bruddet og en migrerings-
  syklus.

### 4.4 Sammenligning

| Kriterium | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|
| Engine-endring | ~5 linjer | 0 | ~5 linjer |
| Driver-signatur uendret | ✅ | ✅ | ❌ |
| Driver-registry-vekst per ny multi-horisont-kilde | 1 | 3 | 1 |
| YAML-vekst per ny multi-horisont-kilde | 1 entry | 3 entries | 1 entry |
| Feature-engineering dupliseres | nei | ja (eller via privat helper) | nei |
| Konsistent med ADR-006 (`_direction`) | ✅ | ❌ | ❌ |
| Bryter eksisterende tester | nei | nei | ja (~150) |
| Selv-dokumenterende | ⚠ via konvensjon | ✅ | ✅ |
| Egnet for både financial og agri | ✅ | ⚠ må duplisere agri-side | ✅ |

**Valg: Alt 1.** Begrunnelse:

1. ADR-006 etablerte allerede mønstret for engine-injisert kontekst;
   `_horizon` følger naturlig.
2. Sub-fase 12.7 har 16-24 sessioner foran seg (R1 → D3). En
   architecture-decision som bryter 22 drivere før vi engang har
   begynt på data-utvidelsen er feil prioritering.
3. Sub-fase 12.6 sin harvest-pipeline er live nå (Alt γ). Bit-
   identisk score-output er en hard forutsetning for at harvested
   data fra før-12.7 kan kobles til post-12.7 score-versjoner. Alt 1
   gir denne garantien gratis for ~95% av drivere; Alt 2 gir den for
   alle (ingen endring), men til prisen av registry-vekst og duplikat-
   feature-kode senere.

Alt 1 låses i ADR-010.

## 5. Implementasjons-skisse for R1

### 5.1 Engine-patch

I `_score_families` (engine.py:345-401), utvid `params_with_dir` til
også å bære horisont:

    # Pseudokode-skisse — eksakt patch i engine-commit
    params_with_dir = {
        **driver_spec.params,
        "_direction": direction.value,
        "_horizon": horizon,  # NY — None for agri
    }

`_score_families` må derfor ta `horizon: str | None` som parameter.
Kallene fra `_score_financial` (har horizon-streng) og `_score_agri`
(sender None) oppdateres tilsvarende. Ingen signatur-endring på
`Engine.score()` selv — den tar allerede `horizon`-arg.

### 5.2 Snapshot-baseline

PRE-patch: kjør `scripts/snapshot_score_baseline.py` (ny skripte i
denne session) som itererer alle YAML-er, kjører `score_instrument`
for hver kombinasjon, og dumper `(instrument, horizon, direction) →
{score, grade, family_scores}` til
`tests/snapshot/expected/score_baseline.json`. Dette er ankeret.

POST-patch: kjør samme skripte mot ny code-path og diff mot
expected. **Må gi 0 forskjeller** — det er R1s acceptance-kriterium.

R3 og R4 vil re-kjøre samme diff etter hver driver-refactor og
familie-batch. Eventuelle forskjeller må være eksplisitt
introduserte og dokumenterte (eks. ny driver lagt til, en families
sammensetning endret).

### 5.3 Micro-test

`tests/unit/test_engine_horizon_propagation.py` dekker to
påstander:

- **Test A** (engine setter key korrekt): registrer en mock-driver
  som returnerer `params.get("_horizon")` som streng. Kjør Engine
  mot en mini-FinancialRules med horizon="SWING" og en mini-
  AgriRules; verifiser at mock-driver så `"SWING"` for financial og
  `None` for agri.
- **Test B** (eksisterende driver bit-identisk): registrer en mock-
  driver som returnerer en konstant uavhengig av params. Verifiser
  at score er bit-identisk om `_horizon` er satt eller ikke. Det er
  denne testen som er den faktiske bakoverkompatibilitet-garantien.

## 6. Følge-leveranser for sub-fase 12.7

R2 (neste session) leverer `docs/driver_horizon_pattern.md`:
feature-konvensjon (pct_12m, delta_5d_z, extreme_flag,
approaching_extreme, surprise_z, time_to_release_min,
post_release_drift_3d, extreme_contrarian_score), per-horisont test-
strategi (snapshot-uendret, monotonisitet, regime-shift), sesong-
driver-mønster (kalender-aware, ingen ny polarity), og to ende-til-
ende-eksempler.

R3 refactorer 3 referanse-drivere: `positioning_mm_pct`,
`real_yield`, `crop_progress_stage`. Hver produserer flere features
internt og velger via `params["_horizon"]`.

R4 batch-migrerer alle drivere i 7 commits (én per familie-gruppe).
Snapshot-tester må forbli grønne for hver batch.

## 7. Avgrensninger / out-of-scope for R1

- Ingen driver-endringer i R1. Alle eksisterende drivere ignorerer
  `_horizon` per default. R3 åpner refactor-arbeidet.
- Ingen YAML-endringer. Ingen `polarity`-flagg eller terskel-
  endringer. Sub-fase 12.7 er additiv på engine-siden og bevarer
  hele dagens score-pipeline.
- Backfill-policy (ADR-011) er en separat ADR — den definerer
  retningslinjer for engangs-historikk-skripts som Spor D vil
  produsere, men selv ingen kode i R1.
- ADR-012 (deprecation-policy) og ADR-013 (failure-mode-policy) er
  bevisst utsatt (Alt Z, PLAN § 19.3). Håndteres reaktivt per
  fetcher i D-fasene.

## 8. Referanser

- PLAN § 19 — sub-fase 12.7 master-plan
- ADR-006 — direction-asymmetric scoring (presedens for engine-
  injisert kontekst-key)
- ADR-010 — horisont-bevisst driver-pattern (Alt 1, låses her)
- ADR-011 — backfill-policy for engangs-historikk-skripts
- `src/bedrock/engine/engine.py:345-401` — `_score_families`
- `src/bedrock/engine/drivers/__init__.py` — driver-kontrakt
- `src/bedrock/orchestrator/score.py` — `score_instrument`
- `tests/unit/test_engine_direction_polarity.py` — testmønster for
  ADR-006 som R1 speiler
