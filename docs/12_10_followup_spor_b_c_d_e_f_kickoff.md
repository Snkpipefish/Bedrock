# Kickoff-prompt for sub-fase 12.10 follow-up Spor B-F (nytt kontekstvindu)

Lim hele blokken under inn i en ny Claude Code-session.

---

## START

Sub-fase 12.10 hovedlevering er LUKKET (tag `v0.12.10-fase-12.10-LUKKET`,
2026-05-02). Spor A (YAML-wirings av 12.10-bunke-drivere) er **også
LUKKET** 2026-05-02 etter 11 sub-spor (A1-A11). Tags `v0.12.10-followup-a1`
... `v0.12.10-followup-a11`.

**A-track totalsammendrag:**
- 52 wirings + 11 replacements (22/22 instrumenter dekket)
- 2 grade-flips totalt (begge SP500/Nasdaq SWING buy B→A i A10, modest)
- Bunker fullt wired: 6 (EIA), 7 (AGSI)
- 28 unike nye drivere i bruk
- Pyright src/: 0 errors
- Snapshot-baseline regenerert per spor

Bot fortsetter på cTrader demo i bakgrunnen.

## Følg session-start-protokollen i [CLAUDE.md](http://CLAUDE.md):

1. Les [CLAUDE.md](http://CLAUDE.md) (auto-lastet)
2. Les [STATE.md](http://STATE.md) fra topp til første `---`
3. Les [PLAN.md](http://PLAN.md) § 22.5 (A-track LUKKET-blokk), § 22.6 (Spor B-F-spec), § 22.7 (anbefalt rekkefølge)
4. Helse-sjekk: `bash scripts/session_health.sh`
5. Bekreft til operatør: "Fortsetter på 12.10 follow-up [Spor X] [N]. Helse: [grønn|rød — X]. Blockers: [...]. Jeg starter med [handling]."
6. Vent på godkjenning før arbeid starter (kun hvis du må gjøre arkitektoniske valg som ikke er låst i § 22.1; ellers utfør direkte).

## DEFERRED-arbeid — velg ETT spor

Per § 22.7 anbefalt rekkefølge:

### Spor C: ALSI + IIP-routes (ANBEFALT FØRST per § 22.7)
Bygger direkte på AGSI-mønster fra bunke7. GIE-key allerede registrert (én key dekker AGSI+ALSI+IIP). Lavest risk for høy verdi.

C1. Schema-utvidelse `alsi_storage`-tabell + IIP REMIT-tabell.
C2. Fetcher-extensions med GIE-key.
C3. Drivere `alsi_eu_pct`, `alsi_storage_change`, `iip_supply_unavailability`.
C4. Backfill + tester + YAML-wirings (NaturalGas + Brent macro).
C5. Snapshot-baseline regen + diff-rapport.

**Estimat:** 1-2 sessioner.

### Spor D: NASS yield/grain_stocks
USDA NASS QuickStats-utvidelse. Bygger på eksisterende Crop Progress-fetcher.

D1. Schema-utvidelse `nass_yield` + `nass_grain_stocks`-tabeller.
D2. NASS QuickStats-fetcher utvidelser (yield-survey + quarterly-stocks-routes).
D3. Drivere `nass_yield_corn_yoy`, `nass_yield_soy_yoy`, `nass_grain_stocks_quarterly`.
D4. Backfill + tester + YAML-wirings (Corn + Soybean yield/cross-familier).
D5. Snapshot-baseline regen + diff-rapport.

**Estimat:** 1-2 sessioner.

### Spor B: *_surprise data-arkitektur
**Substantial — ADR-014 kreves.** Implementere `nfp_surprise`/`cpi_surprise`/`gdp_surprise`/`pce_surprise` i ny `event`-familie.

**Blocker:** FF mangler actual; FRED PAYEMS/CPIAUCSL/GDP/PCEPI mangler i DB.

B1. Velg data-kilde for actual-felt (FRED-cross-reference vs alt feed).
B2. Backfill PAYEMS/CPIAUCSL/GDP/PCEPI fra FRED.
B3. Implementer cross-source-join-logikk.
B4. 4 `econ_surprise`-drivere med title-pattern + country + bull_when.
B5. 4 YAML-wirings (SP500/Nasdaq/USDJPY/EURUSD `event`-familie).
B6. Snapshot-baseline regen + diff-rapport.

**Estimat:** 2-3 sessioner.

### Spor E: Driver-impl-rewrites (#36-#41 + #34)
**Best etter ~2-4 uker live-demo** for empirisk underperform-data. Hver er substantial refactor.

E1. #36 `momentum_z` regime-conditional lookback (20d hi-vol, 100d lo-vol)
E2. #37 `sma200_align` slope-component
E3. #38 `range_position` ATR-normalisering 14-20d
E4. #39 `shipping_pressure` 90d-trend + 12mo-MA-regime
E5. #40 `hdd_cdd_anomaly` per-instrument-vekt
E6. #41 `aaii_extreme` 8-uker-MA-divergens
E7. #34 multi-lookback-konsolidering (~25 drivere)

**Estimat:** 6-7 sessioner.

### Spor F: Resterende mindre DEFERRED
Lav prioritet; ta opportunistisk.

F1. ism_pmi_level alt-kilde (manuell CSV-fallback?)
F2. CBOE pcr_total_extreme + pcr_equity_only fra CBOE-direkte
F3. cboe_vix_term_curve (overlapper vix_term_ratio — kanskje droppe)
F4. noaa_enso_forecast_3mo fra IRI-CSV
F5. cot_concentration_top4 + cot_swap_dealer_skew (schema-utvidelse)
F6. Treasury auctions (#27) — ny fetcher mot Treasury direct
F7. crypto_sentiment_extreme (vent til ~juli 2026 når 100+ rader)
F8. eia_natgas_processing (monthly natgas-route)

**Estimat:** 4-6 sessioner totalt.

### Mini-spor: enso_regime cleanup
Død driver i `agri.py` (erstattet i alle agri-YAMLs i A4 med noaa_oni_index, men brukes fortsatt av analog-dim-extractor i `bedrock/data/analog.py`).

Subtasks:
- Oppdater `_extract_enso_regime` til å lese fra ONI-series direkte (samme data, men matcher noaa_oni_index-driver-mønster).
- Slett `enso_regime`-driver i `agri.py`.
- Oppdater 3 testfiler: `test_drivers_r4_horizon_only.py`, `test_analog_dims.py`, `test_drivers_agri.py`.
- Tag som `v0.12.10-followup-cleanup-enso`.

**Estimat:** 1 session, low-risk hvis tester følger med.

## Beslutninger som er låst (ikke diskuter på nytt)

Per § 22.1 (PLAN-tag fra 2026-05-02):
- Ingen familie-restruktur — flat YAML beholdes (ny `event`-familie kun for *_surprise i Spor B)
- Backtest droppet — all validering mot live-demo
- Ingen ADR (unntatt ADR-014 hvis Spor B krever cross-source-arkitektur)
- Separat commit per driver/endring, snapshot-baseline regen + diff-rapport per leveranse

## Memory-feedback aktivt

Fra tidligere sessioner:
- `dont-ask-process-decisions`: Bestem commit-rekkefølge OG spor-valg selv. Ikke spør operatør om disse prosess-beslutningene.
- `free-api-no-parallel-requests`: Sekvensielle HTTP-kall mot gratis API-er, ikke parallelle.
- `baseline-regen-needs-fresh-python`: Snapshot-regen må starte fra ny Python-prosess hvis driver-registry endres mid-session.
- `test-scope-proportional-to-change`: Scoped pytest for små endringer, full suite kun ved fase-LUKKING / delt-kode-sti.

## Arbeids-stil

- Forklar kort hva du gjør før hvert steg
- Auto-mode er aktivt — utfør, men spør hvis arkitektonisk valg dukker opp som ikke er løst i § 22 eller LUKKET-blokken
- Bruk TodoWrite for å spore framgang innen valgt spor
- Snapshot-baseline diff-rapport per leveranse
- Stop-criterion: ≤5 grade-flips per asset-class. Eskaler hvis brutt.

## Når du er ferdig med valgt spor

Stop og rapporter til meg:
- Hva ble levert (commits + tag-navn)
- Antall drivere/tabeller berørt
- Grade-flip-distribusjon per asset-class
- Eventuelle anomalier
- Klar-meld for neste spor

Ikke gå til nytt spor uten min godkjenning (men fortsett innen sub-trinn av valgt spor selv).

## SLUTT
