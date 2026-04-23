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
