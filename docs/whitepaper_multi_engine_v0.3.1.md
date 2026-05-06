# Whitepaper: Multi-Engine Trading Architecture

**Status:** Utkast v0.3.1 — for ekstern peer review og diskusjon
**Dato:** 2026-05-06
**Forfatter:** Bedrock-teamet: operatør + AI-assistanse
**Målgruppe:** kvantanalytikere, softwarearkitekter, systemutviklere og AI-assistenter

> **Formål:** Dette dokumentet beskriver en foreslått overgang fra én monolittisk scoring-arkitektur til en multi-engine-arkitektur der hvert instrument får en dedikert engine, egen markedslogikk, egen validering og eksplisitt sannsynlighetskalibrert signal-output.

---

## Endringer fra v0.3

Tre presisjoner er lagt inn etter intern review. Hver av dem adresserer en konkret risiko for at sugar-engine-v1 ville produsert backtest-edge som ikke replikeres live:

1. **§4.5.1 — Vol-justert Sharpe-terskel.** Generisk Sharpe ≥ 1.0 er for lavt for soft commodities. Ny tabell skiller etter instrument-vol og transaksjonskostnad-impact.
2. **Appendix A, S2 — Trend-filter på COT-mean-reversion.** Den klassiske dødsfellen ved fade-the-crowd er entry på en posisjon som ennå ikke har toppet. Trigger krever nå at z-score-endringen er flat eller negativ, ikke bare ekstrem absolutt-verdi.
3. **Appendix A, S5 — Eksplisitt regresjons-retning og spread-direksjon.** Engle–Granger er asymmetrisk. v0.3 spesifiserte ikke avhengig variabel eller hvilken sides spread-leg som er long/short. Dette er nå formalisert.

## Endringer fra v0.2

v0.2 var for vag på de punktene som avgjør om engine-arkitekturen produserer realistiske trading-setups eller bare pene backtest-resultater. v0.3 konkretiserer derfor fire områder:

1. **Ny §1.4 — Forward-pricing-løsning.** §1.2.5 identifiserte forward-pricing-mismatchen, men foreslo ingen operasjonell løsning. Dette er nå spesifisert.
2. **Ny §4.5 — Statistisk realisme-terskler.** Tersklene for overgang fra Fase 2 → shadow-mode → live er kvantifisert. Dette gir Q6 et empirisk rammeverk.
3. **Ny Appendix A — Setup-katalog for sukker.** Q3s generiske setup-arketyper er erstattet med fem konkrete kandidat-setups med trigger, entry, stop, target, N-krav og invalideringsregler.
4. **Ny Appendix B — Conviction-kalibreringsprotokoll.** Q7 om risk-arbitrasje er ikke meningsfull uten en definert conviction-skala. Den er nå formalisert.

**Resterende åpne spørsmål:** Q1, Q4, Q5, Q8, Q9 og Q10 er fortsatt åpne for review. Q2 og Q3 er innsnevret, men ikke lukket.

---

# 1. Bakgrunn

## 1.1 Dagens system: Bedrock

**Bedrock** er et produksjonssystem som har vært utviklet og kjørt i omtrent 12 måneder. Systemet dekker cirka 22 instrumenter og bruker 99 drivere fordelt på syv additive driverfamilier.

Dagens system består av:

* daglig fetch-pipeline for cirka 34 datakilder, inkludert USDA, NOAA, FRED, COT, værdata og andre makro-/fundamentalkilder
* backtest-rammeverk med DSR-validering
* cTrader-bot med risk-management
* 12–14 års historikk per instrument
* scoring-modell som produserer BUY/SELL-signaler basert på additive driverfamilier

## 1.2 Hva som ikke virker

Problemene under er identifisert i `docs/engine_fundamental_review_2026-05-06.md`.

1. **Per-direction-uavhengig scoring.** 16 instrumenter har både BUY og SELL over publish-floor samtidig.
2. **Multi-horizon parallel scoring.** 11 instrumenter publiserer samme retning på flere horisonter med duplisert entry-level. Dette skaper risiko for trippel-eksponering.
3. **7-familie additive scoring mangler ekte ortogonalitetsverifikasjon.** Effective k ser ut til å være cirka 3–4 dimensjoner, ikke 7. Dette er verifisert via PCA på driver-korrelasjonsmatrisen, se `docs/pca_driver_analysis_2026-04-22.md`.
4. **Sirkulær score-kalibrering.** Drivere er tunet mot publish-floor, samtidig som publish-floor er tunet mot driverne.
5. **Forward-pricing-mismatch.** Sukker handles og prises ofte mot forward-kontrakter, mens Bedrock primært leser current/historical spot-lignende serier. Foreslått løsning er beskrevet i §1.4.
6. **Setup-builder er kontekstblind.** Samme entry-level kan genereres på tvers av ulike horisonter.
7. **Manuelle familievekter drifter over tid.** Vektene mangler eksplisitt governance, rekalibreringsregler og degraderingslogikk.

## 1.3 Rotårsak

Rotårsaken er at én scoring-modell, én aggregator og ett felles driversett ikke generaliserer godt nok over 22 instrumenter på tvers av fem asset-klasser.

Hver instrumenttype har egen markedslogikk:

* sukker prises gjennom forward-cycle og fysisk tilbud/etterspørsel
* EURUSD reagerer på makro, rate-differanser og intrauke-flow
* Bitcoin handles 24/7 og påvirkes sterkt av sentiment, likviditet og regime
* korn, softs, energi og metaller har egne sesong-, lager- og logistikkstrukturer

Disse markedene bør ikke presses inn i samme generiske scoring-modell.

## 1.4 Forward-pricing-løsning

§1.2.5 identifiserte at sukker ofte prises 6–12 måneder forward, mens Bedrock leser current/historical serier. Konsekvensen er at backtesten kan validere mot en prisserie som ikke tilsvarer den eksponeringen traderen faktisk handler live.

Hvis dette ikke løses før `sugar-engine-v1` bygges, kan engine produsere setups som ser statistisk valide ut i backtest, men som ikke lar seg replikere i live trading.

### Løsningskandidater

| Alternativ | Tilnærming                                                                                           | Kost / kompleksitet | Datakvalitet                           |
| ---------- | ---------------------------------------------------------------------------------------------------- | ------------------: | -------------------------------------- |
| **A**      | Kontinuerlig forward-serie fra ICE #11-kontrakter, for eksempel H/K/N/V, med dokumentert rull-metode |                 Lav | Høy — handlbar prisserie               |
| **B**      | Cost-of-carry-syntese: spot + frakt + storage + finansiering                                         |             Middels | Middels — modellrisiko i carry-input   |
| **C**      | Eksplisitt forward-data fra leverandører som Czarnikow / Green Pool                                  |     Middels til høy | Høy — avhenger av leverandør og lisens |

### Anbefaling for v0.3

Anbefalt løsning er **A: kontinuerlig forward-serie fra ICE #11-kontrakter**.

Begrunnelse:

* data finnes allerede i ICE-feed
* rull-metoden kan dokumenteres og reproduseres
* backtesten kan kjøres mot en faktisk handlbar prisserie
* ingen ny datakostnad introduseres i første fase
* alternativ B og C kan senere brukes som krysstesting-kilder

### Implementeringsspesifikasjon for shared library

Forward-curve-modulen i shared library bør støtte:

* kontinuerlige serier per kontraktrolle:

  * `front_month`
  * `M+1`
  * `M+3`
  * `M+6`
* konfigurerbar rull-trigger, default **5 handelsdager før First Notice Day**
* justeringsmetode: **proportional back-adjustment**, ikke difference back-adjustment
* eksplisitt engine-valg av hvilken serie som brukes til scoring
* default for sukker: `M+6`, fordi dette representerer en mid-cycle forward-serie som er mer relevant for mange fundamentale sukkerposisjoner enn front-month alene
* backtest som skiller mellom:

  * **score-serie:** for eksempel `M+6`
  * **execution-serie:** for eksempel `front_month`

### Konsekvens for andre asset-klasser

Samme forward-curve-bibliotek bør senere kunne brukes for cocoa, kaffe, hvete, mais og andre futures-markeder der forward-struktur er sentral. Spot-markeder som EURUSD og BTCUSD påvirkes ikke av denne modulen.

---

# 2. Design-visjon

## 2.1 Én dedikert engine per instrument

Hovedprinsippet er:

> Ett instrument bør ha ett dedikert program med egen markedslogikk, egne setups, egen validering og egen sannsynlighetskalibrering.

Hver engine skal ha:

* egen filosofi: mean reversion, momentum, event anticipation, spread-arbitrage eller annet
* egne kriterier: setup-type, drivere, vekter og invalideringsregler
* egen tidshorisont: for eksempel 7 dager, 30 dager, 90 dager eller 365 dager
* egen validering: backtest, out-of-sample, shadow-mode og live-monitorering

## 2.2 Felles bot

Den felles boten skal:

* motta signaler fra alle engines
* validere signalformat
* utføre risk-arbitrasje på porteføljenivå
* eksekvere handler i cTrader
* returnere faktiske outcomes til engine for senere analyse og kalibrering

Botens rolle skal være passiv og regelstyrt. Den skal ikke ha skjult markedslogikk eller egne meninger om hvilken engine som «har rett». Den skal bare håndtere risiko, eksekvering og feedback.

## 2.3 Felles bibliotek

Shared library skal inneholde det som faktisk bør være felles:

* DataStore
* fetchers
* secrets-management
* backtest-rammeverk
* forward-curve-modul
* conviction-kalibrering
* signal-protokoll
* felles datavalidering

Det som er instrumentspesifikt, skal ikke flyttes inn i shared library. Sukkerlogikk skal ligge i sugar-engine, ikke i en generell commodity-engine.

## 2.4 Setup-først, ikke score-først

Den nye arkitekturen skal være setup-først.

Dette betyr ikke at scoring forsvinner. Det betyr at scoring bare brukes etter at en konkret setup-kandidat er identifisert.

**Bedrock-modellen:**

> Beregn score kontinuerlig for alle markeder → finn et nivå som passer scoren → publiser signal.

**Foreslått modell:**

> Identifiser konkret setup → valider setup-spesifikke betingelser → beregn conviction → publiser signal med både `setup_id` og kalibrert sannsynlighet.

Output til bot skal derfor ikke være en grade som A+/A/B/C. Output skal være:

* instrument
* setup-id
* retning
* entry
* stop
* target
* holding-window
* conviction = kalibrert sannsynlighet for at target treffes før stop

---

# 3. Åpne design-spørsmål

Hvert spørsmål under har flere mulige svar. Reviewer-input ønskes. Q3 og Q7 er innsnevret gjennom Appendix A og B, men ikke endelig lukket.

---

## Q1: Repo-struktur

| Alternativ                                                   | Fordeler                                                                     | Ulemper                                                                      |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **A. Eget GitHub-repo per engine**                           | Full isolering, uavhengige releases, lav risiko for cross-contamination      | Mer overhead, CI per repo, cross-cutting endringer krever koordinert release |
| **B. Monorepo med strengt isolerte subdirectories**          | Enklere refaktorering, én CI, lettere å endre signal-protokoll og shared API | Risiko for at fellesmodell sniker seg inn hvis disiplinen glipper            |
| **C. Hybrid: shared-lib repo + engine-repos som submodules** | Strukturert og versjonert shared library                                     | Submodule-friksjon, mer komplekst for én operatør                            |

**Operatør-preferanse:** A.

**Motargument som bør vurderes:** For én utvikler kan cross-cutting endringer i Alt A gi unødvendig friksjon. Alt B, med streng mappeisolering og lint-håndhevet cross-import-forbud, kan gi 90 % av isoleringen med vesentlig lavere overhead.

**Spørsmål til reviewer:** Bør operatør-preferansen for repo-per-engine overstyres av praktiske hensyn før code-start?

---

## Q2: Scoring-system og filosofi

Operatørens posisjon er foreløpig:

> Det er ikke avklart om dagens scoring-system bør beholdes. Først må vi finne ut hva som er realistisk med dataen vi faktisk har.

Dagens Bedrock-modell bruker:

> 99 drivere → 7 driverfamilier → additiv sum → grade A+/A/B/C → publish-floor.

Denne modellen har skapt kontradiksjoner, per-direction konflikter og falsk ortogonalitet.

### Alternative tilnærminger

| Tilnærming                                          | Kjerneidé                                                                                    | Når passer det?                                                                                |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **A. Fortsette med scoring, men forenklet**         | 5–7 ortogonale drivere per engine, ingen familier, flat score og VIF-sjekk                   | Hvis additiv modell fortsatt vurderes som prinsippielt riktig                                  |
| **B. Rule-based decision tree**                     | Eksplisitte if/then-regler                                                                   | Hvis trading-thesis er klar og kan kodifiseres                                                 |
| **C. Probabilistic ensemble**                       | Hver driver returnerer sannsynlighetsbidrag, aggregert via Bayesiansk eller logistisk modell | Mer prinsipielt, men krever bedre kalibrering og nok data                                      |
| **D. ML-modell**                                    | XGBoost, LSTM, Transformer eller annen modell trent på historiske utfall                     | Krever mye data og streng overfit-kontroll                                                     |
| **E. Hybrid: setup-finder + LLM-confluence-scorer** | Teknisk setup-detektor + LLM som leser kontekst, nyheter, COT og fundamentale data           | Eksperimentelt; kan fange kontekst, men må ha sterk kontroll mot hallucination og inkonsistens |
| **F. Manuell trader-confluence-checker**            | Engine flagger kandidater, operatør tar beslutning                                           | Trygt i læringsfasen, men skalerer dårlig                                                      |

### Felles krav uansett modellvalg

Uansett valg av A–F må engine returnere:

> **kalibrert sannsynlighet mellom 0.50 og 0.95**, ikke bokstavgrade.

Dette er nødvendig for at botens risk-arbitrasje skal kunne fungere på tvers av engines.

**Spørsmål til reviewer:** Hvilken tilnærming er mest realistisk for sukker, gitt cirka 12–14 års daglig prisdata, COT, UNICA bi-uke, Comtrade månedlig, ANP daglig, ENSO månedlig og WASDE månedlig?

---

## Q3: Setup-detection-filosofi

Dagens Bedrock-modell er score-først. v0.3 foreslår setup-først.

Appendix A definerer fem konkrete kandidat-setups for sukker:

1. UNICA-surprise momentum
2. COT-ekstrem mean reversion
3. white-premium-arbitrage
4. frost-event asymmetri
5. BRL-#11 kointegrasjonsspread

Hver setup spesifiserer:

* trigger
* entry
* stop
* target
* holding-window
* minimum N for backtest
* invalideringsregler

Dette gjør setup-først til en operasjonell kontrakt, ikke bare en filosofisk preferanse.

**Spørsmål til reviewer:**

* Er kandidatlisten i Appendix A dekkende, eller mangler det åpenbare sukker-setups?
* Bør setups rangeres etter forventet edge før Fase 2, eller bør alle fem testes parallelt med eksplisitt multiple-testing-justering?

---

## Q4: Signal-bus og kommunikasjon mellom engine og bot

| Alternativ                      | Beskrivelse                                                                               | Når passer det?                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **A. Filsystem med JSON-filer** | Engines skriver til `signals/inbox/<id>.json`, bot konsumerer og flytter til `processed/` | MVP, single-host, lavt volum                                      |
| **B. SQLite signals-tabell**    | Felles SQLite-database med queue-mønster                                                  | Mer robust, ACID, lett å query historikk                          |
| **C. Redis pub/sub**            | Engines publiserer, bot subscriber                                                        | Real-time, men krever egen tjeneste                               |
| **D. Kafka / NATS**             | Event-streaming på enterprise-nivå                                                        | Overkill for én bruker i første fase                              |
| **E. ArcticDB**                 | Tidsserieorientert lagring                                                                | God for historikk, men mindre naturlig som live signal queue      |
| **F. HTTP REST API**            | Bot eksponerer `/submit_signal`                                                           | Standard og lett å monitorere, men krever at boten alltid er oppe |

**Default for v0.3:** A for første 1–3 engines. Migrer til B hvis signalvolum overstiger cirka 50 signaler per dag, eller hvis historikk-query blir hyppig.

**Viktig implementeringskrav hvis filsystem velges:**

* skriv først til midlertidig fil
* flush/sync
* atomic rename til `inbox/`
* unik signal-id
* idempotent consumer
* processed/error-mapper

Dette reduserer risikoen for delvis skrevne filer og race conditions.

**Spørsmål til reviewer:** Er filsystem godt nok for én bruker med 1–3 engines, eller bør SQLite velges fra start for å unngå subtile queue-bugs?

---

## Q5: Storage-arkitektur for tidsseriedata

Dagens Bedrock bruker SQLite. Databasen er omtrent 213 MB og inneholder 12+ års daglig data.

| System                     | Styrke                                         | Svakhet                                                                                    |
| -------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **SQLite**                 | Enkelt, filbasert, ingen server                | Kan bli begrensende ved store datamengder, tung parallell skriving eller høyfrekvente data |
| **ArcticDB**               | Pandas-vennlig, tidsserieorientert, komprimert | Krever LMDB eller S3-backend, mer læringskurve                                             |
| **DuckDB**                 | Sterk analytisk OLAP, rask på aggregater       | Ikke spesialisert for live time-series ingest                                              |
| **InfluxDB / TimescaleDB** | Tidsserie-spesialisert                         | Serverarkitektur og mer driftsoverhead                                                     |
| **Parquet + Polars**       | Rask kolonne-scan, enkelt filformat            | Mindre praktisk for mange små append-operasjoner                                           |

**Default for v0.3:** Behold SQLite til Bedrock-DB nærmer seg 5 GB, eller til 5+ engines er live. 213 MB er ikke i nærheten av å være en teknisk flaskehals.

**Spørsmål til reviewer:** Finnes det scenarioer, for eksempel minuttsdata for BTC eller hyppige multi-instrument cross-correlation queries, der SQLite blir en flaskehals tidligere enn forventet?

---

## Q6: Engine-filosofi og utviklingsprosess

Operatørens nåværende posisjon:

> Engine-filosofi må utvikles per instrument. Den kan ikke bestemmes generisk på forhånd.

Foreslått prosess:

1. **Data-eksplorering:** 1–2 uker per instrument.
2. **Hypoteser:** formuler 1–3 konkrete trading-thesis-kandidater.
3. **Backtest-validering:** test hypotesene mot §4.5-tersklene.
4. **Setup-utvalg:** velg setup-typer basert på validert thesis.
5. **Driver-utvalg:** velg 5–7 mest mulig ortogonale drivere, med VIF < 5 som eksplisitt kontroll.
6. **Kode:** implementer engine.
7. **Shadow-mode:** varighet bestemmes av instrumentets syklus og minimum trade count.
8. **Live cut-over:** start med 50 % normal risk i tre måneder, deretter vurder full risk.

For sukker foreslås minimum **8 måneder shadow-mode**, fordi én full crush-sesong bør observeres før live cut-over.

---

## Q7: Risk-arbitrasje på bot-side

Eksempel: tre engines sender signal samtidig.

| Engine | Signal | Conviction | Beregnet risk ved `max_per_trade_risk = 1.0 %` |
| ------ | -----: | ---------: | ---------------------------------------------: |
| Sugar  |   SELL |       0.78 |                                         0.56 % |
| Wheat  |    BUY |       0.65 |                                         0.30 % |
| Coffee |   SELL |       0.55 |                                         0.10 % |

Formel fra Appendix B:

```text
risk_pct = (conviction − 0.50) × 2 × max_per_trade_risk
```

Sum requested risk er 0.96 %, som er under et hypotetisk daglig budsjett på 2.0 %. Alle signaler får derfor full størrelse.

Hvis samlet ønsket risiko overstiger budsjettet, vurderes følgende metoder:

| Strategi                     | Beskrivelse                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------ |
| **A. Pro-rata haircut**      | Skaler alle signaler ned med samme faktor til samlet risk er innenfor budsjett |
| **B. Conviction-prioritert** | Høyeste conviction får full størrelse først, deretter neste                    |
| **C. Track-record-vektet**   | Engine med best live-historikk får prioritet                                   |
| **D. Sektor-cap**            | For eksempel maks 1.5 % samlet risk på soft commodities                        |
| **E. Korrelasjonsjustert**   | Reduser posisjoner som er sterkt korrelert med eksisterende eksponering        |

**Default for v0.3:** A + D + E.

Track-record-vekting innføres ikke før engines har minst 12 måneder live-historikk. Før det er faren stor for at man vektlegger støy.

**Spørsmål til reviewer:** Bør porteføljerisiko håndteres med en enkel regelpakke i starten, eller bør formelle metoder som Markowitz, Black-Litterman eller CVaR-optimalisering vurderes tidlig?

---

## Q8: Outcome-feedback-loop

Når et signal blir tatt og eksekvert, skal bot returnere følgende til engine:

| Felt                               | Type          | Bruk                                                  |
| ---------------------------------- | ------------- | ----------------------------------------------------- |
| Faktisk fill-pris                  | float         | Sammenlignes med planned entry                        |
| Slippage                           | float         | Brukes til å evaluere setup-realismen                 |
| Holdetid                           | duration      | Brukes til å evaluere horisont-target                 |
| MFE / MAE                          | float / float | Brukes til å evaluere stop, target og trailing-regler |
| Eksisterende korrelerte posisjoner | list          | Brukes til senere risk- og signalanalyse              |
| Calibration outcome                | bool          | Brukes til Brier-score: target før stop eller ikke    |

### Online vs offline learning

| Tilnærming           | Risiko                                                                   |
| -------------------- | ------------------------------------------------------------------------ |
| **Online learning**  | Kan overreagere på enkeltutfall og feilaktig tolke støy som regime-shift |
| **Offline learning** | Reagerer tregere på ekte regime-endring                                  |

**Default for v0.3:** Offline månedlig rekalibrering de første 12 månedene per engine.

Online learning innføres bare hvis engine har vist stabil Brier-score og reliability over minst 12 måneder live.

---

## Q9: Bedrock-pensjonering

Operatørens nåværende posisjon:

> Bedrock beholdes foreløpig. Pensjonering tas per instrument etter hvert.

| Strategi                                                          | Beskrivelse                                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **A. Bedrock som permanent research-mirror**                      | Bedrock fortsetter å produsere research-signaler som referanse                             |
| **B. Per-instrument pensjonering**                                | Når sugar-engine er validert, skrus sukker av i Bedrock, mens øvrige instrumenter beholdes |
| **C. Total pensjonering etter portering av alle 22 instrumenter** | 2–3 års horisont, krever nye engines for alle instrumenter                                 |
| **D. Bedrock som backtest-laboratorium**                          | Brukes til å teste nye drivere før de eventuelt flyttes inn i dedikerte engines            |

**Spørsmål til reviewer:** Har Bedrock verdi som parallel research-mirror, eller vil signal-divergens mellom Bedrock og v3-engines hovedsakelig skape støy?

---

## Q10: Versjonering og backwards compatibility

Hvis `sugar-v1` fungerer i seks måneder, og `sugar-v2` senere bygges med ny filosofi, må overgang håndteres eksplisitt.

| Strategi                       | Beskrivelse                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------ |
| **A. Hard cut-over**           | v1 stoppes, v2 tar over                                                                          |
| **B. Parallel-kjøring / A/B**  | v1 og v2 sender signaler parallelt; bot velger basert på conviction, track-record og risk-regler |
| **C. Versjonert i samme repo** | Repo inneholder både `v1.py` og `v2.py`; YAML bestemmer aktiv versjon                            |
| **D. Eget repo per versjon**   | Separate repos, for eksempel `sugar-engine-v1` og `sugar-engine-v2`                              |

**Spørsmål til reviewer:** Hva er beste praksis for trading-strategi-versjonering, og hvor lang parallel-kjøring trengs før v2 kan erstatte v1?

---

# 4. Foreløpig konsensus

Disse punktene er stabile nok til å brukes som designgrunnlag, men kan fortsatt utfordres av reviewere:

* **Én engine per instrument**
* **Bot er passiv risk-arbiter**
* **Felles bot mottar signaler fra alle engines**
* **Shared library for DataStore, fetchers, secrets, forward-curve, signal-protokoll og conviction-kalibrering**
* **Strikt sekvensiell skalering: ett instrument valideres før neste prioriteres**
* **Bedrock-current beholdes parallelt inntil videre**
* **Setup-først over score-først**
* **Outcome-feedback fra bot til engine**
* **Offline månedlig rekalibrering første 12 måneder per engine**
* **Conviction = kalibrert P(target før stop), 0.50–0.95**
* **Forward-curve-replikasjon for sukker og andre cycle-priced commodities**

---

# 4.5 Statistisk realisme-terskler

Disse tersklene gjelder uansett scoring-tilnærming og setup-type. De definerer når en setup kan gå fra backtest til shadow-mode og videre til live.

## 4.5.1 Fra Fase 2 til shadow-mode

En setup-type kvalifiserer ikke for shadow-mode med mindre alle kravene under er oppfylt:

| Krav                  |                                                       Terskel | Begrunnelse                                                            |
| --------------------- | ------------------------------------------------------------: | ---------------------------------------------------------------------- |
| Minimum OOS trades    |                                                          ≥ 30 | Under dette er Sharpe-estimatet svært ustabilt                         |
| Sharpe OOS            |                                  vol-justert, se tabell under | Annualisert, etter slippage og spread-modell                           |
| Calmar OOS            |                                                         ≥ 0.5 | Beskytter mot strategier med høy snittavkastning, men stor hale-risiko |
| Deflated Sharpe Ratio | > 0.95-percentil etter justering for antall testede hypoteser | Reduserer multiple-testing-bias                                        |
| Max drawdown          |                                 ≤ 2 × annualisert volatilitet | Flagges hvis drawdown er uforholdsmessig stor mot volatilitet          |
| Trade frequency       |                                                 ≥ 8 events/år | Lavere frekvens gjør live regime-detektering svært vanskelig           |

### Vol-justert Sharpe-terskel

Generisk Sharpe ≥ 1.0 er for lavt for høyvolatilitets-instrumenter der spread og slippage spiser en større andel av brutto-edge. Tersklene under reflekterer at samme nominelle Sharpe gir veldig forskjellig nettopålitelighet avhengig av instrument-vol og transaksjonskostnad-impact.

| Instrument-tier               | Eksempler                                  | Annualisert vol | Sharpe-krav | Begrunnelse                                                                                              |
| ----------------------------- | ------------------------------------------ | --------------: | ----------: | -------------------------------------------------------------------------------------------------------- |
| **Lav vol / lav spread**      | EURUSD, USDJPY, store G10                  |          5–10 % |       ≥ 1.0 | Spread og slippage er små relativt til annualisert avkastning                                            |
| **Middels vol**               | Gull, Brent, S&P 500                       |         15–20 % |       ≥ 1.2 | Spread og slippage ikke trivielt, men håndterbart                                                        |
| **Høy vol / softs**           | Sukker, kaffe, kakao, bomull               |         25–35 % |       ≥ 1.5 | Wide spreads på CFD; sesongstrukturer skaper konsentrert PnL; backtest-edge svekkes mer av eksekvering   |
| **Veldig høy vol / 24/7**     | BTC, ETH, andre likvide krypto             |         50–80 % |       ≥ 1.8 | Funding-kost, gap-risiko, regime-shifts gjør backtest-til-live-degradering verst                         |
| **Kalkulert Sharpe-haircut**  | —                                          |               — | Backtest-Sharpe må overstige tier-kravet **etter** at slippage-modell og kontraktspesifikk spread er innbakt | — |

**For sugar-engine spesifikt: backtest-Sharpe må være ≥ 1.5 etter at Skilling-spread (typisk 4–6 pips på #11) og slippage-antakelser er modellert.** Hvis backtest viser Sharpe 1.2 brutto men 0.9 netto, kvalifiserer setup ikke for shadow.

## 4.5.2 Fra shadow-mode til live

| Krav                             |                                                             Terskel |
| -------------------------------- | ------------------------------------------------------------------: |
| Shadow-varighet                  |              ≥ 6 måneder eller ≥ 1 full sesongsyklus per instrument |
| For sukker                       |                                  minimum 8 måneder / 1 crush-sesong |
| Shadow Sharpe-avvik mot backtest |                        innenfor ±0.3, ellers regime-breakdown-flagg |
| Conviction Brier-score           |                                                              < 0.20 |
| Reliability-diagram              | maks 0.05 avvik fra perfekt kalibrering i enhver probability bucket |

## 4.5.3 Hvis terskler ikke møtes

* **Backtest fail:** setup-type kasseres. Engine går tilbake til hypothesis-formulering.
* **Shadow fail:** engine pauses. Operatør gjør årsaksanalyse og re-baseliner shadow-window.
* **Calibration fail:** engine pauses. Conviction-modell re-fittes, og ny shadow-periode på tre måneder kreves før live-resume.

## 4.5.4 Multiple-testing-disiplin

Operatør skal logge antall hypoteser som testes gjennom hele engine-utviklingen:

```text
antall hypoteser = setup-typer × driver-kombinasjoner × horisonter
```

Eksempel:

```text
5 setup-typer × 4 driver-sett × 3 horisonter = 60 hypoteser
```

Jo flere hypoteser som testes, desto strengere må DSR-kravet bli. Dette beskytter mot at systemet finner tilsynelatende edge i tilfeldig støy.

---

# 5. Forventet bygge-rekkefølge

## Fase 0: Diskusjon og design

Estimert innhold:

* whitepaper-iterasjoner med flere reviewere
* beslutninger på Q1, Q4, Q5 og Q7–Q10
* konkret arkitekturspesifikasjon basert på valgene
* review av Appendix A før første engine bygges

## Fase 1: Infrastruktur

Leveranser:

* shared library-pakkestruktur
* forward-curve-modul
* signal-protokoll v1.0
* conviction-kalibreringsbibliotek
* bot multi-engine consumer
* engine-template
* minimal CI
* logging og audit trail

## Fase 2: Sugar-engine v1

Fase 2 bør ikke starte før Fase 1 er stabil nok til at engine kan backtestes og kjøres i shadow-mode.

Leveranser:

* data-eksplorering på sukker
* filosofi-formulering
* implementering av fem setup-kandidater fra Appendix A
* backtest av hver setup mot §4.5-terskler (inkludert vol-justert Sharpe ≥ 1.5 for sukker)
* multiple-testing-justert DSR
* valg av topp 1–2 setups som kvalifiserer
* forward-curve-validering mot både M+6 og front-month
* minimum 8 måneder shadow-mode
* live cut-over med 50 % risk i tre måneder

## Fase 3+: Wheat, Coffee og andre engines

Hver ny engine skal ha:

* egen data-eksplorering
* egen markedsfilosofi
* egne setups
* egen kalibrering
* ingen gjenbruk av sukkervekter

Forward-curve-modulen kan gjenbrukes for futures-markeder der den er relevant.

---

# 6. Spørsmål til peer reviewere

## A. Filosofiske spørsmål

* Er én engine per instrument riktig disiplin, eller er det overengineering?
* Er setup-først-tilnærmingen i Appendix A tilstrekkelig konkret?
* Mangler sukker-katalogen åpenbare setup-typer?
* Er 5–7 ortogonale drivere per engine riktig granularitet?

## B. Tekniske spørsmål

* Bør repo-per-engine beholdes, eller bør monorepo med strikt isolering velges?
* Er JSON-filer på filsystem trygt nok for 1–3 engines hvis atomic write brukes?
* Når blir SQLite en reell flaskehals?
* Når er online learning trygt nok til å innføres?

## C. Strategiske spørsmål

* Er 8 måneder shadow-mode for sukker riktig, eller for konservativt?
* Har Bedrock verdi som parallel research-mirror?
* Hvordan bør v1 og v2 kjøres parallelt før eventuell hard cut-over?
* Er vol-tier-Sharpe-tabellen i §4.5.1 kalibrert riktig, eller bør tersklene strammes ytterligere?

## D. Spørsmål spesifikt for sukker

* Hvilke av S1–S5 har høyest sannsynlighet for empirisk edge?
* Er `M+6` riktig default forward-serie, eller bør `M+3` eller `M+9` vurderes?
* Hva er realistisk Sharpe-target etter korrekt forward-curve-replikasjon? Er ≥ 1.5 riktig krav, eller for konservativt etter forward-curve-fix?
* Hvor mye edge ligger i betalte forward-data som ikke fanges av ICE-baserte kontinuerlige serier?

---

# 7. Hvorfor utkastet er bevisst åpent

Bedrock har gitt 12 måneder med læring fra en monolittisk arkitektur. Hovedlæringen er at for tidlig commitment til én felles scoring-modell skapte problemer som nå må reverseres.

Samtidig er det motsatte også en risiko: Hvis designet holdes for åpent, får reviewere for lite konkret å gi presis tilbakemelding på.

v0.3 forsøker derfor å skille tydelig mellom:

* **observasjoner:** det vi vet ikke fungerer i Bedrock-current
* **foreløpige beslutninger:** det vi planlegger å bygge rundt
* **åpne spørsmål:** det vi ønsker review på før kode skrives
* **operasjonelle spesifikasjoner:** de delene som må være konkrete for at backtest og shadow-mode skal være meningsfulle

Reviewer-tilbakemelding på §3 og Appendix A bør inkorporeres i v0.4 før code-start.

---

# 8. Neste steg

1. Send v0.3.1 til 2–3 eksterne analytikere og tekniske reviewere.
2. Samle tilbakemeldinger over 1–2 uker.
3. Skriv v0.4 med integrerte beslutninger.
4. Lås Fase 0/1-arkitektur.
5. Start kode først når §3 og Appendix A er tilstrekkelig avklart.

---

# Appendix A — Setup-katalog for sukker

Denne katalogen erstatter generiske setup-arketyper med fem konkrete kandidat-setups for Fase 2-backtest. Listen er ikke empirisk validert ennå. Den er laget for å være implementerbar, testbar og falsifiserbar.

---

## S1 — UNICA-surprise momentum

**Tese:** Bi-ukentlig crush-data fra UNICA inneholder ny informasjon om brasiliansk tilbud. Avvik mellom faktisk rapport og konsensus kan korrelere med 5–10 dagers prisretning.

| Felt         | Spesifikasjon                                                                                                |
| ------------ | ------------------------------------------------------------------------------------------------------------ |
| Horisont     | 5–10 handelsdager                                                                                            |
| Trigger      | UNICA bi-uke publisert; faktisk crush vs konsensus avviker med > 1 SD mot rullerende 24-rapporters historikk |
| Retning      | Positiv crush-surprise + lav sugar mix → SELL #11. Negativ crush-surprise + høy sugar mix → BUY #11          |
| Entry        | Open neste handelsdag etter publisering                                                                      |
| Gap-filter   | Hvis open gapper > 0.5 % fra forrige close, annulleres entry                                                 |
| Stop         | 1.5 × ATR(14) fra entry                                                                                      |
| Target       | 2.5 × ATR eller 7 handelsdager, det som inntreffer først                                                     |
| Minimum N    | Omtrent 50 events ønskes, men N kan bli tynn etter filtrering                                                |
| Invalidering | Manglende konsensus-data → setup skrus av                                                                    |

**Kjent feilkilde:** UNICA-data kan revideres. Surprise må beregnes på første publisering, ikke reviderte tall. Ellers introduseres look-ahead bias.

---

## S2 — COT-ekstrem mean reversion

**Tese:** Når Managed Money-posisjonering er statistisk ekstrem **og posisjons-momentumet har avtatt**, øker sannsynligheten for posisjons-unwind. Ekstrem absolutt-verdi alene er ikke tilstrekkelig — historiske rallyer har vist z-score > +3 vedlikeholdt i flere uker før topp (eks. 2008, 2010, 2016 oppganger).

| Felt                       | Spesifikasjon                                                                                                                                                                                                                                                              |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Horisont                   | 3–6 uker                                                                                                                                                                                                                                                                   |
| **Trigger (begge må holde)** | **(a)** Managed Money netto-posisjon z-score, 3-års rullerende, > +2.5 (long-ekstrem) eller < −2.5 (short-ekstrem). **(b)** **Posisjons-derivat-betingelse:** 1-ukes endring i z-score er ≤ 0 ved long-ekstrem, eller ≥ 0 ved short-ekstrem (momentum-toppen er bekreftet) |
| Retning                    | Motsatt av ekstrem Managed Money-posisjon                                                                                                                                                                                                                                  |
| Entry                      | Første handelsdag etter at både (a) og (b) er bekreftet i samme COT-rapport eller på første rapport som bekrefter (b) etter at (a) først ble truffet                                                                                                                       |
| Stop                       | Brudd over forrige 4-ukers high ved short, eller under forrige 4-ukers low ved long                                                                                                                                                                                        |
| Target                     | z-score returnerer til ±0.5, eller 30 kalenderdager                                                                                                                                                                                                                        |
| Minimum N                  | Med trend-filter forventes 4–7 events/år × 14 år ≈ 56–98 events. Lavere enn uten filter, men setupen er substansielt mindre eksponert mot fortsatt trending posisjonering                                                                                                  |
| Invalidering               | Manglende COT-publisering → setup skrus av den uken. Hvis (a) er truffet men (b) aldri bekreftes innen 8 uker → kandidat-event utløper                                                                                                                                     |

**Kjent feilkilde:** COT har publiseringslag. Posisjonering kan ha endret seg før entry. Backtest må teste sensitivitet for lag.

**Bakgrunn for trend-filter:** Den klassiske dødsfellen for COT-mean-reversion er entry på en ekstrem-posisjon som ennå ikke har toppet. 2008-rallyet hadde MM-z-score over +3 i nesten 6 uker før topp; en naiv fade-strategi ville tatt en stor SHORT-posisjon halvveis ut i rallyet og blitt stoppet ut. Trend-filteret krever at z-score-momentumet har snudd før entry tas.

---

## S3 — White-premium-arbitrage

**Tese:** White premium, definert som differansen mellom white sugar og raw sugar, reflekterer raffineringskapasitet og fysisk etterspørsel. Ekstreme verdier kan mean-reverte.

Forenklet definisjon:

```text
white_premium = #5 USD/t − (#11 c/lb × 22.046)
```

| Felt         | Spesifikasjon                                                                          |
| ------------ | -------------------------------------------------------------------------------------- |
| Horisont     | 2–4 uker                                                                               |
| Trigger      | White premium i øvre eller nedre 5-percentil over rullerende 5-års vindu               |
| Retning      | Ekstremt høy premium → long #11 / short #5. Ekstremt lav premium → short #11 / long #5 |
| Entry        | Første daglig close i ekstrem-percentil                                                |
| Stop         | Spread-bevegelse 30 USD/t mot posisjon                                                 |
| Target       | Retur til 5-års median                                                                 |
| Minimum N    | Omtrent 8–12 events/år × 14 år                                                         |
| Invalidering | Strukturelt skift i raffineringskapasitet → re-baseline vindu                          |

**Operasjonelt forbehold:** Dette er en multi-leg spread-trade. Signal-protokoll, bot og risk-modell må støtte multi-leg ordre før denne setupen kan handles live.

---

## S4 — Frost-event asymmetri

**Tese:** Frost i São Paulo / Paraná i juni–august kan skade cane-produksjon og crush. Markedet kan underprise tail-risk før faktisk skade er bekreftet.

| Felt         | Spesifikasjon                                                                         |
| ------------ | ------------------------------------------------------------------------------------- |
| Horisont     | 10–20 dager                                                                           |
| Trigger      | NOAA / INPE / ECMWF-prognose < 2 °C i relevant cane-belte, med ≥ 60 % modellkonfidens |
| Retning      | BUY #11                                                                               |
| Entry        | Ved første prognosetreff, ikke etter bekreftet frost                                  |
| Stop         | −1.5 × ATR fra entry                                                                  |
| Target       | Empirisk prisresponskurve per event-magnitude: mild, moderat eller hard               |
| Minimum N    | 0–3 events/år; lav N                                                                  |
| Invalidering | Prognose oppjusteres til > 4 °C → exit ved neste open                                 |

**Metodologisk risiko:** Lav N. S4 bør ikke stå alene som selvstendig live-strategi. Den bør i første omgang behandles som `setup_type=frost_supplement`.

---

## S5 — BRL-#11 kointegrasjonsspread

**Tese:** Brasiliansk eksportøkonomi koblet via marginal cane-produsent gjør at BRL og #11 har en stabil long-run-relasjon. Når residualet fra denne relasjonen bli statistisk ekstremt, øker sannsynligheten for mean reversion.

### Regresjons-spesifikasjon

Den statistiske relasjonen estimeres med **#11 som avhengig variabel og BRL som forklarende variabel**:

```text
ln(#11_t) = α + β · ln(BRL/USD_t) + ε_t
```

Begrunnelse: prisingsmekanismen går fra valuta til sukkerpris (svakere BRL → lavere USD-eksportkost → høyere konkurransedyktig BRL-eksportprising → press på #11), ikke motsatt. Engle–Granger er asymmetrisk; valg av avhengig variabel påvirker både β-estimat og residual-egenskaper.

Estimering:

* rullerende 1-års vindu (252 handelsdager), daglige log-priser
* OLS for β; residual ε_t er målet
* z-score av ε_t = (ε_t − rolling mean(ε)) / rolling stdev(ε)

### Spread-konstruksjon

| Tilstand                                              | Tolkning                                                  | Posisjon                                                                                |
| ----------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Residual z-score > +2** (ε høy: #11 dyr vs. BRL)    | #11 har avveket oppover fra det BRL-implisert nivå tilsier | **SHORT #11 + LONG BRL/USD**. Forventet retur: ε mean-reverter ned mot 0.                |
| **Residual z-score < −2** (ε lav: #11 billig vs. BRL) | #11 har avveket nedover fra BRL-implisert nivå            | **LONG #11 + SHORT BRL/USD**. Forventet retur: ε mean-reverter opp mot 0.                |

Hedge-ratio for BRL-leg: `β × (notional_#11_USD / spot_BRL/USD)`. Hedge-en er ikke 1:1 — den bestemmes av estimert β fra regresjonen. Engine logger β ved hver entry for senere PnL-attribusjon.

| Felt         | Spesifikasjon                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------- |
| Horisont     | 5–15 dager                                                                                          |
| Trigger      | \|residual z-score\| > 2 over rullerende 1-års vindu                                                |
| Retning      | Som i tabell over (asymmetrisk per residual-fortegn)                                                |
| Entry        | Første daglig close i ekstrem residual                                                              |
| Stop         | Residual beveger seg ytterligere 1 SD mot posisjon (entry-z + 1, eller entry-z − 1)                 |
| Target       | Residual tilbake til \|z\| < 0.5                                                                    |
| Minimum N    | Omtrent 10–20 events/år                                                                             |
| Invalidering | Rolling Engle–Granger eller Johansen-test på 1-års vindu feiler kointegrasjon (p > 0.10) → setup skrus av til ny test bekrefter relasjonen |

### Teknisk forbehold

* engine må kjøre rullerende kointegrasjonstest minst ukentlig
* hvis test feiler, må alle åpne S5-posisjoner avvikles (ikke bare nye entries blokkeres)
* Operasjonelt er dette en multi-leg trade som S3; bot og signal-protokoll må støtte koblede ordre med eksplisitt hedge-ratio

**Bakgrunn for spesifikasjon:** v0.3 spesifiserte "regresjon mellom BRL og #11" uten å definere avhengig variabel eller hvilken side som tas long/short i spreaden. Engle–Granger er ikke symmetrisk i avhengig-uavhengig-valg, og en spread-trade krever eksplisitt long/short per leg. Begge er nå spesifisert.

---

## Foreløpig setup-rangering før Fase 2

| Setup                  | Forventet edge  |     Forventet N | Operasjonell kompleksitet |
| ---------------------- | --------------- | --------------: | ------------------------- |
| S2 — COT-ekstrem       | Høy (med trend-filter) | Middels-høy | Lav-middels (krever derivat-beregning) |
| S5 — BRL-kointegrasjon | Middels         |             Høy | Middels-høy (multi-leg, rolling kointegrasjonstest) |
| S3 — White premium     | Middels-høy     |         Middels | Middels til høy           |
| S1 — UNICA-surprise    | Middels         | Lav til middels | Middels                   |
| S4 — Frost             | Asymmetrisk høy |       Svært lav | Lav                       |

**Anbefaling:** Start Fase 2 med S2 og S5. S3 er attraktiv, men krever multi-leg-arkitektur. S1 og S4 kan testes parallelt, men bør ikke forventes å kvalifisere alene uten sterk empirisk støtte.

---

# Appendix B — Conviction-kalibreringsprotokoll

## B.1 Definisjon

**Conviction = kalibrert sannsynlighet for at target treffes før stop.**

Output-skala:

```text
0.50 til 0.95
```

Tolkning:

* 0.50 = ingen edge; engine skal normalt ikke publisere
* 0.60 = svak edge
* 0.75 = moderat til sterk edge
* 0.90 = svært sterk edge
* 0.95 = maksimal publiserbar conviction

Verdier over 0.95 clamped til 0.95 for å redusere overkonfidens.

## B.2 Risk-mapping

```text
risk_pct = (conviction − 0.50) × 2 × max_per_trade_risk
```

Med `max_per_trade_risk = 1.0 %`:

| Conviction |   Risk |
| ---------: | -----: |
|       0.60 | 0.20 % |
|       0.75 | 0.50 % |
|       0.90 | 0.80 % |
|       0.95 | 0.90 % |

Merk at formelen bevisst ikke gir 1.00 % risk ved 0.95 conviction. Dette etterlater buffer mot overkonfidens og porteføljejustering.

## B.3 Kalibreringsmetode

Initial kalibrering:

* isotonic regression på rullerende 100 historiske setups
* inkluder både backtest og shadow-data, men merk datakilde eksplisitt
* test separat per setup-type hvis N tillater det

Etter live-start:

* re-fit månedlig på siste 100 closed trades
* hvis N < 100, bruk expanding window, men flagg lav datakvalitet
* ikke la én måned med støy endre live-risk direkte uten operatørgodkjenning

## B.4 Validering

| Metrikk              |                                  Terskel | Frekvens                          |
| -------------------- | ---------------------------------------: | --------------------------------- |
| Brier-score          |                                   < 0.20 | Månedlig                          |
| Reliability-diagram  | < 0.05 avvik i enhver probability bucket | Månedlig                          |
| Hosmer-Lemeshow-test |                                 p > 0.10 | Månedlig, hvis N er tilstrekkelig |

Hvis en validering feiler:

1. Engine pauses.
2. Conviction-modell re-fittes.
3. Årsak analyseres: regime-shift, overfit, datakvalitet eller lav N.
4. Ny shadow-periode på tre måneder kreves før live-resume.

## B.5 Hvorfor ikke grade A+/A/B/C

Grade-bokstaver kan ikke kombineres matematisk på tvers av engines. To engines som begge returnerer A+ gir ikke boten en presis risk-allocation.

Kalibrert sannsynlighet gjør signalene sammenlignbare:

* Sugar SELL conviction 0.78
* Wheat BUY conviction 0.65
* Coffee SELL conviction 0.55

Boten kan da allokere risiko etter eksplisitt formel, sektor-cap og korrelasjonsjustering.

## B.6 Hvorfor 0.50 floor

Engine skal bare publisere signal når den mener den har edge.

Conviction under 0.50 betyr i praksis:

> Ingen publiserbar edge.

Dette hindrer at boten mottar støy-signaler som den selv må filtrere. Ansvaret for edge-detektering ligger hos engine. Ansvaret for porteføljerisiko ligger hos bot.

---

# Status

Dette er **utkast v0.3.1** for review. Dokumentet er ikke implementeringsklart. Formålet er å få presise tilbakemeldinger på arkitektur, sukker-setups, forward-pricing, signal-protokoll, storage, risk-arbitrasje og validering før kode skrives.

Tilbakemelding kan sendes til operatør eller gis som PR mot `docs/whitepaper_*.md`.
