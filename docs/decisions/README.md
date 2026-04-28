# Architecture Decision Records (ADR)

Kort-format for å dokumentere *hvorfor* arkitektur-valg ble tatt. Hver ADR er
immutabel etter skriving — nye beslutninger som erstatter gamle får ny ADR som
refererer den forrige som "superseded".

## Mal

```markdown
# ADR-<nr>: <kort tittel>

Dato: YYYY-MM-DD
Status: proposed | accepted | superseded by ADR-NN | deprecated
Fase: <hvilken fase i PLAN.md>

## Kontekst

Hva er problemet? Hvilke krefter er i spill? Hva valgte vi *ikke*?

## Beslutning

Én eller to setninger: hva valgte vi?

## Konsekvenser

Positive:
- ...

Negative:
- ...

Nøytrale (men verdt å nevne):
- ...

## Alternativer vurdert

- **Alternativ A:** ...
  - Pro: ...
  - Con: ...
- **Alternativ B:** ...

## Referanser

- PLAN.md § X
- Tidligere diskusjoner: session N
```

## Indeks

| # | Tittel | Status | Fase |
|---|---|---|---|
| [001](001-one-engine-two-aggregators.md) | Én Engine, to aggregatorer | accepted | 1 |
| [002](002-sqlite-instead-of-duckdb.md) | SQLite + pandas som storage-backend | accepted | 2 |
| [003](003-gates-via-named-registry-not-dsl.md) | Gates via named-function registry, ikke string-DSL | accepted | 5 |
| [004](004-python-3-10-baseline.md) | Python 3.10 baseline | accepted | 1 |
| [005](005-analog-data-schema.md) | Analog data schema | accepted | 7 |
| [006](006-direction-asymmetric-scoring.md) | Direction-asymmetric scoring | accepted | 12 (95b) |
| [007](007-fetch-port-strategy.md) | Fetch-port-strategi | accepted | 12.5 |
| [008](008-fetch-port-mapping.md) | Per-fetcher mapping | accepted | 12.5 |
| [009](009-cutover-readiness.md) | Cutover-readiness 12.5+ → 12.6 → Fase 13 | accepted | 12.5+ |
| [010](010-horizon-aware-driver-pattern.md) | Horisont-bevisst driver-pattern (Alt 1) | accepted | 12.7 (R1) |
| [011](011-backfill-policy.md) | Backfill-policy for engangs-historikk-skripts | accepted | 12.7 (R1) |
