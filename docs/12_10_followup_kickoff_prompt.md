# Kickoff-prompt for sub-fase 12.10 follow-up (ny session-kontekst)

Lim hele blokken under inn i en ny Claude Code-session.

---

## START

Sub-fase 12.10 hovedlevering er LUKKET (tag `v0.12.10-fase-12.10-LUKKET`,
2026-05-02). 9 bunker tagget. ~50 nye drivere registrert, ~60 000+ rader
backfilt, 100+ nye tester. Bot fortsetter på cTrader demo i bakgrunnen.

Følg session-start-protokollen i [CLAUDE.md](http://CLAUDE.md):
1. Les [CLAUDE.md](http://CLAUDE.md) (auto-lastet)
2. Les [STATE.md](http://STATE.md) fra topp til første `---`
3. Les [PLAN.md](http://PLAN.md) § 22 (LUKKET-blokk + DEFERRED-liste) og § 22.2 (bunke-spec)
4. Helse-sjekk: `bash scripts/session_[health.sh](http://health.sh)`
5. Bekreft til meg: "Fortsetter på 12.10 follow-up [N]. Helse: [grønn|rød — X]. Blockers: [...]. Jeg starter med [handling]."
6. Vent på godkjenning før arbeid starter.

## Hva som er gjort (referanse)

Per `STATE.md` Current state — sub-fase 12.10 LUKKET-blokk + per-bunke-
notater. Drivere er registrert i:
- `src/bedrock/engine/drivers/macro_bunke3.py` (14 FRED-drivere)
- `src/bedrock/engine/drivers/macro_bunke4.py` (8 Yahoo+CBOE+NOAA-drivere)
- `src/bedrock/engine/drivers/macro_bunke6.py` (6 EIA thin-wrappers)
- `src/bedrock/engine/drivers/macro_bunke7.py` (5 AGSI + 2 COT-drivere)
- `src/bedrock/engine/drivers/macro_bunke8.py` (2 USGS seismic-drivere)
- `src/bedrock/engine/drivers/risk.py` (news_intel_severity_veto)
- 4 cot_ice_mm_pct YAML-wirings i softs-instrumenter
- Bug-fixer: `release_calendar.py`, AsOfDateStore, min_samples-guards

Diff-rapporter: `docs/snapshot_diff_2026-05-02_bunke{1,2,3,9}.md`

## DEFERRED-arbeid — velg ETT spor

Operatør velger neste spor basert på prioritet. Hver av disse er en egen
session-leveranse (ikke alle på en gang).

### Spor A: YAML-wirings (PRIMÆR per § 22.1)
Mest kritisk for å aktivere de ~50 nye registrerte driverne. Må gjøres
basert på empirisk demo-resultat. Anbefalt rekkefølge:

A1. Først wire ~5-10 høyverdige drivere i 3-5 representative YAMLs (f.eks.
    SP500/Nasdaq risk-familie får hy_oas_change + vix9d_vix_ratio +
    cboe_skew_z; CrudeOil/Brent macro får ovx_z + EIA-utvidelser).
A2. Regen baseline + grade-flip-rapport per asset-class.
A3. Hvis ingen systematisk bias: utvid til neste batch instrumenter.
A4. Inkluder #30 (enso_regime → noaa_oni_index), #31 (weather_stress
    1mnd→6mnd), #32 (nfci_change → anfci_z), #42 (drought CONUS-sekundær).

### Spor B: *_surprise data-arkitektur
B1. Velg data-kilde for `actual` (FRED-cross-reference vs alternativ feed
    som tradingeconomics/dailyfx).
B2. Backfill PAYEMS/CPIAUCSL/GDP/PCEPI fra FRED.
B3. Implementer `econ_surprise`-driver med title-pattern + country + bull_when.
B4. 4 YAML-wirings (nfp/cpi/gdp/pce_surprise).

### Spor C: ALSI + IIP-routes (#24/#25)
C1. Skjema-utvidelse `alsi_storage`-tabell + IIP REMIT-tabell.
C2. Fetcher-extensions med GIE-key.
C3. Drivere `alsi_eu_pct`, `alsi_storage_change`, `iip_supply_unavailability`.
C4. Backfill + tester + YAML-wirings.

### Spor D: NASS yield/grain_stocks (#20)
D1. Skjema-utvidelse for nass_yield + nass_grain_stocks-tabeller.
D2. NASS QuickStats-fetcher utvidelser (yield-survey + quarterly-stocks).
D3. Drivere `nass_yield_corn_yoy`, `nass_yield_soy_yoy`, `nass_grain_stocks_quarterly`.
D4. Backfill + tester + YAML-wirings i Corn/Soybean.

### Spor E: Driver-impl-rewrites (#36-#41)
Hver av disse er substantial refactor med behov for tester + ev. baseline-
flips. Anbefalt en-om-gangen.

E1. #36 momentum_z regime-conditional lookback (20d hi-vol, 100d lo-vol)
E2. #37 sma200_align slope-component
E3. #38 range_position ATR-normalisering 14-20d
E4. #39 shipping_pressure 90d-trend + 12mo-MA-regime
E5. #40 hdd_cdd_anomaly per-instrument-vekt
E6. #41 aaii_extreme 8-uker-MA-divergens

### Spor F: Resterende mindre DEFERRED
F1. ism_pmi_level alt-kilde (manuell CSV?)
F2. CBOE pcr_total_extreme + pcr_equity_only fra CBOE-direkte
F3. cboe_vix_term_curve (overlapper med vix_term_ratio — kanskje droppe)
F4. noaa_enso_forecast_3mo fra IRI-CSV
F5. cot_concentration_top4 + cot_swap_dealer_skew (schema-utvidelse)
F6. Treasury auctions (#27) — ny fetcher mot Treasury direct
F7. crypto_sentiment_extreme (vent til ~juli 2026)
F8. eia_natgas_processing (monthly natgas-route)

## Beslutninger som er låst (ikke diskuter på nytt)

Per § 22.1 (PLAN-tag fra 2026-05-02):
- Ingen familie-restruktur — flat YAML beholdes
- Backtest droppet — all validering mot live-demo
- Ingen ADR
- Separat commit per driver/endring, snapshot-baseline regen + diff-rapport
  per leveranse

## Arbeids-stil

- Forklar kort hva du gjør før hvert steg
- Auto-mode er aktivt — utfør, men spør hvis arkitektonisk valg dukker
  opp som ikke er løst i § 22 eller LUKKET-blokken
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

Ikke gå til nytt spor uten min godkjenning.

## SLUTT
