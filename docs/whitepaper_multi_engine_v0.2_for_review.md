# Whitepaper: Multi-Engine Trading Architecture

**Status:** UTKAST v0.2 — for **ekstern peer-review og diskusjon**
**Dato:** 2026-05-06
**Forfatter:** Bedrock-team (operatør + AI-assistanse)
**Målgruppe:** kvant-analytikere, software-arkitekter, andre AI-assistenter

> **Til reviewer:** dette er et tidlig utkast. Mange design-valg er bevisst åpne — vi vil høre flere stemmer før kode skrives. Hvis du ser bedre løsninger eller alvorlige svakheter, si fra. Vi har 12 mnd erfaring med en monolitt som ikke skalerer (Bedrock); nå tenker vi nytt.

---

## 1. Bakgrunn

### 1.1 Hva som finnes i dag

**Bedrock** (12 mnd gammelt, ~22 instrumenter, 99 drivere, 7-familie additive scoring). Production-system med:
- Daily fetch-pipeline for 34 datakilder (USDA, NOAA, FRED, COT, vær, etc.)
- Backtest-rammeverk med DSR-validering
- cTrader-bot med risk-management
- 12-14 års historikk per instrument

### 1.2 Hva som ikke virker

Identifisert i `docs/engine_fundamental_review_2026-05-06.md`:

1. **Per-direction-uavhengig scoring** → 16 instrumenter har BÅDE BUY+SELL over publish-floor samtidig
2. **Multi-horizon parallel scoring** → 11 instrumenter publiserer samme retning på flere horisonter med duplikat entry-level (trippel-eksponering)
3. **7-familie additive scoring** mangler ekte ortogonalitets-verifikasjon (effective k ≈ 3-4 dimensjoner, ikke 7)
4. **Sirkulær score-kalibrering** (drivere tunet til floor som tunet til drivere)
5. **Forward-pricing-mismatch** (sukker prises 6-12 mnd forward; vi leser current/historical)
6. **Setup-builder kontekst-blind** (samme entry-level for alle horisonter)
7. **Manuelle familie-vekter** drifter over tid uten styring

### 1.3 Rotårsak

**Én scoring-modell, én aggregator, én sett med drivere kan ikke generalisere over 22 instrumenter på tvers av 5 asset-klasser.** Hver instrument-type har sin egen markedslogikk. Sukker prises forward-cycle. EURUSD trender intra-uke. Bitcoin har 24/7 sentiment. Disse FORTJENER ikke å presses inn i samme modell.

---

## 2. Design-visjon (foreløpig)

**Per instrument: ett dedikert program.**

- Egen filosofi (mean-reversion / momentum / event-anticipation / etc.)
- Egne kriterier (setup-type, drivere, vekter)
- Egen tidshorisont (kan være 7d, kan være 365d)
- Egen validering (backtest, OOS, shadow-mode)

**Felles bot:**
- Mottar signaler fra alle engines
- Risk-arbitrasje på portefølje-nivå
- Eksekverer i cTrader
- Returnerer outcomes til engines for læring

**Felles bibliotek:**
- DataStore + fetchers + secrets-management
- Backtest-rammeverk
- (gjenbrukes fra Bedrock — den delen virker)

---

## 3. Åpne design-spørsmål (HOVED-FOKUS FOR REVIEW)

Hvert spørsmål under har MULTIPLE alternativer — ingen er bestemt. Reviewer-input ønskes.

### Q1: Repo-struktur

| Alternativ | Fordeler | Ulemper |
|---|---|---|
| **A. Eget GitHub-repo per engine** ⭐ operatør-preferanse | Full isolering; uavhengige releases; ingen cross-contamination | Mer overhead å sette opp; CI per repo; shared-lib som dependency |
| B. Monorepo med subdirs (`engines/sugar/`, `engines/wheat/`) | Enklere refactor; én CI; lett å dele kode | Kan friste til "felles modell"; cross-coupling sniker seg inn |
| C. Hybrid: shared-lib repo + engine-repos som submodules | Strukturert; shared-lib versjonert | Mer komplekst for enkeltbruker; submodule-friction |

**Operatør-valg:** A (eget repo per engine).

**Åpent for review:** er dette praktisk for én enkelt utvikler? Hvordan unngår vi å duplikere shared-lib-oppdateringer?

---

### Q2: Scoring-system / filosofi

**Operatør-posisjon:** "Jeg vet ikke om jeg vil beholde scoringsystemet — må finne ut hva som er realistisk med dataen vi har."

**Bedrock-current-tilnærming:** 99 drivere → 7 familier → additive sum → grade A+/A/B/C → publish-floor. Vist å skape kontradiksjoner og fake ortogonalitet.

**Alternative tilnærminger å vurdere:**

| Tilnærming | Kjerne-idé | Når passer det |
|---|---|---|
| **A. Fortsett scoring** (med fixes) | 5-7 drivere per engine, ingen familier, flat score | Hvis vi tror den additive modellen i prinsipp er rett, bare for kompleks i dag |
| **B. Rule-based decision tree** | Sett av if/then-regler ("hvis A og B men ikke C, så ta SELL") | Hvis vi har klar trading-thesis vi kan kodifisere |
| **C. Probabilistic ensemble** | Hver driver returnerer P(opp Hd), aggregat via Bayesian update | Mer prinsippielt; krever mer matematikk + data |
| **D. ML-modell** (XGBoost / LSTM / Transformer) | Tren end-to-end på historiske utfall | Krever stor data-mengde + risiko for overfit; black box |
| **E. Hybrid: setup-finder + LLM-confluence-scorer** | Teknisk setup-detektor + LLM som leser news/COT/fundamenta og gir 0-100 | Eksperimentelt; LLM kan fange kontekst regler ikke kan |
| **F. Manuell trader-confluence-checker** | Engine flagger setup-kandidater; operatør tar beslutning | Trygt mens vi lærer; ikke skalerbar |

**Operatør-spørsmål til reviewer:** hvilken tilnærming ville du anbefalt for sukker spesifikt, gitt at vi har 12 års daglig pris + COT + UNICA bi-uke + Comtrade månedlig + ANP daglig + ENSO månedlig + WASDE månedlig?

---

### Q3: Setup-detection-filosofi

**Bedrock-current-tilnærming:** "score-først" — beregn score, finn nivå som passer.

**Alternativ:** "setup-først" — finn nivå, score confluence.

| Setup-type-kandidater | Beskrivelse | Fungerer når |
|---|---|---|
| **A. Mean-reversion at major S/R** | Vent på pris-approach til betydelig nivå, scor confluence | Trange ranges, etablerte instrumenter |
| **B. Momentum-breakout** | Vent på brudd over recent high/low, scor med volum | Trender-marked, post-event |
| **C. Event-anticipation** | Posisjonering før WASDE/NFP/OPEC, scor med surprise-prediksjon | Kalender-drevne markeder |
| **D. Calendar-spread arbitrage** | Mar/May vs Jul/Sep spread, scor med inventory + sesong | Storage-bare commodities (sukker, kaffe) |
| **E. News-shock-fade** | Etter overdreven respons til nyhet, fade tilbake til pre-shock | Likvide markeder med klare overshoot-mønstre |
| **F. Multi-leg basket** | Cross-instrument spreads (sugar/coffee, gold/silver) | Korrelerte par-trades |

**Operatør-spørsmål til reviewer:** for sukker — hvilken setup-type har empirisk best edge gitt dagens data?

---

### Q4: Signal-bus / kommunikasjon engine ↔ bot

**Operatør-posisjon:** "Vet ikke filsystem enda — kanskje LLMWiki / Obsidian for md-filer / ArcticDB for tidsserie-data — diskuter videre."

| Alternativ | Beskrivelse | Når passer det |
|---|---|---|
| **A. Filsystem (JSON-filer)** | Engines skriver `signals/inbox/<id>.json`, bot konsumerer + flytter til `processed/` | MVP, single-host, lav volum (< 100 signaler/dag) |
| **B. SQLite signals-tabell** | Felles SQLite med queue-mønster | Litt mer robust; ACID; lett å query historikk |
| **C. Redis pub/sub** | Engines publiserer, bot subscriber | Real-time; skalerer; standalone-tjeneste |
| **D. Kafka / NATS** | Enterprise-grade event-streaming | Overkill for én bruker; lærings-overhead |
| **E. ArcticDB** | Tidsserie-DB optimert for finansdata | God for historikk; usikkert om passer for "live signal queue" |
| **F. HTTP REST API** | Bot eksponerer `/submit_signal`-endepunkt | Standard; lett å monitorere; krever bot oppe alltid |

**Tilleggsbruk: dokumentasjon + research-notater**
- **Obsidian** — markdown-filer + lenker, lokal; bra for trader-research
- **LLMWiki** — kan AI-assistere både skriving og søk
- **Notion / Logseq** — alternativer for personlig kunnskapsbase

**Operatør-spørsmål til reviewer:** for én bruker med 1-3 engines initialt + ønske om enkel debugging — hva er minste-rasjonelle valg?

---

### Q5: Storage-arkitektur for tidsserie-data

**Bedrock-current:** SQLite (~213MB DB med 12+ års daglig data).

**Alternative:**

| System | Styrke | Svakhet |
|---|---|---|
| SQLite (current) | Enkelt, fil-basert, ingen server | Kjapt for små data; sliter > 10GB |
| **ArcticDB** | Optimert for tidsserier; Pandas-vennlig; kompresjon | Krever LMDB / S3 backend; lærings-kurve |
| **DuckDB** | Analytisk OLAP; kjapt på aggregater | Ikke optimert for time-series spesifikt |
| **InfluxDB / TimescaleDB** | Spesialisert tidsserie-DB | Server-arkitektur; overhead for én bruker |
| **Parquet-filer + Polars** | Rene file-based; lyn-rask kolonne-scan | Mindre fleksibelt for små append-operasjoner |

**Operatør-vurdering:** ArcticDB nevnt som mulighet. Bedrock har 213 MB i dag — ikke ut av SQLite-skalaen, men vil vokse.

**Operatør-spørsmål til reviewer:** når begynner SQLite å være flaskehals? Lønner det seg å bytte før det blir nødvendig?

---

### Q6: Engine-filosofi-utviklings-prosess

**Operatør-posisjon:** "Filosofi må utarbeides — vet ikke ennå."

**Foreslått prosess:**

1. **Data-eksplorering først (1-2 uker per instrument)**: hva har vi, hva sier det, hvor er signal vs støy
2. **Hypothesis-formulering**: 1-3 trading-thesis kandidater
3. **Backtest-validering på shadow-data**: hvilken thesis gir Sharpe ≥ 1.5 OOS?
4. **Setup-type-utvalg**: basert på thesis (mean-reversion / momentum / event)
5. **Driver-utvalg**: 5-7 drivere som direkte støtter thesis
6. **Konvertering til kode**: implementer engine
7. **Shadow-mode 3-6 mnd**: live-signaler logget, ikke utført
8. **Cut-over til live**: med 50% av normal risk i 3 mnd

**Operatør-spørsmål til reviewer:** hvor lang shadow-mode-periode er prinsippielt riktig før live-trading? Er 6 mnd for konservativt? 3 mnd for risikabelt?

---

### Q7: Risk-arbitrasje på bot-side

Hvis 3 engines (sugar, wheat, coffee) sender signaler samtidig:
- Sugar: SELL @ 1.5% conviction-score-vektet
- Wheat: BUY @ 1.0%
- Coffee: SELL @ 0.5%

Daily risk-budget = 2.0%. Hvordan allokere?

| Strategi | Beskrivelse |
|---|---|
| **A. Konviksjon-prioritert (largest first)** | Sugar 1.5% → 0.5% igjen til wheat (kuttet fra 1.0) → Coffee 0% |
| **B. Pro-rata** | Sugar 1.0% → Wheat 0.67% → Coffee 0.33% |
| **C. Track-record-vektet** | Engine med beste historiske Sharpe får prioritet |
| **D. Sektor-cap** | Hvis sugar+coffee er begge softs, max 1.5% på softs samlet |
| **E. Time-of-day-boost** | Helt nye signaler får forrang fremfor pending |

**Operatør-spørsmål til reviewer:** hvordan håndterer profesjonelle multi-strategy hedge-fond denne typen arbitrasje?

---

### Q8: Outcome-feedback-loop

Når et signal blir tatt og eksekvert, hva returnerer bot til engine?

| Felt | Type | Bruk |
|---|---|---|
| Faktisk fill-pris | float | Sammenligne med planned entry |
| Slippage | float | Engine kan justere setup-type-preferanser |
| Holdetid | duration | Engine kan justere horisont-target |
| MFE / MAE | float, float | Engine kan tune trailing-parameters |
| Eksisterende correlated positions | list | Engine kan vekt-justere fremtidige signaler |

**Spørsmål:** skal outcome-feedback brukes til **online learning** (engine endrer vekter live) eller **offline tuning** (operatør re-trener månedlig)?

Risiko ved online: engine kan overshoot på enkelt-tap → reduserer eksponering uhensiktsmessig.
Risiko ved offline: tar tid før engine adapterer til regime-shift.

---

### Q9: Bedrock-pensjonering-tidslinje

**Operatør-posisjon:** "Vi lar Bedrock stå så lenge — tar pensjonering etterhvert."

| Strategi | Beskrivelse |
|---|---|
| **A. Bedrock = research-mirror evig** | Aldri pensjoneres, fortsetter å produsere "research-signaler" som referanse |
| **B. Per-instrument pensjonering** | Når sugar-v3 validert: skru av sukker i Bedrock; behold andre 21 |
| **C. Total pensjonering etter alle 22 portet** | 2-3 års horisont; krever 22 nye engines |
| **D. Bedrock blir backtest-laboratorium** | Bevares for å eksperimentere med nye drivere før de wires inn i v3-engines |

**Operatør-spørsmål til reviewer:** er det verdi i å ha Bedrock-current som "research-mirror" (parallel kjøring), eller drar det bare ressurser?

---

### Q10: Versjonering + backwards-compat

Hvis sugar-v1 fungerer 6 mnd, så bygger vi sugar-v2 med ny filosofi:

| Strategi | Beskrivelse |
|---|---|
| **A. Hard cut-over** | Ved cut-over slettes v1, v2 tar over alt |
| **B. Parallel-kjøring (A/B)** | v1 og v2 sender begge signaler; bot velger basert på conviction × track-record |
| **C. Versjonert i samme repo** | sugar-engine inneholder both v1.py og v2.py; YAML velger aktiv versjon |
| **D. Eget repo per versjon** | sugar-engine-v1 / sugar-engine-v2 = separate repos |

**Operatør-spørsmål til reviewer:** hva er industri-standard for trading-strategi-versjonering?

---

## 4. Hva vi VET vi vil ha (foreløpig konsensus)

Disse punktene er stabile uavhengig av åpne spørsmål:

✅ **Eget repo per engine** (Q1.A)
✅ **Bot er passiv risk-arbiter** (ingen logikk om "hvilken signal å ta")
✅ **Felles bot mottar fra alle engines**
✅ **Shared bibliotek for DataStore + fetchers + secrets** (gjenbruk fra Bedrock)
✅ **Strikt sekvensiell skalering** — ett instrument fullt validert før neste startes
✅ **Bedrock-current beholdes** parallelt, pensjonering tas etterhvert
✅ **Setup-først over score-først** som arkitektonisk preferanse
✅ **Outcome-feedback til engines** for læring (offline eller online — Q8)

---

## 5. Forventet bygge-rekkefølge

**Fase 0: Diskusjon + design** (4-6 uker — der vi er nå)
- Whitepaper iterasjoner med flere reviewere
- Operatør-beslutninger på Q1-Q10
- Konkret arkitektur-spec basert på avklaringer

**Fase 1: Infrastruktur** (1-2 uker)
- Felles bibliotek-pakkestruktur
- Signal-protokoll v1.0 (avhenger av Q4-valg)
- Bot multi-engine consumer
- Engine-template (avhenger av Q1-valg)

**Fase 2: Sugar-engine v1** (4-8 uker — avhenger av Q2 + Q3-valg)
- Data-eksplorering på sukker (Q6 prosess)
- Filosofi-formulering
- Setup-finder + scoring (uansett tilnærming)
- Backtest + shadow-mode

**Fase 3+: Wheat, Coffee, ...** (2-3 mnd per ny engine)
- Hver med EGEN data-eksplorering + filosofi-formulering
- Ingen gjenbruk av sukker-vekter

---

## 6. Spørsmål til peer-reviewere

For analytikere + andre AI-aktører — vi vil vite:

**A. Filosofiske:**
- Er "én engine per instrument" overengineering, eller riktig disiplin?
- Setup-først vs score-først — er forskjellen så stor som vi tror?
- Hvor "kunnskaps-tung" bør hver engine være (5 drivere vs 50)?

**B. Tekniske:**
- Hvilken signal-bus passer for 1-bruker, 1-3 engines (Q4)?
- ArcticDB / DuckDB / SQLite — hvor er trade-offs (Q5)?
- Online vs offline outcome-learning (Q8)?

**C. Strategiske:**
- Realistisk shadow-mode-tid før live (Q6)?
- Cut-over-strategi mellom Bedrock og v3 (Q9)?
- Versjonering-mønster (Q10)?

**D. Spesifikt for sukker:**
- Best setup-type gitt 14 års data + bi-uke UNICA + månedlig Comtrade (Q3)?
- Realistisk Sharpe-target (1.0? 1.5? 2.0)?
- Hvor mye edge ligger i forward-pricing-data (Green Pool / Czarnikow) som Bedrock ikke fanger?

---

## 7. Hvorfor dette utkastet er bevisst åpent

Vi har 12 mnd erfaring med en monolitt-arkitektur som ikke skalerte. Læringen var: **for tidlig commitment til design ga oss problemer vi nå må reversere.**

Dette utkastet skiller derfor mellom:
- **Sannheter** (det vi vet ikke virker — § 1.2, 1.3)
- **Bestemmelser** (det vi har bestemt — § 4)
- **Åpne spørsmål** (der vi vil ha innspill — § 3)

Reviewer-tilbakemelding på § 3 vil bli inkorporert i v0.3 før noen kode skrives.

---

## 8. Neste steg

1. **Operatør sender utkast** til 2-3 ekstern analytikere + AI-aktører
2. **Samle tilbakemeldinger** over 1-2 uker
3. **v0.3 av whitepaper** med integrerte beslutninger
4. **Detaljer Fase 0/1-arbeidet** basert på avklarte design-valg
5. **Code-start** — ikke før § 3 er stort sett besvart

---

*Status: UTKAST v0.2 — for review. Ikke implementeringsklart. Operatør tar imot tilbakemeldinger på leifsebastian@gmail.com eller via PR til `docs/whitepaper_*.md`.*
