# ADR-010: Horisont-bevisst driver-pattern

Dato: 2026-04-28
Status: accepted
Fase: 12.7 R1 (session 119)
Refererer til: ADR-006 (direction-asymmetric scoring, presedens),
PLAN § 19, `docs/horizon_refactor_audit.md`

## Kontekst

Dagens drivere returnerer én skalar `0..1` per kall. `Engine.score(...,
horizon, direction)` propagerer retning ned til driver-laget via en
intern `_direction`-key i en kopi av `params` (ADR-006), men horisonten
konsumeres allerede i `_score_financial` og er borte før `_score_families`
kjører — drivere har ingen måte å vite om scoring-en gjelder SCALP,
SWING eller MAKRO.

Sub-fase 12.7 (PLAN § 19) tar inn flere data-kilder hvor samme rådata
har **ulik signal-verdi per horisont** (CFTC TFF: 12m percentil →
MAKRO, ukentlig delta → SWING, mandag-gap → SCALP. Baker Hughes,
VIX-termstruktur, AAII, FAS Export Sales: tilsvarende). Hvis hver
kilde implementeres som tre uavhengige drivere, vokser registry 3×
og feature-engineering dupliseres.

Tre alternativer ble vurdert i `docs/horizon_refactor_audit.md`. Alt 1
(YAML-styrt `_horizon`-param via engine-propagering) ble valgt.

## Beslutning

Engine setter en `_horizon`-key i en kopi av driver-`params`, analogt
med ADR-006s `_direction`. Driver-kontrakten er uendret. Drivere som
er horisont-bevisste leser `params["_horizon"]` og velger feature;
horisont-uavhengige drivere ignorerer key-en og kjører bit-identisk
som før.

Konkret patch i `_score_families`:

    params_with_dir = {
        **driver_spec.params,
        "_direction": direction.value,
        "_horizon": horizon,  # NY — None for agri
    }

`_score_families` tar `horizon: str | None` som ny parameter.
`_score_financial` sender sin horizon-streng (`"SCALP"` / `"SWING"` /
`"MAKRO"`); `_score_agri` sender `None`. Engine.score() selv har
ingen signatur-endring (den tok allerede `horizon`-arg).

## Konsekvenser

### Positive

- Minimal engine-endring (~5 linjer + 1 nytt argument til intern
  helper).
- Driver-kontrakten `(store, instrument, params) -> float` er
  bevart. Eksisterende ~22 drivere trenger ingen endring.
- Snapshot-tester gir bit-identisk score for alle horisont-
  uavhengige drivere ut av boksen — score-uendret-garantien (PLAN
  § 19.1) er enkel å verifisere.
- Konsistent med ADR-006 — neste driver-utvikler ser umiddelbart at
  `_horizon` følger samme mønster som `_direction`.
- For agri (horizon=None på engine-siden) er mønstret nedwards-
  kompatibelt: agri-drivere som trenger horisont-info kan ta det
  som vanlig YAML-param, eller R2 kan etablere driver-intern
  kalender-aware-mønster (sesong-drivere).

### Negative

- Driver-koden må eksplisitt sjekke `params.get("_horizon")` der
  det er relevant. Ikke selv-dokumenterende på signaturen. Mitigeres
  ved å oppdatere `docs/driver_authoring.md` til å nevne både
  `_direction` og `_horizon` som engine-injiserte kontekst-keys, og
  ved at R2 etablerer en standard feature-konvensjon
  (`pct_12m`/`delta_5d_z`/...) som horisont-bevisste drivere
  forholder seg til.

### Nøytrale

- Antall engine.score()-kall per signals-regenerering er uendret
  (104 i dag: 15 financial × 3 × 2 + 7 agri × 1 × 2). R1 endrer
  ingen YAML, ingen aggregator-logikk og ingen grade-terskler.
- Bot/signal_server-API-en og UI er upåvirket. Hele endringen er
  internt i engine-pakken.

## Alternativer vurdert

### Alt 2 — Per-horisont driver-instans i YAML

Hver multi-horisont-kilde får tre driver-navn (`tff_makro`,
`tff_swing`, `tff_scalp`) med hardkodet horisont per driver.

- Pro: Selv-dokumenterende navn. Ingen engine-endring.
- Con: Driver-registry tredobles per ny multi-horisont-kilde.
  Feature-engineering dupliseres eller pakkes i privat helper —
  begge er komplikasjoner Alt 1 unngår. YAML blir lengre og mer
  feilutsatt; hver familie må peke på riktig horisont-variant per
  instrument.

### Alt 3 — Endret driver-signatur

Driver-kontrakten utvides til `(store, instrument, params, horizon)
-> float`.

- Pro: Selv-dokumenterende på signaturen.
- Con: Bryter alle 22 eksisterende drivere + ~150 driver-tester
  (samme situasjon som Alt A i ADR-006 — eksplisitt forkastet).
  STATE invariants låser driver-kontrakten "fra Fase 1"; en endring
  her ville kreve egen ADR for selve kontrakts-bruddet og en
  migrerings-syklus før vi engang kan begynne på data-utvidelsen.

## Referanser

- `docs/horizon_refactor_audit.md` — full audit + sammenlignings-
  tabell mellom Alt 1/2/3.
- ADR-006 — direction-asymmetric scoring (presedens for engine-
  injisert kontekst-key).
- PLAN § 19.3 — låste beslutninger (Alt 1 valgt 2026-04-28).
- PLAN § 19.4 — fase-tabell (R1 leverer ADR-010 + engine-patch).
- `src/bedrock/engine/engine.py:345-401` — `_score_families`,
  patche-target.
- `tests/unit/test_engine_direction_polarity.py` — test-mønster
  for ADR-006 som R1 speiler.
