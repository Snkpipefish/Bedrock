# ADR-008: Per-fetcher mapping for sub-fase 12.5+

Dato: 2026-04-27
Status: accepted
Fase: 12.5+ (sessions 105-117)
Refererer til: ADR-007 (fetch-port strategi), PLAN § 7.5

## Kontekst

ADR-007 låste *strategien* for porting av 11 cot-explorer-fetchere
(3 port-typer, manuell CSV-fallback, sentiment-fetchere som UI-only).
Denne ADR-en låser **per-fetcher mapping**: hvilken bedrock-modul,
hvilken DB-tabell, hvilken cron, hvilken driver, hvilke instrumenter.

Tabellen er en kontrakt mellom session 105 (calendar_ff) og session 117
(cutover-readiness). Endringer krever ny ADR.

## Mapping-tabell

| Sess | cot-explorer-modul | bedrock-modul | DB-tabell | Cron (Oslo) | Stale_h | Driver | Instrumenter | Type |
|---|---|---|---|---|---|---|---|---|
| 105 | `fetch_calendar.py` | `fetch/calendar_ff.py` | `econ_events` | `15 */6 * * *` | 8 | `event_distance` | alle 22 | full driver-port |
| 106 | `fetch_ice_cot.py` | `fetch/cot_ice.py` | `cot_ice` | `30 22 * * 5` | 168 | `cot_ice_mm_pct` | Brent (primær), NaturalGas (TTF-overlay) | full driver-port |
| 107 | `fetch_oilgas.py` (kun EIA) | `fetch/eia_inventories.py` | `eia_inventory` | `30 17 * * 3` | 200 | `eia_stock_change` | CrudeOil, Brent, NaturalGas | full driver-port (resten droppet — duplikat) |
| 108 | `fetch_comex.py` | `fetch/comex.py` (+ CSV-fallback) | `comex_inventory` | `0 22 * * 1-5` | 30 | `comex_stress` | Gold, Silver, Copper | full driver-port |
| 109 | `fetch_seismic.py` | `fetch/seismic.py` | `seismic_events` | `0 4 * * *` | 30 | `mining_disruption` | Gold, Silver, Copper, Platinum | full driver-port |
| 110 | `fetch_euronext_cot.py` | `fetch/cot_euronext.py` (+ CSV-fallback) | `cot_euronext` | `0 18 * * 3` | 168 | `cot_euronext_mm_pct` | Wheat, Corn (EU-overlay) | full driver-port |
| 111 | `fetch_conab.py` | `fetch/conab.py` (PDF) | `conab_estimates` | `0 20 15 * *` | 720 | `conab_yoy` | Corn, Soybean, Coffee | full driver-port |
| 112 | `fetch_unica.py` | `fetch/unica.py` (PDF) | `unica_crush` | `0 21 * * 1` | 360 | `unica_mix` | Sugar | full driver-port |
| 113 | `fetch_shipping.py` | `fetch/shipping.py` (utvider `bdi`) | `shipping_indices` (rename av `bdi`) | `35 23 * * 1-5` | 30 | `shipping_pressure` (utv. av `bdi_chg30d`) | Wheat, Soybean, Corn | konsolidering |
| 114 | `fetch_intel.py` | `fetch/news_intel.py` | `news_intel` | `0 */4 * * *` | 8 | (ingen) | (ingen) | UI-context only |
| 115 | `fetch_crypto.py` | `fetch/crypto_sentiment.py` | `crypto_sentiment` | `30 */4 * * *` | 8 | (ingen) | (ingen) | UI-context only |

Cron-verdier i lokal Oslo TZ (per § 7.4). Minutt-feltet er valgt
off-:00/:30 for å spre last på datakildene. `Persistent=true` på
alle systemd-timere → catch-up ved boot.

## Detaljer per fetcher

### 105 — calendar_ff (Forex Factory)

- Kilde: `https://nfs.faireconomy.media/ff_calendar_thisweek.json`
- Felter: `country`, `title`, `date` (ISO UTC), `impact` (High/Medium/Low),
  `forecast`, `previous`.
- Filtrering ved fetch-tid: kun `impact ∈ {High, Medium}`.
- Country-mapping per instrument: `USD → all USD-baserte`, `EUR → EURUSD`,
  `GBP → GBPUSD`, `JPY → USDJPY`, `AUD → AUDUSD` (per cot-explorer-presedens).
- Driver `event_distance(min_hours=4, impact_levels=['High'], countries=...)`:
  returnerer 1.0 hvis ingen relevant event innenfor `min_hours`,
  ellers lineært ned mot 0.0 ved hours_to_event=0.
- Wiring:
  - **15 financial:** add to `risk`-familie. `vol_regime` 1.0 → 0.7,
    `event_distance` 0.3.
  - **7 agri:** add to `cross`-familie. Sub-vekt 0.1, andre redistribueres.

### 106 — cot_ice

- Kilde: ICE Excel-filer (Brent, Gasoil, TTF Natural Gas).
- Schema parallell til CFTC disaggregated (managed_money, comm, non-rep).
- Brent får ny primær COT-kilde (er listet på ICE, ikke CFTC).

### 107 — eia_inventories

- Kilde: EIA STEO/PSI-CSV (US oil/gas weekly inventories).
- Drop *priser* og *nyheter* fra cot-explorer's fetch_oilgas (duplikat med
  Yahoo + cot_cftc + news_intel).

### 108 — comex (med CSV-fallback fra dag 1)

- Primær: metalcharts.org HTML scrape.
- Fallback: `data/manual/comex_inventory.csv` (samme mønster som NASS).

### 109 — seismic

- Kilde: USGS GeoJSON (M ≥ 4.5 siste 7 dager).
- Region-filtre: Chile/Peru, Mexico, USA/Canada, DRC/Zambia, Australia.
- Driver returnerer 0..1 basert på siste seismic-aktivitet i mining-regioner.

### 110 — cot_euronext (med CSV-fallback fra dag 1)

- Primær: Euronext per-produkt HTML-rapporter.
- Fallback: `data/manual/cot_euronext.csv`.
- MiFID II-kategorier: Investment Funds (≈ Managed Money), Investment Firms,
  Commercial, Other Financial.

### 111 — conab (PDF via poppler-utils)

- Brazil corn/soybean/coffee crop estimates.
- pdftotext primær; pypdf fallback (ADR-007 § 6).

### 112 — unica (PDF via poppler-utils)

- Brazil center-south sugar mix (sugar % vs ethanol %).
- Halvmånedlig publisering.

### 113 — shipping (konsolidering)

- Eksisterende `bdi`-fetcher (session 89) utvides til full Baltic-suite:
  BDI, BCI (Capesize), BPI (Panamax), BSI (Supramax).
- Tabell `bdi` renames til `shipping_indices` med kolonner per index.
- Driver `bdi_chg30d` rebrandes til `shipping_pressure` med `index=BDI|BPI|...`-param.
- Migrering: SQL ALTER TABLE eller fresh-migrasjon (avgjøres i session 113).

### 114 — news_intel (UI-only)

- Google News RSS: gold, silver, copper, oil, gas-related categories.
- Schema: per-event row med (date, category, title, source, url, sentiment_label).
- Ingen driver. UI-tab ny "Markedsnytt" eller utvidet "Kartrommet"-info.

### 115 — crypto_sentiment (UI-only)

- alternative.me Fear & Greed Index (daily 0-100).
- CoinGecko market data (BTC/ETH dominance, total market cap).
- Schema: (date, indicator, value).
- Ingen driver. Vises i UI på BTC/ETH-kort.

## Schema-konvensjoner

- Tabell-navn: snake_case, kort, beskrivende.
- PK på (id-felter, ts/date) for idempotent INSERT OR REPLACE.
- ISO-datoer som TEXT (SQLite-konvensjon).
- Numeriske verdier som REAL.
- Categorical felter som TEXT (ikke ENUM; SQLite har ikke enum).
- `EconomicEvent` (105): se schema i `bedrock/data/schemas.py`.

## Konsekvenser

- Total bedrock-fetcher-count etter session 115: 9 + 11 = **20 fetchere**.
- Total driver-count etter session 113: 22 + 9 driver-ports = **31 drivere**
  (calendar 1, cot_ice 1, eia 1, comex 1, seismic 1, cot_euronext 1,
  conab 1, unica 1, shipping 1 ny). News_intel + crypto_sentiment har ingen driver.
- Total instrument-YAML-coverage: alle 22 får event_distance via session 105.

## Refererer til

- ADR-007 (fetch-port-strategi)
- PLAN § 7.5 (roadmap-tabell)
- ADR-002 (SQLite som data-lag)
