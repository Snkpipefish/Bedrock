# Kickoff-prompt for sub-fase 12.10 follow-up Spor F (nytt kontekstvindu)

---

## START

Sub-fase 12.10 hovedlevering er LUKKET (tag `v0.12.10-fase-12.10-LUKKET`,
2026-05-02). Spor A LUKKET 2026-05-02 (A1-A11, 52 wirings). Spor C
LUKKET 2026-05-02 (`v0.12.10-followup-spor-c`, ALSI+IIP REMIT). Spor D
LUKKET 2026-05-02 (`v0.12.10-followup-spor-d`, NASS yield+grain_stocks).
Spor B LUKKET 2026-05-02 (`v0.12.10-followup-spor-b`, *_surprise +
event-familie + ADR-014). **Tre av fem follow-up-spor lukket.**

**Akkumulert resultat:** 11 nye tabeller, 6 nye fetchere/extensions,
~24 nye drivere wired, 250+ nye tester, ~78000 nye datarader. Pyright
src/: 0 errors. Bot fortsatt på cTrader demo hele veien.

**Spor E utsatt til ~2026-06-01** (~4 uker etter Spor B live-demo-
start) per bruker-beslutning 2026-05-02. Empirisk underperform-data
trumfer refactor-på-tro.

## Følg session-start-protokollen i CLAUDE.md:

1. Les CLAUDE.md (auto-lastet)
2. Les STATE.md fra topp til første `---`
3. Les PLAN.md § 22.5 (A-track LUKKET-blokk), § 22.6 (Spor F-spec
   under "Spor F: Resterende mindre DEFERRED"), § 22.7 (rekkefølge —
   B/C/D LUKKET, F NESTE, E utsatt til ~2026-06-01).
4. Helse-sjekk: `bash scripts/session_health.sh`
5. Bekreft til operatør: "Fortsetter på 12.10 follow-up Spor F. Helse:
   [grønn|rød — X]. Blockers: [...]. Jeg starter med [F-X]."
6. Vent på godkjenning før arbeid starter (kun hvis arkitektoniske
   valg som ikke er låst i § 22.1; ellers utfør direkte).

## Spor F: Resterende mindre DEFERRED — subtasks

Per § 22.6. Hver subtask er liten, men data-tilgang varierer.
Foreslått kjøre-rekkefølge: lavest-risk-først.

### F1: ism_pmi_level alt-kilde
- **Status:** DEFERRED i bunke3 (FRED NAPMPMI returnerer 404 — ISM har
  trukket gratis-feeden).
- **Forslag:** Manuell CSV-fallback fra dag 1 per ADR-007 § 4. Bruker
  populerer `data/manual/ism_pmi.csv` månedlig fra ISM-rapportens HTML
  (gratis å se, ikke automatiserbart pga login).
- **Estimat:** 1 session.
- **Subtasks:** schema → manuell-CSV-loader-extension → driver `ism_pmi_level`
  i macro_bunke3.py → manuell sample-data + dokumentasjon → YAML-wirings
  (SP500/Nasdaq macro-familie).

### F2: CBOE pcr_total_extreme + pcr_equity_only fra CBOE-direkte
- **Status:** DEFERRED i bunke4 (Yahoo har ikke disse; CBOE har egen feed).
- **Forslag:** Ny `bedrock.fetch.cboe_pcr.py` mot CBOE's daglige CSV
  (`https://cdn.cboe.com/api/global/us_indices/daily_options_data/...` —
  gratis, ikke token).
- **Estimat:** 1-2 sessioner.
- **Subtasks:** schema (cboe_options_pcr-tabell) → fetcher → 2 drivere
  → backfill (~5 år historikk fra CBOE) → YAML-wirings (SP500/Nasdaq
  positioning eller risk-familie).

### F3: cboe_vix_term_curve
- **Status:** DEFERRED — overlapper `vix_term_ratio` (allerede levert
  i bunke3 fra Yahoo VIX/VIX3M/VIX6M).
- **Forslag:** **Droppe.** Eksisterende vix_term_ratio dekker samme signal-
  domene; CBOE-direkte gir ikke ekstra-verdi. Dokumenter som "ikke-
  levert / overlapp" i PLAN.
- **Estimat:** 0 sessioner — bare PLAN-oppdatering.

### F4: noaa_enso_forecast_3mo fra IRI-CSV
- **Status:** DEFERRED — NOAA gir ikke forward-forecast i CFSv2-feeden;
  IRI (Columbia U) publiserer 3-mnd-forecast i månedlig PDF/CSV.
- **Forslag:** Manuell CSV-fallback (~1 ny rad/mnd, lite vedlikehold).
  Driver leser IRI ENSO Plumes (ensemble-mean Niño 3.4 sone for 3 mnd
  fram) og mapper til 0..1 score.
- **Estimat:** 1 session.
- **Subtasks:** schema (noaa_iri_forecast-tabell) → manuell CSV-loader
  → driver `noaa_enso_forecast_3mo` → YAML-wirings (Cocoa/Coffee/Sugar
  enso-familie).

### F5: cot_concentration_top4 + cot_swap_dealer_skew
- **Status:** DEFERRED — Conc_Net-kolonner ikke i `cot_disaggregated`-
  schema; Swap Dealer-kategori kun i TFF-rapport.
- **Forslag:** Schema-utvidelse. cot_disaggregated får conc_net_top4,
  conc_net_top8 (parses fra eksisterende CFTC-feed som allerede har
  disse kolonnene — bare ikke lagret i bedrock). cot_tff er allerede
  i bedrock; legge til swap_long/swap_short kolonner.
- **Estimat:** 1-2 sessioner.
- **Subtasks:** schema-ALTER (idempotent) → fetcher-extension → 2 drivere
  → re-backfill av eksisterende rader fra CFTC-arkiv → YAML-wirings
  (de fleste energy/agri-instrumenter med cot_disaggregated).

### F6: Treasury auctions (#27)
- **Status:** DEFERRED — ingen data, ingen fetcher.
- **Forslag:** Ny fetcher mot Treasury Direct's TreasuryDirect API
  (`https://www.treasurydirect.gov/TA_WS/securities/...` — gratis JSON-
  API). Auction results, bid-to-cover, indirect-bidder %, primary-
  dealer-takedown.
- **Estimat:** 1-2 sessioner.
- **Subtasks:** schema (treasury_auctions-tabell) → fetcher → driver
  `treasury_auction_demand` → backfill (10 år) → YAML-wirings
  (SP500/Nasdaq macro eller positioning).

### F7: crypto_sentiment_extreme (vent til ~juli 2026)
- **Status:** DEFERRED per spec. Schema/fetcher allerede levert i
  session 115. Driver mangler — venter til ≥100 rader er akkumulert
  (~juli 2026). Dagens DB har ~30 rader (siden 2026-04-27).
- **Forslag:** **IKKE LEVERE i denne sub-fasen.** Markér i PLAN som
  "venter til 2026-07-01-snapshot ≥100 rader".
- **Estimat:** 0 sessioner nå — 1 session i juli 2026.

### F8: eia_natgas_processing
- **Status:** DEFERRED i bunke6 — krever monthly natgas-processing-route
  i `bedrock.fetch.eia` (egen series-id liste).
- **Forslag:** Utvide eksisterende eia.py med ny `fetch_eia_natgas_
  processing()` som henter NW2_EPG0_VPP_NUS_MMCFM (Plant Liquids
  Production) + NW2_EPG0_VPC_NUS_MMCFM (Processing Plant Capacity Use).
- **Estimat:** 1 session.
- **Subtasks:** fetcher-extension → driver `eia_natgas_processing` i
  macro_bunke6.py → backfill → YAML-wirings (NaturalGas macro).

## Forslått prioritert rekkefølge

1. **F3** (drop overlapping driver) — 0 sessioner, bare PLAN-cleanup
2. **F8** (eia_natgas_processing) — 1 session, lavest risk, bygger på
   eksisterende eia.py
3. **F4** (noaa_enso_forecast_3mo) — 1 session, manuell CSV
4. **F1** (ism_pmi_level) — 1 session, manuell CSV
5. **F2** (CBOE pcr-drivere) — 1-2 sessioner, ny fetcher
6. **F5** (cot_concentration + swap_skew) — 1-2 sessioner, schema-ALTER
7. **F6** (Treasury auctions) — 1-2 sessioner, ny fetcher
8. **F7** (crypto_sentiment_extreme) — UTSATT til juli 2026

**Akkumulert estimat:** 6-9 sessioner totalt for F1-F6 + F8.

## Beslutninger som er låst (ikke diskuter på nytt)

Per § 22.1 (PLAN-tag fra 2026-05-02):
- Ingen familie-restruktur — flat YAML beholdes (event-familie i
  Spor B var unntak fra denne regelen).
- Backtest droppet — all validering mot live-demo.
- Ingen ADR (unntatt hvis F2/F5/F6 krever schema-ALTER med
  cross-cutting effekt — usannsynlig, men flagg i så fall).
- Separat commit per driver/endring, snapshot-baseline regen + diff-
  rapport per F-leveranse.

**Spor E er utsatt til ~2026-06-01.** Ikke åpne før observasjonsvinduet
har minst 2 uker av live-demo-data.

## Memory-feedback aktivt

Fra tidligere sessioner:
- `dont-ask-process-decisions`: Bestem commit-rekkefølge OG sub-spor-
  valg selv. Ikke spør operatør om disse.
- `free-api-no-parallel-requests`: Sekvensielle HTTP-kall mot gratis-API.
- `baseline-regen-needs-fresh-python`: Snapshot-regen må starte fra ny
  Python-prosess hvis driver-registry endres mid-session.
- `test-scope-proportional-to-change`: Scoped pytest for små endringer,
  full suite kun ved fase-LUKKING / delt-kode-sti.

## Arbeids-stil

- Forklar kort hva du gjør før hvert steg.
- Auto-mode er aktivt — utfør, men spør hvis arkitektonisk valg dukker
  opp som ikke er løst i § 22 eller LUKKET-blokken.
- Bruk TodoWrite for å spore framgang innen valgt sub-spor.
- Snapshot-baseline diff-rapport per leveranse.
- Stop-criterion: ≤5 grade-flips per asset-class. Eskaler hvis brutt.

## Når du er ferdig med Spor F

Stop og rapporter til meg:
- Hva ble levert (commits + tag-navn per sub-spor)
- Antall drivere/tabeller berørt
- Grade-flip-distribusjon per asset-class
- Eventuelle anomalier
- Klar-meld for Spor E (når 4 uker har gått siden Spor B-LUKKET 2026-05-02)

Ikke gå til Spor E før operatør godkjenner — uansett om vi har vært
gjennom hele Spor F. Vent på empirisk live-demo-data først.

## SLUTT
