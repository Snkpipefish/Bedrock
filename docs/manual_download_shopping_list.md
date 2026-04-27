# Manuell historisk backfill — shopping-liste

Dato: 2026-04-27. Etter undersøkelse av alle Phase A-C-kilder. Lister
alt vi mangler historikk for, eksakt URL-mønster der det finnes, og
hvor i `data/manual/` vi forventer filen.

**Mål:** full historikk 2010+ for alle drivere som scorer i bedrock,
slik at backtest blir meningsfull over hele perioden (ikke bare siste
12 mnd).

**Format-konvensjon:** alle manuelle CSV-er må matche kolonne-navn fra
`bedrock/data/schemas.py`. Tabell-mapping vises under hver kilde.

---

## Prioritet 1 — Kritiske gaps (KUN 1-7 rader i DB)

Disse fyrer drivere som scorer aktivt; uten historikk er backtest
bortimot ubrukelig for berørte instrumenter.

### 1.1 COMEX inventory (Gold, Silver, Copper)

**Status:** 1 rad per metall (kun 2026-04-24).
**Mål:** 2010-01-01 → i dag, daglig (~5800 rader/metall × 3 = ~17 400 rader).
**Berørte instrumenter:** Gold (vekt 0.20 i macro), Silver (0.25), Copper (0.20).

**Gratis offentlige kilder:**
- **CME Group ClearPort** har offisielle daglige reports som PDF, men
  ingen åpen historikk-API. Tilgjengelig via betalt CME DataMine.
- **TradingView**, **MacroMicro**, **Quandl/Nasdaq Data Link** har
  COMEX-inventory tidsserier i deres datasett — krever konto.
- **Goldsilver.com** har scraped data for gull/sølv tilbake til ~2008
  som CSV.

**Anbefalt manuell vei:**
- Finn historisk CSV for hver metall fra Quandl/macro-source.
- Forventet kolonner: `metal,date,registered,eligible,total,units`
- Lagre som: `data/manual/comex_inventory_history.csv`
- Vi har allerede `data/manual/comex_inventory.csv` for daglig fallback —
  ny historikk-fil kan være separat eller append.

**URL-mønstre å undersøke:**
- https://www.kitco.com/news/2024-03-13/COMEX-warehouse-stocks
- https://goldsilver.com (har historisk gull/sølv)
- https://www.cmegroup.com/clearing/files/dailybulletin_comex_metals.pdf (daglig PDF)

---

### 1.2 Seismic events (USGS)

**Status:** 88 events fra 2026-04-20 → 2026-04-27.
**Mål:** alle M≥4.5 events 2010-01-01 → i dag i mining-regions
(~10 000 events globalt / år × 16 år = ~160 000 events totalt; vi
filtrerer regional → ~1500-2000 i mining-regions).
**Berørte instrumenter:** Gold (0.10), Silver (0.10), Copper (0.15),
Platinum (0.30 — TYNGST).

**USGS har ÅPNT API for historikk:**

```
https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2010-01-01&endtime=2026-04-27&minmagnitude=4.5&limit=20000
```

USGS sin FDSN-API (ikke en gratis kommersiell tjeneste — det er den
publike geologiske survey-API-en) tillater opp til 20 000 events per
request. For 16 års historikk trenger vi 4-8 sekvensielle calls med
`starttime`/`endtime`-paginering. **Dette KAN automatiseres trivielt.**

**Anbefalt automatisering:** utvid eksisterende `fetch_seismic.py` med
`historical=True`-flagg som walker år-for-år. Vi kan kode dette på 30
min og kjøre i bakgrunnen. **Gjøre dette automatisk istedenfor
manuelt — utvid fetcheren og restart.**

---

### 1.3 Forex Factory econ_events

**Status:** 37 events fra 2026-04-26 → 2026-05-01 (1 uke fremover).
**Mål:** historiske High/Medium-impact events 2010-01-01 → i dag.
**Berørte instrumenter:** alle 22 (event_distance vekt 0.1-0.3 i risk).

**Forex Factory har ingen offentlig historikk-API.** Bare
`ff_calendar_thisweek.json` for nåværende uke. Historikk krever:

**Alternativ A — Investing.com:**
- https://www.investing.com/economic-calendar/ har historisk arkiv
- Krever scraping eller manuell eksport (er commercial-grade)

**Alternativ B — DailyFX/Bloomberg/MarketWatch:**
- Scrape per-uke via Wayback Machine

**Alternativ C — Manuell historisk dump:**
- Forex Factory har historisk export i deres members-area
- Brukeren kan eksportere CSV manuelt fra deres konto

**Anbefalt format:** `event_ts,country,title,impact,forecast,previous,fetched_at`
**Filplass:** `data/manual/econ_events_history.csv`

---

### 1.4 CONAB Brazil grain estimates

**Status:** 1 rad per commodity (kun 2026-04-27, 7 commodities = 7 rader).
**Mål:** månedlige rapporter 2017-01 → i dag (~108 mnd × 7 commodities = ~750 rader).
**Berørte instrumenter:** Corn (vekt 0.3 i conab-familie), Soybean (1.0!), Coffee (1.0!).

**Kilde:** CONAB Pentaho-dashboard på
https://pentahoportaldeinformacoes.conab.gov.br/pentaho/api/repos/%3Ahome%3ASIMASA2%3ASerieHistorica%3ASerieHistorica.wcdf/generatedContent

**Kan vi automatisere?**
- Pentaho CDF-dashboards eksponerer underliggende data via
  `/pentaho/plugin/cda/api/doQuery` med riktig dataAccessId
- Krever 1-2 timer reverse-engineering av dashboard-AJAX-kall

**Manuell vei (raskere for brukeren):**
- Gå til https://portaldeinformacoes.conab.gov.br/safra-serie-historica-graos.html
- Pentaho-dashboardet har vanligvis "Export to CSV"-knapp i sidebaren
- Velg per-crop (Soja, Milho, Trigo, Algodão, Café Arábica, Café Conilon, Total)
- Eksporter månedlig serie 2017-2026 som CSV
- Forventet format: `report_date,commodity,production,production_units,area_kha,yield_value,yield_units,levantamento,safra,yoy_change_pct,mom_change_pct`
- Filplass: `data/manual/conab_estimates_history.csv`

**Alternativ — månedlige PDF-er:**
- https://www.conab.gov.br/info-agro/safras/graos/boletim-da-safra-de-graos
- Hver mnd-publisering har egen PDF
- PDF-link-pattern: `https://www.conab.gov.br/info-agro/safras/graos/boletim-da-safra-de-graos/item/download/{ID}_{HASH}`
- Kan parses med eksisterende `fetch_conab.py` PDF-parser

---

### 1.5 UNICA Brazil sugar/ethanol

**Status:** 1 rad (kun 2026-04-27).
**Mål:** halvmånedlige rapporter 2010 → i dag (~370 rapporter).
**Berørte instrumenter:** Sugar (vekt 1.0 i unica-familie — KRITISK).

**Status etter undersøkelse:**
- `unicadata.com.br/listagem.php?idMn=63` viser kun siste rapport
- PDF-URL-er har random hashes (`/2020/10/0830e33d066f0de0c0165616c04368da.pdf`)
- Direkte directory-listing returnerer 403
- **Ingen praktisk automatisert vei**

**Manuell vei:**
- UNICAdata har "Anuário de Safra" på https://unicadata.com.br/listagem.php?idMn=157
- Inneholder konsolidert tidsserie i Excel-format
- Last ned årlig anuário-fil per safra-år (2010/11 → 2025/26)
- Ekstraher mix_sugar_pct, crush_kt, sugar_production_kt etc per quinzena
- Forventet format: `report_date,position_date,period,crop_year,mix_sugar_pct,mix_sugar_pct_prev,mix_ethanol_pct,mix_ethanol_pct_prev,crush_kt,crush_kt_prev,crush_yoy_pct,sugar_production_kt,sugar_production_kt_prev,sugar_production_yoy_pct,ethanol_total_ml,ethanol_total_ml_prev,ethanol_total_yoy_pct`
- Filplass: `data/manual/unica_reports_history.csv`

**Alternativ — kontakt UNICA direkte:**
- Email: imprensa@unica.com.br for full historisk dataset
- Akademisk request er ofte gratis

---

## Prioritet 2 — Partielle gaps (har 1-4 år, trenger 10+)

### 2.1 cot_euronext (Milling Wheat / Corn / Canola)

**Status:** 2022-06-29 → 2026-04-22 (194 rader/produkt).
**Mål:** 2018+ (Euronext begynte rapportering ifm. MiFID II i 2018) → i dag.
**Berørte instrumenter:** Wheat (vekt 0.2 i cross), Corn (0.15 i cross).

**Euronext har INGEN offentlig bulk-API** (per deres docs).
Brute-force per-onsdag HTML er eneste vei.

**Anbefalt automatisering:** utvid eksisterende `fetch_cot_euronext.py`
med optimaliseringer (cookie-warmup én gang, redusert pacing,
DB-skip). Detached runner kjører 200-300 onsdager på ~10-15 min. **Vi
KAN automatisere dette — bare ikke kjørt enda.**

---

### 2.2 NASS Crop Progress

**Status:** 2022-04-03 → 2026-04-26 (4 år).
**Mål:** 2010+ → i dag (16 år, ~80 rader/år/commodity × 4 = ~5000 rader).
**Berørte instrumenter:** Corn, Soybean, Wheat, Cotton (alle har crop_progress 0.5 i yield-familie).

**NASS QuickStats har offentlig API med API-key:**
- https://quickstats.nass.usda.gov/api
- Vi har allerede infrastruktur (API-key satt, fetcher fungerer)
- **Eksisterende `bedrock backfill crop-progress --year 2010 --year 2011 ...`
  kan gjøre full historikk** — bare ikke kjørt med eldre år ennå
- **Kan automatiseres umiddelbart** via eksisterende CLI

---

### 2.3 BDI / shipping indices

**Status:** BDI 2018-03-22 → 2026-04-24 (8 år via Yahoo BDRY ETF).
**Mål:** BDI 2010+ → i dag, samt BCI/BPI/BSI (capesize/panamax/supramax)
historikk.

**Baltic Exchange er kommersiell**, ingen åpen API.

**Gratis kilder:**
- BDRY ETF startet 2018-02 — så Yahoo BDRY har ikke pre-2018 data
- **Bloomberg, Investing.com, og DryShipsCarriers.com** har historisk
  BDI tilbake til 2008+
- Manuell CSV-eksport fra Investing.com:
  https://www.investing.com/indices/baltic-exchange-dry-historical-data

**Manuell vei:**
- Last ned BDI historikk fra Investing.com (2008-2018)
- Last ned BCI/BPI/BSI hvis tilgjengelig
- Forventet format: `index_code,date,value,source`
- Filplass: `data/manual/shipping_indices_history.csv` (append til
  eksisterende auto-fetched 2018+)

---

### 2.4 Brent / Copper CFTC (kontrakt-navn-drift)

**Status:** Brent 2022-02-08 → 2026-04-21 (220 rader). Copper samme.
**Mål:** 2010+ → i dag.
**Allerede dokumentert i `docs/data_gaps_2026-04.md`** (CFTC navn-drift).

**Allerede løst** for 6/8 instrumenter ifølge state-loggen ("Tier 1
CFTC-name-drift backfill — 6/8 instrumenter til full historikk").
Sjekk om Brent + Copper er resterende 2/8.

---

## Prioritet 3 — Kompletteringer (mindre kritisk)

### 3.1 NOAA ENSO observations

**Status:** Tabell mangler (`enso_observations`). Tilgjengelig via
`fundamentals.NOAA_ONI` 1950-01 → 2026-02 (914 rader) — så vi har
dataen, bare i annet schema.

**Action:** Sjekk om enso_regime-driveren leser fra `fundamentals` med
series_id="NOAA_ONI" istedenfor egen tabell. Ingen backfill trengs
hvis koden allerede gjør dette.

### 3.2 WASDE (USDA) før 2019

**Status:** 2019-05-10 → 2026-04-10 (8703 rader).
**Mål:** 2010+ kunne være nyttig.

**ESMIS-arkivet** har publisering tilbake til ~2002. Eksisterende
`fetch_wasde.py` kan utvides med pre-2019 backfill — krever
URL-pattern-utvidelse i ESMIS-paginerings-walker.

---

## Sammendrag — hva du kan starte med

### Du kan automatisere (bedrock kan skrive kode + kjøre):

1. **USGS seismic historikk** — utvid `fetch_seismic.py` med år-walker (~30 min kode + ~5 min kjøring)
2. **NASS Crop Progress 2010-2021** — bruk eksisterende CLI med utvidede `--year` flagg (~10 min kjøring)
3. **Euronext 200 onsdager** — optimaliser eksisterende fetcher + detached runner (~30 min kode + 10 min kjøring)
4. **CFTC kontrakt-navn-drift** — fortsett Tier 1 for resterende 2/8 instrumenter

### Du må gjøre manuelt (laste ned og legge filer i data/manual/):

5. **COMEX inventory historikk** — last ned fra Quandl/Kitco eller annen kilde for Gold/Silver/Copper 2010+
6. **Forex Factory econ_events historikk** — eksporter fra members-area eller scrape Investing.com
7. **CONAB grain estimates historikk** — eksporter CSV fra Pentaho-dashboard, eller hent monthly PDFs 2017+
8. **UNICA sugar reports historikk** — last ned anuário-Excel-filer per safra-år 2010/11+
9. **BDI shipping pre-2018** — eksporter fra Investing.com eller annen kilde

---

## Format-detaljer for manuelle CSV-er

Alle manuelle filer skal ha header-rad med eksakt kolonne-navn.
Dato-format: ISO `YYYY-MM-DD` for date-felter, `YYYY-MM-DDTHH:MM:SS+00:00` for ts-felter.

**comex_inventory_history.csv:**
```
metal,date,registered,eligible,total,units
gold,2010-01-04,12345678.0,8765432.0,21111110.0,oz
```

**econ_events_history.csv:**
```
event_ts,country,title,impact,forecast,previous,fetched_at
2010-01-15T14:30:00+00:00,USD,CPI m/m,High,0.2,0.1,2010-01-15T14:35:00+00:00
```

**conab_estimates_history.csv:**
```
report_date,commodity,production,production_units,area_kha,yield_value,yield_units,levantamento,safra,yoy_change_pct,mom_change_pct
2017-01-15,soja,113900.0,kt,33800.0,3370.0,kg/ha,4o,2016/17,5.2,
```

**unica_reports_history.csv:**
```
report_date,position_date,period,crop_year,mix_sugar_pct,mix_sugar_pct_prev,mix_ethanol_pct,mix_ethanol_pct_prev,crush_kt,crush_kt_prev,crush_yoy_pct,sugar_production_kt,sugar_production_kt_prev,sugar_production_yoy_pct,ethanol_total_ml,ethanol_total_ml_prev,ethanol_total_yoy_pct
2010-04-16,2010-04-15,1ª quinzena de abril,2010/11,38.5,40.2,61.5,59.8,12000.0,11800.0,1.7,820.0,815.0,0.6,510.0,500.0,2.0
```

**shipping_indices_history.csv:**
```
index_code,date,value,source
BDI,2010-01-04,3104.0,investing
BCI,2010-01-04,5123.0,investing
BPI,2010-01-04,3987.0,investing
BSI,2010-01-04,2890.0,investing
```

---

## Etter manuelle filer er lagt på plass

Hver fetcher har en `_manual` fallback-funksjon som leser CSV-en og
appender til DB. Etter manuell nedlastning:

```bash
# COMEX
.venv/bin/python -c "from bedrock.fetch.comex import fetch_comex_manual; from bedrock.data.store import DataStore; df = fetch_comex_manual(); DataStore('data/bedrock.db').append_comex_inventory(df)"

# CONAB
.venv/bin/python -c "from bedrock.fetch.conab import fetch_conab_manual; ..."

# Etc per kilde.
```

Eller bruk en samlet ingest-script som vi lager etter du har filene
klare.
