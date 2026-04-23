# Commit-konvensjon

Vi følger [Conventional Commits](https://www.conventionalcommits.org) med Bedrock-spesifikke
type-er. Håndheves av `commitizen` pre-commit-hook.

## Format

```
type(scope): subject

[body]

[footer: BREAKING CHANGE, Co-Authored-By, Refs, etc.]
```

**Imperativ** ("add" ikke "added"). Subject < 72 tegn, uten punktum på slutten.

## Typer

| Type | Når |
|---|---|
| `feat` | Ny funksjonalitet (ny driver, nytt endpoint, ny config-nøkkel) |
| `fix` | Bug-fix |
| `refactor` | Kode-endring uten atferds-endring |
| `perf` | Ytelses-forbedring uten atferds-endring |
| `docs` | Bare dokumentasjon (README, PLAN, docs/, docstrings) |
| `test` | Legge til eller fikse tester uten kode-endring |
| `chore` | Dependency-oppdatering, build-config, CI, pre-commit |
| `config` | Endring i `config/*.yaml` (instrument-regler, terskler) |
| `state` | Endring i `STATE.md` (holdes separat fra kode-commits) |

## Scopes

Komponent-navn eller mappenavn:

- `engine`, `drivers`, `aggregators`, `grade`, `explain`
- `setups`, `levels`, `horizon`, `generator`
- `data`, `store`, `backfill`, `analogs`
- `fetch`, `fetch-cot`, `fetch-prices`, `fetch-agri`, ...
- `signals`, `schema`, `publisher`
- `server`, `server-routes`, `server-admin`
- `bot`, `bot-entry`, `bot-exit`, `bot-sizing`
- `pipeline`, `gates`, `hourly`, `main-cycle`
- `cli`
- `ui`, `admin`
- `tests`, `tests-logical`, `tests-backtest`
- `docs`
- `ci`, `build`

## Eksempler

### Bra

```
feat(engine): implement weighted_horizon aggregator

Første aggregator. Leser horizon-vekter fra YAML, kombinerer familie-scores
med multiplikasjon, returnerer GroupResult. Støtter overstyring per instrument
via rules.horizons.<h>.family_weights.

Logiske tester for Gold SWING/MAKRO, 4 scenarier grønne.

Co-Authored-By: Claude <noreply@anthropic.com>
```

```
fix(bot): remove agri ATR override on t1

Boten overstyret signal.t1 med entry + 2.5×ATR for agri-instrumenter,
hvilket forårsaket for små take-profits. Fjernet; bot respekterer nå
signal.t1 som sendt av setup-generator.

Regresjonstest verifiserer at Corn/Sugar/Coffee-signaler ikke får TP
omskrevet.

Refs #12
```

```
config(instruments): tune gold structure family weights for SWING

Strukturfamilien var for dominerende i SWING (1.3 vekt) — flyttet til
1.0 for å gi positioning+macro mer plass. Dry-run mot 2024-historikk
viser 3 færre falske A+, 1 ekte mistet.

Backtest-rapport: docs/backtest/gold_2024_struct_weight.md
```

```
refactor(bot): split trading_bot.py into 8 modules

Ingen atferds-endring. Splitter 2977-linjers fila i ctrader_client,
entry, exit, sizing, state, safety, comms, __main__. Alle eksisterende
tester grønne; 4 nye regresjonstester for entry-gates.

Co-Authored-By: Claude <noreply@anthropic.com>
```

```
state: session 7 avsluttet, neste er exit.py
```

```
docs(plan): expand § 5 with hysterese-details for setup generator
```

### Dårlige eksempler (avvist av hook)

```
Updated some files
```
→ Ingen type, ingen scope, ikke imperativ.

```
feat: add thing
```
→ Mangler scope, subject er ubeskrivende.

```
feat(engine): Added new aggregator.
```
→ "Added" skal være "add". Ingen punktum.

```
wip
```
→ WIP-commits er OK på branch hvis de er tydelige (`wip(engine): exploring...`),
men aldri som standalone. Squash-merge fjerner dem uansett før main.

## Commit-body: når og hvordan

Skriv body hvis:
- Endringen har ikke-åpenbare konsekvenser
- Du fjerner noe (forklar hvorfor)
- Du velger A over B når begge var mulige
- Det er en bug-fix (forklar root-cause, ikke bare symptom)

Body forklarer **hvorfor**, subject forklarer **hva**. Diff forklarer **hvordan**.

## Footers

- `Co-Authored-By: Claude <noreply@anthropic.com>` på alle Claude Code-commits
- `Refs #N` eller `Closes #N` ved issue-referanse
- `BREAKING CHANGE: <beskrivelse>` ved schema-brudd eller API-endring

## Claude Code-spesifikt

Claude Code skal alltid:
1. Bruke dette formatet
2. Inkludere Co-Authored-By-linjen
3. Commite STATE.md-endringer separat med `state: ...`-type
4. Skrive body når endringen ikke er triviell
5. Aldri bruke `wip:`-type på main-merge

## Tag-konvensjon ved fase-slutt

```
git tag -a v0.1.0-fase-1 -m "Engine core + 10 drivere ferdig"
git push origin v0.1.0-fase-1
```

Versjon-mønster:
- `v0.X.0-fase-Y` — fase-slutt-tagger under utvikling
- `v1.0.0` — første live-cutover (Fase 12)
- `v1.X.0` — ny feature/refaktor etter live
- `v1.X.Y` — patch etter live
