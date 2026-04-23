# ADR-001: Én Engine, to aggregatorer

Dato: 2026-04-24
Status: accepted
Fase: 1

## Kontekst

Bedrock scorer to veldig forskjellige asset-klasser:

1. **Financial** (FX, metals, energy, indices, crypto). Bruker horisont-spesifikke
   familie-vekter: Trend vektes høyt for SCALP, Positioning/Macro vektes høyt for
   MAKRO, etc. Hver horisont har sin egen `max_score` og sin egen weight-vektor
   per familie. Total-score er en *vektet sum* av familie-scores.

2. **Agri** (grains, softs). Har ikke horisont-splitt på scoring-siden. Hver
   familie har en fast cap i YAML (f.eks. `outlook: 5`, `yield: 3`, etc.), og
   total er *additiv sum* av familie-bidragene med fast total-max (typisk 18).

Aggregering er altså strukturelt forskjellig, men alt rundt (driver-signatur,
driver-registry, per-familie-løkke, explain-trace, grade-terskler) er
strukturelt likt.

## Beslutning

**Én `Engine`-klasse.** YAML velger aggregator ved navn (`aggregation:
weighted_horizon` eller `aggregation: additive_sum`). Engine slår opp
aggregator-funksjonen og anvender den på `dict[family_name, family_score]`.
Driver-registry og familie-løkke er felles.

Aggregator-funksjonene ligger i `bedrock.engine.aggregators` og har ingen felles
signatur utover at de mottar `family_scores: dict[str, float]` og returnerer en
`float`. Øvrige argumenter (horisont-vekter for financial, familie-caps for
agri) er aggregator-spesifikke og tas ut av `rules` av Engine før kall.

## Konsekvenser

Positive:
- Én driver-kontrakt. Drivere kan gjenbrukes på tvers av asset-klasser
  (f.eks. en DXY-momentum-driver kan være relevant for både Gold og Sugar).
- Ny asset-klasse i fremtiden = ny aggregator-funksjon. Ingen ny Engine.
- Explain-trace-formatet er felles, så UI + CLI + signal-builder trenger ikke
  kjenne til asset-klasse-forskjeller.
- YAML styrer valg av aggregator — prinsipp 1 (konfig, ikke kode).
- Tester kan parameteriseres på tvers av aggregatorer med samme `Engine`-fikstur.

Negative:
- Aggregator-funksjonene har ulike signaturer (ikke én felles Protocol).
  `Engine` må derfor ha en liten dispatch-gren per aggregator-navn.
  Dette er akseptabelt — forventet antall aggregatorer er lite (2-3 over
  prosjektets levetid), og alternativet ville vært en tvunget generisk
  signatur som hvert spesialtilfelle likevel måtte plukke fra.

Nøytrale (verdt å nevne):
- Per-horisont-logikk (SCALP/SWING/MAKRO) ligger i `weighted_horizon` og i
  YAML-horisonten — ikke i `Engine`. `Engine.score()` tar `horizon` som
  parameter. For agri er `horizon` ignorert (eller standardisert til én dummy-
  horisont i agri-YAML-en); setup-generator (Fase 4) tildeler horisont basert
  på setup-karakteristikk, ikke score.
- I Fase 1 session 2 er kun `weighted_horizon` implementert. `additive_sum`
  kaster `NotImplementedError` slik at agri-YAML eksplisitt feiler inntil agri-
  støtten legges til.

## Alternativer vurdert

- **Alternativ A — to separate Engine-klasser (`FinancialEngine`, `AgriEngine`).**
  Pro: null dispatch-logikk. Con: duplikasjon i driver-invocation, explain-trace,
  grade-terskel-håndtering. Hver gang noe utvides må begge klasser vedlikeholdes.
  Forkastet.

- **Alternativ C — én Engine med stor if/else per asset-klasse internt i
  `Engine.score()`.**
  Pro: ingen separasjon av aggregator-modul. Con: skalerer ikke — hvis/når en
  tredje asset-klasse (f.eks. krypto-spesifikk) kommer, må `score()` voksle enda
  en gren. Bryter åpen-for-utvidelse. Forkastet.

## Referanser

- `PLAN.md` § 4 (scoring-motor)
- `PLAN.md` § 4.2 (Gold/financial YAML-eksempel) og § 4.3 (Corn/agri YAML-eksempel)
- `CLAUDE.md` (designprinsipp: "én motor, to aggregatorer")
