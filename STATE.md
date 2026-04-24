# Bedrock — state

## Current state

- **Phase:** 9 **ÅPEN** (UI: 4 faner + admin-editor). Struktureres som tre runder per bruker-beslutning 2026-04-24:
  - **Runde 1 (session 47-50):** minimal data-wiring per fane, funksjonelt null polish
  - **Runde 2 (session 51-53):** styling, flyt, filtrering, detaljmodaler
  - **Runde 3 (session 54-55):** admin-rule-editor på separat URL med kode-gate
- Session 47 lukket — Fane 1 Skipsloggen (KPI + trade-log-tabell).
- Session 48 lukket — Fane 2 Financial setups (kort-grid med grade/score-sortering).
- Session 49 lukket — Fane 3 Soft commodities (samme kort-grid; backend klar fra 48).
- Session 50 lukket — Fane 4 Kartrommet (pipeline-helse, gruppert per PLAN § 10.4). **Runde 1 LUKKET** — alle fire faner har funksjonell data-wiring.
- **Branch:** `main` (jobber direkte på main under utvikling, Nivå 1-modus)
- **Blocked:** nei
- **Next task:** **Runde 2 (sessions 51-53)** — styling, flyt, filtrering, detaljmodaler. Konkret scope for session 51 velges ved start:
  - **Option A (polish-først):** farger + typografi + header + visuell hierarki. Gir umiddelbar UX-vin.
  - **Option B (filter-først):** filter-bar på Skipsloggen (horizon/result/instrument) og setups-fanene (grade/instrument/direction). Funksjonell forbedring uten polish.
  - **Option C (modal-først):** klikk-på-rad/kort åpner detaljmodal med explain-trace/analog-matcher. Forutsetter at backend eksponerer denne informasjonen — må kartlegges.
- Runde 3 (sessions 54-55) er admin-rule-editor på separat URL med kode-gate.
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
