# ADR-007: Fetch-port strategi for ikke-portede cot-explorer-fetchere

Dato: 2026-04-27
Status: accepted
Fase: 12.5+ (sub-fase, sessions 104-117)

## Kontekst

PLAN-prinsipp 6 sier at alle eksisterende fetch-moduler fra `~/cot-explorer/`
skal beholdes. Audit i session 104 (svar på "audit STATE vs PLAN vs faktisk
kode") avdekket at **11 fetchere ikke ble portet** under Fase 6:

```
fetch_calendar.py     fetch_oilgas.py       fetch_unica.py
fetch_comex.py        fetch_seismic.py      fetch_euronext_cot.py
fetch_conab.py        fetch_intel.py        fetch_crypto.py
fetch_ice_cot.py      fetch_shipping.py
```

Hverken STATE.md eller PLAN.md noterte dette som åpen gjeld — det var
"stille divergens". Brukeren har bestemt (2026-04-27) at alle 11 skal
portes inn i bedrock og wires til scoring der det gir verdi.

## Beslutning

### 1. Cot-explorer er referanse-implementasjon, ikke kanonisk

Hver fetcher i `~/cot-explorer/` portes som en **ren re-implementasjon
mot bedrock SQLite-skjema**, ikke som direkte kopi:

- cot-explorer skriver til `data/<navn>/latest.json` + `history.json` som
  primær persistens. Dette duplikerer tidsserie-data og krever full
  re-skriving ved hver kjøring.
- Bedrock skriver til SQLite-tabell med PK på (id, ts) → idempotent
  append, ingen JSON-blobs som primær persistens.
- Parsing-logikk (regex, pdftotext-pipeline, HTML-skraping) gjenbrukes
  fra cot-explorer der den er moden; resten skrives på nytt.

### 2. Tre port-typer per fetcher

| Type | Port-omfang | Når brukes |
|---|---|---|
| **full driver-port** | fetcher + DB-skjema + driver + YAML-wiring + tester + systemd-timer | Når data er strukturert (numerisk/tabellær) og kan gå inn i scoring |
| **fetcher + UI-context** | kun fetcher + DB-skjema + UI-rendering | Når data er sentiment-basert (nyheter, fear&greed) — empirisk validering før scoring-bruk |
| **konsolidering** | utvider eksisterende fetcher framfor å lage ny | Når cot-explorer-fetcher overlapper bedrock-fetcher (>70 % duplikat) |

### 3. Konsolidering før duplisering

Hvis en cot-explorer-fetcher i hovedsak overlapper en allerede portet
bedrock-fetcher, **konsolideres** framfor å lage ny modul:

- `fetch_oilgas.py` (priser+COT+nyheter+EIA) → kun **EIA-bit** portes som
  `fetch/eia_inventories.py`. Priser dekkes av Yahoo (session 58),
  CFTC-COT av `cot_cftc.py`, ICE-COT av session 106, nyheter av
  session 114.
- `fetch_shipping.py` (BDI/BCI/BPI/BSI + nyheter) → utvider eksisterende
  `manual_events.py:fetch_bdi` til ny `fetch/shipping.py` med alle
  sub-indekser i én tabell `shipping_indices`.

### 4. Manuell CSV-fallback fra dag 1 for fragile kilder

HTML-skrapere er sårbare for kilde-redesign. To kilder i sub-fase 12.5+
faller i denne kategorien:

- `fetch_comex.py` — scraper metalcharts.org/heavymetalstats.com
- `fetch_euronext_cot.py` — parser Euronext live-HTML

Begge implementeres med **manuell CSV-fallback fra dag 1**, samme
mønster som NASS (session 97-98) og WASDE (session 85): hvis primær-kilden
feiler eller returnerer 0 rader, leses `data/manual/<navn>.csv`.

### 5. Sentiment-fetchere starter som UI-context

`news_intel` (Google News RSS for metals/oil) og `crypto_sentiment`
(Fear&Greed-indeks + funding rate) er kvalitative sentiment-signaler.
Disse:

- Portes som **kun fetcher + DB-skjema + UI-rendering** i sessions 114-115.
- Får **ingen driver, ingen YAML-wiring** initialt.
- Vurderes for scoring-driver i ADR-009 (cutover-readiness audit, session 117)
  basert på empirisk korrelasjon med forward-return etter 1+ måneds
  observasjons-data.
- Hvis driver senere implementeres: maks driver-vekt 0.1 i første runde,
  bumpet kun etter backtest-validering.

### 6. PDF-parsere bruker poppler-utils med pypdf-fallback

Conab og Unica leverer data som PDF. Cot-explorer bruker `pdftotext`
(poppler-utils) via subprocess. Bedrock-port:

- Primær: `pdftotext -layout` via subprocess (poppler-utils).
- Fallback: `pypdf` (Python-only) hvis poppler-utils ikke er installert
  eller `pdftotext` returnerer tom output.
- Detektering: én test ved fetcher-import som setter `_PDF_BACKEND` til
  `"poppler"` eller `"pypdf"`.

Bruker har bekreftet (2026-04-27) at prod-host kan installere
poppler-utils. Fallback er for utviklings-miljøer.

### 7. Cron-cadence i lokal Oslo TZ

Per § 7.4 (session 103): alle nye fetch.yaml-cron-verdier settes i
**lokal-tid (Oslo, CEST/CET)**, ikke UTC. Hver ny fetcher får cron-tid
som lander **etter** kildens publisering Oslo-lokal-tid.

### 8. Per-fetcher mapping låses i ADR-008

Detaljert tabell over (cot-explorer-modul → bedrock-modul → DB-tabell →
cron → driver-navn → instrumenter) hører hjemme i ADR-008, som skrives
i session 105 (parallelt med første fetcher-port). ADR-007 (denne) er
kun strategien.

## Konsekvenser

**Positivt:**
- Klar guide for hver av de 11 sessionene 105-117.
- Konsolidering (eia, shipping) sparer ~2 sessioner mot full re-port.
- UI-først for sentiment-fetchere unngår scoring-støy uten empirisk grunnlag.
- Manuell CSV-fallback fra dag 1 gir robusthet mot kilde-redesign.

**Negativt:**
- 11 sessioner er betydelig commitment før observasjonsvinduet kan
  re-aktiveres. Bruker har akseptert dette som forutsigbart arbeid med
  klar rekkefølge.
- News_intel og crypto_sentiment lagres uten umiddelbar score-bruk —
  hvis de aldri promoveres til driver, blir de "data uten scoring-formål"
  inntil videre. Akseptabelt per prinsipp 6 (bevare alle fetch-ressurser).

**Risiko:**
- HTML-skrapere kan brytes mellom port-tidspunkt og første live-kjøring.
  Mitigering: manuell CSV-fallback + smoke-test ved fetch-runner-kjøring.
- PDF-parsere er sensitive for kilde-format-endring (Conab har endret
  PDF-layout en gang siden cot-explorer ble skrevet). Mitigering:
  hvert release verifiserer fixture-PDF; tester feiler hvis parsing
  endrer seg.

## Alternativer vurdert

- **Alt A: Drop alle 11 fetchere fra prosjekt-scope.** Avvist av bruker —
  ønsker full data-coverage før Fase 13 cutover.
- **Alt B: Port direkte 1-til-1 (JSON som primær lagring).** Avvist —
  dupliserer SQLite-modellen og bryter ADR-002. Ville krevd parallell
  data-modell.
- **Alt C: Port alle 11 i én stor session.** Avvist — bryter session-
  budsjett (CLAUDE.md § 17.5: én avgrenset leveranse per session).

## Refererer til

- PLAN § 7.5 (mapping-tabell over de 11 fetcherne)
- PLAN prinsipp 6 (bevare alle fetch-ressurser)
- ADR-002 (SQLite som data-lag)
- ADR-005 (analog-data-skjema, presedens for additive tabeller)
- STATE.md sesjon 104 (audit-resultat)
