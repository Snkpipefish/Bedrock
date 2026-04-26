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
