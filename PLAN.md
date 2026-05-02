# Bedrock — implementasjonsplan

Dato opprettet: 2026-04-23
Sist oppdatert: 2026-05-01
Status: Fase 0-11 fullført, Fase 12 åpen (sub-fase 12.5+/12.6/12.7/12.8 LUKKET — sub-fase 12.9 åpen, bedrock-bot cutover, se § 21)
Referanser: `NYTT_PROSJEKT_UTKAST.md` (i cot-explorer), `AGRI_KARTLEGGING.md` (i cot-explorer), fase-1-audit-rapport (i chat-logg).

## Endringshistorikk (etter initial godkjenning)

**2026-05-01 (sub-fase 12.9 åpning, session 139 fortsettelse):** Ny § 21
lagt til — "bedrock-bot cutover". Scalp_edge retires; bedrock-bot
(allerede 95% bygget per Fase 8) tar over som cTrader-grensesnitt.
D1 (signal-adapter + `/bot/signals`-endpoint) LANDET (`649f429`).
D2-D6 pending: refresh-token-flow, bot.yaml + secrets, systemd-service,
demo-test ≥24t, scalp_edge retire. Full operasjonell plan i
`docs/bedrock_bot_cutover.md`. cTrader-credentials lagt i
`~/.bedrock/secrets.env` (CTRADER_CLIENT_ID/CLIENT_SECRET/ACCESS_TOKEN/
REFRESH_TOKEN/ACCOUNT_ID — alle 5 ✓).

**2026-05-01 (planleggings-session, sub-fase 12.8):** Ny § 20 lagt til —
"Data-gjeld + cron-tuning + whitelist-revisjon". Sub-fase 12.6 LUKKET
(`v0.12.6-fase-12.6-LUKKET`) med Strategi 3. § 20.2 låser horisont-
bruk-prinsipper: samme datakilde har ulik bruksverdi per horisont
(M/S/Sc); coverage-rapport og whitelist-revisjon må kvalifisere per
(instrument × horisont), ikke aggregat. 4 sub-tasks (A1 kartlegging
session 139, A2 kode-fixer 140, B cron-tuning 141, C whitelist-
revisjon 142). Plan-S (§ 19.10) utsatt til 12.8 LUKKET.

**2026-04-30 (UI-refresh, session 137):** § 10 oppdatert fra "4 faner"
til "5 faner" og fane-navnene rettet for å matche faktisk innhold.
6 av 7 etapper levert (1d969ee, 943961f, 5b526c3, ba991e1, 04d9fea +
bug-log 56353c9):
- Fane-renaming: Skipsloggen→Handelslogg, Financial setups→Finans,
  Soft commodities→Agri, Sentiment→Markedspuls, Kartrommet→Datakilder.
- Setup-kort: horisont-pille + mini-score-bar + familie-mini-bars.
- Tre nye read-only-API: `/api/ui/system_health`, `/api/ui/risk_indicators`,
  `/api/ui/agri_weather`. Alle WAL-trygge under harvest.
- Admin: ny "Drivers"-fane + `GET /admin/drivers`-endpoint.
- Første mobile breakpoints i prosjektet (≤ 768px og ≤ 480px).
- Kjent bug logget: `aaii_sentiment.bull_bear_spread`-kolonne
  feilskrevet av fetcher (workaround i risk_indicators-endpoint).
- **Etappe 7 (Backtest-fane) ikke startet** — venter på harvest-session
  136-fullføring + analyzer-runde (session 137+).

**2026-04-28 (planleggings-session, sub-fase 12.7):** Ny § 19 lagt til —
"Horisont-refactor + data-utvidelse". To-spors plan godkjent etter audit
+ tre patcher fra bruker:
- **Spor R (R1-R4):** horisont-bevisst driver-arkitektur (Alt 1 — YAML-
  styrt `horizon`-param via engine-propagering av `_horizon` analogt med
  `_direction`). Score-uendret-garanti via snapshot-tester.
- **Spor D (D0-D3):** 12 nye fetchere + 5 utvidelser + 6 mapping-
  refaktorer organisert i tiers. **A14 Eskom DROPPED 2026-04-29 (D0):**
  bekreftet bak betalingsmur. **C2 Platinum mining_disruption→Eskom
  DROPPED:** Platinum beholder seismic uendret. GHS/XOF droppet helt —
  Cocoa cross blir `dxy@0.85 + event_distance@0.15`.
- **ADR-er:** ADR-009 (horisont-pattern, Alt 1) + ADR-010 (backfill-
  policy: 2010-cutoff, sekvensiell pacing 1.5s, engangs-skripts i
  `scripts/backfill/`, lov til å være "shitty"). ADR-011 (deprecation)
  + ADR-012 (failure-mode) bevisst utsatt — håndteres reaktivt per
  fetcher (Alt Z).
- **Scalp-arkitektur** (release-clock, surprise-z som schema-kontrakt,
  cross-asset-ledere, vol-regime-sizing) UTSATT til separat Plan-S
  etter D2.
- **Trading-logikk-svar:** percentil 12m+36m, ekstrem-terskler 2/98
  (hard) + 5/95 (soft), Cotton ENSO uendret.
- Sub-fase 12.7 koordineres med 12.6 (data-driven rebalansering) —
  rekkefølge er åpent spørsmål, se § 19 og STATE.md open questions.

**2026-04-27 (session 105 follow-up):** § 7.3 og § 7.4 utvidet:
- § 7.3 tabell fikk ny kolonne `systemd-timer?` som markerer
  faktisk system-deployment (skiller kode-nivå-runner fra
  installert timer). 9 av 10 ⚠ generert-ikke-installert.
- § 7.4 splittet i tre subsections: 7.4.1 runner-registry-
  mønster (kontrakt + responsibilities), 7.4.2 smart-schedule-
  prinsipper (TZ, stale_hours, off-:00/:30, conservative cadence,
  cron-konverter-funksjoner), 7.4.3 audit-funn fra session 105
  om generert vs installert + aksjonsplan til ADR-009.
- calendar_ff lagt til som 10. fetcher (eneste system-deployed).

**2026-04-27 (session 104):** Docs-cleanup etter audit:
- § 3.1 mappetre oppdatert til faktisk struktur (signal_server/ ikke server/,
  orchestrator/ ikke pipeline/+signals/, setups/hysteresis.py ikke persistence.py,
  drivers utvidet med agri/agronomy/currency/seasonal).
- § 3.2 dataflyt-diagram oppdatert (SQLite, ikke parquet).
- § 7.3 statuslinje: 6/8 live (var "5/8 live"-tekst i STATE.md).
- § 7.5 (ny) — roadmap for de 11 ikke-portede cot-explorer-fetcherne (sessions
  105-117). Strategi i ADR-007.
- § 11 + § 13 — eksplisitt notert at Fase 11 UI-fane er utsatt etter Fase 13.
- § 12 — sub-fase 12.5+ scope dokumentert.
- § 16 — Neste steg oppdatert til sessions 104-117.

**2026-04-26 (session 103):** § 7 utvidet:
- Ny § 7.4 dokumenterer runner-registry og full fetch-schedule (9 fetchere etter at WASDE/NASS/BDI er wiret + ENSO-runner-bug fixet).
- § 7.3 tabellen markerer nå hvilke kilder som har auto-fetcher vs manuell CSV.
- OnCalendar tolkes i lokal TZ — cron i fetch.yaml settes i lokal-tid (ikke UTC) slik at firing lander etter publisering.
- `cron_to_oncalendar` støtter range/list i dom + month for vekstsesong-aware schedules.

**2026-04-23:** Følgende beslutninger etter første utkast:
- § 5.4 omskrevet: dropp setup-persistence-som-lifecycle. Erstatt med generator-determinisme + hysterese + stabilitets-filtre. Enklere, mindre state.
- § 10 utvidet: UI-kode beskytter HELE dashboardet (ikke bare admin). Killswitch i UI-en når man er logget inn.
- § 15 avklart: **Flask** (ikke FastAPI). Frontend: **vanilla JS + Alpine.js-sprinkling**.
- § 7 tillagt: ubrukt-data-gjennomgang er Fase 10-oppgave.
- **Ny § 17:** Session-disiplin (start/end-protokoll, STATE.md, fase-gate-review).
- **Ny § 18:** Git-regler og commit-konvensjon.

---

## 1. Hva Bedrock skal være

Ett standalone prosjekt som samler markedsdata, genererer **asymmetriske trading-setups på reelle støtte/motstandsnivåer**, sender godkjente setups til cTrader-boten via signal_server, og viser bot-logg, setups og pipeline-helse i én UI. Prosjektet støtter analog-matching mot 10+ års historikk og er config-drevet slik at nye drivere/regler kan legges til uten kode-endringer.

Tre eksisterende kode-enheter konsolideres:
- `~/cot-explorer/` (data + scoring + dashboard)
- `~/scalp_edge/signal_server.py` (Flask-broker)
- `~/scalp_edge/trading_bot.py` (cTrader-klient)

---

## 2. Designprinsipper

1. **Konfigurasjon, ikke kode.** YAML bestemmer *hvilke* drivere og *hvilke* vekter. Python bestemmer *hvordan* hver driver beregner.
2. **Asymmetri er et mål.** Setup-generator leter aktivt etter asymmetriske entry-soner; R:R er output fra reelle nivåer, ikke en hardkodet multiplier.
3. **Reelle nivåer, ikke mekanisk ATR.** Entry/SL/TP plasseres relativt til faktiske swing-highs/lows, volume-profile-nivåer, ukentlig H/L, COT-pivoter. ATR brukes kun som buffer/margin.
4. **Setup-persistens.** SWING og MAKRO setups har ID og lever på tvers av pipeline-kjøringer. Oppdateres, erstattes ikke (med mindre genuint invalide).
5. **Per-instrument scoring.** Hver instrument har egen YAML-regel som arver fra en asset-klasse-default.
6. **Bevare alle fetch-ressurser.** Ingen datakilder fjernes. Om scoring ikke bruker dem, ligger de tilgjengelig for analog, UI og fremtidige regler.
7. **Én motor, to aggregatorer.** `weighted_horizon` (financial) og `additive_sum` (agri). Ny asset-klasse kan få tredje aggregator uten ny motor.
8. **Test-drevet fra dag én.** Logiske tester (gitt X-data → forvent Y-signal) fremfor implementasjonstester. Snapshot-filer + property-tester + backtest på historikk.
9. **YAML har ingen logikk.** Ingen uttrykk, ingen `eval`, ingen betingelser. Bare navn, parametre, vekter.
10. **Public repo.** Hemmeligheter i `~/.bedrock/secrets.env`. Ingen API-nøkler, ingen kill-switch-endepunkter eksponert i UI.

---

## 3. Arkitektur-oversikt

### 3.1 Mappestruktur

```
bedrock/
├── README.md
├── pyproject.toml                  # uv + Python 3.12
├── .env.example                    # dokumenter alle env-vars
│
├── config/                         # ← konfigurasjon, ikke kode
│   ├── defaults/
│   │   ├── base.yaml               # globale defaults (horisonter, R:R-min, stale-terskler)
│   │   ├── family_financial.yaml   # weighted_horizon-aggregator + default family-vekter
│   │   └── family_agri.yaml        # additive_sum-aggregator + default bidrag
│   ├── instruments/
│   │   ├── gold.yaml               # per-instrument-regler (arver fra defaults)
│   │   ├── eurusd.yaml
│   │   ├── brent.yaml
│   │   ├── corn.yaml
│   │   ├── coffee.yaml
│   │   └── ...                     # én pr instrument (16 financial + 7 agri = 23 filer)
│   ├── fetch.yaml                  # cadence + stale + kilder per fetch-modul
│   ├── bot.yaml                    # alle hardkodede thresholds fra trading_bot.py
│   └── pipeline.yaml               # rekkefølge + timers
│
├── src/bedrock/                    # Python-pakke
│   ├── engine/                     # scoring-motor
│   │   ├── __init__.py
│   │   ├── engine.py               # hovedklasse Engine.score(instrument, data, rules)
│   │   ├── aggregators.py          # weighted_horizon + additive_sum
│   │   ├── drivers/                # driver-registry
│   │   │   ├── __init__.py         # @register-dekorator
│   │   │   ├── trend.py            # sma_align, momentum, etc.
│   │   │   ├── positioning.py      # cot_mm_pct, divergence, etc.
│   │   │   ├── macro.py            # dxy_trend, vix_regime, etc.
│   │   │   ├── fundamental.py      # fred_composite, conab_momentum, etc.
│   │   │   ├── structure.py        # level_proximity, sweep_detected
│   │   │   ├── risk.py             # event_distance, geo_alert
│   │   │   └── analog.py           # k_nearest_outcome
│   │   ├── grade.py                # grade-logikk (A+/A/B/C) fra YAML-terskler
│   │   └── explain.py              # trace hva som bidro til score
│   │
│   ├── engine/drivers/             # driver-registry (faktisk struktur per session 103)
│   │   ├── __init__.py             # @register-dekorator
│   │   ├── trend.py                # sma200_align, momentum_z
│   │   ├── positioning.py          # positioning_mm_pct, cot_z_score
│   │   ├── macro.py                # real_yield, dxy_chg5d, brl_chg5d, vix_regime
│   │   ├── structure.py            # range_position
│   │   ├── risk.py                 # vol_regime
│   │   ├── analog.py               # analog_hit_rate, analog_avg_return
│   │   ├── agri.py                 # weather_stress, enso_regime
│   │   ├── agronomy.py             # crop_progress_stage, wasde_s2u_change,
│   │   │                           # export_event_active, disease_pressure,
│   │   │                           # bdi_chg30d, igc_stocks_change
│   │   ├── currency.py             # currency_cross_trend
│   │   ├── seasonal.py             # seasonal_stage
│   │   └── _stats.py               # interne statistikk-helpers
│   │
│   ├── setups/                     # setup-generator (NY kritisk komponent)
│   │   ├── __init__.py
│   │   ├── levels.py               # reelle-nivåer-detektor (swing, POC, W/D H/L, round)
│   │   ├── generator.py            # finn asymmetriske setups rundt nivåer
│   │   ├── hysteresis.py           # determinisme + hysterese (revidert § 5.4)
│   │   ├── snapshot.py             # last_run.json som "forrige tilstand"
│   │   └── horizon.py              # horisont fra setup-karakteristikk, ikke score
│   │
│   ├── data/                       # datalag (SQLite, ADR-002)
│   │   ├── store.py                # DataStore over sqlite3 + pandas
│   │   ├── schemas.py              # pydantic + DDL for tabeller
│   │   └── analog.py               # find_analog_cases (K-NN, ADR-005)
│   │
│   ├── fetch/                      # rå I/O (ingen scoring) — faktisk per session 103
│   │   ├── base.py                 # felles retry/logging/stale-sjekk
│   │   ├── cot_cftc.py             # CFTC disaggregated + legacy
│   │   ├── prices.py               # legacy stooq-port (deprecated etter session 58)
│   │   ├── yahoo.py                # default pris-fetcher (ADR-005-followup)
│   │   ├── fred.py                 # FRED fundamentals
│   │   ├── weather.py              # ERA5-vær + agri_history månedlig
│   │   ├── enso.py                 # NOAA ONI (session 57)
│   │   ├── wasde.py                # USDA WASDE ESMIS-XML (sessions 85, 87)
│   │   ├── nass.py                 # USDA NASS QuickStats (sessions 97-98)
│   │   ├── manual_events.py        # eksport-events, disease, BDI/BDRY
│   │   └── usda_calendar.py        # USDA-blackout-gate (session 27)
│   │   # -- portes i sub-fase 12.5+ (sessions 105+):
│   │   #   calendar_ff.py, eia_inventories.py, cot_ice.py, comex.py,
│   │   #   seismic.py, news_intel.py, conab.py, unica.py,
│   │   #   cot_euronext.py, shipping.py, crypto_sentiment.py
│   │
│   ├── signal_server/              # refaktor av signal_server.py (Fase 7, ny navn)
│   │   ├── app.py                  # Flask
│   │   ├── endpoints/              # routes splittet per domene
│   │   ├── schemas.py              # Pydantic (låst v1 + extras)
│   │   └── storage.py              # in-memory + disk-persistering
│   │
│   ├── bot/                        # refaktor av trading_bot.py
│   │   ├── __main__.py             # entry-point + CLI (--demo/--live)
│   │   ├── ctrader_client.py       # Twisted + Protobuf-lag
│   │   ├── state.py                # TradeState, CandleBuffer, TradePhase
│   │   ├── entry.py                # 3-punkts bekreftelse + alle entry-gates
│   │   ├── exit.py                 # P1-P5 exit-logikk
│   │   ├── sizing.py               # risk% + lot-tier
│   │   ├── safety.py               # daily_loss + kill + server-frozen
│   │   ├── comms.py                # signal_server-polling
│   │   ├── config.py               # bot.yaml-loader
│   │   └── instruments.py          # instrument-mapping
│   │
│   ├── orchestrator/               # signal-pipeline (erstatter PLAN-original pipeline/+signals/)
│   │   ├── signals.py              # generate_signals + score_instrument (Fase 5)
│   │   └── (publisher folded inn i CLI signals_all)
│   │
│   ├── parallel/                   # compare/monitor for parallell-drift (Fase 12)
│   │
│   ├── backtest/                   # Fase 11 — replay + compare
│   │   ├── runner.py               # outcome-replay + orchestrator-replay
│   │   ├── compare.py              # signal-diff (session 65)
│   │   └── report.py               # markdown + JSON
│   │
│   ├── systemd/                    # generator + installer for timer/service
│   │   └── generator.py            # cron_to_oncalendar + install
│   │
│   ├── config/                     # YAML-lasting + driver-runner-registry
│   │   ├── fetch_runner.py         # @register_runner-dispatcher (session 103)
│   │   └── secrets.py              # ~/.bedrock/secrets.env-loader
│   │
│   └── cli/                        # kommandolinje-verktøy
│       ├── __main__.py             # `bedrock` command
│       ├── backfill.py             # `bedrock backfill prices/cot/...`
│       ├── backtest.py             # `bedrock backtest run/compare`
│       ├── fetch.py                # `bedrock fetch run <name>`
│       ├── instruments.py          # `bedrock instruments list/show`
│       ├── server.py               # `bedrock server` (waitress + Flask-fallback)
│       ├── signals.py              # `bedrock signals <instrument>`
│       ├── signals_all.py          # `bedrock signals-all` (alle 22 inst → JSON)
│       └── systemd.py              # `bedrock systemd generate/install/list`
│
├── web/                            # statisk frontend (GitHub Pages)
│   ├── index.html                  # 4 faner (Skipsloggen / Financial / Soft commodities / Kartrommet)
│   ├── admin.html                  # separat rule-editor (kode-beskyttet)
│   ├── assets/
│   └── data/                       # symlink til publisert JSON
│
├── data/                           # kjøredata (gitignored større deler)
│   ├── bedrock.db                  # SQLite (ADR-002) — alle tidsserier i tabeller
│   ├── signals.json                # financial setups (90 entries, 22 inst)
│   ├── agri_signals.json           # agri setups (42 entries, splittet session 94)
│   ├── signals_bot.json            # bot-only whitelist-output (session 92)
│   ├── setups/last_run.json        # hysterese-snapshot (Fase 4 § 5.4)
│   ├── signal_log.json             # ETT sted. Bot skriver her. Ingen kopiering.
│   ├── manual/                     # manuelle CSVer (eksport-events, disease)
│   └── _meta/                      # pipeline_health + signal-diff baseline
│
├── systemd/                        # versjonerte timer/service-filer (per session 103)
│   ├── bedrock-fetch-prices.{timer,service}
│   ├── bedrock-fetch-cot_disaggregated.{timer,service}
│   ├── bedrock-fetch-cot_legacy.{timer,service}
│   ├── bedrock-fetch-fundamentals.{timer,service}
│   ├── bedrock-fetch-weather.{timer,service}
│   ├── bedrock-fetch-enso.{timer,service}
│   ├── bedrock-fetch-wasde.{timer,service}
│   ├── bedrock-fetch-crop_progress.{timer,service}
│   ├── bedrock-fetch-bdi.{timer,service}
│   ├── bedrock-signals-all.{timer,service}    # daglig signal-generering
│   ├── bedrock-server.service                 # 24/7 UI (session 93)
│   ├── bedrock-monitor.{timer,service}        # pipeline-helse 06:30
│   └── bedrock-compare.{timer,service}        # signal-diff vs cot-explorer 06:35
│
├── tests/
│   ├── logical/                    # "gitt X → forvent Y"-tester (hoved-testsuite)
│   │   ├── test_scoring_scenarios.py
│   │   ├── test_setup_generator.py
│   │   ├── test_horizon_assignment.py
│   │   ├── test_rr_calculation.py
│   │   └── test_explain.py
│   ├── snapshot/                   # golden-file-tester
│   │   ├── fixtures/               # historisk input-data
│   │   └── expected/               # forventet output (committes)
│   ├── backtest/                   # regel-impact-tester på historikk
│   │   └── test_rules_v1_vs_v2.py
│   ├── integration/                # full-pipeline-tester
│   │   └── test_end_to_end.py
│   └── unit/                       # små komponent-tester
│       ├── test_drivers.py
│       ├── test_aggregators.py
│       └── test_data_store.py
│
└── docs/
    ├── architecture.md
    ├── data_contract.md            # signal-schema v1 + extras
    ├── rule_authoring.md           # hvordan skrive ny YAML-regel
    ├── driver_authoring.md         # hvordan skrive ny driver (Python)
    ├── backfill.md                 # hvordan backfille historikk
    ├── runbook.md                  # incident playbook
    └── decisions/                  # ADR-format for arkitektur-valg
```

### 3.2 Dataflyt

```
    fetch/*                    setups/                 engine/                  orchestrator/
    (rå I/O)                   (generator)             (scoring)                (publisering)
        │                          │                       │                          │
        ▼                          ▼                       ▼                          ▼
  data/bedrock.db           data/setups/last_run.json (in-memory GroupResult)  data/signals.json
  (SQLite-tabeller)              ▲                       ▲                  data/agri_signals.json
        │                        │                       │                  data/signals_bot.json
        └──► data/analog.py ◄────┘                       │                          │
                                                         │                          ▼
                                                  config/instruments/*.yaml   signal_server /push-alert
                                                  config/defaults/*.yaml            │
                                                  drivers/*.py                      ▼
                                                                              bot polls /signals
                                                                                      │
                                                                                      ▼
                                                                              cTrader execution
                                                                                      │
                                                                                      ▼
                                                                           data/signal_log.json
```

---

## 4. Scoring-motoren

### 4.1 Prinsipp

Én `Engine`-klasse. Én metode `engine.score(instrument_id, data, rules) → GroupResult`. Internt:

1. Les `rules.aggregation` → velg aggregator (`weighted_horizon` | `additive_sum`)
2. For hver familie i `rules.families`:
   - For hver driver i familien:
     - Slå opp Python-funksjonen i registry ved navn
     - Kjør funksjonen med `data` + `params` → float 0-1
     - Multiplier med driver-vekt
   - Aggregert familie-score
3. Aggregator kombinerer familie-scores → total score
4. Grade-logikk med terskler fra `rules.grade_thresholds` → A+/A/B/C
5. Returner `GroupResult` med total, per-familie, per-driver, og full explain-trace

### 4.2 Eksempel-YAML — Gold (financial)

```yaml
# config/instruments/gold.yaml
inherits: family_financial
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  cfd_ticker: Gold

aggregation: weighted_horizon

horizons:                                # horisont-spesifikke vekt-sett
  SCALP:
    family_weights: {trend: 1.2, positioning: 0.5, macro: 0.7, fundamental: 0.5, structure: 1.3, risk: 0.8}
    max_score: 5.0
    min_score_publish: 1.5
  SWING:
    family_weights: {trend: 1.0, positioning: 1.0, macro: 1.0, fundamental: 1.0, structure: 1.0, risk: 1.0}
    max_score: 6.0
    min_score_publish: 2.5
  MAKRO:
    family_weights: {trend: 0.8, positioning: 1.3, macro: 1.3, fundamental: 1.3, structure: 0.5, risk: 0.8}
    max_score: 5.9
    min_score_publish: 3.5

families:
  trend:
    drivers:
      - {name: sma200_align,     weight: 0.4, params: {tf: D1}}
      - {name: momentum_z,       weight: 0.3, params: {window: 20}}
      - {name: d1_4h_congruence, weight: 0.3}
  positioning:
    drivers:
      - {name: cot_mm_percentile, weight: 0.5, params: {lookback_weeks: 52}}
      - {name: cot_commercial_z,  weight: 0.3}
      - {name: oi_regime,         weight: 0.2}
  macro:
    drivers:
      - {name: real_yield_change, weight: 0.4, params: {series: DGS10, horizon: 5d}}
      - {name: dxy_momentum,      weight: 0.3, params: {horizon: 5d}}
      - {name: vix_regime_bias,   weight: 0.3, params: {bull_in: [normal, elevated], bear_in: [extreme]}}
  fundamental:
    drivers:
      - {name: gold_silver_zscore, weight: 0.4}
      - {name: comex_stress,       weight: 0.3}
      - {name: fred_composite,     weight: 0.3, params: {composite: metals_risk}}
  structure:
    drivers:
      - {name: level_proximity,      weight: 0.7, params: {max_distance_atr: 1.0}}
      - {name: htf_smc_confirmation, weight: 0.3}
  risk:
    drivers:
      - {name: event_distance,    weight: 0.5, params: {calendar_impact: high, min_hours: 4}}
      - {name: correlation_gate,  weight: 0.5}

grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 4}
  A:      {min_pct_of_max: 0.55, min_families: 3}
  B:      {min_pct_of_max: 0.35, min_families: 2}

gates:                                   # kapping ved bestemte forhold
  - {when: "event_distance < 3h",       cap_grade: A}
  - {when: "data_quality = stale",      cap_grade: B}
```

### 4.3 Eksempel-YAML — Corn (agri)

```yaml
# config/instruments/corn.yaml
inherits: family_agri
instrument:
  id: Corn
  asset_class: grains
  ticker: ZC
  cfd_ticker: Corn

aggregation: additive_sum
max_score: 18
min_score_publish: 7                     # ~39 % av max

families:
  outlook:
    weight: 5                            # familie kan gi opp til 5 poeng
    drivers:
      - {name: weather_outlook, weight: 1.0, params: {regions: [us_cornbelt, brazil_mato_grosso]}}
  yield:
    weight: 3
    drivers:
      - {name: yield_score_crop, weight: 1.0, params: {crop: Corn}}
  weather:
    weight: 2
    drivers:
      - {name: regional_stress, weight: 1.0, params: {regions: [us_cornbelt]}}
  enso:
    weight: 2
    drivers:
      - {name: enso_bias_grains, weight: 1.0}
  conab:
    weight: 2
    drivers:
      - {name: conab_crop_momentum, weight: 1.0, params: {crop: milho}}
  cross:
    weight: 2
    drivers:
      - {name: cross_confirm, weight: 1.0, params: {signals: [yield, conab_yoy]}}

grade_thresholds:
  A_plus: {min_score: 14, min_families_active: 4}
  A:      {min_score: 10, min_families_active: 3}
  B:      {min_score: 7,  min_families_active: 2}

usda_blackout:                           # agri-spesifikk gate
  pre_hours: 3
  post_hours: 3
  sources: [WASDE, crop_progress, grain_stocks]
```

### 4.4 Driver-kontrakt (Python)

```python
# src/bedrock/engine/drivers/trend.py
from bedrock.engine.drivers import register
from bedrock.data.store import DataStore

@register("sma200_align")
def sma200_align(store: DataStore, instrument: str, params: dict) -> float:
    """
    Returnerer 0-1 for om prisen er over SMA200 på gitt TF.
    0 = under SMA, 1 = over SMA, mellom = svakt bekreftet.
    """
    tf = params.get("tf", "D1")
    prices = store.get_prices(instrument, tf=tf, lookback=250)
    sma = prices.rolling(200).mean().iloc[-1]
    close = prices.iloc[-1]
    if close > sma * 1.01: return 1.0
    if close > sma:        return 0.6
    if close > sma * 0.99: return 0.4
    return 0.0
```

Regler i stein:
- Signatur er alltid `(store, instrument, params) → float`
- Returnerer 0-1 (eller -1 til 1 for bi-direksjonale drivere)
- Ingen side-effekter
- Feil → return 0.0 og logg (ikke kast)
- Deterministisk for samme input

### 4.5 Explain / traceability

Hvert Signal inneholder full `explain`-trace:

```json
{
  "signal_id": "sig_abc123",
  "score": 3.45,
  "grade": "A",
  "explain": {
    "aggregation": "weighted_horizon",
    "horizon": "SWING",
    "families": {
      "trend": {
        "weight": 1.0, "score": 0.75,
        "drivers": [
          {"name": "sma200_align", "value": 1.0, "weight": 0.4, "contribution": 0.4},
          {"name": "momentum_z",   "value": 0.6, "weight": 0.3, "contribution": 0.18},
          {"name": "d1_4h_congruence", "value": 1.0, "weight": 0.3, "contribution": 0.3}
        ]
      },
      "positioning": { ... }
    },
    "gates_triggered": [],
    "grade_rule": "A (>=0.55 pct of max, 4 families active)"
  }
}
```

CLI-kommando: `bedrock explain sig_abc123` printer dette lesbart.

---

## 5. Setup-generator — reelle nivåer

**Den mest kritiske nye komponenten.** Dette er der "super små TP-er"-problemet løses. Det nye systemet har to uavhengige steg:

1. **Finn reelle nivåer** i historikk/nå-situasjon
2. **Bygg asymmetriske setups** på disse nivåene

### 5.1 Nivå-detektor

`src/bedrock/setups/levels.py`. Inputs fra data-lager. Outputs: rangert liste av nivåer med type, styrke og "siste gang testet":

| Nivå-type | Beregning | Styrke-signal |
|---|---|---|
| Swing high/low | Fraktal på N-candles (configurerbar per TF) | Antall tester, alder |
| Volume-profile POC/VAH/VAL | Session/daglig volum-distribusjon | Volum-konsentrasjon |
| Prior weekly/daily H/L | Direkte fra OHLC | Kjent institusjonelt nivå |
| Monthly H/L | Direkte fra OHLC | HTF |
| Round numbers | Psykologisk (1.0900, 2000, 100, ...) | Avstand til hele tall |
| Prior COT-pivot | Pris der MM-percentile vendte | COT-historikk |
| ATR-bånd | Kun som buffer-mål, ikke selvstendig nivå | — |

Hvert nivå får en `strength_score` 0-1 (styrke, nylighet, vektet kombinasjon), og `type`-tagg slik at setup-generatoren kan velge.

**Historikk-avhengighet:** nivå-detektor bruker parquet-lag (`data/parquet/prices/`) for å finne swing-highs/lows langt bakover — derfor er DuckDB-backfill premisset for denne komponenten.

### 5.2 Setup-bygger

For hvert instrument + retning (BUY/SELL), gitt en score fra engine:

1. Hent relevante nivåer i nærheten av nåpris
2. For hver horisont (SCALP/SWING/MAKRO) separat:
   - **Entry-sone:** lag en zone ved nærmeste sterke nivå *bak* nåpris (BUY: nærmeste støtte; SELL: nærmeste motstand)
   - **SL:** litt under/over nivået (buffer = `k × ATR` per instrument, default 0.3)
   - **TP per horisont:**
     - **SCALP:** neste nivå i retningen (typisk 1-2 nivåer unna)
     - **SWING:** 2. eller 3. nivå i retningen — må gi R:R ≥ `min_rr_swing`, ellers forkast horisonten for dette instrumentet
     - **MAKRO:** **ingen TP — kun trailing**. Entry og SL settes; boten tråler etter første tegn på trend-brudd
3. Beregn R:R for hvert kandidat-setup; rangér etter asymmetri
4. Forkast setups som ikke kan finne et TP-nivå som gir asymmetrisk R:R

### 5.3 Asymmetri-krav per horisont

**Ikke mekanisk** — dvs. R:R kommer fra *reelle nivåer*, ikke fra en mal. Men en minimum-floor eksisterer:

| Horisont | Min R:R | Kommentar |
|---|---|---|
| SCALP | 1:1.5 | Minste akseptable |
| SWING | 1:2.5 | Under dette: forkast SWING for dette instrumentet |
| MAKRO | N/A (trailing) | Asymmetrien kommer fra trailing-faktoren, ikke fast TP |

Disse lever i `config/defaults/base.yaml` og kan overstyres per-instrument.

### 5.4 Generator-determinisme og konsistens (tidligere: setup-persistens)

**Problemet du flagget:** MAKRO/SWING-setups byttes ut hver 4. time → inkonsistent.

**Revidert løsning (2026-04-23):** ikke lifecycle-tracking. I stedet:
**deterministisk generator + hysterese + stabilitets-filtre.** Samme input → samme
output, små input-endringer flipper ikke horisont eller entry.

**Tre mekanismer:**

1. **Deterministisk output.** Ingen tilfeldighet, ingen rekkefølge-avhengighet,
   ingen tid-avhengige seed-er. Generator tar `(data, rules, context)` inn og
   returnerer eksakt samme setup-liste uansett hvor mange ganger den kjøres.

2. **Hysterese på horisont-tildeling.** Score-terskler har buffer-sone (typisk
   ±5 %). Hvis nåværende score er innenfor bufferen rundt en horisont-terskel,
   beholdes forrige horisont. Hindrer flip-flopping mellom SWING og SCALP når
   score svinger rundt 2.5.

3. **Stabilitets-filtre på nivå-valg.**
   - Hvis nytt SL-nivå ligger innenfor `k × ATR` av forrige SL, behold forrige
     (default k=0.3)
   - Hvis nytt TP-nivå er innenfor `k × ATR` av forrige TP, behold forrige
     (default k=0.5)
   - Kun regenerer SL/TP når reelt bedre nivå dukker opp

**Implementasjon:**
- Siste kjøring-snapshot lagres i `data/setups/last_run.json` (kun som "forrige
  tilstand", ikke som lifecycle-objekt)
- Generator sammenligner sitt output mot siste snapshot og anvender hysterese-reglene
- Hvis setup er stabil → samme ID beholdes (for UI-kontinuitet og log-sammenheng)
- Ingen eksplisitt "watchlist → triggered → active → closed"-state i
  setup-generatoren. Bot har sin egen state-maskin per åpne trade.

**Konsekvens for bot:** boten har ingen endring — den får samme signal-schema som
før, bare at signal-id-en forblir stabil mellom kjøringer når setupen er uendret.

Fordeler vs opprinnelig lifecycle-forslag:
- Null risiko for zombie-setups (ingenting "holdes kunstig i live")
- Mindre state å vedlikeholde og debugge
- Atferden er lettere å teste — du kan forutsi output fra input alene
- Konsistens kommer fra determinisme, ikke fra state-mutasjon

### 5.5 Horisont-tildeling

Horisont kommer fra **setup-karakteristikk**, ikke fra score.

```
Horizon classifier:
  entry_tf = 15m → SCALP
  entry_tf = 4h/1D, expected_hold = 7-21d → SWING
  entry_tf = 1D/W, expected_hold = 30-90d → MAKRO

Score validerer at condition støtter den horisonten:
  SWING krever score >= swing_threshold AND aktive POSITIONING/MACRO/FUNDAMENTAL
  MAKRO krever enda sterkere fundamental + strukturell konsensus
```

Scoring-YAML har `min_score_publish` per horisont; setup-generator respekterer det.

---

## 6. Historisk data-lag

### 6.1 Valg: SQLite + pandas (revidert 2026-04-24, ADR-002)

**Revidert fra DuckDB+parquet** — se ADR-002. Produksjons-hardwaren (Pentium
T4200, 2008) mangler SSE4.2/AVX og klarer ikke kjøre binær-wheels for
`duckdb` eller `pyarrow`/`fastparquet`. `Illegal instruction`-krasj ved
import.

**Nytt valg:** SQLite via Python stdlib `sqlite3`, pandas-native lesing
(`pd.read_sql`), én `.db`-fil på disk. Ingen eksterne tjenester, null
SIMD-avhengighet, bygget inn i Python selv.

**Migreringsvei til DuckDB+parquet** hvis hardware oppgraderes: endags-
jobb, kun `bedrock.data.store` endres. Drivere og Engine ser ikke
endringen (samme `DataStoreProtocol`).

### 6.2 Skjema

Én SQLite-database: `data/bedrock.db`. Tabeller:

```
prices:              [instrument, tf, ts, open, high, low, close, volume]
                     PK (instrument, tf, ts)

cot_disaggregated:   [report_date, contract, mm_long, mm_short, other_long,
                      other_short, comm_long, comm_short, nonrep_long,
                      nonrep_short, open_interest]
                     PK (report_date, contract)
                     CFTC 2010-present (managed money / other / commercial /
                     non-reportable)

cot_legacy:          [report_date, contract, noncomm_long, noncomm_short,
                      comm_long, comm_short, nonrep_long, nonrep_short,
                      open_interest]
                     PK (report_date, contract)
                     CFTC 2006-present (non-commercial / commercial /
                     non-reportable). Brukes for kontrakter uten
                     disaggregated-rapport, og for historikk før 2010.

fundamentals:        [series_id, date, value]
                     PK (series_id, date)
                     FRED-stil tidsserier. `value` er NULL-able (FRED
                     rapporterer ofte missing observations).

weather:             [region, date, tmax, tmin, precip, gdd]
                     PK (region, date)
                     Daglige region-observasjoner. Alle målinger
                     valgfrie (noen kilder gir kun tmax/tmin).

fundamentals:  [series_id, date, value]
               PK (series_id, date)  -- Fase 2 session 7+

weather:       [region, date, tmax, tmin, precip, gdd]
               PK (region, date)  -- Fase 2 session 7+

trades:        [ts, signal_id, entry, exit, pnl_r, ...]
               PK (signal_id)  -- Fase 2 session 7+
```

DDL-konstanter lever i `bedrock.data.schemas` (Pydantic-modeller + rå DDL).
Pydantic validerer rader før skriving; DDL oppretter tabell ved
`DataStore.__init__`.

### 6.3 API

```python
store = DataStore(db_path="data/bedrock.db")

# Fase 2 session 6 (implementert):
prices = store.get_prices("Gold", tf="D1", lookback=250)   # pd.Series indeksert på ts
store.append_prices("Gold", "D1", df)                      # INSERT OR REPLACE på PK

# Fase 2 session 7 (implementert):
cot = store.get_cot("GOLD", report="disaggregated", last_n=104)   # pd.DataFrame
store.append_cot_disaggregated(df)
store.append_cot_legacy(df)   # for kontrakter uten disaggregated

# Fase 2 session 8 (implementert):
fund = store.get_fundamentals("DGS10", last_n=120)            # pd.Series (value indeksert på date)
weather = store.get_weather("us_cornbelt", last_n=90)         # pd.DataFrame (tmax/tmin/precip/gdd)
store.append_fundamentals(df)
store.append_weather(df)

# Fase 2 senere sessions:
# (ingen flere getters planlagt i Fase 2 — trades.parquet venter til bot-refaktor i Fase 8)

# Analog-søk (Fase 10):
neighbors = store.find_analog_cases(
    instrument="Gold",
    query_dims={"vix": 22, "dxy_chg5d": -1.5, "real_yield": 0.8, "cot_pct": 12},
    k=5,
    dim_weights={"vix": 0.3, "dxy_chg5d": 0.3, "real_yield": 0.2, "cot_pct": 0.2}
)
# Returns list of (historic_date, similarity_score, forward_return_30d, forward_return_90d)
```

**Driver-kontrakt uendret:** `get_prices(instrument, tf, lookback) -> pd.Series`
er den samme Fase-1-signaturen som `InMemoryStore` (slettet i session 6)
brukte. Drivere trenger ingen endring.

### 6.4 Backfill

- **Priser:** 10 år fra stooq/Yahoo (2016-). CLI: `bedrock backfill prices --instruments all --from 2016`
- **CFTC COT:** 2010- (disaggregated), 2006- (legacy). Allerede samlet delvis, fyll hull.
- **FRED:** 10 år tilbake per serie.
- **ERA5-vær:** 15 år (du har).
- **Conab/UNICA:** så langt API-ene rekker (5-10 år).

Kjøres én gang ved prosjekt-oppsett, deretter kun inkrement per pipeline-kjøring.

### 6.5 Analog-matching — første versjon

Per asset-klasse ulik dimensjons-liste (valgt med grep på det som faktisk har prediktiv verdi i historikken):

- **Metals (Gold/Silver):** `vix_regime`, `real_yield_chg5d`, `dxy_chg5d`, `cot_mm_pct`
- **FX:** `rate_differential_chg`, `vix_regime`, `dxy_chg5d`, `term_spread`
- **Energy (Oil):** `backwardation`, `supply_disruption_level`, `dxy_chg5d`, `cot_commercial_pct`
- **Grains:** `weather_stress_key_region`, `enso_regime`, `conab_yoy`, `dxy_chg5d`
- **Softs:** `weather_stress`, `enso_regime`, `unica_mix_change`, `brl_chg5d`

K=5 default. Similarity = weighted Euclidean på normaliserte dimensjoner.

Output per signal: "N historisk matcher, Y av N steg >3 % innen 30d, snitt +X%". Levert som egen `analog` driver-familie i scoring, og som narrative i UI.

---

## 7. Fetch-laget

### 7.1 Alle eksisterende fetch-moduler beholdes

Inkludert `seismic` og `intel` — prinsipp 6. De kjører i følge cadence, skriver til både `data/latest/` og `data/parquet/`. Om scoring ikke referer dem, er det greit — de er i dashboardet og tilgjengelig for fremtidig driver.

### 7.2 Config-drevet cadence

`config/fetch.yaml` erstatter den store if/else-matrisen i `update.sh`:

```yaml
fetchers:
  cot_cftc:
    module: bedrock.fetch.cot_cftc
    cron: "0 0 * * 6"                # lør 00:00
    stale_hours: 168                 # ukentlig
    on_failure: log_and_skip
  prices:
    module: bedrock.fetch.prices
    cron: "40 * * * 1-5"             # hverdager hver time :40
    stale_hours: 2
    on_failure: retry_with_backoff
  ...
```

Pipeline-runner leser yaml, orkestrerer. Ingen shell-if-else.

### 7.3 Nye datakilder (gaps fra AGRI_KARTLEGGING.md pkt 9)

Alle viktige per dine ord. Implementeres i faser (se § 13).

**Status etter session 110:** 6 av 8 har auto-fetcher (live), 1 manuell CSV
sample, 1 betalt/manuell import. ICE softs COT er live via `cot_disaggregated`-
runneren; ICE Brent/Gasoil/TTF har egen full COT-fetcher fra session 106 — se § 7.5.

`Auto-fetcher?`-kolonnen markerer om vi har en `register_runner`-implementasjon
(kode-nivå). `systemd-timer?`-kolonnen markerer om timer-unit faktisk er
installert (system-nivå). Audit i session 107 avdekket at session 105's audit
var ufullstendig — den så kun i `/etc/systemd/system/` og misset 8 user-timers
i `~/.config/systemd/user/`. Korrigert status under viser at alle timers er
installert (system eller user); se § 7.4.3 for full splittstatus.

| Kilde | Hva | Implementering | Fase | Auto-fetcher? | systemd-timer? |
|---|---|---|---|---|---|
| USDA WASDE | Ending stocks, yield-prognoser, S2U | XML-parser fra ESMIS (sessions 85, 87) + manuell CSV-fallback | 4 | Ja (`wasde`-runner, session 103) | ✅ installert (user-timer) |
| USDA Crop Progress | % planted/silked/harvested ukentlig | NASS QuickStats API (session 97-98) | 4 | Ja (`crop_progress`-runner, session 103) | ✅ installert (user-timer) |
| Eksport-policy-tracker | India/Indonesia/Ivory Coast-hendelser | Manuell CSV (`export_events`) | 5 | Nei (manuell CSV) | N/A (manuell) |
| BRL/USD aktivt drivet | Pris-feed + som driver for softs | DEXBZUS via FRED (session 80) | 4 | Ja (gjennom `fundamentals`-runner) | ✅ installert (user-timer) |
| Baltic Dry til agri | Kobling BDI → grain-eksport-pris | BDRY ETF via Yahoo (session 89) | 5 | Ja (`bdi`-runner, session 103) | ✅ installert (user-timer) |
| Disease/pest-varsling | Coffee rust, wheat stripe rust | Manuell CSV (`disease_alerts`) | 6 | Nei (manuell CSV) | N/A (manuell) |
| ICE softs COT | Sukker/kaffe-spesifikk via CFTC | Finnes via `cot_disaggregated` | 4 | Ja (gjennom `cot_disaggregated`) | ✅ installert (user-timer) |
| ICE Brent/Gasoil/TTF COT | EU-basert energy-COT | ICE COTHist*.csv (session 106) | 12.5+ | Ja (`cot_ice`-runner, session 106) | ✅ installert (system-timer) |
| IGC rapporter | International Grains Council | Månedlig PDF-parse (session 84) | 5 | Nei (manuell import) | N/A (manuell) |
| NOAA ONI (ENSO) | El Niño / La Niña-regime | NOAA-ASCII (session 57) | 4 | Ja (`enso`-runner, session 103) | ✅ installert (user-timer) |
| Forex Factory kalender | High/medium-impact econ events | JSON via faireconomy.media (session 105) | 12.5+ | Ja (`calendar_ff`-runner, session 105) | ✅ installert (system-timer) |
| EIA weekly inventories | Crude/Gasoline/Nat Gas Storage | EIA Open Data v2 (session 107) | 12.5+ | Ja (`eia_inventories`-runner, session 107) | ✅ installert (user-timer) |
| COMEX warehouse | Gold/Silver/Copper supply-stress | metalcharts.org JSON (session 108) | 12.5+ | Ja (`comex`-runner, session 108) | ✅ installert (user-timer) |
| USGS seismic | M≥4.5 events i mining-regions | USGS GeoJSON feed (session 109) | 12.5+ | Ja (`seismic`-runner, session 109) | ✅ installert (user-timer) |
| Euronext MiFID II COT | Wheat/Corn EU-positioning-overlay | Euronext HTML-parser (session 110) | 12.5+ | Ja (`cot_euronext`-runner, session 110) | ✅ installert (user-timer) |

### 7.4 Runner-registry og fetch-schedule

#### 7.4.1 Runner-registry-mønster

`bedrock fetch run <name>` dispatcher via `register_runner`-decorator i
`src/bedrock/config/fetch_runner.py`. Alle navn i `fetch.yaml` må ha en
matchende runner — manglende runner gir hard FAIL (oppdaget i session 103
da `enso`-timeren feilet hver måned uten registrert runner).

Runner-kontrakt:

```python
@register_runner("calendar_ff")
def run_calendar_ff(
    spec: FetcherSpec,
    store: Any,
    from_date: date,
    to_date: date,
    instruments: Iterable[InstrumentConfig],
) -> FetchRunResult: ...
```

Runner-funksjonen er ansvarlig for:
1. Iterere over instrumenter som faktisk trenger dataen (skip-on-missing-
   metadata; ikke-instrument-spesifikke kilder kjører som single item).
2. Per item: kalle stateless `fetch_*`-funksjon → DataFrame.
3. Skrive via `store.append_*` (idempotent INSERT OR REPLACE på PK).
4. Fange exceptions per item (`_safe_run`-helper) — én feilet
   instrument stopper ikke resten.
5. Returnere `FetchRunResult` med per-item-status (ok/fail, rows_written).

Per ADR-007 § 4: HTML-skrapere og PDF-parsere må ha manuell CSV-fallback
fra dag 1. Runner-funksjonen velger primær eller fallback basert på
om primær returnerer tom DataFrame eller kaster exception.

#### 7.4.2 Smart-schedule-prinsipper

systemd-timers genereres fra `fetch.yaml` via `bedrock systemd generate`
+ `... install`. `Persistent=true` på alle timers → catch-up ved boot
hvis fyrings-tiden ble missed.

**Tidsone-konvensjon:** OnCalendar tolkes i lokal TZ (Oslo: CEST/CET).
Cron-verdier i fetch.yaml må settes i lokal-tid, ikke UTC, slik at
firing lander etter publiseringstidspunkt på kilden — ikke før.

**Stale_hours-konvensjon:** representerer "alder data kan ha før vi
betrakter det som stale". UI Kartrommet bruker dette til å klassifisere
fersk/aging/stale per `_classify_staleness`. Setter:
- daglige fetchere → `stale_hours = cron-periode + 6h slack` (typisk 30)
- ukentlige → cron-periode + 1 dag (typisk 168 for ukentlig)
- månedlige → cron-periode + 1 uke (typisk 720-840)

**Off-:00/:30 minutt-konvensjon (ADR-008):** unngå minutt 0 og 30 når
mulig — alle som ber om "kl 09" får `0 9 * * *` og lander på samme
sekund som mange andre fetchere globalt. Minutt 15/35/45 gir bedre
last-fordeling. Kun bruk :00 når kilden eksplisitt publiserer på hel
time.

**Conservative cadence:** fetch ikke oftere enn nødvendig. Forex
Factory JSON oppdateres når events legges til eller forecast/previous
fylles inn 1-2 timer før release; daglig 2× (06:15 + 18:15 Oslo) er
nok for `event_distance`-driverens timing-krav (4-24t). Aggressiv
fetching koster nettverk uten verdi.

**Cron-konverteren** (`cron_to_oncalendar`) støtter:
- range/list i dom- og month-feltene siden session 103 (`4-11` → `04..11`),
  nødvendig for vekstsesong-aware schedules som NASS Crop Progress.
- range/list i hour- og minute-feltene siden session 105 (`6,18` →
  `06,18`), nødvendig for fetchere som fyrer flere ganger daglig
  (calendar_ff).
- DOW-felt med navngitte dager (`MON-FRI`) → systemd `Mon-Fri`-prefix.

Gjeldende fetcher-liste (etter session 110, 15 totalt):

| Fetcher | Cadence | OnCalendar | Stale_hours | Source |
|---|---|---|---|---|
| prices | hverdager hver time | `Mon-Fri *-*-* *:40:00` | 30 | Yahoo |
| cot_disaggregated | ukentlig | `Fri *-*-* 22:00:00` | 168 | CFTC |
| cot_legacy | ukentlig | `Fri *-*-* 22:00:00` | 168 | CFTC |
| fundamentals | daglig | `*-*-* 02:30:00` | 48 | FRED |
| weather | daglig | `*-*-* 03:00:00` | 30 | ERA5 |
| enso | månedlig | `*-*-12 06:00:00` | 720 | NOAA ONI |
| wasde | månedlig | `*-*-13 19:00:00` | 840 | USDA ESMIS |
| crop_progress | ukentlig (apr-nov) | `Mon *-04..11-* 23:00:00` | 200 | NASS API |
| bdi | hverdager | `Mon-Fri *-*-* 23:30:00` | 30 | BDRY ETF (Yahoo) |
| calendar_ff | daglig 2× | `*-*-* 06,18:15:00` | 14 | Forex Factory |
| cot_ice | ukentlig | `Fri *-*-* 22:30:00` | 168 | ICE COTHist*.csv |
| eia_inventories | ukentlig (ons) | `Wed *-*-* 17:30:00` | 200 | EIA Open Data v2 |
| comex | hverdager | `Mon-Fri *-*-* 22:00:00` | 30 | metalcharts.org |
| seismic | daglig | `*-*-* 04:00:00` | 30 | USGS GeoJSON |
| cot_euronext | ukentlig (ons) | `Wed *-*-* 18:00:00` | 168 | Euronext HTML |

#### 7.4.3 Generert vs systemd-installert (audit korrigert session 107)

**Status:** `bedrock systemd generate` skriver timer/service-filer til
`/home/pc/bedrock/systemd/` (gitignored). Installasjon kan skje to steder:
- **System-nivå:** `/etc/systemd/system/` via `sudo cp + systemctl daemon-reload
  + enable --now`. Krever NOPASSWD-sudo eller passord-prompt.
- **User-nivå:** `~/.config/systemd/user/` via `cp + systemctl --user
  daemon-reload + enable --now`. Krever ikke sudo. Fordel: enklere å
  rulle ut. Begrensning: kjører kun når brukeren er logget inn (eller
  `loginctl enable-linger pc`).

Audit-funn fra session 105 var **ufullstendig** — det listet 9 fetchere som
"generert, ikke installert" fordi det kun så i `/etc/systemd/system/`. Audit
korrigert i session 107: 8 av disse var allerede installert som user-timers
i `~/.config/systemd/user/` siden tidligere sessioner. Korrekt status etter
session 110 (alle 15 fetchere er aktivt installert):

| Lag | Fetchere |
|---|---|
| ✅ System-installert | calendar_ff (105), cot_ice (106) |
| ✅ User-installert | prices, cot_disaggregated, cot_legacy, fundamentals, weather, enso, wasde, crop_progress, bdi (alle pre-session 105), eia_inventories (107), comex (108), seismic (109), cot_euronext (110) |

**Hvorfor begge nivåer i bruk?** Tidligere fetchere ble installert som user-
timers i et tidlig dev-stadium. Sessions 105-106 brukte system-timers fordi
NOPASSWD-sudo var aktivt. Sessions 107-110 falt tilbake på user-timers fordi
NOPASSWD-sudo ikke lenger var konfigurert; user-timer er pragmatisk og
fungerer godt for dev/single-user-systemet.

**Aksjonsplan før Fase 13 cutover (ADR-009 audit i session 117):**
1. Bestemme om alle skal være system- eller user-timers (preferanse: system
   for prod, fordi `loginctl enable-linger` er ekstra steg). Konvertere
   etter behov.
2. Verifisere at alle aktivt fyrer (sjekke `LAST` + `NEXT`-kolonnene mot
   forventet cron).
3. Inkludere systemd-status i `bedrock-monitor`-rapporten (per-timer
   "last run age" + "next run").

Service-relaterte units som ER installert (system-nivå):
`bedrock-server.service` (24/7 UI), `bedrock-signals-all.timer`
(daglig signal-generering), `bedrock-monitor.timer` (06:30 pipeline-
helse), `bedrock-compare.timer` (06:35 signal-diff vs cot-explorer).

### 7.5 Ikke-portede fetchere fra cot-explorer (sub-fase 12.5+ roadmap)

Prinsipp 6 sier at alle fetch-moduler skal beholdes. Audit i session 104
avdekket at **11 fetchere fra `~/cot-explorer/` ikke ble portet** under
Fase 6 — de ble parkert som gjeld. Sub-fase 12.5+ (sessions 105-118)
porter dem inn i bedrock-strukturen og wirer dem inn i scoring der det
gir verdi. Strategi: ADR-007. Per-fetcher-mapping: ADR-008 (sessions 105+).

| Session | cot-explorer-modul | bedrock-mål | Driver | Instrumenter | Type |
|---|---|---|---|---|---|
| 105 | `fetch_calendar.py` | `fetch/calendar_ff.py` | `event_distance` | **alle 22** | full driver-port |
| 106 | `fetch_ice_cot.py` | `fetch/cot_ice.py` | `cot_ice_mm_pct` | Brent (primær COT), NaturalGas | full driver-port |
| 107 | `fetch_oilgas.py` (kun EIA-bit) | `fetch/eia_inventories.py` | `eia_stock_change` | CrudeOil, Brent, NaturalGas | full driver-port (resten droppet — duplikat med Yahoo + CFTC) |
| 108 | `fetch_comex.py` | `fetch/comex.py` (+ manuell CSV-fallback) | `comex_stress` | Gold, Silver, Copper | full driver-port |
| 109 | `fetch_seismic.py` | `fetch/seismic.py` | `mining_disruption` | Gold, Silver, Copper, Platinum | full driver-port |
| 110 | `fetch_euronext_cot.py` | `fetch/cot_euronext.py` (+ manuell CSV-fallback) | `cot_euronext_mm_pct` | Wheat, Corn (EU-overlay) | full driver-port |
| 111 | `fetch_conab.py` | `fetch/conab.py` (PDF via poppler-utils) | `conab_yoy` | Corn, Soybean, Coffee | full driver-port |
| 112 | `fetch_unica.py` | `fetch/unica.py` (PDF via poppler-utils) | `unica_mix` | Sugar | full driver-port |
| 113 | `fetch_shipping.py` | konsolideres med eksisterende `bdi` → `fetch/shipping.py` | `shipping_pressure` (utvidelse av `bdi_chg30d`) | Wheat, Soybean, Corn | refactor + utvidelse |
| 114 | `fetch_intel.py` | `fetch/news_intel.py` | (ingen) | (ingen) | **kun fetcher + UI-context.** Driver-vurdering etter empirisk validering. |
| 115 | `fetch_crypto.py` | `fetch/crypto_sentiment.py` | (ingen) | (ingen) | **kun fetcher + UI-context.** Driver-vurdering etter empirisk validering. |

Etter session 115 har bedrock 20 fetchere totalt (9 + 11 nye). Phase D
(sessions 116-117) konsoliderer:
- Backtest-validering på alle 22 instrumenter med komplett data-grunnlag
- ADR-009 cutover-readiness audit
- Tag `v0.12.5-fetch-port-complete`

---

## 8. Signal server — refaktor

### 8.1 Fra én fil på 974 linjer til modul-struktur

Dagens `~/scalp_edge/signal_server.py` har: `/push-alert`, `/push-agri-alert`, `/signals`, `/agri-signals`, `/kill`, `/clear_kills`, `/upload`, `/invalidate`, `/push-prices`, `/prices`, `/health`, `/status`.

Alle beholdes funksjonelt. Rutes splittes per domene (`routes_signals`, `routes_prices`, `routes_kill`, `routes_admin`).

Ny tillegg: `/admin/rules` (POST) — kode-beskyttet endpoint som lar UI-admin-siden oppdatere YAML-filer. Validerer YAML + skriver til `config/instruments/`.

### 8.2 Kill-switch — allerede løst, bare dokumentere

- Boten poller `/kill` hvert loop
- `/kill` returnerer liste av `sig_id` som skal lukkes umiddelbart
- Beskyttet med `X-API-Key: {SCALP_API_KEY}`
- CLI: `bedrock kill sig_abc123` eller `bedrock kill all`
- Kill-liste sparket bort ved `/clear_kills` (kun admin)

Ingen UI-eksponering → sikkert selv i public repo.

### 8.3 Rule-editor endpoint

```
POST /admin/rules
Header: X-Admin-Code: <secret>
Body: {"instrument": "gold", "yaml_content": "..."}

Effekt:
1. Valider yaml-struktur mot schema
2. Kjør dry-run score på siste snapshot + ny regel
3. Returner diff: hvilke signaler ville endret seg
4. Hvis client bekrefter: skriv til config/instruments/gold.yaml + git-commit
```

UI-flow: admin-siden (separat HTML, beskyttet med lokal kode), laster gjeldende YAML, lar deg redigere, viser dry-run-diff, lar deg commit.

---

## 9. Bot — refaktor

### 9.1 Hva fjernes (kritisk fix)

**Agri ATR-override** (`trading_bot.py:2665-2691`, `_calibrate_agri_signal`): boten overstyrer `signal.t1` til `entry ± 2.5 × live_atr_15m`. Dette er **bug-en som forårsaket små agri-TP-er**.

- Ny Bedrock-setup-generator produserer reelle-nivå-baserte SL/T1 per horisont
- Boten skal **respektere signal.t1 som sendt** — ingen override
- Hvis setup-generatoren kommer opp med 5×ATR TP pga. reelt nivå, skal det holde
- Fjernes i bot-refaktoren. Enhetstest verifiserer at agri-signaler ikke får SL/T1 omskrevet.

### 9.2 Hva beholdes (hele maskineriet)

- Twisted + Protobuf + cTrader Open API
- 3-punkts confirmation (body, wick-rejection, EMA-gradient)
- Alle entry-gates (horizon-TTL, daily-loss, correlation, agri-subgruppe, session-times, Monday-gap, oil-geo)
- Exit-prioritet P1-P5 (geo-spike, kill, weekend, T1, trail, EMA9, timeout, hard-close) **— horisont-spesifikk gating per session 138 (2026-04-30):**
  - **SCALP** kjører hele matrisen (P1-P5b)
  - **SWING** ekskluderer P4 (EMA9-kryss), P5a (8-candle timeout), P5b (16-candle hard close); P2.5 weekend strammer SL men lukker ikke
  - **MAKRO** ekskluderer P3 (T1, ingen fast TP), P3.6 (give-back), P4, P5a, P5b, og P2.5 weekend SL-stram. P3.5 trail er aktiv fra entry. Trail/SL er eneste exit utover P1/P2.
- Position sizing (risk-% + lot-tier + VIX/geo-nedskalering)
- Schema-versjons-toleranse (1.0, 2.0, 2.1, 2.2)
- Daily-loss-state persistering
- Heartbeat + auto-reconnect

### 9.3 Config-ekstraksjon

Alle hardkodede terskler fra § 11 i bot-rapporten flyttes til `config/bot.yaml`:

```yaml
# config/bot.yaml
confirmation:
  body_threshold_atr_pct: 0.30
  ema_gradient_buy_min: -0.05
  ema_gradient_sell_max: 0.05

trail_atr_multipliers:
  fx: 2.5
  gold: 3.5
  silver: 3.5
  oil: 3.0
  indices: 2.8
  grains: 2.0
  softs: 2.5
  cotton: 2.5

giveback:
  peak_threshold: 0.85
  exit_threshold: 0.30

break_even:
  atr_ratio: 0.15

expiry_candles:
  fx: 32
  metals: 48
  oil: 48
  indices: 40
  agri: 48

risk_pct:
  full: 1.0
  half: 0.50
  quarter: 0.25

daily_loss:
  pct_of_balance: 2.0
  minimum_nok: 500

agri:
  max_concurrent: 2
  max_per_subgroup: 1
  max_spread_atr_ratio: 0.40
  session_times_cet:
    corn:    {start: "09:00", end: "21:00"}
    wheat:   {start: "09:00", end: "21:00"}
    soybean: {start: "09:00", end: "21:00"}
    coffee:  {start: "09:00", end: "19:30"}
    cotton:  {start: "09:00", end: "20:00"}
    sugar:   {start: "09:00", end: "19:30"}
    cocoa:   {start: "09:00", end: "19:30"}

oil:
  min_sl_pips: 25
  max_spread_mult: 3.0

polling:
  scalp_active_seconds: 20
  default_seconds: 60
```

Re-leses ved SIGHUP (bot trenger ikke restart for config-endring).

### 9.4 Bot-refaktor plan

Splitt `trading_bot.py` (2977 linjer, én fil) i:

| Fil | Ansvar | Omtrentlig linjer |
|---|---|---|
| `bot/ctrader_client.py` | Twisted, Protobuf, reconnect | 400-500 |
| `bot/entry.py` | Confirmation + alle entry-gates | 500-600 |
| `bot/exit.py` | P1-P5 exit-logikk | 400-500 |
| `bot/sizing.py` | Risk-% + lot-tier | 150-200 |
| `bot/state.py` | TradeState/Candle/Buffer/Phase | 200-250 |
| `bot/safety.py` | Daily-loss + kill + server-frozen | 200-300 |
| `bot/comms.py` | Signal_server-polling | 150-200 |
| `bot/__main__.py` | Wire alt sammen | 100-150 |

**Null logikk-endring i denne fasen** (utover fjerning av agri-override). Bare renaming + flytting.

### 9.5 Pre-Fase-13 blockers (oppdaget 2026-04-30, session 138)

To åpne saker som må adresseres før Fase 13 cutover (se STATE.md "Kjente
bugs" for full kontekst):

1. **Setup→bot signal-format-adapter.** `data/signals_bot.json` (skrevet
   av `bedrock signals-all --bot-only`) har en helt annen schema enn
   `bot/entry.py` + `bot/comms.py` leser. Bot kan ikke handle dagens
   signal-fil. Krever en adapter som mapper:

   - `setup.setup.entry → alert_level` med `entry_zone` ±tolerance
   - `setup.setup.tp → t1` (None-respekt for MAKRO)
   - `setup.setup.sl → stop`
   - lowercase `horizon → uppercase`
   - `setup.setup_id → id`
   - populerer `horizon_config` per horisont (TTL, sizing-base-risk osv.)
   - utleder `status` ut fra `published`-flag og grade

   Plassering åpen: i `signals_all`-CLI (transformer ved skriving) eller
   i `signal_server` (transformer ved `/signals`-respons). Førstnevnte
   holder serveren enkel; sistnevnte holder fila human-readable for
   diff/backtest. **Avgjøres i første post-harvest-session.**

2. **Push-prices fra bot fjernet (2026-04-30).** `SignalComms.push_prices`
   + `assemble_prices_from_state` + `INSTRUMENT_TO_PRICE_KEY` slettet —
   harvester eier prises mot `DataStore`. Server-endepunktet
   `/push-prices` beholdt foreløpig (utenfor bot-scope), kan vurderes
   slettet senere.

---

## 10. UI — 5 faner

> **Refresh-pass 2026-04-30 (session 137):** opprinnelig 4-fane-design er
> utvidet til 5 faner og fane-navnene er rettet for å matche faktisk
> innhold etter sub-fase 12.5/12.6/12.7-arbeid. Section-IDer i HTML er
> beholdt (`skipsloggen`, `financial`, `agri`, `sentiment`, `kartrom`)
> for å unngå JS-bindings-brudd. Mobile breakpoints (≤ 768px og ≤ 480px)
> er lagt til samme runde — første `@media`-blokker i prosjektet.

### 10.1 Fane 1 — Handelslogg (tidligere "Skipsloggen")

Bot-logg og historikk. Leser `data/signal_log.json`. KPI-kort
(trades/wins/losses/win-rate/total PnL) + filtrerbar trade-tabell med
horisont-kolonne. Filter-bar med horisont-pills (`Alle/Scalp/Swing/Makro`).

### 10.2 Fane 2 — Finans (tidligere "Financial setups")

Aktive setups fra `data/signals.json` filtrert på asset_class ∈
{fx, metals, energy, indices, crypto}. Setup-kort viser:
- Instrument + retning + grade-pille
- **Horisont-pille** (fargekodet: scalp=blå, swing=oransje, makro=lilla)
- **Mini-score-bar** med publish-floor-mark
- Entry/Stop/T1/R:R (trailing-tekst for MAKRO-setups uten TP)
- **Familie-mini-bars** med alle 6 familier rangert etter relativ score
Klikk → modal med full explain-trace og analog-matcher.

### 10.3 Fane 3 — Agri (tidligere "Soft commodities")

Samme kort-format som Finans, men leser `data/agri_signals.json`
(asset_class ∈ {grains, softs}) og familie-mini bruker agri-familier
(outlook/yield/weather/enso/cross/analog).

**Weather-strip nederst på hvert kort** (Etappe 5, commit `ba991e1`):
- ENSO-pille (NOAA ONI fase: La Niña / Nøytral / El Niño)
- Region-pille (water_bal + tørr-dager fra weather_monthly)
- Drought-pille (US Drought Monitor, kun for amerikanske instrumenter)

Backend-API: `GET /api/ui/agri_weather` aggregerer alt på én call.

### 10.4 Fane 4 — Markedspuls (tidligere "Sentiment")

Risk-indikatorer + sentiment + nyheter. Tre seksjoner:

**Risk-indikatorer** (Etappe 4, commit `5b526c3`) — 5 makro-indikatorer
fra `bedrock.db` med klassifisering (calm/normal/elevated/stress):
- VIX term-spread (VIXCLS − VIX3M)
- AAII bull-bear (kontrarisk, regnet bull% − bear% pga fetcher-bug —
  se "Kjente bugs" i STATE.md)
- NFCI (Chicago Fed financial conditions)
- Credit-spread BAA-10Y (Moody's)
- 10Y real yield (DGS10 − T10YIE)

Backend-API: `GET /api/ui/risk_indicators`.

**Crypto-sentiment** — Fear & Greed-historikk + market-cap.

**Markedsnyheter** — Google News RSS-kategorier med artikkel-counts.

### 10.5 Fane 5 — Datakilder (tidligere "Kartrommet")

Pipeline-kontrollbord + daglig systemsjekk.

**Daglig systemsjekk-banner** (Etappe 3, commit `943961f`):
fargekodet OK/FAIL-pille + grid med ett kort per check
(fetcher_freshness, pipeline_log_errors, agri_tp_override, signal_diff).

Backend-API: `GET /api/ui/system_health` leser nyeste
`data/_meta/monitor_*.json` skrevet av `scripts/daily_monitor.py`.

**Pipeline-helse per fetch-kilde** (uendret fra session 50): viser
fresh/aging/stale/missing med `_meta.generated_at` og rad-antall.
Gruppert (Core / Bot-priser / CFTC / Ekstern COT / Fundamentals /
Sektor / Geo). Read-only.

### 10.6 Fane 6 — Backtest (planlagt, ikke implementert)

**Etappe 7 av UI-refresh-arbeidet, ikke startet.** Avventer harvest-
session 136-fullføring + analyzer-runde (session 137+). Skal vise:
- IC per driver × instrument × horisont fra harvest-output
- Forward-return-statistikk fra `driver_observations`
- Cross-correlation-matrise mellom drivere
- Anbefalinger for vekt-justeringer fra rebalanserings-analyse

### 10.7 Separat: Admin-rule-editor + driver-utforsker

`web/admin.html`. Beskyttet med lokal kode (kode-input → hasha + matchet
mot server-lagret hash). Tre seksjoner via sidebar-nav:

**Rules** (uendret): rediger YAML-regler per instrument, dry-run-diff,
commit. POST til `/admin/rules`.

**Drivers** (Etappe 6, commit `04d9fea`): driver-utforsker som viser
alle registrerte drivere fra in-process registry + observation-stats
fra `driver_observations`. Hver driver klassifisert som
active/monotone/silent/deprecated. Brukes til å se hvilke drivere
faktisk leverer signal vs. er stille (typisk symptom på data-mangel
eller at trigger-instrument ikke er i drift).

Backend-API: `GET /admin/drivers` (X-Admin-Code-protected).

**Logs**: tail siste N linjer fra `logs/pipeline.log` med refresh.

Fordi repoet er public ligger `admin.html` bak et separat endpoint
som ikke linkes fra `index.html`. Bruker kan nå den via direkte URL
+ kode.

### 10.6 Prinsipp: ingenting krever terminal

All konfigurasjon, alle justeringer, all drift styres fra web-UI-et. Terminalen
brukes kun av Claude Code under utvikling og av systemd i produksjon. Brukeren
skal aldri måtte åpne terminal for å endre noe i daglig drift.

**Editerbart via admin-UI (kode-beskyttet):**

| Hva | Fil bak scenen | Hvor i UI |
|---|---|---|
| Scoring-regler per instrument | `config/instruments/*.yaml` | Admin → Instruments → velg → edit |
| Driver-vekter og parametre | Samme | Admin → Instruments → familie → driver |
| Grade-terskler (A+/A/B) | Samme, evt `config/defaults/` | Admin → Instruments → grade |
| Horisont-vekter per asset-klasse | `config/defaults/family_*.yaml` | Admin → Defaults |
| Fetch-cadence og stale-terskler | `config/fetch.yaml` | Admin → Pipeline → Fetch-schedule |
| Bot-thresholds (confirmation, trail, giveback, osv.) | `config/bot.yaml` | Admin → Bot config |
| Instrument-liste (legg til / fjern) | Egen YAML | Admin → Instruments → New |
| Aktivering/deaktivering av fetch-kilder | `config/fetch.yaml` | Admin → Pipeline → toggle |

**Styring via UI (ikke bare editering):**

| Handling | UI-knapp | Bak scenen |
|---|---|---|
| Stopp alle åpne trades (killswitch) | Stor rød knapp øverst | POST `/kill all` med admin-kode |
| Invalider enkeltsignal | Trykk på signal → "Cancel" | POST `/invalidate` |
| Force-run pipeline nå | Admin → Pipeline → "Run now" | trigger systemd-service |
| Pause pipeline midlertidig | Admin → Pipeline → "Pause" | deaktiver timer |
| Vis siste kjørings-log | Admin → Logs | les `logs/pipeline.log`, 200 siste linjer |
| Dry-run ny regel | Admin → Instruments → edit → "Dry-run" | kjør scoring mot siste 7 dager, vis diff |
| Ta regelen i bruk | Samme editor → "Commit" | POST `/admin/rules`, YAML skrives, git-commit |
| Se bot-status | Dashboard top-bar | read `signal_log.json` + `/status` |

**Implementasjon:**

- UI: `web/admin.html` (separat fra offentlig `index.html`, skjult URL, kode-gate)
- Backend: utvid `signal_server` med admin-endpoints (`/admin/rules`, `/admin/fetch`, `/admin/bot`, `/admin/pipeline`)
- Alle admin-endepunkter krever `X-Admin-Code`-header (SHA-256 hash matches ADMIN_CODE_HASH i env)
- YAML-edits går gjennom dry-run + validering + diff-visning før commit
- Alle endringer auto-commits med `config(<scope>): ...`-melding; auto-push-hook sender til GitHub

**Hva UI IKKE dekker (én-gangs eller sikkerhets-kritisk):**

- Installere uv / Python — én gang, Claude Code gjør det
- SSH-nøkler / GitHub-tilgang — nettleser, ikke terminal
- Førstegangs-systemd-installasjon — én gang, Claude Code gjør det
- cTrader-credentials i `.env` — sensitivt, bruker skriver selv (f.eks. med tekst-editor
  i filutforsker) fordi de aldri skal på GitHub

Totalt: bruker skal kunne drive Bedrock uten å åpne terminal i daglig bruk. Terminal
er kun for førstegangs-oppsett og utvikler-arbeid.

---

## 11. Testing — logiske tester

**Filosofi:** vi tester *atferd*, ikke *implementasjon*. Fire lag:

### 11.1 Logiske tester (hoved-testsuite)

Format: "gitt dette input-data, forvent dette output-signal".

```python
# tests/logical/test_scoring_scenarios.py
def test_gold_swing_bull_macro_supports():
    """Gitt gull med sterk trend, moderat COT, VIX normal → forvent SWING A/A+ bull"""
    data = fixture("gold_2024_03_15")    # kurert historisk snapshot
    rules = load_rules("gold.yaml")
    result = engine.score("Gold", data, rules)
    assert result.horizon == "SWING"
    assert result.direction == "bull"
    assert result.grade in ("A", "A+")
    assert result.score >= 3.0

def test_corn_agri_fresh_drought_gives_A():
    """Gitt Corn med US drought + ENSO La Niña + Conab YoY -5% → forvent A-grade"""
    data = fixture("corn_2024_07_drought")
    rules = load_rules("corn.yaml")
    result = engine.score("Corn", data, rules)
    assert result.grade in ("A", "A+")
    assert result.families["outlook"].score >= 4.0
    assert "drought" in str(result.explain).lower()

def test_stale_data_caps_grade_to_B():
    """Gitt fersk scoring men stale Conab → grade kappes til B"""
    data = fixture("corn_stale_conab")
    result = engine.score("Corn", data, load_rules("corn.yaml"))
    assert result.grade == "B"
    assert "stale" in result.gates_triggered
```

Hver test er et **scenario**. Fikturene er JSON-filer i `tests/logical/fixtures/`, kurert manuelt fra ekte historikk.

### 11.2 Setup-generator-tester

```python
def test_setup_respects_real_levels():
    """Gitt Gold nåpris 2000, SMA200=1950, neste motstand 2050 → bull swing TP=2045"""
    levels = [LevelAt(price=2050, type="resistance", strength=0.8), ...]
    setup = generator.build("Gold", "bull", "SWING", nåpris=2000, levels=levels)
    assert setup.t1 == 2045          # "litt før motstand" = 5-pip buffer
    assert setup.sl < 1950           # under SMA200/støtte
    assert setup.rr_t1 >= 2.5        # asymmetri-krav

def test_makro_setup_has_no_tp():
    """MAKRO-setups skal ha t1=None og bruke trailing"""
    setup = generator.build("Gold", "bull", "MAKRO", ...)
    assert setup.t1 is None
    assert setup.exit_strategy == "trail_only"

def test_setup_persists_across_runs():
    """SWING-setup som fortsatt er gyldig skal beholde ID og oppdatere score-history"""
    setup_v1 = generator.build("Gold", "bull", "SWING", data=fixture("t1"))
    store.save(setup_v1)
    setup_v2 = generator.reevaluate(setup_v1.id, data=fixture("t1_plus_4h"))
    assert setup_v2.id == setup_v1.id
    assert len(setup_v2.score_history) == 2
```

### 11.3 Explain-tester

```python
def test_explain_lists_every_driver():
    """Hvert signal skal kunne forklare eksakt hvilke drivere som bidro"""
    result = engine.score("Gold", fixture("gold_a_plus"), load_rules("gold.yaml"))
    for family in result.families.values():
        for driver in family.drivers:
            assert driver.value is not None
            assert driver.weight > 0
            assert driver.contribution == approx(driver.value * driver.weight)
    assert sum_of_contributions(result) == approx(result.score, rel=0.01)
```

### 11.4 Snapshot / golden-files

Fixtures committes. Hvis engine-endring gir *annen* output, testen feiler, og du må bevisst bekrefte (`pytest --snapshot-update`). Hindrer utilsiktet drift.

### 11.5 Backtest-rammeverk

```python
# tests/backtest/test_rules_v1_vs_v2.py
def test_rules_v2_vs_v1_on_2024():
    """Kjør begge regelsett mot 2024-historikk, rapporter forskjeller"""
    v1_signals = backtest(rules="v1", from_="2024-01-01", to="2024-12-31")
    v2_signals = backtest(rules="v2", from_="2024-01-01", to="2024-12-31")
    diff = compare_signals(v1_signals, v2_signals)
    assert diff.signal_count_delta < 0.10 * len(v1_signals)   # max 10 % endring
    # ikke "feiler", men rapporterer — brukes i PR for å vise regelens impact
```

### 11.6 Integrasjonstest

Én test som kjører full pipeline på en fikst historisk dato:

```python
def test_full_pipeline_2026_03_15():
    data_dir = "tests/integration/fixtures/2026-03-15/"
    pipeline.main_cycle(data_dir=data_dir, dry_run=True)
    signals = load("tests/integration/fixtures/2026-03-15/expected_signals.json")
    actual = load(f"{data_dir}/data/signals.json")
    assert signals == actual
```

Dette er kontrakten: gitt denne input-dataen, genererer pipelinen *nøyaktig* denne signal-fila.

### 11.7 Smoke-tester for produksjon

Kjøres av systemd etter hver `main_cycle`:
- `data/signals.json` eksisterer og har valid schema
- `data/macro/latest.json` er < 6t gammel
- POST /push-alert returnerte 200
- Git-push lyktes (eller retry trigget)

Feil på disse → varsel til lokal log + `data/_meta/pipeline_health.json`.

---

## 12. Migrering — ingen trades mistet

### 12.1 Parallell-drift 2 uker

- Nytt prosjekt `~/bedrock/` ved siden av `~/cot-explorer/` + `~/scalp_edge/`
- Bedrock-systemd-timer kjører i `--dry-run` (skriver signals men POST-er ikke til signal_server)
- Bedrock bot kjører på egen `--demo`-konto parallelt
- Daglig sammenligning: diff mellom gamle `signals.json` og Bedrocks versjon

### 12.2 signal_log.json-migrering

Dette er den eneste fila bot + dashboard deler. Overgang:

1. Bedrock bot starter på *ny* signal_log-sti (`~/bedrock/data/signal_log.json`)
2. Gamle `~/scalp_edge/trading_bot.py` fortsetter med sin gamle sti til alle åpne trades er lukket (maks ~5 dager for SWING, ~3 mnd MAKRO men statistisk sjelden over 2 uker)
3. Bedrock bot tar *nye* trades fra demo-perioden
4. Cutover: når siste gamle trade er lukket, kill gammel bot, skru Bedrock-bot til live

### 12.3 Cutover-kriterier etter 2 uker demo

Per din bekreftelse: evalueres subjektivt + logg. Men minimum:

- Null unexpected exceptions i `data/_meta/pipeline_health.json`
- Ingen git-push-feil i `logs/pipeline.log`
- Siste 20 setups manuelt inspisert: entry-nivå gir mening, TP ved reelt nivå, R:R ≥ horisont-min
- Bedrock-bot log viser 0 tilfeller av "agri TP overridden" (bug-fix fungerer)
- Signal-diff mellom gammel og ny pipeline forklarbar (ikke tilfeldig støy)
- **Sub-fase 12.6-konvergens** (ny krav per ADR-009 session 117):
  ≥2 iterasjoner med rebalansert YAML der re-harvest viser
  scoring-forbedring; setup-walker P&L positiv risk-justert på minst
  4 av 6 (asset-klasse, retning)-kombinasjoner

### 12.5+ Fetcher-port-strategi — LUKKET 2026-04-27

Sessions 104-117. Tag `v0.12.5-fetch-port-complete`. Alle 11 ikke-
portede cot-explorer-fetchere fra § 7.5 portet til bedrock-strukturen
(sessions 105-115), AsOfDateStore utvidet med Phase A-C-proxy-getters
+ Phase D backtest-infrastruktur levert (session 116), ADR-009 låser
in cutover-readiness-status (session 117). Se ADR-008 for per-fetcher
mapping og ADR-009 for sluttvurdering.

### 12.6 Data-driven rebalansering — ÅPEN 2026-04-27

Ny sub-fase mellom 12.5+ og Fase 13 per ADR-009. Bruker harvester+
analyzer-infrastrukturen fra session 116 til empirisk å rebalansere
scoring-systemet før cutover.

**Scope:**

1. **Detached harvest** (sessions 118+): full historisk
   `driver_observations` + `feature_snapshots` + `signal_setups` over
   ≥10 års historikk for alle 22 instrumenter × 3 horisonter ×
   2 retninger via `scripts/run_full_history_harvest.sh`. Kjøres
   detached — ~24-35 timer per komplett harvest. Resumable.

2. **Analyzer-utvidelser:**
   - `analyze_driver_performance.py`: per-driver IC, kvartil-hit-
     rate, monotonisitet (allerede levert session 116)
   - `analyze_cross_correlations.py`: forward-looking IC-matrise
     prediktor × target (allerede levert session 116)
   - **Sesong-bucketing:** IC per kalenderkvartal — fanger sykler
     (Sugar pre/post Brazil-høst, Wheat pre/post US-planting,
     energi sesongsyklus, FX-rentesyklus)
   - **Lead-lag-IC:** driver_value(t) vs forward_return ved lag 0,
     14, 30, 60d — driver kan predikere lengre frem på SWING/MAKRO
     enn SCALP
   - **Setup-walker** (12.6.b): walker prisene forover dag-for-dag
     for hver setup, avgjør TP-hit / SL-hit / timeout / break-even,
     skriver til ny `setup_outcomes`-tabell. Gir ekte P&L-distri-
     busjon, ikke bare hit-rate

3. **YAML-vekt-rebalansering:** basert på empiri, IKKE skjønn.
   Drivere med median |IC| < 0.05 og monotonisitet < 0.4 vurderes
   for vekt-reduksjon eller fjerning. Drivere med median |IC| > 0.10
   og monotonisitet > 0.7 kan vekt-økes.

4. **Iterer:** re-harvest delsett etter rebalansering → bekreft
   forbedring → ny rebalansering. Til konvergens.

5. **Empirisk validering av Phase A-C-drivere:** når Phase A-C-
   data har akkumulert ≥1 mnd, kjør spike-mode (zero-out) for hver
   ny driver via `backtest_phase_d_session116.py --mode spike`.
   Resultat avgjør om driver beholdes / vekt-justeres / fjernes.

6. **News_intel + crypto_sentiment driver-aktivering:** vurderes
   etter ≥1 mnds data + IC-analyse fra harvest. Maks 0.1 vekt i
   første runde per ADR-007 § 5.

**Test-krav:** harvester + analyzer er resumable (PRIMARY KEY på
alle nye tabeller); analyzer-output reproducerer session 99-baseline
± 1pp; minst én rebalansering-iterasjon viser positiv ∆IC på ≥1
high-confidence-driver.

---

## 13. Faser og rekkefølge

Hver fase avsluttes med testing + commit. Ingen fase starter før forrige er grønn.

| Fase | Innhold | Estimat | Test-krav |
|---|---|---|---|
| **0** | Bedrock-repo, pyproject.toml, uv, pre-commit (ruff, pyright), CI | 1-2 dager | `pytest` kjører tomme tester grønt |
| **1** | Engine + driver-registry + aggregators + grade + explain. 5-10 drivere. Eksempel-YAML Gold + Corn. | 1 uke | Logiske tester for scoring-scenarioer |
| **2** | Data-lag: SQLite + pandas (revidert, ADR-002), skjemaer, DataStore-API | 4-5 dager | Unit-tester på store.py |
| **3** | Backfill-CLI: priser, COT, FRED, vær. 10 års historikk. | 1 uke (+ kjøretid) | Data-integritets-tester |
| **4** | Setup-generator: nivå-detektor + generator + persistence + horisont-klassifisering. MAKRO no-TP. | 2 uker | Logiske tester for setup-output. Dette er hjertet i "asymmetri-målet". |
| **5** | Scoring-motor komplett: per-instrument YAML med `inherits`-inheritance, orchestrator (score_instrument + generate_signals), gates/cap_grade (ADR-003), bedrock signals CLI-wrapper. | 1-2 uker | Orchestrator E2E-tester + instrument-YAML-validering |
| **6** | Fetch-laget: USDA-kalender + usda_blackout-gate, config-drevet `fetch.yaml` + status-CLI, `bedrock fetch run <name>`-dispatcher med per-item resiliens, systemd-unit-generator (generate/install/list). Ekstra drivere (BRL/USD, BDI, Crop Progress, WASDE) legges til fortløpende når behov oppstår — ikke blockere. | 1-2 uker | Smoke-tester per fetcher + CLI-integrasjonstester |
| **7** | Signal-server refaktor: modul-splitt fra 974-linjers fil, `/admin/rules` endpoint, schema-validering | 3-5 dager | API-tester |
| **8** | Bot-refaktor: splitt i 8 moduler, fjern agri-ATR-override-bug (trading_bot.py:2665-2691), config-ekstraksjon | 1 uke | Bot må fortsatt kjøre demo i parallell |
| **9** | UI: 4 faner + admin-editor. Erstatter eksisterende HTML. | 1-2 uker | Visuell verifisering + signal-visning-tester |
| **10** | Analog-matching: K-NN, per asset-klasse, outcome-labels, integrer i scoring + UI | 1 uke | Backtest av analog-driver mot forward-return |
| **11** | Backtest-rammeverk + 12 måneder historikk-replay (CLI). UI-fane utsatt etter Fase 13 (bruker-beslutning 2026-04-25). | 1 uke | Output: rapport over signal-performance |
| **12** | Parallell-drift + sub-fase 12.5 debt-rydding (drivere før instrumenter) + sub-fase 12.5+ fetch-port (§ 7.5, sessions 105-117) + sub-fase 12.6 data-driven rebalansering (sessions 118-138) + sub-fase 12.7 horisont-refactor (§ 19) + sub-fase 12.8 data-gjeld + cron + whitelist (§ 20, sessions 139-142) | 2 uker observasjon + 14-15 sessions debt + N sessions rebalansering + 4 sessions 12.8 | Cutover-kriterier møtt + 12.6/12.7/12.8 LUKKET |
| **13** | Cutover: skru av gamle timers (cot-explorer + scalp_edge), install systemd-units, gå live | 1 dag | Alt grønt |

Totalt: ~14-18 uker. Kan parallelliseres noe (data-lag og engine kan jobbes samtidig).

**Merk:** Fase 5 ble lagt inn 2026-04-24 for å reflektere faktisk leveranse — den originale Fase 5 "fetch-laget" er nå Fase 6, og alle senere faser er skjøvet ett hakk. Tags: `v0.1.0-fase-1` .. `v0.5.0-fase-5` (sessions 21-26), `v0.6.0-fase-6` (sessions 27-31).

---

## 14. Risiko-register

| Risiko | Konsekvens | Mitigering |
|---|---|---|
| Bot-bug under migrasjon | Mistede trades, kapital-tap | Parallell-drift på *separate* demo-kontoer; gamle bot holder åpne trades |
| YAML-regler drifter fra ekte atferd | "Config funker i test, ikke i prod" | Integrasjons-test i CI kjører full pipeline på fikstur |
| DuckDB/parquet skalering | Treg analog-query ved stor historikk | Benchmark i fase 2; ArcticDB-migrering har endags-kost om nødvendig |
| Setup-persistens-bug | Zombie-setups eller mistede oppdateringer | Eksplisitte lifecycle-state-tester |
| Nye USDA-kilder blokker agri-pipeline | Alt annet stopper fordi én fetcher feiler | `on_failure: log_and_skip` i fetch-config; soft-dependencies |
| Rule-editor kompromittert | Noen endrer YAML og pusher live | Kode-hash lokalt, `/admin/rules` alltid kjører dry-run først og krever eksplisitt bekreftelse |
| Git-push kontinuerlig feil | Data hopes lokalt, dashboard stopper | Retry + varsling i `_meta/pipeline_health.json` |
| Agri ATR-override-fjerning introduserer ny bug | Bot tar feil T1 | Regresjon-test per agri-instrument med fikst signal |

---

## 15. Åpne designbeslutninger (tas underveis)

**Avgjort 2026-04-23:**
1. ✅ Web-backend: **Flask** (lavere RAM på gammel laptop)
2. ✅ Frontend: **vanilla JS + Alpine.js**-sprinkling (ingen build-steg)
3. ✅ Secrets: **`~/.bedrock/secrets.env`** (kommer inn som env-vars)
4. Analog-matching distance metric: **weighted Euclidean** (start). Oppgradere om kvaliteten krever.
5. Logrotasjon: **Python `RotatingFileHandler`** (som boten bruker i dag)
6. Rule-editor dry-run: **siste 7 dager** med data

---

## 16. Neste steg

Fase 0-11 fullført. Fase 12 åpen — parallell-drift pauset, sub-fase 12.5
(debt-rydding) gjennomført sessions 70-103. Sub-fase 12.5+ (sessions 104-117)
portet de 11 ikke-portede cot-explorer-fetcherne + leverte Phase D backtest-
infrastruktur — **LUKKET 2026-04-27** med tag `v0.12.5-fetch-port-complete`.

Sub-fase 12.6 (sessions 118+) ÅPEN: data-driven rebalansering før Fase 13
cutover. Per ADR-009 skal vi bygge empirisk grunnlag for YAML-vekt-justeringer
i stedet for å låse inn dagens skjønnsbaserte vekter. Harvester+analyzer-
infrastruktur fra session 116 er fundamentet — full historisk harvest startet
detached fra session 117.

Aktivt nå (sessions 118+):
1. Vente på + monitorere harvest-progress (~24-35 timer)
2. Analyzer-utvidelser: sesong-bucketing, lead-lag-IC, setup-walker
3. YAML-rebalansering basert på empiri
4. Iterer til konvergens
5. Etter sub-fase 12.6: re-aktiver observasjonsvinduet (parallell-drift sub-
   session 68) før Fase 13 cutover.

**Sub-fase 12.7 (planlagt 2026-04-28) — se § 19** for horisont-refactor +
data-utvidelse. Spor R kan starte parallelt med 12.6 (score-uendret); Spor D
koordineres etter 12.6-konvergens (anbefalt Alt β). Åpent spørsmål: alt α/β/γ
låses i første 12.7-session.

---

## 17. Session-disiplin (ny seksjon)

### 17.1 Motivasjon

Claude Code-sessioner har kontekst-grense. Lange sessioner → tokens sløses på
re-eksplorering + sannsynlighet for off-track øker. Disiplin: hver session har
atomisk scope, start/end-protokoll, skriftlig overlevering.

### 17.2 Tre .md-filer

| Fil | Eier | Innhold | Endringskadens |
|---|---|---|---|
| `CLAUDE.md` | Bruker | Konvensjoner + start/end-protokoll | Kun ved endret prosess |
| `PLAN.md` | Bruker + Claude Code (etter samtale) | Masterplan | Sjelden, egen commit |
| `STATE.md` | Claude Code | Nåværende task + session-logg | Hver session |

`CLAUDE.md` auto-lastes av Claude Code i hver session. Skal være < 200 linjer.
`PLAN.md` leses selektivt (relevant fase-seksjon).
`STATE.md` har `Current state`-blokk øverst + append-only session-logg nedover.

### 17.3 Session-start-protokoll

1. Les `CLAUDE.md` (auto)
2. Les `STATE.md` fra topp til første `---`
3. Les relevant fase-seksjon i `PLAN.md`
4. Bekreft til bruker: "Fortsetter på [task]. Blockers: [...]. Starter med [handling]."
5. Vent på bekreftelse eller ny retning

### 17.4 Session-end-protokoll

1. Commit + push ferdig kode (på feature-branch)
2. Oppdater `STATE.md`:
   - Ny entry øverst i session log
   - Oppdater `Current state`-blokk
   - Legg til open questions
   - Oppdater invariants hvis endret
3. Commit `STATE.md` separat (`state: session N avsluttet`)
4. Fortell bruker: "Session logget. Neste: [X]."

### 17.5 Session-budsjett

Tommelfinger-regel: én avgrenset leveranse per session, avslutt før kontekst går
over 60-70 %. Eksempler:
- Én driver + tester → én session
- Én fetch-modul refaktor → én session
- Ett bot-modul-splitt + regresjonstester → én session

Ikke "gjør hele Fase 4". Alltid bryt ned til atomisk scope.

### 17.6 Claude Chat som fase-gate-review

Ved slutten av hver større fase (Fase 1, 4, 5, 7, 8, 11) kjører bruker en Claude
Chat-session med prompt av typen:

> "Her er diff for Fase N (ved lenke til git-log + endrede filer). Gå gjennom:
> (a) samsvar med `PLAN.md`, (b) technical debt, (c) manglende tester,
> (d) scope-creep. Rapport med prioritert liste."

Tilbakemeldingen tas enten som personlig arbeid eller gis Claude Code som input
til ny session.

**Ikke** gate på hver commit — det er for mye friksjon. Tester og pre-commit
hooks er førstelinje; Chat er fase-gate.

På-forespørsel-review støttes alltid: når bruker er i tvil, spør Chat.

### 17.7 Hva Claude Chat IKKE skal gjøre

- Skrive kode direkte til repoet (Claude Code eier koden)
- Endre `PLAN.md` eller `STATE.md` direkte (Claude Code-sessioner eier dem)
- Kjøre tester eller commits

---

## 18. Git-regler og commit-konvensjon (ny seksjon)

### 18.1 To modus: utvikling vs. live

**Nivå 1 (enkel) — aktiv under Fase 0 til og med Fase 11:**
- Commit direkte til `main`
- Auto-push-hook (`.githooks/post-commit`) sender hver commit til GitHub umiddelbart
- Ingen feature-branches, ingen PR
- Null ceremony, maksimal fart under utvikling
- Main er ennå ikke produksjon (ingen systemd-service kjører fra den)

**Nivå 3 (streng) — aktiveres ved Fase 11-12, før live-cutover:**
- Feature-branch → auto-push branch → PR → CI grønn → review → squash-merge til main
- Aldri direkte-til-main når main = produksjon
- Branch-beskyttelse på GitHub (require PR, require status checks)
- Beskrevet fullt i `docs/branch_strategy.md`

**Overgang:** ved start av Fase 11 setter bruker opp branch-beskyttelse på main i
GitHub-UI, og Claude Code bytter atferd til feature-branch-flyt. Dette er en
1-minutts endring.

### 18.2 Flyt (Nivå 1 — nå)

```
Claude Code gjør endring
   → git add <filer>
   → git commit -m "type(scope): subject"
   → auto-push hooken sender til origin/main automatisk
   → ferdig
```

### 18.3 Flyt (Nivå 3 — ved Fase 11+)

Feature-branch → daglig push → PR → CI grønn → review → squash-merge til main.
Se `docs/branch_strategy.md` for full beskrivelse.

### 18.4 Branch-navn (Nivå 3)

```
feat/<scope>-<beskrivelse>       feat/engine-core
fix/<scope>-<beskrivelse>        fix/bot-agri-tp-override
refactor/<scope>-<beskrivelse>   refactor/bot-split-into-modules
config/<instrument-eller-system> config/gold-swing-tune
docs/<beskrivelse>               docs/update-plan-session-discipline
chore/<beskrivelse>              chore/bump-ruff
```

### 18.5 Commit-format

Conventional Commits, håndhevet av commitizen pre-commit-hook:

```
type(scope): subject

[body — forklar HVORFOR]

[Co-Authored-By: Claude <noreply@anthropic.com>]
```

Typer: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `config`, `state`.

Full liste og eksempler: `docs/commit_convention.md`.

### 18.6 Regler

1. Én logisk endring per commit
2. Tester grønne før commit
3. Aldri commit hemmeligheter
4. Aldri `git add -A` — alltid eksplisitt eller `git add -p`
5. Aldri force-push til main
6. Aldri amend etter push
7. Co-authored-by på Claude-commits
8. Ingen WIP på main
9. STATE.md-commits holdes separate fra kode

### 18.7 Main-beskyttelse (GitHub-settings, aktiveres ved Fase 11)

Bruker setter opp én gang:
- Require PR before merging
- Require status checks: `lint-and-test`
- Require linear history (tvinger squash eller rebase)
- Require conversation resolution before merging
- No bypassing

### 18.8 Fase-tagger

```bash
git checkout main && git pull
git tag -a v0.1.0-fase-1 -m "Engine core + 10 drivere ferdig"
git push origin v0.1.0-fase-1
```

Gir rollback-punkt uten avhengighet av commit-hashes.

---

## 19. Sub-fase 12.7 — Horisont-refactor + data-utvidelse

**Status:** PLANLAGT (godkjent 2026-04-28). Aktiveres etter koordinering med
sub-fase 12.6 — se § 19.7.

### 19.1 Bakgrunn og to spor

Drivere returnerer i dag én skalar `[0..1]` per kall. Dette dekker én horisont
av gangen, men flere planlagte datakilder har **ulik signal-verdi per horisont
fra samme rådata** (CFTC TFF: 12m-percentil → MACRO, ukentlig delta → SWING,
mandag-gap → SCALP. Baker Hughes: 13w trend → MACRO, 4-8w break → SWING.
VIX-termstruktur: regime → MACRO, regime-switch → SWING, VIX9D/VIX-ratio →
SCALP). Hvis hver kilde implementeres som tre uavhengige drivere, vokser
driver-registry 3× og feature-engineering dupliseres.

To spor, må kjøres i rekkefølge:

- **Spor R (R1-R4) — refactor først:** gjør driver-arkitekturen horisont-
  bevisst slik at samme rådata kan produsere ulike features for SCALP/SWING/
  MACRO. **Score-uendret-garanti** for alle 22 instrumenter × 3 horisonter ×
  2 retninger.
- **Spor D (D0-D3) — data-utvidelse etterpå:** 13 nye fetchere + 5 utvidelser
  + 7 mapping-refaktorer. Med horisont-pattern på plass kan hver ny driver
  implementeres riktig fra dag én.

**Hvorfor i denne rekkefølgen:** Hvis vi tar inn data først og refactorer
etterpå, må alle nye drivere skrives om.

### 19.2 Hva endres ikke

- `max_score` per instrument forblir uendret
- Familie-strukturen (financial: 6 familier; agri: 6-7) forblir uendret
- Grade-terskler (A+/A/B) forblir uendret
- Aggregerings-logikk (`weighted_horizon` for financial, `additive_sum` for
  agri) forblir uendret
- Polarity-system (`directional`/`neutral` på familie-nivå) forblir uendret
- Engine-API for bot/signal_server forblir uendret

### 19.3 Låste beslutninger (audit + samtale 2026-04-28)

**Arkitektur — Alt 1 (YAML-styrt `horizon`-param):**
- Engine får ~5 linjer: i tillegg til eksisterende `_direction`-propagering
  via `params_with_dir` (engine.py:377-380), legges en `_horizon`-key inn
  basert på financial horizon-arg. Drivere kan lese `params["_horizon"]`
  for å velge feature.
- For financial er horisonten kjent ved scoring-tid (kommer fra YAML-key).
- For agri (no horizon på engine-siden): drivere kan ta `horizon` eksplisitt
  som YAML-param hvis nødvendig — ingen engine-endring kreves.
- Driver-kontrakten `(store, instrument, params) -> float` er uendret. Mønstret
  matcher analog-driver-presedens (session 100, ADR-006).
- Begrunnelse: minst engine-endring; lesbar YAML; feilsøkbar; konsistent
  med eksisterende direction-propagering.

**Trading-logikk:**
- Percentil-vinduer: **12m + 36m** (12m fanger sesong-syklus + matcher
  eksisterende 52w-bruk; 36m fanger fed-syklus + multi-commodity-cykler)
- Ekstrem-terskler: **2/98 hard `extreme_flag` + 5/95 soft
  `approaching_extreme`-feature** (begge eksponert; YAML-vekting velger)
- Cocoa GHS/XOF: **dropp helt nå.** Cocoa cross-familie blir
  `dxy@0.85 + event_distance@0.15`. EM-FX-pipeline kan tas opp i egen syklus.
- Cotton ENSO: **uendret** (familie-konsistens).

**Refactor-spesifikke valg:**
- R3 referanse-drivere: `positioning_mm_pct` (financial-positioning, alle
  instrumenter), `real_yield` (financial-macro, alle), `crop_progress_stage`
  (agri-agronomy — validerer agri-pattern)
- R4 batch-rekkefølge: trend → structure → risk → positioning → macro →
  agri/agronomy → analog/seasonal (lavest blast-radius først)
- TFF-driver-komposisjon (A4): **to separate drivere** —
  `positioning_lev_funds_pct` + `positioning_asset_mgr_pct` deler privat
  helper i `positioning.py`. `cot_z_score` beholdes uendret.
- AAII mean-reversion (A12): **driver-intern logikk** — driveren returnerer
  invertert score (1.0 = bull-of-instrument ved bear-ekstrem). YAML-polarity
  forblir `directional`. Ingen ny polarity-type.
- Sesong-modulert polarity (`hdd_cdd_anomaly`): **driver-intern logikk** —
  driveren vet kalender-måned, returnerer "demand-pressure-score" som er
  bull-of-NG (vinter+HDD eller sommer+CDD bullish). YAML `directional`,
  ingen ny polarity-type.
- ADR-011 (deprecation) + ADR-012 (failure-mode): **utsatt** (Alt Z).
  Håndteres reaktivt per fetcher; "sekundær"-drivere settes til vekt 0 i
  YAML med kommentar `# DEPRECATED-<session>`. Driver-feil returnerer 0.0
  per eksisterende kontrakt; ingen dynamisk vekt-reweight.

**Out-of-scope (eksplisitt):**
- Scalp-arkitektur (release-clock-orchestrator, surprise-z som schema-
  kontrakt, cross-asset-ledere, vol-regime-sizing-multiplier, real-time-
  pipeline) — egen Plan-S etter D2.
- C4 news_intel/F&G scoring — egen design-syklus etter ≥1 mnds data.
- Grade-terskel-rekalibrering — flagges hvis distribusjon drifter, men
  rekalibreres ikke i denne syklusen.
- Bot/signal_server-API-endringer, UI-endringer for nye drivere,
  backtest-rammeverk-utvidelser, live-cutover (Fase 13).
- Datakilder vurdert men ute: MOVE Index, crypto-spesifikke (funding rates,
  on-chain, ETF-flows, stablecoin supply), Bolsa de Cereales, AHDB UK,
  EU MARS, Cocobod / CCC.

### 19.4 Fase-tabell

| Fase | Innhold | Størrelse | Leveranse |
|---|---|---|---|
| **R1** | Audit + ADR-010 (horisont-pattern Alt 1) + ADR-011 (backfill-policy: 2010-cutoff, sekvensiell pacing 1.5s, engangs-skripts i `scripts/backfill/`, lov til å være "shitty"). Engine `_horizon`-propagering (~5 linjer + 1 micro-test). | S | `docs/horizon_refactor_audit.md`, ADR-010, ADR-011, engine-patch |
| **R2** | Feature-konvensjon: standard typer (`pct_12m`, `pct_36m`, `delta_5d_z`, `delta_20d_z`, `extreme_flag`, `approaching_extreme`, `surprise_z`, `time_to_release_min`, `post_release_drift_3d`, `extreme_contrarian_score`). Per-horisont test-strategi (3 typer: snapshot score-uendret, monotonisitet ved gradvis data-tilkomst, regime-shift fanger delta). Sesong-driver-mønster (driver-intern kalender-aware, ingen ny polarity). 2 ende-til-ende-eksempler: "Brent SWING onsdag 10:30 ET (post-EIA)" + "Corn yield-familie i juli". | M | `docs/driver_horizon_pattern.md` |
| **R3** | Refactor 3 referanse-drivere: `positioning_mm_pct`, `real_yield`, `crop_progress_stage`. Hver produserer flere horizon-features via samme funksjon, valgt via `params["_horizon"]`. Snapshot-tester må gi bit-identisk output for default-horizon. | M | 3 refactored drivere + snapshot/logiske/monotonisitet-tester |
| **R4** | Batch-vis migrering i 7 commits (én per familie-gruppe per rekkefølge over). Snapshot-tester må være grønne for hver batch. Score-uendret-garanti låst på 22 inst × 3 horisonter × 2 retninger. | L | Alle drivere migrert, snapshot grønt |
| **D0** | Smoke-tests for 12 nye + 5 utvidelser. Engangs-skripts i `scripts/smoke/`. **A14 DROPPED ved D0-start (paywall).** Inkluderer eksplisitt: (a) **B5 Yahoo `@F`-curve-feasibility** for calendar spreads (høyrisiko), (b) **A11 ICE TTF-status** (NaturalGas TFF-spørsmål). ADR-011 brukes som mal for backfill-skripts. | M | `docs/smoke_test_results.md` med per-kilde GO/RISK/SKIP/BLOCK |
| **D1** | **Tier 1.** ~~A1 Baker Hughes~~ (DROPPED 2026-04-29, ingen FRED-rute + endpoint-timeout). A2 AGSI (session 130, levert), A3 FAS Export Sales (LEVERT session 133 — api.fas.usda.gov-domain), A4 CFTC TFF + C1 (cot_legacy→cot_tff for finansielle, session 128), B1 yield-diff + kreditt/NFCI/NetFedLiq (session 129), B3 DXY-bytte Yahoo `DX-Y.NYB` (session 128). Hver kilde commit-isolert. YAML-diff per instrument med Pydantic-validering at familie-sum=1.0. | L | 5 nye fetchere/utvidelser + 8 nye drivere + YAML-diff |
| **D2** | **Tier 2.** A5-A7 ETF-holdings, A8 NOPA, A9 Drought Monitor, A11 ICE certified stocks, A12 AAII (mean-reversion driver-intern). B2 VIX-termstruktur, B4 HDD/CDD→NG (sesong-modulert), ~~B5 calendar spreads~~ **DEFERRED til Plan-S 2026-04-30 (session 134)** — kontrakts-rolling-infra hører hjemme i scalp-rammeverket. **C2 DROPPED — Eskom paywall, Platinum beholder seismic uendret.** C3 drop shipping (Cotton/Cocoa). | L | 5-7 nye fetchere + ~8 nye drivere + YAML-diff |
| **D3** | **Tier 3.** A10 Cecafé. ~~B5 calendar spreads metaller/korn~~ **DEFERRED til Plan-S 2026-04-30** (sammen med energi-B5). Backtest-validering av grade-distribusjon × 12mnd × 22 instrumenter; flagg drift > 25 pp i A+/A/B-andel for senere terskel-rekalibrering (ikke i scope). | M | 1-2 nye fetchere + grade-distribusjons-rapport |

**Estimat:** R1+R2 = 1-2 sessioner. R3 = 1 session. R4 = 3-4 sessioner.
D0 = 1-2 sessioner. D1 = 4-6. D2 = 4-6. D3 = 2-3. Totalt **16-24 sessioner**.

**Tag-strategi:** `v0.X.0-fase-R1`, `-R4`, `-D0`, `-D1`, `-D2`, `-D3`.
R2/R3 commits men ingen tag (mellom-fase).

### 19.5 Ny data — oversikt

**12 nye fetchere (Del A) — drop/defer-status etter D0+D1+D2:**
DROPPED: A1 (D1 V3, ingen FRED-rute), A7 (D2-prep, ingen daglig holdings),
A8 (D2-prep, LSEG-paywall), A11 (D2-prep, ICE er JS-SPA), A14 (D0, paywall).
LEVERT: A2 (130), A3 (133 — domain-korrigering), A5 (132), A6 (132 PARTIAL),
A9 (133), A12 (131). PARTIAL: A6 (D2, kun shares_outstanding-proxy).
GJENSTÅR: A4 (TFF, levert tidligere session 128), A10 (Cecafé Tier 3 — ikke
kritisk), A13 (BRL-ticker — levert session 128 D1 V3).

~~A1 Baker Hughes Rig Count~~ — **DROPPED 12.7**: V3-funn (session 127)
viste ingen FRED-rute (`baker+hughes+rig` = 0 treff i FRED) og direkte-
endpoint på `rigcount.bakerhughes.com` timer ut fra arbeidsmiljøet.
Vekten i Brent/CrudeOil/NaturalGas macro er liten (co-driver) og
arkitektonisk friksjon (manuell CSV-fallback fra dag 1) rettferdiggjør
ikke 12.7-scope. Vurderes på nytt i Plan-S hvis ny rute åpner. ·
A2 AGSI EU gas storage (API, 2011+, daglig, macro low_bull) ·
**A3 FAS Export Sales — LEVERT 2026-04-29 (session 133)**: USDA FAS
ESR via `api.fas.usda.gov/api/esr/...` (api.data.gov-konvensjon med
`X-Api-Key`-header). Session 132 prøvde feil domain
(`apps.fas.usda.gov/OpenData/...` — egen Azure-subscription kreves);
session 133 verifiserte at api.fas.usda.gov-domenet aksepterer
api.data.gov-key. Backfill: ~91500 rader (Corn/Soybean/Wheat/Cotton
× 11 MYs × ~40 land × ~52 uker, 2015-08 → 2026-04). Cotton-kode
korrigert fra 501 (CFD-symbol) til 1404 (FAS' "All Upland Cotton"
aggregat-kode). Driver `fas_exports` med default-trapp på WoW
%-endring i sum(weekly_exports) + R4 mode-utbygging. Wired i
Corn/Soybean/Wheat/Cotton cross-familier per § 19.5 Del C+
måltilstand. ·
A4 CFTC TFF (ny tabell-variant i eksisterende COT-Socrata-modul, 2010+) ·
**A5 GLD ETF holdings — LEVERT 2026-04-29 (session 132)**: full
historikk via SPDR `api.spdrgoldshares.com/api/v1/historical-archive`-
endpoint (Excel/xlsx, 2004-11-18→2026-04-28, 5593 rader, manuell
data klar i `bedrock manuell data/gld_holdings/`). Implementert som
felles `etf_holdings`-tabell + `etf_holdings_change`-driver med
ticker-param-dispatch (delt med A6 SLV). Wired i Gold macro@0.15 per
§ 19.5 Del C+ måltilstand. ·
**A6 SLV ETF holdings — LEVERT 2026-04-29 (session 132, PARTIAL via
proxy)**: iShares xls-endpoint gir kun `nav_per_share` +
`shares_outstanding` (5039 rader, 2006-04-21→2026-04-28). Ingen
direkte tonnes/ounces — `etf_holdings_change`-driver bruker
`shares_outstanding`-change som proxy (silver-per-share-decay er
~0.5 %/år expense ratio, neglisjerbar på WoW/MoM-skala; caveat
dokumentert i driver-docstring + MANIFEST). Wired i Silver macro@0.20
per § 19.5 Del C+ måltilstand. Delt schema/driver med A5 GLD. ·
~~A7 PPLT ETF holdings~~ — **DROPPED 2026-04-29 (D2-prep)**: abrdn
har lukket alle public APIer for PPLT (etter migrering fra Aberdeen
Standard). SEC EDGAR har kun kvartalsvise 10-K/10-Q (CIK 0001460235)
— ikke tilstrekkelig for daglig holdings. Yahoo OHLCV kan brukes som
prisreferanse men er ikke holdings-data. Reallokér 0.15-vekt i
Platinum macro (real_yield + dxy + vix + mining_disruption). Per
A1-presedens. ·
~~A8 NOPA Crush~~ — **DROPPED 2026-04-29 (D2-prep)**: NOPA distribuerer
månedlig crush-data via LSEG/Refinitiv-subscription, ikke offentlig.
Eneste public PDFs i NOPA WordPress media library er to compilation-
filer (CY2015 + CY2016) som dekker 11 måneder totalt — ikke nok for
10-år-rolling scoring. Soybean yield-familie var aldri NOPA-justert
(verifisert session 127 V1), så ingen YAML-revertering nødvendig.
Vekter forblir weather@0.25 + crop_progress@0.25 + wasde@0.50 = 1.0. ·
**A9 US Drought Monitor — LEVERT 2026-04-29 (session 133)**: USDM
ukentlig CONUS-aggregat fra `usdmdataservices.unl.edu/api/USStatistics/
GetDroughtSeverityStatisticsByAreaPercent` (gratis, ingen auth).
Backfill: 1096 rader (2015-12 → 2026-04). Default-input: ``d2_pct``
(% i D2+ severe+, cumulative). Driver `drought_monitor` med terskel-
trapp (5/15/25/40 → 0/0.25/0.5/0.75/1.0) + R4 mode-utbygging. Wired i
Corn/Soybean/Wheat/Cotton weather-familie @ 0.45 (weather_stress
1.00 → 0.55) per § 19.5 Del C+ måltilstand. ·
A10 Cecafé Brasil kaffe-eksport (PDF, 2002+, månedlig — Tier 3) ·
~~A11 ICE certified stocks~~ — **DROPPED 2026-04-29 (D2-prep)**: ICE
report-center er migrert til JS-rendert SPA. Alle `report/N`-URLer
returnerer SPA-skall, statiske PDF-URL-er gir 404. Krever Playwright-
scraping eller ICE Connect-subscription. Reallokér 0.25-vekt i
Coffee/Cocoa/Sugar outlook-familien til `seasonal_stage@1.00`. Per
A14-presedens. ·
A12 AAII Sentiment (CSV, 1987+, ukentlig tor) ·
A13 BRL=X (kun ny ticker i eksisterende `prices`-fetcher) ·
~~A14 Eskom load-shedding~~ — **DROPPED**: bekreftet bak betalingsmur.
Platinum beholder seismic uendret (C2 også dropped).

**5 utvidelser av eksisterende fetchere (Del B):**
B1 `fundamentals` med yield-diff + kreditt-spreads + NFCI + NetFedLiq ·
B2 `prices` med VIX-termstruktur (^VIX3M, ^VIX6M, ^VIX9D) ·
B3 DXY-bytte FRED→Yahoo `DX-Y.NYB` (sekundær FRED beholdes) ·
B4 `weather` til NaturalGas (HDD/CDD i NE-USA, TX/LA, Midwest) ·
B5 Calendar spreads beregnet fra eksisterende `prices` (Brent/CrudeOil/NG først).
**STATUS 2026-04-30 (session 134) — DEFERRED til Plan-S:** D0 GO-klassifisert
M1-continuous-tickere (BZ=F/CL=F/NG=F, 16.3y). Implementasjon krever
spesifikke kontraktsmåneder (CLM26.NYM-stil, ~8.4y RISK). Session
134 smoke-test viste at just-expired front-måned (K = mai) returnerer
0 rows fra Yahoo for Brent + WTI (NG fortsatt 21 rows), mens forward-
måneder M/N/Q/Z/M27 alle har 22 rows. Robust kontrakts-rolling-logikk
(velg ny front N dager før expiry, expiry-spec varierer per kontrakt)
er ny infrastruktur som passer naturlig med Plan-S real-time scalp-
rammeverk — calendar-spread regime-detection (back/contango) er
primært swing/scalp-feature. Kombinert med 8.4y under ADR-011 10-y
rolling-preferanse: defer beslutning. § 19.5 Del C+ structure for
Brent/CrudeOil/NaturalGas forblir `range_position@1.00` (uendret).
B5 re-vurderes i Plan-S sammen med scalp-arkitektur (release-clock,
surprise-z, cross-asset-ledere). Tier 2 (metaller/korn cal-spreads)
forblir også Plan-S-scope.

**6 mapping-refaktorer (Del C) — C2 DROPPED 2026-04-29 (D0):**
C1 cot_legacy→cot_tff for finansielle (følger A4) ·
~~C2 Platinum mining_disruption seismic→Eskom~~ — **DROPPED**: Eskom
paywall (jf. A14), Platinum beholder seismic uendret ·
**C3 Drop shipping for Cotton/Cocoa — LEVERT 2026-04-29 (session 133)**:
Cotton dekket via A3-commit-rekken (shipping 0.20 → 0; reallokerer til
dxy 0.65 + event 0.15 + fas_exports 0.20 = 1.00). Cocoa dekket
separat (shipping 0.20 → 0; reallokerer til dxy 0.85 + event 0.15 =
1.00; ingen fas_exports siden USDA FAS ikke rapporterer kakao). ·
C4 news_intel/F&G UI-only→scoring (UTE av scope, egen syklus) ·
C5 BRL→Coffee/Sugar (dekket i A13) ·
C6 Weather→NaturalGas (dekket i B4) ·
C7 Cotton ENSO uendret.

### 19.6 Per-horisont-mapping (Del E fra pre-plan)

Samme rådata brukes ulikt per horisont. Hver horisont-bevisst driver
produserer features som dekker relevante horisonter:

- **MAKRO (uker-måneder):** regime-klassifisering, posisjonerings-
  ekstremer, strukturell tilbud/etterspørsel. Features: 12m/36m-percentil,
  regime-flagg. Datafrekvens ukentlig-månedlig holder.
- **SWING (dager-uker):** katalysator + teknisk konfluens, pre-positioning
  før events, mean-reversion ved ekstremer. Features: 5d/20d-delta z-score,
  surprise-z, ekstrem-flagg. Datafrekvens daglig-ukentlig.
- **SCALP (minutter-timer):** vol-ekspansjon rundt scheduled releases,
  surprise vs consensus. Features: time-to-release, surprise-magnitude,
  vol-regime. **NB:** Full scalp-arkitektur er Plan-S — denne fasen leverer
  kun trivielle scalp-features (time_to_release_min, basic surprise_z fra
  wasde/eia hvis schema gir consensus).

Per-kilde × horisont-mapping (full tabell i pre-plan-dokument; bevart der):
A3 FAS (●●/●●●/●●●) **RE-AKTIVERT 2026-04-29**, A4 TFF (●●●/●●●/◐),
A12 AAII (●●●/●●●/–), B2 VIX-term (●●●/●●●/●●●),
B4 HDD/CDD (●●●/●●●/◐), ~~B5 cal-spreads~~ **DEFERRED til Plan-S 2026-04-30**.
~~A1 Baker Hughes~~ DROPPED 2026-04-29 (V3),
~~A7 PPLT~~ DROPPED 2026-04-29 (D2-prep, ingen daglig holdings),
~~A8 NOPA~~ DROPPED 2026-04-29 (D2-prep, LSEG-paywall),
~~A11 ICE~~ DROPPED 2026-04-29 (D2-prep, JS-SPA),
~~A14 Eskom~~ DROPPED (paywall).
`●●●`=primær, `●●`=sekundær, `◐`=marginal, `–`=ikke relevant.

### 19.7 Koordinering med sub-fase 12.6

Sub-fase 12.6 (data-driven rebalansering) er ÅPEN siden 2026-04-27.
Detached harvest startet, NASS 2010-2021-backfill kjører, neste mål er
analyzer + YAML-rebalansering basert på empirisk IC.

Sub-fase 12.7 må koordineres mot 12.6:

- **Spor R (refactor)** kan kjøre parallelt med 12.6 fordi score-output
  er bit-identisk før/etter (snapshot-tester garanterer det). 12.6 sin
  harvester ser ingen forskjell.
- **Spor D (nye drivere)** vil endre score-output → invalider 12.6 sine
  IC-resultater for berørte instrumenter/familier. Tre alternativer:
  - **Alt α — 12.6 først, så 12.7:** rebalanser eksisterende drivere
    først, deretter Spor R+D. Etter D3 må 12.6 re-kjøres for å rebalanser
    nye drivere. Dobbelt arbeid på rebalansering, men tydelig før/etter-
    måling per spor.
  - **Alt β — Spor R parallelt, 12.6 fullført + Spor D etter:** R kjører
    nå (uavhengig). 12.6 fullføres på dagens drivere. Spor D etter — ny
    12.6-runde for nye drivere.
  - **Alt γ — Pause 12.6, full 12.7, så ny 12.6 over alt:** stopp 12.6
    nå, kjør R1-R4 + D0-D3, kjør 12.6 én gang over hele settet. Lengst
    tid før neste rebalansering, men eliminerer dobbelt arbeid.

**Låst 2026-04-28: Alt γ.** Bruker-policy: ingen backtest før all data er
på plass. Sub-fase 12.6 er empirisk rebalansering (analyzer + setup-walker
over harvested data) — det ER backtesting. Derfor:
1. **Sub-fase 12.6 PAUSES** (detached harvest fortsetter i bakgrunnen,
   men analyzer/rebalansering venter)
2. **Spor R kjøres nå** (bit-identisk score, trygt parallelt med harvest)
3. **Spor D kjøres etter R** (nye fetchere + nye drivere, full backfill
   per ADR-010)
4. **Sub-fase 12.6 GJENÅPNES** etter D3 — ett rebalanserings-pass over
   det komplette systemet (gamle + nye drivere). Ingen dobbelt arbeid.

Estimert tid før første rebalansering er lengre enn Alt α/β, men
empirisk grunnlag dekker hele datasettet inkludert nye kilder.

### 19.8 Patch 2 — eksisterende drivere som mister vekt

Når en ny driver legges til en familie, må eksisterende drivere reduseres
slik at familie-sum=1.0. Patch 2 fra 2026-04-28 leverer en
verifikasjons-checklist (ikke autoritativ tabell — Del D fra pre-plan-
dokument er sannhetskilde). Pydantic-schema som validerer familie-sum=1.0
ved YAML-lasting er førstelinje-forsvar. Hvis Claude Code finner at
familie-sum ≠ 1.0 etter migrering, **stopp og spør** — ikke fiks stille.

Eksempler på reduksjoner ved D-fasene (ikke-uttømmende):
- `real_yield` 0.40→0.25 i EURUSD macro (yield-diff legges til, B1)
- `dxy_chg5d` 0.50→0.30 i EURUSD macro (yield-diff)
- `eia_stock_change` 0.50→0.30 i NaturalGas macro (rig_count + AGSI)
- `weather_stress` 0.25→0.20 i Soybean yield (NOPA legges til, A8)
- `dxy_chg5d` 0.55→0.45 i Corn cross (FAS legges til, A3)
- `shipping_pressure` droppes (0.20→0) i Cotton/Cocoa cross (C3)
- `seasonal_stage` 1.00→0.75 i Coffee/Cocoa/Sugar outlook (ICE certified stocks, A11)
- `weather_stress` 1.00→0.55 i Corn/Soybean/Wheat/Cotton weather (drought_monitor, A9)
- `vol_regime` 0.70→0.50 i Nasdaq/SP500 risk (vix_term_ratio, B2)
- `range_position` 1.00→0.55 i Brent/CrudeOil/NaturalGas structure (calspread, B5)

### 19.9 ADR-er som leveres i denne sub-fasen

- **ADR-010 — Horisont-bevisst driver-pattern.** Låser Alt 1 (YAML-styrt
  `horizon`-param via engine-propagering). Driver-kontrakt uendret;
  `_horizon`-key analog til `_direction` (ADR-006). (Nummerert 010 fordi
  ADR-009 er allerede tatt av cutover-readiness 2026-04-27.)
- **ADR-011 — Backfill-policy.** **10-år-rolling-cutoff** (myket opp
  fra 2010-01-01 i session 126 D0). Engangs-skripts i
  `scripts/backfill/<source>.py` (separat fra produksjons-`bedrock
  backfill <source>`-CLI). Sekvensiell HTTP med ≥1.5s pacing. Lov til
  å være "shitty": manuell kjøring, sleep mellom requests, ingen
  retry-policy beyond exponential backoff. Skal IKKE forurense
  produksjons-fetcher-koden.

ADR-012 (deprecation) + ADR-013 (failure-mode): **ikke i denne sub-
fasen**. "Sekundær" = vekt 0 i YAML + kommentar `# DEPRECATED-<session>`.
Driver-feil → 0.0 per eksisterende kontrakt.

### 19.10 Plan-S — scalp-arkitektur (utsatt referanse)

Plan-S leveres som egen syklus etter D2. Forutsetninger som må være på
plass:
- Minst 3 av Tier-1/2-fetchere live (FAS A3, NOPA A8, EIA, calendar_ff)
- Surprise-vs-consensus som strukturert numerisk schema (krever schema-
  endring av wasde + eventuelt ny event_outcomes-tabell)
- Release-clock-infrastruktur (sentralisert kalender for FAS tor 8:30 ET,
  NOPA mnd ~15., EIA ons 10:30 ET, WASDE mnd 12pm ET, NFP, FOMC, CPI)
- Cross-asset-ledere (BRL→Coffee/Sugar 1-5 min, DXY→Gold, US10Y→USDJPY,
  VIX→SP500)
- Trigger-driver-konseptet (event-trigget vs kontinuerlig) — påvirker om
  scoring-pipeline må splittes i batch (macro/swing) + real-time (scalp)
- Vol-regime-sizing-multiplier (ikke direksjon — sizing-input)
- **B5 calendar spreads (energi + Tier 2 metaller/korn)** — DEFERRED hit
  fra D2/D3 i session 134. Krever robust kontrakts-rolling-logikk
  (front-month select N dager før expiry, varierer per kontrakt-spec
  per commodity), passer naturlig med real-time scalp-rammeverket der
  back/contango-regime-detection er primært swing/scalp-feature.

Plan-S er ikke designet ferdig her. Reservert som own-track når Tier 1/2-
data har akkumulert tilstrekkelig.

---

## 20. Sub-fase 12.8 — Data-gjeld + cron-tuning + whitelist-revisjon

ÅPEN 2026-05-01 etter sub-fase 12.6 LUKKET (`v0.12.6-fase-12.6-LUKKET`).
Plan-S (§ 19.10) utsatt til 12.8 er ferdig — Plan-S' Tier 1/2-data
forutsetter at vi vet hva vi har og hva som faktisk oppdateres.

### 20.1 Bakgrunn

Bedrock har akkumulert 19 fetchere + 21 systemd-timere + ~30 SQLite-
tabeller siden Fase 6. Sub-fase 12.5+ portet 11 nye fetchere.
Sub-fase 12.6 rebalanserte 41 drivere mot 489k harvested rader. Men
ingen helhetlig audit av "hvilken data har hvert instrument fersk
tilgang til, og fungerer oppdaterings-mekanismen?"

Helse-monitor (sub-fase 12.6 § 12) flagger fetcher_freshness men:
- Aging-tersklene er flat (ikke per-fetcher tunet til faktisk
  publikasjons-cycle)
- `bedrock-fetch-enso.service` + `bedrock-monitor.service` failed
  siden ukjent dato — rødt blir bakgrunnsstøy
- Ingen oversikt over per-instrument coverage

Sub-fase 12.6 var også IC-aggregat (BUY+SELL × alle horisonter).
Det maskerer at samme kilde har ulik bruksverdi per horisont — § 20.2
introduserer horisont-bruk-prinsipper som låses for resten av 12.8.

### 20.2 Horisont-bruk-prinsipper

Datakilder har **ulik bruksverdi per horisont**. Sub-fase 12.8 må
kvalifisere coverage per (instrument × horisont), ikke bare per
instrument-aggregat.

**Macro (uker–måneder)** — regime-klassifisering + posisjonerings-
ekstremer + strukturell tilbud/etterspørsel. Datafrekvens ukentlig–
månedlig holder. Primærkilder:
- B1 (HY OAS, NFCI, NetFedLiq, VIX-termstruktur) → kreditt-/
  likviditetsregime, leder equity 1-4 uker
- fundamentals (FRED-basis) → yield/real/dollar/vol-regime
- COT-percentiler 12-mnd / 3-år (alle COT-varianter brukt som
  percentil) → spec-net ≥95th + commercial ≤5th = klassisk
  macro-reversal-setup
- TFF Asset Manager vs Leveraged Funds-divergens (sterkere enn
  legacy for finansielle)
- wasde / conab / unica / NOPA / crop_progress (sesong) / shipping
  (BDI) / AGSI (EU-gass) / Baker Hughes (shale) / ETF-holdings
  (investment demand) / LME (når implementert)
- ENSO (kun macro — for treg ellers)
- yield-differensialer 2Y/10Y, BRL-overlay for Coffee/Sugar

**Swing (dager–uker)** — katalysator + teknisk konfluens + weekly-
release-drift + mean-reversion ved ekstremer. Datafrekvens daglig–
ukentlig kritisk. Primærkilder:

Weekly-release-drift er hovedkilden:
- Mandag 16:00 ET: crop_progress → tirsdag-gap på korn
- Tirsdag: CFTC TFF/disagg/legacy (officially fre 15:30, dekker tirsdagen)
- Onsdag 10:30 ET: EIA → energi-direksjon for resten av uken
- Torsdag 8:30 ET: FAS Export Sales + Drought Monitor + AAII →
  grain-uka avgjøres her
- Fredag etter close: Baker Hughes + COT-release → mandag-gap

Pre-event positioning: calendar_ff er ryggraden — vet hvilke events
som kommer 5d frem. Mean-reversion ved ekstremer: AAII <20% bulls
eller >55% bulls, F&G ≤25 eller ≥75, COT-percentiler i ekstreme.
Vær/forecast-shifts: weather (7-14d forecast-update vs realized),
HDD/CDD for NG. Spread-bevegelse: B5 calendar spreads. Cross-asset-
divergenser: equity vs HY OAS, gull vs realrente, BRL vs Coffee.

**Scalp (minutter–timer)** — vol-ekspansjon rundt scheduled releases
+ surprise vs consensus + real-time event-detektorer. Trenger ikke
nye rådata, men release-kalender + forecast-data søkbart per minutt
rundt release. Primærkilder:

Scheduled releases er kjernen:

| Tid (ET) | Event | Instrumenter |
|---|---|---|
| Tir 8:30 | CPI, PPI, retail sales | Alle 22, særlig DXY/indekser/krypto |
| Ons 8:15 | ADP | Indekser, FX |
| Ons 10:30 | EIA crude/gas | Brent, CrudeOil, NaturalGas |
| Ons 14:00 | FOMC (8x/år) | Alle 22 |
| Tor 8:30 | Initial claims, FAS Export Sales | Indekser, grain |
| Tor varierer | ECB, BoE, BoJ | Respektiv FX |
| Fre 8:30 | NFP (1/mnd) | Alle 22 |
| Fre 12:00 | WASDE (1/mnd) | Alle agri |
| Mnd ~15. | NOPA Crush | Soybean |

Vol-regime for sizing: B2 VIX9D/VIX-ratio er primær. VIX9D > VIX
(backwardation) = høy realisert vol = redusere størrelse. VIX9D <<
VIX = lav vol-forventning = kan øke størrelse. Real-time event-
detektorer: seismic (USGS GeoJSON streamer M≥4.5), news_intel når
scored. Surprise vs consensus: calendar_ff har forecast/prev —
selve scalpen drives av actual vs forecast. Cross-asset-leder:
BRL leder Coffee/Sugar 1-5 min, DXY leder gull, VIX leder SP500,
US 10Y-yield leder USDJPY.

**Tre nøkkel-innsikter for 12.8-audit:**

1. **Samme kilde, helt ulik bruk per horisont.** COT er macro-
   percentil, swing-delta, og scalp-mandag-gap-trigger. Coverage-
   rapporten må skille mellom "har data" og "har data brukbart for
   horisont X" — en månedlig-kilde dekker M men ikke Sc selv om
   feltet er fersk.

2. **Scalp trenger lite ny rådata, men struktur rundt calendar_ff.**
   Forecast/prev/actual må være søkbart per minutt rundt release.
   Coverage-rapporten må eksplisitt sjekke om calendar_ff har
   forecast-felt populert (ikke bare event_ts + impact). calendar_ff
   er undervurdert i nåværende oppsett.

3. **Macro og swing overlapper i kilder men ikke i features.** Macro
   tenker percentil/regime, swing tenker delta/ekstrem-reversering.
   Det betyr at samme fetcher må produsere både rolling-percentile
   og rolling-z-score-features — ikke bare nivå-tall.

**Kilde × horisont-mapping** (●●● primær / ●● sekundær / ◐ marginal /
– ikke relevant):

| Kilde | M | S | Sc | Hovedbruk |
|---|---|---|---|---|
| prices (EOD OHLC) | ●●● | ●●● | – | M: trend-regime/MA-stack. S: S/R, breakouts. Sc krever intraday (ikke i scope). |
| cot_disagg/legacy/tff/ice/euronext | ●●● | ●●● | ◐ | M: 12m-percentil, comm/spec-divergens. S: ukentlig delta, ekstrem-reversering. Sc: kun mandag-gap fra fre-release. |
| fundamentals (FRED-basis) | ●●● | ●● | – | M: regime (yield/real/dollar/vol). S: 5d/20d-divergens. |
| B1 (HY/IG OAS, NFCI, NetFedLiq) | ●●● | ●● | – | M: kreditt-/likviditetsregime — leder equity 1-4 uker. S: spread-breakout som trigger. |
| B1 yield-diff (FX) | ●●● | ●● | ◐ | M: strukturell FX-driver. S: 2Y-diff-momentum. Sc: kun rundt CB-events. |
| B2 VIX-termstruktur (VIX9D/3M/6M) | ●●● | ●●● | ●●● | M: contango/backwardation-regime. S: regime-switch. Sc: VIX9D/VIX-ratio er primær risk-on/off-meter intraday. |
| weather (Open-Meteo) | ●● | ●●● | ◐ | M: sesong-anomali. S: 7-14d forecast-vs-realized. Sc: weekend-forecast-update → mandag-gap. |
| enso (NOAA ONI) | ●●● | – | – | M: 6-12 mnd outlook tropisk agri. For treg for swing/scalp. |
| wasde (mnd, 12pm ET) | ●●● | ●●● | ●●● | M: balance-sheet-trend. S: post-WASDE drift 3-5d. Sc: release-event. |
| crop_progress (man 16:00 ET) | ●● | ●●● | ●● | M: pace vs 5yr. S: G/E-rating endring. Sc: tirsdag-gap. |
| shipping (BDI) | ●●● | ●● | – | M: global trade-regime. S: 20-30d trend. |
| calendar_ff | ◐ | ●●● | ●●● | M: forecast-bias. S: pre-positioning. Sc: KJERNE-DATA. |
| eia_inventories (ons 10:30 ET) | ●● | ●●● | ●●● | M: storage-trend. S: build/draw vs forventning. Sc: ons-event for crude/NG. |
| comex inventories | ●●● | ●● | – | M: lager-trend. S: divergens vs pris. |
| LME-lager (WIP) | ●● | ●●● | ◐ | M: industriell-metaller-balanse. S: cancelled warrants som leading. Sc: kun ved store daglige bevegelser. |
| seismic (USGS) | – | ●● | ●●● | Real-time event-detector — primær scalp-trigger for Cu/Au/Ag når M≥6 i Chile/Peru. |
| conab | ●●● | ●● | ◐ | M: Brasil-tilbud. S: revisjons-drift. Sc: release-day på Coffee/Sugar. |
| unica (halvmnd) | ●● | ●●● | ●●● | M: sukker-balanse. S: bi-weekly surprise. Sc: release-move. |
| news_intel | ●●● | ●●● | ●●● | M: tematisk-count. S: cluster-deteksjon. Sc: breaking-news-katalysator (når scored). |
| crypto_sentiment (F&G) | ●●● | ●●● | – | M: regime. S: ≤25/≥75 mean-reversion-edge. |
| A1 Baker Hughes (fre etter close) | ●●● | ●● | ◐ | M: shale-tilbud. S: 4-8 uker trend. Sc: kun fre-close-tilt. |
| A2 AGSI (EU gas) daglig | ●●● | ●● | – | M: vinter-balanse. S: % full vs 5yr. |
| A3 FAS Export Sales (tor 8:30 ET) | ●● | ●●● | ●●● | M: kumulativt vs USDA-target. S: ukentlig surprise. Sc: tor-event for grain. |
| A4 CFTC TFF | ●●● | ●●● | ◐ | Som COT — Asset Manager vs Leveraged Funds-divergens er sterkeste positioning-signalet for finansielle. |
| A5-A7 ETF-beholdninger | ●●● | ●● | – | M: investment-demand-trend. S: divergens vs pris. |
| A8 NOPA Crush (mnd ~15.) | ●●● | ●●● | ●●● | M: crush-pace. S: mnd-surprise. Sc: release-event for soybean. |
| A9 Drought Monitor (tor 8:30) | ●● | ●●● | – | Som weather, ukentlig D0-D4-klasse. |
| A10 Cecafé (mnd) | ●●● | ◐ | – | M: Brasil-eksport. |
| A11 ICE certified stocks | ●●● | ●● | – | M: deliverable-trend. S: lav-lager-pricing-pressure. |
| A12 AAII Sentiment (tor) | ●●● | ●●● | – | M: kontrarian-regime. S: ekstrem-readings. |
| A13 BRL=X | ●●● | ●●● | ●● | M: Brasil-overlay Coffee/Sugar. S: 5-20d-move. Sc: leder Coffee/Sugar intraday. |
| B5 calendar spreads | ●● | ●●● | ●●● | M: strukturell carry. S: spread-tightening/widening. Sc: M1-M2 reaksjon på inventory-event. |

### 20.3 Sub-tasks

| Sub-task | Innhold | Sessions | Estimat |
|---|---|---|---|
| **A1** Kartlegging | Per-instrument data-coverage-rapport per horisont | 139 | 4-6t |
| **A2** Kode-fixer | Plug rimelige gaps (WASDE pre-2019, schema-drift, AAII bug, comex/cafe-ingest, fas_esr docstring, disease_pressure tester) | 140 | 4-6t |
| **B** Cron-tuning | Per-fetcher refresh-cycle audit + smart-skip-verifisering + helse-rydding + FRED-fail-policy | 141 | 3-5t |
| **C** Whitelist-revisjon | Per-(instrument × horisont) coverage-score → trim bot-whitelist per-horisont | 142 | 4-6t |

Totalt ~15-23t / 4 sessions. Plan-S åpnes etter C.

### 20.4 Sub-task A1 — Kartleggings-rapport (session 139)

**Mål:** Én Markdown-rapport som per instrument viser:
1. Hva vi har av data (tabeller, rader, tidsspenn)
2. Hva som er konfigurert til oppdatering (fetch.yaml + systemd-timer)
3. Om oppdateringen faktisk fungerer (siste-rad-dato vs forventet)
4. Per-(instrument × horisont)-coverage-vurdering: kan dette
   instrumentet handles på horisont X?

**Format:**

- **Sammendragstabell 1 — per-horisont-coverage:** én rad per
  instrument × tre kolonner (M / S / Sc) med ✓/⚠/✗ flagg basert på
  primærkilder for hver horisont. Gir umiddelbart svar på "kan
  dette instrumentet handles på horisont X?"
- **Sammendragstabell 2 — per-kilde-helse:** én rad per fetcher,
  cron-tid, sist oppdatert, helse-flagg. Gir oversikt over
  pipeline-helse uavhengig av instrument.
- **Drill-down per instrument:** tabell med rader/tidsspenn/
  cron-konfig/sist-oppdatert/helse-flag per data-kategori, +
  per-horisont-vurdering (M/S/Sc adekvat?).

**Helse-flagg per kilde-cycle:**

| Cycle | Forventet refresh | Aging-buffer | Rødt hvis |
|---|---|---|---|
| Daglig | 24t | +12t | siste rad >36t |
| Ukentlig | 7d | +2d | siste rad >9d |
| Månedlig | 30d | +10d | siste rad >40d |
| Halvmånedlig | 14d | +6d | siste rad >20d |
| Event-basert | varierer | — | ingen ny rad >7d |

**Per-horisont-kvalifisering:**

| Horisont | Krav for "✓" |
|---|---|
| **Macro** | Har ferske COT-percentiler (12mnd) + ferske fundamentals (FRED-makro relevant for asset-klassen) + ferske strukturelle (wasde/conab/etc). Månedlig oppdatering nok. |
| **Swing** | Har komplett weekly-release-cycle for asset-klassen (e.g. grain: crop_progress + WASDE + FAS + drought + COT alle ferske innen forrige uke). Daglig-ukentlig oppdatering kritisk. |
| **Scalp** | Har calendar_ff med forecast/prev-felt populert + event-tracker for relevante release-times for asset-klassen. Real-time-data er prioritet. |

**Output:**
- `scripts/report_data_coverage.py` (nytt verktøy, kan re-kjøres senere)
- `docs/data_coverage_2026-05-01.md` (rapport + sammendrag)
- Ingen kode-endringer i `src/`

### 20.5 Sub-task A2 — Kode-fixer (session 140)

Basert på A1-funn, plugge gaps som er innen rekkevidde:

- **WASDE pre-2019**: utvide ESMIS-paginering-walker (~1-2t)
- **Schema-drift**: 3 manglende harvester-tabeller i `schemas.py`
- **AAII bull_bear_spread fetcher-bug** (audit Sjekk 9.6): fix
  formel + backfill 537 rader
- **Manuell-data ingest-gaps** (audit Sjekk 10):
  - `comex`-subkommando i `ingest_manual_data.py` (KRITISK 1)
  - `cafe`-subkommando for CONAB Café-boletins
  - README i `cafe_boletins/`, `comex data/`, `conab_boletins/`
- **`fas_esr.py:134`** stale docstring
- **disease_pressure** test-coverage til ≥7 tester
- **calendar_ff forecast/prev-felt audit**: hvis A1 viser at felt
  ikke er populert konsekvent, fix fetcher (kritisk for scalp).

Akseptér og dokumenter (ikke kode-fix denne runden):
- CFTC Brent/Copper pre-2022 (fundamentalt gap)
- CONAB Café-PDF historikk (IP-throttled — ny strategi i Plan-S)
- UNICA archive (ingen public API)
- PPLT/NOPA droppet
- LME-lager (WIP — egen Plan-S-task hvis prioritert)

### 20.6 Sub-task B — Cron-tuning + helse-rydding (session 141)

1. **Per-fetcher refresh-cycle audit**: cron-tid vs faktisk
   publikasjons-tid. Eksempel: comex publiserer T-1 daglig man-fre;
   nåværende cron `0 22 * * 1-5` Oslo passer; verifiser smart-skip
   ikke gjør duplicate kall.
2. **Smart-skip-verifisering**: hver fetcher må sjekke
   `latest_observation_ts(table, key)` før HTTP-kall. Verifisert i
   cot_ice + comex + eia; sjekk resten.
3. **Stale_hours-tuning**: per fetcher i `fetch.yaml` justeres slik
   at monitor ikke flagger falskt rødt. Tersklene fra § 20.4 er
   utgangspunkt.
4. **Helse-rydding**:
   - `bedrock-fetch-enso.service` failed → diagnose + fix
   - `bedrock-monitor.service` failed → diagnose + fix
   - 5 aging fetchers (comex, cot_disaggregated, cot_ice, cot_legacy,
     fundamentals): sjekk om kilden faktisk er stale eller cron er
     for streng
5. **FRED-fetcher hard-fail-policy**: hva skjer hvis API-key revokert
   eller series fjernet? Default er nå silent silence. Definér
   policy: hard-fail eller graceful-degrade.

### 20.7 Sub-task C — Whitelist-revisjon (session 142)

1. **Per-(instrument × horisont) coverage-score** (basert på A1):
   - Macro-score: COT-percentil-coverage + FRED-coverage +
     asset-strukturell-coverage
   - Swing-score: weekly-release-cycle-coverage for asset-klassen
   - Scalp-score: calendar_ff forecast-coverage + real-time-detektorer
2. **Threshold per horisont:**
   - Macro krever: ≥3 år CFTC, ≥5 år priser, ≥3 av 5 strukturelle
     kilder ferske
   - Swing krever: alle weekly-release-fetchere fungerende for
     asset-klassen (per horisont-mapping § 20.2)
   - Scalp krever: calendar_ff forecast-coverage ≥80% for relevante
     release-typer + asset-klassens primær-real-time-kilder ferske
3. **Trim-runde**: instrumenter under terskel for HORISONT pauses
   fra bot-whitelist KUN på den horisonten. Et instrument som
   kvalifiserer for MAKRO men ikke SCALP fortsetter å scores på
   MAKRO/SWING. Krever schema-endring i `bot_whitelist.yaml`:
   per-horisont-flagg istedenfor flat liste.
4. **Ressursbesparelse**: paused (instrument × horisont)-kombinasjoner
   ekskluderes fra signals_bot for den horisonten, men beholder
   pris-fetching + harvest for re-aktivering når historikk
   akkumuleres.

### 20.8 Stop-criterion sub-fase 12.8

- A1: rapport committet, helse-flagg per (instrument × horisont) er
  reproduserbar
- A2: kode-fixer landet, regresjons-tester grønne, schema komplett
- B: alle 19 fetchere har riktig cron + smart-skip + tunet
  `stale_hours`; monitor returnerer grønt ved health-check
- C: per-(instrument × horisont) whitelist-revisjon committet;
  signal_bot.json kjører kun mot godkjente kombinasjoner

Tag: `v0.12.8-fase-12.8-LUKKET`. Plan-S kan åpnes umiddelbart etter.

### 20.9 Relasjon til andre låser

- **PLAN § 19.3 trading-logikk-låser**: ufravikelige.
- **ADR-007 sentiment-cap**: paused crypto_sentiment + news_intel
  påvirkes ikke av 12.8 (de er allerede UI-only inntil scoring).
- **§ 12.6-snapshot-baseline**: 12.8 endrer ikke YAML-vekter, så
  snapshot er stabilt.
- **Plan-S** (§ 19.10): forutsetninger fra Plan-S som overlapper
  med 12.8 (release-clock-infrastruktur, surprise-vs-consensus-
  schema, cross-asset-ledere) tilhører Plan-S og adresseres ikke
  i 12.8 ut over coverage-flagging.

---

## 21. Sub-fase 12.9 — bedrock-bot cutover

**ÅPEN 2026-05-01** etter sub-fase 12.8 LUKKET. Erstatter scalp_edge-
boten med bedrock-bot som cTrader-trading-grensesnitt. Trigger:
scalp_edge har vært i auth-failure crash-loop (CH_ACCESS_TOKEN_INVALID)
siden 28. apr. Bruker bekreftet retire av scalp_edge.

Full operasjonell plan: `docs/bedrock_bot_cutover.md`.

### 21.1 Eksisterende state

**Bedrock-bot (`src/bedrock/bot/`, 4950 linjer, 11 moduler)** er en
komplett refaktor av scalp_edge per Fase 8 (sessions 41-46). Allerede
ferdig: `ctrader_client.py`, `entry.py`, `exit.py`, `sizing.py`,
`safety.py`, `instruments.py`, `comms.py`, `state.py`, `__main__.py`,
`config.py`, `instruments.py`.

### 21.2 Sub-tasks

| Task | Innhold | Status | Estimat |
|---|---|---|---|
| **D1a** | Schema-adapter `signals_bot.json` → bot-format | ✓ LANDET (`649f429`) | — |
| **D1b** | HTTP `/bot/signals`-endpoint i bedrock-server | ✓ LANDET (`649f429`) | — |
| **D2** | Refresh-token-flow i `ctrader_client.py` | PENDING | 2-3t |
| **D3** | `bot.yaml`-config + secrets-env-mønster | PENDING | 30 min |
| **D4** | Systemd user-service `bedrock-bot.service` | PENDING | 30 min |
| **D5** | End-to-end demo-test | PENDING | 1-2t |
| **D6** | scalp_edge retire (disable timer + arkiver) | PENDING | 30 min |

### 21.3 D1 — adapter + endpoint (LANDET 2026-05-01)

Ny modul `src/bedrock/signal_server/bot_adapter.py` transformerer
bedrocks flat-list `signals_bot.json` til wrapped object med
`schema_version="2.1"` (matcher bot's SUPPORTED_SCHEMA_VERSIONS).
Per-horisont defaults hard-kodet for SCALP/SWING/MAKRO. Filter:
kun `published=true`. Ny route `/bot/signals` (blueprint
url_prefix=`/bot`) som leser `signals_bot.json` fra
`ServerConfig.signals_bot_path` og returnerer adapter-output.
29 nye tester (22 adapter + 7 endpoint). Pyright 0/0/0.

### 21.4 D2 — refresh-token-flow

cTrader-tokens expirer ~30 dager. Eksisterende bot leser kun
`CTRADER_ACCESS_TOKEN` og krasjer ved expired (CH_ACCESS_TOKEN_INVALID).

Fix: ved auth-fatal-error, kall
`https://connect.spotware.com/apps/token` med
`grant_type=refresh_token` + `refresh_token`, oppdater
`~/.bedrock/secrets.env` med ny access + refresh, retry auth
**én gang** før `_fatal_exit(78)`.

Implementering:
- Add `refresh_token: str | None = None` til `CtraderCredentials`
- Add `CTRADER_REFRESH_TOKEN` (valgfri) i `load_credentials_from_env`
- Add `refresh_ctrader_access_token(creds) -> dict` modul-level helper
- Add `update_secrets_env_var(key, value, path)` helper i
  `bedrock.config.secrets`
- I `_on_error_res`: `if creds.refresh_token and not _refresh_attempted: try refresh, retry`
- Tester: simulert auth-fail med mock-HTTP-response

### 21.5 D3 — bot.yaml + secrets-env-mønster

Ny `config/bot.yaml` med:
- `signal_url: http://127.0.0.1:5100/bot` (treffer `/bot/signals`)
- Mode-default: `demo`
- Polling-intervall: 60s normal / 20s SCALP-active
- Daily-loss-limits, position-sizing-defaults
- `signal_api_key_env: null` (lokal trafikk, ingen API-key trengs)

Bekrefte at `~/.bedrock/secrets.env` har 5 cTrader-vars:
`CTRADER_CLIENT_ID/CLIENT_SECRET/ACCESS_TOKEN/REFRESH_TOKEN/ACCOUNT_ID`.

### 21.6 D4 — systemd user-service

Ny `~/.config/systemd/user/bedrock-bot.service`:
- ExecStart: `python -m bedrock.bot --demo`
- EnvironmentFile: `~/.bedrock/secrets.env`
- Restart: on-failure (men ikke ved exit 78 = FATAL — operatør må
  generere ny token manuelt hvis refresh også feiler)
- After: network-online.target + bedrock-server.service

### 21.7 D5 — demo-test ≥24t

Skjerm-overvåking under første demo-test. Verify:
- Auth-flow OK (først direkte, deretter refresh-test ved simulert
  expiry)
- Signal-fetch (parse + schema 2.1 + ingen warnings)
- Ordre-plassering på 1 paper-money-trade
- TP/SL-hit + position-close
- Daily_loss-persistens etter restart

### 21.8 D6 — scalp_edge retire

Etter ≥24t grønt på bedrock-bot:
- `systemctl --user disable --now scalp_edge.*` (alt)
- Arkiv-tag: `scalp-edge-final-2026-05-XX` på siste fungerende
  scalp_edge-commit
- Behold `~/scalp_edge/` katalog som referanse (ikke slett)
- Update STATE.md med retire-status

### 21.9 Stop-criterion sub-fase 12.9

- D2: refresh-flow tester grønt (mock + livet test)
- D3+D4: bot starter via systemctl uten env-feil
- D5: ≥24t demo uten crash, ≥1 trade plassert + lukket
- D6: scalp_edge disabled

Tag: `v0.12.9-fase-12.9-LUKKET`. Etter dette starter Plan-S
(§ 19.10) eller sub-fase 12.10 (resterende UI-arbeid + WASDE pre-2019
+ comex/cafe ingest hvis prioritert).

### 21.11 Avdekkede follow-ups (logget for Plan-S / 12.10)

Følgende er avdekket under D5-implementasjon 2026-05-01 og er
**ikke** gating for å lukke 12.9 — de blokker SCALP-ytelse, men
30-min-cadence (D5+ commit `bab3370`) er en betydelig forbedring
fra 24t-statusen som var blocker.

**Fase 2 — `signals-all` ytelse (kritisk for SCALP <5 min cadence)**

**LEVERT 2026-05-01 (commit `f606ca5`).** Profilering avdekket at
89 % av tiden gikk i YAML-loading — `find_instrument` ble kalt 24x
per instrument og hver kall lastet alle 22 YAMLer fra disk.
`@lru_cache(maxsize=8)` på `_load_all_cached`-wrapper løste dette.

Effekt:
- Gold-score (1 inst): 79.3s → 12.4s (6.4x)
- `bedrock signals-all --bot-only` (17 inst): 8m19s → 1m16s (6.5x)
- SCALP-staleness: ≤30 min → ≤5 min (intraday-timer satt fra
  `06..21:00/30:00` til `06..21:00/5:00`, 960 fyringer/uke)

Gjenstående optimalisering (kan utsettes til empirisk behov dukker
opp; 1m16s møter § 20.2 SCALP-cadence-krav):
- pandas read_sql 4.5s (247 calls): per-driver DB-cache mulig
- analog _knn 4s (12 calls): algoritmisk
- positioning _load_metric_series 3s (12 calls): DB-cache-mulighet

Per-instrument parallellisering var planlagt som backup-strategi
men er ikke nødvendig.

**Fase 3 — per-horisont drivere (§ 20.2)**

**LEVERT 2026-05-01** (commits `c901162`, `9824247`, `4740d51`).
Schema utvidet med `DriverSpec.horizons: list[str] | None`; engine
filtrerer drivere før iterasjon og re-normaliserer gjenværende
vekter slik at familie-summen bevares. Bakoverkompatibelt — drivere
uten `horizons`-felt gjelder alle 3 horisonter (status quo for 22
inst utenom de 3 driverne under).

YAML-migrasjon (per § 20.2-eksplisitte drivere):
- event_distance → [SCALP, SWING] på alle 22 instrumenter
  (calendar_ff KJERNE for scalp + pre-event swing, ikke macro-input)
- aaii_extreme → [SWING] på Nasdaq + SP500 (sentiment mean-
  reversion er swing-fenomen)
- vix_term_ratio var allerede droppet i session 138 — ikke kandidat

Engine-renormalisering: når event_distance filtreres ut av MAKRO-risk
(eks. Gold), skaleres vol_regime fra spec-vekt 0.7 → effective 1.0
slik at family-summen forblir 1.0. DriverResult.weight rapporterer
effective_weight (etter renorm), gjenspeiler hva som faktisk teller.

UI-overflate: modal driver-trace fikk ny "HORISONT"-kolonne med
M/Sw/Sc-chips per driver. Drivere uten filter viser "alle"
(grå meta-tekst). Live-verifisert i preview at Gold SWING/risk har
event_distance med Sc+Sw-chips, mens MAKRO-versjonen filtrerer den
ut helt.

Tester: 7 nye engine-tester (filter-skip, renorm-bevarelse, partial-
values, empty-family, agri-no-horizon, status-quo-bakoverkomp). Alle
36 eksisterende engine-tester forblir grønne.

Snapshot-baseline regen + grade-distribusjons-rapport: 26/132
grade-flips, fordelt fx 11 / metals 10 / energy+crypto+indices 5 /
agri 0. Innen normal-rekkevidde for skjema-endring + drift; ingen
systematisk asset-class-bias-flipp. Ny baseline låst som anker.

**Mindre debt-poster (kosmetisk)**

- secrets.env har 3 `export `-prefiks-linjer (FRED/NASS/EIA-keys) som
  systemd ignorerer med warning. Bot trenger ikke disse keys; warning
  er støy. Trivielt fix: `sed -i 's/^export //' ~/.bedrock/secrets.env`.
- pyOpenSSL versjons-mismatch: `ctrader-open-api 0.9.2` krever 24.1.0,
  vi har 26.1.0. Fungerer, men kan pinnes hvis annet pakkearbeid
  setter det på prøve.

### 21.10 Hva tas fra scalp_edge

| scalp_edge-fil | bedrock-bot-status |
|---|---|
| `trading_bot.py` (2977 lin) | ✓ Refactored til 11 moduler i `src/bedrock/bot/` |
| `signal_server.py` (974 lin) | ⚠ ERSTATTET av `/bot/signals`-route (D1) |
| `get_token.py` | ⚠ Beholdes som standalone-script for OAuth-bootstrap |
| `start_bot.sh` | ✗ ERSTATTES av systemd-service (D4) |
| `signal_log.json` | ✓ bedrock-bot logger til `state.py` |
| `daily_loss_state.json` | ✓ `state.py` har persistens |
| `latest_signals.json` | ✓ Bedrock genererer `signals_bot.json` |
| `live_prices.json` | ✗ Bot fetcher live priser fra cTrader direkte |

---

## 22. Sub-fase 12.10 — driver-rebalansering (LUKKET 2026-05-02)

**Status:** LUKKET 2026-05-02 (tag `v0.12.10-fase-12.10-LUKKET`). Bunker
1-9 alle taggget med per-bunke-tag (`v0.12.10-bunke1` ... `v0.12.10-bunke9`).

**Levert:**
- ~50 nye drivere registrert + smoke-testet mot live DB (i moduler
  `macro_bunke3.py` / `macro_bunke4.py` / `macro_bunke6.py` /
  `macro_bunke7.py` / `macro_bunke8.py` + utvidelser i `risk.py`,
  `macro.py`, `agronomy.py`)
- 3 bug-fixer (COT released_at look-ahead, min_samples-guards på 4
  sparsom-data-drivere, event_distance audit-vakter)
- 2 driver-default-bumps (#33 mining_disruption M5.5, #35 comex_stress
  min_samples=180)
- ~60 000+ nye rader backfilt på 30+ datakilder (FRED/Yahoo/NOAA/ICE-
  softs/EIA/USDM-states/AGSI)
- 100+ nye tester, pyright src/: 0 errors

**DEFERRED (~17 drivere/endringer for senere session):**
- *_surprise (#5): FF mangler actual; krever cross-source-arkitektur
- ism_pmi_level (#10): FRED NAPMPMI deprecated
- CBOE pcr/term_curve + NOAA enso_forecast (#16/#17): ikke i Yahoo-feed
- NASS yield + grain_stocks (#20): QuickStats-utvidelse
- FAS china/eu (#21): YAML-wiring follow-up
- ALSI + IIP REMIT (#24/#25): nye GIE-routes
- cot_concentration_top4 + cot_swap_dealer_skew (#26): schema-utvidelse
- Treasury auctions (#27): ny fetcher
- crypto_sentiment_extreme (#29): vent til 100+ rader
- YAML-wirings av alle nye drivere (#30/#31/#32/#34/#42): per § 22.1
  live-demo-validering først
- Driver-impl-rewrites (#36/#37/#38/#39/#40/#41): substantial refactors

**Følger:** YAML-wirings + DEFERRED-arbeid tas i egne senere sessioner
basert på empirisk demo-resultat per § 22.1 ("validering mot live-demo").

D6 (scalp_edge retire) tas som egen senere task når operatør sier OK;
ikke gating for 12.10.

**Kjørte på demo-konto hele veien — ingen live-cutover under 12.10.**

### 22.1 Beslutninger låst (2026-05-02)

- **Ingen familie-restrukturering.** Beholde flat YAML (`trend/positioning/macro/structure/risk/analog/...`). Nye drivere plasseres i eksisterende familier; én ny familie `event` for `*_surprise`-drivere fordi ingen eksisterende familie passer.
- **Backtest droppet i denne sub-fasen.** ALFRED-vintage-migrasjon utelates (var backtest-relevant). All validering skjer mot live-demo via signals_bot.json + faktiske trades.
- **GIE-key dekker AGSI+ + ALSI + IIP** (verifisert 2026-05-02). Én key, tre tjenester. Lagret i `~/.bedrock/secrets.env` som `BEDROCK_AGSI_API_KEY`.
- **Ingen ADR.** Driver-utvidelser uten arkitektonisk skifte (regime-vekting droppet for 12.10).
- **Alle bug-fixer + alle ~67 nye drivere skal leveres.** Separat commit per driver/endring for enkel revert/bisect.
- **Snapshot-baseline regen etter hver bunke-leveranse** (uke 1 / uke 2 / uke 3-4 / måned 2).

### 22.2 Bunker (rekkefølge bestemt av Claude per ditt mandat)

**Bunke 1 — Bug-fixer (uke 1, alle 3 sammen):**
1. COT `released_at`-fix (3-dagers look-ahead) — schema-utvidelse + filter-logikk på 7 drivere
2. `min_samples`-guards på sparsom-data-drivere: unica_export_change, disease_pressure, export_event_active, comex_stress
3. `event_distance` future-actual verifisering

**Bunke 2 — Lavt-hengende frukt (uke 1, parallelt):**
4. `cot_ice_cocoa/coffee/sugar/wheat` — wire 4 drivere mot eksisterende ICE COT-data
5. `nfp_surprise`, `cpi_surprise`, `gdp_surprise`, `pce_surprise` — calendar_ff har forecast/actual-felt **DEFERRED 2026-05-02 (Bunke 2 finale):** Forex Factory `ff_calendar_thisweek.json` har KUN forecast+previous-keys, ikke actual. FRED-serier PAYEMS/CPIAUCSL/GDP/PCEPI er heller ikke i DB. Surprise-driverne krever cross-source join (FF.forecast × FRED.actual eller alternativ feed med actual-felt). Re-åpnes i egen session når data-arkitektur er valgt.
6. `news_intel_severity_veto` — veto-driver fra eksisterende news_intel-tabell

**Bunke 3 — FRED-utvidelse (uke 2):**
7. `t10y3m`, `t_bill_3mo_yield` (yields)
8. `hy_oas_change` (credit) — `BAMLH0A0HYM2`
9. `initial_claims_z`, `continuing_claims_z` (labor)
10. `ism_pmi_level`, `industrial_production_yoy`, `cfnai_3mma`, `umich_sentiment_z`, `jolts_openings_yoy` (growth)
11. `anfci_z` (erstatter nfci_change), `m2_yoy` (liquidity)
12. `vix9d_vix_ratio` (volatility)
13. `dollar_index_breadth` (fx)
14. `fomc_decision_distance` — calendar_ff under-signal

**Bunke 4 — Yahoo + CBOE + NOAA (uke 3):**
15. `move_index_z`, `vvix_z`, `gvz_z`, `ovx_z` (Yahoo)
16. `cboe_skew_z`, `cboe_pcr_total_extreme`, `cboe_pcr_equity_only`, ~~`cboe_vix_term_curve`~~ (CBOE) — *vix_term_curve DROPPED Spor F3 2026-05-02 (overlapper `vix_term_ratio` levert i bunke3 fra Yahoo VIX/VIX3M/VIX6M; CBOE-direkte gir ikke ekstra-verdi)*
17. `noaa_oni_index` (erstatter `enso_regime`), `noaa_enso_forecast_3mo`, `noaa_pdo_index`
18. `intraday_atr_h1` — Yahoo 1h candles

**Bunke 5 — USDM per-stat + USDA-utvidelser (uke 3-4):**
19. `usdm_state_iowa`, `usdm_state_texas`, `usdm_state_california`, `usdm_state_kansas_ndakota`
20. `nass_yield_corn_yoy`, `nass_yield_soy_yoy`, `nass_grain_stocks_quarterly`
21. `fas_exports_china`, `fas_exports_eu` (split eksisterende)

**Bunke 6 — EIA-utvidelse (måned 2 uke 1):**
22. `eia_distillate_change`, `eia_propane_change`, `eia_refinery_utilization_z`, `eia_petroleum_supplied`, `eia_natgas_processing`, `eia_imports_crude`, `eia_gasoline_demand`

**Bunke 7 — GIE-utvidelse + COT-disaggregated (måned 2 uke 2):**
23. `agsi_germany_pct`, `agsi_netherlands_pct`, `agsi_italy_pct`, `agsi_withdrawal_rate`, `agsi_injection_rate` (AGSI+ per-land)
24. `alsi_eu_pct`, `alsi_storage_change` (ALSI LNG-terminals — ny driver-kategori)
25. `iip_supply_unavailability` (IIP REMIT-meldinger — ny driver-kategori)
26. `cot_oi_change`, `cot_concentration_top4`, `cot_commercial_extreme`, `cot_swap_dealer_skew`

**Bunke 8 — Treasury + USGS + sluttspillet (måned 2 uke 3):**
27. `treasury_btc_10y`, `treasury_indirect_pct`, `treasury_quarterly_refunding`
28. `seismic_m6_global_24h`, `seismic_chile_peru_copper`
29. `crypto_sentiment_extreme` (vent til 100+ rader, ~juli 2026 — kan defer hvis ikke klart)

**Bunke 9 — Endringer på eksisterende (måned 2 uke 4):**
30. `enso_regime` → erstatt med `noaa_oni_index` (parallelt med #17)
31. `weather_stress`: lookback 1mnd → 6mnd
32. `nfci_change` → erstatt med `anfci_z` (parallelt med #11)
33. `mining_disruption`: M ≥ 5.5-terskel + region-mask
34. Multi-lookback-konsolidering (~25 drivere): én primær window per driver
35. `comex_stress`: disable til 6mnd (`min_samples=180`)
36. `momentum_z`: regime-conditional lookback (20d høy-vol, 100d lav-vol)
37. `sma200_align`: legg til slope-komponent
38. `range_position`: ATR-normalisert med 14-20d lookback
39. `bdi_chg30d`: utvid med 90d-trend + 12mo-MA-regime
40. `hdd_cdd_anomaly`: per-instrument-vekt
41. `aaii_extreme`: bytte til 8-uker-MA-divergens
42. `drought_monitor`: gjør CONUS-aggregat sekundær til state-level

### 22.3 Stop-criterion sub-fase 12.10

- Alle 9 bunker landed
- Snapshot-baseline regenerert etter hver bunke + grade-distribusjons-rapport per asset-class viser ingen systematisk bias (≤5 grade-flips per asset-class per bunke)
- 22 instrument-YAMLer wired med relevante nye drivere
- Pyright src/: 0 errors
- Alle nye drivere har minst 3 tester (default + edge + horisont-filter hvis applikabel)

Tag: `v0.12.10-fase-12.10-LUKKET`. Etter dette: bruker vurderer **Bedrock-2.0**-cutover etter empirisk demo-resultat.

### 22.4 Hva 12.10 IKKE inkluderer

- Familie-restruktur til 2-nivå-taksonomi (eksplisitt droppet)
- ALFRED-vintage-migrasjon (backtest-relevant, droppet)
- Regime-conditional weighting i scoring-aggregator (utsatt — vurderes etter 12.10)
- Live-cutover (kun demo-konto fra start til slutt)
- Trade-execution-side (bot.yaml lot-sizing/exit-policies — egen sub-fase)
- UI-eksponering av 67 nye drivere (incremental etter hver bunke; ingen big-bang UI)

### 22.5 Sub-fase 12.10 follow-up Spor A — LUKKET 2026-05-02 (A1-A11)

**Status:** Spor A (YAML-wirings av 12.10-bunke-drivere) LUKKET. 11 sub-spor (A1-A11) levert. Tags: `v0.12.10-followup-a1` ... `v0.12.10-followup-a11`.

**Levert per § 22.1 PRIMÆR-spor:**
- **52 wirings + 11 replacements** (51 wirings ved spor-finale; A11 leverte siste 1)
- **2 grade-flips totalt** (Nasdaq + SP500 SWING buy B→A i A10, ved B/A-grensen 3.20). Stop-criterion ≤5/asset-class respektert i alle 11 spor.
- **Bunker fullt wired:** 6 (alle 6 EIA-drivere), 7 (alle 5 AGSI-drivere)
- **Bunker delvis wired:** 3 (9/14 — resten har overlap), 4 (5/8 — 3 DEFERRED på CBOE/NOAA-feed), 8 (2/3 — Treasury DEFERRED)
- **Per asset-class coverage:** Alle 22/22 instrumenter har minst én ny 12.10-bunke-driver wired

**Gjenstår fra A-track (lav prioritet — overlapp eller død kode):**
- `enso_regime` død driver i `agri.py` (analog-dim-extractor må også oppdateres til noaa_oni_index — egen refactor-commit)
- `continuing_claims_z`, `t_bill_3mo_yield`, `fomc_decision_distance` — overlapp med eksisterende drivere; kan wires hvis empirisk verdi etablert

**Ikke levert (utsatt til separate spor B-E):**
- Bunke9 #34 multi-lookback-konsolidering (substantial driver-refactor — Spor E)
- Bunke9 #36-#41 driver-impl-rewrites (substantial refactors — Spor E)
- *_surprise data-arkitektur (#5 — Spor B)
- ALSI/IIP-routes (#24/#25 — Spor C)
- NASS yield/grain_stocks (#20 — Spor D)
- Resterende mindre DEFERRED (CBOE pcr, NOAA enso_forecast, ism_pmi_level, treasury_auctions, crypto_sentiment_extreme, eia_natgas_processing, cot_concentration_top4, cot_swap_dealer_skew — Spor F). *vix_term_curve droppet Spor F3 2026-05-02 (overlapp).*

### 22.6 Sub-fase 12.10 follow-up Spor B-F — gjenstår

#### Spor B: *_surprise data-arkitektur (PLAN § 22.2 #5)

**Mål:** Implementere `nfp_surprise`, `cpi_surprise`, `gdp_surprise`, `pce_surprise`-drivere i ny `event`-familie (per § 22.1 låst beslutning).

**Blocker:** Forex Factory `ff_calendar_thisweek.json` har KUN forecast+previous-keys, ikke actual. FRED-serier PAYEMS/CPIAUCSL/GDP/PCEPI er heller ikke i DB.

**Subtasks:**
- B1: Velg data-kilde for actual-felt (FRED-cross-reference vs alternativ feed som tradingeconomics/dailyfx). ADR-014 hvis arkitektonisk skifte.
- B2: Backfill PAYEMS/CPIAUCSL/GDP/PCEPI fra FRED til fundamentals.
- B3: Implementer cross-source-join-logikk (FF.forecast × FRED.actual eller alt feed).
- B4: Implementer 4 `econ_surprise`-drivere med title-pattern + country + bull_when.
- B5: 4 YAML-wirings (SP500/Nasdaq/USDJPY/EURUSD `event`-familie med vekt 1.0).
- B6: Snapshot-baseline regen + diff-rapport.

**Estimat:** 2-3 sessioner. Substantial fordi cross-source-arkitektur er ny.

#### Spor C: ALSI + IIP-routes (PLAN § 22.2 #24/#25)

**Mål:** GIE-extensions for ALSI (LNG-terminal-storage) og IIP REMIT (supply-unavailability).

**Subtasks:**
- C1: Schema-utvidelse `alsi_storage`-tabell + IIP REMIT-tabell.
- C2: Fetcher-extensions med GIE-key (allerede registrert per § 22.1 — én key dekker AGSI+ALSI+IIP).
- C3: Drivere `alsi_eu_pct`, `alsi_storage_change`, `iip_supply_unavailability`.
- C4: Backfill + tester + YAML-wirings (NaturalGas + Brent macro).
- C5: Snapshot-baseline regen + diff-rapport.

**Estimat:** 1-2 sessioner. Bygger på AGSI-mønster fra bunke7.

#### Spor D: NASS yield/grain_stocks (PLAN § 22.2 #20)

**Mål:** USDA NASS QuickStats-utvidelse for yield-survey + quarterly-stocks.

**Subtasks:**
- D1: Schema-utvidelse `nass_yield` + `nass_grain_stocks`-tabeller.
- D2: NASS QuickStats-fetcher utvidelser (yield-survey + quarterly-stocks-routes).
- D3: Drivere `nass_yield_corn_yoy`, `nass_yield_soy_yoy`, `nass_grain_stocks_quarterly`.
- D4: Backfill + tester + YAML-wirings (Corn + Soybean yield/cross-familier).
- D5: Snapshot-baseline regen + diff-rapport.

**Estimat:** 1-2 sessioner. Bygger på eksisterende NASS Crop Progress-fetcher.

#### Spor E: Driver-impl-rewrites (PLAN § 22.2 #36-#41 + #34)

**Mål:** Substantial refactor av 6 eksisterende drivere + multi-lookback-konsolidering.

**Subtasks (én per session):**
- E1: #36 `momentum_z` regime-conditional lookback (20d høy-vol, 100d lav-vol)
- E2: #37 `sma200_align` slope-component
- E3: #38 `range_position` ATR-normalisering 14-20d
- E4: #39 `shipping_pressure` 90d-trend + 12mo-MA-regime
- E5: #40 `hdd_cdd_anomaly` per-instrument-vekt
- E6: #41 `aaii_extreme` 8-uker-MA-divergens
- E7: #34 multi-lookback-konsolidering (~25 drivere — én primær window per driver)

**Estimat:** 6-7 sessioner. Hver har behov for tester + ev. baseline-flips.

#### Spor F: Resterende mindre DEFERRED

**Subtasks:**
- F1: ism_pmi_level alt-kilde (manuell CSV-fallback?)
- F2: ~~CBOE pcr_total_extreme + pcr_equity_only~~ — **BLOCKED 2026-05-02 (re-DEFERRED).** Kickoff-spec antok `cdn.cboe.com/api/global/...`-CSV er gratis; verifisert 2026-05-02 at endepunktet returnerer 403. Legacy CBOE-CSV stopper oktober 2019. Yahoo har ikke `^CPC/^CPCE/^CPCI`-tickerne (404). Eneste gjenstående gratis-tilnærming er manuell daily ingest av PCR fra CBOE Daily Market Statistics-HTML — operator-tempo for høyt for daily-published indikator. Re-åpne hvis (a) FRED re-publiserer CBOE-PCR-feed, (b) StockCharts/WSJ-free serveres med direct-link, eller (c) operator-driven manuell daily-CSV-flow blir gjennomførbar. Inntil videre dekker `cboe_skew_z` + `vix_term_ratio` + `vvix_z` mye av samme contrarian/options-positioning-signal-domene.
- F3: ~~cboe_vix_term_curve~~ — **DROPPED 2026-05-02.** Overlapper `vix_term_ratio` levert i bunke3 (Yahoo VIX/VIX3M/VIX6M); CBOE-direkte gir ikke ekstra signal-verdi. Ingen kode-leveranse.
- F4: noaa_enso_forecast_3mo fra IRI-CSV
- F5: cot_concentration_top4 + cot_swap_dealer_skew (schema-utvidelse for Conc_Net + TFF Swap)
- F6: Treasury auctions (#27) — ny fetcher mot Treasury direct
- F7: crypto_sentiment_extreme (vent til ~juli 2026 når 100+ rader). **STATUS 2026-05-02 (Spor F LUKKET):** ikke åpnet. DB-rader vokste fra ~30 (sub-fase 12.10-start) til estimat ~70+ ved 2026-05-02. Forventet ≥100 rader rundt 2026-07-01 (~3 mnd akkumulering siden første harvest). Re-åpnes operasjonelt da; 1 session estimert (driver-impl + tester + YAML).
- F8: eia_natgas_processing (monthly natgas-route i eia.fetch)

**Estimat:** 4-6 sessioner. Hver er liten, men data-tilgang varierer.

### 22.7 Anbefalt rekkefølge for Spor B-F

Basert på leveranse-verdi vs implementasjons-kompleksitet:

1. **Spor C** (ALSI/IIP) — **LUKKET 2026-05-02** (`v0.12.10-followup-spor-c`). 0 grade-flips, 95 nye tester. 21924 ALSI + 10628 IIP-rader.
2. **Spor D** (NASS yield) — **LUKKET 2026-05-02** (`v0.12.10-followup-spor-d`). 0 grade-flips, 64 nye tester. 443 yield + 444 stocks-rader.
3. **Spor B** (*_surprise) — **LUKKET 2026-05-02** (`v0.12.10-followup-spor-b`). 1 grade-flip (USDJPY MAKRO sell B→A), 24 nye tester, ADR-014 levert. 400 FRED-rader + 468 events fikk actual.
4. **Spor F** (mindre DEFERRED) — **LUKKET 2026-05-02** (`v0.12.10-followup-spor-f`). Levert i én session: F3 droppet (overlapp), F8 (eia_natgas_processing), F4 (noaa_enso_forecast_3mo + IRI manuell CSV), F1 (ism_pmi_level + ISM manuell CSV), F5 (cot_concentration_top4 + cot_swap_dealer_skew + schema-ALTER + 5y re-backfill), F6 (treasury_auction_demand + TreasuryDirect-fetcher). F2 re-DEFERRED (CBOE data paywalled — verifisert 2026-05-02). F7 venter til ~juli 2026 (≥100 crypto_sentiment-rader). Akkumulert: 5 nye drivere wired, 4 nye fetchere/extensions, 4 nye DB-kolonner på cot_disaggregated, 1 ny tabell, ~4400 nye rader, 35+ nye tester. Stop-criterion ≤5 grade-flips/asset-class respektert (max 1 flip på softs Coffee A→A+ + 1 på energy CrudeOil B→A; 0 metals/indices grade-flips).
5. **Spor E** (driver-impl-rewrites #36-#41 + #34 multi-lookback) — **VENTER til ~2026-06-01** (~4 uker etter Spor B live-demo-start, slik at vi har empirisk data på hvilke drivere som faktisk underperformer). 6-7 sessioner. Bruker-beslutning 2026-05-02: utsette til empiri foreligger fremfor å refactore på tro.

**Spor F-LUKKET-summary (2026-05-02):**
- Faktisk levert vs estimat: 1 session (estimat var 6-9). Gevinst skyldes (a) sammenslått drivere/backfill/wiring/baseline-regen i hver F-leveranse vs estimerte separate sessioner, (b) fetcher-recovery ble lett siden infrastrukturen fra Spor C/D var moden, (c) F2-deferral sparte 1-2 sessioner, (d) F7-utsettelse sparte 1.
- Akkumulert resultat etter alle 12.10-followup-spor (A+B+C+D+F): 12 nye tabeller/kolonne-utvidelser, 10+ nye fetchere/extensions, ~30 nye drivere wired, 285+ nye tester, ~82500 nye datarader. Pyright src/: forventet 0 errors (verifiseres post-commit).
- F2 (CBOE pcr) og F7 (crypto_sentiment_extreme) er enslige gjenværende DEFERRED-poster fra hele 12.10-followup-løpet.
