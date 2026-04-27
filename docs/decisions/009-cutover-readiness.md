# ADR-009: Cutover-readiness — sub-fase 12.5+ → 12.6 → Fase 13

Dato: 2026-04-27
Status: accepted
Fase: 12.5+ (sessions 105-117) avsluttende vurdering
Refererer til: ADR-007 (fetch-port-strategi), ADR-008 (per-fetcher mapping),
PLAN § 12, § 13

## Sammendrag

Sub-fase 12.5+ har levert all teknisk infrastruktur for fetcher-port:
**11/11 fetchere portet** (sessions 105-115), **AsOfDateStore utvidet
med Phase A-C-proxy-getters** (session 116), **Phase D backtest-
infrastruktur på plass** (session 116). Sub-fase er teknisk komplett.

Cutover til Fase 13 er likevel **BLOKKERT på empirisk rebalansering av
scoring-systemet** — en ny sub-fase 12.6 mellom 12.5+ og Fase 13 som
bruker den nybygde harvester+analyzer-infrastrukturen til å re-vekte
drivere basert på forward-looking IC-data, ikke skjønn.

## Status per Phase A-C-fetcher

| Sess | Fetcher | DB-rader | Fetch-status | Driver-status | Empirisk validering |
|---|---|---:|---|---|---|
| 105 | calendar_ff | 37 | systemd 06:15+18:15 OK | event_distance wired alle 22 | < 1 dag data — utilstrekkelig |
| 106 | cot_ice | 136 | systemd Fre 22:30 OK | cot_ice_mm_pct wired Brent + NaturalGas | 68 uker — OK for backtest |
| 107 | eia_inventories | 5018 | user-systemd Ons 17:30 OK | eia_stock_change wired CrudeOil/Brent/NG | 1991-2026 — full historikk |
| 108 | comex | 3 | user-systemd Mon-Fri 22:00 OK | comex_stress wired Gold/Silver/Copper | 1 dag data — bygger over tid |
| 109 | seismic | 101 | user-systemd 04:00 OK | mining_disruption wired 4 metals | 7 dagers rolling — short-window OK |
| 110 | cot_euronext | 174 (DB viser 15) | user-systemd Ons 18:00 OK | cot_euronext_mm_pct wired Wheat+Corn | 58 uker — OK |
| 111 | conab | 7 | user-systemd 15. mnd OK | conab_yoy wired Corn/Soybean/Coffee | månedlig — bygger over tid |
| 112 | unica | 1 | user-systemd 1.+16. mnd OK | unica_change wired Sugar | halvmånedlig — bygger over tid |
| 113 | shipping | 2034 | user-systemd Mon-Fri 23:30 OK | shipping_pressure rebrand av bdi_chg30d | 2018-2026 BDI — full |
| 114 | news_intel | 0 | fetch.yaml ikke installert | (ingen — UI-only) | — |
| 115 | crypto_sentiment | 0 | fetch.yaml ikke installert | (ingen — UI-only) | — |

**Konklusjon Phase A-C:** alle 11 fetchere portet og fungerer. 5 har
rik historisk data (eia, shipping, cot_ice, cot_euronext, seismic);
3 har én dag eller mindre (comex, unica, conab); 2 er UI-only ennå
ikke aktivert. Empirisk validering varierer: drivere på rik data
(eia, cot_ice) kan validers nå; drivere på spinkel data (comex,
unica, conab) trenger 1-3 mnd akkumulering.

## Status Phase D backtest-infrastruktur (session 116)

**Levert:**
- AsOfDateStore utvidet med 9 nye proxy-getters — fjernet kritisk
  blokker der orchestrator-replay falt stille tilbake til 0.0 for
  Phase A-C-drivere
- `scripts/backtest_phase_d_session116.py` — 3-modus backtest-driver
  (baseline / orchestrator / spike)
- `docs/backtest_phase_d_2026-04.md` — baseline reproducerer session
  99 eksakt; orchestrator-replay 12 inst × 2 hor × 2 dir × 12mnd; 3
  driver-spikes (cot_ice_mm_pct, conab_yoy, unica_change)
- `scripts/harvest_driver_observations.py` + `scripts/harvest_feature_snapshots.py`
  + `scripts/run_full_history_harvest.sh` — full historisk harvest-
  fundament for sub-fase 12.6

**Empiriske funn fra Phase D:**
- Sugar BUY 0% hit-rate ved 81.8/87.5% pub-rate (30d/90d) — direction-
  bias-justering utover session 102 trenger vurdering
- cot_ice_mm_pct bidrar +0.094-0.692 score for Brent
- conab_yoy bidrar +0.6-2.0 score for Corn/Soybean/Coffee SELL
- unica_change er kritisk for Sugar SELL pub-rate (-75pp når zeroed)

## Beslutninger låst i denne ADR

### 1. Sub-fase 12.5+ er teknisk LUKKET

**Beslutning:** Tag `v0.12.5-fetch-port-complete` settes på siste
session 117-commit. Markerer at fetcher-port-strategien fra ADR-007
+ mapping fra ADR-008 er gjennomført fullstendig.

**Implikasjon:** ingen flere fetcher-porter skal regnes som del av
sub-fase 12.5+. Eventuelle nye fetcher-behov håndteres som egne sub-
faser.

### 2. Sub-fase 12.6 etableres mellom 12.5+ og Fase 13

**Beslutning:** Ny sub-fase 12.6 "data-driven rebalansering" inntreffer
før Fase 13 cutover. Scope:

- Detached harvest av all historisk data (drivere × instrumenter ×
  features) over ≥10 års kalenderhistorikk via
  `run_full_history_harvest.sh` + `harvest_feature_snapshots.py`
- Forward-looking IC-analyse via `analyze_driver_performance.py` +
  `analyze_cross_correlations.py`
- Sesong-/syklusaware analyse — IC per kalenderkvartal + per cycle-
  fase per asset-klasse
- Setup-walker (Phase 12.6.b): dag-for-dag forward simulation av
  hver setup → ekte P&L-distribusjon
- YAML-vekt-rebalansering basert på empiri, IKKE skjønn
- Re-harvest delsett etter rebalansering for å bekrefte forbedring
- Iterer til konvergens

**Rasjonale:** dagens YAML-vekter er skjønnsbasert (drivere ble lagt
til i takt med utviklingen, vekter tilpasset per instrument av
vurdering). Phase D session 116 viste at orchestrator gir rimelige
men ikke målbart-rebalanserte resultater. Cutover til Fase 13 uten
empirisk rebalansering ville være å låse inn skjønnsbaserte vekter
permanent — i strid med ADR-001 design-prinsipp om data-drevne valg.

### 3. News_intel + crypto_sentiment driver-aktivering UTSETTES

**Beslutning:** ingen aktivering nå. Re-vurder etter sub-fase 12.6
når harvest-data + IC-analyse foreligger.

**Rasjonale:**
- ADR-007 § 5 krever empirisk validering før driver-aktivering, maks
  0.1 vekt i første runde
- DB er tom (sessions 114+115 systemd-timers ikke installert ennå —
  fetch.yaml-konfigurasjon er på plass men ikke aktivert)
- Selv om vi installerte timers nå ville vi ha < 1 mnds data ved
  beslutningstidspunkt — utilstrekkelig

**Implikasjon:** ingen nye driver-registreringer i denne ADR. Driver-
count forblir 30.

### 4. Branch-modus forblir Nivå 1 (commits direkte til main)

**Beslutning:** ingen overgang til Nivå 3 (feature-branches + PR) i
sub-fase 12.6. Re-vurderes ved Fase 13-nærhet (når sub-fase 12.6
viser konvergens).

**Rasjonale:**
- Auto-push-hook + Nivå 1 har fungert godt for sessions 70-117 (~50
  sessions med data-drift, instrument-utvidelser, fetcher-porter).
  Workflow-velocity er høy, ingen merge-konflikter.
- Sub-fase 12.6 er fortsatt utforskende — flere små eksperiment-
  commits med rebalansering forventes. PR-overhead per eksperiment
  ville bremse ned uten å fange feil.
- Når Fase 13 cutover-vinduet åpner (live-data sammenlignet mot bot),
  endres karakter: feilrater og review-behov stiger. PR-flow-fordelene
  blir reelle der.

### 5. Cutover-tidspunkt for Fase 13 — IKKE BESLUTTET

**Beslutning:** ingen kalender-dato. Cutover-kriterier skjerpes fra
PLAN § 12.3:

- Sub-fase 12.6 må vise konvergens — ≥2 iterasjoner med rebalansert
  YAML der re-harvest viser scoring-forbedring (high-IC-drivere
  vekt-økt, lav-IC-drivere vekt-redusert)
- Setup-walker må kjøres på rebalansert system → P&L-distribusjon
  må vise positiv risk-justert avkastning på minst 4 av 6 (asset-
  klasse, retning)-kombinasjoner
- Bot-whitelist må re-evalueres mot setup-walker-resultater (i dag
  17 instrumenter — listen kan endre seg etter sub-fase 12.6-funn)

## Konsekvenser

### For PLAN.md

§ 12.5 / § 12.5+ markeres ferdig. Ny § 12.6 "data-driven rebalansering"
introduseres med scope ovenfor. § 13 cutover-kriterier oppdateres.

### For sessions 118+

Sub-fase 12.6 består sannsynligvis av disse session-typene:
- **A:** Vente på + monitorere harvest-progress (kort)
- **B:** Analyzer-utvidelser (sesong-bucketing, lead-lag-IC, setup-walker)
- **C:** YAML-vekt-rebalansering basert på empiri
- **D:** Re-harvest delsett + verifisere forbedring
- **E:** Iterer C-D til konvergens

### For risikoflater

- **Fetcher-data-vekst:** comex/unica/conab/news_intel/crypto_sentiment
  trenger systemd-timers installert + 1-3 mnd akkumulering. Sessions
  118+ håndterer.
- **Harvest-restartability:** PRIMARY KEY på alle nye tabeller —
  resumable. Strømbrudd / kill / OOM gir ikke data-tap.
- **Backtest-validity:** look-ahead-strict via AsOfDateStore er
  bekreftet i Phase D session 116. Forward-return-clipping holder
  K-NN leak-free.

## Referanser

- ADR-001: one-engine-two-aggregators (data-drevne vekter)
- ADR-005: analog-data-schema (forward_return-konvensjon)
- ADR-006: direction-asymmetric-scoring (polarity-felt)
- ADR-007: fetch-port-strategi
- ADR-008: per-fetcher mapping for sub-fase 12.5+
- `docs/backtest_phase_d_2026-04.md` (Phase D-rapport)
- `scripts/harvest_driver_observations.py` (sub-fase 12.6-fundament)
- `scripts/analyze_cross_correlations.py` (forward-looking IC-matrise)
