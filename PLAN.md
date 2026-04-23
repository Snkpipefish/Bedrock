# Bedrock — implementasjonsplan

Dato opprettet: 2026-04-23
Sist oppdatert: 2026-04-23
Status: godkjent, Fase 0 fullført
Referanser: `NYTT_PROSJEKT_UTKAST.md` (i cot-explorer), `AGRI_KARTLEGGING.md` (i cot-explorer), fase-1-audit-rapport (i chat-logg).

## Endringshistorikk (etter initial godkjenning)

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
│   ├── setups/                     # setup-generator (NY kritisk komponent)
│   │   ├── __init__.py
│   │   ├── levels.py               # reelle-nivåer-detektor (swing, POC, W/D H/L, round)
│   │   ├── generator.py            # finn asymmetriske setups rundt nivåer
│   │   ├── persistence.py          # setup-ID + lifecycle (watch→trigger→active→closed)
│   │   └── horizon.py              # horisont fra setup-karakteristikk, ikke score
│   │
│   ├── data/                       # datalag
│   │   ├── store.py                # DuckDB + parquet
│   │   ├── schemas.py              # pydantic + parquet-schemas for tidsserier
│   │   ├── backfill.py             # historisk backfill-orkestrator
│   │   └── analogs.py              # K-NN-søk mot historikk
│   │
│   ├── fetch/                      # rå I/O (ingen scoring)
│   │   ├── base.py                 # felles retry/logging/stale-sjekk
│   │   ├── cot_cftc.py
│   │   ├── cot_ice.py
│   │   ├── cot_euronext.py
│   │   ├── prices.py
│   │   ├── fundamentals_fred.py
│   │   ├── agri_weather.py
│   │   ├── agri_conab.py
│   │   ├── agri_unica.py
│   │   ├── calendar_ff.py
│   │   ├── shipping.py
│   │   ├── comex.py
│   │   ├── crypto.py
│   │   ├── oilgas.py
│   │   ├── seismic.py              # beholdes selv om unuset i scoring (prinsipp 6)
│   │   ├── intel.py
│   │   └── new/                    # nye datakilder (se § 8.3)
│   │       ├── usda_wasde.py       # stocks-to-use + yield
│   │       ├── usda_crop_progress.py
│   │       ├── export_policy.py
│   │       └── agri_freight.py
│   │
│   ├── signals/                    # setup + score → signal-objekt
│   │   ├── builder.py              # bygg Signal fra (score, setup, context)
│   │   ├── publisher.py            # POST til signal_server + disk
│   │   └── schema.py               # Pydantic-modeller (låst v1 + extras)
│   │
│   ├── server/                     # refaktor av signal_server.py
│   │   ├── app.py                  # Flask/FastAPI
│   │   ├── routes_signals.py       # /signals /push-alert /invalidate
│   │   ├── routes_prices.py        # /push-prices /prices
│   │   ├── routes_kill.py          # /kill /clear_kills
│   │   ├── routes_admin.py         # /admin/rules POST (kode-beskyttet)
│   │   └── store.py                # in-memory state + disk-persistering
│   │
│   ├── bot/                        # refaktor av trading_bot.py
│   │   ├── __main__.py             # entry-point + CLI (--demo/--live)
│   │   ├── ctrader_client.py       # Twisted + Protobuf-lag
│   │   ├── state.py                # TradeState, CandleBuffer, TradePhase
│   │   ├── entry.py                # 3-punkts bekreftelse + alle entry-gates
│   │   ├── exit.py                 # P1-P5 exit-logikk
│   │   ├── sizing.py               # risk% + lot-tier
│   │   ├── safety.py               # daily_loss + kill + server-frozen
│   │   └── comms.py                # signal_server-polling
│   │
│   ├── pipeline/                   # orkestrering (erstatter update.sh)
│   │   ├── main_cycle.py           # full fetch + score + publish (4-timer)
│   │   ├── hourly.py               # pris-rescore (hver time :40)
│   │   ├── gates.py                # dag/klokkeslett-logikk (CFTC lør etc.)
│   │   └── runner.py               # systemd entry-point
│   │
│   └── cli/                        # kommandolinje-verktøy
│       ├── __main__.py             # `bedrock` command
│       ├── kill.py                 # `bedrock kill <sig_id>` / `bedrock kill all`
│       ├── backfill.py             # `bedrock backfill prices --from 2016`
│       ├── explain.py              # `bedrock explain <sig_id>` (hvorfor scoret det så)
│       └── backtest.py             # `bedrock backtest --rules rules_v2 --from 2024`
│
├── web/                            # statisk frontend (GitHub Pages)
│   ├── index.html                  # 4 faner (Skipsloggen / Financial / Soft commodities / Kartrommet)
│   ├── admin.html                  # separat rule-editor (kode-beskyttet)
│   ├── assets/
│   └── data/                       # symlink til publisert JSON
│
├── data/                           # kjøredata (gitignored større deler)
│   ├── parquet/                    # historikk-lag (DuckDB queryable)
│   │   ├── prices/
│   │   ├── cot/
│   │   ├── fundamentals/
│   │   ├── weather/
│   │   └── trades/
│   ├── latest/                     # siste snapshots per kilde
│   │   ├── macro.json
│   │   ├── signals.json
│   │   └── ...
│   ├── setups/                     # aktive setups (persisterte)
│   ├── signal_log.json             # ETT sted. Bot skriver her. Ingen kopiering.
│   └── _meta/                      # genereringstid per fil
│
├── systemd/                        # versjonerte timer/service-filer
│   ├── bedrock-main.timer
│   ├── bedrock-main.service
│   ├── bedrock-hourly.timer
│   ├── bedrock-hourly.service
│   ├── bedrock-server.service
│   └── bedrock-bot.service
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

# Fase 2 senere sessions:
weather = store.get_weather("us_cornbelt", from_="2024-01-01")
store.append_weather(df)
fund = store.get_fundamentals("DGS10", from_="2016-01-01")
store.append_fundamentals(df)

# Analog-søk (Fase 9):
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

Alle viktige per dine ord. Implementeres i faser (se § 13):

| Kilde | Hva | Implementering | Fase |
|---|---|---|---|
| USDA WASDE | Ending stocks, yield-prognoser, S2U | Parse PDF/XLS månedlig | 4 |
| USDA Crop Progress | % planted/silked/harvested ukentlig | API (NASS QuickStats) | 4 |
| Eksport-policy-tracker | India/Indonesia/Ivory Coast-hendelser | News-scraper + manuell kuratert kalender | 5 |
| BRL/USD aktivt drivet | Pris-feed + som driver for softs | Pris-feed finnes allerede; legg til som driver | 4 |
| Baltic Dry til agri | Kobling BDI → grain-eksport-pris | Driver som regresserer BDI mot eksport-cost | 5 |
| Disease/pest-varsling | Coffee rust, wheat stripe rust | Ekstern service (PestMon, CABI) — senere | 6 |
| ICE softs COT | Sukker/kaffe-spesifikk | Finnes delvis; utvid | 4 |
| IGC rapporter | International Grains Council | Månedlig PDF-parse | 5 |

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
- Exit-prioritet P1-P5 (geo-spike, kill, weekend, T1, trail, EMA9, timeout, hard-close)
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

---

## 10. UI — 4 faner

### 10.1 Fane 1 — Skipsloggen

Bot-logg og historikk. Dagens `index.html` Skipsloggen-fane er et godt utgangspunkt. Leser `data/signal_log.json`. Kapteins-KPI, trade-log, pirat-flavor per trade (deterministisk hash).

### 10.2 Fane 2 — Financial setups

Aktive setups fra `data/setups/active.json` filtrert på asset_class ∈ {fx, metals, energy, indices, crypto}. 5 topp-kort med instrument/retning/horisont/grade/stjerner + entry/SL/TP + 6 familie-badges. Klikk → modal med full explain-trace og analog-matcher.

### 10.3 Fane 3 — Soft commodities setups

Samme som fane 2 men for `asset_class ∈ {grains, softs}`. Viser i tillegg agri-spesifikke data: vær-stress per region, ENSO-status, Conab/UNICA-flagg, yield-score, analog-år.

### 10.4 Fane 4 — Kartrommet

Pipeline-kontrollbord. Viser helse per fetch-kilde (fresh/aging/stale/missing) med `_meta.generated_at` og rad-antall. Gruppert (Core / Bot-priser / CFTC / Ekstern COT / Fundamentals / Sektor / Geo). Read-only.

### 10.5 Separat: Admin-rule-editor

`web/admin.html`. Beskyttet med lokal kode (kode-input → hasha + matchet mot server-lagret hash). Lar bruker redigere YAML-regler, se dry-run-diff, commit. POST til `/admin/rules` på signal_server.

Fordi repoet er public ligger `admin.html` bak et separat endpoint som ikke linkes fra `index.html`. Bruker kan nå den via direkte URL + kode.

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

---

## 13. Faser og rekkefølge

Hver fase avsluttes med testing + commit. Ingen fase starter før forrige er grønn.

| Fase | Innhold | Estimat | Test-krav |
|---|---|---|---|
| **0** | Bedrock-repo, pyproject.toml, uv, pre-commit (ruff, pyright), CI | 1-2 dager | `pytest` kjører tomme tester grønt |
| **1** | Engine + driver-registry + aggregators + grade + explain. 5-10 drivere. Eksempel-YAML Gold + Corn. | 1 uke | Logiske tester for scoring-scenarioer |
| **2** | Data-lag: DuckDB + parquet, skjemaer, DataStore-API | 4-5 dager | Unit-tester på store.py |
| **3** | Backfill-CLI: priser, COT, FRED, vær. 10 års historikk. | 1 uke (+ kjøretid) | Data-integritets-tester |
| **4** | Setup-generator: nivå-detektor + generator + persistence + horisont-klassifisering. MAKRO no-TP. | 2 uker | Logiske tester for setup-output. Dette er hjertet i "asymmetri-målet". |
| **5** | Fetch-laget: flytt alle moduler, config-drevet cadence. USDA WASDE + Crop Progress + BRL-driver + Baltic-til-agri. | 1 uke | Smoke-tester per fetcher |
| **6** | Signal-server refaktor: modul-splitt, /admin/rules, schema-validering | 3-5 dager | API-tester |
| **7** | Bot-refaktor: splitt i 8 moduler, fjern agri-override, config-ekstraksjon | 1 uke | Bot må fortsatt kjøre demo i parallell |
| **8** | UI: 4 faner + admin-editor. Erstatter eksisterende HTML. | 1-2 uker | Visuell verifisering + signal-visning-tester |
| **9** | Analog-matching: K-NN, per asset-klasse, outcome-labels, integrer i scoring + UI | 1 uke | Backtest av analog-driver mot forward-return |
| **10** | Backtest-rammeverk + 12 måneder historikk-replay | 1 uke | Output: rapport over signal-performance |
| **11** | 2 uker demo-parallell-drift | 2 uker | Cutover-kriterier møtt |
| **12** | Cutover: skru av gamle timers, gå live | 1 dag | Alt grønt |

Totalt: ~12-16 uker. Kan parallelliseres noe (data-lag og engine kan jobbes samtidig).

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

Fase 0 er fullført — `~/bedrock/` opprettet med full infrastruktur, git-regler,
CI, tests-skall, docs, CLAUDE.md, STATE.md. Godkjent av bruker 2026-04-23.

Neste session (Fase 1):
1. Opprett `feat/engine-core` branch
2. Implementer `Engine`-klasse + driver-registry (base + `@register`-dekorator)
3. Implementer `weighted_horizon`-aggregator
4. Første to drivere: `sma200_align`, `momentum_z`
5. Logiske tester for Gold SWING-scenario
6. Første ADR: `docs/decisions/001-one-engine-two-aggregators.md`

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

Ved slutten av hver større fase (Fase 1, 4, 6, 7, 10) kjører bruker en Claude
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

**Nivå 1 (enkel) — aktiv under Fase 0 til og med Fase 10:**
- Commit direkte til `main`
- Auto-push-hook (`.githooks/post-commit`) sender hver commit til GitHub umiddelbart
- Ingen feature-branches, ingen PR
- Null ceremony, maksimal fart under utvikling
- Main er ennå ikke produksjon (ingen systemd-service kjører fra den)

**Nivå 3 (streng) — aktiveres ved Fase 10-11, før live-cutover:**
- Feature-branch → auto-push branch → PR → CI grønn → review → squash-merge til main
- Aldri direkte-til-main når main = produksjon
- Branch-beskyttelse på GitHub (require PR, require status checks)
- Beskrevet fullt i `docs/branch_strategy.md`

**Overgang:** ved start av Fase 10 setter bruker opp branch-beskyttelse på main i
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

### 18.3 Flyt (Nivå 3 — ved Fase 10+)

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

### 18.7 Main-beskyttelse (GitHub-settings, aktiveres ved Fase 10)

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
