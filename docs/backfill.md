# Backfill — historisk data

Stub. Utfylles i Fase 3.

## Mål-horisonter

| Kilde | Fra | Notat |
|---|---|---|
| Priser (stooq/yahoo) | 2016-01-01 (10 år) | Daglig OHLCV per instrument × TF |
| CFTC COT disaggregated | 2010 | Ukentlig |
| CFTC legacy | 2006 | Ukentlig |
| ICE COT | 2018 | Ukentlig — Brent/Gasoil |
| Euronext COT | 2018 | Ukentlig — hvete/raps/mais |
| FRED fundamentals | 2016 | Daglig/ukentlig/månedlig varierer per serie |
| ERA5 vær | 15 år (har allerede) | Månedlige aggregater per region |
| Conab | 2020 | Månedlig |
| UNICA | 2020 | Halvmånedlig |

## CLI

Kommer i Fase 3:

```bash
uv run bedrock backfill prices --instruments all --from 2016-01-01
uv run bedrock backfill cot --report disaggregated --from 2010-01-01
uv run bedrock backfill weather --regions all --from 2011-01-01
```

Hver backfill skriver til `data/parquet/<kilde>/<instrument_eller_region>.parquet`.
Inkremental: kun nye rader appenderes ved senere kjøringer.
