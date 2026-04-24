# Bedrock — state

## Current state

- **Phase:** 6 — åpen. Session 28 FERDIG: config-drevet fetch-cadence — `config/fetch.yaml` + Pydantic-schema + `bedrock.config.fetch` staleness-modul + `bedrock fetch status` CLI.
- **Branch:** `main` (jobber direkte på main under utvikling, Nivå 1-modus)
- **Blocked:** nei
- **Next task:** Session 29 — `bedrock fetch run [--stale-only]`-subkommando som faktisk kjører fetchere basert på config. Bygger på session 28's FetcherSpec + check_staleness. Krever en dispatcher: gitt `module: bedrock.fetch.prices`, kjør tilsvarende fetch-funksjon. Enklest approach: mapping `module → (fetcher, required_params)` siden hver fetcher har forskjellig signatur. Instrument-config brukes for params (allerede støttet i backfill). Begrunnelse for rekkefølge: run er naturlig neste skritt etter status (status viser HVA som er stale, run kjører dem). Cron-daemon/systemd-integrasjon kommer etter run fungerer.
- **Git-modus:** Nivå 1 (commit direkte til main, auto-push aktiv). Bytter til Nivå 3 (feature-branches + PR) ved Fase 10-11.

## Open questions to user

- Skal pre-commit-hooks (ruff/yamllint/commitizen) aktiveres nå eller venter
  vi til `uv sync` er kjørt? Per nå committer vi uten pre-commit-validering.
- PLAN § 10.6 (alt editerbart via admin-UI, YAML auto-committes): bekreftet
  notert for Fase 8. Pydantic-modellene har `populate_by_name=True` på
  grade-terskel-modellene slik at round-trip YAML <-> model fungerer.
- Fase 2 rekkefølge: utvid DataStore med flere `get_*`-metoder først (COT,
  fundamentals, weather) ELLER start backfill-CLI (Fase 3 per PLAN-tabell)
  først for å få ekte data inn i sqlite-databasen tidlig? Begge er
  forsvarlige. Lateness-argument: CLI trenger uansett `append_*`-metoder å
  kalle, så schema-utvidelse kommer først uansett. Min anbefaling: session
  7 = COT-schema + `get_cot`/`append_cot`; session 8 = fundamentals +
  weather; session 9 = første backfill-CLI-command (prices fra stooq).

## Invariants (må holdes)

- **Eksisterende produksjon kjører uendret** i `~/cot-explorer/` og `~/scalp_edge/`
  inntil Fase 11 cutover. Bedrock er fullstendig parallelt.
- **Signal-schema v1** (eksisterende API-kontrakt) må bevares — gamle signal_server
  og bot fortsetter å funke med den.
- **Bot-agri-ATR-override er en kjent bug** (trading_bot.py:2665-2691) som skal
  fjernes i Fase 7. Inntil da: ikke kopier den logikken.
- **Setup-generator skal ha determinisme + hysterese + stabilitets-filtre**, ikke
  lifecycle-tracking.
- **YAML har ingen logikk.** Alltid.
- **Driver-kontrakt låst** (fra Fase 1): `(store, instrument, params) -> float`
  med `store.get_prices(instrument, tf, lookback) -> pd.Series`. Fase 2s
  `DataStore` må implementere samme signatur slik at ingen drivere behøver
  endring ved byttet fra InMemoryStore.
- **Engine API låst** (fra Fase 1): `Engine.score(instrument, store, rules, horizon=None) -> GroupResult`.
  `rules` er `FinancialRules | AgriRules`. Ingen breaking changes på
  `GroupResult` uten ADR.
- **DataStore-API låst** (fra Fase 2): metoder `get_prices`, `get_cot`,
  `get_fundamentals`, `get_weather` og tilsvarende `append_*` er
  kontrakten drivere + fetch-lag bygger på. Returner-typer låst
  (`pd.Series` for prices/fundamentals, `pd.DataFrame` for cot/weather).
  Schema-endring krever ADR + migrerings-plan.
- **SIMD-sensitive deps må pinnes** (fra ADR-002): numpy pinnet `>=2.2,<2.3`.
  Nye SIMD-tunge pakker (pyarrow, duckdb, fastparquet, scipy, numexpr) må
  avvises eller pinnes til versjon verifisert på produksjons-CPU.
- **Backfill-CLI-kontrakt låst** (fra Fase 3): alle `bedrock backfill *`-
  kommandoer har felles mønster — `--from` påkrevd, `--to` default i dag,
  `--db` default `data/bedrock.db`, `--dry-run` viser URL uten HTTP/DB.
  Nye subkommandoer må følge samme signatur.
- **Secrets kun via env/fil** (fra Fase 3): hemmeligheter leses fra
  `~/.bedrock/secrets.env` eller env-var via `bedrock.config.secrets`.
  Aldri hardkodet, aldri i YAML, aldri i UI. `--dry-run` masker secrets
  uansett om de er satt eller ikke.
- **Setup-generator API låst** (fra Fase 4):
  - `Level`, `LevelType`, `Setup`, `Direction`, `Horizon` Pydantic-
    modeller (felles med scoring-engine der relevant)
  - `detect_*`-funksjoner returnerer råliste; clustering hører i
    setup-bygger
  - `build_setup(instrument, direction, horizon, current_price, atr,
    levels, config) -> Setup | None` — deterministisk, null state
  - `stabilize_setup(new, previous, now, config) -> StableSetup` —
    hysterese + ID-persistens via slot-hash (instrument+direction+horizon)
  - `classify_horizon`, `is_score_sufficient`, `apply_horizon_hysteresis`
    — rule-based horisont-tildeling
  - Brytes kun med ADR.
- **Orchestrator API låst** (fra Fase 5 session 24):
  - `score_instrument(instrument_id, store, *, horizon, instruments_dir,
    defaults_dir, engine) -> GroupResult`
  - `generate_signals(instrument_id, store, *, horizons, directions,
    instruments_dir, defaults_dir, snapshot_path, now, price_tf,
    price_lookback, swing_window, round_number_step, setup_config,
    hysteresis_config, engine, write_snapshot) -> OrchestratorResult`
  - `OrchestratorResult`, `SignalEntry`, `OrchestratorError` Pydantic/
    Exception
  - YAML-horisonter er uppercase (SCALP/SWING/MAKRO); `Horizon`-enum
    lowercase (scalp/swing/makro). Mapping encapsulert i
    `_YAML_TO_ENUM`/`_ENUM_TO_YAML` i `signals.py`. CLI og web-UI
    bruker orchestrator-API-et direkte uten å kjenne til mappingen.
  - Brytes kun med ADR.

---

## Session log (newest first)

### 2026-04-24 — Session 28: config-drevet fetch-cadence (schema + status)

Andre Fase 6-leveranse (etter usda-kalenderen i session 27). PLAN § 7.2
skisserer `config/fetch.yaml` som erstatter shell-if/else i update.sh.
Denne sessionen bygger grunnlaget; neste session kjører faktisk fetchere.

**Opprettet:**
- `bedrock.config.fetch`:
  - `FetcherSpec` Pydantic: module, cron, stale_hours, on_failure,
    table, ts_column. `on_failure` som Literal(log_and_skip |
    retry_with_backoff | raise)
  - `FetchConfig` med `fetchers: dict[str, FetcherSpec]`
  - `load_fetch_config(path)` + `FetchConfigError`
  - `latest_observation_ts(store, table, ts_column)` — wrapper som
    parser ts-streng fra DataStore til timezone-aware datetime
    (håndterer ISO, date-only, unix-ts)
  - `check_staleness(name, spec, store, now) -> FetcherStatus`
  - `status_report(config, store, now)` — batch for alle fetchere
- `config/fetch.yaml` — cadence for de 5 eksisterende fetcherne med
  fornuftige stale_hours-terskler
- `bedrock.cli.fetch.fetch`:
  - `status`-subkommando med `--config`, `--db`, `--json`
  - Human-readable tabell: navn | fresh/STALE/NO_DATA | last_obs |
    age_h | stale_h
- `tests/unit/test_fetch_config.py` (18 tester)

**Endret:**
- `DataStore.latest_observation_ts(table, ts_column) -> str | None` —
  ny generisk accessor. Returnerer rå-streng (caller parser). Håndterer
  manglende tabell med None istedenfor SQL-error.
- `bedrock.cli.__main__`: registrerer fetch-gruppen

**Design-valg:**
- `cron`-felt lagres kun som streng i session 28 — ingen evaluering
  ennå. Croniter-integrasjon skjer i scheduler-session
- Staleness per tabell (ikke per instrument) i første runde. Per-
  instrument kan utvides ved å legge `key_columns` på FetcherSpec
  senere — ikke-breaking endring
- `--json`-modus undertrykker NO_DATA-advarselen på stderr for å
  bevare parsbar output
- `_DummyStore` i CLI for manglende DB — null-data stand-in unngår
  at DataStore oppretter fil bare for å vise status

**Commits:** `dd189c8`.

**Tester:** 479/479 grønne på 17.1 sek (fra 461 session 27, +18).

**Bevisste utsettelser:**
- Faktisk kjøring av fetchere (`bedrock fetch run`) — neste session
- Cron-evaluering + scheduler-daemon — session 30+
- Per-instrument-stale (ikke bare per tabell) — utvides ved behov
- systemd-unit-filer for deployment — Fase 11

**Neste session:** 29 — `bedrock fetch run` med dispatcher-mapping.

### 2026-04-24 — Session 27: Fase 5 lukket + USDA-kalender + usda_blackout

Session 27 startet med å lukke Fase 5 via tag `v0.5.0-fase-5` (sessions
21-26 oppsummert) og åpnet Fase 6 (fetch-laget per PLAN § 7 / § 13).

Første Fase 6-leveranse: USDA-rapport-kalender og `usda_blackout`-gate
som bruker den. Dette lukker det siste utestående elementet fra
PLAN § 4.3-eksempelet (Corn).

**Bruker-valg (AskUserQuestion ved session-start):**
- USDA-scope: kun Prospective Plantings (årlig ca 30. mars)
- Data-kilde: hardkodet YAML per år (brukeren oppdaterer manuelt)
- Vindu: ±3h (fra PLAN-eksempelet)

**Opprettet:**
- `config/calendars/usda.yaml` — 2024, 2025, 2026 Prospective Plantings
  som UTC-tidsstempler. Flere rapport-typer (grain_stocks, WASDE,
  crop_progress) kan legges til uten kode-endring
- `bedrock.fetch.usda_calendar`:
  - `load_usda_calendar(path)` — pyyaml + datetime-parsing, sortert,
    timezone-aware (naiv → UTC). Cache per absolutt sti
  - `clear_usda_calendar_cache()` for reload
  - `UsdaCalendarError` for ugyldig YAML-format
  - `@gate_register("usda_blackout")`-gate med params
    `{calendar_path, report_types, hours, hours_before, hours_after}`
  - Asymmetrisk vindu støttet (hours_before/hours_after overstyrer
    symmetrisk hours)
- `tests/unit/test_usda_calendar.py` (16 tester)

**Endret:**
- `bedrock.fetch.__init__` + `bedrock.orchestrator.__init__`: side-
  effekt-import av `bedrock.fetch.usda_calendar` slik at gate er
  registrert i alle normale entry-points

**Design-valg:**
- Gate leser kalenderen selv via loader (ikke via GateContext): holder
  GateContext smal som session 25 ADR-003 krevde. Caching gjør
  gjentatte kall billige
- Naive datetimes tolkes som UTC både i YAML og i `context.now` —
  konsistent policy, unngår silent-bug ved manglende timezone
- Side-effekt-import istedenfor eksplisitt `load_gates()`-kall:
  matcher mønsteret fra `bedrock.engine.drivers`-pakken (trend-
  modulen importeres for side-effekt)

**Commits:** `f2e4263`.
**Tag:** `v0.5.0-fase-5` (lukker sessions 21-26).

**Tester:** 461/461 grønne på 17.3 sek (fra 445 session 26, +16).

**Bevisste utsettelser:**
- Flere USDA-rapport-typer (WASDE, Crop Progress, Grain Stocks) —
  legges til når bruker trenger dem; struktur støtter det allerede
- USDA NASS API-integrasjon — bruker valgte hardkodet YAML; kan
  senere bygges som valgfri validator/auto-oppdaterer
- `usda_blackout`-gate i checked-in corn.yaml — kan legges til når
  bruker ønsker at Corn-signaler faktisk skal kappes under
  Prospective Plantings

**Neste session:** 28 — config-drevet fetch-cadence (PLAN § 7.2).

### 2026-04-24 — Session 26: bedrock signals CLI-wrapper

Sjette komponent i Fase 5 (cross-cutting). Orchestrator fra session 24
eksponeres nå via `bedrock signals <instrument_id>`.

**Opprettet:**
- `bedrock.cli.signals.signals_cmd`:
  - Argument: `INSTRUMENT_ID` (positional)
  - Flagge: `--horizon` (multiple), `--direction` (multiple),
    `--db`, `--instruments-dir`, `--defaults-dir`, `--snapshot`,
    `--price-tf`, `--price-lookback`, `--json`, `--no-snapshot-write`
  - Human-readable output: én blokk per entry med score/grade/published/
    setup-felter/gates_triggered/skip_reason
  - JSON-output via `OrchestratorResult.model_dump(mode="json")` for
    programatisk forbruk
- `tests/unit/test_cli_signals.py` (9 tester)

**Endret:**
- `SignalEntry.gates_triggered: list[str]` — ny felt; propagert fra
  `GroupResult.gates_triggered`. Gjør gates direkte synlige i
  orchestrator-resultatet uten ekstra lookup
- `bedrock.cli.__main__`: registrerer `signals`-kommandoen

**Design-valg:**
- `--json` foretrekkes for scripting/pipe-bruk; human-output er default
- Direction-casing: CLI tar uppercase (BUY/SELL); Direction-enum er
  lowercase; mapping i `signals_cmd`. JSON eksponerer enum-value
  (lowercase) for konsistens med andre Pydantic-dumps
- `--no-snapshot-write` for dry-run-lignende kjøringer uten å endre
  snapshot-fil (viktig for debug/utforsking)

**Commits:** `739a542`.

**Tester:** 445/445 grønne (fra 436 session 25, +9).

**Bevisste utsettelser:**
- `usda_blackout` (PLAN § 4.3) — krever USDA-kalender-fetcher.
  Flyttes naturlig til Fase 6 (fetch-laget) per PLAN § 13
- Explain-kommando `bedrock explain <signal_id>` (PLAN § 4.5) —
  krever signal-lagring først (Fase 6 signal-server)

**Neste session:** 27 — lukk Fase 5 med tag `v0.5.0-fase-5` og start
på Fase 6 (fetch-laget). `usda_blackout` hører naturlig i Fase 6 siden
den krever USDA-kalender-fetcher (som PLAN § 13 plasserer der).
Begrunnelse for min rekkefølge-beslutning: Fase 5 dekker nå scoring-
motor-utvidelsene (instrument-config + inherits + gates + orchestrator
+ signals CLI) og er en stabil milepæl. Å holde Fase 5 åpen for én
kalender-gate ville blandet arbeidet.

### 2026-04-24 — Session 25: gates / cap_grade (ADR-003)

Femte komponent i Fase 5. Gates er det første sub-systemet som kan
kappe grade uten å endre score — PLAN § 4.2-feature nå funksjonelt.

**Opprettet:**
- `docs/decisions/003-gates-via-named-registry-not-dsl.md` — ADR
  begrunner named-function-registry istedenfor string-DSL
- `bedrock.engine.gates`:
  - `GateSpec` Pydantic (name, params, cap_grade)
  - `GateContext` dataclass (instrument, score, max_score,
    active_families, family_scores, now)
  - Registry: `@gate_register("navn")`, `get_gate`, `all_gate_names`,
    `is_gate_registered`
  - `apply_gates(specs, context) -> (cap|None, triggered_names)` —
    flere utløste: laveste cap vinner
  - `cap_grade(grade, cap)` — aksepterer både `"A+"` (engine-form)
    og `"A_plus"` (YAML-form) via `_CAP_ALIAS`
  - Standard-bibliotek: `min_active_families`, `score_below`,
    `family_score_below` — alle data-frie, brukbare umiddelbart
- `tests/unit/test_gates.py` (18 tester)
- `tests/unit/test_engine_gates_integration.py` (10 tester)

**Endret:**
- `FinancialRules.gates: list[GateSpec]` + `AgriRules.gates` (default
  tom). Serialiseres som del av Rules, valideres strict.
- `Engine._score_financial` / `_score_agri`: bygger GateContext,
  kjører `apply_gates`, kapper grade, populerer
  `GroupResult.gates_triggered`
- `bedrock.config.instruments`: fjernet `gates` fra `_DEFERRED_KEYS`;
  lagt til i `_RULES_KEYS` + `_FINANCIAL_RULES_KEYS` +
  `_AGRI_RULES_KEYS`
- `test_gates_key_ignored_silently` → `test_gates_key_parsed_into_rules`
  (ny ekspliitt test for parsing)

**Design-valg:**
- Named-function registry (ikke DSL): samme mønster som drivers, null
  eval-risiko, typet params, testbart
- Cap_grade-alias: engine bruker `"A+"`; YAML-brukere ser
  `grade_thresholds: {A_plus: ...}` og forventer å skrive `cap_grade:
  A_plus`. Begge aksepteres i gates.py
- `gates_triggered` i rekkefølge av spec-deklarasjon, ikke trigger-tid
  (deterministisk explain-trace)
- `GateContext` er smal per prinsipp: data-frie gates kan brukes i dag;
  event-kalender/freshness krever egen ADR + utvidelse senere
- Tester er unit-nivå med null data-dependency (dummy-driver
  `always_one`). Orchestrator+ekte-data-tester kommer via signals E2E
  allerede i session 24

**Commits:** `185abe1`.

**Tester:** 436/436 grønne på 15.2 sek (fra 406 session 24, +30).

**Bevisste utsettelser:**
- `usda_blackout` som ekte gate — trenger USDA-kalender-fetcher (egen
  session)
- Gate som sjekker `now` mot event-kalender — samme
- `freshness` / `data_quality`-gate — trenger freshness-spor fra
  DataStore (egen session eller som del av Fase 6)
- Generisk DSL over registry-funksjoner (OR-kombinasjon, NOT) —
  kommer når konkret behov dukker opp, ny ADR

**Neste session:** 26 — CLI-wrapper `bedrock signals <instrument_id>`.

### 2026-04-24 — Session 24: orchestrator (score + signals) E2E

Fjerde komponent i Fase 5. Integrasjons-moment: YAML + DataStore +
Engine + setup-generator + hysterese + snapshot kobles sammen i én
topp-nivå-funksjon. Første sted hele Fase 1-4-stacken kjører i ett
kall. Utført i én session (session 24) i to del-commits:
`79a997a` score + `ce9e601` signals.

**Opprettet:**
- `bedrock.orchestrator.__init__` — public exports
- `bedrock.orchestrator.score.score_instrument`:
  - Minimum-bridge: YAML-lasting + `Engine.score` → `GroupResult`
  - Case-insensitive filnavn-match mot `<id>.yaml`
  - Horisont-validering: financial krever horisont, agri krever None
  - `OrchestratorError` på manglende YAML / ugyldig horisont
- `bedrock.orchestrator.signals.generate_signals`:
  - Full E2E: score + OHLC-fetch + ATR + level-detect + build_setup +
    stabilize (via snapshot) + SetupSnapshot-skriving
  - `SignalEntry` per (direction, horizon): score, grade, published,
    setup (eller skip_reason)
  - `OrchestratorResult`: liste av entries + run_ts + snapshot_written
  - Financial: én score per horisont. Agri: én score delt på alle 3
    horisonter (default SCALP/SWING/MAKRO × BUY/SELL = 6 entries)
  - Horisont-filter + retnings-filter via kwargs
  - Round-number-detektor inkluderes kun når caller angir step
    (asset-klasse-spesifikt)
  - `write_snapshot=False` deaktiverer persistens (for tester/dry-run)
- `tests/logical/test_orchestrator_score.py` (8 tester)
- `tests/logical/test_orchestrator_signals.py` (10 tester)

**Design-valg:**
- YAML/enum-mapping encapsulert: YAML-nøkler er `"SCALP"/"SWING"/
  "MAKRO"` (PLAN § 4.2); `Horizon`-enum-verdier er lowercase
  `"scalp"` etc. (fra session 17). `_YAML_TO_ENUM`-mapping ligger i
  `signals.py` slik at caller kan bruke begge casinger i kwarg
- Snapshot-flyt: én load (pre), én save (post). Ingen inkrementelle
  writes — save_snapshot skriver atomisk via tmp-rename (session 18)
- `SignalEntry` alltid inkluderer retry-informasjon: hvis
  build_setup returnerer None, `setup=None` + `skip_reason` satt.
  Caller filtrerer selv (UI kan vise "no setup found" status)
- Engine-instans injiserbar slik at caller kan gjenbruke samme på
  tvers av mange kall og batch-prosessere effektivt
- `_find_yaml` duplikat i score.py (private_protected): delt helper
  ville kreve eksport; for session 24 lettere å la begge moduler
  bruke samme logikk. Konsolideres hvis flere orchestrator-moduler
  kommer

**Commits:** `79a997a` (score), `ce9e601` (signals).

**Tester:** 406/406 grønne på 15.3 sek (fra 388 i session 23, +18).

**Bevisste utsettelser:**
- `gates`/`cap_grade` (PLAN § 4.2) — neste session, krever ADR for
  gate-DSL (safe predikat-evaluator, ikke eval())
- `usda_blackout` (PLAN § 4.3) — trenger USDA-kalender-fetcher
- CLI-kommando `bedrock signals <id>` som wrapper på
  `generate_signals` — klargjort for senere (API er stabil)
- Analog-matching / `find_analog_cases` — Fase 9
- Signal v1 schema for eksport til signal_server — Fase 6

**Neste session:** 25 — gates (eller CLI-wrapper avhengig av bruker).

### 2026-04-24 — Session 23: inherits-inheritance + beslutnings-retningslinje

Tredje komponent i Fase 5. `inherits: family_financial` (og transitivt
`inherits: base`) resolver nå rekursivt fra `config/defaults/` via
shallow merge på top-level keys. YAML-filene gold.yaml/corn.yaml kan nå
skrives slankere ved å arve fra family_*-defaults.

Brukeren ga også eksplisitt feedback om beslutningsautonomi: Claude
skal ikke forelegge A/B/C/D-valg for ren implementasjons-rekkefølge.
Lagret som feedback-memory + ny CLAUDE.md-seksjon "Beslutnings-
retningslinje" som skiller bestem-selv-områder (rekkefølge, mappe-
plassering, intern struktur) fra spør-bruker-områder (trading,
UX, sikkerhet, scope).

**Opprettet:**
- `bedrock.config.instruments._resolve_inherits(raw, defaults_dir,
  source, chain)` — rekursiv resolver:
  - Opprulling av parent's egen `inherits:` før merge
  - Shallow merge: `{**parent_resolved, **child}` per top-level key
  - Sletter `inherits`-nøkkelen etter opprulling
  - Circular-detect via chain-argument → tydelig cycle-melding
  - Manglende parent → tydelig "not found at <path>"-melding
- `DEFAULT_DEFAULTS_DIR = Path("config/defaults")` eksportert
- `_FINANCIAL_RULES_KEYS` / `_AGRI_RULES_KEYS`: filtrerer rules_data
  per aggregation slik at base.yaml's `horizons` (entry_tfs/hold-
  semantikk) ikke krasjer AgriRules-validering
- `tests/unit/test_config_instruments_inherits.py` (9 tester)
- CLAUDE.md § "Beslutnings-retningslinje"
- Memory-fil `feedback_decision_autonomy.md`

**Endret:**
- `load_instrument_config(path, defaults_dir=None)` +
  `load_all_instruments(directory, defaults_dir=None)`: begge tar nå
  `defaults_dir`-param
- `bedrock.cli._instrument_lookup.find_instrument`: `defaults_dir`
  propages til `load_all_instruments`
- `bedrock.cli.instruments list/show`: `--defaults-dir`-flagg
- `_DEFERRED_KEYS`: fjernet `inherits` (resolves nå), lagt til
  `data_quality` + `hysteresis` (arvet fra base.yaml, ikke enda brukt
  av engine/setups)
- `test_cli_instruments.py`: +3 tester for CLI-inherits-flow

**Design-valg:**
- Shallow merge (ikke deep): hvis gold.yaml lister `trend`/`positioning`
  og family_financial har `fundamental`, skal ikke `fundamental` sniekes
  inn via deep merge. "Child list is the full list" matcher hvordan
  brukere faktisk tenker om YAML-defaults
- Filter-per-aggregation i `_parse_instrument_dict`: cleaner enn å
  gjøre extra='ignore' på Rules-modellene — bevarer strict typo-
  fangst innenfor hver rules-modell
- `DEFAULT_DEFAULTS_DIR` kun brukt hvis YAML har `inherits:`. YAML
  uten inherits funker uavhengig av om katalogen eksisterer
- `gates` og `usda_blackout` fortsatt stille-skippet: scope-disiplin,
  egne sessions implementerer scoring-integrasjon

**Commits:** `c880ad4` (CLAUDE.md), `485b63e` (inherits).

**Tester:** 388/388 grønne på 12.5 sek (fra 376 i session 22, +12).

**Bevisste utsettelser (uendret):**
- `gates` cap_grade — trenger DSL-ADR
- `usda_blackout` — trenger USDA-kalender-fetcher

**Neste session:** 24 — orchestrator som knytter alt sammen.

### 2026-04-24 — Session 22: CLI-integrasjon av InstrumentConfig

Andre komponent i Fase 5: YAML fra session 21 brukes nå av CLI-laget.
Brukermønster: `bedrock backfill fundamentals --instrument Gold --from
2016-01-01` henter alle FRED-serier Gold trenger; én feil stopper ikke
jobben, og retry-kommandoer for failed items printes på slutten.

**Opprettet:**
- `src/bedrock/cli/_instrument_lookup.py`:
  - `DEFAULT_INSTRUMENTS_DIR = Path("config/instruments")`
  - `find_instrument(id, dir)` — case-insensitive fallback etter eksakt
    match. `click.UsageError` ved ukjent ID eller manglende katalog
- `src/bedrock/cli/_iteration.py`:
  - `ItemResult` dataclass (item_id, ok, rows_written, error)
  - `run_with_summary(items, process_fn, retry_command, label)` —
    per-item progress (`[n/N] label=id`), fanger exceptions, samler
    opp resultater, printer summary på slutten, gir exit-kode 1 ved
    minst én feil. Failed items → stderr med ferdig-formattert
    retry-kommando
- `src/bedrock/cli/instruments.py`:
  - `bedrock instruments list` — kolonne-tabell: id, asset_class,
    ticker, cot_contract, weather, fred-count. Sortert alfabetisk
  - `bedrock instruments show <id>` — metadata-dump + rules-oversikt.
    FinancialRules viser horisont-liste + familie-sett på tvers;
    AgriRules viser max_score + publish-gulv + familie-liste
- `tests/unit/test_cli_instruments.py` (10 tester)
- `tests/unit/test_cli_backfill_with_instrument.py` (15 tester)

**Endret:**
- `src/bedrock/cli/backfill.py`:
  - Alle 5 subkommandoer fikk `--instrument <id>` + `--instruments-dir`
  - `--ticker` (prices), `--contract` (cot), `--region/--lat/--lon`
    (weather), `--series-id` (fundamentals) ble alle valgfrie —
    eksplisitt arg vinner, ellers slås opp i YAML
  - Per-subkommando `_resolve_*`-helpers håndterer oppslag + tydelige
    feilmeldinger når YAML mangler nødvendige felter (f.eks. Gold
    uten weather_region → "Instrument 'Gold' har ikke komplett
    weather-metadata")
  - `fundamentals_cmd` itererer via `run_with_summary`; DataStore
    opprettes lat (ingen tom DB-fil ved 0-resultat)
- `src/bedrock/cli/__main__.py`: `cli.add_command(instruments)`
- `tests/unit/test_cli_backfill_fundamentals.py`: 2 tester oppdatert
  til nytt output-format (`OK DGS10 → 3 row(s)` i stedet for
  `Wrote 3 observation(s)`)

**Design-valg:**
- Case-insensitive instrument-lookup (f.eks. `--instrument gold` →
  `Gold.yaml`) siden brukerne ofte skriver lowercase i CLI, men YAML-
  ID-en er ofte kanonisk casing
- DB-tag kommer alltid fra `cfg.instrument.id` (kanonisk) når YAML-
  lookup brukes — gir konsistent DB-nøkkel uavhengig av hvordan
  brukeren skriver ID-en
- Resiliens-mønster generalisert via `run_with_summary`-helper slik at
  fremtidige multi-item CLI-er (f.eks. multi-region weather, multi-
  ticker prices) bare plugger inn
- 1-item success undertrykker summary-header for å unngå støy i den
  vanlige ett-ticker-for-ett-instrument-caset
- Eksplisitte args bevart: `bedrock backfill prices --instrument Silver
  --ticker xagusd` funker uten å kreve silver.yaml — lar brukere teste
  før YAML er skrevet

**Commits:** `398400b` — 8 filer, +1492/-68 linjer.

**Tester:** 376/376 grønne på 11.8 sek (fra 351 i session 21 → +25).

**Bevisste utsettelser:**
- `inherits: family_financial`-inheritance — neste session
- `gates: [...]` cap_grade-regler — trenger scoring-engine-utvidelse
- `usda_blackout` kalender-integrering — egen session
- Top-level orchestrator `generate_setups(instrument_id)` — når mer
  av Fase 5-scaffolding er på plass

**Invariant:** ingen endring i låste API-er (DataStore, Engine,
Setup-generator, Backfill-CLI felles mønster fra Fase 3). CLI-er har
additive endringer: nye flag, eksisterende signatur-usage uendret.

**Neste session:** bruker velger mellom (a-d) listet over i "Next
task".

### 2026-04-24 — Session 21: Fase 5 åpnet, instrument-config

Første komponent i Fase 5: per-instrument YAML-konfigurasjon som
binder sammen metadata (ticker/contract/region) med rules (engine-input).

**Opprettet:**
- `src/bedrock/config/instruments.py`:
  - `InstrumentMetadata` Pydantic — id, asset_class, ticker + alle
    optional fetch-pekere (`stooq_ticker`, `cot_contract`, `cot_report`,
    `weather_region/lat/lon`, `fred_series_ids`)
  - `InstrumentConfig` = metadata + rules (union `FinancialRules |
    AgriRules`)
  - `load_instrument_config(path)` — pyyaml + splitt top-level keys i
    metadata vs rules; `aggregation` diskriminerer union
  - `load_all_instruments(dir)` — `{id: config}` dict over alle
    `*.yaml`; duplikat-ID → error; ikke-yaml skippes
  - `InstrumentConfigError` for struktur-feil; Pydantic-feil propageres
  - `extra='forbid'` på begge modeller → fanger typos
  - Bevisst stille skip av `inherits`, `gates`, `usda_blackout`
    (kommer i senere sessions — YAML skrevet for fremtid bryter ikke)
- `config/instruments/gold.yaml` (PLAN § 4.2) — Gold med full
  horisont-sett, metadata inkl. cot_contract + fred_series_ids.
  Placeholder-drivere (sma200_align) hvor ekte drivere mangler
- `config/instruments/corn.yaml` (PLAN § 4.3) — Corn agri med 6
  familier + caps, weather_region=us_cornbelt med lat/lon
- `tests/unit/test_config_instruments.py` (21 tester)

**Design-valg:**
- Nested `rules:` ville vært Pydantic-native, men PLAN § 4.2/4.3 har
  top-level keys (aggregation/horizons/families). Custom parser
  honorerer PLAN-strukturen og ville uansett trenges for `inherits`-
  inheritance senere
- Placeholder-drivere i gold/corn.yaml: `sma200_align` i alle familier.
  Driver-registry har kun 2 drivere ennå; ekte drivere per familie
  kommer i senere fase. YAML-filene er strukturelt komplette men
  semantisk MVP
- Deferred-keys er stille-skippet (ikke advarsel): lar MVP-filer ha
  `inherits: family_financial`-stubs uten å lage støy

**Commits:** `5fd42a1` kode+config+tester.

**Tester:** 351/351 grønne på 11.2 sek.

**Bevisste utsettelser:**
- `inherits: family_financial` → Fase 5 senere session (defaults-
  inheritance mot `config/defaults/family_*.yaml`)
- `gates: [...]` → senere session (scoring-engine må først støtte
  cap_grade)
- `usda_blackout: ...` → senere session (kalender-integrering)
- CLI-integrasjon — session 22

**Neste session:** session 22 — CLI-integrasjon (`bedrock backfill
prices --instrument gold` etc.).

### 2026-04-24 — Session 20: Fase 4 CLOSED

Verifisert at `src/bedrock/setups/` har null placeholders. 13 public
funksjoner, 8 Pydantic-modeller, 4 enums + helpers. 330/330 grønne.

**Tag:** `v0.4.0-fase-4` opprettet og pushet.

**Fase 4 leveranse-sum:**
- **Nivå-detektor** (`setups.levels`): 3 av 7 typer — `detect_swing_levels`
  (fraktal, prominens-basert strength), `detect_prior_period_levels`
  (W/D/M resample, fast 0.8 strength), `detect_round_numbers` (trailing-
  zero-heuristikk). `rank_levels` uten dedup
- **Setup-bygger** (`setups.generator`): `Direction`/`Horizon` enums,
  `Setup`/`ClusteredLevel`/`SetupConfig` Pydantic. `compute_atr` (SMA),
  `cluster_levels` (transitiv single-link + konfluens-bonus),
  `build_setup` (deterministisk, per-horisont TP-logikk, asymmetri-gate)
- **Hysterese** (`setups.hysteresis` + `setups.snapshot`): slot-basert
  setup-ID (SHA1 av instrument+direction+horizon), `StableSetup` +
  `SetupSnapshot` modeller, `stabilize_setup` + `apply_hysteresis_batch`,
  `load_snapshot`/`save_snapshot` med atomic-write
- **Horisont-klassifisering** (`setups.horizon`): rule-based fra
  entry_tf + expected_hold_days, score-gate, ±5% symmetrisk hysterese
  rundt horisont-terskler
- **130+ nye tester** (fra 210 ved Fase 3-close → 330 nå)

**Utsatt til senere faser (bevisst):**
- Volume-profile POC/VAH/VAL — krever tick-data
- COT-pivot-detektor — design-runde mangler
- Top-level orchestrator som kombinerer alt — Fase 5 når
  instrument-config finnes
- Per-instrument YAML-overrides av `SetupConfig`/`HysteresisConfig` —
  Fase 5
- Backtest-evaluering av heuristikker (strength, clustering, hysterese-
  parametre) — Fase 10

**Neste:** Fase 5 i ny session.

### 2026-04-24 — Session 19: horisont-klassifisering

Siste komponent i Fase 4. PLAN § 5.5 + § 5.4.2 dekket.

**Opprettet:**
- `bedrock.setups.horizon`:
  - `estimate_expected_hold_days(entry, tp, atr, atr_per_day=1.0)` —
    grov hold-estimat fra TP-distanse i ATR-enheter. Defensiv mot
    `atr<=0` og returnerer `None` for MAKRO (tp=None)
  - `classify_horizon(entry_tf, expected_hold_days)` — rule-based per
    PLAN § 5.5. Håndterer intraday/mid-TF/daily-plus, hold-bånd
    <1/7-21/>21 dager, edge cases (hold=None → MAKRO)
  - `is_score_sufficient(score, horizon, min_score_publish)` — score-
    gate. Defensiv ved manglende terskel
  - `apply_horizon_hysteresis(candidate, previous, score, thresholds,
    buffer_pct=0.05)` — ±5% buffer rundt alle terskler per PLAN § 5.4.2.
    Symmetrisk hysterese (dempes både ved opp- og nedgang)
- `tests/unit/test_setups_horizon.py` (31 tester) — estimerings-edge,
  classify-rule-kombinasjoner, gate-edge, hysterese-scenarier inkl.
  multi-threshold + negative-threshold-ignorering + end-to-end 3-run

**Design-valg:**
- `_INTRADAY_TFS` inkluderer M1-M30; `_MID_TFS` H1-H4; daily+
  inkluderer D/W. 4H behandles som daily-plus (ikke intraday) per
  vår 30m-grense
- Hysterese sjekker ALLE terskler — hvis score er i buffer rundt
  f.eks. MAKRO-terskelen (3.5) og previous=SWING → keep SWING
  selv om candidate er MAKRO. Dette matcher intensjonen om å
  hindre flip-flopping uansett retning
- `_ = Direction` i slutten av modulen er en no-op for å indikere
  at Horizon/Direction hører til samme setup-domene — signaliserer
  intensjon til lesere uten å lage public-API

**Commits:** `<hash kommer>`.

**Tester:** 330/330 grønne på 11.2 sek.

**Bevisste utsettelser:**
- YAML-drevet horisont-thresholds og buffer_pct per instrument — Fase 5
- Top-level orchestrator som kombinerer detektor → bygger → hysterese →
  klassifisering → score-gate — kan lages i Fase 5 når instrument-
  config finnes

**Neste session:** Fase 4 CLOSED + tag `v0.4.0-fase-4`.

### 2026-04-24 — Session 18: hysterese + snapshot

Tredje komponent i Fase 4. PLAN § 5.4 stabilitets-filtre dekket; horisont-
hysterese (§ 5.4.2) utsatt til session 19 siden horisont-klassifisering
ikke finnes ennå.

**Opprettet:**
- `bedrock.setups.hysteresis`:
  - `HysteresisConfig` (sl_atr=0.3, tp_atr=0.5, enabled=True)
  - `compute_setup_id(instrument, direction, horizon)` — 12-char SHA1.
    Slot-basert: `Gold BUY SCALP` = samme ID uavhengig av entry/SL/TP
  - `StableSetup` Pydantic (setup_id, first_seen, last_updated, setup)
  - `SetupSnapshot` Pydantic (run_ts, setups) + `.find(...)`-metode
  - `stabilize_setup(new, previous, now, config) -> StableSetup`:
    * SL innenfor buffer → behold forrige; utenfor → ny
    * TP samme (men tp=None i MAKRO går gjennom begge veier)
    * R:R recomputed etter substitusjon
    * first_seen bevares når slot matcher; last_updated = now
    * enabled=False slår av alt
    * Mismatched slot → ValueError (bug-detection for caller)
  - `apply_hysteresis_batch` for batch-prosessering
- `bedrock.setups.snapshot`:
  - `DEFAULT_SNAPSHOT_PATH = data/setups/last_run.json` (PLAN § 5.4)
  - `load_snapshot(path)` — None ved manglende fil
  - `save_snapshot(snapshot, path)` — atomic write (tmp + rename),
    auto-opprettet parent-dir

**Design-valg:**
- Setup-ID basert på slot (instrument, direction, horizon), ikke på
  entry/SL/TP. Gir UI-kontinuitet: kortet for Gold BUY SWING beholder
  ID mens innholdet oppdateres
- Atomic write via `.tmp + rename`: POSIX-atomisk, hindrer at pipeline
  leser halvskrevet fil
- JSON-format (ikke pickle): menneskelesbar for debugging, schema-safe
  via Pydantic v2
- Slot-mismatch detekteres og rises ValueError — caller-bug er bedre
  loggeligst enn stille feil

**Commits:** `<hash kommer>`.

**Tester:** 299/299 grønne på 12.3 sek. Inkluderer en pipeline-
integrasjonstest over 3 sekvensielle kjøringer som verifiserer at
`first_seen` låses ved første kjøring og `SL=99.7` holdes stabil
gjennom tre påfølgende runs med små SL-justeringer.

**Bevisste utsettelser:**
- Horisont-hysterese (§ 5.4.2, ±5% buffer rundt horisont-terskel) —
  session 19, krever `classify_horizon` først
- Per-instrument YAML-overrides av HysteresisConfig — Fase 5

**Neste session:** horisont-klassifisering (§ 5.5) → Fase 4 closure.

### 2026-04-24 — Session 17: setup-bygger

Andre komponent i Fase 4. PLAN § 5.2 + § 5.3 dekket: clustering, ATR,
entry/SL/TP per horisont, asymmetri-gate.

**Opprettet:**
- `bedrock.setups.generator`:
  - `Direction` (BUY/SELL), `Horizon` (SCALP/SWING/MAKRO) — str-backed
    enums
  - `Setup` Pydantic (instrument, direction, horizon, entry, sl, tp, rr,
    atr + traceability: entry_cluster_price/types, tp_cluster_*).
    `tp+rr=None` for MAKRO (trailing-only)
  - `ClusteredLevel` Pydantic (price, types, strength, source_count)
  - `SetupConfig` med defaults per PLAN § 5.3 (min_rr_scalp=1.5,
    min_rr_swing=2.5, cluster_atr_multiplier=0.3, sl_atr_multiplier=0.3,
    min_entry_strength=0.6)
  - `compute_atr(ohlc, period=14)` — True Range SMA (MVP; Wilder senere)
  - `cluster_levels(levels, buffer)` — transitiv single-link. Kjede-
    effekt: 100/100.2/100.5 med buffer=0.3 blir én klynge. Strength =
    strongest + 0.1×(n-1), konfluens-bonus
  - `build_setup(...)` — deterministisk. Entry=nærmeste sterke klynge
    bak nåpris; SL=entry±buffer; TP=horisont-spesifikk (SCALP 1./2.,
    SWING 2./3., MAKRO None) med R:R-gate
- `tests/unit/test_setups_generator.py` (27 tester — ATR edge cases,
  clustering incl. transitiv, BUY+SELL per horisont, rejection-paths,
  determinisme, integrasjon med detektorer)

**Design-valg:**
- Clustering bruker transitiv single-link, ikke centroid-klustering —
  unngår iterativ konvergens, gir deterministisk resultat
- Cluster-pris = den sterkestes pris (ikke snitt) — bevarer faktisk
  støtte/motstand-nivå (snitt ville gitt en "syntetisk" pris som aldri
  eksisterer som nivå)
- MAKRO håndteres separat og returnerer Setup uten TP-klyngelookup
  (ingen grunn til å kreve TP-kandidater for trailing)
- `atr` tas som parameter (ikke beregnet inni) slik at caller kan
  gjenbruke på tvers av BUY/SELL × SCALP/SWING/MAKRO kombinasjoner

**Commits:** `<hash kommer>`.

**Tester:** 274/274 grønne på 10.8 sek.

**Bevisste utsettelser:**
- Hysterese + snapshot-komparasjon (§ 5.4) — session 18
- Horisont-klassifisering fra setup-karakteristikk (§ 5.5) — session 19
- Per-instrument YAML-overrides av `SetupConfig` — Fase 5
- Volume-profile-nivåer — senere; krever tick-data

**Neste session:** determinisme/hysterese (§ 5.4).

### 2026-04-24 — Session 16: Fase 4 åpnet, nivå-detektor

Første komponent i setup-generator. PLAN § 5.1 dekket med 3 av 7 detektor-
typer; resten (volume-profile, COT-pivot) utsatt til egne sessions når
design er mer konkret.

**Opprettet:**
- `bedrock.data.store.DataStore.get_prices_ohlc(instrument, tf, lookback)`
  — returnerer full OHLCV-DataFrame. Trengs fordi `get_prices` (close-only)
  ikke eksponerer high/low som nivå-detektoren trenger
- `src/bedrock/setups/__init__.py`
- `src/bedrock/setups/levels.py`:
  - `LevelType` enum (str-backed for JSON/YAML): `SWING_HIGH/LOW`,
    `PRIOR_HIGH/LOW`, `ROUND_NUMBER`
  - `Level` Pydantic (price, type, strength 0..1, ts optional)
  - `detect_swing_levels(ohlc, window)` — fraktal. Strength = prominens
    × 20 + 0.5 floor, cap 1.0
  - `detect_prior_period_levels(ohlc, period)` — pandas resample
    "W"/"D"/"M" (sistnevnte oversatt til "ME" internt). Strength fast 0.8
  - `detect_round_numbers(current_price, step, count_above, count_below)`
    — multipler av step rundt nåpris. Strength via trailing-zeros i
    (price/step): 0→0.5, 1→0.7, 2+→0.9. `ts=None` (ikke tidsbundet)
  - `rank_levels` — synkende strength-sortering, INGEN dedup (per
    bruker-krav: clustering hører i setup-bygger session 17)
- `tests/unit/test_store_ohlc.py` (7 tester — DatetimeIndex, kolonner,
  dtypes, lookback, NULL-håndtering)
- `tests/unit/test_setups_levels.py` (30 tester — Level-model, swings
  med prominens-variasjoner, prior-period med W/D/M, round numbers med
  step-variasjoner + edge cases, rank-levels stabilitet, integrasjons-
  test mot DataStore)

**Design-valg:**
- Hver detektor dokumenterer strength-heuristikken eksplisitt i docstring
  (per bruker-krav). Formelen skal kunne refineres uten å flytte definisjon
- Swing-strength bruker prominens (ikke test-count) i MVP. PLAN § 5.1
  nevner test-count; det krever historikk-scanning og kommer senere
- Prior-period fast 0.8 — ingen aldersdegradering MVP
- Round-number trailing-zero-heuristikk reflekterer hvordan tradere
  faktisk prisetter runde tall ($2000 > $2010)
- `rank_levels` gjør ingen dedup — per session-scope-avtale

**Bevisste utsettelser:**
- Volume-profile POC/VAH/VAL — krever tick-data/volum-distribusjon
- COT-pivot — design-runde rundt "pivot-definition" (MM-percentile
  reversering?)
- ATR-bånd — kommer med setup-bygger siden det kun er buffer
- Setup-bygger selv — session 17 (inkluderer nivå-clustering)
- Determinisme/hysterese — session 18+
- Horisont-klassifisering — senere session

**Commits:** `<hash kommer>`.

**Tester:** 247/247 grønne på 10.6 sek.

**Neste session:** setup-bygger med nivå-clustering + ATR + asymmetri-
gate.

### 2026-04-24 — Session 15: Fase 3 CLOSED

Verifisert at Fase 3 er reell implementasjon: grep mot
`src/bedrock/{fetch,cli,config}/` fant null `NotImplementedError`/`TODO`/
`FIXME`/`XXX`. 5 fetchere + 5 CLI-subkommandoer implementert. 210/210
tester grønne.

**Tag:** `v0.3.0-fase-3` opprettet og pushet.

**Fase 3 leveranse-sum:**
- **5 fetchere** (`bedrock.fetch.*`):
  - `prices.fetch_prices` (Stooq CSV, no auth)
  - `cot_cftc.fetch_cot_disaggregated` (CFTC Socrata 72hh-3qpy, 2010-)
  - `cot_cftc.fetch_cot_legacy` (CFTC Socrata 6dca-aqww, 2006-)
  - `weather.fetch_weather` (Open-Meteo Archive, no auth)
  - `fred.fetch_fred_series` (FRED, krever API-key)
- **5 CLI-subkommandoer** (`bedrock backfill *`):
  - `prices`, `cot-disaggregated`, `cot-legacy`, `weather`, `fundamentals`
  - Felles mønster: `--from` required, `--to` default i dag, `--db`
    default `data/bedrock.db`, `--dry-run` viser URL uten HTTP/DB
- **Fetch-base** (`bedrock.fetch.base`):
  - `http_get_with_retry` (tenacity, 3 forsøk, exp backoff)
  - stdlib logging (per bruker-beslutning, ikke structlog)
- **Secrets** (`bedrock.config.secrets`):
  - `load_secrets` / `get_secret` / `require_secret`
  - Prioritet env-var > fil > default
  - `~/.bedrock/secrets.env` via python-dotenv, ingen env-mutasjon
  - `--dry-run` masker alltid secrets (aldri lekk via logs)
- **Delt Socrata-helper**: `_fetch_cot_socrata` + `_normalize_cot` felles
  for disaggregated og legacy; offentlige fetchere er tynne wrappere
- **Idempotent backfill**: alle fetchere → DataStore.append_* med
  INSERT OR REPLACE på PK, trygg å re-kjøre
- **105 nye tester** (fra 107 ved Fase 2-close → 210 nå): prices (17),
  cot-disagg (18), cot-legacy (11), weather (18), fred+secrets+CLI (35),
  + 6 CLI-specific parent-help/argument-validation

**Utsatt til senere faser (bevisst):**
- Instrument→ticker/contract/lat-lon-mapping — Fase 5 (YAML)
- Config-drevet cadence (cron-scheduled backfill) — Fase 5
- ICE/Euronext COT, Conab/UNICA, USDA WASDE — Fase 5 hvis drivere trenger
- Live integrasjonstester mot eksterne API-er — flaky; manuell verifisering
  når bruker kjører CLI
- systemd-integrasjon — Fase 5/11

**Kommando-oversikt (alle har `--dry-run`):**
```
bedrock backfill prices --instrument Gold --ticker xauusd --from 2016-01-01
bedrock backfill cot-disaggregated --contract "GOLD - COMMODITY EXCHANGE INC." --from 2010-01-01
bedrock backfill cot-legacy --contract "CORN - CHICAGO BOARD OF TRADE" --from 2006
bedrock backfill weather --region us_cornbelt --lat 40.75 --lon -96.75 --from 2016-01-01
bedrock backfill fundamentals --series-id DGS10 --from 2016-01-01
```

**Neste:** Fase 4 eller Fase 5 i ny session. Bruker velger.

### 2026-04-24 — Session 14: `backfill fundamentals` (FRED) + secrets-modul

Siste backfill-subkommando i Fase 3. Første kilde som krever auth —
introduserer `bedrock.config.secrets` med prioriterte lookup-regler.

**Opprettet:**
- `src/bedrock/config/__init__.py`
- `src/bedrock/config/secrets.py`:
  - `DEFAULT_SECRETS_PATH = ~/.bedrock/secrets.env` (ekspandert)
  - `load_secrets(path)` via `python-dotenv`s `dotenv_values` — ingen
    `os.environ`-mutasjon, ingen global state
  - `get_secret(name, path, default)` — prioritet: env-var > fil > default
  - `require_secret(name, path)` kaster `SecretNotFoundError` hvis mangler
  - Ikke-eksisterende fil håndteres som tom dict
- `src/bedrock/fetch/fred.py`:
  - `FRED_OBSERVATIONS_URL` + `build_fred_params` (eksponert for masking)
  - `fetch_fred_series(series_id, api_key, from_date, to_date)` —
    returnerer DataFrame matching `DataStore.append_fundamentals`
  - FRED's `"."` for missing observations → NaN → NULL i DB
  - HTTP-feil inkluderer body-preview (FREDs error-messages nyttig ved
    debugging av auth/serie-ID-problemer)
  - `FredFetchError` for permanente feil
- `bedrock.cli.backfill.fundamentals_cmd`:
  - Obligatoriske: `--series-id`, `--from`
  - API-key resolver: `--api-key` CLI > env-var `FRED_API_KEY` >
    secrets-fil > `click.UsageError`
  - `--dry-run` MASKERER api_key som `***` i URL-output (aldri lekk
    via logs/screenshots). Rapporterer `resolved`/`MISSING`.
    Fungerer uten nøkkel
- `tests/unit/test_config_secrets.py` (15 tester — parse, kommentarer,
  blank-linjer, env-override, fil-default, tilde-ekspansjon, require-
  raises, error-message-includes-path)
- `tests/unit/test_fetch_fred.py` (10 tester — param-bygging, mocked
  HTTP success+feil, `.`-til-NaN-konvertering, empty-observations,
  malformed payload, e2e mot DataStore, correct URL)
- `tests/unit/test_cli_backfill_fundamentals.py` (10 tester — CLI-key,
  env-var, CLI-overrides-env, no-key-errors, masking i dry-run,
  dry-run-uten-key, resolved/MISSING-reporting, empty-result,
  required-args, parent-help)

**Design-valg:**
- `python-dotenv` (allerede i pyproject fra Fase 0) i stedet for custom
  parser: håndterer quoting, escaping, kommentarer riktig
- API-key-masking i dry-run ikke-valgfritt: alltid `***`. Dry-run-output
  skal kunne deles i logs eller screenshots uten å lekke
- HTTP-error body-preview: 200 tegn er nok til å se FRED's error-message
  uten å blote loggen
- Ingen separat "fundamentals" (Pydantic) validering i fetcher — stole
  på at `DataStore.append_fundamentals` valideres der

**Commits:** `<hash kommer>`.

**Tester:** 210/210 grønne på 9.5 sek.

**Bevisste utsettelser:**
- Live-test mot FRED med ekte nøkkel — manuell når bruker er klar
- Instrument→series-ID-mapping (f.eks. "us_10y_yield" → "DGS10") —
  Fase 5 instrument-config
- CLI for ICE COT / Euronext COT / Conab / UNICA / USDA WASDE —
  ikke i Fase 3-scope; kommer i Fase 5 hvis/når drivere trenger dem

**Neste session:** avslutte Fase 3, tag `v0.3.0-fase-3`.

### 2026-04-24 — Session 13: `backfill weather` (Open-Meteo, no auth)

Fjerde backfill-subkommando. Siste no-auth kilde før FRED-secrets.

**Opprettet:**
- `src/bedrock/fetch/weather.py`:
  - `OPEN_METEO_ARCHIVE_URL` + `_DAILY_VARS` konstant
  - `fetch_weather(region, lat, lon, from_date, to_date)` — returnerer
    DataFrame matching `DataStore.append_weather` (region, date, tmax,
    tmin, precip, gdd)
  - `gdd` lagres som NULL — base-temperatur er crop-spesifikk og
    beregnes i driver med context
  - `build_open_meteo_params` eksponert for `--dry-run`
  - `WeatherFetchError` for permanente feil
- `bedrock.cli.backfill.weather_cmd`:
  - Obligatoriske: `--region`, `--lat`, `--lon`, `--from`
  - Defaults: `--db data/bedrock.db`, `--to i dag`
  - `--dry-run` viser URL + alle query-params uten HTTP eller DB
- `tests/unit/test_fetch_weather.py` (11 tester — param-bygging, mocked
  HTTP success+feil, empty-time-array, missing-daily-block, missing-
  daily-field, gdd=NULL-verifikasjon, e2e mot DataStore, correct URL)
- `tests/unit/test_cli_backfill_weather.py` (7 tester — normal flow,
  --dry-run, empty-result, default-to-today, required-args,
  invalid-lat-type, parent-help)

**Design-valg:**
- region-navnet lagres som-er i DB; (lat, lon) brukes kun som query-
  param. Region→koordinat-mapping utsatt til Fase 5 instrument-config
- Ingen GDD-beregning i fetcher: base-temp er crop-spesifikk (10°C mais,
  8°C hvete, etc.). Hører i driver med crop-context
- Ingen aggregering fra GPS-punkt til region: Open-Meteo tar ett
  (lat, lon)-punkt som representativt. Ekte region-aggregering fra
  flere punkt hører til Fase 5 hvis påkrevd

**Commits:** `<hash kommer>`.

**Tester:** 175/175 grønne på 9.3 sek.

**Bevisste utsettelser:**
- `backfill fundamentals` — session 14 (FRED, secrets-håndtering)
- Region→koordinat-mapping — Fase 5
- GDD-beregning — driver i senere fase

**Neste session:** Fase 3 session 14 — FRED fundamentals, introduserer
`bedrock.config.secrets` (`~/.bedrock/secrets.env`).

### 2026-04-24 — Session 12: `backfill cot-legacy`, delt Socrata-helper

Tredje backfill-subkommando + refaktor for å unngå duplikasjon mellom
disaggregated- og legacy-fetcherne.

**Endret:**
- `src/bedrock/fetch/cot_cftc.py`:
  - Ny `CFTC_LEGACY_URL` (dataset `6dca-aqww`)
  - Ny `_LEGACY_FIELD_MAP` (Socrata → Bedrock legacy-schema)
  - Refaktor: `_fetch_cot_socrata(url, field_map, contract, ...)` +
    `_normalize_cot(rows, contract, field_map)` er de felles private
    helperne. Begge offentlige fetchere er nå tynne wrappere (~5 linjer hver)
  - Ny `fetch_cot_legacy(contract, from_date, to_date)`
- `src/bedrock/cli/backfill.py`: ny `cot_legacy_cmd` — samme mønster som
  `cot_disaggregated_cmd`, treffer legacy-URL

**Opprettet:**
- `tests/unit/test_fetch_cot_legacy.py` (6 tester — legacy-kolonneskjema,
  korrekt URL, e2e mot `DataStore.append_cot_legacy`, tabell-isolasjon
  fra disagg, empty-response, string-to-int, missing-fields med
  legacy-specific error)
- `tests/unit/test_cli_backfill_cot_legacy.py` (5 tester — normal flow
  inkl. isolasjon fra disagg-tabellen, --dry-run viser 6dca-aqww ikke
  72hh-3qpy, empty-result, argument-validering, parent-help)

**Design-valg:**
- Refaktor nå, ikke senere: 2 nesten-identiske fetchere er den kanoniske
  grensen der DRY lønner seg. 3 (hvis ICE eller Euronext COT legges til)
  ville vært umulig uten dette
- Helperne er private (`_fetch_cot_socrata`, `_normalize_cot`) — ikke
  re-eksportert for eksterne brukere

**Commits:** `<hash kommer>`.

**Tester:** 157/157 grønne på 9.3 sek.

**Bevisste utsettelser:**
- `backfill weather` — session 13 (Open-Meteo, no auth)
- `backfill fundamentals` — senere session (FRED, secrets)
- ICE/Euronext COT — hvis noensinne; ikke i PLAN-scope for Fase 3

**Neste session:** Fase 3 session 13 — weather via Open-Meteo.

### 2026-04-24 — Session 11: `backfill cot-disaggregated`

Andre backfill-subkommando + andre fetcher-modul. Følger samme mønster
som prices — eksponert `build_socrata_query` for `--dry-run`,
`CotFetchError` for permanente feil, mocked HTTP i tester.

**Opprettet:**
- `src/bedrock/fetch/cot_cftc.py`:
  - `CFTC_DISAGGREGATED_URL` = Futures Only Disaggregated (72hh-3qpy)
  - `fetch_cot_disaggregated(contract, from_date, to_date)` — henter
    SoQL-filtrert Socrata-JSON, normaliserer til Bedrock-schema
  - Socrata-til-Bedrock-feltmapping (`m_money_*` → `mm_*`, `prod_merc_*`
    → `comm_*`, etc.)
  - Socrata leverer tall som strenger → `pd.to_numeric` + `int64`-cast
  - ISO-timestamp (f.eks. `2024-01-02T00:00:00.000`) trimmes til
    `YYYY-MM-DD`
  - Tom respons returnerer tom DataFrame med riktig kolonne-sett
    (ikke exception)
- `bedrock.cli.backfill.cot_disaggregated_cmd`:
  - Obligatoriske: `--contract`, `--from`
  - Defaults: `--db data/bedrock.db`, `--to i dag`
  - `--dry-run` viser URL + `$where`/`$order`/`$limit` uten HTTP eller DB
- `tests/unit/test_fetch_cot_cftc.py` (12 tester — query-bygging, mocked
  HTTP success+feil, string-til-int-konvertering, end-to-end mot
  DataStore, timestamp-trimming, empty-response)
- `tests/unit/test_cli_backfill_cot.py` (6 tester — normal flow, empty
  result OK, --dry-run, argument-validering)

**Design-valg:**
- Kontrakt-navn er CFTCs eksakte `market_and_exchange_names`-verdi
  (f.eks. `'GOLD - COMMODITY EXCHANGE INC.'`). Instrument-til-kontrakt-
  mapping hører til Fase 5 instrument-config
- Ingen pagination implementert: 10 år × ukentlig = ~520 rader per
  kontrakt, godt under Socratas $limit=50000

**Commits:** `<hash kommer>`.

**Tester:** 146/146 grønne på 7.6 sek.

**Bevisste utsettelser:**
- `backfill cot-legacy` — session 12
- `backfill fundamentals` (FRED) — krever secrets-håndtering
- `backfill weather` (Open-Meteo) — senere session
- Live integrasjonstest mot CFTC Socrata — flaky

**Neste session:** Fase 3 session 12.

### 2026-04-24 — Session 10: Fase 3 åpnet, `backfill prices`

Første backfill-subkommando + første fetcher-modul.

**Opprettet:**
- `src/bedrock/fetch/__init__.py`
- `src/bedrock/fetch/base.py` — `http_get_with_retry` (tenacity, 3 forsøk,
  exponential backoff på `RequestException`). Generisk `retry`-dekorator
  for ikke-HTTP. Bruker **stdlib logging** (per bruker-beslutning i
  session 10, ikke structlog — drivers/trend.py beholder structlog)
- `src/bedrock/fetch/prices.py` — `fetch_prices(ticker, from_date, to_date)`
  mot Stooq CSV. `build_stooq_url_params` eksponert for `--dry-run`.
  `PriceFetchError` for permanente feil
- `src/bedrock/cli/__init__.py`
- `src/bedrock/cli/__main__.py` — click-gruppe med `-v` for DEBUG-logging
- `src/bedrock/cli/backfill.py` — `bedrock backfill prices`:
  - obligatoriske: `--instrument`, `--ticker`, `--from`
  - defaults: `--db data/bedrock.db`, `--to i dag`, `--tf D1`
  - `--dry-run` bygger URL og viser destinasjon uten HTTP eller
    DB-skriving (ingen parent-dir opprettes)
- `tests/unit/test_fetch_prices.py` (10 tester — URL-bygging, mocked
  HTTP success+feil, FX uten volume, no-data-respons)
- `tests/unit/test_cli_backfill.py` (11 tester — normal flow, --dry-run,
  tf-respekt, dir-auto-opprettelse, argument-validering)

**Design-valg:**
- Stooq over Yahoo: enklere CSV-endepunkt, ingen auth
- stdlib logging i fetch/CLI, structlog beholdes der det allerede er
- `--dry-run` viser kun URL + destinasjon, gjør ingen HTTP-kall
  (bruker-spesifikasjon: "verifisere URL uten å skrive til DB")
- CLI tar `--ticker` eksplisitt (instrument→ticker-mapping hører til
  instrument-config i Fase 5, ikke Fase 3)

**Commit:** `<hash kommer>`.

**Tester:** 128/128 grønne på 8.1 sek.

**Bevisste utsettelser:**
- Andre backfill-subkommandoer (cot, fundamentals, weather) — egne sessions
- Instrument-ticker-mapping fra YAML — Fase 5
- Live integrasjonstest mot Stooq — flaky; venter til CI er satt opp med
  retry/skipif
- `--concurrent`-flagg for parallell backfill av flere instrumenter —
  premature optimization; venter til det faktisk trengs

**Neste session:** Fase 3 session 11 — neste backfill-subkommando.

### 2026-04-24 — Session 9: Fase 2 CLOSED

Verifisert at datalaget er reell implementasjon: grep mot `src/bedrock/data/`
fant null `NotImplementedError`/`TODO`/`FIXME`/`XXX`. Alle 10 I/O-metoder
+ 4 `has_*`-hjelpere implementert mot SQLite. 107/107 tester grønne.

**Tag:** `v0.2.0-fase-2` opprettet og pushet.

**Fase 2 leveranse-sum:**
- `bedrock.data.store.DataStore` — SQLite-backet via stdlib `sqlite3`
  (null SIMD-avhengighet, kjører på produksjons-CPU-en)
- `bedrock.data.store.DataStoreProtocol` — uendret kontrakt fra Fase 1;
  `InMemoryStore` slettet
- 5 tabeller: `prices`, `cot_disaggregated`, `cot_legacy`, `fundamentals`,
  `weather`. PK-er sikrer idempotent re-run ved INSERT OR REPLACE
- Pydantic-schemas for alle rad-typer (`PriceBar`, `CotDisaggregatedRow`,
  `CotLegacyRow`, `FredSeriesRow`, `WeatherDailyRow`)
- Getter-API: `get_prices`/`get_fundamentals` returnerer `pd.Series`
  (skalar per dato), `get_cot`/`get_weather` returnerer `pd.DataFrame`
  (multi-column). `last_n` overalt; `from_` utsatt til driver trenger det
- Append-API: `append_prices`, `append_cot_disaggregated`,
  `append_cot_legacy`, `append_fundamentals`, `append_weather`
- ADR-002: SQLite-begrunnelse + SIMD-pinning-policy (tabell over
  problem-pakker + oppgraderings-regler)
- numpy pinnet `>=2.2,<2.3` i pyproject
- 107 tester: 30 store-unit (prices + cot + fund + weather) + 77 fra
  Fase 1 (engine, grade, aggregators, drivere, logisk)

**Utsatt til senere faser (bevisst):**
- `find_analog_cases` (PLAN § 6.5) — Fase 9 (analog-matching)
- `trades`-tabell — Fase 7 (bot-refaktor)
- `get_*(from_=...)`-argument — legges til når en driver trenger det
- Ekte data i databasen — Fase 3 (backfill-CLI)
- Fetch-modulene — Fase 5

**Neste:** Fase 3 i ny session. Backfill-CLI for priser først.

### 2026-04-24 — Session 8: fundamentals + weather, numpy-pin

Session 8 utvider DataStore med fundamentals (FRED) og weather.
Inkluderer tillegg fra session 6 som bruker flaget etter-post: numpy
pinnet mot SIMD-drift, ADR-002 utvidet med SIMD-policy.

**Opprettet:**
- `schemas.FredSeriesRow` + `DDL_FUNDAMENTALS` + `FUNDAMENTALS_COLS`
  (series_id, date, value — value NULL-able)
- `schemas.WeatherDailyRow` + `DDL_WEATHER` + `WEATHER_COLS`
  (region, date, tmax, tmin, precip, gdd — alle målinger valgfrie)
- `DataStore.append_fundamentals` / `get_fundamentals(series_id, last_n)`
  returnerer pd.Series (shape likt get_prices — skalar per dato)
- `DataStore.append_weather` / `get_weather(region, last_n)` returnerer
  pd.DataFrame (multi-column, shape likt get_cot)
- `has_fundamentals` / `has_weather` test-hjelpere
- `tests/unit/test_store_fundamentals.py` (9 tester)
- `tests/unit/test_store_weather.py` (9 tester)

**Etterfyll til session 6 (bruker-flagget):**
- `pyproject.toml`: numpy pinnet til `>=2.2,<2.3` med kommentar
  "SIMD-sensitive, pin upper bound (ADR-002)"
- `ADR-002`: ny seksjon "Related: SIMD-sensitive dependency pinning" med
  tabell over kjente problem-pakker og oppgraderings-policy (CI-runnere
  fanger ikke krasjen — lokal test på produksjons-CPU kreves)

**Commits:** `2ab4ef6` (numpy pin + ADR-utvidelse), `52ea518`
(fundamentals + weather + PLAN § 6.2/6.3).

**Tester:** 107/107 grønne på 6.3 sek.

**Bevisste utsettelser:**
- `find_analog_cases` (PLAN § 6.5) venter til Fase 9
- `trades`-tabell venter til Fase 7 (bot-refaktor)
- `get_*(from_=...)`-argument utsatt til en driver faktisk trenger det
  (i dag bruker alle get_* kun `last_n`)

**Neste session:** avslutte Fase 2 og starte Fase 3 (backfill-CLI).
DataStore-laget er ferdig utbygget for nåværende PLAN-scope.

### 2026-04-24 — Session 7: COT-støtte i DataStore

**Opprettet:**
- `schemas.CotDisaggregatedRow` + `CotLegacyRow` Pydantic-modeller
- `schemas.TABLE_COT_DISAGGREGATED` / `TABLE_COT_LEGACY` + DDL-konstanter
- `schemas.COT_DISAGGREGATED_COLS` / `COT_LEGACY_COLS` kolonne-rekkefølge
- `DataStore.append_cot_disaggregated(df)` / `append_cot_legacy(df)` —
  INSERT OR REPLACE paa PK (report_date, contract). Felles private
  `_append_cot()`-helper
- `DataStore.get_cot(contract, report="disaggregated"|"legacy", last_n=None)`
  — returnerer pd.DataFrame (multi-column)
- `DataStore.has_cot(contract, report)` — test-hjelper
- `tests/unit/test_store_cot.py` — 15 tester: append+get, last_n, dedupe,
  append-nye-datoer, missing-columns, ukjent-contract, ukjent-report-type,
  default-report-type, separate-contracts, has_cot, survive-reopen,
  default-er-ikke-legacy

**Design-valg:** To separate tabeller (cot_disaggregated, cot_legacy) i
stedet for én tabell med `report_type`-kolonne. Grunn: ulike kolonne-
strukturer fra CFTC gir NULL-sprawl ved felles tabell. PLAN § 6.2/6.3
oppdatert tilsvarende.

**Bevisste utsettelser:**
- ICE og Euronext COT-tabeller (PLAN § 6.2 originalt) — utsettes til behov
  oppstår i senere faser. CFTC dekker alle financial + agri-instrumenter
  vi trenger nå
- DataStoreProtocol uendret — drivere rører ikke COT ennå
- Ingen positioning-drivere ennå (cot_mm_percentile etc.) — kommer når
  flere drivere skrives, sannsynligvis etter Fase 2 avsluttes

**Commits:** `6469d8c` (feat/data COT), `5843a11` (docs/plan § 6.2+6.3).
Auto-push aktiv.

**Tester:** 89/89 grønne på 4.6 sek.

**Neste session:** Fase 2 session 8 — fundamentals (FRED-serier) og/eller
weather. Alternativ: backfill-CLI (Fase 3) hvis bruker vil teste mot
ekte data før flere schemas legges til.

### 2026-04-24 — Session 6: Fase 2 åpnet, SQLite-DataStore

Fase 2-oppstart traff uforventet hardware-blokker: CPU (Pentium T4200,
2008) mangler SSE4.2/AVX/AVX2. Moderne `duckdb`, `pyarrow`, `fastparquet`-
wheels krasjer med Illegal instruction ved import (bekreftet på T4200).
Brukerbeslutning: SQLite + pandas i stedet for PLAN §6.1-valget.

**Opprettet:**
- `src/bedrock/data/schemas.py` — `PriceBar` Pydantic + `TABLE_PRICES` +
  `DDL_PRICES` (SQLite DDL med PK instrument+tf+ts for INSERT OR REPLACE
  dedupe)
- `src/bedrock/data/store.py` — komplett rewrite:
  - `DataStoreProtocol` **uendret** (driver-kontrakt låst fra Fase 1)
  - `InMemoryStore` **slettet**
  - `DataStore(db_path)` med `get_prices`, `append_prices`, `has_prices`.
    Bruker stdlib `sqlite3` + `pd.read_sql` — ingen SIMD-avhengighet.
- `docs/decisions/002-sqlite-instead-of-duckdb.md` — dokumenterer
  hardware-begrunnelse + migreringsvei tilbake til DuckDB om hardware
  oppgraderes

**Endret:**
- `tests/unit/test_store.py` — komplett omskrevet (15 tester, opp fra 7)
- `tests/logical/test_trend_drivers.py` — fixture-basert med `tmp_path`,
  ny `_add_closes`-helper. Driver-logikk uendret.
- `PLAN.md` §6.1/6.2/6.3 — oppdatert for SQLite
- `pyproject.toml` — duckdb + pyarrow fjernet fra deps

**Commits:** `0f4e9cb` (feat/data), `56dc5b4` (ADR-002), `e15bafa`
(plan+pyproject). Auto-push aktiv — alle på GitHub.

**Tester:** 74/74 grønne på 3.4 sek. Ingen driver-kode endret.

**Neste session:** Fase 2 session 7 — utvid DataStore med COT-støtte
(`get_cot`, `append_cot`, schemas for CFTC disaggregated + legacy),
eller hopp til backfill-CLI (Fase 3) avhengig av brukers valg.

### 2026-04-24 — Session 5: Fase 1 CLOSED

Verifisert at additive_sum + agri-grade er reell implementasjon (ikke
placeholder): grep mot src/ fant null `NotImplementedError`/`TODO`/`FIXME`/
`XXX`. Alle agri-symboler på plass (`additive_sum`, `AgriRules`,
`AgriFamilySpec`, `AgriGradeThreshold(s)`, `grade_agri`, `_score_agri`).
66/66 tester grønne.

**Tag:** `v0.1.0-fase-1` opprettet og pushet.

**Fase 1 leveranse-sum:**
- `Engine.score()` for begge asset-klasser (financial weighted_horizon,
  agri additive_sum)
- Pydantic-modeller for YAML round-trip (Rules, FamilySpec, GroupResult +
  alias-støtte for A_plus/A/B)
- Driver-registry med `@register`-dekorator og duplicate-guard
- `grade_financial` (pct-av-max) + `grade_agri` (absolutte terskler)
- `bedrock.data.store.InMemoryStore` med stabil `get_prices`-kontrakt som
  Fase 2s ekte DataStore må implementere
- 2 ekte drivere: `sma200_align`, `momentum_z` (trend-familien)
- ADR-001: én Engine + aggregator-plugin
- 66 tester: 27 unit (registry + aggregators + grade + engine smoke) +
  12 agri + 7 store + 14 logiske driver-tester + 1 engine-integrerings-
  sanity + 3 pre-eksisterende smoke

**Utsatt til senere faser (bevisst):**
- 3-8 resterende drivere (positioning, macro, fundamental, structure, risk,
  analog) — skrives i Fase 2 mot ekte data
- `gates`-felt på Rules (PLAN § 4.2 `cap_grade`) — Fase 2/3 når faktiske
  scenarier trenger det
- `StoreProtocol`-duplikat mellom `bedrock.engine.drivers` og
  `bedrock.data.store` — konsolideres i Fase 2

**Neste:** Fase 2 i ny session. Erstatt InMemoryStore med DuckDB+parquet.

### 2026-04-24 — Session 4 (Claude Code + bruker)

Fase 1 session 4: Engine-kjøring end-to-end med ekte drivere og datalag-stub.

**Opprettet:**
- `src/bedrock/data/__init__.py`
- `src/bedrock/data/store.py` — `InMemoryStore` + `DataStoreProtocol`.
  Implementerer `get_prices(instrument, tf, lookback)` som matches av den
  ekte `DataStore` i Fase 2. API-kontrakten er stabil; drivere trenger
  ingen endring ved senere bytte.
- `src/bedrock/engine/drivers/trend.py` — `sma200_align`, `momentum_z`
- Auto-registrering: `drivers/__init__.py` importerer `trend` slik at
  `@register`-kall kjører ved import av drivers-pakken
- `tests/unit/test_store.py` (7 tester)
- `tests/logical/test_trend_drivers.py` (14 driver-tester + 1 Engine-integrerings-sanity)

**Bevisste utsettelser:**
- `DataStoreProtocol` i `bedrock.data.store` er minimal. Duplikat-Protocol
  i `bedrock.engine.drivers.StoreProtocol` beholdes inntil Fase 2 konsoliderer
- Ingen positioning/macro/structure-drivere ennå
- `get_cot()`, `get_weather()` osv. er ikke på InMemoryStore ennå — legges
  til når første driver som trenger dem skrives

**Commit:** `819e14c` (store + trend-drivere). Auto-push aktiv.

**Tester:** 66/66 grønne lokalt i `.venv` (sec 2.02). Ekte Gold-SWING-scenario
med bare trend-familien gir score=1.0 og grade=B (riktig gitt enkelt regelsett).

**Neste session:** valg mellom (a) flere drivere innenfor Fase 1 (foreslår
positioning-familien: `cot_mm_percentile` + `cot_commercial_z` — krever
`get_cot()` på store) eller (b) avslutt Fase 1 og start Fase 2 (DuckDB-store).
Fase 1 estimert som "1 uke, 5-10 drivere" — vi har pt 2. Resterende 3-8
drivere kan komme i Fase 2 hvor de har ekte data å kjøre mot.

### 2026-04-24 — Session 3 (Claude Code + bruker)

Fase 1 session 3: `additive_sum` + agri-grade. Engine komplett for begge
asset-klasser; ingen drivere ennå.

**Opprettet / endret:**
- `aggregators.additive_sum(family_scores, family_caps)` — agri-variant
- `grade.AgriGradeThreshold` + `AgriGradeThresholds` + `grade_agri()`
  (absolutte terskler, ikke pct-av-max)
- `engine` refaktorert: `FinancialRules` + `FinancialFamilySpec` (renamed
  fra `Rules`/`FamilySpec`), `AgriRules` + `AgriFamilySpec`,
  `Rules = FinancialRules | AgriRules` TypeAlias. `Engine.score()`
  dispatcher via `isinstance`. `horizon` er nå Optional på både metode-sign
  og `GroupResult`
- `tests/unit/test_engine_agri_smoke.py` (5 tester), utvidet
  `test_aggregators.py` (+5) og `test_grade.py` (+7)

**Bevisste utsettelser:**
- Ingen ekte drivere ennå (kommer session 4)
- `gates`-felt på Rules (PLAN § 4.2 `cap_grade`-regler) utsatt

**Commit:** `c57fe82` (additive_sum + agri-rules/grade). Auto-push aktiv.

**Tester:** 44/44 grønne lokalt i `.venv`. ADR-001 dekker valget av
aggregator-plugin-arkitektur — ingen ny ADR nødvendig (implementasjonen er
execution av den beslutningen).

**Neste session:** session 4 — første ekte drivere (`sma200_align`,
`momentum_z`) mot minimal in-memory `DataStore`-stub, med logiske tester
på kurerte pris-serier.

### 2026-04-24 — Session 2 (Claude Code + bruker)

Fase 1 session 2: Engine-skjelett + `weighted_horizon` + grade + driver-registry.

**Opprettet:**
- `src/bedrock/engine/__init__.py`
- `src/bedrock/engine/drivers/__init__.py` — `@register`-dekorator, registry-lookup,
  duplicate-guard, `StoreProtocol`-stub (formaliseres i Fase 2)
- `src/bedrock/engine/aggregators.py` — `weighted_horizon(family_scores, family_weights)`
- `src/bedrock/engine/grade.py` — `GradeThreshold` + `GradeThresholds` (Pydantic, YAML-alias
  for `A_plus`/`A`/`B`) + `grade_financial()`
- `src/bedrock/engine/engine.py` — `Engine.score()` + Pydantic-modeller: `Rules`,
  `FamilySpec`, `DriverSpec`, `HorizonSpec`, `DriverResult`, `FamilyResult`, `GroupResult`
- `tests/unit/test_driver_registry.py` (5 tester)
- `tests/unit/test_aggregators.py` (6 tester, inkl. edge cases)
- `tests/unit/test_grade.py` (8 tester, inkl. YAML-alias-parse)
- `tests/unit/test_engine_smoke.py` (8 tester med mock-drivere)
- `docs/decisions/001-one-engine-two-aggregators.md` + oppdatert ADR-indeks

**Bevisste utsettelser:**
- `additive_sum` kaster `NotImplementedError` — kommer neste session
- Ekte drivere (`sma200_align` etc.) skrevet når `DataStore` finnes (Fase 2)
- `gates`-støtte (PLAN § 4.2) ikke ennå — kommer med grade-utvidelser

**Commits:** `e6829d0` (engine scaffolding), `541ccbc` (ADR-001). Auto-push aktiv — begge på GitHub.

**Tester:** 27/27 grønne lokalt i `.venv` (pytest 9.0.3, pydantic 2.12). CI ikke bekreftet
kjørende siden bruker ikke har satt opp `uv sync` enda.

**Neste session:** enten (a) in-memory `DataStore`-stub + `sma200_align`+`momentum_z`,
eller (b) `additive_sum`-aggregator + agri-grade. Bruker velger.

### 2026-04-23 — Session 1 (Claude Code + bruker)

Fase 0 infrastruktur opprettet.

**Opprettet:**
- Katalog-struktur (src/, tests/, config/, data/, web/, docs/, systemd/, .github/)
- `.gitignore`, `.pre-commit-config.yaml`, `.yamllint.yaml`
- `.github/pull_request_template.md`, `.github/workflows/ci.yml`
- `CLAUDE.md` (session-disciplin + git-regler + konvensjoner)
- `STATE.md` (denne)
- `PLAN.md` (kopiert og oppdatert fra `BEDROCK_PLAN.md` med siste beslutninger)
- `README.md` (prosjekt-overview)
- `pyproject.toml` (uv + Python 3.12 + ruff + pyright + pytest + pydantic v2)
- `.env.example` (env-var-dokumentasjon)
- `docs/commit_convention.md` (full commit-mal)
- `docs/branch_strategy.md` (branch-navn + flyt)
- `docs/architecture.md` (skeleton)
- `docs/rule_authoring.md` (stub)
- `docs/driver_authoring.md` (stub)
- `docs/decisions/README.md` (ADR-format)
- Minimal `src/bedrock/__init__.py` + skall for `engine/`, `setups/`, `data/`, `fetch/`
- Config-stubs: `config/defaults/base.yaml`, `config/defaults/family_financial.yaml`, `config/defaults/family_agri.yaml`
- `tests/conftest.py` + trivial smoke-test for å verifisere CI

**Commits:** `07c2b95` (initial repo setup, Fase 0 — 45 filer, 2804 insertions).

**Neste session:** opprett `feat/engine-core` branch, skriv `Engine`-klasse + drivers-registry
+ første to drivere (`sma200_align`, `momentum_z`) + logiske tester for dem.

**Open (bruker må gjøre):**
1. Sett opp branch-beskyttelse på main i GitHub-settings (se `docs/branch_strategy.md`)
2. Installer uv + kjør `uv sync --all-extras` + `uv run pre-commit install`

**Oppnådd 2026-04-24:**
- SSH-nøkkel generert og lagt inn på GitHub
- Remote byttet fra HTTPS til SSH (git@github.com:Snkpipefish/Bedrock.git)
- Main pushet — 3 commits på GitHub
- Auto-push-hook verifisert fungerende
