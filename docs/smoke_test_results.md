# Smoke-test-resultater for sub-fase 12.7 D0

Dato: 2026-04-29 (session 126)
Status: **FERDIG**

D0 verifiserte historikk-tilgjengelighet + endpoint-stabilitet for nye
datakilder før implementasjon i D1/D2/D3. Engangs-skripts ligger i
`scripts/smoke/<source>.py` (lov til å være "shitty" per ADR-011).

## Klassifikasjons-disiplin (ADR-011 oppmykning, commit `1a5f450`)

- **GO:** ≥10 år historikk + stabilt endpoint + gratis
- **RISK:** 5-10 år historikk ELLER ustabilt endpoint (token-friksjon,
  fragil parsing, etc.) — implementeres med eksplisitt risiko-notat
- **SKIP:** <5 år historikk — utsett til kilde modnes eller erstatt
- **BLOCK:** Paywall / login / utilgjengelig — droppes

A14 Eskom og C2 Platinum-refactor DROPPED ved D0-start (commit
`2cd54d5`) — bekreftet bak betalingsmur.

## Sammendrag

| Kilde | Type | Historikk | Endpoint | Klassifikasjon |
|---|---|---|---|---|
| **B3 DXY (Yahoo `DX-Y.NYB`)** | Yahoo | **55.3 år (1971+)** | 0.73s | **GO** |
| **B2 ^VIX3M / ^VIX6M / ^VIX9D** | Yahoo | **15.3–19.8 år** | 0.34–0.40s | **GO** |
| **B1 FRED — 9 av 11 serier** | FRED | **23–56 år** | 0.30–0.61s | **GO** |
| B1 BAMLH0A0HYM2 (HY OAS) | FRED | 3.0 år | 0.34s | **SKIP** |
| B1 BAMLC0A0CM (IG OAS) | FRED | 3.0 år | 0.30s | **SKIP** |
| **A12 AAII Sentiment** | XLS | (ikke parset, men 1.1MB) | 1.39s | **GO** |
| **A4 CFTC TFF (`gpe5-46if`)** | Socrata | **19.9 år (juni 2006+)** | 0.63s | **GO** |
| **A9 US Drought Monitor** | CSV API | **26.3 år (2000+)** | 1.97s | **GO** |
| **A10 Cecafé månedlig** | PDF | Siste rapport OK (mars 2026) | 4.56s | **GO** |
| **B5 Calendar spreads M1** (BZ/CL/NG/GC/SI/HG/PL/ZC/ZS/ZW) | Yahoo | **16.3 år** | <0.5s | **GO** |
| A1 Baker Hughes Rig Count | CSV | (timeout fra shell) | 20s timeout | **RISK** |
| A5 GLD / A6 SLV / A7 PPLT holdings | HTML | (JS-rendret) | 0.2–2.8s | **RISK** |
| A11 ICE certified stocks | HTML | (inkonsistente rapport-IDer) | 0.2–0.7s | **RISK** |
| A3 FAS Export Sales | API | (HTTP 403) | 0.79s | **RISK** |
| A2 AGSI EU gas storage | API+token | (token-registrering kreves) | 0.20s | **RISK** |
| B5 Calendar spreads spesifikke kontraktsmåneder | Yahoo | 8.4 år | <0.5s | **RISK** |
| A8 NOPA Crush Report | PDF | (kun release-kalender; data via LSEG) | 1.10s | **BLOCK** |

**Totalt: 14 GO-bekreftede kilder/serier + 8 RISK + 3 SKIP/BLOCK.**

## Per-kilde-rapporter

### B3 DXY Yahoo (`DX-Y.NYB`) — GO

- **Endpoint:** `https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB`
- **Historikk:** 1971-01-04 → 2026-04-29 (55.3 år)
- **Frekvens:** Daglig
- **Schema:** ts (datetime UTC), open, high, low, close, volume (alle float64/int64)
- **Eksempel siste close:** 98.708
- **Implementasjon:** D1. Bruk eksisterende `bedrock.fetch.yahoo.fetch_yahoo_prices`
  — bare ny ticker i `prices`-fetcher, ingen ny modul nødvendig.
- **Smoke-script:** `scripts/smoke/b3_dxy_yahoo.py`

### B2 VIX-termstruktur Yahoo — GO

- **Tickere:** `^VIX3M`, `^VIX6M`, `^VIX9D`
- **Historikk:**
  - ^VIX3M: 2006-07-17 → 2026-04-28 (19.8 år)
  - ^VIX6M: 2008-01-02 → 2026-04-28 (18.3 år)
  - ^VIX9D: 2011-01-03 → 2026-04-28 (15.3 år)
- **Implementasjon:** D2 (vix_term_ratio-driver). Samme `prices`-fetcher.
- **Smoke-script:** `scripts/smoke/b2_vix_term.py`

### B1 FRED-utvidelse — 9 GO + 2 SKIP

| Series ID | Historikk | Klassifikasjon |
|---|---|---|
| DGS2 | 1976-06-01 → 2026-04-27 (49.9 år) | **GO** |
| IRLTLT01DEM156N (DE 10Y) | 1970-01-01+ (56.2 år) | **GO** |
| IRLTLT01GBM156N (GB 10Y) | 1970-01-01+ (56.2 år) | **GO** |
| IRLTLT01JPM156N (JP 10Y) | 1989-01-01+ (37.2 år) | **GO** |
| IRLTLT01AUM156N (AU 10Y) | 1970-01-01+ (56.2 år) | **GO** |
| WALCL (Fed total assets) | 2002-12-18+ (23.3 år) | **GO** |
| RRPONTSYD (Reverse Repo) | 2003-02-07+ (23.2 år) | **GO** |
| WTREGEN (TGA balance) | 1986-01-08+ (40.3 år) | **GO** |
| NFCI (Chicago Fed FCI) | 1971-01-08+ (55.3 år) | **GO** |
| **BAMLH0A0HYM2 (HY OAS)** | **2023-04-30+ (3.0 år)** | **SKIP** |
| **BAMLC0A0CM (IG OAS)** | **2023-04-30+ (3.0 år)** | **SKIP** |

**KRITISK D1-FUNN:** ICE BofA OAS-seriene returnerer kun 3 år fra FRED gratis-API.
Forventet historikk var ~1996+. Mulige årsaker:
1. FRED rate-limit eller API-version som filtrerer eldre data
2. Serien er rebrandet/ny under samme kode
3. ICE BofA-data er flyttet bak betalingsmur

**Anbefaling:** D1 må undersøke. Alternativ kilde for kreditt-spreads:
- St. Louis Fed FRED Economic Indicators (annen serie-ID)
- ICE Yield Book direkte (subscription)
- Yahoo FRED-aggregator-pakke

Hvis ingen alternativ finnes, drop HY/IG OAS fra B1 og marker som
fundamental gap.

- **Smoke-script:** `scripts/smoke/b1_fred_extension.py`

### A12 AAII Sentiment Survey — GO

- **Endpoint:** `https://www.aaii.com/files/surveys/sentiment.xls`
- **Status:** HTTP 200, 1.1 MB Excel-fil
- **Forventet historikk:** 1987+
- **Implementasjon:** D2. Krever `xlrd>=2.0.1` for .xls-parsing (ikke
  installert per session 126). Pip-add ved D2-start.
- **Mean-reversion-driver-intern:** AAII bull-share inverteres til
  "extreme_contrarian_score" per pattern-doc § 3.2.
- **Smoke-script:** `scripts/smoke/a12_aaii_sentiment.py`

### A4 CFTC TFF (Socrata `gpe5-46if`) — GO

- **Endpoint:** `https://publicreporting.cftc.gov/resource/gpe5-46if.json`
- **Historikk:** 2006-06-13 → 2026-04-21 (19.9 år) — **bedre enn forventet 2010+**
- **Schema:** 73 felter inkludert dealer_positions_long_all,
  asset_mgr_positions_long, lev_money_positions_long etc.
- **Implementasjon:** D1. Gjenbruker eksisterende
  `bedrock.fetch.cot_cftc._fetch_cot_socrata`-klient — ny tabell-variant
  i samme modul. Ny field-map for TFF (Dealer/Asset Manager/Leveraged
  Funds vs disaggregated MM-typer).
- **C1 (cot_legacy→cot_tff for finansielle):** kan implementeres samme
  session som A4 fordi datapipelinen er klar.
- **Smoke-script:** `scripts/smoke/a4_cftc_tff.py`

### A9 US Drought Monitor — GO

- **Endpoint:** `https://usdmdataservices.unl.edu/api/USStatistics/GetDroughtSeverityStatisticsByAreaPercent`
- **Historikk:** 2000-01-04 → 2026-04-27 (26.3 år)
- **Frekvens:** Ukentlig (tor)
- **Schema:** MapDate, AreaOfInterest (US/CONUS/Total/Per state),
  None, D0, D1, D2, D3, D4 (severity-percentages), ValidStart, ValidEnd
- **Implementasjon:** D2. Stabilt CSV-API, ingen auth.
- **Smoke-script:** `scripts/smoke/a9_drought_monitor.py`

### A10 Cecafé Brasil kaffe-eksport (Tier 3) — GO

- **Endpoint:** `https://www.cecafe.com.br/publicacoes/relatorio-de-exportacoes/`
- **Status:** HTTP 200, finner 1 PDF-lenke per session (siste rapport)
- **PDF:** mars 2026, 23 sider, 2.8 MB. pypdf-parsing OK.
- **Backfill-utfordring:** Index-siden viser kun siste rapport. D3 må
  bygge URL-pattern fra navnemønster
  (`CECAFE-Relatorio-Mensal-{MONTH}-{YEAR}.pdf`) for å hente historikk
  2002+.
- **Implementasjon:** D3 (Tier 3, lavest prioritet).
- **Smoke-script:** `scripts/smoke/a10_cecafe.py`

### B5 Calendar spreads Yahoo — GO (M1) + RISK (specific contracts)

- **Tier 1 M1-tickers (energi):** BZ=F, CL=F, NG=F — alle 16.3 år historikk
  (2010-01-04+) ⇒ **GO**
- **Tier 2 M1-tickers (metaller + korn):** GC=F, SI=F, HG=F, PL=F, ZC=F,
  ZS=F, ZW=F — alle 16.3 år ⇒ **GO**
- **Spesifikke kontraktsmåneder** (CLM26.NYM, CLU26.NYM, CLZ26.NYM):
  8.3-8.4 år historikk per kontrakt ⇒ **RISK**
- **Implementasjon:** D2 (energi M1-front-month vs neste-måned-spread).
  Calendar-spread-driver beregner `front_month - next_month` fra
  pris-serien.
- **Smoke-script:** `scripts/smoke/b5_calendar_spreads.py`

### A1 Baker Hughes Rig Count — RISK

- **Endpoint:** `https://rigcount.bakerhughes.com/...`
- **Status:** Timeout fra denne arbeids-shellen (20s). Hovedsiden
  `bakerhughes.com` er tilgjengelig (200), men subdomenet `rigcount.bakerhughes.com`
  timeout — sannsynligvis DNS/firewall-blokkering fra denne shellen.
- **Forventet historikk:** 1944+ ukentlig (fre)
- **Anbefaling D1:** verifisere på annen maskin eller bruke alternativ
  kilde:
  - FRED-serie `IPN213111N` (US Oil & Gas Extraction Index, 1972+) —
    proxy-mål, ikke direkte rig count.
  - Manuell CSV-fallback fra dag 1 (per ADR-007 manuell-CSV-mønster).
- **Smoke-script:** `scripts/smoke/a1_baker_hughes.py`

### A5/A6/A7 ETF holdings (GLD/SLV/PPLT) — RISK

- **Endepunkter (alle HTTP 200):**
  - `https://www.spdrgoldshares.com/usa/historical-data/`
  - `https://www.ishares.com/us/products/239855/...`
  - `https://www.abrdn.com/en-us/etf/pplt`
- **Status:** Sider tilgjengelige men JS-rendret. Ingen direkte CSV/XLSX-
  lenker funnet via HTML-skraping.
- **Forventet historikk:** 2004+ (GLD), 2006+ (SLV), 2010+ (PPLT)
- **Anbefaling D2:** Reverse-engineer JSON/AJAX-API som cot-explorer
  gjorde. Manuell CSV-fallback fra dag 1. Yahoo-tickere GLD/SLV/PPLT
  gir markedspris (ikke fysiske holdings) som tertiær fallback.
- **Smoke-script:** `scripts/smoke/a5_a7_etf_holdings.py`

### A11 ICE certified stocks — RISK

- **Endepunkter:**
  - `https://www.theice.com/marketdata/reports/178` (Coffee) — **HTTP 404**
  - `https://www.theice.com/marketdata/reports/179` (Cocoa) — HTTP 200
  - `https://www.theice.com/marketdata/reports/180` (Sugar) — **HTTP 404**
- **Funn:** Rapport-IDer er inkonsistente. ICE har flyttet eller fjernet
  enkelte rapporter; Coffee+Sugar trenger ny URL-research.
- **Anbefaling D2:** Forsk ICE-API direkte via `theice.com/marketdata/`-
  navigasjon. Manuell CSV-fallback for Coffee+Sugar fra dag 1.
- **Smoke-script:** `scripts/smoke/a11_ice_certified_stocks.py`

### A3 FAS Export Sales — RISK

- **Endpoint:** `https://apps.fas.usda.gov/OpenData/api/esr/...`
- **Status:** HTTP 403 (Forbidden) på alle endpoints uten subscription-
  key.
- **Token-flyt (gratis registrering):**
  1. Registrer på `https://api.fas.usda.gov` (eller via api.gov-portal)
  2. Bekreft email
  3. Legg key i `~/.bedrock/secrets.env`: `FAS_API_KEY=<token>`
  4. Bruk header: `Ocp-Apim-Subscription-Key: <token>` i requests
- **Forventet historikk:** 1990+ ukentlig (tor 8:30 ET)
- **Anbefaling D1:** Token-registrering før implementasjon. Manuell CSV-
  fallback fra dag 1.
- **Smoke-script:** `scripts/smoke/a3_fas_export_sales.py`

### A2 AGSI EU gas storage — RISK

- **Endpoint:** `https://agsi.gie.eu/api`
- **Status:** HTTP 200, returnerer `{"error":"access denied","message":"Invalid or missing API key"}`.
  Endpoint er stabilt, men krever token.
- **Token-flyt (gratis registrering):**
  1. Registrer på `https://agsi.gie.eu/account`
  2. Bekreft email
  3. Legg key i `~/.bedrock/secrets.env`: `AGSI_API_KEY=<token>`
  4. Bruk header: `x-key: <token>`
- **Forventet historikk:** 2011+ daglig
- **Anbefaling D1:** Token-registrering før implementasjon. Per ADR-007
  manuell CSV-fallback fra dag 1.
- **Smoke-script:** `scripts/smoke/a2_agsi_eu_gas.py`

### A8 NOPA Crush Report — BLOCK

- **Endpoint:** `https://www.nopa.org/resources/nopa-monthly-crush-report/`
- **Funn:** Siden tilgjengelig (HTTP 200) men inneholder kun **release-
  kalender-PDF**, ikke selve crush-data. Den faktiske rapporten
  distribueres via **LSEG (Refinitiv) subscription** ("LSEG Release
  Dates (at Noon Eastern)").
- **Klassifikasjon:** **BLOCK** — paywall.
- **Anbefaling for D-fasen:** Drop fra B1/D2-scope. Alternativ for
  Soybean-fundamentals: `wasde_s2u_change` (allerede implementert) +
  `crop_progress_stage` (allerede implementert). NOPA crush var ment
  som tilleggssignal, ikke kritisk.
- **Smoke-script:** `scripts/smoke/a8_nopa_crush.py`

## D-fase-konsekvenser av smoke-test-utfall

### D1 (Tier 1) — endringer fra § 19.4-plan

**Originalt scope:** A1, A2, A3, A4 + C1, B1, B3.

- **Beholdes som GO:** A4 CFTC TFF + C1, B3 DXY Yahoo, B1 (9 av 11 FRED-serier).
- **Krever token-håndtering før implementasjon:** A2 AGSI, A3 FAS.
  Brukeren må registrere tokens før D1-fetcher-kode kan testes mot live
  endpoints. Manuell CSV-fallback fra dag 1 per ADR-007.
- **Verifisering kreves separat maskin:** A1 Baker Hughes (timeout fra
  arbeids-shell). FRED-fallback (`IPN213111N`) som tertiær.
- **Drop fra B1:** BAMLH0A0HYM2 + BAMLC0A0CM (HY/IG OAS) — kun 3 år
  historikk fra FRED gratis-API. Marker som data-gjeld i STATE.

### D2 (Tier 2) — endringer fra § 19.4-plan

**Originalt scope:** A5-A7 ETF, A8 NOPA, A9 USDM, A11 ICE, A12 AAII,
B2 VIX-term, B4 HDD/CDD, B5 cal-spreads (energi), C2 Eskom→Platinum,
C3 drop shipping.

- **Beholdes som GO:** A9 USDM, A12 AAII, B2 VIX-term, B5 cal-spreads
  M1 (energi BZ/CL/NG).
- **C2 DROPPED** ved D0-start (Eskom paywall, Platinum beholder seismic).
- **A8 NOPA DROPPED** — paywall (LSEG/Refinitiv).
- **Krever ekstra research:** A5/A6/A7 ETF (JSON-API reverse-engineering),
  A11 ICE (URL-research for Coffee+Sugar).
- **Manuell CSV-fallback:** A5/A6/A7, A11 — fra dag 1 per ADR-007.

### D3 (Tier 3) — endringer fra § 19.4-plan

**Originalt scope:** A10 Cecafé, B5 cal-spreads metaller/korn (hvis D0
viste Yahoo-curve), backtest-validering.

- **Beholdes som GO:** A10 Cecafé, B5 cal-spreads metaller/korn (alle
  Tier 2 M1-tickers GO med 16.3y historikk).
- **A10 backfill-utfordring:** URL-pattern må reverse-engineeres for å
  hente PDF-er pre-2026.

## Tech-gjeld for senere session

1. **`event_distance._now`-injeksjon** (R4-tech-gjeld 1) — utsatt til
   D1 eller pre-D1.
2. **Cross-module helper-import** (R4-tech-gjeld 2) — lazy-import-løsning
   fungerer; utsatt.
3. **B1 BAMLH0A0HYM2 + BAMLC0A0CM 3-års-historikk** (D0-funn) — D1 må
   undersøke alternativ kilde eller drop fra B1-scope.
4. **A1 Baker Hughes endpoint-timeout** — verifiseres på annen maskin
   før D1-implementasjon.
