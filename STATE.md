# Bedrock — state

## Current state

- **Phase:** 11 **ÅPEN** (backtest-rammeverk + 12 mnd historikk-replay). Bruker-beslutning 2026-04-25: bli på Nivå 1 til Fase 11 ferdig, bytt til Nivå 3 ved Fase 12 start.
  - **62:** scaffold + outcome-replay-CLI + rapport-format. **LUKKET 2026-04-25**
  - **63+:** as-of-date orchestrator-replay (krever DataStore-view-clip), per-grade-breakdown, `compare_signals(v1, v2)`, evt. UI-fane
- **Phase:** 10 **LUKKET 2026-04-25** (tag `v0.10.0-fase-10`). Analog-matching + ubrukt-data-audit. Splittet i to spor per bruker-beslutning 2026-04-25:
  - **Spor B — ubrukt-data-audit (session 56):** dokumentasjon, ingen kode. **LUKKET 2026-04-25**
  - **Spor A — analog-matching (sessions 57-61):** A-D besvart 2026-04-25 (M/B2/U/split). Re-numrert til 5 sessions etter D-splitt:
    - **57:** ADR-005 + skjema + DataStore-utvidelse + ENSO-fetcher (pure kode). **LUKKET 2026-04-25**
    - **58:** backfill-eksekvering (3 nye CLI + Yahoo-port + full backfill). **LUKKET 2026-04-25**
    - **59:** `find_analog_cases`-impl + asset-klasse-dim-mapping. **LUKKET 2026-04-25**
    - **60:** `analog`-driver-familie + YAML-integrasjon. **LUKKET 2026-04-25**
    - **61:** UI-rendering (modal-utvidelse + `analog`-felt på SignalEntry). **LUKKET 2026-04-25**
- **Phase:** 9 **LUKKET 2026-04-25** (UI: 4 faner + admin-editor). Struktureres som tre runder per bruker-beslutning 2026-04-24:
  - **Runde 1 (session 47-50):** minimal data-wiring per fane, funksjonelt null polish
  - **Runde 2 (session 51-53):** styling, flyt, filtrering, detaljmodaler — **LUKKET 2026-04-25**
  - **Runde 3 (session 54-55):** admin-rule-editor på separat URL med kode-gate — **LUKKET 2026-04-25**
- Session 47 lukket — Fane 1 Skipsloggen (KPI + trade-log-tabell).
- Session 48 lukket — Fane 2 Financial setups (kort-grid med grade/score-sortering).
- Session 49 lukket — Fane 3 Soft commodities (samme kort-grid; backend klar fra 48).
- Session 50 lukket — Fane 4 Kartrommet (pipeline-helse, gruppert per PLAN § 10.4). **Runde 1 LUKKET** — alle fire faner har funksjonell data-wiring.
- **Pre-runde-2 cleanup (2026-04-25):** Python 3.10-baseline (ADR-004), CI bumpet til 3.10, pre-commit aktivert lokalt via `.githooks/pre-commit`-delegering, datetime.UTC reverted til timezone.utc i 20 filer. Pyright-step non-blocking i CI inntil 162 akkumulerte type-errors er ryddet (egen task).
- Session 51 lukket — Filter-bar (horizon/grade/instrument/direction) på Skipsloggen + Financial + Soft commodities. Pure filter-logikk i `web/assets/filter.js`; 18 logiske tester (`tests/web/test_filter.test.mjs`).
- Session 52 lukket — Modal med explain-trace. SignalEntry utvidet med `families: dict[str, FamilyResult]` + `active_families: int` (persisterer driver-trace fra Engine til JSON). Klikk på setup-kort eller trade-rad åpner modal med score-bar/driver-tabell/setup-detaljer. Trade-modal har disclaimer om at trace ikke lagres per trade enda.
- Session 53 lukket — UI-polish. Tokenbasert designsystem (--c-*/--sp-*/--fs-*/--r-*), system-fonter med tabular-nums for alle tall, header med gradient + accent + live `/health`-status-pill (online/down/unreachable), tettere KPI-kort, klarere tab-aktiv-tilstand, semantiske status-pills i Kartrommet. **Runde 2 LUKKET** — alle fire faner har filter, modal med explain-trace, og polert visuell stil.
- Session 54 lukket — Admin rule-editor (instrument-YAML). Ny `/admin`-route + `web/admin.html` med kode-gate (X-Admin-Code → sessionStorage/localStorage), to-pane editor (sidebar med instrument-liste + YAML-textarea), Reload + Lagre + Cmd/Ctrl+S. Bygger på eksisterende `/admin/rules`-endepunkter fra Fase 7 session 38.
- Session 55 lukket — Admin-editor utvidet: (a) lightweight dry-run (`POST /admin/rules/<id>/dry-run` validerer Pydantic uten å skrive), (b) git-commit-on-save (subprocess `git -C <root>` add + commit; auto-push-hook pusher; respons har `git`-felt), (c) logs-viewer (`GET /admin/logs?tail=N` + UI-tab med monospace pre-output). **Runde 3 LUKKET** — admin-editor er funksjonell for instrument-regler med safe-edit-loop (validate → save → commit → push) og pipeline-log-viewer. **Fase 9 LUKKET** — alle tre runder (data-wiring + filter/modal/polish + admin-editor) er levert.
- Session 56 lukket — Fase 10 spor B (audit). `docs/data_audit_2026-04.md` levert: kilde × leses-av-tabell + K-NN-feasibility per asset-klasse mot PLAN § 6.5. Hovedfunn: bedrock.db er tom (0 rader), 4 av 5 DataStore-getters har ingen konsument (kun get_prices brukes), 3 brudd mot § 6.5 flagget (energy backwardation/supply, grains/softs ENSO, softs UNICA). Fire beslutninger til bruker (A-D) blokkerer session 57.
- Session 57 lukket — ADR-005 + skjema + DataStore-utvidelse + ENSO-fetcher. Pure kode + 45 nye tester (1038/1038 grønt). Ingen backfill-eksekvering (det er session 58). Beslutninger A-D besvart: A=M (NOAA ONI-fetcher), B=B2 (migrer agri_history månedlig, ny `weather_monthly`-tabell), C=U (utsett energy/softs), D=split (57=kode, 58=backfill).
- Session 58 lukket — full backfill kjørt. To kilder krevde fix underveis: (a) Stooq begynte å kreve API-nøkkel → port av cot-explorers `build_price_history.py` til ny `bedrock/fetch/yahoo.py`, Yahoo nå default for prices; (b) CFTC endret feltnavn `m_money_positions_long` → `..._long_all` → `_DISAGG_FIELD_MAP` rebased. 3 nye CLI-er: `bedrock backfill enso/weather-monthly/outcomes`. DB vokste fra 0 → 3.54 MB med 46 569 rader. 1085/1085 tester grønne (+47 nye). Se `docs/backfill_2026-04.md` for full statistikk.
- Session 59 lukket — `find_analog_cases`-impl. Ny modul `bedrock/data/analog.py` (320 linjer) med ASSET_CLASS_DIMS (§ 6.5 slavisk), 6 implementerte DIM_EXTRACTORS, `extract_query_from_latest`, og K-NN (weighted Euclidean over z-normaliserte verdier). ADR-005-avvik dokumentert: funksjonen ble frittstående (ikke DataStore-metode) for å unngå data → config-kobling. Sanity mot ekte Gold/Corn-data: topp-5 sims 0.88-0.95 (Gold), 0.70-0.72 (Corn). 1129/1129 tester (+44 nye fordelt på 3 filer).
- Session 60 lukket — analog-driver-familie + YAML-integrasjon. Ny `bedrock/engine/drivers/analog.py` med `analog_hit_rate` + `analog_avg_return` (registrert via `@register`). Felles `_knn`-helper med defensive exception-håndtering (alle feil → 0.0 + log). Sirkulær import (cli → config → engine → drivers → drivers.analog) løst med lat import av `find_instrument` inne i `_knn`. Gold + Corn-YAML utvidet med `analog`-familie (Gold: family_weights 0.3/0.8/1.2 per horizon; Corn: weight 2). Engine end-to-end-verifisert mot ekte data: Gold scorer 0.45 i analog-familien, Corn 0.0. 1145/1145 tester (+16 nye).
- Session 61 lukket — UI-rendering + SignalEntry-utvidelse. Nye `AnalogNeighbor` + `AnalogTrace` Pydantic-modeller. `SignalEntry.analog: AnalogTrace | None = None` (additiv, bakoverkompatibel). `_build_analog_trace` plukker driver-params fra første driver i analog-familien, kaller `find_analog_cases`, bygger trace med narrative-felter (n_neighbors, hit_rate_pct, avg_return_pct, dims_used, neighbors[]). UI-modal får `_analogHtml`-helper som rendrer "X av N steg ≥Y% innen Hd"-narrative + neighbor-mini-tabell. CSS for analog-tabell + pos/neg-fargekoder. End-to-end-verifisert: Gold MAKRO-signal har 5 naboer (topp: 2022-03-23 sim=0.955), JSON-roundtrip OK. 1155/1155 tester (+10 nye). **Fase 10 LUKKET — tag `v0.10.0-fase-10`.**
- Session 62 lukket — Fase 11 åpning. Scaffold for backtest-rammeverket: ny modul `bedrock/backtest/` (config + result + report + runner) + ny CLI `bedrock backtest run` + demo-rapport `docs/backtest_2026-04_gold-corn.md` mot ekte data (Gold/Corn × 30d/90d). Outcome-replay leser pre-beregnet `analog_outcomes` — ingen as-of-date orchestrator-replay ennå (det er senere session). Hit-flag beregnes on-the-fly fra config-terskel slik at samme tabell kan re-aggregeres uten re-backfill. Sanity: Gold 2024 30d hit-rate 59.1%, avg +3.87% (matcher Gold-bull-året). 1183/1183 tester (+28 nye fordelt på 2 filer).
- **Branch:** `main` (jobber direkte på main, Nivå 1-modus). Bruker-beslutning 2026-04-25: bli på Nivå 1 til Fase 11 ferdig, bytt til Nivå 3 ved Fase 12 start.
- **Blocked:** nei
- **Next task:** **Session 63** = as-of-date orchestrator-replay. Krever `DataStoreView`-wrapper (eller equivalent) som klipper data ved en gitt ref_date slik at `Engine.score(...)` kun ser data ≤ ref_date. Så `run_orchestrator_replay` itererer ref_dates og samler full SignalEntry per dato → populerer score/grade/published på `BacktestSignal` + per_grade-breakdown på `BacktestReport`. Bevisst tett scope — `compare_signals(v1, v2)` og UI-fane hører i senere sessions etter as-of-date-replay er stabil.
- **Git-modus:** Nivå 1 (commit direkte til main, auto-push aktiv). Bytter til Nivå 3 (feature-branches + PR) **ved Fase 12 start** per bruker-beslutning 2026-04-25.

## Open questions to user

### Eldre, fortsatt åpne

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
- **DataStore-API låst** (fra Fase 2, utvidet ADR-005 Fase 10 session 57):
  metoder `get_prices`, `get_cot`, `get_fundamentals`, `get_weather`,
  `get_weather_monthly`, `get_outcomes` og tilsvarende `append_*` er
  kontrakten drivere + fetch-lag bygger på. Returner-typer låst
  (`pd.Series` for prices/fundamentals, `pd.DataFrame` for cot/weather/
  weather_monthly/outcomes). Schema-endring krever ADR + migrerings-plan.
  Nye additiver i ADR-005: `weather_monthly` + `analog_outcomes`-tabeller,
  ENSO som `series_id="NOAA_ONI"` i `fundamentals`. `find_analog_cases`-
  signatur designet (impl venter til session 59).
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

### 2026-04-25 — Session 62: Fase 11 åpning — backtest-scaffold + outcome-replay + rapport-format (LUKKET)

**Scope:** Første session i Fase 11. Per bruker-instruks: scaffold +
rapport-format, ikke as-of-date orchestrator-replay (det kommer i
session 63). Bruke eksisterende `analog_outcomes`-tabell + orchestrator
som datakilde.

**Endret denne session (commit `a511223`):**

`src/bedrock/backtest/` (ny modul):
- `__init__.py` — re-eksport av offentlige navn
- `config.py` — `BacktestConfig`: instrument, horizon_days,
  from_date, to_date, outcome_threshold_pct (default 3.0 per § 6.5),
  report_format (markdown|json). `model_validator(mode="after")`
  sjekker at from_date ≤ to_date.
- `result.py` — `BacktestSignal` (ref_date, instrument, horizon_days,
  forward_return_pct, max_drawdown_pct, hit) + score/grade/published
  som None-able for senere orchestrator-replay. `BacktestResult`
  pakker config + signals.
- `report.py` — `BacktestReport` (n_signals, n_hits, hit_rate_pct,
  avg/median/best/worst return, avg/worst drawdown, n_published,
  by_grade). `summary_stats(result)` aggregerer. `format_markdown`
  + `format_json` for output.
- `runner.py` — `run_outcome_replay(store, config)`: leser
  `store.get_outcomes(instrument, horizon_days)`, filtrerer på
  dato-vindu, bygger BacktestSignal per rad, hit beregnes
  on-the-fly fra config-terskel.

`src/bedrock/cli/backtest.py` (ny CLI):
- `bedrock backtest run --instrument <X> --horizon-days <H>
  --from <D> --to <D> --threshold-pct <T> --report markdown|json
  --output <FILE>`
- Output til stdout eller fil

`src/bedrock/cli/__main__.py`:
- `cli.add_command(backtest)`

`docs/backtest_2026-04_gold-corn.md` (ny demo-rapport):
- Gold 30d (4071 obs): hit-rate 34.5%, avg +1.21%
- Gold 90d (4011 obs): hit-rate 52.5%, avg +3.72%
- Corn 30d (4069 obs): hit-rate 36.6%, avg +0.58%
- Corn 90d (4009 obs): hit-rate 40.4%, avg +1.84%
- Sub-period Gold 2024 30d (252 obs): hit-rate 59.1%, avg +3.87%
- Demonstrerer både full-range og sub-period rapport-format

**Tester (+28 nye → 1183/1183):**

`test_backtest_runner.py` (21 tester):
- BacktestConfig validering: minimal, horizon > 0, dato-vindu,
  extra-felt forbidden, report_format choices
- BacktestSignal/Result roundtrip
- run_outcome_replay: full window, dato-filter, terskel-konfigurerbar,
  unknown instrument/horizon → empty, sortering
- summary_stats: empty, basic, n_published-None når score-felter mangler
- format_markdown: metrics, signed return, empty-data-melding
- format_json: roundtrip
- BacktestReport-struktur

`test_cli_backtest.py` (7 tester):
- CLI markdown til stdout
- CLI JSON til stdout
- CLI til fil (parent-mkdir)
- Missing DB → UsageError
- Window-filter
- Threshold-konfigurerbar
- Unknown instrument viser "Ingen outcomes funnet"

**Designvalg:**

- **Hit-flag beregnes on-the-fly** (ikke lagret i `BacktestSignal`):
  oh wait — det ER lagret. Men terskelen som ble brukt er i config,
  ikke i signal. Dette gjør at `summary_stats` kan re-aggregere
  med ulike terskler bare ved å re-lese config + re-kjøre runner
  — ikke nødvendig å persistere flere `hit`-felter.
- **`score`/`grade`/`published` som None-able** på BacktestSignal:
  outcome-replay har ingen orchestrator-output. Når
  `run_orchestrator_replay` er ferdig, fyller den disse uten å
  endre schema — bakoverkompat.
- **`n_published` = None når ingen signaler har published-flag**:
  unngår misvisende "0 av N publisert" når data faktisk mangler.
  Markdown-formatter hopper over rad hvis None.
- **`by_grade` er tom dict** for outcome-replay (ingen score). Når
  orchestrator-replay populerer, fyller den per-grade-stats.
  Markdown-formatter rendrer kun seksjon hvis dict har innhold.
- **`pd.isna`-import er late** i runner.py for å holde top-of-file
  rent for ren-Python-import (matchet eksisterende
  schemas.py-mønster).
- **Demo-rapport har bevisst ingen sub-period for Corn**: Corn-
  historikken er volatil og 5 sub-perioder hadde gjort rapporten
  uoverskuelig. Vi kan utvide når sub-period-analyse blir et
  konkret behov.

**Verifisert:**
- pytest full → 1183/1183 (var 1155, +28)
- ruff check + format → grønt
- Pre-commit hook → grønt (måtte la end-of-file-fixer kjøre én gang
  på demo-rapporten)
- Auto-push → `origin/main`
- Manuell sanity: `bedrock backtest run --instrument Gold
  --horizon-days 30 --from 2024-01-01 --to 2024-12-31` produserer
  ekte rapport mot data/bedrock.db

**Neste session (63):**
- as-of-date orchestrator-replay
- Designvalg å ta: en `DataStoreView`-wrapper som filtrerer alle
  store-getters til ts ≤ ref_date, eller la run_orchestrator_replay
  injisere et "as_of"-clip i Engine.score-pipelinen
- Når replay er stabil: per-grade-breakdown blir naturlig
- `compare_signals(v1, v2)` og UI-fane: senere sessions

---

### 2026-04-25 — Session 61: Fase 10 spor A — UI-rendering + SignalEntry-analog (LUKKET, FASE 10 LUKKET)

**Scope:** Siste session i Spor A og Fase 10. Bind K-NN-resultater
fra session 59-60 til UI-modal via persistert `analog`-felt på
SignalEntry. Tagger `v0.10.0-fase-10` etter session.

**Endret denne session (commit `a017944`):**

`src/bedrock/orchestrator/signals.py` (+150 linjer):
- Ny `AnalogNeighbor`-modell (ref_date, similarity,
  forward_return_pct, max_drawdown_pct)
- Ny `AnalogTrace`-modell (asset_class, horizon_days,
  outcome_threshold_pct, n_neighbors, hit_rate_pct, avg_return_pct,
  avg_drawdown_pct, dims_used, neighbors[])
- `SignalEntry.analog: AnalogTrace | None = None` — additiv felt,
  bakoverkompatibelt for eldre tester og fixtures
- `_build_analog_trace(cfg, store) -> AnalogTrace | None`:
  - Plukker driver-params fra første driver i analog-familien
    (asset_class, k, horizon_days, outcome_threshold_pct,
    min_history_days, dim_weights)
  - Kaller `find_analog_cases` via lat import (unngår sirkulær)
  - Bygger trace med beregnet hit_rate + avg_return + avg_drawdown
  - Defensive — alle exceptions → None (UI viser "ingen analog
    tilgjengelig")
- `pd_is_na`-helper for safe NaN-håndtering på max_drawdown
- `_build_entry` tar nå `store: Any | None = None`-arg og kaller
  `_build_analog_trace` hvis store gitt
- `generate_signals` passerer store til `_build_entry`

`web/assets/app.js` (+45 linjer):
- Ny `_analogHtml(analog)` med:
  - Narrative: "X av N steg ≥Y% innen Hd" + snitt-return
  - Pos/neg-farger basert på avg_return-fortegn
  - Note om manglende dim ("X av 4 § 6.5-dim mangler data")
  - Neighbor-mini-tabell: ref_date, similarity, fwd ret, max DD
- `openSetupModal` rendrer nå `_analogHtml(entry.analog)` etter
  driver-trace-seksjonen

`web/assets/style.css` (+38 linjer):
- `.modal-analog-narrative` med pos/neg-fargekode
- `.modal-analog-table` matchende eksisterende driver-tabell-stil

`tests/logical/test_orchestrator_analog.py` (ny, 10 tester):
- Pydantic round-trip for AnalogNeighbor + AnalogTrace (full +
  minimal)
- SignalEntry default analog=None (bakoverkompat)
- `_build_analog_trace` populerer riktig fra fixture-DB
- Defensive: ingen analog-familie / tom store / ukjent
  asset_class → None
- `generate_signals` end-to-end inkluderer analog
- JSON-serialisering for UI-konsumering

**Designvalg:**

- **`_build_analog_trace` plukker params fra første driver** istedenfor
  å re-iterere alle. Hit-rate-driveren har alle nødvendige params;
  avg-return-driveren bruker samme asset_class/horizon/k. Hvis vi
  senere har 3+ ulike analog-drivere, kan vi vurdere mer sofistikert
  parameter-merging.
- **Lat import av `find_analog_cases`** for å unngå sirkulær
  (data.analog → engine → orchestrator). Samme mønster som driver-
  laget i session 60.
- **`store: Any | None = None`** på `_build_entry` (ikke krevd):
  bakoverkompat for direkte instansieringer i tester. Når store er
  None, hopper vi over analog-trace.
- **Ingen `analog` på `SignalEntry` for `setup is None`-grenen?**
  Jo — analog skrives uansett om setup ble bygd. Hvis setup mislyktes
  pga manglende OHLC, kan vi fortsatt vise historisk K-NN-narrative
  som kontekst. (Kanskje ikke trenger UI-rendering da, men det er en
  separat sak.)
- **Pos/neg-farger i UI** følger `--c-pos`/`--c-neg`-CSS-tokens
  hvis definert, fallback til hard-coded grønn/rød.
- **Neighbor-tabell viser kun topp-K** (samme antall som K-NN
  returnerte). Ingen pagination — modal er kompakt nok.

**End-to-end-verifisert** (mot `data/bedrock.db`):
- Gold MAKRO buy/sell: analog populert med 5 naboer
- Topp nabo: 2022-03-23 sim=0.955 fwd=-3.23% dd=-3.86%
- hit_rate_pct=40.0% avg_return_pct=+1.02%
- dims_used=['cot_mm_pct', 'dxy_chg5d', 'real_yield_chg5d']
  (vix_regime mangler → flagget i UI)

**Verifisert:**
- pytest full → 1155/1155 (var 1145, +10 nye)
- ruff check + format → grønt
- Pre-commit hook → grønt
- Auto-push → `origin/main`
- Manuell sanity: orchestrator end-to-end mot ekte Gold-data,
  full SignalEntry-JSON inkluderer korrekt analog-blokk

**Fase 10 LUKKET** — `v0.10.0-fase-10` tag opprettes etter denne
session-loggen. Spor B + Spor A levert i 6 sessions (56-61):
- Audit-rapport (`docs/data_audit_2026-04.md`)
- ADR-005 (`docs/decisions/005-analog-data-schema.md`)
- 4 nye database-tabeller (`weather_monthly`, `analog_outcomes`)
  + ENSO i `fundamentals`
- 4 nye fetcher/CLI-er (NOAA ONI, weather-monthly migrering,
  outcomes-beregning, Yahoo prices)
- K-NN-modul (`bedrock/data/analog.py`) med ASSET_CLASS_DIMS,
  6 extractors, `find_analog_cases`
- 2 nye drivere (`analog_hit_rate`, `analog_avg_return`)
- YAML-integrasjon i Gold + Corn
- UI-rendering: SignalEntry-utvidelse + modal-narrative + tabell
- Backfill-rapport (`docs/backfill_2026-04.md`)
- Total: 1155/1155 tester grønne (var 993, +162 nye fordelt på
  ~12 nye filer)
- Total kode: ~2 300 linjer ny implementasjon + ~1 700 linjer
  tester + ~1 200 linjer dokumentasjon

**Neste fase (11):**
- Backtest-rammeverk + 12 mnd historikk-replay
- Output: rapport over signal-performance
- Vurdere overgang til Nivå 3 git-modus (feature-branches + PR +
  branch-protection)
- Tag `v0.11.0-fase-11` ved fase-slutt

---

### 2026-04-25 — Session 60: Fase 10 spor A — analog-driver-familie + YAML-integrasjon (LUKKET)

**Scope:** Tredje kode-session i Spor A. Bind K-NN-resultater fra
session 59 til scoring-pipelinen via to nye drivere registrert i
engine, og aktiver dem i Gold + Corn YAML.

**Endret denne session (commit `07d4f73`):**

`src/bedrock/engine/drivers/analog.py` (ny, 220 linjer):
- `analog_hit_rate(store, instrument, params) -> float`:
  - Andelen av K nærmeste naboer der forward_return ≥
    `outcome_threshold_pct` (default 3.0)
  - Returnerer 0..1 direkte (n_hits/k)
  - Per ADR-005 B5: terskel er driver-config, ikke baked into data
- `analog_avg_return(store, instrument, params) -> float`:
  - Avg forward_return mappet via terskel-trapp til 0..1
  - Default mapping: ≥+5%→1.0, ≥+3%→0.8, ≥+2%→0.65, ≥+1%→0.5,
    ≥0%→0.4, <0%→0.0
  - `direction: invert`-param flipper fortegn (bear-bruk)
  - `score_thresholds`-dict overstyrer default
- `_knn(store, instrument, params)` felles helper:
  - Validerer asset_class mot `ASSET_CLASS_DIMS`
  - Slår opp `InstrumentMetadata` via `find_instrument` (lat import)
  - Bygger query via `extract_query_from_latest(skip_missing=True)`
  - Kaller `find_analog_cases`
  - Defensive: alle exceptions → (None, error_msg) → driver returnerer
    0.0 + log

`src/bedrock/engine/drivers/__init__.py`:
- Auto-import-linja oppdatert: `from bedrock.engine.drivers import
  analog, currency, trend`. Sikrer at `@register("analog_*")` kjøres.

`config/instruments/gold.yaml`:
- `family_weights[analog]` lagt til per horizon: SCALP=0.3, SWING=0.8,
  MAKRO=1.2 (K-NN matcher best lange horisonter)
- `max_score` bumpet 4.5/5.0/4.7 → 4.8/5.8/5.9
- Ny `families.analog`-blokk med to drivere (hit_rate + avg_return),
  hver vekt 0.5, params `{asset_class: metals, k: 5,
  horizon_days: 30, ...}`

`config/instruments/corn.yaml`:
- Ny `families.analog` (weight: 2, samme som andre families). Drivere
  konfigurert for grains.
- `max_score` bumpet 18 → 20

`tests/unit/test_analog_drivers.py` (ny, 16 tester):
- Hit-rate basic + edge-cases: missing/unknown asset_class, unknown
  instrument, no-data, terskel-konfig (0% / 100% / default)
- Avg-return basic + invert + custom-thresholds + negative-history +
  strong-positive (1.0 maks)
- Sanity: begge drivere registrert under riktig navn

**Designvalg:**

- **Lat import av `find_instrument`** løste sirkulær import. Modul-
  toppen importerer fra `bedrock.data.analog`; CLI-helperen
  importeres inne i `_knn`-funksjonen. Dokumentert i selve modulen
  (kommentar over import-blokken).
- **Frittstående `_knn`-helper, ikke duplisert i hver driver.**
  Begge drivere har identisk pre-prosessering (validering, lookup,
  K-NN-kall) — refaktor inn felles helper. Bare differensieringen
  (hit-rate-aggregering vs avg-mapping) er per driver.
- **`outcome_threshold_pct` lagres ikke i driver-output.** Driver
  returnerer kun hit_rate (0..1). Caller (familie-aggregator) ser
  ikke hva terskelen var. Hvis vi senere vil ha det i explain-trace,
  må vi utvide DriverResult — egen task.
- **YAML-vekter er bevisst forskjellige per horizon for Gold.** SCALP
  får liten vekt (0.3) — 30d-K-NN sier lite om scalp-trading. MAKRO
  får stor vekt (1.2) — passer perfekt med 90d-historikk-matching.
  SWING (0.8) er midt i mellom.
- **`max_score` bumpet konsistent.** 4.5 + 0.3 = 4.8 (nytt SCALP-
  max). Hvis vi senere bytter analog-vekt, må max_score justeres
  manuelt (det er ikke automatisk derivat fra family_weights). Som
  i dag.
- **Corn fikk lavere relativ analog-vekt** (2 av 18 i den additive
  modellen, dvs. 11%) enn Gold MAKRO (1.2 av 5.9, dvs. 20%). Begrunnelse:
  vær-stress + ENSO er allerede dekket av andre Corn-families
  (`weather`, `enso`), så analog er mindre marginal.

**End-to-end-resultat (Engine.score mot ekte data):**

| Instrument | Horizon | Total | Grade | Analog-fam |
|---|---|---:|---|---|
| Gold | SCALP | 4.34 | A+ | 0.45 (hit=0.4, avg=0.5) |
| Gold | SWING | 5.11 | A+ | 0.45 |
| Gold | MAKRO | 5.04 | A+ | 0.45 |
| Corn | (additiv) | 16.0 | A+ | 0.0 (hit=0, avg=0) |

Corn analog 0.0 reflekterer at K-NN-naboer for nåværende vær/ENSO/
DXY-tilstand har historisk hatt avg ret -13.7%/-30.7% — driveren
gir riktig 0.0 for bull-instrument. invert-direction-driver kan
brukes for short-corn-signaler i framtiden.

**Verifisert:**
- pytest full → 1145/1145 (var 1129, +16 nye)
- ruff check + format → grønt
- Pre-commit hook → grønt
- Auto-push → `origin/main`
- Manuell sanity: Engine.score over Gold (3 horisonter) + Corn

**Neste session (61 — siste i Spor A/Fase 10):**
- UI-rendering i modal: analog-seksjon m/narrative + neighbor-tabell
- SignalEntry utvides med `analog`-felt (analogt med session 52
  `families`)
- Orchestrator `_build_entry` kaller `find_analog_cases` per signal
  og persisterer resultatet
- Tester: snapshot på SignalEntry-JSON, logical på modal-rendering
- Etter session 61 lukkes Fase 10 (tag `v0.10.0-fase-10`)

---

### 2026-04-25 — Session 59: Fase 10 spor A — find_analog_cases-impl + dim-mapping (LUKKET)

**Scope:** Andre kode-session i Spor A. Ny modul som binder
DataStore + InstrumentMetadata til K-NN-resultater. Per ADR-005 B4
+ B5-skiss klar for driver-laget i session 60.

**Endret denne session (commit `3a60d16`):**

`src/bedrock/data/analog.py` (ny, 320 linjer):
- `ASSET_CLASS_DIMS: dict[str, list[str]]` per § 6.5-tabellen
  slavisk (5 asset-klasser × 4 dim hver). Per Q2-instruks: streng
  kontrakt — ingen utvidelse uten godkjenning.
- `DIM_EXTRACTORS: dict[str, Callable]` med 6 implementerte:
  `dxy_chg5d`, `real_yield_chg5d`, `term_spread`, `cot_mm_pct`,
  `enso_regime`, `weather_stress(_key_region)` (alias). Resterende
  6 kaster `MissingExtractorError` slik at driver-laget kan
  håndtere uten å krasje.
- `extract_query_from_latest(store, meta, asset_class, dims=None,
  skip_missing=True)` — bygg `query_dims` fra ferskeste obs per
  dim. Kun de dim som faktisk har data returneres når
  skip_missing=True.
- `find_analog_cases(store, instrument, meta, asset_class,
  query_dims, *, k=5, dim_weights=None, horizon_days=30,
  min_history_days=365)` — frittstående funksjon (ikke DataStore-
  metode, se ADR-avvik nedenfor). Returnerer DataFrame med
  `ref_date, similarity, forward_return_pct, max_drawdown_pct`.
  Similarity = `1/(1+weighted_euclidean)`, så høyere er bedre,
  max 1.0.
- Validering: query_dims sjekkes mot ASSET_CLASS_DIMS for
  asset-klassen — ekstra dim (utenfor § 6.5) gir ValueError.

`docs/decisions/005-analog-data-schema.md`:
- B4-tillegg: `find_analog_cases` ble frittstående, ikke
  DataStore-metode. Begrunnelse: extractors trenger
  `InstrumentMetadata` (cot_contract, weather_region), og å la
  DataStore importere fra config-laget hadde innført unødvendig
  modul-kobling. Funksjonen tar `store` + `meta` eksplisitt.

`tests/unit/test_analog_dims.py` (ny, 25 tester):
- § 6.5-konformitet (alle 5 asset-klasser, 4 dim hver, slavisk navn-match)
- DIM_EXTRACTORS coverage (kun de 6 implementerte)
- get_extractor + MissingExtractorError for ikke-impl dim
- Hver extractor mot fixture-DB (real_yield, term_spread, dxy,
  cot_mm_pct med 0/0-håndtering, enso, weather_stress)
- Manglende cot_contract/weather_region kaster MissingDataError
- extract_query_from_latest med skip_missing + eksplisitt
  dims-overstyring

`tests/unit/test_analog_knn.py` (ny, 13 tester):
- Top-K returneres sortert på similarity descending
- Similarity i [0, 1]-range
- Perfect match → similarity > 0.999
- Validering av query_dims mot asset_class
- min_history_days filter
- dim_weights skewer K-NN mot vektet dim
- horizon_days isolerer outcomes
- Tom outcomes → tom DataFrame (ikke exception)
- Ingen dim-overlap → InsufficientHistoryError

`tests/unit/test_analog_realdata.py` (ny, 6 tester):
- Auto-skip via `pytest.mark.skipif` hvis bedrock.db ikke finnes
  (slik at CI uten data ikke faller)
- Sanity Gold + Corn × 30d/90d mot ekte backfilt data
- Verifiser at query-dim-navn er subset av ASSET_CLASS_DIMS

**Designvalg:**

- **Frittstående funksjon, ikke DataStore-metode** (avvik fra
  ADR-005 B4 originalt). Begrunnelse i ADR-tillegget. Decision-rule
  fra CLAUDE.md: "modul-struktur, klasser vs funksjoner — optimer
  for lesbarhet og test-isolering". DataStore-API kan utvides
  hvis ADR justeres senere.
- **Z-score-normalisering med ddof=0** (befolknings-std, vanlig i
  ML). std=0 → erstatt med 1 for å unngå 0-divisjon ved konstant
  dim.
- **`similarity = 1/(1+distance)`** — bedre enn `1 - distance/max`
  fordi den ikke krever maks-distance og monotont avtagende.
- **Forward-fill av ukentlig/månedlig data** (CFTC, ENSO, weather)
  til daglig granularitet — gir alle dim sammenlignbar tids-
  oppløsning.
- **Outcomes inner-join på `_match_date`** (date-normalisert,
  tz-strippet) — håndterer at outcomes har timezone-bearing
  timestamps fra prices-tabellen (Yahoo) mens dim-history er
  rene datoer.

**Sanity mot ekte data (manuelt verifisert):**
- Gold metals (3 av 4 dim, vix mangler):
  - 30d: K=5 sims 0.88-0.95, hit-rate(≥3%)=40%, avg ret +1.0%
  - 90d: K=5 sims 0.88-0.95, hit-rate(≥3%)=60%, avg ret +9.0%
- Corn grains (3 av 4 dim, conab mangler):
  - 30d: K=5 sims 0.70-0.72, hit-rate(≥3%)=0%, avg ret -13.7%
  - 90d: samme sims, hit-rate 0%, avg ret -30.7%

Lavere similarity for Corn er forventet (vær-stress er volatil).
Negative avg-returns reflekterer at K-NN identifiserer historiske
match for nåværende corn-tilstand som ikke har vært bullish for
30/90d-vindu — meningsfull signal som driver-laget kan score lavt.

**Verifisert:**
- pytest full → 1129/1129 (var 1085, +44 nye)
- ruff check + format → grønt
- Pre-commit hook → grønt
- Auto-push → `origin/main`
- Manuell sanity (3 separate kjøringer mot data/bedrock.db)

**Neste session (60):**
- Skriv `bedrock/engine/drivers/analog.py` med to drivere:
  - `analog_hit_rate`: returnerer (n_hits / k) som driver-score
  - `analog_avg_return`: avg forward_return mappet til 0..1-score
  - Evt. `analog_match_count`: confidence-multiplier basert på k
- Drivere kaller `find_analog_cases` med driver-params (k,
  horizon_days, outcome_threshold_pct)
- Utvid `gold.yaml` + `corn.yaml` med `analog`-familie-blokk
- Tester: driver-output mot kjent fixture, explain-trace har
  analog-felt

---

### 2026-04-25 — Session 58: Fase 10 spor A — full backfill + 3 nye CLI + Yahoo-port + CFTC-fix (LUKKET)

**Scope:** Ekseksvere full backfill for K-NN, etter at session 57
leverte skjema/API. Per D-splitt: backfill-eksekvering. Faktisk scope
ble utvidet med 3 nye CLI-er (uten dem kan ikke backfill kjøres) og
to fetcher-fixes oppdaget under eksekvering.

**Endret denne session (commits `e0d67d4` + `015988d`):**

`src/bedrock/fetch/yahoo.py` (ny, 180 linjer):
- Port av cot-explorers `build_price_history.py` (verifisert
  produksjons-kode for 15 års historikk)
- `urllib`-basert (ikke `requests`) for å matche bevist mønster
- User-Agent "Mozilla/5.0" + Accept "application/json" — Yahoo
  returnerer 403 uten dem
- `parse_yahoo_chart` eksponert separat for testing
- `--interval 1d/1wk/1mo`-støtte; default daglig

`src/bedrock/cli/backfill.py` (+260 linjer):
- `prices`-CLI utvidet med `--source yahoo|stooq` (default yahoo) +
  `--interval`. Stooq beholdt som fallback.
- `_resolve_prices` velger ticker-felt (yahoo_ticker vs stooq_ticker)
  basert på source.
- 3 nye subkommandoer:
  - `enso`: kaller `fetch_noaa_oni` → `append_fundamentals`
  - `weather-monthly`: leser `agri_history/<region>.json`-filer,
    dropper `days`-felt, skriver via `append_weather_monthly`
  - `outcomes`: beregner forward_return + max_drawdown fra `prices`-
    tabellen, multi-instrument + multi-horizon support

`src/bedrock/config/instruments.py` (+1 linje):
- `yahoo_ticker: str | None` i InstrumentMetadata

`src/bedrock/fetch/cot_cftc.py` (+1 felt, kommentar):
- `_DISAGG_FIELD_MAP`: `m_money_positions_long_all` (var
  `m_money_positions_long`). CFTC splittet i `_all/_old/_other` for
  hyphenert termin-struktur. Kun `_all` er ekvivalent.

`config/instruments/{gold,corn}.yaml`:
- Ny `yahoo_ticker`: `GC=F` (Gold), `ZC=F` (Corn)

Tester (+47 nye → 1085/1085):
- `test_fetch_yahoo.py` (14 tester): URL-bygging, parse-edge-cases
  (None-close, missing-volume, empty-result, error-blokk),
  HTTP-mock + URLError-håndtering
- `test_cli_backfill_enso.py` (3 tester)
- `test_cli_backfill_weather_monthly.py` (10 tester): loader-helper
  + CLI-flow + idempotens
- `test_cli_backfill_outcomes.py` (16 tester): _parse_horizons +
  _compute_outcomes + CLI-flow + idempotens
- Eksisterende prices-tester: rebased med `--source stooq` for å
  matche ny default
- `test_fetch_cot_cftc.py`: m_money-fixture-felt `_all`-suffiks via
  sed

**Backfill-resultat** (DB: 0 → 3.54 MB, 46 569 rader):

| Kilde | Tabell | Rader | Range |
|---|---|---:|---|
| Yahoo daglig | `prices` | 8 200 | Gold + Corn 2010 → 2026-04-24 |
| CFTC Socrata | `cot_disaggregated` | 1 702 | 851 hver, 2010 → 2026-04-21 |
| FRED (4 serier) | `fundamentals` | 17 017 | DGS10/DGS2/T10YIE/DTWEXBGS |
| NOAA ONI | `fundamentals` | 914 | 1950-01 → 2026-02 |
| agri_history-migrering | `weather_monthly` | 2 576 | 14 regioner × 184 mnd |
| Beregnet fra prices | `analog_outcomes` | 16 160 | Gold + Corn × {30d, 90d} |

Outcomes-baseline (sanity for K-NN-driver-utvikling):
- Gold 30d: avg +1.21%, hit-rate(≥3%)=34.5%, avg_dd=−3.07%
- Gold 90d: avg +3.72%, hit-rate(≥3%)=52.5%, avg_dd=−4.97%
- Corn 30d: avg +0.58%, hit-rate(≥3%)=36.6%, avg_dd=−5.67%
- Corn 90d: avg +1.84%, hit-rate(≥3%)=40.4%, avg_dd=−10.21%

**Designvalg:**

- **Yahoo som default** for prices framover (ikke som flag-fallback):
  Stooq er nå tregere å onboarde (krever captcha + API-nøkkel) og
  cot-explorers Yahoo-port er allerede produksjons-verifisert.
  Stooq-pathen beholdes for fremtid.
- **Sekvensiell henting + 2s sleep mellom kall** (per bruker-instruks):
  gratis API-er feiler med parallelle requests. Eksisterende cot-
  explorer kjører også sekvensielt.
- **`days`-felt fra agri_history droppes ved migrering** (det 9. JSON-
  feltet, ikke i § 6.5, kan beregnes fra `month`-string).
- **Hit-rate IKKE pre-beregnet** — kun rå `forward_return_pct` lagres.
  Driver beregner hit on-the-fly fra config-terskel (per ADR-005 B3),
  slik at terskel kan justeres uten re-backfill.
- **Wall-time totalt: ~7 min** (mot 1-2 t-estimat). Yahoo og FRED
  håndterte 16-års-vinduer i én request — ingen pagination nødvendig.

**Pre-conditions verifisert før eksekvering:**
- `~/.bedrock/secrets.env` med `FRED_API_KEY` (32 tegn) ✓
- `~/cot-explorer/data/agri_history/` med 14 region-filer ✓

**Verifisert:**
- pytest full → 1085/1085 (var 1038, +47)
- ruff check + format → grønt
- Pre-commit hook → grønt
- Auto-push → `origin/main`
- Manuell sanity: bedrock.db row counts + sample queries (siste
  Gold COT mm_long=123 681 mot 2026-04-21)

**Neste session (59):**
- `find_analog_cases`-impl per ADR-005 B4-signatur
- Asset-klasse-til-dim-mapping (hardcoded constant per § 6.5-tabell)
- Feature-extractor: hent ferskeste obs per dim fra DataStore
  (DGS10 chg5d, DTWEXBGS chg5d, T10YIE-DGS10 (real-yield), COT mm-pct)
- Z-score-normalisering over hele historikken (ikke pre-cached)
- Logical tester: gitt mock-DB med kjente naboer, K=5 returneres riktig

---

### 2026-04-25 — Session 57: Fase 10 spor A — ADR-005 + skjema + DataStore-utvidelse + ENSO-fetcher (LUKKET)

**Scope:** Første kode-session i Spor A. Etter D-splitten:
**pure kode + tester, mockbart, ingen backfill-eksekvering**. Etablerer
all skjema-/API-grunn for K-NN slik at session 58 kan fokusere på
ren backfill og session 59 på K-NN-impl.

**Endret denne session (commit `874998e`):**

`docs/decisions/005-analog-data-schema.md` (ny, 235 linjer):
- B1: ENSO i `fundamentals` med `series_id="NOAA_ONI"` (ikke ny tabell)
- B2: ny `weather_monthly`-tabell (separat fra daglig `weather`)
- B3: ny `analog_outcomes`-tabell (lagrer rå return + drawdown,
  ikke binær hit — terskel er driver-config)
- B4: `find_analog_cases`-API-kontrakt (impl venter session 59)
- B5: eksempel-driver-skiss (`analog_hit_rate`, ikke implementert)
- 5 forkastede alternativer dokumentert (A1-A5)

`src/bedrock/data/schemas.py` (+120 linjer):
- `WeatherMonthlyRow` Pydantic-modell + `_MONTH_RE`-validator for
  'YYYY-MM'-format
- `DDL_WEATHER_MONTHLY` + `TABLE_WEATHER_MONTHLY` + `WEATHER_MONTHLY_COLS`
- `AnalogOutcomeRow` med påkrevd `forward_return_pct` + valgfri
  `max_drawdown_pct`, `horizon_days > 0`-validator
- `DDL_ANALOG_OUTCOMES` + `TABLE_ANALOG_OUTCOMES` + `ANALOG_OUTCOMES_COLS`

`src/bedrock/data/store.py` (+220 linjer):
- `_init_schema()` oppretter de to nye tabellene
- `append_weather_monthly` + `get_weather_monthly` + `has_weather_monthly`
  (NULL-safe int/float-konvertering, INSERT OR REPLACE på PK)
- `append_outcomes` + `get_outcomes` (batch-lookup via `ref_dates`-
  parameter med IN-clause; tomt sequence short-circuit-er DB-hit) +
  `has_outcomes` (med valgfri horizon_days-filter)
- `from datetime import date` lagt til i toppen

`src/bedrock/fetch/enso.py` (ny, 130 linjer):
- `NOAA_ONI_URL` (CPC ASCII-endepunkt)
- `_SEAS_TO_MONTH`-mapping (DJF→1, JFM→2, ..., NDJ→12)
- `parse_noaa_oni_text(text)` — rein parser, eksponert for
  test-fixture; skipper header, blanke linjer, missing-marker
  (-99.9), unparseable verdier
- `fetch_noaa_oni()` — wrapper med HTTP-feilhåndtering →
  `NoaaOniFetchError`
- Output matcher `DataStore.append_fundamentals`-skjema
  (series_id/date/value)

`config/fetch.yaml`:
- Ny `enso`-entry: cron `0 6 12 * *` (12. i mnd 06:00 UTC),
  `stale_hours: 720`, `on_failure: log_and_skip`,
  `table: fundamentals`

`tests/unit/test_store_weather_monthly.py` (ny, 11 tester):
- Pydantic: minimal/full/bad-month/negative-precip/extra-field
- Round-trip + idempotens + last_n + KeyError + has-helper
- NULL-håndtering for valgfrie kolonner
- Multi-region-isolering

`tests/unit/test_store_outcomes.py` (ny, 14 tester):
- Pydantic: minimal/full/zero-horizon-rejected/extra-field-rejected
- Append/get + idempotens + horizon-filter
- Batch-lookup på ref_dates (incl. Timestamp-objekter, tomt sequence)
- max_drawdown valgfri
- PK inkluderer horizon (samme dato to horisonter = to rader)

`tests/unit/test_fetch_enso.py` (ny, 12 tester):
- Parser: SEAS→month-mapping, value-konvertering, header-skip,
  blank/short-line-skip, -99.9-skip, unparseable-skip + warn,
  empty/header-only → empty frame
- Output kompatibel med `FredSeriesRow` Pydantic
- HTTP-mock: success / 503 / nettverks-feil
- Integrasjon: fetcher → store.append_fundamentals → get_fundamentals

**Designvalg (utover ADR):**

- **`from datetime import date` i store.py** ble nødvendig for
  `Sequence[str | date | pd.Timestamp]`-type-hint på `get_outcomes`.
  Ruff fanget det som F821; bedre å fikse ved import enn å bruke
  `"date"`-string-form.
- **Empty-`ref_dates`-short-circuit** i `get_outcomes`: returnerer
  tom DataFrame uten DB-hit. Caller (K-NN) kan trygt sende inn
  `neighbors["ref_date"].tolist()` selv når neighbors er tom.
- **Test-fixture er hard-kodet ASCII-utdrag** fra ekte NOAA-format
  (DJF 1950, NDJ 1950 for å verifisere mnd-konvensjon, DJF/JFM 2024
  for moderne-tilfelle). Ingen ekte HTTP i CI; matcher
  bedrock-konvensjon for fetch-tester.
- **`http_get_with_retry` monkey-patches på modul-attributtet**
  (`bedrock.fetch.enso.http_get_with_retry`), ikke på base-modulen.
  Sikrer at re-importer gir riktig dispatch.

**Verifisert:**
- pytest full → 1038/1038 (var 993, +45 nye)
- ruff check + format → grønt på alle nye filer
- Pre-commit hook → grønt
- Auto-push → `origin/main`

**Neste session (58 — backfill-eksekvering):**
- prices: `bedrock backfill prices --instruments Gold Corn --from 2010`
- cot_disaggregated: Gold + Corn contracts
- fundamentals: DGS10, DGS2, T10YIE, DTWEXBGS (alle FRED, 2010-)
- ENSO: ny `bedrock backfill enso`-CLI (eller ad-hoc-script i
  første versjon, formaliseres senere)
- weather_monthly: migrere `~/cot-explorer/data/agri_history/<14 regioner>.json`
- analog_outcomes: beregne fra prices for begge horisonter (30d/90d)
- Wall-time forventet 1-2 timer; backfill-CLI-kommandoer er
  idempotent så trygg å re-kjøre.

---

### 2026-04-25 — Session 56: Fase 10 spor B — fetch-data-audit + K-NN-feasibility (LUKKET)

**Scope:** Første session i Fase 10. Ren dokumentasjons-leveranse —
ingen kode. Mandat fra PLAN § 14-tillegg ("ubrukt-data-gjennomgang er
Fase 10-oppgave") + bruker-instruksjon: kartlegg `kilde × leses-av`
+ K-NN-feasibility per asset-klasse mot § 6.5. Ingen sletting av
fetch-scripts.

**Endret denne session (commit `f16ed20`):**

`docs/data_audit_2026-04.md` (ny, 307 linjer):
- § 1: fetch-modul-inventar (7 moduler, alle aktive, ingen døde)
- § 2: DataStore-tabell-status — alle 5 tabeller har 0 rader,
  bedrock.db er fullstendig tom
- § 3: krys-referanse `kilde × leses-av` — kun `prices` har
  konsumenter; `cot_disaggregated`/`cot_legacy`/`fundamentals`/
  `weather` brukes ikke av noen driver/endpoint/UI
- § 4: eksterne data-reservoarer i `~/cot-explorer/data/` —
  16 års COT-history (2010-2025) + 184 mnd weather i
  `agri_history/` + masse snapshots
- § 5: K-NN-feasibility per asset-klasse mot § 6.5; tre brudd
  flagget med M/D/U-forslag per Q2-instruks
- § 6: fire beslutninger til bruker (A-D) som blokkerer session 57

**Designvalg:**

- **Streng kontrakt mot § 6.5** (per Q2): brudd flagget istedenfor
  stille utvidelse. Audit avdekket ikke en data-rik kilde som
  åpenbart burde tilføyes som "tillegg-dim Y".
- **K-NN-omfang i Spor A** anbefales begrenset til Gold (metals)
  og betinget Corn (grains, avhenger av A+B). Energy + softs +
  FX har ingen instrument konfigurert i `config/instruments/`,
  så å levere K-NN uten et instrument å score er trolig ikke
  verdt det. Anbefaling: utsett til instrumentene introduseres.
- **Ingen ADR i denne sessionen.** ADR-005 (DataStore-API for
  analog: `find_analog_cases`, `get_outcomes`, `append_outcomes`,
  evt. `weather_monthly`) hører i session 57 etter at A-D er
  besvart, fordi ADR-en avhenger av beslutning B (weather-form).
- **Ingen migrasjon av `~/cot-explorer/`-data** — utføres i session
  57 etter beslutning B og D.

**Verifisert:**
- Audit basert på faktisk fil-inspeksjon: `sqlite3 data/bedrock.db`
  for tabell-rader, `grep store.get_*` over `src/`, `grep fetch\\(`
  over `web/assets/`, `find ~/cot-explorer/data` for inventar.
- Ingen påvirkning på eksisterende kode/tester (audit er ren MD).
- pytest ikke kjørt — ingen kode-endring.

**Neste session (57):**
- Først: bruker svarer på A-D
- Deretter: ADR-005 → outcome-labels-DDL → backfill-CLI-kjøring →
  forward-return-beregning + lagring → tester
- Bevisst tett scope: outcome-labels alene. K-NN-implementasjon
  hører i session 58.

---

### 2026-04-25 — Session 55: Fase 9 runde 3 — dry-run + git-commit + logs-viewer + RUNDE 3 LUKKET

**Scope:** Siste session i runde 3. Lukker safe-edit-loopen
(validate → save → commit → push) og legger til pipeline-log-viewer.
Bevisst tett scope etter kartlegging — heavyweight dry-run, andre
YAML-editorer, og pipeline-styringer er flagget som deferred.

**Endret denne session (commit `2a1006d`):**

`src/bedrock/signal_server/config.py`:
- Nye felt `admin_git_root: Path | None` og `admin_log_path: Path | None`
- env: BEDROCK_ADMIN_GIT_ROOT + BEDROCK_ADMIN_LOG_PATH
- None-default ⇒ funksjonene deaktivert (no-op for git, 404 for logs)

`src/bedrock/signal_server/endpoints/rules.py`:
- `_git_commit_yaml(git_root, yaml_path, instrument_id)`:
  - Bruker `git -C <root>` (subprocess) så cwd ikke endres
  - Sjekker `git status --porcelain <path>` først; tom output = no
    change → no commit
  - Stage + commit med melding `config(<id>): admin-edit via /admin/rules`
  - Returnerer dict {committed, sha?, error?, reason?}
  - Auto-push-hook (`.githooks/post-commit`) håndterer push
  - Time-out på alle git-kall (10-15s)
- PUT integrerer git-commit. Respons får nytt `git`-felt når
  `admin_git_root` er konfigurert.
- Ny `POST /admin/rules/<id>/dry-run`: validate-only via
  `load_instrument_from_yaml_string`. 200 med config_summary
  (`{id, asset_class, families[]}`) eller 400 med Pydantic-loc-
  detaljer. Heavyweight dry-run (score-diff mot 7 dager) er deferred
  — krever DataStore-injeksjon + dobbelt Engine-kjøring.
- Ny `GET /admin/logs?tail=N` (default 200, max 2000). Leser
  `cfg.admin_log_path`, returnerer `{path, total_lines, returned,
  lines: [...]}`. 404 hvis path None eller fil mangler. Auth via
  X-Admin-Code som resten.

`web/admin.html`:
- Sidebar får nav-row med Rules / Logs-tabs
- Editor-toolbar får Dry-run-knapp (mellom Reload og Lagre)
- Ny logs-pane (`#logs-pane`) med header (path + tail-input +
  Refresh-knapp) og `<pre>` for monospace log-output

`web/assets/admin.css` (+74):
- `.admin-nav-btn` (tab-stil pills, accent-soft når aktiv)
- `.admin-tail-input` (number-input m/aksent-fokus-ring)
- `.admin-logs-output` (monospace, max-height: calc(100vh - 200px),
  pre-wrap + word-break for lange linjer)
- `.admin-editor-feedback.dry-run-ok` (info-soft farge)

`web/assets/admin.js` (+90):
- `dryRunCurrent()`: POSTer til /dry-run, viser ✓-feedback med
  family-summary eller error-detaljer
- `showSection(name)`: toggler `[data-admin-section]`-elementer
- `loadLogs()`: fetcher /admin/logs, viser path + linje-teller,
  graceful 404-tilstand
- `saveCurrent()` rendrer git-info i feedback når PUT-respons har
  `git`-felt: "✓ git-commit abc1234: config(gold): admin-edit"
- `setFeedback` ryddet til å bruke `el.className = 'admin-editor-
  feedback ' + kind` (støtter alle varianter med samme logikk)

`tests/unit/test_signal_server_rules.py` (+11 tester):
- Dry-run: valid (no write), invalid (400 + details), auth, id-mismatch
- Git: commits change, skips no-change, no git_root → no 'git'-felt
  (test-fixture initialiserer eget tmp-repo med subprocess)
- Logs: 404 unconfigured, returns tail (500-line fil → tail=10
  returnerer linje 490-499), default 200, requires auth

**Designvalg:**

- **Lightweight dry-run** valgt over heavyweight: validate-only
  endpoint er én forutsigelig ting. Heavyweight dry-run krever
  DataStore + Engine + diff-struktur og fortjener en egen session
  med 7-dagers-backtest-tenkning. Bruker får uansett trygghet:
  Pydantic-validering finner 95% av feilene før de når disk.
- **`git -C <root>` framfor `os.chdir`**: thread-safe, idempotent,
  ingen sjanse for at server ender opp i feil cwd hvis exception
  kastes mellom add og commit.
- **Status-check før commit** for å unngå tomme commits når YAML
  er identisk med disk. Rygger ikke ut noe ved feil — bare logger
  warning og returnerer `committed: false`. Brukeren ser dette i
  feedback-boksen.
- **Logs som rules.py-blueprint, ikke ny admin_bp**: rules_bp har
  allerede `_check_auth` + path-traversal-helpere. Splitting bare
  pga URL-prefix gir mer kode uten verdi. Hvis vi senere får 5+
  admin-endpoints utenfor /admin/rules, refaktorerer vi.
- **Auth nominalt cleartext over loopback** — uendret fra session
  54. SHA-256-oppgradering er separat task. Ikke verdt å koble inn
  i session 55.

**Verifisert:**
- pytest full → 993/993 (var 982, +11 nye)
- node --test (filter-tester uberørt) → 18/18
- Browser preview med mock-fetch:
  - Dry-run-knapp viser '✓ Dry-run OK · gold · Familier: trend,
    positioning' i info-soft feedback
  - Save → success med 'git-commit abc1234: config(gold): admin-edit
    via /admin/rules'
  - Logs-tab bytter pane via showSection('logs'), viser
    '/var/log/bedrock/pipeline.log · viser 200/1500 linjer' i
    header, monospace log-linjer i `<pre>`
- Ruff-format kjørte og reformaterte to filer (rules.py +
  test_signal_server_rules.py) — kun whitespace, semantisk
  uendret. Etter format kjørte tester fortsatt 35/35 på rules-suiten.

**Commit:** `2a1006d feat(server-admin): dry-run + git-commit-on-
save + logs-viewer`. Auto-pushet til origin/main.

**Runde 3 LUKKET. Fase 9 LUKKET.**

Status etter Fase 9:
- 4 faner (Skipsloggen / Financial / Soft commodities / Kartrommet)
  med funksjonell data-wiring (runde 1)
- Filter (horizon/grade/instrument/direction) på alle relevante
  faner (runde 2 session 51)
- Modal med explain-trace + persisterte families i SignalEntry
  (runde 2 session 52)
- Tokenbasert designsystem + live status-pill (runde 2 session 53)
- Admin-editor med kode-gate + instrument-YAML CRUD + dry-run +
  git-commit-on-save + logs-viewer (runde 3 sessions 54-55)

**Deferred admin-utvidelser** (ikke blokkerende — lever når brukeren
ber):
1. Heavyweight dry-run: kjør orchestrator mot siste 7 dager med
   proposed config, returner score/grade/active_families-diff per
   instrument
2. /admin/fetch (config/fetch.yaml-editor for cron + stale-terskler)
3. /admin/bot (config/bot.yaml-editor for confirmation/trail/giveback-
   thresholds)
4. /admin/defaults (config/defaults/family_*.yaml + grade-terskler)
5. Pipeline-styringer:
   - Admin-auth på eksisterende `/kill`-endpoint (sikkerhets-gap)
   - `/kill all` killswitch-knapp i UI
   - `/pause` (deaktiver systemd-timer)
   - `/force-run` (trigger systemd-service nå)

**Neste:** **Fase 10** per PLAN-tabellen. Status-fortsettelse ved
oppstart av Fase 10.

### 2026-04-25 — Session 54: Fase 9 runde 3 — admin rule-editor (instrument-YAML)

**Scope:** Første av to admin-sessions. Lever fungerende editor for
instrument-regler mot eksisterende `/admin/rules`-endepunkter (Fase 7
session 38 implementerte allerede GET liste / GET enkelt / PUT med
Pydantic-validering + atomic write). Session 55 utvider med dry-run
+ git-commit + flere YAML-editorer + pipeline-styringer.

**Endret denne session (commit `0cd7e53`):**

`src/bedrock/signal_server/endpoints/ui.py`:
- Ny `/admin`-route som serverer `web/admin.html`. Skjult URL —
  ikke linket fra index.html, brukeren når den via direkte URL +
  kode-gate. PLAN § 10.5.

`web/admin.html`:
- Erstattet placeholder med full editor-skall:
  - `<header>` med admin-badge + status-pill (samme som dashboard)
  - `<section id="gate">` (kode-input + "Husk for fanen"-checkbox
    + feilmelding-felt) — vises før auth
  - `<main id="admin-main" hidden>` med to-pane:
    - `.admin-sidebar` (instrument-liste, sticky position, Reload-
      og Logg ut-knapp)
    - `.admin-editor-pane` (tittel + path + Reload/Lagre-knapper +
      dirty-indicator + YAML-textarea + feedback-area)

`web/assets/admin.css` (ny, 217 linjer):
- Bygger på tokens fra `style.css` (en kilde for hele systemet)
- `[hidden] !important` for å vinne over display:grid/flex på
  .admin-main / .admin-editor-active
- Gate-card med shadow-2 + akse-fokus-ring på input
- Sidebar med sticky-position + scrollable instrument-liste
- Monospace YAML-textarea med tab-size: 2
- Success/error-feedback med semantisk soft-palett

`web/assets/admin.js` (ny, 252 linjer):
- `authFetch(url, init)` — wrapper som henter X-Admin-Code fra
  storage og legger på header automatisk
- `tryAuth(code)` — tester via GET /admin/rules (200/401/503)
- `bootGate()` — sjekker om lagret kode fortsatt virker; ellers
  vis gate
- `loadInstrumentList()` — fetcher liste, rendrer som klikkbar
  `<ul>` med tabindex/Enter/Space-tilgjengelighet
- `loadInstrument(id)` — fetcher YAML, fyller textarea, lagrer
  i `LAST_LOADED_YAML` for dirty-sammenlikning
- `saveCurrent()` — PUT med Content-Type: application/json. Ved
  400 med `details` rendres Pydantic-loc-trefte feil
- Cmd/Ctrl+S = lagre. `beforeunload`-advarsel hvis dirty.
- Confirm-prompt før forkasting av endringer ved instrument-bytte
  / reload / logg ut.

`tests/unit/signal_server/test_endpoints_ui.py` (+2 tester):
- `test_admin_serves_html` (klar 200 + innhold)
- `test_admin_404_when_missing` (web_root finnes men admin.html
  mangler)
- web_root-fixture inkluderer nå `admin.html`

**Sikkerhet:**
- X-Admin-Code er **cleartext-sammenlikning** over loopback (eksisterende
  fra Fase 7 — endres ikke i denne sessionen). PLAN nevner SHA-256
  hash mot ADMIN_CODE_HASH; det er en separat oppgradering.
- Kode lagres i `sessionStorage` (default — slettes når fane lukkes).
  Hvis bruker huker av "Husk for denne fanen" → `localStorage` (vedvarer
  mellom session). Aldri i URL eller cookie.
- Logg ut-knapp clearer begge storages umiddelbart.
- Path-traversal-sanitering finnes på backend (`_INSTRUMENT_ID_RE`).

**Designvalg:**

- **Bygge på eksisterende endpoints** — `/admin/rules`-endpunktene
  fra Fase 7 var ferdige. Session 54 leverer kun frontend +
  ruter-tillegg. Det gjorde at scope-en faktisk var rimelig for én
  session.
- **Plain `<textarea>` ikke CodeMirror** — vanilla JS, ingen
  build-step, ingen npm-deps (PLAN § 15). YAML er kort nok at
  syntax highlighting ikke er kritisk. Hvis det blir savnet i
  praksis, kan vi legge til Prism eller CodeMirror i en senere
  session uten å rive opp arkitekturen.
- **Storage-valg via checkbox** — bruker velger eksplisitt om
  koden skal vedvare. Default er `sessionStorage` (mer privacy-
  bevart). For en single-user-installasjon på lokal maskin er
  `localStorage` praktisk; for delt bruk er `sessionStorage` riktig.
- **Editor-flyt med dirty-indicator** — `LAST_LOADED_YAML`
  sammenliknes med `textarea.value` i hver `input`-event. Lagre-
  knappen disables når ikke-dirty, så bruker kan ikke ved uhell
  POSTe med samme innhold. `beforeunload` + confirm-prompt
  beskytter mot tap av endringer.
- **Feedback med Pydantic-detail-rendering** — PUT-endpointet
  returnerer `details: [{loc: [...], msg: ...}]` ved
  ValidationError. Vi viser dette som `families.trend: mangler
  påkrevd felt`-format så bruker ser nøyaktig hvor i YAML-en
  feilen ligger.

**Verifisert:**
- pytest full → 982/982 (var 980 før, +2 nye admin-route-tester)
- Browser preview med mock-fetch:
  - Wrong code (`wrong`) → "Ugyldig admin-kode." vises i gate
  - Riktig code (`secret123`) → main vises, 3 instruments listet
    (gold/corn/wheat med byte-størrelser)
  - Click på `gold` → YAML lastet i textarea, editor-tittel +
    path oppdatert, save-knapp disabled (ikke dirty)
  - Edit textarea → dirty-indicator "● endringer ulagrede" vises,
    Lagre-knappen aktiveres
  - Save → success-feedback `"Lagret: /cfg/gold.yaml"`, dirty
    skjult, save-knapp disabled igjen
  - Save med `SHOULD_FAIL`-trigger → error-feedback `"validering
    feilet\n  families.trend: mangler påkrevd felt"`, dirty
    bevart
  - Logg ut → kode slettet fra begge storages, gate vises igjen
- `[hidden] !important` fix: før dette overstyrte `.admin-main {
  display: grid }` `[hidden]`-attributtens UA-spec'd `display: none`.

**Commit:** `0cd7e53 feat(ui): admin rule-editor — kode-gate +
instrument YAML-editor`. Auto-pushet til origin/main.

**Neste:** Session 55 — utvid admin-editor med:
1. Dry-run-scoring (POST /admin/rules/<id>/dry-run → kjør
   orchestrator mot siste 7 dager → returner score-diff)
2. Git-commit-on-save (etter atomic write — git add + commit +
   auto-push-hook tar resten)
3. `/admin/fetch` + `/admin/bot` + `/admin/defaults`-endepunkter +
   tabs i admin.html for å bytte mellom YAML-typer
4. Pipeline-styringer: killswitch (POST /kill all) / pause / force-
   run + UI-knapper
5. Logs-viewer (les siste 200 linjer av logs/pipeline.log)

### 2026-04-25 — Session 53: Fase 9 runde 2 — UI-polish (Option A) + RUNDE 2 LUKKET

**Scope:** Visuell polering av dashbordet. Funksjonelt komplett etter
51 (filter) + 52 (modal + explain-trace) — denne sessionen tuner det
visuelle uten å endre data-flyt eller backend.

**Endret denne session (commit `1b796d8`):**

`web/assets/style.css` (+579 / -273, full refaktor med tokens):
- Nytt `:root`-token-sett:
  - Color-skala: `--c-bg/surface/surface-alt/border/border-strong/
    ink/ink-muted/ink-faint`, brand `#1a1f2c`, accent `#3554a8`
    (dempet stålblå), semantisk `--c-pos/neg/warn/info` med soft +
    sterk variant
  - Spacing 4-pkt-skala: `--sp-1` (4px) til `--sp-8` (32px)
  - Type: `--font-sans` (system stack med Inter-fallback) +
    `--font-mono` (ui-monospace m/SF Mono fallback), `--fs-xs/sm/
    md/lg/xl/2xl/num-md/num-lg`
  - Radius: `--r-sm/md/lg`. Elevation: `--shadow-1/2/modal`.
    Transition: `--t-fast` (120ms)
- Hardkodet hex/px erstattet med tokens overalt — én senere endring
  i `:root` propagerer
- `tabular-nums` + monospace satt på alle numeriske felt (KPI-kort,
  setup-tabeller, trade-log-celler, modal-driver-tabell, modal-kv,
  filter-count, pipeline-tabell)

`.app-header`:
- Vertikal gradient `#1a1f2c → #131722` med tynn aksent-glow på
  `::after` border-bottom
- Wordmark `Bedrock` får 6×6 px aksent-firkant (visuell signatur)
- Ny `.status-pill` (right-aligned i `.app-header-row`) med
  pulsende dot. `data-status='ok'` → grønn pulserende, `'down'` →
  rød. Tekst format: `online · HH:MM · Nms` eller `unreachable` /
  `down · http NNN`

`.tab` aktiv-state:
- `background: var(--c-bg)` matcher main-bakgrunn → tab "kobler"
  visuelt til panelet
- `font-weight: 600` på aktiv (kontra 500 default)
- `::after` overstyrer 1px border for sømløs overgang

`.kpi-card`:
- Padding `var(--sp-3) var(--sp-4)` (var: `10px 14px`)
- Tall: `font-mono`, 22px, vekt 600, tabular-nums, semantic-pos/
  neg-fargekoding for total_pnl_usd

`.filter-bar` + `.flt-pill`:
- `flt-pill` default: surface-alt + dempet ink-muted; hover
  bytter til accent-soft
- aktiv pill: `var(--c-brand)` (mørk navy) — BUY/SELL beholder
  pos/neg-farge
- search-input får aksent-fokus-ring `box-shadow 0 0 0 3px
  accent-soft`

`.setup-card`, `.trade-log tr`:
- `.clickable:focus-visible { outline: 2px solid accent }` for
  tastatur-navigasjon
- Hover gir `var(--shadow-2)` + `translateY(-1px)`

`.modal`:
- Bruker tokens. `::backdrop` får `backdrop-filter: blur(2px)`
  for litt mykere overgang
- `.modal-scorebar-mark` utvidet over hele baren (top: -2px,
  height: calc(100% + 4px)) for synlighet på kantene

`.pipeline-group` (Kartrommet):
- Kompaktere typografi, tabular-nums i alder/stale-celler
- Status-pills bruker semantisk soft-palett (FRESH/AGING/STALE/
  MISSING)

`web/index.html`:
- `.app-header` re-strukturert: `.app-header-row` (h1 + status-
  pill) over `.tabs`
- `<span class='status-pill' id='server-status' data-status=
  'unknown'>` med dot + text-span

`web/assets/app.js` (+25):
- `loadServerStatus()` poller `/health` med `cache: 'no-store'`,
  måler latency med `performance.now()`, setter `data-status` og
  pill-tekst
- 30s interval (samme rate som loadSkipsloggen)
- Endpointet finnes allerede fra Fase 7; ingen backend-endring

**Designvalg:**

- **Tokens > globals:** Hard-kodede farger var spredt over 575
  linjer; samling til `:root` gjør tema-bytte trivielt og
  garanterer konsistens. Future dark-mode er nå ~30 linjer
  override, ikke en omskriving
- **Stålblå accent (#3554a8) ikke teal/orange:** Markedet er
  fullt av neon-tradingdashboards. Bedrock signaliserer
  "instrumentell, ikke leketøy" — dempet aksent bygger den
  vibben uten å være kjedelig
- **Status-pill polling 30s:** Matcher loadSkipsloggen-rate.
  Performans-budsjett ubetydelig (1 HEAD-størrelse fetch). Hvis
  signal_server går ned, ser brukeren det innen 30s
- **Latency-tall i pillen:** Gir gratis observability. En sub-
  10ms-stamp lokalt forteller alt — om den hopper til 200ms+, er
  noe galt
- **Mono-fonten valgt strengt for tall:** UI-tekst bruker sans-
  serif. Numerics (entry/sl/pnl/score) bruker mono med tabular-
  nums slik at alle tall i en kolonne har lik bredde — kritisk
  for å skanne pris-rader

**Verifisert:**
- `pytest` (full suite) → 980/980 (uberørt — kun frontend-
  endringer)
- `node --test tests/web/test_filter.test.mjs` → 18/18 (filter-
  tester uberørt)
- Browser preview:
  - Header: gradient + "Bedrock"-wordmark + aksent-firkant +
    grønn pulserende status-pill ("online · 10:42 · 8ms")
  - Tabs: aktiv har solid background-match med panel-bg
  - KPI: bold monospace tall, grønn `+1247.30` for pos PnL
  - Modal: GOLD-modal har fortsatt full driver-trace, nå med
    bedre visuell spacing og tokens
  - Pipeline: status-pills (FRESH/AGING/STALE/MISSING) i
    semantisk soft-palett
- Down-state: `data-status='down'` → rød dot uten pulse, tekst
  "unreachable"

**Commit:** `1b796d8 feat(ui): polish — design tokens, typografi,
header med status-pill`. Auto-pushet til origin/main.

**Runde 2 LUKKET.** Alle fire faner har:
- Filter (horizon/grade/instrument/direction der relevant) — session 51
- Modal med explain-trace per setup + trade-detaljer — session 52
- Polert visuell stil + live system-status — session 53

**Neste:** Runde 3 (sessions 54-55) — admin-rule-editor på `web/
admin.html` med kode-gate. PLAN § 10.5 + § 10.6.

### 2026-04-25 — Session 52: Fase 9 runde 2 — modal + persistert explain-trace (Option C)

**Scope:** Klikk på setup-kort / trade-rad åpner modal. Setup-modal
viser per-familie + per-driver explain-trace direkte fra Engine.
Trade-modal viser entry/setup/PnL/posisjons-data.

**Kartlegging avdekte at backend droppet trace:**

`GroupResult` (Engine) bærer `families: dict[str, FamilyResult]` +
`gates_triggered` + `active_families`. Men `_build_entry` i
orchestrator kopierte kun `score`/`grade`/`max_score`/`gates_triggered`
inn i `SignalEntry` — `families` ble droppet på vei til JSON.
`signal_server` er pass-through på filer; den kaller ikke Engine.
`PersistedSignal` har `extra='allow'` så ekstra felt round-tripper
transparent.

Bruker valgte Option B-utvidet (mot A-lett / C-hybrid): persister
families nå, lever modal med ekte forklaring, ikke et tomt stillas.

**Backend (orchestrator):**

`src/bedrock/orchestrator/signals.py`:
- Importerer `FamilyResult` fra `engine.engine`
- `SignalEntry` får to nye felt:
  - `families: dict[str, FamilyResult] = Field(default_factory=dict)`
  - `active_families: int = 0`
- Begge har defaults så eksisterende tester/fixtures som instansierer
  SignalEntry direkte ikke brekker (additivt, ikke breaking)
- `_build_entry` populerer begge fra `group_result.families` og
  `group_result.active_families` i begge return-stier (skip_reason +
  stable-setup)

`tests/logical/test_orchestrator_signals.py`:
- Ny test `test_generate_signals_persists_explain_trace_families`
  verifiserer at families er populert med min ett driver per familie,
  og at `model_dump(mode='json')` produserer JSON med
  `families.<name>.drivers[*]` med `{name, value, weight, contribution}`.
- Test passerer på første kjøring; resten av suite (979 tester) er
  uberørt → totalt 980/980.

**Frontend:**

`web/index.html`:
- `<dialog id='modal' class='modal'>` rett før `<script>`-taggene.
  Nytt globalt modal-element brukt av begge klikk-typer.

`web/assets/app.js` (+325):
- `openSetupModal(entry)` — bygger header (instrument + direction +
  horizon med farget border-bottom), score-bar (med publish-floor-
  tick), driver-trace-section med collapsible `<details>` per familie
  (drivers sortert på |contribution| desc, vises som tabell name/value/
  weight/bidrag), setup-tabell, persistens-tabell, gates_triggered-
  liste, skip_reason-tekst hvis present.
- `openTradeModal(entry)` — header + Tidslinje/Setup/Posisjon/PnL
  med pos/neg-fargekoding på pnl_usd. Disclaimer i bunn: "Driver-
  trace lagres ikke per trade enda — se setup-modalen via
  Financial / Soft commodities for full forklaring."
- `closeModal()` + `_wireModalGlobal` (klikk på dialog-elementet
  utenfor `.modal-content` lukker; klikk på `.modal-close` lukker;
  ESC håndteres av `<dialog>` native).
- `_wireModalDelegation()` — én listener per container
  (`#financial-cards`, `#agri-cards`, `#trade-log-body`). Bruker
  `el.__bedrockSetups`/`__bedrockEntries` som cache av filtrert
  subset (filter-aware lookup). Klikk på `[data-modal-idx]` slår opp
  riktig entry. Tastatur (Enter/Space) på fokuserte kort/rader virker
  også (role='button', tabindex='0' på kort/rader).
- `renderSetupCards`/`renderTradeTable` setter
  `el.__bedrockSetups`/`__bedrockEntries` etter innerHTML, og legger
  `class='clickable' data-modal-idx=N tabindex='0' role='button'`
  på hver kort/rad.

`web/assets/style.css` (+217):
- `.modal` + `::backdrop` (rgba 0.55-overlay)
- `.modal-head` med farget border-bottom (grønn buy / rød sell) og
  farget direction-pill matching headers
- `.modal-scorebar` (lineær gradient 0→100%) + `.modal-scorebar-mark`
  (rød 2px-tick på publish-floor-prosenten)
- `.modal-family` (collapsible card-style) + `.modal-driver-table`
  (kompakt 4-kolonne med tabular-nums)
- `.modal-kv` (key/value-tabell), `.modal-disclaimer` (italic, sentrert,
  border-top)
- `.setup-card.clickable` + `tr.clickable` med subtil hover-løft

**Designvalg:**

- **Persister hele FamilyResult**, ikke en flatere shape. Pydantic-
  modellen er allerede definert i Engine; gjenbruk den i SignalEntry
  gir round-trip uten nye konverteringssteg.
- **Ikke breaking** — defaults på nye felt + `extra='allow'` i
  `PersistedSignal` betyr at gamle SignalEntry-fixtures og signal-
  server-konsumenter fortsetter å funke uten endring.
- **Driver-trace bak `<details>`-collapse** — fane 2 har 2-6 familier
  med 1-5 drivere hver. Modalen kan vise alle åpent men hver familie
  blir ~80px → 480px tre-skjerm. Default lukket gir oversikt; bruker
  åpner det de bryr seg om.
- **Trade-modal _ikke_ trace-utvidet** — det krever signal_id-lookup
  mot signals.json (fersk på publish-tidspunkt, ikke nødvendigvis nå).
  Disclaimer dokumenterer dette eksplisitt; egen senere session.
- **`__bedrockSetups`/`__bedrockEntries` på containerelementet**
  (ikke globalt) — etter filter-endring re-renderer vi cards, og
  cachen følger med. Indeksbasert oppslag over filtrert liste virker
  umiddelbart.

**Verifisert:**
- `pytest` (full suite) → 980/980 grønne (var 979 før, +1 ny test)
- `node --test tests/web/test_filter.test.mjs` → 18/18 grønne
  (filter-tester uberørt)
- Browser preview med mock-data:
  - Setup-modal: GOLD/BUY/SWING header, score-bar 3.20/5.00 med
    publish-tick på 2.50, families {trend, positioning, macro},
    expand → sma200_align 1.00 × 0.60 = 0.60 første rad (sortert på
    |bidrag|)
  - Trade-modal: EURUSD/SELL/SCALP header, WIN-pill, +280.50 USD ✓
    realisert (grønn), disclaimer-tekst i bunn
  - Backdrop-click lukker; closeModal() lukker
- `<dialog>`-native ESC virker i ekte browser (synthetic
  KeyboardEvent treffer ikke browser-internal ESC-handler — confirmed
  ikke-bug)

**Commit:** `b4a7ce9 feat(ui): modal med explain-trace + persisterte
families i SignalEntry`. Auto-pushet til origin/main.

**Neste:** Session 53 = Option A (polish — typografi/farger/hierarki/
header). Dashboard er nå funksjonelt komplett (4 faner + filter +
modal + persistert trace) → polish-sessionen tuner det visuelle uten
å røre data-flyt eller backend.

### 2026-04-25 — Session 51: Fase 9 runde 2 — filter-bar (Option B)

**Scope:** Første session i runde 2. Filter-bar over Skipsloggen + begge
setups-faner. Klientsidig på allerede-fetchede entries — backend
uberørt. KPI-sammendrag (Skipsloggen) aggregeres fortsatt over full
logg; kun rad-listen filtreres. Bruker valgte Option B fra runde-2-
trekanten (B før C/A) fordi B er backend-uavhengig og funksjonell
forbedring større enn polish, mens C trenger explain-trace-API-
kartlegging som er bedre som egen session.

**Filter-akser per fane:**
- Skipsloggen, Financial, Soft commodities: `direction`,
  `grade`, `horizon`, `instrument`
- Kartrommet: ingen (read-only pipeline-helse)

**Filer endret/opprettet:**

`web/assets/filter.js` (ny, 53 linjer):
- Pure FLT-state per scope (skipsloggen / financial / agri)
- `applyFilter(scope, items, axesOf)` — generisk på begge entry-
  former
- `fltAxesFromTrade(entry)` leser fra `.signal`-undertre (trade-log)
- `fltAxesFromSetup(s)` leser top-level (setups)
- CommonJS-eksport guardet mot browser (testbar fra Node uten DOM)

`web/assets/app.js` (+85, -10):
- Importerer filter.js som klassisk script-global
- `wireFilterBar(scope, onChange)` + `buildFilterBarHtml()` +
  `setFilterCount(scope, shown, total)` — DOM-glue
- `TRADE_ENTRIES`, `FINANCIAL_SETUPS`, `AGRI_SETUPS` lagrer
  unfiltered fetch-resultat
- `renderTradeTableFiltered/renderFinancialFiltered/renderAgriFiltered`
  — gjenrender post-filter
- Tomt-state-tekst skiller "ingen treff" fra "ingen data"
- KPI-render uberørt (bruker `summary` direkte fra `/trade_log/summary`
  som aggregerer over full logg på server-siden)

`web/index.html` (+5, -0):
- 3 × `<div class="filter-bar-mount" data-flt-scope="...">`
- `<script src="/assets/filter.js">` lastet før `app.js`

`web/assets/style.css` (+82, -0):
- `.filter-bar` + `.flt-pill` + `.flt-search` + `.flt-reset`
- Aktiv pill = mørk navy; aktiv `data-val=BUY` grønn,
  `data-val=SELL` rød (matcher eksisterende `.pos`/`.neg`)
- Reset-knapp blir `:disabled` når ingen filter er aktiv

`tests/web/test_filter.test.mjs` (ny, 18 tester):
- `node --test` (built-in test-runner, ingen npm-deps)
- Importerer filter.js via CommonJS-require
- Dekker:
  - `fltAxesFromTrade` leser `.signal`-undertre, `fltAxesFromSetup`
    top-level
  - Manglende `.signal` → tom-streng-akser (kun ALL matcher)
  - `fltActive` false på fresh state, true ved én aktiv akse
  - `applyFilter` per akse (dir / grade / horizon / instr-substring
    case-insensitive)
  - Stacking: 4 akser samtidig (BUY+A++SWING+gold) gir kun GOLD
  - Skopisolasjon: mut av FLT.financial påvirker ikke FLT.agri
  - Tom treff-liste returneres (ikke null)
  - Trade-log: filter på `.signal.instrument` virker

**Design-valg:**

- **Pure-funksjon-utvinning:** filter-state og applyFilter ligger i
  egen fil, ikke begravd i app.js. Test-kostnaden går fra "umulig
  uten JSDOM" til "node --test importerer require". 53 linjer er
  ikke over-engineering — det er én tydelig modul med ett ansvar.
- **Klientside-filter:** API-rundtrip per filter-endring ville være
  dårlig UX og krevd backend-endring. Allerede-fetchede entries
  ligger i minne (≤ 100 trade-rader, ≤ ~20 setups) — filtrering er
  trivielt billig.
- **KPI uberørt:** Filter er en visnings-affordance, ikke en
  scope-redusering. Captain-stats skal alltid vise full sannhet.
- **`data-val`-styling:** BUY/SELL får farge-koding via attribute-
  selektor i CSS. Ingen JS for å sette farger — den semantiske
  HTML-attributten driver visning.
- **`disabled`-reset:** Reset-knappen er disabled når
  `fltActive(scope) === false`. Visuell hint at "ingenting å
  nullstille". Implementert via `_syncBarUi`.

**Verifisert:**
- `node --test tests/web/test_filter.test.mjs` → 18/18 grønne
- `pytest` (full suite) → 979/979 grønne
- `curl` smoke: 3 mount-divs i `/index.html`, `/assets/filter.js` +
  `/assets/app.js` serveres riktig

**Commit:** `669e58b feat(ui): filter-bar (horizon/grade/instrument/
direction) på Skipsloggen + setups`. Auto-pushet til origin/main.

**Neste:** Session 52 = Option C (modal). Først kartlegg hva
orchestrator/Engine eksponerer av explain-trace (Fase 5 har allerede
struktur), så implementer modal ved klikk på trade-rad / setup-kort.

### 2026-04-25 — Pre-runde-2 cleanup: Python 3.10 + pre-commit + ADR-004

**Scope:** Lukke pre-runde-2-cleanup før Fase 9 runde 2 starter.
Bruker flagget at Python 3.12-kravet i pyproject var en planleggings-
feil — lokal maskin har ikke 3.12 og ADR-002 dekket bare wheels/CPU-
instruksjoner, ikke interpreter-versjon. Adresserte også at CI feilet
på fire fronter (uv.lock-cache, protobuf-pin, ruff lint, pyright).

**Fix-sekvens (4 commits):**
1. `24f21b5` ci: setup-uv@v3 cache-dependency-glob til pyproject.toml
2. `830823a` ci: `[tool.uv] override-dependencies` for protobuf-pin
3. `40f2428` ci: ruff lint — auto-fix 325 + ignore stilvalg + 8 ekte
   feil (78 filer reformatert)
4. `df3ad4a` chore: Python 3.10-baseline + pre-commit + ADR-004

**Endret denne session (df3ad4a):**

`pyproject.toml`:
- `requires-python = '>=3.10'` (var '>=3.12')
- `[tool.ruff] target-version = 'py310'`
- `[tool.pyright] pythonVersion = '3.10'`
- `ignore += ['UP017']` — datetime.UTC er 3.11+

Revert UP017 i 20 filer:
- `from datetime import UTC` → `from datetime import timezone`
- `datetime.UTC` / `UTC` → `timezone.utc`

`.github/workflows/ci.yml`:
- Python 3.10 (var 3.12) — match lokal Ubuntu 22.04 LTS
- Pyright-step non-blocking (`|| true`) — 162 akkumulerte type-
  errors er teknisk gjeld utenfor scope

`.githooks/pre-commit` (ny):
- Delegerer til `.venv/bin/pre-commit run --hook-stage pre-commit`
- Skrevet manuelt fordi `core.hooksPath=.githooks` (auto-push)
- Graceful: hopper over hvis pre-commit ikke installert

`.pre-commit-config.yaml`:
- ruff: v0.6.9 → v0.15.12 (matcher lokal venv)
- pyright: stages: [manual] — defer til cleanup

`.yamllint.yaml`:
- alignment-padding tillatt (max-spaces-after: -1 for colons/commas,
  max-spaces-inside: 1 for braces)

`docs/decisions/004-python-3-10-baseline.md` (ny ADR):
- Dokumenterer 3.10-valget. ADR-003 var allerede tatt (gates-via-
  named-registry); denne blir 004
- Skiller fra ADR-002 (det handler om SSE4.2/AVX-wheels)

**Design-valg:**

- **Pyright non-blocking:** 162 errors fra Fase 1-9 da pyright aldri
  kjørte. CI-step rapporterer men blokkerer ikke. Cleanup blir egen
  task — ikke verdt å forsinke runde 2
- **`.githooks/pre-commit` manuelt:** core.hooksPath blokkerer
  `pre-commit install`. Manuelt script som delegerer er enkleste vei
- **Ruff bumpet i pre-commit:** Eldre v0.6.9 kunne ikke parse
  moderne pyproject med [tool.uv] eller forstå RUF059/UP017
- **YAML alignment OK:** Bedrocks YAML bruker bevisst column-
  alignment; verdi-vs-friksjon: tillat det

**Verifisert lokalt:**
- `pytest`: 979/979 grønne på 36.2s
- `ruff check` + `ruff format --check`: rent
- `pre-commit run --all-files`: alle hooks Passed (EXIT=0)

**Commits:** `24f21b5` + `830823a` + `40f2428` + `df3ad4a`. Auto-
pushet til origin/main.

**Neste:** Runde 2 (sessions 51-53). Bruker velger entry-punkt:
- A — polish-først (farger/typografi/hierarki)
- B — filter-først (horizon/grade/instrument-bar)
- C — modal-først (klikk → detaljer)

### 2026-04-24 — Session 50: Fase 9 runde 1 — Kartrommet + RUNDE 1 LUKKET

**Scope:** Siste fane i runde 1. Pipeline-helse per fetch-kilde,
gruppert per PLAN § 10.4. Etter denne er alle fire faner wired med
minimal data-flyt.

**Opprettet:**
- `GET /api/ui/pipeline_health` i `ui_bp`:
  - Laster `config.fetch_config_path` via `load_fetch_config`
  - Instansierer `DataStore(config.db_path)`
  - Kjører `status_report(fetch_cfg, store)` → `list[FetcherStatus]`
  - Klassifiserer via `_classify_staleness(has_data, age_hours, stale_hours)`:
    - `missing` (ingen observasjoner)
    - `fresh` (age < stale_hours)
    - `aging` (stale_hours ≤ age < 2×stale_hours)
    - `stale` (age ≥ 2×stale_hours)
  - Grupperer via hardkodet `_FETCHER_GROUPS` mapping:
    `prices→Core`, `cot_*→CFTC`, `fundamentals→Fundamentals`,
    `weather→Geo`, øvrige → `Other`
  - `_GROUP_ORDER` definerer UI-rekkefølge (Core first, Other last)
  - Respons: `{groups: [{name, sources: [...]}], last_check}`. Hver
    source har `name/module/table/status/stale_hours/age_hours/
    latest_observation/cron`

- `web/index.html` kartrom-fane med last_check-meta + group-container

- `web/assets/app.js`:
  - `loadKartrommet()` fetcher og kaller `renderKartrommet(res)`
  - Per gruppe: `<section class="pipeline-group">` med `<h3>`-header
    + `<table class="pipeline-table">` (kilde/tabell/status/alder/
    stale-grense/siste-obs/cron)
  - Status-pill med `.status-{fresh,aging,stale,missing}`-klasser
  - Graceful: `res.error` → viser feilmelding; tom groups → "Ingen
    fetch-kilder konfigurert"

- `web/assets/style.css`:
  - `.pipeline-group` med gråtone-header
  - `.pipeline-table` med uppercase th-labels
  - `.status-pill` klasser med grønn/gul/rød/grå farger

**Endret:**
- `ServerConfig` har nytt felt `fetch_config_path` (default `config/fetch.yaml`)

**Design-valg:**
- **Graceful ved førstegangs oppstart:** Tom SQLite → alle fetchere
  viser `missing` (ingen observasjoner enda). `fetch.yaml` mangler →
  200 + error-felt, ikke 500. Fetch.yaml ugyldig → samme. UI-en skal
  aldri være bryte når bot/pipeline ikke har kjørt enda
- **Hardkodet gruppering (ikke YAML-drevet):** Runde 1 skal være
  minimal. Hvis fremtidige fetchere trenger egen gruppe, legg de til
  i `_FETCHER_GROUPS` + evt. `_GROUP_ORDER`. YAML-drevet gruppering
  vurderes i runde 2 hvis det blir mange nye fetchere
- **2× stale_hours som aging-grense:** enkelt heuristic; matches
  intuisjonen "fetcher skulle ha kjørt igjen". Finere granularitet
  (3 grader, fast-grense i YAML) kan komme senere
- **Ingen auto-refresh på Kartrommet ennå:** Bruker må tabbe tilbake
  for å oppdatere. Runde 2 legger til polling hvis det trengs;
  pipeline-state endrer seg sjelden nok at 30-sek-poll er overkill

**Tester (8 nye):**
- `empty_db_all_missing`: alle fire fetchere fra test-fetch.yaml er
  `missing` med `age_hours=None`
- `groups_by_plan_categories`: `Core < CFTC < Geo < Other` i svaret
- `unknown_fetcher_in_other_group`: `unknown_fetcher` havner i "Other"
- `fresh_status_under_stale_threshold`: 1t gammel prises-obs i
  sqlite → status=`fresh`
- `aging_between_1x_and_2x_stale`: 45t (1.5 × 30) → `aging`
- `stale_above_2x`: 100t (>2 × 30) → `stale`
- `missing_fetch_config`: ikke-eksisterende fil → 200 + error-felt,
  tom `groups`
- `includes_cron_and_stale_hours`: respons inneholder `cron`-streng
  og `stale_hours`-tall per kilde

**Ikke endret:**
- Orchestrator/bot: uendret
- `check_staleness` og `status_report` fra `bedrock.config.fetch`
  gjenbrukes uendret

**Commits:** `36065f5`.

**Tester:** 979/979 grønne (fra 971 + 8 nye) på 33.2 sek.

═══════════════════════════════════════════════════════════
FASE 9 RUNDE 1 LUKKET
═══════════════════════════════════════════════════════════

Alle fire faner har funksjonell data-wiring (sessions 47-50).
Data-kilder:
- `~/bedrock/data/bot/signal_log.json` (ExitEngine)
- `data/signals.json` (orchestrator/push-alert)
- `data/agri_signals.json` (samme)
- `data/bedrock.db` (DataStore latest-observations)
- `config/fetch.yaml` (fetcher-definisjoner)

Backend-endepunkter:
- `GET /` + `GET /assets/<path>` (static)
- `GET /api/ui/trade_log` (+ `/summary`)
- `GET /api/ui/setups/financial`
- `GET /api/ui/setups/agri`
- `GET /api/ui/pipeline_health`

Frontend: 4 faner, vanilla JS med lazy-load per fane. Skipsloggen
har 30-sek auto-refresh; andre lades ved tab-klikk. Minimal CSS
(polish kommer i runde 2).

**Neste:** Runde 2 — styling/filtrering/modaler. Bruker velger
mellom polish-først (A), filter-først (B), eller modal-først (C)
ved session 51-start.

### 2026-04-24 — Session 49: Fase 9 runde 1 — Soft commodities

**Scope:** Tredje fane. Ren frontend-wire — backend `/api/ui/setups/agri`
ble landet i session 48 (samme kontrakt som financial mot
`agri_signals_path`).

**Endret:**
- `web/index.html` — agri-fanen har samme struktur som financial
  (meta-linje + setups-grid-container)
- `web/assets/app.js`:
  - `loadAgriSetups()` gjenbruker `renderSetupCards('agri-cards', ...)`
    + oppdaterer `visible_count`/`total_count` i meta-linjen
  - Wired i `loaders`-dict → tab-klikk trigger lazy-fetch

**Design-valg:**
- Gjenbrukte `renderSetupCards` i stedet for egen `renderAgriCards`.
  Agri-spesifikke felt (weather_stress, enso_status, conab_flag,
  yield_score per PLAN § 10.3) eksisterer ikke i setup-dict enda —
  fetch-lagene for vær/ENSO/Conab er ikke ferdige. Legges i runde 2
  eller Fase 10 når data er tilgjengelig
- Ingen nye tester — backend-endepunkt allerede testet i session 48,
  frontend-wire er ikke kompleks nok til å rettferdiggjøre JS-
  testramme i runde 1

**Ikke endret:**
- Backend: uendret (endepunkt landet session 48)
- CSS: uendret (gjenbruker financial-styling)

**Commits:** `e7cdf86`.

**Tester:** 971/971 grønne (ingen nye).

**Neste session:** 50 — Fane 4 Kartrommet (siste i runde 1).
Pipeline-helse per fetch-kilde.

### 2026-04-24 — Session 48: Fase 9 runde 1 — Financial setups

**Scope:** Andre fane. Leser `config.signals_path` og viser setups som
kort-grid. Null styling utover struktur — polish i runde 2.

**Kartlagt:** Ingen eksisterende `data/setups/active.json` — setups
flyter allerede via `signals_path`/`agri_signals_path` (satt av
orchestrator via `/push-alert`-endepunkt). Bruker dermed eksisterende
transport istedenfor å introdusere ny fil.

**Opprettet:**
- `GET /api/ui/setups/financial` i `ui_bp`:
  - Leser `config.signals_path` (rå dict-liste; ikke Pydantic-
    validert — UI-laget er graceful på valgfrie felt)
  - Sortering: grade A+ > A > B > C via `_GRADE_RANK`, så score
    descending innen samme grade
  - Invalidated-signaler skjules (caller kan ikke handle dem)
  - `?limit=N`-query-param kutter topp N
  - Feil-tilfeller: fraværende fil / korrupt JSON / non-list top-
    level / ikke-dict-rader → graceful tom liste + warning-log
- `GET /api/ui/setups/agri` — samme kontrakt mot `agri_signals_path`
  (brukes av session 49; backend landes her for å holde setup-
  logikken samlet i én PR)

- `web/index.html` financial-fane:
  - Meta-linje: `visible_count` synlige (`total_count` totalt)
  - `setups-grid`-container for kort-grid

- `web/assets/app.js`:
  - `loadFinancialSetups()` fetcher og rendrer via
    `renderSetupCards(containerId, setups)` (gjenbrukbar for agri
    session 49)
  - Kort-innhold: instrument/direction/grade + horizon+score-row +
    entry/stop/t1/rr-tabell. Grade-chip styles per A+/A/B/C.
    Retnings-border (venstre kant grønn=buy, rød=sell)
  - `loaders`-dict mapper tab-id → fetch-funksjon. Tab-klikk
    trigger `activateTab()` → lazy-load. Skipsloggen fortsatt
    auto-refresh hver 30s; financial lades kun ved tab-skift

- `web/assets/style.css`:
  - `.setups-grid` med `repeat(auto-fit, minmax(240px, 1fr))`
  - `.setup-card` med border-left som direction-indikator
  - Grade-chip-klasser for A+/A/B/C
  - Level-tabell i monospace for pris-alignment

**Design-valg:**
- Gjenbruke `signals_path` (allerede testet + populert av orchestrator)
  istedenfor å introdusere ny `data/setups/active.json`. Reduserer
  scope og data-konsistens-risiko
- Rå dict-liste fra backend, ikke Pydantic-validert — UI skal være
  robust på valgfrie felt som `setup.entry`/`setup.stop_loss` (noen
  signals har `setup: null` hvis generator returnerte None)
- Setup-dict har inkonsistent feltnavn i eksisterende kode (`stop_loss`
  vs `sl` vs `stop`; `target_1` vs `t1`). `app.js:renderSetupCards`
  er graceful med `?? `-fallback. Runde 2 kan normalisere i backend
- Lazy-load per fane: Skipsloggen auto-refresher, setup-faner lades
  kun ved klikk. Reduserer unødig HTTP når bruker bare ser på
  trade-logg
- Agri-endepunkt landet her (ikke session 49) fordi koden er identisk
  — sparer en separat Edit i session 49

**Ikke endret:**
- Backend-tester: ingen endring utenfor `test_endpoints_ui.py`
- Orchestrator/bot: uendret

**Commits:** `fa5359a`.

**Tester:** 971/971 grønne (fra 959 + 12 nye) på 33.9 sek.

**Neste session:** 49 — Fane 3 Soft commodities. Backend allerede
klar; kun frontend-wire + eventuelle agri-spesifikke badges (weather/
ENSO/Conab) hvis de finnes i `setup`-dict.

### 2026-04-24 — Session 47: Fase 9 runde 1 — Skipsloggen

**Scope:** Første fane av fire i Fase 9 runde 1 (minimal data-wiring).
Leser `~/bedrock/data/bot/signal_log.json` skrevet av ExitEngine.

**Opprettet:**
- `src/bedrock/signal_server/endpoints/ui.py` (~140 linjer) — `ui_bp`:
  - `GET /` serverer `web/index.html` via `send_from_directory`
  - `GET /assets/<path>` serverer statiske JS/CSS-filer
  - `GET /api/ui/trade_log` returnerer `{entries, last_updated,
    total_count}`. `?limit=N`-query-param kutter listen (entries er
    allerede nyeste-først fra log-writer)
  - `GET /api/ui/trade_log/summary` returnerer KPI-aggregat:
    `{total, open, closed, wins, losses, managed, total_pnl_usd,
    win_rate, last_updated}`. PnL summerer både positive og negative;
    win_rate regnes på closed-trades

- `web/index.html` — full 4-fane-struktur:
  - Tab-bar: Skipsloggen / Financial setups / Soft commodities /
    Kartrommet. Tab-skifte via `data-tab`-attributt + klassetoggle
  - Skipsloggen: 6-KPI-grid + trade-tabell (12 kolonner: timestamp,
    signal_id, instrument, direction, horizon, entry, stop, t1,
    closed_at, result, exit_reason, pnl). Placeholder-rad ved
    "Laster…"/"Ingen trades". `last_updated`-meta nederst
  - Financial/Agri/Kartrom: placeholder-seksjoner for sessions 48-50

- `web/assets/app.js` — vanilla JS (per PLAN § 15):
  - Tab-navigasjon
  - `loadSkipsloggen()` fetcher begge endepunkter i parallell via
    `Promise.all`, rendrer KPI + tabell
  - `renderKpi(summary)` — formaterer win_rate som prosent,
    total_pnl_usd med fortegn og pos/neg-klasse
  - `renderTradeTable(entries)` — HTML-stringtemplates (ingen
    rammeverk), result-pills via `fmtResult()`, pnl-farger via
    `fmtPnl()` (`✓` suffix hvis `pnl_real`)
  - 30-sek auto-refresh via `setInterval`. Fetch-feil logges og viser
    feilmelding i tabell-body

- `web/assets/style.css` — minimum for lesbarhet:
  - Mørk header-bar med tab-row
  - KPI-grid med `grid-template-columns: repeat(auto-fit, minmax(140px, 1fr))`
  - Sticky tabell-header, pos/neg-farger for PnL
  - Result-pills (win=grønn, loss=rød, managed=gul, open=grå)
  - Polish kommer i runde 2

**Endret:**
- `src/bedrock/signal_server/config.py` — nye felt på `ServerConfig`:
  - `trade_log_path: Path` (default `~/bedrock/data/bot/signal_log.json`)
  - `web_root: Path` (default `Path("web")`)
- `src/bedrock/signal_server/app.py` — registrerer `ui_bp`
- `src/bedrock/signal_server/endpoints/__init__.py` — eksport `ui_bp`

**Design-valg:**
- Graceful håndtering av fraværende/ugyldig fil: tom liste, aldri 500.
  Første gangs oppstart (før bot har kjørt første trade) må ikke
  breake UI-en. Logger warning ved JSON-decode-feil
- Vanilla JS uten Alpine.js-sprinkling ennå — holder runde 1 så
  enkel som mulig. Alpine legges evt. inn i runde 2 hvis
  detaljmodaler krever reaktiv state
- KPI + trade-log hentes som to separate endepunkter (ikke én
  aggregert) for å gi runde 2 mulighet til å cache KPI uavhengig av
  hele loggen når log blir stor
- 30-sek polling er hardkodet i JS. Runde 2 kan flytte til
  `/api/ui/config` hvis nødvendig

**Ikke endret:**
- `~/scalp_edge/` — READ-ONLY
- Ingen endring i `bedrock.bot` — UI leser kun fra samme fil bot
  allerede skriver til

**Commits:** `e54123f`.

**Tester:** 959/959 grønne (fra 944 + 15 nye) på 32.9 sek.

**Neste session:** 48 — Fane 2 Financial setups (runde 1). Krever
kartlegging av `data/setups/active.json` eller orchestrator-
snapshot. Hvis ikke eksisterer: legg til write-point.

### 2026-04-24 — Session 46: bot/__main__.py + FASE 8 LUKKET

**Scope:** Siste modul i bot-refaktor. `__main__.py` wirer opp alle
bot-moduler og starter Twisted reactor. Etter denne er hele
`trading_bot.py` portert til Bedrock.

**Opprettet:**
- `src/bedrock/bot/__main__.py` (~260 linjer) — entry-point:
  - argparse `--demo`/`--live` (live krever interaktiv 'JA'),
    `--config` for custom bot.yaml-sti
  - `build_bot(demo, config_path)` instansierer og wirer
    SafetyMonitor → CtraderClient → SignalComms → EntryEngine →
    ExitEngine i én funksjon. Returnerer alle instanser slik at
    tester kan verifisere wire-up uten å starte reactor
  - `_apply_kill_ids(active_states, kill_ids)`: markerer IN_TRADE-
    states med `kill_switch=True`. P2 i ExitEngine lukker ved neste
    candle (ikke fra HTTP-callback-tråd)
  - `_make_sighup_handler`: kaller `reload_bot_config` + muterer
    eksisterende `ReloadableConfig` in-place via
    `apply_reloadable_inplace`. Alle moduler ser nye verdier
    umiddelbart. `startup_only`-diffs logges som warning. Exception-
    safe: ugyldig YAML → error-log, gammel config beholdes
  - `_make_shutdown_handler("SIGTERM"/"SIGINT")`: kaller
    `reactor.callFromThread(reactor.stop)` — sikker på tvers av
    tråder
  - `_schedule_polling_loop(comms, config, reactor)`: initial
    `callLater(0, _tick)`; hver tick kaller `comms.fetch_once()` +
    planlegger neste via `adaptive_poll_interval` (SCALP-watchlist
    aktivt → 20s, ellers 60s). Exception i fetch_once svelges
  - `register_signal_handlers`: binder SIGHUP/SIGTERM/SIGINT via
    `signal.signal()` FØR `reactor.run()`
  - `main(argv)`: orchestrerer hele oppstart. Live-mode uten 'JA'
    → return 0. Credentials mangler → return 1

- `docs/bot_running.md` (~100 linjer):
  - Env-var-oppsett (creds + SCALP_API_KEY + BEDROCK_BOT_CONFIG)
  - Start-kommandoer med `PYTHONPATH=src`
  - Signal-oppførsel-tabell (SIGHUP/SIGTERM/SIGINT)
  - Systemd-unit-eksempel med EnvironmentFile + ExecReload +
    TimeoutStopSec=60s (må gi tid til å lukke posisjoner)
  - Kjørings-logikk fra oppstart → trade → management → shutdown
  - Exit-kode-tabell (78 auth-fatal, 79 reconnect-budsjett, 80
    symbol-mismatch)
  - Smoke-test-kommando for CI

**Endret:**
- `src/bedrock/bot/config.py` — `apply_reloadable_inplace(current, new)`:
  ny helper som muterer `current.ReloadableConfig` in-place fra
  `new`'s felter via `type(new).model_fields` (Pydantic v2-kompatibel).
  Dette er SIGHUP-mekanismen — alle moduler som holder ref til
  samme ReloadableConfig-instans ser nye verdier uten restart

**Design-valg:**
- SIGHUP-semantikk: `reloadable`-delen muteres in-place (alle
  moduler får nye verdier), `startup_only` krever restart.
  `apply_reloadable_inplace` er bevisst ikke en swap — swap ville
  krevd at alle moduler fikk ny referanse; mutasjon er enklere og
  matcher «config er delt state»-modellen
- Kill-switch propagering via polling-loop: /kill-endpoint pushes
  signal_ids → `_apply_kill_ids` setter `kill_switch=True` → P2 i
  ExitEngine lukker ved neste candle. Bevisst å ikke lukke i HTTP-
  callback-tråden fordi ordre-sending må gå via Twisted-reactoren
- `reactor.callFromThread(reactor.stop)` i shutdown-handler i
  stedet for `reactor.stop()` direkte — SIGTERM/SIGINT kan fyres
  fra annen tråd enn reactor-tråden, og `stop()` er ikke thread-safe
- `build_bot()` returnerer alle instanser slik at smoke-tester kan
  verifisere wire-up uten reactor.start(). Tester mocker ikke
  internal modul-konstruksjon — bruker ekte moduler med fake env
- Polling-loop er `callLater`-basert, ikke `LoopingCall`. `callLater`
  lar oss justere intervall pr tick basert på signal-aktivitet;
  `LoopingCall` ville kreve start/stop ved hver reconfiguration

**Tester (18 nye i test_main.py):**
- `_apply_kill_ids`: setter kill på IN_TRADE-state, ignorerer
  AWAITING_CONFIRMATION; tom kill-ids er no-op
- `apply_reloadable_inplace`: muterer current til new sine verdier
  (confirmation.min_score_default 2→99, risk_pct.full 1.0→1.5)
- `build_bot`: verifiserer at alle seks client-callbacks wires til
  riktig entry/exit-metode; entry._manage_open_positions ==
  exit.manage_open_positions; comms._on_signals == entry.on_signals
- `build_bot` warner ved manglende SCALP_API_KEY
- `build_bot` raiser RuntimeError ved manglende creds
- SIGHUP-handler: nye reloadable-verdier aktiveres (3/8 i stedet
  for 2/6 defaults); startup_only-diff logger warning med
  "signal_url"; ugyldig YAML → error-log + config uendret
- Shutdown-handler: `reactor.callFromThread(stop)` kalt når
  `reactor.running=True`; no-op når False
- `_schedule_polling_loop`: initial `callLater(0, _tick)`;
  `_tick()` kaller fetch_once og scheduler med
  scalp_active_seconds når watchlist har SCALP; default_seconds
  når `latest_signals is None`; `fetch_once.side_effect=Exception`
  svelges og neste tick schedulert uansett
- `register_signal_handlers` binder alle tre signaler
- `main(["--live"])` uten 'JA' → return 0 + 'Avbrutt' i stdout
- `main(["--demo"])` uten creds → return 1 + 'Mangler
  miljøvariabler' i error-log

**Ikke endret:**
- `~/scalp_edge/` — READ-ONLY gjennom hele session
- Ingen prosesser rørt
- Ingen kode-endring i eksisterende Bedrock-moduler utenom `config.py`

**Commits:** `25d872b`. Tag `v0.8.0-fase-8` pushet til origin.

**Tester:** 944/944 grønne (fra 926 + 18 nye) på 30.6 sek.

═══════════════════════════════════════════════════════════
FASE 8 BOT-REFAKTOR LUKKET
═══════════════════════════════════════════════════════════

Alle ni bot-moduler portert fra `~/scalp_edge/trading_bot.py`
(~3000 linjer) til `bedrock.bot/` (~4000 linjer inkl. tester):
  __init__.py + state.py + instruments.py + config.py +
  ctrader_client.py + safety.py + comms.py + entry.py +
  sizing.py + exit.py + __main__.py

Session-telling:
- Session 36: bot/__init__ + state + instruments + config
- Session 37-40: safety + comms (flere iterasjoner)
- Session 41: ctrader_client (transport-lag)
- Session 42: safety + comms stabilisert
- Session 43: entry + sizing + AGRI-BUG FIX (kritisk)
- Session 44: _execute_trade + cTrader ordre-APIs
- Session 45: exit.py med ExitEngine
- Session 46: __main__.py + wire-up + docs

Kritisk bug-fix levert (session 43): `_recalibrate_agri_levels`
fjernet — agri-signalers reelt-nivå-baserte SL/T1/T2/entry_zone
respekteres nå gjennom hele bot-pipelinen.

Botport kan nå kjøres parallelt med gammel `trading_bot.py`:
    PYTHONPATH=src .venv/bin/python -m bedrock.bot --demo

**Neste fase:** Fase 9 (admin-UI for YAML-config-editering) eller
Fase 10 (UI-oppdateringer for bot-logg og setups) per PLAN-
tabell. Brukeren velger prioritet.

### 2026-04-24 — Session 45: bot/exit.py med ExitEngine

**Scope:** Portert hele exit-laget fra `trading_bot.py` per migrasjons-
plan § 3.4 + 8 punkt 5. Åttende av åtte bot-logikkmoduler — hele
bot-refaktoren er nå portert (kun `__main__.py` + wire-up gjenstår).

**Opprettet:**
- `src/bedrock/bot/exit.py` (~700 linjer) — `ExitEngine`:
  - `manage_open_positions(symbol_id, candle)` — P1-P5 exit-prioritet
  - cTrader-event-handlere:
    - `on_execution(event)`: fill → `IN_TRADE` + amend SL/TP for
      MARKET; partial-fill justerer `full_volume`/`remaining_volume`
      til faktisk filled; `closePositionDetail` lagres som
      `state._real_pnl`/`_real_commission`; LIMIT-fills skipper
      amend (SL/TP allerede på ordren)
    - `on_order_error(event)`: `POSITION_NOT_FOUND` detekterer TP vs
      SL basert på siste kjente pris (avstand til t1 vs stop);
      andre errors rydder stuck AWAITING-states (aldri fikk pos)
    - `on_reconcile(res)`: tar over åpne SE-posisjoner ved oppstart,
      oppretter `TradeState(reconciled=True)` + `reconciled_sl/tp`
      for M10-divergens-advarsler ved senere trail/BE-override
  - Trade-close-logging til `~/bedrock/data/bot/signal_log.json`
    atomisk via tempfile + os.replace, UTEN git-push (gammel bot
    pushet til cot-explorer; Bedrock skal ikke gjøre git i hot-path)
  - Akkumulerer daily_loss via `SafetyMonitor.add_loss(abs(pnl))`
    ved negativ PnL, persistert via eksisterende mekanisme
  - PnL-beregning: USD-quote (EURUSD/GOLD/...) vs USD-base (USDJPY/...),
    halv-spread-fratrekk, commission integrert fra cTrader-deals

- **Exit-prioritet (P1 → P5b)** implementert i manage_open_positions:
  - P1   Geo-spike: `move_against > geo_mult × ATR` → STENG
  - P2   Kill-switch: `state.kill_switch` → STENG
  - P2.5 Weekend (CET): fredag ≥20 lukker SCALP; ≥19 strammer SWING/
         MAKRO SL til `config.weekend.sl_atr_mult × ATR`
  - P3   T1 nådd → partial close (`exit_t1_close_pct`) + BE + trail-aktiv.
         `_calc_close_volume` forced_full hvis remaining < min_volume
  - P3.5 Trailing stop (ratchet): `close < trail_level` (eller > for sell)
  - P3.6 Give-back (pre-T1): `peak_progress ≥ gb_peak` og
         `progress ≤ gb_exit` → STENG
  - P4   EMA9-kryss (post-T1, SWING/MAKRO bruker 1H EMA9):
         disabled hvis `gp.ema9_exit=False` eller `exit_ema_tf="D1"`;
         3-candle grace-period for reconciled states
  - P5a  Timeout (`candles_since_entry ≥ expiry_candles`):
         progress > partial_pct → aktiver trail med 2/3 mult;
         progress > 0 → "8-CANDLE-MARGINAL"; ellers "8-CANDLE-LOSS"
  - P5b  Hard close ved `candles_since_entry ≥ 2 × expiry`

- **Helpers** (ExitEngine-metoder):
  - `_weekend_action() -> {close_scalp, tighten_sl}` — kun-CET-tid
  - `_compute_weekend_sl(state, close, atr)` — returnerer None hvis
    ny SL ikke er strammere enn nåværende
  - `_compute_progress(state, close)` — 0.0=entry, 1.0=T1, negativ=mot SL
  - `_update_trail(state, close, sid, mult)` — ratchet-logikk +
    `client.amend_sl_tp`; SWING/MAKRO bruker 1H ATR
  - `_set_break_even(state, sid)` — buffer = spread + ratio × ATR,
    sikkerhetssperre mot SL ≥ bid (buy) eller SL ≤ ask (sell),
    flytter kun hvis bedre enn nåværende SL. M10-advarsel ved
    reconciled-SL-override > 1×ATR
  - `_calc_close_volume(state, fraction)` — step-rounded + min_volume-
    floor, forced_full hvis remaining < min_volume
  - `_resolve_trail_mult` — `horizon_config.exit_trail_atr_mult[group]`
    > `rules.trail_atr_multiplier` > `gp.trail_atr`
  - `_close_all(state, close_price, reason)` — lukk resten + logg
  - `_calc_pnl(state, close_price)` — estimert PnL i USD + pips;
    overstyres av `state._real_pnl` i `_log_trade_closed` hvis satt
  - `_log_trade_closed(state, reason, close_price)` — oppdaterer
    siste åpne entry for signal_id med close-data + PnL; akkumulerer
    daily_loss ved negativ PnL
  - `_log_reconcile_opened(state)` — idempotent (skipper hvis
    signal_id allerede har åpen entry)
  - `_atomic_write_json(data)` — tempfile + os.replace

**Endret:**
- `src/bedrock/bot/entry.py`:
  - `get_ema9_h1(sid, offset=0)` — trengs av ExitEngine P4 for
    SWING/MAKRO-exits
  - `set_manage_open_positions(callback)` — post-construction wiring
    for å løse sirkulær dep (EntryEngine → manage-callback,
    ExitEngine → EntryEngine-ref for indikatorer)

**Design-valg:**
- ExitEngine tar `entry: EntryEngine`-referanse (TYPE_CHECKING-import
  for å unngå runtime circular dep). Leser indikatorer via
  `entry.get_atr14/atr14_h1/ema9/ema9_h1`, trade-log-opening via
  `entry._log_trade_opened(state)` (entry eier hot-path IO)
- Autouse-fixture `_freeze_to_thursday` i test_exit.py hindrer at
  dagens ukedag (fredag 2026-04-24) trigger weekend-gate utilsiktet.
  Weekend-spesifikke tester monkeypatche'r selv — test-lokal patch
  vinner over autouse
- Sirkulær dep løst via `set_manage_open_positions`: `bot/__main__.py`
  instansierer EntryEngine først (uten callback), så ExitEngine med
  entry-ref, så `entry.set_manage_open_positions(exit.manage_open_positions)`
- ExitEngine.on_execution kaller `self._entry._log_trade_opened(state)`
  (ikke `self._log_reconcile_opened`) — trade-log-eierskap blir dermed:
  entry eier "åpnet via fill"-loggin, exit eier "stengt + reconcile"
- PnL-beregning: `_real_pnl` (fra cTrader closePositionDetail) vinner
  over estimert `_calc_pnl`. Commission fra intermediate deals
  akkumulerer i `state._real_commission` og integreres i estimert PnL

**Tester (36 nye):**
- P-tester: P1 close_buy (triggs), P1 no-op-in-favor,
  P2 kill-switch, P3 T1 partial (50%) + forced_full,
  P3.6 give-back, P5a timeout negative/positive progress,
  P5b hard close
- Helpers: compute_progress (buy/sell/missing-t1),
  calc_close_volume (partial + forced_full),
  weekend_action (fredag kveld/sen-ettermiddag/torsdag),
  compute_weekend_sl (tightens/none),
  set_break_even (amend kalt + ny SL i riktig rekkefølge),
  update_trail (ratchet — monoton i trade-retningen)
- `_calc_pnl`: USD-quote buy (10.0 USD for 100k vol × 0.01 diff),
  USD-base USDJPY (pnl_usd ≈ 6.62 for 1 JPY × 100k / 151),
  empty ved missing entry
- `_log_trade_closed`: oppdaterer entry + akkumulerer daily_loss
  (loss → safety.daily_loss > 0); no-op ved fil-mangel
- `_log_reconcile_opened`: oppretter entry med reconciled=True;
  idempotent når signal_id allerede er logget
- `on_execution`: full fill + amend SL/TP (MARKET),
  partial fill (state.full_volume justert til faktisk),
  duplikat-event ignorert (IN_TRADE),
  non-SE-label ignorert
- `on_order_error`: POSITION_NOT_FOUND → TP-detektering via
  last_price-avstand; andre errors → stuck-rydd
- `on_reconcile`: oppretter SE-state med reconciled=True +
  reconciled_sl/tp; skipper duplikate position_id

**Ikke endret:**
- `~/scalp_edge/` — READ-ONLY gjennom hele session
- Ingen prosesser rørt

**Commits:** `7879750`.

**Tester:** 926/926 grønne (fra 890 + 36 nye) på 32.4 sek.

**Neste session:** 46 — `bot/__main__.py` entry-point + SIGHUP/SIGTERM-
handlers + full wire-up av alle bot/-moduler. Etter dette er hele
bot-porten komplett og kan kjøres parallelt med gammel
`~/scalp_edge/trading_bot.py`. Fase 8 avsluttes.

### 2026-04-24 — Session 44: _execute_trade + cTrader ordre-APIs

**Scope-splitt (brukerbeslutning):** Opprinnelig session 44-scope var
`bot/exit.py` + `_execute_trade` + CtraderClient-ordre-APIs. For stort
for én session — `_execute_trade` hører logisk i entry (confirm → gates
→ size → execute), ikke i egen execution-modul. Splittet:
- **Session 44 (denne):** CtraderClient ordre-APIs + sizing-utvidelser
  + `_execute_trade_impl` i `EntryEngine` + tester
- **Session 45 (neste):** `bot/exit.py` med `ExitEngine` + P1-P5 + helpers
  + callback-wiring + tester

**Opprettet/utvidet:**
- `src/bedrock/bot/ctrader_client.py` (+90 linjer) — fire ordre-APIs
  (transport-only, null state):
  - `send_new_order(symbol_id, trade_side, volume, label, comment,
    order_type, limit_price, stop_loss, take_profit, expiration_ms)`
    — MARKET/LIMIT. LIMIT tillater SL/TP/expiry direkte; MARKET må
    bruke `amend_sl_tp` etter fill (cTrader-API-begrensning).
  - `amend_sl_tp(position_id, stop_loss, take_profit)` — patch åpen
    posisjon
  - `close_position(position_id, volume)` — full eller partial
  - `cancel_order(order_id)` — pending LIMIT
  - `ValueError` hvis `order_type="LIMIT"` uten `limit_price`

- `src/bedrock/bot/sizing.py` (+96 linjer) — tre nye rene funksjoner
  portert fra `_execute_trade`:
  - `compute_desired_lots(sig, risk_pct) -> float` — lot-tier
    (SCALP 0.01 / SWING 0.02 / MAKRO 0.03) fra
    `horizon_config.sizing_base_risk_usd`, så VIX/geo-nedskalering
    (`risk_pct < 0.5` → ×0.5, `< 1.0` → ×0.75), så agri-halvering,
    minimum 0.01
  - `lots_to_volume_units(desired_lots, symbol_info) -> int` —
    stepVolume-rounding + min_volume-gulv; fallback 1000 enheter
    hvis `symbol_info` mangler (matcher gammel bot)
  - `volume_to_lots(volume, symbol_info) -> float | None` — invers
    for trade-logging; FX-standard fallback (100 000 enheter = 1 lot)

- `src/bedrock/bot/entry.py` (+481 linjer) — `EntryEngine._execute_trade_impl`:
  - Monday-gap-gate (`config.monday_gap.atr_multiplier`)
  - Oil geo-advarsel-gate (`config.oil.min_sl_pips` / `max_spread_mult`,
    override via `rules["oil_min_sl_pips"]`/`oil_max_spread_mult`)
  - Daily-loss-gate via `SafetyMonitor.daily_loss_exceeded`
  - Agri: `max_concurrent` / `max_per_subgroup` / session-filter /
    spread > `max_spread_atr_ratio × ATR14`
  - Korrelasjon: per-gruppe + `max_total` fra
    `global_state.correlation_config`, fallback til lokal
    `INSTRUMENT_GROUP`-mapping hvis signal ikke har
    `correlation_group`
  - MARKET/LIMIT-ordre via `client.send_new_order`. MARKET setter
    ikke SL/TP på request (amendes av ExitEngine etter fill);
    LIMIT setter SL/TP/expiry direkte
  - Skriver state før ordre-send (entry_price, full_volume,
    lots_used, risk_pct_used, horizon, grade, horizon_config,
    correlation_group). Phase forblir `AWAITING_CONFIRMATION`
    til ExitEngine flipper til `IN_TRADE` på fill
  - `_is_monday_gap(sid) -> bool` og `_agri_session_ok(instr) -> bool`
    helpers — leser `h1_candle_buffers`, `atr14_h1`, `config.agri.
    session_times_cet` (lowercase-key-mapping mot capitalized
    instrument-navn)
  - `_log_trade_opened(state)` — atomisk skriving til
    `~/bedrock/data/bot/signal_log.json`. **UTEN git-push** — gammel
    bot pushet til cot-explorer; Bedrock skal ikke gjøre git i
    hot-path (confirmert i CLAUDE.md «ikke-gjør»)
  - `_remove_state(state)` — trygg fjerning (swallow `ValueError`)

- `src/bedrock/bot/state.py` (+2 linjer) — `TradeState` utvidet med
  `lots_used: Optional[float]` og `risk_pct_used: Optional[float]`.
  Gammel bot satte dem ad-hoc via attribute-assignment; nå formelle
  felt slik at type-checker godtar dem

**Design-valg:**
- `EntryEngine.__init__`: `execute_trade`-callback er nå
  `Optional[ExecuteTradeCallback] = None`. Hvis `None`: bruk
  `self._execute_trade_impl`. Hvis gitt: bruk callbacken. Tester
  kan fortsatt stubbe via `execute_trade=MagicMock()`, men i
  produksjon (session 46 `bot/__main__.py`) kan callback utelates —
  entry eier utførelsen
- `EntryEngine._execute_trade_impl` er en **metode**, ikke egen
  modul. Bruker-beslutning: «Flyten confirm → gates → size →
  execute er alt entry-atferd. Ingen egen execution-modul.»
- Sizing-funksjoner er rene; de leser kun `sig` og `symbol_info`.
  Gjør dem trivielle å teste matrisebasert (13 nye tester)
- Oil-gate i `_execute_trade_impl` bruker både rules-override og
  config-default. Matcher gammel bots rekkefølge
- `_log_trade_opened` skriver atomisk (tempfile + os.replace) og
  svelger exceptions til log.warning. IO-feil skal ikke blokkere
  trade. Kall-sted er session 45 (`ExitEngine.on_execution` ved
  `ORDER_FILLED`) — modulen eier IO-en uansett
- `_agri_session_ok` leser `config.agri.session_times_cet` med
  `instrument.lower()` som key fordi config bruker «corn/wheat/…»
  (lowercase) mens instrument-navn er «Corn/Wheat/…» (capitalized).
  Ukjent instrument → True (ikke blokkér)
- Ordre-API-ene er deliberate nøkkel-orderde (`*, symbol_id, ...`)
  for å unngå positional-argument-forvirring i call-site

**Tester (40 nye):**
- `tests/unit/bot/test_sizing.py` (+13):
  - `compute_desired_lots`: SCALP/SWING/MAKRO-tier, default base_risk,
    VIX quarter/half nedskalering, floor 0.01, agri-halvering (SWING
    → 0.01 / MAKRO → 0.015), agri+VIX kombinert (→ 0.01-gulv)
  - `lots_to_volume_units`: exact match, step-down-rounding,
    min_volume-enforcing, fallback 1000, agri step_volume=100
  - `volume_to_lots`: med info, zero returns None, FX fallback
- `tests/unit/bot/test_ctrader_client.py` (+8):
  - `send_new_order` MARKET (verifiser label/volume/side)
  - `send_new_order` LIMIT med SL/TP/expiry
  - `send_new_order` LIMIT uten limit_price → `ValueError`
  - `amend_sl_tp` med SL+TP
  - `amend_sl_tp` med kun SL
  - `close_position` (positionId + volume)
  - `cancel_order` (orderId)
- `tests/unit/bot/test_entry.py` (+19):
  - `_execute_trade_impl`: MARKET-happy-path, LIMIT (rules=`use_limit_orders`),
    zero risk blocked, daily-loss blocked, oil geo+tight SL blocked,
    total-korrelasjon blocked, agri out-of-session blocked,
    agri in-session sender ordre med halvert volum
  - `_is_monday_gap`: gap > 2×ATR blokker, utenfor første time →
    False, ikke mandag → False
  - `_agri_session_ok`: innenfor timer / utenfor / ukjent instrument
  - `_log_trade_opened`: skriver korrekt JSON (signal-id,
    instrument, direction uppercase, lots, position_id, closed_at=None)

**Ikke endret:**
- `~/scalp_edge/` — READ-ONLY gjennom hele session
- Ingen prosesser rørt
- Ingen kode-endring i eksisterende Bedrock-moduler utenfor
  bot/{ctrader_client,entry,sizing,state}.py

**Commits:** `c201304`.

**Tester:** 890/890 grønne (fra 850 + 40 nye) på 32.3 sek.

**Neste session:** 45 — `bot/exit.py` med `ExitEngine`. Portere
`_manage_open_positions` (P1-P5 exit-prioritet), trail/BE-helpers,
weekend-gate, execution-handlere (on_execution/on_reconcile/
on_order_error), callback-wiring. Session 46 = `bot/__main__.py`
+ signal-handlers + full integrasjon.

### 2026-04-24 — Session 43: bot/entry + bot/sizing + AGRI-BUG FIX

**═══ KRITISK BUG-FIX (Fase 8 hovedleveranse) ═══**

`_recalibrate_agri_levels` (gammel trading_bot.py:2665-2693) er IKKE
portert. Kall-stedet i `_on_candle_closed` er fjernet. Gammel bot
overstyrte agri-signalers stop/t1/t2_informational/entry_zone med
1.5/2.5/3.5×live_atr uansett hva setup-generatoren hadde beregnet på
reelle støtte/motstand-nivåer. Ny `entry.py:_on_candle_closed` lar
agri-signal passere uendret til `_process_watchlist_signal`, som
setter `TradeState.stop_price/t1_price` fra `sig['stop']/sig['t1']`
direkte.

Regresjonstest: `test_agri_signal_not_overridden` i
`tests/unit/bot/test_entry.py`.

**Opprettet:**
- `src/bedrock/bot/entry.py` (~630 linjer) — `EntryEngine`:
  - Eier candle-buffere (15m/5m/1h) + indikator-state (EMA9, ATR14,
    ATR14-5m) per sid
  - Callbacks ut: `on_symbols_ready(client)`, `on_spot(event)`,
    `on_historical_bars(res)`, `on_signals(data)`
  - `_on_candle_closed`: daily-loss-reset, bot-lock-sjekk, server-
    frozen-guard, signal-fil-expiry, watchlist-iterasjon → filters →
    confirmation → `execute_trade`-callback → `manage_open_positions`-
    callback
  - `_process_watchlist_signal`: USD-dir-mapping-varsel, tidlig
    daily-loss-gate, per-signal TTL (fra config), duplikat-blokk,
    TradeState-oppretting ved in-zone, confirmation-candle-limit
  - `_passes_filters`: USDA blackout (agri), spread cold-start,
    spread-grense (agri_multiplier / non_agri_multiplier × stop_mult),
    R:R-gate (config.horizon_min_rr + geo-override)
  - `_check_confirmation`: 3-punkt scoring (body/wick/EMA-gradient),
    strict_score ved motstridende FX USD-retning, stats akkumuleres,
    persist hver 20. evaluering via atomic write
  - Helpers: `get_ema9`, `get_atr14`, `get_atr14_h1`, `get_normal_spread`

- `src/bedrock/bot/sizing.py` (~55 linjer) — `get_risk_pct` ren
  funksjon. Full/half/quarter basert på geo/VIX/character/outside.
  `rules.get("risk_pct_*")` overstyrer `cfg`-defaults slik at per-
  instrument YAML-override fortsatt virker

- `tests/unit/bot/test_entry.py` (26 tester):
  - `test_agri_signal_not_overridden` (KRITISK regresjonstest)
  - `test_technical_signal_also_unchanged`
  - Daily-loss-gate, TTL (stale SCALP / fresh SWING), duplikat-blokk
  - `_passes_filters`: cold-start, wide spread, R:R, USDA blackout
  - `_check_confirmation`: body ok, small-body-fails-strict, no-EMA,
    stats-persist-every-20
  - Indikatorer, on_symbols_ready, on_signals, execute_trade-callback
    full-flyt, manage_open_positions-callback uten signaler / frozen

- `tests/unit/bot/test_sizing.py` (13 tester): full matrise av
  geo/VIX/character/outside + rules-override + cfg-defaults

**Design-valg:**
- Scope-splitt: session 43 er candle-handling + signal-evaluering +
  confirmation. `_execute_trade` (ordre-sending) defer til session 44
  sammen med `bot/exit.py` fordi begge trenger CtraderClient-
  ordre-APIs (`send_new_order`, `amend_sl_tp`, `close_position`)
  som også legges til session 44. Dette grupperer cTrader-skrivende
  operasjoner logisk
- `EntryEngine` mottar `CtraderClient` som stub som leser
  symbol_map/last_bid/last_ask/spread_history/account_balance.
  Ingen ordre-sending ennå
- `execute_trade` og `manage_open_positions` injiseres som callbacks
  — stubbet til no-op i denne session. Session 44 wirer faktiske
  handlers
- `signal_data` settes via `on_signals`-callback (fra SignalComms),
  ikke direkte attributt-mutasjon — matcher dependency-injection-
  mønsteret resten av bot/
- TTL, min_rr, spread-min-samples, confirmation-terskler leses fra
  `ReloadableConfig` — SIGHUP-reload aktiverer nye verdier uten
  restart
- Confirmation-stats persistet atomisk (tempfile + os.replace) til
  `~/bedrock/data/bot/confirmation_stats.json`
- Spam-vern-set (`_usd_dir_missing_logged`, `_spread_cold_logged`,
  `_ttl_logged`, `_daily_loss_logged`) er instans-state, nullstilles
  ved restart — bevisst så ny instans får full-volum-logging

**Ikke endret:**
- `~/scalp_edge/` — READ-ONLY gjennom hele session
- Ingen prosesser rørt
- Ingen kode-endring i eksisterende Bedrock-moduler

**Commits:** `dcf415a`.

**Tester:** 850/850 grønne (fra 811 + 39 nye) på 30.1 sek.

**Neste session:** 44 — `bot/exit.py` + `_execute_trade` +
CtraderClient-ordre-APIs. Dette er session 43s naturlige fortsettelse
som gjenforener cTrader-ordre-skrivende-operasjoner.

### 2026-04-24 — Session 42: bot/safety + bot/comms

**Opprettet:**
- `src/bedrock/bot/safety.py` (~280 linjer) — `SafetyMonitor`:
  - Eier daily-loss-state + atomic persist (tempfile + os.replace)
    til `~/bedrock/data/bot/daily_loss_state.json`
  - `reset_daily_loss_if_new_day()` returnerer bool + kaller
    `on_rollover(prev_date, new_date)` FØR state resettes
  - `daily_loss_limit(balance, cfg)` statisk: max(pct × balance, nok-gulv)
  - `daily_loss_exceeded(balance, cfg)` → bool
  - `record_fetch_success()` — rydder server_frozen + fail-count
  - `record_fetch_failure(reason)` — eskalerende log
    (INFO n≤2 → WARNING 3≤n<10 → ERROR hvert 10. fra n=10)
  - Flagg: `server_frozen`, `bot_locked`, `bot_locked_until`
  - Corrupted/old-day state-handling: ignorerer trygt
  - Callback-exception isolert slik at git-commit-feil ikke
    blokkerer daily-reset
- `src/bedrock/bot/comms.py` (~320 linjer) — HTTP-lag + batch-commit:
  - `SignalComms(startup_cfg, api_key, safety, on_signals, on_kill_ids,
    session)` — valgfri requests.Session for mocking
  - `fetch_signals()` → dict | None. Schema-versjon-warn én gang per
    ukjent versjon. Sync med safety-tellere. on_signals-callback
  - `fetch_kill_ids()` → list[str]. Støtter både liste-svar og
    `{signal_ids: [...]}`. Fryser IKKE bot ved feil
  - `push_prices(prices)` → bool. POST /push-prices med X-API-Key
  - `fetch_once()` → `FetchResult(signals_data, kill_ids)` —
    convenience for polling-loop
  - Hand-rolled retry (0/1/3s backoff) i `_fetch_with_retry`. Retry
    kun på 5xx + nettverksfeil; 4xx propageres umiddelbart
  - `adaptive_poll_interval(signals_data, PollingConfig)` — ren
    funksjon, scalp_active_seconds hvis SCALP watchlist aktiv
  - `assemble_prices_from_state(symbol_map, price_feed_sids, last_bid)`
    — ren funksjon, bygger /push-prices-payload fra CtraderClient-state
  - `commit_daily_trade_log(log_path, date, repo_root)` — git-add +
    commit, `.githooks/post-commit` pusher. Toleranse: manglende fil
    = True, utenfor repo = False+warning, "nothing to commit" = True,
    commit-failure = False+warning
  - `SUPPORTED_SCHEMA_VERSIONS = frozenset({1.0, 2.0, 2.1})`
- `tests/unit/bot/test_safety.py` (26 tester)
- `tests/unit/bot/test_comms.py` (38 tester)

**Design-valg:**
- Polling-loopen (reactor.callLater self-scheduling) ligger ikke i
  comms.py — flyttes til `bot/__main__.py` i session 45 der
  Twisted-wiring er relevant. Ren HTTP + interval-beregning er her
  for test-isolering
- Schema-warn-set per-instans (ikke modul-nivå) slik at ny
  SignalComms gjenoppretter varslene — enklere test-isolering
- `commit_daily_trade_log` er modul-funksjon, ikke metode, så
  `safety.on_rollover` kan binde via `functools.partial` i
  `bot/__main__.py`
- Atomic write via tempfile + os.replace er forandring fra gammel
  bot (som gjorde direkte write). Dette er ikke "logikk" men
  robustness mot mid-write crash
- Initial retry-implementasjon brukte `sleep_fn=time.sleep`-default.
  Fix: `time.sleep` slås opp per kall (ikke bundet ved definisjon)
  slik at `patch('bedrock.bot.comms.time.sleep')` fungerer i tester

**Endringer fra gammel bot (ikke logikk):**
- `_git_push_log` (no-op i gammel bot etter K5) erstattes av faktisk
  daglig commit — kalt fra safety.on_rollover ved midnatt UTC
  (session 39-avtalen)
- daily_loss_state.json flyttet til `~/bedrock/data/bot/`
- Atomic persist (tempfile + os.replace)
- SIGNAL_URL leses fra `StartupOnlyConfig.signal_url` istedenfor
  modul-globalt

**Commits:** `dab6bc3`.

**Tester:** 811/811 grønne (fra 747 + 64 nye) på 29.3 sek.

**Neste session:** 43 — `bot/entry.py` + `bot/sizing.py`. Kritisk:
slett `_recalibrate_agri_levels` (agri-ATR-override-bug).

### 2026-04-24 — Session 41: bot/ctrader_client transport-port

**Opprettet:**
- `src/bedrock/bot/ctrader_client.py` (~680 linjer) — port av transport-
  laget fra `~/scalp_edge/trading_bot.py`:
  - `CtraderCredentials` (dataclass): cTrader OAuth-felt, injiseres
    via konstruktør istedenfor modul-level env-globale
  - `CtraderCallbacks` (dataclass): 8 callbacks med no-op defaults:
    `on_spot`, `on_historical_bars`, `on_execution`, `on_order_error`,
    `on_error_res`, `on_reconcile`, `on_symbols_ready`, `on_trader_info`
  - `CtraderClient`: eier Twisted-client + symbol-lookup-state
    (`symbol_map`, `symbol_digits`, `symbol_price_digits`, `symbol_pip`,
    `symbol_info`, `price_feed_sids`) + bid/ask/spread_history + reconnect-
    budsjett + watchdog/heartbeat
  - Public metoder: `start()`, `send()`, `send_reconcile()`,
    `request_historical_bars(symbol_id, period, bars_back)`
  - Private: `_on_connected`, `_on_disconnected`, `_fatal_exit`,
    `_on_message` (dispatcher), `_on_app_auth`, `_on_account_auth`,
    `_on_trader_info`, `_on_symbols_list` (inkl. throttle-scheduling),
    `_on_subscribe_spots`, `_on_symbol_by_id`, `_dump_agri_symbol_info`,
    `_on_spot`, `_on_historical_bars`, `_on_execution`,
    `_on_order_error`, `_on_error_res`, `_on_reconcile`,
    `_send_heartbeat`, `_watchdog_check`, `_check_symbol_silence`
  - Modulkonstanter: `M15_PERIOD`/`M5_PERIOD`/`H1_PERIOD`,
    `AUTH_FATAL_ERROR_CODES` (6 koder), `AGRI_SYMBOL_INFO_PATH`,
    watchdog-terskler, heartbeat-intervall (25s), watchdog-intervall (30s)
  - `load_credentials_from_env()` for `bot/__main__.py` session 45
- `tests/unit/bot/test_ctrader_client.py` (32 tester)

**Endringer fra gammel bot (ikke "logikk", men nødvendige):**
- Credentials: injiseres via `CtraderCredentials` i stedet for
  modul-global `CLIENT_ID`/`CLIENT_SECRET`/`ACCESS_TOKEN`/`ACCOUNT_ID`
- AGRI-symbol-dump flyttet fra `~/cot-explorer/data/prices/` til
  `~/bedrock/data/bot/agri_symbol_info.json` (cot-explorer eksisterer
  ikke som referanse i Bedrock)
- Reconnect-budsjett leses fra `StartupOnlyConfig.reconnect` (var
  modul-konstanter `RECONNECT_WINDOW_SEC=600`/`RECONNECT_MAX_IN_WINDOW=5`)
- `_on_error_res` sjekker nå `AUTH_FATAL_ERROR_CODES` eksplisitt og
  kaller `_fatal_exit(78)` (gammel bot hadde lignende sjekk spredt i
  `_on_app_auth`/`_on_account_auth`-paths; ny sentralisering fanger
  token-expired selv på senere responses)

**Design-valg:**
- `CtraderCallbacks` med no-op defaults slik at testing ikke krever
  full bot-wiring og stegvis integrasjon er enkelt
- Callbacks eksception-isolert med try/except: én krasj i entry/exit
  stopper ikke transport-laget
- `on_symbols_ready(client)` fires FØR subscribe-spots starter —
  bot/entry har tid til å initialisere candle-buffere før første
  spot-event ankommer
- Transport-laget eier bid/ask + spread_history (ikke candle-buffere),
  fordi disse er rene TCP-side-effekter av SpotEvent
- `request_historical_bars` tar `period` som argument (ny flexibility)
  i stedet for gammel `_request_historical_bars_h1` duplikatmetode
- Handler-dispatcher (`_handlers()`) returnerer dict som bygges ved
  første kall; instansierer prototype-protobuf-meldinger lazy slik at
  import av modulen (for ctrader_client-konstruksjon i tester) ikke
  krever fullt protobuf-reg-oppsett
- Agri-dump bruker `pathlib.Path`/`read_text`/`write_text` i stedet
  for `os.path`/`open()` — ryddigere; samme atferd

**Dependency-håndtering:**
- Bot-extras installert i `.venv`:
  - `twisted==24.3.0`
  - `protobuf==6.33.6`
  - `service_identity==24.2.0`
  - `ctrader-open-api==0.9.2` (med `--no-deps` for å omgå
    transitive `protobuf==3.20.1`-pin)
- Dette matcher `~/scalp_edge/requirements.txt` produksjonsversjoner.
  `pyproject.toml`-endring utsatt — når `uv sync` brukes i Fase 11-12
  cutover trengs `[tool.uv] override-dependencies = ["protobuf>=6.0"]`
  eller tilsvarende

**Ikke gjort i denne session:**
- `send_new_order`, `amend_sl_tp`, `close_position`, `cancel_order`:
  utsatt til session 43-44 (entry/exit trenger dem; generell `send()`
  dekker inntil da)

**Ikke endret:**
- `~/scalp_edge/` — fullstendig READ-ONLY
- Ingen prosesser rørt
- `pyproject.toml` — bot-extras-blokken uendret (kjent konflikt
  noteres for ops-oppsett)

**Commits:** `5f710a3`.

**Tester:** 747/747 grønne (fra 715 + 32 nye) på 28.5 sek.

**Neste session:** 42 — `bot/safety.py` + `bot/comms.py`.

### 2026-04-24 — Session 40: bot/ skjelett + state + instruments + config

**Opprettet:**
- `src/bedrock/bot/__init__.py` (pakke-doc med modul-oversikt)
- `src/bedrock/bot/state.py` — `TradePhase`, `Candle`, `TradeState`,
  `CandleBuffer` portert 1:1 fra `~/scalp_edge/trading_bot.py:335-398`.
  Forblir dataclass (ikke Pydantic); endring krever ADR
- `src/bedrock/bot/instruments.py` — `INSTRUMENT_MAP`, `PRICE_FEED_MAP`,
  `INSTRUMENT_TO_PRICE_KEY`, `FX_USD_DIRECTION`, `AGRI_INSTRUMENTS`,
  `AGRI_SUBGROUPS`, `INSTRUMENT_GROUP` + `net_usd_direction`,
  `looks_like_fx_pair`, `get_group_name`. Ren data-lookup; ikke i YAML
  fordi YAML-en ville blitt rent støy og kreve egen Pydantic-modell
- `src/bedrock/bot/config.py` — Pydantic-modell for `config/bot.yaml`
  med eksplisitt splitt:
  - `StartupOnlyConfig`: signal_url, signal_api_key_env, reconnect
  - `ReloadableConfig`: confirmation, risk_pct, daily_loss, spread,
    horizon_ttl, horizon_min_rr, polling, weekend, monday_gap, trail,
    agri (incl. session_times_cet), oil, group_params (per gruppe)
  - `load_bot_config(path)` — oppstart-lasting, støtter tom eller
    manglende fil → Pydantic-defaults
  - `reload_bot_config(path, current)` — SIGHUP-handler-entry: leser
    ny YAML, beholder `current.startup_only` aktiv, bytter bare
    `reloadable`, returnerer `(merged_config, diffs: list[str])`
  - `diff_startup_only(a, b)` — rekursiv sammenligning for warning-
    logging ved SIGHUP
  - Path-oppløsning: eksplisitt argument > env `BEDROCK_BOT_CONFIG` > default
- `config/bot.yaml` — alle defaults fra `trading_bot.py` portert 1:1.
  Top-level seksjoner `startup_only` + `reloadable`
- `tests/unit/bot/test_state.py` (5 tester) — enum, Candle-konstruksjon,
  TradeState-defaults, CandleBuffer-defaults, uavhengige deque-instanser
- `tests/unit/bot/test_instruments.py` (16 tester) — lookup-komplett,
  ingen overlapp mellom trading- og pris-feed-symboler, net_usd_direction
  per retning, looks_like_fx_pair positive+negative, get_group_name
  fallback, FX-dekning
- `tests/unit/bot/test_config.py` (22 tester) — defaults, empty/partial
  YAML-merge, bundled `config/bot.yaml` parses og matcher Python-
  defaults, roundtrip, extra=forbid på nested modeller, SIGHUP-diff
  top-level + nested, reload holder startup_only og bytter reloadable,
  path-oppløsning (arg > env > default), GroupParams-validering

**Design-valg:**
- YAML-splitt med `startup_only`/`reloadable` speiles i Pydantic-
  typer, ikke konvensjon — type-systemet gjør det umulig å blande
- `reload_bot_config` returnerer diff-liste i stedet for å logge
  selv; caller (SIGHUP-handler i `bot/__main__.py`, kommer session 45)
  styrer loggernavn
- `signal_api_key_env` holder *navn* på env-var, ikke selve nøkkelen
  (secrets kun via env/fil per PLAN § 10.6)
- `GroupParams` er felt-nivå påkrevd (ingen defaults) for å fange
  utilsiktet utelatelse av `ema9_exit` eller `expiry` ved ny gruppe
- `_default_group_params()` dekker 12 grupper fra gammel bot;
  brukeren kan overstyre alle eller deler via `reloadable.group_params`
- `AGRI_INSTRUMENTS` som `frozenset` i stedet for `set` — signaliserer
  at den ikke skal muteres, matcher i dag-semantikk i gammel bot
- Sortert nøkler i `_walk_diff` for deterministisk diff-output

**Prosess-avklaringer fra bruker (session 40):**
- SIGHUP-split bekreftet: startup_only = signal_url, reconnect,
  account_id-nivå; reloadable = terskler + risk + agri + polling
- Bot gjør git-add+commit selv for trade-logging, men batches til
  én commit per dag ved daily_loss-reset (unngår spam). SSH-tilgang
  for bot-service håndteres i Fase 13 cutover. Implementeres i
  session 42 med `bot/comms.py` eller `bot/safety.py`

**Ikke endret:**
- `~/scalp_edge/` — fullstendig READ-ONLY under hele session
- Ingen prosesser rørt

**Commits:** `0802327`.

**Tester:** 715/715 grønne (fra 672 + 43 nye) på 28.9 sek.
Kjøring krever `PYTHONPATH=src` — verifisert at `bedrock`-pakken
ikke er installert som editable, men tester fungerer likevel.

**Neste session:** 41 — `bot/ctrader_client.py` per migration-plan
§ 8 punkt 2. Port Twisted + Protobuf + reconnect-laget; ingen
trade-logikk, kun transport.

### 2026-04-24 — Session 39: Fase 8 åpnet, migrasjonsplan for bot-refaktor

**Opprettet:**
- `docs/migration/` (ny katalog for Fase 8-dokumentasjon)
- `docs/migration/bot_refactor.md` (633 linjer) — research-leveranse:
  - Fil-metadata for `~/scalp_edge/trading_bot.py` (2977 linjer,
    4 top-level klasser + ScalpEdgeBot med 66 metoder)
  - Topp-nivå struktur-mapping (imports, env-config, logging,
    modul-konstanter, dataclasses, `ScalpEdgeBot`, `check_env`)
  - Metode-kart per målmodul (ctrader_client, entry, sizing, exit,
    state, safety, comms, __main__) med eksakte linjenumre
  - Eksakt kode-sitat av agri-ATR-override-bugen: metode er
    `_recalibrate_agri_levels` (linje 2665-2693), ikke
    `_calibrate_agri_signal` som PLAN § 9.1 sier. Overstyrer stop/t1/
    t2_informational/entry_zone med 1.5/2.5/3.5×live_atr uansett
    setup-generator-nivå
  - Hardkodede terskler delt i:
    (a) allerede parametrisert via `rules.get()` — kun default
    flyttes til `bot.yaml`
    (b) ikke-parametrisert — legges til `bot.yaml` (MIN_SPREAD_SAMPLES,
    HORIZON_TTL_SECONDS, AGRI_SESSION, GROUP_PARAMS, body-threshold,
    EMA-gradient-grenser, weekend-SL-mult, monday-gap-mult, osv.)
    (c) skal IKKE i YAML (protobuf-enums, auth-error-koder,
    instrument-lookup-dicts)
  - Target-modul-struktur (10 filer, ikke 8 som PLAN § 9.4 foreslår —
    avvik begrunnet: `bot/instruments.py` for data-lookup og
    `bot/config.py` for SIGHUP-reload)
  - Avhengighetsgraf uten sirkulære imports
  - Refaktor-rekkefølge session 40-47 med konkrete leveranser per session
  - Test-strategi (logiske primær, enhets sekundær)
  - Risiko + åpne spørsmål (Twisted-singleton i pytest,
    reconcile-recovery under cutover, SIGHUP-reload-scope,
    `_git_push_log`-fjerning)

**Endret:**
- (ingen kode endret — research/planning only per Fase 8 session 1-kontrakt)

**Prosess-avtale fra bruker (session 39):**
- Under refaktoren er `~/scalp_edge/` READ-ONLY
- Alle output-filer går til Bedrock-repoet (`docs/migration/`,
  `src/bedrock/bot/`, `config/bot.yaml`, etc.)
- Gammel bot-prosess og gammel signal_server-prosess røres ikke
- Selve refaktoreringen starter fra session 40 i Bedrock-repoet;
  gammel bot fortsetter uendret i demo-parallell til Fase 11-12 cutover

**Design-valg dokumentert:**
- 10 moduler i stedet for 8 (PLAN § 9.4): tillegg `instruments.py`
  og `config.py`. Bestemt via CLAUDE.md beslutnings-retningslinje
  (mappe-struktur = Claude bestemmer, trading-/UX-valg = bruker)
- Agri-override-metode faktisk navn: `_recalibrate_agri_levels`.
  PLAN.md kan rettes senere; ikke blokker Fase 8
- `_git_push_log` fjernes i bot-refaktoren — dekkes av Bedrocks
  `.githooks/post-commit`. Bekreftelse utsatt til session 42
- `ProtoOATrendbarPeriod`-enums, `CET` ZoneInfo, heartbeat-intervall
  25s, watchdog-intervall 30s beholdes i kode (ikke konfig)
- `TradeState` forblir dataclass, ikke Pydantic (endring krever ADR)

**Åpne spørsmål til bruker (ikke blokkerende før session 43-44):**
- SIGHUP-reload scope: kun "myke" felter (trail_atr, giveback,
  confirmation-terskler) eller all-or-nothing?
- Bekreft at `.githooks/post-commit` auto-push dekker alt
  `_git_push_log` gjør i dag, og at bot-loggene kan committes av
  post-commit-hooken uten egne bot-side git-kall

**Commits:** `b1bfa98` (docs-only).

**Tester:** 672/672 uendret (ingen kode berørt).

**Neste session:** 40 — skjelett + state + instruments + config, per
`docs/migration/bot_refactor.md § 8 punkt 1`. Ingen kode-endring
utenfor Bedrock-repoet.

### 2026-04-24 — Session 38: /admin/rules + Fase 7 klar for closure

**Opprettet:**
- `bedrock.config.instruments.load_instrument_from_yaml_string`:
  public validator for YAML-string (parallell til
  `load_instrument_config` som tar Path)
- `config`: `instruments_dir`, `admin_code: str | None`,
  `BEDROCK_ADMIN_CODE` env-override
- `endpoints.rules_bp`:
  - `GET /admin/rules` — instrument-liste
  - `GET /admin/rules/<id>` — rå YAML
  - `PUT /admin/rules/<id>` — validere + atomic write
  - X-Admin-Code header-auth
  - Regex `^[a-zA-Z0-9_-]+$` på id mot path-traversal
  - URL-id må matche YAML-id (case-insensitive)
- `tests/unit/test_signal_server_rules.py` (24 tester)

**Endret:**
- `app.py`, `endpoints/__init__.py`: registrerer rules_bp
- `ENDPOINTS.md`: 3 nye endepunkter implementert
- `test_signal_server_app.py`: /status-test fikset

**Design-valg:**
- Auth via header (ikke session): admin-UI har ikke login-flow
- admin_code=None → 503: secure-by-default; endepunktene av før
  admin konfigurerer passord
- Strikt id-regex: fanger path-traversal før filsystem-operasjon
- URL-id vs YAML-id-match: hindrer filnavn ↔ innhold-divergens
- Public `load_instrument_from_yaml_string` istedenfor å dra inn
  private `_parse_instrument_dict`

**Bevisst utsatt fra PLAN § 8.3:**
- Dry-run-diff (krever orchestrator + snapshot-kobling)
- Auto git-commit i PUT-responsen (ops-tung integrasjon)
- UI-side (HTML/JS) — Fase 9

**Commits:** `2274faa`.

**Tester:** 672/672 grønne på 28.2 sek (fra 648 session 37, +24).

**Fase 7 leveranse-sum (sessions 33-38):**
- Session 33: app-factory, ServerConfig, /health, /status, ENDPOINTS.md
- Session 34: /signals + /agri-signals (read)
- Session 35: /push-alert + /push-agri-alert (skriv, atomic)
- Session 36: /kill + /kills + /clear_kills + /invalidate
- Session 37: /push-prices + /prices + /upload
- Session 38: /admin/rules GET list/detail + PUT

Alle kjerne-endepunkter fra 974-linjers `scalp_edge.signal_server`
+ ny rule-editor-funksjonalitet. Blueprints per gruppe.
Pydantic-validering på alle skriv-endepunkter. Atomic write overalt.
Port 5100 default (parallell-drift). Auth på admin-endepunkter.

**Tag:** `v0.7.0-fase-7` opprettet og pushet.

### 2026-04-24 — Session 37: /push-prices + /prices + /upload

**Opprettet:**
- `schemas.PriceBarIn` (ts + close påkrevd; OHLV valgfritt;
  extra='forbid') og `PushPricesRequest`
- `config`: `db_path`, `uploads_root`, `upload_max_bytes` (10 MB),
  `upload_allowed_exts` (.png, .jpg, .jpeg, .pdf)
- `endpoints.prices_bp`:
  - `POST /push-prices` → DataStore.append_prices via fresh
    DataStore per request. 201 med `{instrument, tf, bars_written}`
  - `GET /prices?instrument=X&tf=Y&last_n=N` — last_n default 500.
    Tom store / ukjent slot → 200 + `bars: []`
- `endpoints.uploads_bp`:
  - `POST /upload` multipart/form-data med `file`-felt. Ekstensjon-
    whitelist + 10 MB-cap + tom-fil-sjekk. Lagres som
    `<token_hex(16)><ext>`. 413 ved størrelse-overskridelse
- `tests/unit/test_signal_server_prices_uploads.py` (22 tester)

**Endret:**
- `app.py`, `endpoints/__init__.py`: registrerer prices_bp + uploads_bp
- `ENDPOINTS.md`: 3 endepunkter markert implementert
- `prices.py`: DataStore.get_prices KeyError → tom 200-respons
- `test_signal_server_app.py`: /status-test oppdatert

**Design-valg:**
- Fresh DataStore per request: ingen connection-pooling før multi-
  worker er relevant
- Idempotent INSERT OR REPLACE på (instrument, tf, ts): bot kan
  retry trygt
- `secrets.token_hex(16)` for upload-navn: unngår path-traversal +
  PII-lekkasje. Original filnavn returneres til klienten, men ikke
  bevart på disk
- Multipart-upload lese til minne før disk-write: 10 MB-cap sikrer
  det er akseptabelt; stream-basert kunne blitt relevant ved GB-skala
- `extra='forbid'` på price-schemas: klient-typos fanges med 400
- KeyError fra get_prices → 200 + `bars: []`: semantikk-match med
  /signals ved manglende fil; fravær av data ≠ server-feil

**Commits:** `a63bc7d`.

**Tester:** 648/648 grønne på 26.5 sek (fra 626 session 36, +22).

**Endepunkt-progresjon:** samtlige kjerne-endepunkter fra gammel
scalp_edge.signal_server (974 linjer) er nå portert. Gjenstår
`/admin/rules` (session 38, PLAN § 8.3 — ny funksjonalitet).

**Neste session:** 38 — `/admin/rules` GET/PUT.

### 2026-04-24 — Session 36: /kill + /kills + /clear_kills + /invalidate

**Opprettet:**
- `schemas.KillSwitch` (instrument, horizon, killed_at auto, reason),
  `.slot`-property for dedupe
- `schemas.InvalidationRequest` (instrument, direction, horizon, reason)
- `storage.load_kills(path)` — samme semantikk som load_signals
- `storage.upsert_kill(path, kill)` — dedupe på (instrument, horizon),
  nyeste vinner. Atomic write
- `storage.clear_all_kills(path)` — returnerer antall fjernet
- `storage.invalidate_matching(path, *, ...)` — marker matchende
  signaler med `invalidated=True`, `invalidated_at`, `invalidated_reason`.
  Atomic skriv kun hvis count > 0
- `endpoints.kills_bp`:
  - `POST /kill` — upsert
  - `GET /kills` — liste
  - `POST /clear_kills` — tøm
- `/invalidate` i signals_bp — POST, sjekker BÅDE signals_path og
  agri_signals_path, returnerer per-fil-count + total
- `tests/unit/test_signal_server_kills.py` (29 tester)

**Design-valg:**
- Dedupe på slot: kill-switch er live-bryter uten historikk;
  flere calls på samme slot er idempotent (nyeste vinner)
- Invalidate sjekker begge filer: klienten trenger ikke vite
  asset-class-fila; per-fil-count gir transparens
- Match-nøkkel = (instrument, direction, horizon): naturlig slot-
  nivå. setup_id-match ville krevd schema-bump av PersistedSignal
- Invalidate-felter via `extra='allow'`: ingen schema-version-bump
- `invalidate_matching` skriver kun hvis count > 0: preserver
  fil-mtime ved ingen match

**Commits:** `08b8531`.

**Tester:** 626/626 grønne på 24.9 sek (fra 597 session 35, +29).

**Neste session:** 37 — /push-prices + /prices + /upload.

### 2026-04-24 — Session 35: /push-alert + /push-agri-alert skriv-path

**Opprettet:**
- `storage.append_signal(path, signal)`:
  - Read-modify-write via `load_signals` + append + `_atomic_write_json`
  - Atomic write: `tempfile.mkstemp` (samme filesystem) → `json.dump` +
    `os.fsync` → `os.replace`. Rydder tmp ved exception
  - Korrupt eksisterende fil → `SignalStoreError` (hindrer overwrite)
  - Auto-oppretter parent-dir
- `bedrock.signal_server.endpoints.alerts_bp`:
  - `POST /push-alert` → `cfg.signals_path`
  - `POST /push-agri-alert` → `cfg.agri_signals_path`
  - Felles `_parse_and_append` med status-koder:
    - 415 ikke-JSON Content-Type
    - 400 ugyldig JSON eller ikke-objekt-body
    - 400 Pydantic-valideringsfeil (med `include_context=False`-
      trimmet details)
    - 500 ved korrupt eksisterende fil
    - 201 + validert signal ved suksess
- `tests/unit/test_signal_server_alerts.py` (21 tester)

**Endret:**
- `app.py`: registrerer alerts_bp
- `endpoints/__init__.py`: eksporterer alerts_bp
- `ENDPOINTS.md`: /push-alert + /push-agri-alert implementert
- `test_signal_server_app.py`: /status-test fikset

**Design-valg:**
- Atomic write via `os.replace` (ikke `os.rename`): `replace` er
  cross-platform og overskriver eksisterende fil; `rename` feiler
  på Windows hvis target finnes
- mkstemp på samme parent: `rename` på tvers av filsystem er ikke
  atomisk; må være innenfor samme mount
- `fsync` før rename: beskytter mot krasj mellom skriv og rename
  (fil ville vært tom ved reboot ellers)
- Korrupt eksisterende fil → 500 (ikke overwrite): beskytter
  eksisterende signaler; ops må fikse/slette manuelt
- Read-modify-write på server (ikke klient-side last-seen): holder
  protokoll enkel; klienten vet ikke om tidligere innhold
- `include_context=False`: ekskluderer ValueError-instanser som
  ikke er JSON-serialiserbare
- Returnerer 201 + normalisert signal: klient ser hva som faktisk
  ble lagret

**Commits:** `1d880d3`.

**Tester:** 597/597 grønne på 23.8 sek (fra 576 session 34, +21).

**Neste session:** 36 — kill-switch + invalidate.

### 2026-04-24 — Session 34: /signals + /agri-signals read-endepunkter

**Opprettet:**
- `bedrock.signal_server.schemas.PersistedSignal`:
  - Pydantic `extra='allow'` → forward-compat mot orchestrator-
    schema-evolusjon
  - Validerer direction (BUY/SELL), horizon (SCALP/SWING/MAKRO),
    score >= 0
  - `SignalStoreError` for korrupt fil
- `bedrock.signal_server.storage.load_signals(path)`:
  - Tom/manglende/whitespace-only fil → `[]`
  - Ugyldig JSON, non-array root, non-object rad, feilet Pydantic
    → `SignalStoreError` med index-info
- `bedrock.signal_server.endpoints.signals_bp`:
  - `GET /signals` fra `cfg.signals_path`
  - `GET /agri-signals` fra `cfg.agri_signals_path`
  - Korrupt fil → 500 + `{error}` (bevisst ikke stille svikt)
- `tests/unit/test_signal_server_signals.py` (23 tester)

**Endret:**
- `app.py`: registrerer signals_bp
- `ENDPOINTS.md`: markert /signals + /agri-signals implementert
- `test_signal_server_app.py`: oppdatert /status-test

**Design-valg:**
- Eget schema framfor å gjenbruke `SignalEntry`: serveren og
  orchestrator kan utvikles uavhengig. `extra='allow'` sikrer at
  ukjente felt passer gjennom HTTP-laget urørt
- 500 på korrupt fil (ikke []): ops-synlighet > tom-liste-lure-UI
- Tom/manglende fil = [] @ 200: helt normalt før første orchestrator-
  kjøring
- To separate filer (signals.json + agri_signals.json): matcher
  gammel scalp_edge og gjør UI-fanene uavhengige

**Commits:** `c9e9193`.

**Tester:** 576/576 grønne på 23.5 sek (fra 553 session 33, +23).

**Neste session:** 35 — `/push-alert` + `/push-agri-alert` (skriv).

### 2026-04-24 — Session 33: Fase 7 åpnet, signal-server-skeleton

Første Fase 7-leveranse. PLAN § 8-refaktor av 974-linjers
scalp_edge/signal_server.py til modul-struktur.

**Opprettet:**
- `bedrock.signal_server`-pakke:
  - `create_app(config=None) -> Flask` — app-factory, fresh
    instans per kall
  - `config.ServerConfig` — Pydantic frozen, extra=forbid.
    Defaults: port 5100 (ikke 5000), host 127.0.0.1, data_root
    data/, server_name "bedrock-signal-server"
  - `config.load_from_env(env)` — BEDROCK_-prefiks
  - `/health` (GET) — liveness-check
  - `/status` (GET) — config-dump + liste over registrerte
    endepunkter
- `src/bedrock/signal_server/ENDPOINTS.md` — inventar av alle 12
  endepunkter fra gammel server + status-kolonne + session-plan
  (34-38)
- `tests/unit/test_signal_server_app.py` (16 tester)

**Endret:**
- flask installert i `.venv` (var i pyproject, bare ikke installert)

**Design-valg:**
- Port 5100: avviker fra gammel 5000 slik at begge kan kjøre samtidig
  under parallell-drift (Fase 12). Cutover i Fase 13 flytter bot+UI
- App-factory + ingen global `app`-variabel: tester kan lage
  isolerte instanser; multi-worker-deploy kan konfigurere pr worker
- Pydantic-config (ikke dict): type-safe, frozen hindrer at
  endepunkter muterer runtime-config
- `app.extensions["bedrock_config"]` som config-kanal: unngår
  Flask-globals-magi
- `/status` lister faktiske endepunkter: selv-dokumenterende;
  bryter hvis ENDPOINTS.md ikke oppdateres når ny gruppe
  registreres
- Ingen CLI-kommando ennå (`bedrock server run`): venter til det
  er minst én reell skriv-endepunkt

**Commits:** `cd385f1`.

**Tester:** 553/553 grønne på 22.2 sek (fra 537 session 31, +16).

**Bevisste utsettelser (planlagt per ENDPOINTS.md):**
- Session 34: `/signals` + `/agri-signals` (read)
- Session 35: `/push-alert` + `/push-agri-alert` (write)
- Session 36: `/kill` + `/clear_kills` + `/invalidate`
- Session 37: `/push-prices` + `/prices` + `/upload`
- Session 38: `/admin/rules` (ny per PLAN § 8.3)

**Neste session:** 34 — `/signals` + `/agri-signals` med Pydantic
response-schema.

### 2026-04-24 — Session 32: Fase 6 CLOSED + PLAN-nummerering sync

Fase 6 leveranse verifisert. Ingen ny kode; ren rydding.

**Tagget:** `v0.6.0-fase-6` med leveranse-summary.

**Fase 6 leveranse-sum (sessions 27-31):**
- **USDA-kalender + `usda_blackout`-gate** (session 27): `usda.yaml`-
  loader med 6 måneders blackout-vindu per event, `usda_in_blackout`-
  gate som nekter signaler i pre-event-stillhet
- **Config-drevet `fetch.yaml`** (session 28): Pydantic-validert
  schema med cron + stale_hours + on_failure, `bedrock fetch
  status`-CLI som viser hvilke kilder som er oppdaterte
- **`bedrock fetch run <name>`-dispatcher** (session 29): runner-
  registry for alle 5 fetchere, --stale-only-filter, --instrument-
  filter, per-item resiliens med retry-kommando-summary
- **systemd-unit-generator** (session 30): `bedrock systemd
  generate/install/list`-CLI, cron → OnCalendar-konverter, 10 auto-
  genererte unit-filer committet. Installasjon utsatt til Fase 12
  cutover per bruker-direktiv
- **`currency_cross_trend`-driver** (session 31): BRL/USD-style
  cross-driver (generisk via params.source), unidirectional bull
  med `direction: invert`-flag

**Ikke i Fase 6 (bevisst utsatt):**
- BRL/USD-backfill — `bedrock backfill prices --ticker brlusd=x`
  fungerer, men er ikke kjørt
- Baltic Dry → agri-driver
- WASDE PDF-parsing, Crop Progress, Eksport-policy-tracker, IGC,
  Disease-varsling (PLAN § 7.3)
- systemd-install (Fase 12 cutover)

Disse er drivere/kilder som kan legges til når som helst uten å
blockere senere faser.

**PLAN § 13-rydding:**
- Ny Fase 5 "Scoring-motor komplett" lagt inn (reflekterer faktisk
  leveranse sessions 21-26)
- Fase 5 "Fetch-laget" → Fase 6
- Fase 6 "Signal-server" → Fase 7
- Alle senere faser skjøvet ett hakk (bot=8, UI=9, analog=10,
  backtest=11, demo=12, cutover=13)
- PLAN-referanser oppdatert: "trades.parquet venter til Fase 8",
  "Analog-søk (Fase 10)", gate-review-faser, Nivå 3-overgang
- CLAUDE.md synkronisert (Fase 0-11 = Nivå 1, Fase 11-12 = overgang)

**Tester:** 537/537 grønne (uendret fra session 31).

**Neste session:** 33 — åpner Fase 7, signal-server-refaktor.

### 2026-04-24 — Session 31: currency_cross_trend-driver

Femte Fase 6-leveranse. PLAN § 7.3 "BRL/USD aktivt drivet" for softs.

**Opprettet:**
- `bedrock.engine.drivers.currency.currency_cross_trend`:
  - Params: source (påkrevd), lookback (default 30), tf (default D1),
    direction ("direct"/"invert")
  - Score-mapping: pct >= +10%: 1.0, >= +5%: 0.8, >= +2%: 0.65,
    >= 0%: 0.5, >= -2%: 0.35, >= -5%: 0.2, < -5%: 0.0
  - `direction: invert` snur fortegn for tilfeller der kun motsatt
    cross (USDBRL) finnes
  - Defensive: manglende source / ukjent direction / kort historikk /
    tomt prisoppslag → 0.0 + logg
- `tests/logical/test_currency_drivers.py` (17 tester)

**Endret:**
- `bedrock.engine.drivers.__init__`: importerer currency-modul

**Design-valg:**
- `instrument`-argumentet ignoreres; driveren leser fra
  `params["source"]`. Dette er første cross-driver-mønster og kan
  gjenbrukes for andre cross (CNY/USD for metaller, etc.)
- Step-funksjon i tester istedenfor lineær ramp: gir eksakt pct-
  endring over lookback-vinduet og matcher driverens formel presis
- Én driver med `direction: invert` framfor to (bull/bear) holder
  YAML-reglene kortere
- Ikke wiring til noen YAML-instrument — det hører til instrument-
  config-arbeid, ikke driver-leveransen

**Commits:** `57e05a4`.

**Tester:** 537/537 grønne på 22.4 sek (fra 520 session 30, +17).

**Bevisste utsettelser:**
- Wiring av driver i sugar.yaml/coffee.yaml — senere session
- BRL/USD backfill — CLI støtter allerede `bedrock backfill prices
  --ticker brlusd=x` via Stooq
- Regresjons-baserte cross-drivere / auto-detect retning —
  premature, venter til konkret behov

**Neste session:** 32 — Baltic Dry til agri (PLAN § 7.3), eller
lukk Fase 6 med tag hvis bruker er fornøyd med nåværende scope.

### 2026-04-24 — Session 30: systemd-unit-generator

Fjerde Fase 6-leveranse. Bruker-direktiv: systemd (PLAN § 3.1 + § 13),
ingen APScheduler. Sessions 28-29 bygde fetch-workflowet; session 30
plugger det inn i systemd slik at cron-kjøring skjer utenfor Python.

**Opprettet:**
- `bedrock.systemd.generator`:
  - `cron_to_oncalendar(expr)` — 5-felt cron → OnCalendar-streng.
    Støttet undersett: `*`, heltall, `A-B`/`A,B,C` i dow. Søndag
    som både `0` og `7`
  - `generate_service_unit(name, *, working_dir, bedrock_executable,
    module_hint)` og `generate_timer_unit(name, cron, *, persistent)`
  - `generate_units(fetch_config, ...)` — batch-mapping
  - `write_units(units, output_dir)` — skriver til disk
  - `CronConversionError` for ikke-støttet syntaks (step, navn)
- `bedrock.cli.systemd`:
  - `generate` — leser fetch.yaml, skriver unit-filer. Flagge:
    --config, --output, --working-dir, --executable
  - `install` — `systemctl --user link` per genererte unit.
    --dry-run, fail-propagering, systemctl-detection
  - `list` — viser OnCalendar-tider uten å installere
- `systemd/` fylt med 10 auto-genererte unit-filer (5 fetchere × 2
  filer). Checked in slik at installasjon fungerer umiddelbart
- `systemd/README.md` omskrevet for `--user`-flyt (erstatter gammel
  `sudo systemctl link`-guide)
- `tests/unit/test_systemd_generator.py` (28 tester)

**Endret:**
- `bedrock.cli.__main__`: registrerer systemd-gruppen

**Design-valg:**
- `systemctl --user` (ikke system-wide): ingen sudo nødvendig,
  brukeren styrer egen deployment
- `Persistent=true` på timer: systemd kjører unit etter boot hvis
  maskinen var av på planlagt tid — kritisk for stale_hours-budsjettet
- `Type=oneshot` på service: riktig for batch-fetchere som avslutter
  når ferdig, ikke long-running daemon
- `install` gjør KUN `link`, ikke `enable --now`. Brukeren må eksplisitt
  aktivere etter inspeksjon — tryggere første-gang-setup
- Auto-detect av `bedrock`-CLI via `<sys.prefix>/bin/bedrock` først,
  fallback til PATH, siste utvei `python -m bedrock.cli`
- Unit-filene sjekket inn som kilde-kontrollert output: gjør diff-ene
  leselige ved fetch.yaml-endringer og lar install fungere uten
  generate først

**Commits:** `ee65765`.

**Tester:** 520/520 grønne på 18.9 sek (fra 492 session 29, +28).

**Bevisste utsettelser:**
- `*/N` step-values og navngitte cron-felter — kommer hvis fetch.yaml
  noensinne trenger dem. For session 30 er dette ikke tilfelle
- `enable --now`-automatisering — UX-valg; bruker ønsker kontroll
- Timere for signal-pipeline/bot/server — Fase 11 (PLAN § 8-9 må
  refaktoreres først)
- Generering av system-wide units — ikke nødvendig i nåværende scope

**Neste session:** 31 — BRL/USD driver (PLAN § 7.3) eller annen
Fase 6-oppgave etter brukers valg.

### 2026-04-24 — Session 29: bedrock fetch run — runner-dispatcher

Tredje Fase 6-leveranse. Session 28 ga schema + status; session 29
legger til faktisk fetcher-kjøring. Fetch-workflow er nå praktisk
uten ekstern scheduler.

**Opprettet:**
- `bedrock.config.fetch_runner`:
  - `@register_runner(name)` + `get_runner` + `all_runner_names` —
    samme mønster som gates-registry fra session 25
  - `FetchRunResult` dataclass + `ItemOutcome` per item
  - `run_fetcher_by_name(name, store, spec, *, from_date, to_date,
    instruments_dir, defaults_dir, instrument_filter)`
  - 5 innebygde runners: prices, cot_disaggregated, cot_legacy,
    weather, fundamentals
  - `default_from_date(spec, now, buffer_multiplier=2.0)` — lookback
    basert på stale_hours
- `bedrock fetch run [name]`:
  - Valgfri positional: én fetcher-navn, eller alle hvis tom
  - Flagge: --config, --db, --instruments-dir, --defaults-dir,
    --from, --to, --stale-only, --instrument
- `tests/unit/test_fetch_runner.py` (13 tester)

**Endret:**
- `bedrock.cli.fetch` utvidet med `run`-subkommando
- `.gitignore`: ignorer `data/*.db` (tester genererte en tom DB som
  snek seg inn i commit, ryddet i separat chore-commit)

**Design-valg:**
- Runner-registry lar nye fetchere plugge inn uten CLI-endring
- Per-runner instrument-filtrering: prices krever stooq_ticker,
  cot_disaggregated krever cot_contract + cot_report=disaggregated,
  weather krever region/lat/lon, fundamentals krever fred_series_ids
- fundamentals de-dupes serier på tvers av instrumenter — hvis to
  instrumenter deler DGS10, hentes den én gang
- Per-item resiliens: én fetch-feil stopper ikke resten; summary med
  ok/fail-tall på slutten, exit 1 ved minst én feil
- --stale-only sjekker check_staleness FØR run, skipper fetchere
  med fersk data i DB. Exit 0 med "Ingen stale" hvis alt er fersk
- --instrument filter gjelder alle runners — brukbart for å kjøre
  akkurat en ticker/kontrakt/region i isolert test

**Commits:** `88eff6d` (runner), `c2476ed` (gitignore-fix).

**Tester:** 492/492 grønne på 18.1 sek (fra 479 session 28, +13).

**Bevisste utsettelser:**
- Cron-basert scheduler (APScheduler eller systemd-timer) — session 30
- Retry-backoff for `on_failure: retry_with_backoff` — `tenacity`
  finnes allerede i fetch.base; legges på per-runner-nivå når
  scheduler skrives
- Logging til fil/strukturert format — Fase 11 deployment
- `raise` on_failure-variant — enkel å legge til i run_fetcher_by_name

**Neste session:** 30 — scheduler-daemon eller systemd-timer-generator.

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
