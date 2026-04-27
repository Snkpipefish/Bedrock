# Manuelle data-kilder

Dette er manuelt-populert data for PLAN § 7.3-datakilder som ikke har
gratis API-tilgang eller er paid-only.

## Filer

| Fil | Schema | Hvor får du dataen? |
|---|---|---|
| `crop_progress.csv` | week_ending, commodity, state, metric, value_pct | NASS API (krever key) eller manuell nedlasting fra https://quickstats.nass.usda.gov/ |
| `wasde.csv` | report_date, marketing_year, region, commodity, metric, value, unit | https://www.usda.gov/oce/commodity-markets/wasde |
| `export_events.csv` | event_date, country, commodity, event_type, severity, bull_bear, description, source_url | News-monitoring (manuelt) — Reuters, Bloomberg, USDA FAS |
| `disease_alerts.csv` | alert_date, region, commodity, pathogen, severity, yield_impact_pct, description, source_url | PestMon, CABI, FAO Crop Prospects |
| `bdi.csv` | date, value, source | Trading Economics, Bloomberg, eller manuell daglig registrering |
| `cot_ice.csv` | report_date, contract, mm_long/short, other_long/short, comm_long/short, nonrep_long/short, open_interest | https://www.ice.com/publicdocs/futures/COTHist{YEAR}.csv (manuell nedlasting hvis prod-host blokkeres) |
| `eia_inventory.csv` | series_id, date, value, units | https://www.eia.gov/petroleum/supply/weekly/ + https://ir.eia.gov/ngs/ngs.html (kun hvis API-key mangler) |
| `comex_inventory.csv` | metal, date, registered, eligible, total, units | https://metalcharts.org/ eller CME-publiserte daglige stats (kun hvis primær HTTP-kilde feiler) |
| `seismic_events.csv` | event_id, event_ts, magnitude, latitude, longitude, depth_km, place, region, url | https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson (manuell hvis USGS ikke tilgjengelig) |

## Format-eksempler

### crop_progress.csv

```csv
week_ending,commodity,state,metric,value_pct
2024-05-12,CORN,US TOTAL,PLANTED,75
2024-05-12,CORN,US TOTAL,GOOD_EXCELLENT,68
2024-07-21,CORN,US TOTAL,SILKING,82
```

### wasde.csv

```csv
report_date,marketing_year,region,commodity,metric,value,unit
2024-09-12,2024/25,US,CORN,ENDING_STOCKS,2057,MIL_BU
2024-09-12,2024/25,US,CORN,YIELD,183.6,BU_ACRE
2024-09-12,2024/25,US,CORN,S2U,14.0,PCT
```

### export_events.csv

```csv
event_date,country,commodity,event_type,severity,bull_bear,description,source_url
2023-07-20,INDIA,RICE,EXPORT_BAN,5,BULL,"India bans non-basmati white rice exports",https://www.reuters.com/...
2024-09-15,IVORY COAST,COCOA,QUOTA,4,BULL,"Ivory Coast announces 30% export quota cut for 2024-25",https://www.bloomberg.com/...
```

### disease_alerts.csv

```csv
alert_date,region,commodity,pathogen,severity,yield_impact_pct,description,source_url
2024-08-01,BRAZIL,COFFEE,COFFEE_RUST,3,5.0,"Hemileia vastatrix outbreak in Minas Gerais",https://...
2025-04-10,AUSTRALIA,WHEAT,STRIPE_RUST,2,2.5,"Localized stripe rust in WA wheat belt",https://...
```

### bdi.csv

```csv
date,value,source
2025-04-15,1845.0,MANUAL
2025-04-16,1862.0,MANUAL
2025-04-17,1834.0,TRADINGECONOMICS
```

### cot_ice.csv

ICE Futures Europe COT (Brent, Gasoil, TTF Natural Gas). Bedrock-canonical
contract-strenger: `ice brent crude`, `ice gasoil`, `ice ttf gas`. Tall
matcher CFTC disaggregated-format som ICE publiserer i (samme kolonner
som `cot_disaggregated`).

```csv
report_date,contract,mm_long,mm_short,other_long,other_short,comm_long,comm_short,nonrep_long,nonrep_short,open_interest
2026-04-22,ice brent crude,180000,95000,40000,32000,520000,610000,18000,21000,1450000
2026-04-22,ice gasoil,55000,42000,18000,15000,210000,225000,9000,10000,485000
```

### eia_inventory.csv

EIA weekly inventories. Default series:
- `WCESTUS1` — US Crude Oil Stocks excl. SPR (MBBL)
- `WGTSTUS1` — US Total Gasoline Stocks (MBBL)
- `NW2_EPG0_SWO_R48_BCF` — US Working Natural Gas Storage Lower 48 (BCF)

Brukes kun hvis API-key mangler (registrer gratis på
https://www.eia.gov/opendata/register.php og sett `BEDROCK_EIA_API_KEY`
i `~/.bedrock/secrets.env`).

```csv
series_id,date,value,units
WCESTUS1,2026-04-17,465729,MBBL
WGTSTUS1,2026-04-17,228374,MBBL
NW2_EPG0_SWO_R48_BCF,2026-04-17,2063,BCF
```

## Workflow for å populere

1. **Daglig/ukentlig**: Sjekk Reuters/Bloomberg agri-news for eksport-policy events. Append-er til `export_events.csv` med severity 1-5.
2. **Månedlig (rundt 10. hver måned)**: Last ned WASDE-rapporten og oppdater `wasde.csv` (eller la auto-fetcher prøve første).
3. **Ukentlig (mandag-mandag)**: Hvis NASS API-key ikke er konfigurert, last ned crop progress fra QuickStats web-UI manuelt.
4. **Per-need**: Disease/pest-alerts fra FAO Crop Prospects.

## Auto-fetcher status

| Source | Auto-fetcher | Krever | Fallback |
|---|---|---|---|
| NASS Crop Progress | `bedrock.fetch.nass` | `BEDROCK_NASS_API_KEY` env-var | manuell CSV |
| WASDE | `bedrock.fetch.wasde` | direkte HTTPS til USDA (kan endre seg) | manuell CSV |
| Eksport-events | — | manuell curation | manuell CSV |
| Disease-alerts | — | manuell curation (paid services finnes) | manuell CSV |
| BDI | — | paid feed (Trading Economics, Bloomberg) | manuell CSV |
| ICE COT | `bedrock.fetch.cot_ice` | direkte HTTPS til ICE COTHist{YEAR}.csv | manuell CSV |
| EIA Inventories | `bedrock.fetch.eia_inventories` | EIA Open Data v2 + `BEDROCK_EIA_API_KEY` | manuell CSV |
| COMEX Inventories | `bedrock.fetch.comex` | metalcharts.org JSON-API (token-basert, ingen key) | manuell CSV |
| USGS Seismic | `bedrock.fetch.seismic` | USGS GeoJSON feed (M≥4.5 siste 7d, ingen key) | manuell CSV |
