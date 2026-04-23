# Arkitektur

Skeleton-dokument. Utvides i Fase 1-2 når hovedkomponenter får sine første
implementasjoner. Komplett overordnet arkitektur beskrevet i `PLAN.md` § 3.

## Dataflyt (fra PLAN.md)

```
    fetch/*                    setups/                 engine/                    signals/
    (rå I/O)                   (generator)             (scoring)                  (publisering)
        │                          │                       │                          │
        ▼                          ▼                       ▼                          ▼
  data/latest/*.json     data/setups/active.json    (in-memory GroupResult)    signals.json
  data/parquet/*.parquet         ▲                       ▲                          │
        │                        │                       │                          ▼
        └──► analogs.py ◄────────┘                       │               signal_server /push-alert
                                                         │                          │
                                                  rules/*.yaml                       ▼
                                                 drivers/*.py                  bot polls /signals
                                                                                      │
                                                                                      ▼
                                                                              cTrader execution
                                                                                      │
                                                                                      ▼
                                                                           data/signal_log.json
```

## Komponent-avhengigheter

Regel: avhengigheter går i én retning, nedover. Ingen sirkulære imports.

```
cli/          → pipeline/
pipeline/     → fetch/ + setups/ + engine/ + signals/ + server/ (via HTTP)
signals/      → engine/ + setups/
engine/       → drivers/ + data/
setups/       → data/
fetch/        → data/ (skriver)
data/         → (ingenting — bunn-lag)
server/       → signals/ (schema) + data/ (lese)
bot/          → server/ (via HTTP)
```

## Skjema-kontrakt

Signal-schema v1 låst som Pydantic-modell i `src/bedrock/signals/schema.py`.
Bot leser kun v1-felter. `extras: dict[str, Any]` gir plass til eksperimentelle
felter uten schema-brudd.

Full beskrivelse: `docs/data_contract.md` (Fase 1).

## Config-arv

```
config/defaults/base.yaml
        ↑ extends
config/defaults/family_financial.yaml  +  family_agri.yaml
        ↑ inherits                          ↑ inherits
config/instruments/gold.yaml           +  corn.yaml, coffee.yaml, ...
```

Alle leses ved pipeline-start via `src/bedrock/engine/config_loader.py` (Fase 1).
YAML-feil = hard fail, ingen lydløs fallback.

## Nøkkel-arkitektur-beslutninger (ADR-er)

Se `docs/decisions/` for individuelle ADR-er. Første som skrives i Fase 1:

- ADR-001: én engine + to aggregatorer vs to engines
- ADR-002: DuckDB + parquet vs ArcticDB for historikk
- ADR-003: YAML-DSL-grenser (ingen uttrykk i YAML)
- ADR-004: determinisme + hysterese vs setup-lifecycle
- ADR-005: Flask vs FastAPI for signal-server

Mal: `docs/decisions/README.md`
