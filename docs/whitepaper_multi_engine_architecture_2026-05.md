# Whitepaper: Multi-Engine Trading Architecture

**Status:** UTKAST — for diskusjon
**Dato:** 2026-05-06
**Forfatter:** Bedrock-team
**Versjon:** 0.1

---

## 1. Executive summary

Forslag: bygge en **multi-engine arkitektur** der hvert instrument får sin egen dedikerte signal-genererings-motor med egne kriterier og tidshorisonter, alle koblet til én felles trading-bot via et standardisert signal-bus.

**Kjerne-prinsipp:** "ett instrument — én filosofi — én motor". Sukker-motoren kan være mean-reversion på 60-180d. Hvete-motoren kan være momentum-breakout på 30-90d. Hver utvikles, valideres, og deployes uavhengig.

**Fordeler vs. dagens monolitiske Bedrock:**
- Eliminerer scope-creep (en motor må valideres før neste startes)
- Lar hver alpha-thesis utvikles uten å kompromisses for "felles modell"
- Gjør motorer versjonerbare og erstattbare (sukker v2 påvirker ikke hvete)
- Skiller forskning (hver motor) fra eksekvering (felles bot)

---

## 2. Problemstilling — hvorfor Bedrock-monolitten ikke skalerer

### 2.1 Identifiserte fundamentale issues

Per `docs/engine_fundamental_review_2026-05-06.md`:
- 16 instrument-horisont-konflikter (BUY+SELL begge over floor)
- 11 instrumenter med trippel-eksponering (multi-horizon duplisering)
- Per-direction-uavhengig scoring → kontradiktoriske signaler
- 7-familie additive-scoring uten ekte ortogonalitets-verifikasjon
- Forward-pricing-mismatch på agri (engine leser current, marked priser forward)
- Setup-builder kontekst-blind (samme entry alle horisonter)

### 2.2 Rotårsak: én-størrelse-passer-alle

Bedrock antar at **samme score-modell + samme familie-vekter + samme grade-thresholds** kan generalisere over 22 instrumenter på tvers av asset-klasser. Det stemmer ikke:

- **Sukker** prises 6-12 mnd forward → krever forward-data
- **EURUSD** trender ofte intra-uke → krever korte momentum-signaler
- **Bitcoin** har 24/7 sentiment-overlay → krever krypto-spesifikke drivere
- **Gull** reagerer på real yields + DXY → krever financial-konditioning
- **Kaffe** har frost-event-binær risiko → krever event-baserte triggere

Å "tweake YAML-vekter" for hvert instrument er bare lapping. Hver INSTRUMENT TYPE krever sin egen filosofi.

### 2.3 Score-først vs setup-først

Bedrock er **score-først**: beregn score → finn nivå som passer.

Profesjonelle tradere er **setup-først**: finn nivå → bekreft med confluence.

Dette er en arkitektonisk forskjell som ikke kan repareres med YAML-tuning. Hver motor i v3 må kunne velge sin egen filosofi.

---

## 3. Arkitektur-visjon

### 3.1 Konseptuell modell

```
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  sugar-engine v1     │  │  wheat-engine v1     │  │  ...future engines    │
│                      │  │                      │  │                       │
│ - egen filosofi      │  │ - egen filosofi      │  │                       │
│ - egne drivere       │  │ - egne drivere       │  │                       │
│ - egne horisonter    │  │ - egne horisonter    │  │                       │
│ - egen backtest      │  │ - egen backtest      │  │                       │
└──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
           │                         │                          │
           │       Signal Protocol (JSON over signal_bus)        │
           └─────────────────────────┼──────────────────────────┘
                                     ▼
                           ┌──────────────────────┐
                           │   signal_bus         │
                           │ (HTTP / file / queue)│
                           └──────────┬───────────┘
                                      ▼
                           ┌──────────────────────┐
                           │  trading_bot         │
                           │                      │
                           │ - multi-engine consum│
                           │ - per-instrument cap │
                           │ - daily risk-budget  │
                           │ - cTrader-execution  │
                           │ - outcome-reporter   │
                           └──────────┬───────────┘
                                      ▼
                                  cTrader
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  outcome_feedback    │
                           │ (filled/SL/TP-hit)   │
                           └──────────┬───────────┘
                                      ▼
                          (tilbake til engines for læring)
```

### 3.2 Designprinsipper

1. **En motor — én filosofi — ett instrument** (initial build).
2. **Felles signal-protokoll** (JSON-skjema, versionert).
3. **Bot er passiv konsument** — ingen logikk om "hvilket signal å ta", bare risk-arbitrasjon.
4. **Engines er stateless mot bot** — sender signaler, mottar fill-confirm/outcome.
5. **Risiko-arbitrasje på bot-side** — per-instrument-cap, daily-cap, sector-cap.
6. **Outcome-feedback til engines** — for læring/validering, ikke for live decision.
7. **Versjonering på signal-nivå** — sugar v1 + sugar v2 kan kjøre parallelt for A/B.
8. **Felles infrastruktur som library** — ikke mikro-tjenester, men shared modules (DataStore, fetchers, backtest-runner).

---

## 4. Signal-protokoll (engine ↔ bot kontrakt)

### 4.1 Signal-skjema (versjon 1)

```json
{
  "schema_version": "1.0",
  "engine_id": "sugar-v1",
  "engine_version": "1.0.3",
  "signal_id": "sugar-v1-20260506-makro-sell-001",
  "instrument": "Sugar",
  "direction": "sell",
  "horizon_days": 120,
  "conviction_score": 87.5,
  "max_score": 100,
  "grade": "A",

  "setup": {
    "type": "mean_reversion_at_resistance",
    "entry_price": 18.29,
    "stop_loss": 18.40,
    "take_profit": 13.22,
    "trailing": {
      "enabled": true,
      "atr_multiplier": 2.5,
      "activate_at_progress": 0.30
    },
    "risk_reward": 45.3
  },

  "validity": {
    "first_seen_utc": "2026-05-06T08:46:19Z",
    "expires_utc": "2026-05-06T20:46:19Z",
    "supersedes": null
  },

  "evidence": {
    "drivers": [
      {"name": "comtrade_export_yoy", "value": 0.85, "weight": 0.25, "note": "India eksport recovering"},
      {"name": "seasonal_stage", "value": 0.40, "weight": 0.10, "note": "May = lager-bygging"},
      {"name": "analog_hit_rate", "value": 1.00, "weight": 0.20, "note": "5/5 historiske matcher gikk ned"}
    ],
    "validation_history": {
      "backtest_sharpe": 1.8,
      "psr": 0.92,
      "samples_30d": 12,
      "ablation_critical": ["comtrade_export_yoy", "analog"]
    }
  },

  "risk_budget": {
    "requested_pct": 1.0,
    "max_acceptable_pct": 1.5,
    "min_acceptable_pct": 0.5
  }
}
```

**Kjerne-felter:**
- `engine_id` + `engine_version` — bot vet hvilken motor som sendte
- `signal_id` — unik, idempotent (samme ID = samme signal)
- `setup.type` — kategorisering (mean_reversion / momentum_breakout / event_anticipation / etc.)
- `evidence.drivers` — top 3-5 bidragene + verdier (for transparans)
- `validation_history` — hvor godt har denne motoren prestert (gir bot info for arbitrasje)
- `risk_budget` — motor sier hva den ønsker, bot bestemmer faktisk allokering

### 4.2 Bot → engine ack/reject

```json
{
  "signal_id": "sugar-v1-20260506-makro-sell-001",
  "decision": "accepted",  // accepted / rejected / partial
  "allocated_risk_pct": 0.8,  // bot kuttet fra 1.0 pga andre setups
  "rejection_reason": null,  // f.eks. "instrument_cap_exceeded", "daily_cap_exceeded"
  "position_id": "ctrader-pos-12345",
  "filled_at_utc": null,  // null = pending fill
  "filled_price": null
}
```

### 4.3 Outcome-feedback til engine

```json
{
  "signal_id": "sugar-v1-20260506-makro-sell-001",
  "position_id": "ctrader-pos-12345",
  "outcome": "tp_hit",  // tp_hit / sl_hit / trailing_exit / manual_close / expired
  "entry_price_actual": 18.32,
  "exit_price": 13.45,
  "duration_hours": 2880,  // 120 dager
  "pnl_pct": -26.6,
  "max_favorable_excursion_pct": -28.1,
  "max_adverse_excursion_pct": +1.2,
  "closed_at_utc": "2026-09-03T14:22:00Z"
}
```

Engines bruker outcome-feedback for:
- Walk-forward weight-tuning
- Driver-validation (hvilke drivere predikerte ekte outcomes)
- Setup-type-validering (mean_reversion vs momentum)

---

## 5. Bot-arkitektur (multi-engine consumer)

### 5.1 Risk-arbitrasje

Bot mottar N signaler fra M engines. Beslutnings-logikk:

```python
def arbitrate_signals(signals: list[Signal], state: BotState) -> list[Decision]:
    """Bestemm hvilke signaler å akseptere + størrelse."""

    # 1. Filter ut utgåtte / duplikat-signaler
    valid = [s for s in signals if not_expired(s) and not_duplicate(s, state)]

    # 2. Per-instrument-cap: hvis flere engines vil ha samme instrument:
    by_instrument = group_by_instrument(valid)
    for inst, sigs in by_instrument.items():
        if len(sigs) > 1:
            # Velg vinner basert på conviction × validation_track_record
            winner = max(sigs, key=lambda s: s.conviction * s.engine_track_record)
            valid = [s for s in valid if s.signal_id == winner.signal_id or s.instrument != inst]

    # 3. Daily-risk-budget allocation
    remaining_budget = state.daily_max_pct - state.used_pct_today
    sorted_by_conviction = sorted(valid, key=lambda s: -s.conviction)

    decisions = []
    for sig in sorted_by_conviction:
        wanted = sig.risk_budget.requested_pct
        if remaining_budget < sig.risk_budget.min_acceptable_pct:
            decisions.append(Decision(sig.signal_id, "rejected", "daily_cap_exceeded"))
            continue
        allocated = min(wanted, remaining_budget)
        decisions.append(Decision(sig.signal_id, "accepted", allocated_pct=allocated))
        remaining_budget -= allocated

    return decisions
```

### 5.2 Engine track-record-vurdering

Bot vedlikeholder statistikk per engine:
- `engine_id` → siste 30 trades: hit-rate, avg_return, max_dd
- Engines med svak track-record får redusert vekting i arbitrasje
- Nye engines starter med "neutral" track-record (50% conviction-multiplier) inntil 10+ trades

### 5.3 Multi-engine same-instrument-tilfelle

Hva hvis sugar-v1 sier SELL og sugar-v2 sier BUY samtidig?

**Beslutning:** ta KUN signalet med høyere `conviction × engine_track_record`. Logg det andre som "outvoted by engine X".

Dette **eliminerer kontradiksjons-problemet på arkitektur-nivå** — bot tar aldri opposing positions på samme instrument.

---

## 6. Faset bygge-plan

### 6.1 Fase 0 — Infrastruktur (2 uker)

- Definer signal-protokoll v1.0 (JSON-skjema + Pydantic)
- Bygg signal_bus (start enkelt: filsystem `signals/inbox/*.json`)
- Bygg bot-side multi-engine consumer + risk-arbitrasje
- Definer engine-template-pakke (`engine_template/` med required interface)
- Outcome-feedback-pipeline (bot → engines)

### 6.2 Fase 1 — Sugar Engine v1 (4-6 uker)

**Filosofi:** Mean-reversion at major support/resistance with confluence

**Pipeline:**
```
sugar-engine/
├── setup_finder.py        # finn S/R med significance-score
├── conviction_scorer.py    # 5-7 validerte drivere, ingen familie-vekter
├── decision_engine.py      # take/skip/wait
├── signal_publisher.py     # serialiser + send til bus
├── outcome_listener.py     # motta fra bot, oppdater state
├── backtest.py             # walk-forward 14 år
└── config/
    ├── drivers.yaml        # 5-7 drivere med vekter
    ├── horizons.yaml       # 60-180d MAKRO target
    └── risk.yaml           # per-position max 1%
```

**Drivere (5-7 max):**
- comtrade_export_yoy (India real-time)
- unica_change(production_yoy)
- seasonal_stage (forward-syklus)
- positioning_extreme_flag (anti-overshoot)
- ethanol_parity_brl (mølle-mix prediktiv)
- weather_stress_centro_sul (BR yield)
- (valgfritt) analog_hit_rate

**Validering:**
- Backtest 14 år (2012-2026) på sukker-historikk
- DSR + ablation per driver
- 6 mnd shadow-mode (signaler logget men ikke utført) før live
- Live-trading med 0.5% risk-cap (50% av normal) i første 3 mnd

**Akseptanse:**
- 30+ historiske trades med Sharpe ≥ 1.5
- 6 mnd shadow-mode med PSR ≥ 0.90
- 0 kontradiktoriske signaler (single-direction-or-neutral)

### 6.3 Fase 2 — Wheat Engine v1 (etter Sugar v1 validert)

**Filosofi-spørsmål** (avhenger av research):
- Mean-reversion på USDA WASDE-overshoots?
- Momentum-breakout på Black-Sea-policy-events?
- Calendar-spread arbitrasje (Mar/May/Jul-spread)?
- Trend-following på Russland-Ukraina-headlines?

Vi VET ikke ennå. Sugar-v1-arbeidet vil informere wheat-design.

**Build-pattern:** kopier sugar-engine/ → wheat-engine/, behold infrastruktur, bytt filosofi + drivere + horisonter.

**Ikke-mål for wheat-v1:**
- Ikke prøv å gjenbruke sugar-vekter
- Ikke anta at samme drivere virker
- Ikke samme horisont-target (kan være 30-90d eller 7-14d)

### 6.4 Fase 3+ — Skalere etter validering

| Engine | Foreslått filosofi | Når? |
|---|---|---|
| coffee-engine | Brasil-frost-event-trigger | Etter wheat ferdig |
| crude-engine | OPEC-meeting-anticipation | Etter coffee ferdig |
| eurusd-engine | NFP-surprise-momentum | Etter crude ferdig |

**Rate:** 1 ny engine per 2-3 mnd. **Ikke prøv å bygge alle 22 instrumenter parallelt — det er hva som ødela Bedrock.**

---

## 7. Migrasjon fra Bedrock

### 7.1 Hva å gjenbruke (~80% av Bedrock)

**Direkte gjenbruk:**
- `bedrock.data.store.DataStore` (SQLite-schema works)
- `bedrock.fetch.*` (alle 34 fetchers)
- `bedrock.config.secrets` (env-loader)
- `bedrock.backtest.runner` (kan adapteres for ny engine-API)
- Alle backfilled data (12-14 års historikk)
- systemd-fetcher-timers (uendret)

**Adapter-laget:**
- `bedrock.engine.drivers.*` — driver-implementasjoner gjenbrukes, men aggregerings-laget byttes ut

**Nytt:**
- Signal-bus + signal-protokoll
- Engine-template
- Bot multi-engine consumer
- Setup-finder (S/R-detektor med significance)
- Conviction-scorer (flat 5-7 drivere, ingen familier)

### 7.2 Cut-over-strategi

**Måned 1-2:** Bygg infrastruktur (Fase 0). Bedrock-current kjører uendret.

**Måned 3-4:** Bygg sugar-v1 i shadow-mode. Logg signaler parallelt med Bedrock-current. Ikke utfør live ennå.

**Måned 5:** A/B-sammenligning på live data. sugar-v1 vs Bedrock-sugar.

**Måned 6:** Hvis sugar-v1 vinner: cut over sugar til ny engine. Bedrock-sugar fortsetter som "research-mirror".

**Måned 7-12:** Bygg wheat, coffee, etc. Pensjonere Bedrock-current per-instrument etter hvert som ny engine validert.

---

## 8. Risiko + åpne spørsmål

### 8.1 Tekniske risikoer

| Risiko | Mitigering |
|---|---|
| Signal-bus blir flaskehals | Start med filsystem; bytt til Redis hvis > 100 signaler/sek |
| Engines duplikerer kode | Felles biblioteks-pakke (bedrock.lib.*) for shared logic |
| Outcome-feedback-loop er forsinket | Live-feedback ikke i loop; brukes kun for offline-tuning |
| Bot kompleksitet vokser | Strict separation of concerns: bot eier KUN risk + execution |

### 8.2 Filosofiske risikoer

| Risiko | Mitigering |
|---|---|
| Frister å gjenbruke Bedrock-vekter for sugar-v1 | Eksplisitt forbudt — start med 5 drivere, lærer fra null |
| "1 instrument" blir til 5 før første er validert | Hard rule: ingen ny engine før forrige har 30+ live-trades |
| Track-record-vurdering manipuleres | Engine track-record beregnes BARE av bot, ikke selvrapportert |
| Bot-konfig blir kompleks per engine | Engine sender all config sammen med signal — bot er stateless |

### 8.3 Åpne spørsmål til diskusjon

1. **Signal-bus-teknologi:** filsystem (enkelt) vs HTTP (skalerer) vs Redis (real-time)?
2. **Engine-template-pakkestruktur:** standalone Python-pakke per engine, eller subpakke under bedrock?
3. **Backtest-isolasjon:** skal hver engine ha egen DB-snapshot, eller dele felles store?
4. **Versjonering:** semver per engine eller dato-basert?
5. **Track-record-vekting:** lineær (1.0 = perfekt) eller eksponentiell decay (siste trades vekter mer)?
6. **Shadow-mode-varighet:** 6 mnd er konservativt — kan vi gå live etter 3 mnd hvis backtest er sterk?
7. **Hva skjer med Bedrock-current?** Pensjonering eller "research-modus" parallelt?
8. **Sukker-filosofi:** mean-reversion at S/R som første-utkast, eller andre kandidater (momentum-breakout, event-anticipation)?

---

## 9. Suksesskriterier

### 9.1 Fase 0 (infrastruktur)

- [ ] Signal-protokoll v1.0 dokumentert + Pydantic-validert
- [ ] Bot kan motta + arbitrere signaler fra 2+ engines simultant
- [ ] Outcome-feedback fungerer ende-til-ende
- [ ] 0 kontradiksjons-tilfeller i risk-arbitrasje (verifisert via tester)

### 9.2 Fase 1 (sugar-v1)

- [ ] 14 års backtest med Sharpe ≥ 1.5
- [ ] 6 mnd shadow-mode med PSR ≥ 0.90
- [ ] 0 kontradiktoriske signaler i shadow-mode
- [ ] Drift-monitoring: signal-frekvens stabil ±20% over 30 dager

### 9.3 Fase 2 (wheat-v1)

- [ ] Helt egne drivere (ingen direkte gjenbruk av sukker-vekter)
- [ ] Egen filosofi (basert på wheat-spesifikk research)
- [ ] Sammenlignbar Sharpe på 6-12 mnd shadow-mode
- [ ] Bot håndterer sugar+wheat samtidig uten konflikter

### 9.4 Fase 3+ (skalere)

- [ ] 1 ny engine per 2-3 mnd, IKKE raskere
- [ ] Hver ny engine validert før neste startes
- [ ] Felles infra (DataStore, fetchers, backtest) gjenbrukes uten endringer
- [ ] Bot-side endringer minimale per ny engine (KUN nye risk-cap-konfigs)

---

## 10. Konklusjon

Bedrock-monolitten er ikke uerstattelig — 80% av infrastrukturen (DataStore, fetchers, backtest, drivere) overlever til v3. Det som BYTTES er aggregerings-laget (familier → flat) + coordination-laget (single-direction enforcement) + setup-builder-laget (kontekst-aware).

**Hovedinnsiktene:**
1. **Hver alpha-thesis fortjener egen motor** — ikke prøv å forene 22 instrumenter under én scoring-modell
2. **Bot er passiv risk-arbiter** — ingen logikk om "hvilket signal å ta", bare allokering
3. **Strikt sekvensiell skalering** — 1 instrument fullt validert før neste startes
4. **Setup-først-filosofi** — finn nivå, så scor confluence (motsatt av Bedrock-current)
5. **Outcome-feedback gir læring** — engines tunes basert på faktisk performance, ikke backtest alene

**Neste steg etter operatør-godkjenning:**
- Detaljer Fase 0-arbeidet (infrastruktur)
- Velg sukker-filosofi for v1 (anbefalt: mean-reversion at S/R)
- Sett opp prosjekt-struktur (eget repo eller sub-pakke)
- Lag kickoff-prompt for første implementerings-vindu

---

*Generert 2026-05-06 som strategisk diskusjons-utkast. Status: UTKAST — venter operatør-tilbakemelding på åpne spørsmål (§ 8.3) før implementering starter.*
