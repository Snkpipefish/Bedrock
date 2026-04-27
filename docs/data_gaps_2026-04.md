# Historisk data-gaps — sub-fase 12.6

Dato: 2026-04-27. Oppdaget under harvest-oppstart i sub-fase 12.6.
Bruker rapporterte at backtest kjørte over perioder uten data → meningsløs.
Denne listen identifiserer hvilke data-kilder som trenger backfill for at
backtest skal gi meningsfulle resultater på alle 22 instrumenter.

## Sammendrag

8 instrumenter er **blokkert** av manglende historisk CFTC-COT-data
fordi CFTC har endret kontrakt-navn over tid og bedrock-DB har bare én
av to navne-versjoner. 3 instrumenter er blokkert av manglende
historisk Phase A-C-data (sessions 106-112). Detaljer under.

## Type 1: CFTC-kontrakt-navn-drift (KRITISK)

CFTC reorganiserer/omdøper kontrakter periodevis. Bedrock-DB har data
for én navne-versjon, mens YAML-en peker på en annen. Fix: backfill
gammel navn i tillegg til ny, eller standardiser YAMLs.

### 1.1 Crude Oil (CFTC disaggregated)

| YAML peker på | DB har | Mangler |
|---|---|---|
| "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE" | 2010-01 → 2022-02 (631 rader) | 2022-02 → i dag (sannsynlig nytt navn "CRUDE OIL, LIGHT SWEET-WTI - NEW YORK MERCANTILE EXCHANGE") |

**Effekt:** CrudeOil mangler ~4 år nyeste positioning-data. Backtest virker for 2010-2022, ikke 2022+.

### 1.2 SP500 (CFTC legacy)

| YAML peker på | DB har | Mangler |
|---|---|---|
| "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE" | 2010-01 → 2022-02 (631 rader) | 2022-02 → i dag (sannsynlig nytt navn "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE") |

**Effekt:** Samme som CrudeOil — mangler 2022+.

### 1.3 Nasdaq (CFTC legacy) — BEGGE NAVN FINNES

| YAML peker på | DB har "MINI" | DB har "Consolidated" |
|---|---|---|
| "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE" | 2010-01 → 2022-02 (631 rader) | 2022-01 → i dag (225 rader) |

**Fix:** YAML peker på "Consolidated" som starter 2022 — vi har gammel "MINI"-data 2010-2022 men leser den ikke. Enten oppdater YAML til både navn (logisk OR), eller migrer gammel "MINI"-data til "Consolidated"-navn.

### 1.4 Wheat (CFTC disaggregated)

| YAML peker på | DB har | Mangler |
|---|---|---|
| "WHEAT - CHICAGO BOARD OF TRADE" | 2010-01 → 2013-12 (206 rader) | 2014+ (sannsynlig nytt navn "WHEAT-SRW - CHICAGO BOARD OF TRADE") |

**Effekt:** Mangler 12+ år! Wheat-positioning er praktisk talt blank for backtest.

### 1.5 Brent CFTC-mini

| YAML peker på | DB har | Mangler |
|---|---|---|
| "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE" | 2022-02 → i dag (220 rader) | 2018-2022 (Brent CFTC-mini ble lansert ~2017-12) |

**Effekt:** Mangler ~4 år tidligste data.

### 1.6 Copper, NaturalGas, GBPUSD — alle starter 2022-02

Disse tre kontraktene starter alle på `2022-02-08` i bedrock-DB, som er
fordi backfill ble startet samtidig fra det punktet. Antagelig:

| YAML peker på | Mangler 2010-2022 (sannsynlig gammel navn) |
|---|---|
| "COPPER- #1 - COMMODITY EXCHANGE INC." | Trolig samme navn — backfill bare ufullstendig |
| "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE" | Trolig "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE" |
| "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE" | Trolig samme navn — bare ufullstendig backfill |

**Effekt:** Alle tre mangler 12 år tidligste data. CFTC har dem siden 1990-tallet.

## Type 2: Phase A-C-data med kort historikk

### 2.1 cot_ice (ICE COT) — Session 106

**Dagens data:** Brent (68 uker, 2025-01 → 2026-04), Gasoil (68 uker)
**Mangler:** 2010-2024 (15 år)

ICE Public Reports-arkiv har historiske `COTHist<år>.csv`-filer. Session 106
hentet bare 2025+2026. Backfill kan kjøre `fetch_cot_ice` mot URLs for
hvert år tilbake til 2010.

**Action:** Modifiser `fetch_cot_ice.py` til å iterere år 2010-2024,
laste ned `COTHist<år>.csv` per år. Forventet wall-time: ~5 min.

### 2.2 cot_euronext — Session 110

**Dagens data:** 15 rader (DB) for 3 produkter, ~5 uker
**Mangler:** Mange år bakover

Euronext per-produkt-arkiv tilgjengelig via samme URL-mønster som session 110.
Bare flere onsdager bakover.

**Action:** Re-kjøre fetch med `n=200` (ca. 4 år bakover) i stedet for default `n=6`.

### 2.3 conab_estimates — Session 111

**Dagens data:** 7 rader (4 grain-typer + 3 coffee-tier fra siste rapport)
**Mangler:** Månedlige rapporter back til 2017+ (CONAB har mange års arkiv)

CONAB publiserer månedlig (15. hver mnd) og holder PDF-arkiv tilgjengelig
på gov.br. Hver gammel PDF har samme struktur — kan parses med eksisterende
`fetch_conab.py`.

**Action:** Bygg en backfill-funksjon som walker `find_pdf_on_index` for
hver mnd 2017-2026 (= ~108 PDFs).

### 2.4 unica_reports — Session 112

**Dagens data:** 1 rad (1ª quinzena de março de 2026)
**Mangler:** Halvmånedlig back til 2010+ (UNICA har 15+ års arkiv)

Samme mønster som conab — UNICA holder PDF-arkiv på unicadata.com.br.

**Action:** Backfill-walker for hver halvmåned 2010-2026 (~370 PDFs).

### 2.5 comex_inventory — Session 108

**Dagens data:** 3 rader (Gold/Silver/Copper @ 2026-04-24)
**Mangler:** Daglig data tilbake noen år

metalcharts.org-API gir bare snapshot. Alternative kilder:
- CME Group bulk historical exports (paid + manual)
- heavymetalstats.com (HTML scrape, ble droppet i session 108 pga fragility)
- CME daily metals reports (PDF-arkiv)

**Action:** Vurder enten (a) backfill via heavymetalstats med bedre parsing,
(b) manuell CSV-import fra CME, (c) akseptér at COMEX-driveren bygger
data fremover bare.

### 2.6 seismic_events — Session 109

**Dagens data:** ~100 events siste 7 dager (USGS rolling)
**Mangler:** All historikk

USGS gir kun "siste 7 dager" via 4.5_week.geojson. Historisk arkiv via:
- USGS Earthquake Catalog (https://earthquake.usgs.gov/earthquakes/search/) — kan eksportere CSV med dato-rangefilter
- Massiv API: GeoNet, IRIS, EMSC

**Action:** Bygg en `backfill_seismic_events.py` som kaller USGS-search-API
(støtter starttime/endtime-params), hent M≥4.5 for 2010-2026 (~50,000 events).

### 2.7 econ_events (Forex Factory calendar) — Session 105

**Dagens data:** ~37 events siste uke
**Mangler:** All historikk

Forex Factory's gratis-feed gir bare current week. Historisk:
- forexfactory.com har søkbart arkiv men krever scraping av HTML
- Trading Economics API (paid)
- Investing.com calendar (krever scraping)

**Action:** Vurder dette som **ikke backfillbart for nå** — driver event_distance
kan ikke evalueres historisk. Aksepter at den kun virker fremover.

### 2.8 news_intel + crypto_sentiment — Sessions 114-115

**Dagens data:** 0 rader (timers ikke installert ennå)
**Mangler:** All historikk

Begge er ikke backfillbare meningsfullt — Google News RSS gir bare 24-48t
nyheter, alternative.me Fear & Greed har 1-års arkiv, CoinGecko har historikk
men endpoint vi bruker er snapshot-only.

**Action:** Aksepter — disse drivere kan kun valideres fremover.

## Prioritert backfill-plan

For maksimal nytte i sub-fase 12.6:

### Tier 1 (kritisk, lav-kost):
1. **CFTC-kontraktnavn-drift fix** — backfill gammel + ny navn for
   CrudeOil, SP500, Wheat, Brent, NaturalGas, Copper, GBPUSD, og merge
   Nasdaq. **Anslag: 1-2 timer kode + ~30 min kjøring.**

2. **ICE-COT historikk 2010-2024** — modifiser `fetch_cot_ice` til å
   iterere år. **Anslag: 30 min kode + ~5 min kjøring.**

### Tier 2 (verdifull, medium-kost):
3. **Euronext-COT bakover** (3-4 år for Wheat/Corn EU-overlay) —
   parameter-bump i fetch. **Anslag: 5 min kode + ~10 min kjøring.**

4. **Conab historikk 2017-2026** — PDF-walker. **Anslag: 1 time
   kode + ~30 min kjøring (108 PDFs ved sekvensielle requests).**

5. **Unica historikk 2010-2026** — PDF-walker. **Anslag: 1 time kode +
   ~2 timer kjøring (~370 PDFs).**

### Tier 3 (nice-to-have, høy-kost):
6. **USGS seismic historikk** — API-port. **Anslag: 2 timer kode +
   ~30 min kjøring.**

7. **COMEX historikk** — usikkert om mulig uten paid kilde. Skipp for nå.

### Tier 4 (ikke backfillbart):
8. **econ_events, news_intel, crypto_sentiment** — kun fremover-validering.

## Konsekvens for harvest-strategi

Mens vi venter på backfill:
- Kjøre harvest **kun fra 2010-01-05** for 14 instrumenter med full data
- Hopp over Brent/Copper/NaturalGas/GBPUSD harvest til Tier 1 er ferdig
- Kjøre BTC fra 2018-04-10 (CFTC start) — ingen gap
- ETH fra 2021-04-06 — ingen gap

Etter Tier 1 backfill: alle 22 instrumenter kan harvestes fra prises-start
(typisk 2010 eller instrument-launch).

## Anbefaling

Start med **Tier 1 fix** (CFTC-navn-drift) før vi starter en ny harvest.
Det fikser de 8 viktigste instrumentene og er ~3-4 timers samlet arbeid.
Tier 2 (cot_ice + euronext + conab/unica) kan kjøres parallelt med
harvest hvis kapasitet finnes.
