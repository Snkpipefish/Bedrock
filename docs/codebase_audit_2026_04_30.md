# Codebase audit 2026-04-30 (mens harvest+backtest kjører)

**Audit-kontekst:**
- Sub-fase 12.7 LUKKET (`v0.12.7-fase-12.7-LUKKET` på `b379330`).
- Sub-fase 12.6 ÅPEN: detached harvest kjører i GitHub Codespace (`stunning-sniffle-pv459prj4wgh664p`), ETA ~24t fra 2026-04-30 ~20:04 CEST.
- 22 instrumenter, 44 drivere registrert, 33 DB-tabeller.
- Audit kjørt **read-only** mot lokal `data/bedrock.db` (84 MB snapshot, last write 20:03). Ingen lokal harvest-prosess; cloud-VM er separat. Ingen pytest, ingen baseline-regen, ingen DB-skriving.

## Sammendrag

- **1 kritisk funn** (audit-runde 3, 2026-04-30): `event_distance` trippel-bug eskalert til pre-rebalanserings-blocker (Sjekk 9.5).
- **4 medium funn** (krever post-harvest-handling før Fase 13 cutover).
- **6 lav-prio cleanup-items** (housekeeping; kan klumpes).

Det kritiske funnet trenger ikke mid-harvest-respons (read-only DB tillater ikke fix nå), men må adresseres i analyzer-runden FØR YAML-rebalansering for å unngå dobbel-arbeid. Audit-resultatet bekrefter at sub-fase 12.7 ble levert konsistent.

---

## Sjekk 1 — Driver-registry vs faktisk kode

**Resultat:** ✅ Konsistent.

- 44 drivere registrert via `@register("...")` i 10 source-filer (agri, agronomy, analog, currency, macro, positioning, risk, seasonal, structure, trend).
- Alle 44 har minst én test-referanse (når søk inkluderer logical/snapshot-suiter, ikke bare unit-quoted-string).
- `horizon_helpers.py` brukes av agronomy/currency/macro (27 tids-serie-drivere). Andre driver-filer bruker inline mode-dispatch (`positioning.py`, `trend.py`, `structure.py`, `risk.py vol_regime`).
- R4-disiplin B (`_horizon` leses men endrer ikke output) dokumentert i: agri (weather_stress, enso_regime), risk (vol_regime, event_distance), seasonal (seasonal_stage), analog (analog_hit_rate, analog_avg_return). 7 drivere unntatt fra full mode-suite by design — OK.

Ingen funn.

---

## Sjekk 2 — YAML vs driver-registry-konsistens

**Resultat:** ✅ Konsistent. **2 dead drivers** (allerede dokumentert).

- 22 instrumenter laster med Pydantic uten feil.
- 0 ukjente drivere referert i YAML.
- 0 zero-weight uses.
- 0 family-sums != 1.0 (alle innen 1e-6 toleranse).

**Dead drivers (LAV):**
- `currency_cross_trend` — 0 YAML-referanser. Allerede listet i [STATE.md](../STATE.md) som dead siden session 136 audit.
- `igc_stocks_change` — 0 YAML-referanser. Samme dead-status.

**Anbefaling:** vurder å fjerne dead drivers eller wire dem inn i en cross-familie etter 12.6-rebalansering. Ingen umiddelbar handling.

---

## Sjekk 3 — Schema-drift mellom `schemas.py` og DB

**Resultat:** ⚠️ **MEDIUM** — 3 sub-fase 12.6 harvester-tabeller mangler i `schemas.py`.

- `schemas.py` definerer 31 `TABLE_*`-konstanter (inkl. `TABLE_BDI` som legacy-migrasjons-referanse).
- DB inneholder 33 reelle tabeller.
- **3 tabeller i DB uten DDL i `schemas.py`:**
  - `driver_observations` — DDL i [scripts/harvest_driver_observations.py:62](../scripts/harvest_driver_observations.py)
  - `signal_setups` — DDL i [scripts/harvest_driver_observations.py:80](../scripts/harvest_driver_observations.py)
  - `feature_snapshots` — DDL i [scripts/harvest_feature_snapshots.py:113](../scripts/harvest_feature_snapshots.py)
- **0 tabeller i `schemas.py` uten DB-rad** (TABLE_BDI er bevisst legacy-konstant; reelle BDI-data ligger i `shipping_indices` med `index_code='BDI'`, 2888 rader).

**Anbefaling:** Etter 12.6 lukkes — flytt DDL fra harvester-skriptene til `src/bedrock/data/schemas.py` slik at canonical-schema-source er én fil. Idiomet bør være: scripts importerer `DDL_DRIVER_OBSERVATIONS` fra schemas.py, ikke embed inline. Lavbrann-fix.

---

## Sjekk 4 — PLAN § 19.5 vs reality

**Resultat:** ✅ Stemmer 100% med kode-virkeligheten.

| § 19.5 item | Plan-status | Verifisert |
|---|---|---|
| A1 Baker Hughes | DROPPED | ✅ Ingen YAML/driver. Smoke-script artefakt finnes (LAV). |
| A2 AGSI | LEVERT (130) | ✅ Driver `agsi_storage_pct` i macro.py:1832 + tabell `agsi_storage` (18270 rader). |
| A3 FAS | LEVERT (133) | ✅ Driver `fas_exports` i agronomy.py:832 + fetcher `fas_esr.py` + tabell `fas_esr` (100378 rader). |
| A4 CFTC TFF | LEVERT (128) | ✅ Tabell `cot_tff` (3276 rader) + drivere `positioning_lev_funds_pct`/`positioning_asset_mgr_pct`. |
| A5 GLD | LEVERT (132) | ✅ `etf_holdings` ticker='gld' (5593 rader). |
| A6 SLV | LEVERT (132 PARTIAL) | ✅ `etf_holdings` ticker='slv' (5039 rader). |
| A7 PPLT | DROPPED (D2-prep) | ✅ Ingen YAML-referanse. (Se merknad nedenfor.) |
| A8 NOPA | DROPPED (D2-prep) | ✅ Ingen YAML-referanse. |
| A9 USDM | LEVERT (133) | ✅ `drought_monitor` driver + tabell (539 rader). |
| A10 Cecafé | LEVERT (135) | ✅ `cecafe_export_change` driver + tabell `cecafe_exports` (668 rader). |
| A11 ICE certified | DROPPED (D2-prep) | ✅ Ingen driver/tabell. |
| A12 AAII | LEVERT (131) | ✅ `aaii_extreme` driver + tabell `aaii_sentiment` (537 rader). |
| A13 BRL | LEVERT (128) | ✅ Driver `brl_chg5d`. |
| A14 Eskom | DROPPED | ✅ 0 referanser. |
| B1 fundamentals | LEVERT (129) | ✅ 4 nye drivere registrert i macro.py. |
| B2 VIX-term | LEVERT (131) | ✅ `vix_term_ratio` i macro.py:1053. |
| B3 DXY Yahoo-bytte | LEVERT (128) | ✅ (Sekundær FRED beholdes per spec.) |
| B4 weather NG HDD/CDD | LEVERT (131) | ✅ `hdd_cdd_anomaly` i macro.py:951. |
| B5 calspread | DEFERRED Plan-S | ✅ Ingen calspread-driver eksisterer. |
| C1 cot_legacy → cot_tff | LEVERT (128) | ✅ SP500/Nasdaq YAML bruker positioning_lev_funds/asset_mgr (TFF-baserte). |
| C2 Platinum mining_disruption | DROPPED | ✅ Platinum YAML har `mining_disruption@0.3` (seismic uendret). |
| C3 Drop shipping Cotton/Cocoa | LEVERT (133) | ✅ Cotton dxy@0.65 + event@0.15 + fas_exports@0.20; Cocoa dxy@0.85 + event@0.15. |
| C7 Cotton ENSO | UENDRET | ✅ |

**Merknad PPLT:** `etf_holdings_change`-driveren (macro.py:1983, 2015) støtter fortsatt `pplt`-ticker som dispatch-key, men ingen instrument bruker det. Dette er forberedt infrastruktur for Plan-S — ikke en finding.

**Lav-prio:** [scripts/smoke/a1_baker_hughes.py](../scripts/smoke/a1_baker_hughes.py) er artefakt fra D0 smoke-testing for et droppet item. Kan slettes som housekeeping.

---

## Sjekk 5 — Test-coverage per driver

**Resultat:** Alle drivere har tester. **2 drivere under R4-mandat på 7-9 tester**, men begge er thin wrappers rundt felles infrastruktur.

| Driver | Antall tester | Bedømmelse |
|---|---|---|
| `disease_pressure` | 6 | ⚠️ Knapt under 7-mandat. Bør bumpes til 7+ (én extra test for sesong-variasjon eller lookback-grense). |
| `positioning_asset_mgr_pct` | 3 | OK by design. Thin wrapper rundt `_tff_driver_with_modes`-fellesfunksjonen som `positioning_lev_funds_pct` (9 tester) tester grundig. |

Top-tier coverage (>20 tester): `cot_ice_mm_pct` (32), `dxy_chg5d` (43), `sma200_align` (35), `vix_regime` (26), `cot_z_score` (22), `event_distance` (21), `real_yield` (21), `brl_chg5d` (22), `momentum_z` (19), `mining_disruption` (19).

**Anbefaling:** post-harvest, bump `disease_pressure` til ≥7 tester. Lav-prio.

---

## Sjekk 6 — TODO/FIXME-inventory

**Resultat:** ✅ Kun 4 TODO/FIXME i hele src+tests+scripts. Ingen FIXME/HACK.

| Sted | Type | Status |
|---|---|---|
| [src/bedrock/parallel/monitor.py:15](../src/bedrock/parallel/monitor.py) | TODO descriptive | OK — kommentar peker bare på automatiseringsbehov i tekst-rapport. |
| [src/bedrock/bot/instruments.py:149](../src/bedrock/bot/instruments.py) | XXX (false positive) | "XXXUSD" naming-pattern, ikke tech-gjeld. |
| [src/bedrock/backtest/report.py:21](../src/bedrock/backtest/report.py) | TODO **STALE** | Sier "Per-grade- og per-horizon-breakdown er TODO inntil run_orchestrator_replay populerer score/grade. I session 62 er feltene tomme." Per [STATE.md](../STATE.md) session 63 implementerte per-grade-breakdown. **Fjern eller oppdater docstring**. |
| [src/bedrock/backtest/store_view.py:22](../src/bedrock/backtest/store_view.py) | TODO active | COT-publication-lag og weather_monthly-lag er reelle backtest-strict-begrensninger. Behold som dokumentasjon. |

**Anbefaling:** rydd report.py:21 stale TODO i samme cleanup-runde som housekeeping-items. LAV.

---

## Sjekk 7 — Dead imports / unused code

**Resultat:** ✅ `ruff --select F401,F841` på `src/`, `tests/`, `scripts/` returnerer **All checks passed!**.

Pyright src/ har vært låst 0/0/0 siden session 77a. CI-blocking. Ingen funn.

---

## Sjekk 8 — Tag-konsistens

**Resultat:** ⚠️ **LAV-MEDIUM** — én tag-anomali i d3-tagging.

| Tag | Faktisk commit | Commit-melding | Forventet (per STATE) |
|---|---|---|---|
| `v0.12.7-r4-finish` | `b3e52d59` | feat(driver): analog + seasonal horizon-aware-ready (R4 finish) | OK |
| `v0.12.7-d0` | `5e61e7dc` | feat(smoke): D0 smoke-tests... | OK |
| `v0.12.7-d1` | `f7d30723` | state: session 130 avsluttet — D1 LUKKET... | OK (på STATE-commit per session 130 close) |
| `v0.12.7-d2` | `e5dc0568` | state: session 134 avsluttet — D2 LUKKET... | OK (på STATE-commit) |
| `v0.12.7-d3` | `b3793301` | state: session 135 avsluttet — sub-fase 12.7 LUKKET... | ⚠️ **STATE.md sa: "Tag `v0.12.7-d3` settes på `ebf8690` (siste D3-commit, før dette STATE-commit)".** Faktisk peker tagen på STATE-commiten, ikke på `ebf8690` ("docs(12.7): grade-validering ×12mnd × 22 instrumenter"). |
| `v0.12.7-fase-12.7-LUKKET` | `b3793301` | (samme som d3) | OK per STATE: "samme commit som overordnet sub-fase-finale-tag". |

**Anbefaling:** Vurder å re-tagge `v0.12.7-d3` til `ebf8690` for å matche STATE-intensjonen, eller oppdater STATE-historikken til å reflektere at d3 bevisst ble lagt på STATE-commit. Kosmetisk; begge tags identifiserer samme sub-fase-tilstand. **Ikke fix mid-harvest** (re-tagging endrer git-historikk).

---

## Sjekk 9 — Open tech-gjeld vs reality

**Resultat:** ✅ Alle dokumenterte tech-gjeld-items i [STATE.md](../STATE.md) bekreftet fortsatt åpne.

### 9.1 — FRED-fetcher hard-fail-policy

[src/bedrock/config/fetch_runner.py:307-340](../src/bedrock/config/fetch_runner.py): Når `FRED_API_KEY` mangler returnerer runner per-serie-error med error-string (mykt — ingen exception). Når den er satt, kalles `fetch_fred_series` som raiser `FredFetchError` på network/parse-feil ([src/bedrock/fetch/fred.py:82-119](../src/bedrock/fetch/fred.py)).

**Status:** ikke entydig "hard-fail". Den per-serie-feil-rapporteringen i runner er soft. Den underliggende `fred.py`-modulen raiser. Tech-gjeld-formuleringen er upresis — krever bruker-avklaring på om problemet er:
(a) at runner skulle raise i stedet for å rapportere per-serie, eller
(b) at fred.py skulle returnere error-resultat i stedet for raise.

**Anbefaling:** spør bruker post-harvest hva spesifikk policy-endring som er ønsket.

### 9.2 — NOPA WASDE-utvidelse

[src/bedrock/fetch/wasde.py](../src/bedrock/fetch/wasde.py): grep "crush" gir **0 treff**. WASDE har ikke crush-metric ekstrahert.

**Status:** ÅPEN bekreftet. Fix krever utvidelse av ESMIS XML-parser til å fange crush-attributter (hvis WASDE-rapportene faktisk inneholder dem — bør verifiseres mot rå XML først).

### 9.3 — CONAB Café-PDF-historikk

DB `conab_estimates`: 158 rader totalt, 6 av disse er Café (commodity in {`cafe_arabica`, `cafe_conilon`, `cafe_total`}).

Manuell-mappe `bedrock manuell data/cafe_boletins/`: 1 PDF (`safra-2026_1o_boletim-de-safras-cafe-fevereiro-26.pdf`, 1.2 MB).

**Status:** ÅPEN bekreftet. Fix krever:
1. Ny `cafe`-subkommando i [scripts/ingest_manual_data.py](../scripts/ingest_manual_data.py) (eller utvidelse av `conab`-subkommandoen).
2. Nedlastning av historiske Café-boletins fra `conab.gov.br/info-agro/safras/cafe`.

### 9.4 — fas_esr.py L134 stale docstring

Verifisert: [src/bedrock/fetch/fas_esr.py:134](../src/bedrock/fetch/fas_esr.py) sier `Cotton=501`. Per session 133 STATE: "Cotton-kode korrigert mid-session 501 → 1404 (`All Upland Cotton` aggregat)". Koden bruker 1404 i kall; docstringen er stale.

**Status:** ÅPEN bekreftet. **Fix er en én-linje docstring-edit**.

### 9.5 — event_distance monotone-bug — **DYP-DIAGNOSE 2026-04-30 (audit-runde 3)**

**Bekreftet bug-omfang:** `driver_observations` har **3153 rader for `event_distance`, ALLE med driver_value=1.0** (empty_score=max). Spenner 780 distinct ref_dates 2010-01-25 → 2026-03-02. Påvirker per nå 6 av 22 wirede instrumenter (Brent 1714, CrudeOil 1001, Cotton 155, Sugar 156, GBPUSD 123, NaturalGas 4) — øvrige 16 mangler harvest-rader fordi Codespace-pass pågår.

**Klassifisering: Type D — KOMPOUNDED bug i 3 lag.** Den preliminære hypotesen i audit-runde 1 ("harvester sender ikke `_now=ref_date`") var bare ⅓ av historien. Faktisk root-cause spenner driver-, engine- OG ingest-laget.

**Type A — Engine `_now`-propagering mangler (KRITISK):**
- Harvester ([scripts/harvest_driver_observations.py:281](../scripts/harvest_driver_observations.py)) sender `now=ref_ts.to_pydatetime()` til `generate_signals(...)` ✅ riktig
- Men [signals.py:233](../src/bedrock/orchestrator/signals.py) lagrer `run_ts = now or datetime.now(...)` og bruker det KUN til `stabilize_setup(now=run_ts)` ([signals.py:598](../src/bedrock/orchestrator/signals.py)) for hysterese
- [signals.py:_compute_scores:359-393](../src/bedrock/orchestrator/signals.py) sender ikke `run_ts` videre til `eng.score(...)` — `Engine.score`-signaturen aksepterer ikke `now`
- [engine.py:384-388](../src/bedrock/engine/engine.py) propagerer `params_with_dir = {**driver.params, "_direction": ..., "_horizon": ...}` — `_now` mangler i listen
- [risk.py:201-205](../src/bedrock/engine/drivers/risk.py) faller tilbake til `datetime.now(timezone.utc)` = harvest-tidspunkt
- **Konsekvens:** for alle 780 ref_dates er `now`-konteksten fast = harvest-tid. Alle rader får samme score basert på events-state ved harvest-kjøring.

**Type B — `ingest_forex_factory` setter `fetched_at = event_ts` uten publikasjons-lag (KRITISK for backtest-realisme):**
- [scripts/ingest_manual_data.py:91-97](../scripts/ingest_manual_data.py) hardkoder `filtered["fetched_at"] = filtered["event_ts"]` med kommentar "Forex Factory publiserer events i forveien så event_ts ≈ fetched_at er rimelig tilnærming". Det er IKKE rimelig: events publiseres typisk 1-7 dager før event-tidspunkt.
- AsOfDateStore.get_econ_events ([store_view.py:236-263](../src/bedrock/backtest/store_view.py)) clipper på `fetched_at <= as_of_date`. Harvester setter `as_of_date = pd.Timestamp(ref_date_str)` = midnatt UTC.
- Verifisert: for ref_date='2010-02-12' (00:00 UTC) returnerer underlying store 4877 rader, men AsOfDateStore returnerer **0 rader** fordi alle events samme dag har `fetched_at=event_ts > 00:00`.
- Bug påvirker ALLE drivere som leser `get_econ_events` via AsOfDateStore i backtest, ikke bare event_distance. Per nå er event_distance eneste konsument.
- Live-mode `calendar_ff.py` ([fetch/calendar_ff.py:66](../src/bedrock/fetch/calendar_ff.py)) setter `fetched_at = datetime.now(UTC)` korrekt — events i framtiden får fetched_at < event_ts. Bug-en er lokal til CSV-import.

**Type C — Driver-design for backtest-snapshot (DESIGN-TWEAK):**
- Default `min_hours=4`, `lookahead_hours=24`. For backtest-snapshot kl 00:00 UTC vil events typisk være 6-24h unna (markeds-åpningstid 12:30-21:00 UTC for US-events) → `nearest_h2e ≥ 4.0` → score=1.0 nesten alltid.
- Selv simulert med Type-A+B fikset (manuell `_now` + bypassed AsOfDateStore-clipping): for sample 30 ref_dates Brent ga driver 1.0 i 30/30 også med `min_hours=24, lookahead=72`.
- Driveren ble designet for live trading ("vent-med-entry"-flagg når event er 0-4h unna). For IC-måling i backtest trenger den enten dag-granularitet eller en `mode: 'live' | 'snapshot'`-bryter.

**Andre drivere som leser `_now`:** Kun `event_distance`. Verifisert via grep over `src/bedrock/engine/drivers/`. Alle andre tids-bevisste drivere bruker `AsOfDateStore`-wrappet store-side filtrering (som fungerer korrekt for ikke-econ_events-tabeller siden de bruker `event_ts/report_date` ikke `fetched_at`).

#### Fix-spec (post-harvest)

**Estimert kompleksitet:** Medium-large (3 lag, +1 backfill-pass).

**Steg 1 — Type A: Engine `_now`-propagering**
1. `engine.py:Engine.score(...)`: legg til `now: datetime | None = None` parameter.
2. `engine.py:_score_families(...)`: motta `now`, legg `_now=now.isoformat() if now else None` i `params_with_dir`.
3. `signals.py:_compute_scores(...)`: aksepter `now: datetime | None`, send til `eng.score(..., now=now)`.
4. `signals.py:253`: kall `_compute_scores(..., now=run_ts)`.
5. Behold `risk.py:201-205` fallback-logikken (test-friendly).
6. Tester: 2 nye unit-tester i `tests/unit/test_engine_now_propagation.py` — `test_now_propagated_to_driver_params` + `test_no_now_falls_back_to_wallclock`.

**Steg 2 — Type B: Forex Factory backfill med publikasjons-lag**
1. `ingest_manual_data.py:91-97`: legg til `--publication-lag-days INT` arg (default 7). Sett `filtered["fetched_at"] = filtered["event_ts"] - pd.Timedelta(days=publication_lag_days)`.
2. Re-import `data/manual/forex_factory_2007_2025.csv` med `--publication-lag-days 7`. Krever lokal DB-write; må vente til Codespace-harvest er ferdig OG synkronisert lokalt, eller kjøres i Codespace selv etter harvest.
3. Tester: oppdater `tests/integration/test_ingest_forex_factory.py` (hvis finnes) til å assert at fetched_at < event_ts.

**Steg 3 — Type C: Driver backtest-mode (valgfri, vurder etter steg 1+2)**
1. Etter steg 1+2 er live: kjør event_distance for sample ref_dates med ekte `_now=ref_date+12:00:00` UTC (markeds-tid) og sjekk om variasjon dukker opp. Hvis fortsatt monotone → driver-design må endres.
2. Foreslått driver-endring: ny param `snapshot_time_offset_hours` (default 0 for live, 12 for backtest) som forskyver `_now` i driver-koden; eller `mode: 'live' | 'snapshot'` der `snapshot`-mode bruker dag-buckets ("event innen 1 dag = score X").
3. Beslutning utsettes til etter steg 1+2 + IC-måling.

**Steg 4 — Backfill driver_observations**
1. Slett event_distance-rader for berørte ref_dates: `DELETE FROM driver_observations WHERE driver_name='event_distance';` (3153 rader, alle ugyldige).
2. Re-kjør harvest med fixet kjede — kun event_distance trenger backfill, andre drivere er upåvirket.
3. Forventet utfall: ≥5 distinct values, IC vs forward_return > 0.

**Verifisering**
1. SQL: `SELECT COUNT(DISTINCT driver_value) FROM driver_observations WHERE driver_name='event_distance';` → forvent ≥5.
2. Per-instrument distribusjon viser ikke-monoton spredning (avg ≠ 1.0).
3. Analyzer-rebalansering rapporterer IC > 0 for event_distance, driveren beholder plass i risk-familien.

**Side-effekter etter fix**
- Score-endring for 22 instrumenter (event_distance-vekt 0.10-0.30 i risk-familie): grade-flips og publish-flag-endringer forventes.
- Krever ny baseline (men 12.6 baseline lages uansett etter harvest-end).
- Påvirker rebalanserings-output: med bug-tilstand droppes driveren (IC=0). Med fix bevares og re-vektes.
- Eksponerer `_now`-propagering for fremtidige tids-bevisste drivere — muligheter (ikke umiddelbar effekt).

**Status:** ÅPEN — eskalert til **PRE-REBALANSERINGS-BLOCKER** for sub-fase 12.6 analyzer-runde. Se [STATE.md](../STATE.md) tech-gjeld-blokken.

### 9.6 — AAII bull_bear_spread-bug

Per [STATE.md:200-220](../STATE.md): alle 537 rader har `bull_bear_spread ≈ 100.0` (bug — fetcher skriver `bull + neutral + bear` i stedet for `bull - bear`). Workaround i `signal_server` siden commit `5b526c3`. **Status:** ÅPEN bekreftet (ingen kode-endring siden STATE-entry).

### 9.7 — Setup→bot signal-format-mismatch

Per [STATE.md:222-275](../STATE.md): `signals_bot.json` har annen schema enn `bot/entry.py` forventer. Fix er stor (adapter-design + end-to-end-test). **Status:** ÅPEN bekreftet — utsatt til etter harvest, før Fase 13 cutover.

---

## Sjekk 10 — Manuell data-bedrock-kobling

**Resultat:** ⚠️ **MEDIUM** — 3 manuell-mapper mangler ingest-pathway eller README.

| Mappe | README | Ingest-vei | DB-rader | Status |
|---|---|---|---|---|
| `cafe_boletins/` | ❌ | **ingen subkommando** (kun cecafé-fetcher dekker eksport-data, ikke CONAB Café-boletim) | 6 cafe-rader (alle fra fetcher) | **GAP — orphan PDF** |
| `comex data/` | ❌ | **ingen `comex` subkommando** | 12 rader (kun fra fetcher) | **GAP — KRITISK 1 ikke fullført** |
| `conab_boletins/` | ❌ | `conab` subkommando OK | 158 rader | OK, men mangler README |
| `gld_holdings/` | ✅ | `gld` subkommando | 5593 rader | OK |
| `slv_holdings/` | ✅ | `slv` subkommando | 5039 rader | OK |
| `ice_certified_stocks/` | ✅ | DROPPED (A11) | n/a | OK |
| `nopa_crush/` | ✅ | DROPPED (A8) | n/a | OK |
| `pplt_holdings/` | ✅ | DROPPED (A7) | n/a | OK |
| `forex_factory_2007_2025.csv` (toppnivå) | n/a | `forex` subkommando | 41063 rader (CSV har 83428 linjer) | ✅ **Bevisst filter** — High+Medium impact only per session 118 STATE-entry. Low + Non-Economic events filtreres ut for å redusere støy i `event_distance`-driver. Ikke bug. |
| `unica_quinzenal_latest.pdf` (toppnivå) | n/a | **ingen** | 1 rad i unica_reports (fra fetcher) | **GAP — orphan PDF** |
| `Baltic Dry Index ... .pdf` (toppnivå) | n/a | `bdi` subkommando | 2888 rader BDI i shipping_indices | OK |

**Anbefaling (MEDIUM):**
1. Legg til `comex`-subkommando i `ingest_manual_data.py` for å laste manuell COMEX inventory-data (KRITISK 1 PARTIALLY RESOLVED → fully resolved).
2. Legg til `cafe`-subkommando for CONAB Café-boletins (parallelt med 9.3).
3. ~~Verifisér at `forex` 41063/83428-ratio er bevisst~~ — **AVKLART**: bevisst High+Medium impact-filter per session 118 STATE-entry. Ikke action.
4. Skriv README.md i `cafe_boletins/`, `comex data/`, `conab_boletins/` — matcher mønsteret fra D2-prep-mapper.
5. UNICA manuell PDF: enten lag `unica`-PDF-parser-subkommando, eller dokumenter at manuell PDF kun er for arkiv-formål (fetcher dekker fersk data).

---

## Anbefalt handlings-rekkefølge for post-harvest-sessioner

### Kritisk (gjør i 12.6 analyzer-runde — FØR rebalansering)

1. **event_distance trippel-bug** (Sjekk 9.5) — **PRE-REBALANSERINGS-BLOCKER** (eskalert audit-runde 3). Type D kompounded bug i 3 lag (engine `_now`-propagering + Forex Factory ingest fetched_at-bug + driver-design). Hvis ikke fikset før analyzer kjøres, vil rebalansering droppe driveren (IC=0) — som så må re-introduseres etter fix → dobbel rebalansering. Se Sjekk 9.5 fix-spec.

### Medium (gjør før Fase 13 cutover)

1. **Setup→bot signal-format-mismatch** (Sjekk 9.7) — adapter-design er størst arbeid. Egen session.
2. **AAII bull_bear_spread fetcher-fix** (Sjekk 9.6) — fix fetcher + backfill 537 rader. Sjekk om driver leser kolonnen direkte.
3. **Manuell-data ingest-gaps** (Sjekk 10) — `comex` + `cafe` subkommandoer i `ingest_manual_data.py`. KRITISK 1 + 9.3 løses sammen.
4. **Schema-drift** (Sjekk 3) — flytt 3 harvester-tabellers DDL fra scripts/ til src/bedrock/data/schemas.py.

### Lav-prio (housekeeping-runde — kan klumpes)

1. **fas_esr.py L134 stale docstring** (Sjekk 9.4) — én linje.
2. **report.py:21 stale TODO** (Sjekk 6) — fjern eller oppdater (per-grade-breakdown ble levert i session 63).
3. **disease_pressure tester < 7** (Sjekk 5) — bump til ≥7.
4. **Dead drivers** (Sjekk 2) — vurder fjerning av `currency_cross_trend` og `igc_stocks_change`, eller wire dem inn der det gir mening.
5. **scripts/smoke/a1_baker_hughes.py** (Sjekk 4) — slett D0-artefakt for droppet item.
6. **Tag-anomali** (Sjekk 8) — re-tagg `v0.12.7-d3` til `ebf8690`, eller dokumenter avviket. **Ikke gjør mid-harvest.**

### Spørsmål til bruker (post-harvest)

- **FRED hard-fail-policy** (Sjekk 9.1): hva er konkret policy-endring som ønskes? Soft per-serie-rapportering i runner vs. hard raise i underliggende `fred.py`?
- **NOPA WASDE-utvidelse** (Sjekk 9.2): er det bekreftet at WASDE-rapportene faktisk inneholder crush-data (rå XML)? Hvis ikke, dropp tech-gjeld-item.
- ~~**forex_factory CSV** (Sjekk 10): er 41063/83428-ratio (50%) bevisst impact-filter, eller bug i ingest?~~ — **AVKLART 2026-04-30 audit-runde 2:** Bevisst High+Medium-filter per session 118 STATE. Ikke spørsmål til bruker.

---

**Audit lukket (3 runder).** Neste handling: vente på Codespace-harvest, så kjør session 137 (analyzer-execution + YAML-rebalansering). **Pre-rebalanserings-blocker:** event_distance-trippel-bug (Sjekk 9.5) må fikses først, ellers vil rebalansering droppe driveren og kreve dobbel re-balanseringsrunde.
