# Sub-fase 12.6 analyzer-runde og YAML-rebalansering

**Status:** plan-doc skrevet i session 136 (2026-04-30) mens detached
harvest kjører. Analyzer-execution + faktisk YAML-rebalansering kommer
i session 137+ når harvest er ferdig (~12-13t ETA fra session 136-start).

**Forutsetning:** sub-fase 12.7 LUKKET 2026-04-30 (tag
`v0.12.7-fase-12.7-LUKKET`). Alt γ-låsen (PLAN § 19.7) oppfylt — én
rebalansering over hele driver-settet (44 drivere) heller enn flere
delvise passes.

## Bakgrunn

PLAN § 12.6 låser at YAML-vekt-rebalansering skal være data-driven, ikke
skjønn. Driver-observasjoner høstes via
`scripts/harvest_driver_observations.py` (long-format SQLite-tabell
`driver_observations`); analyzere beregner IC og cross-correlations.
Drivere med svak prediksjons-evne kandiderer for vekt-reduksjon, sterke
for økning, redundante (cross-corr > 0.7) for konsolidering.

## Steg 1 — IC-måling per driver

**Script:** `scripts/analyze_driver_performance.py` (ferdig session 117).

Per (instrument × horizon × direction) × driver:

- **n:** antall observasjoner (filtrer ut < 50)
- **IC:** Spearman-korrelasjon mellom `driver_value` og
  `forward_return_pct`. Direction-aware: positiv IC for BUY,
  negativ for SELL ⇒ driver predikerer riktig retning.
- **hit_rate_high:** andel hits når driver_value er i top-25%-kvartil
- **hit_rate_low:** hits i bunn-25%-kvartil
- **monotonisitet:** stigende hit-rate kvartil 1 → 4 (verifiserer at
  driver-signal er monotont, ikke U-formet)

Hit-definisjon matcher session 99-baseline (PLAN § 11.5): BUY hit =
forward_return_pct ≥ +3% (30d) / +5% (90d); SELL = motsatt.

**Output:** `docs/driver_performance_2026-MM-DD.md` med:
1. Top-IC drivere på tvers av (inst, hor, dir)
2. Per-driver detaljert tabell
3. Worst performers (kandidater for vekt-reduksjon)

**Kjør:**

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_driver_performance.py
```

## Steg 2 — Cross-correlation per familie

**Script:** `scripts/analyze_cross_correlations.py` (ferdig session 117).

Bygger IC-matrise over alle (prediktor × target)-kombinasjoner:

- **Prediktorer:** features i `feature_snapshots` (close-priser, FRED,
  shipping, COT MM-net%) + drivere fra `driver_observations`
- **Targets:** forward_return_pct per (target_instrument, horizon,
  direction)

For hver prediktor med ≥50 obs og hver target: pair-vis Spearman-IC,
direction-aware. **Forward-looking** — ref_date er as_of_date,
forward_return målt strikt ETTER ref_date.

**Output:** `docs/cross_correlations_2026-MM-DD.md` med:
1. Top-50 sterkeste cross-asset signaler
2. Per-target-tabell: top-5 prediktorer per (instrument, horizon)
3. Per-prediktor-tabell: hvilke targets én feature predikerer best

**Kjør:**

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_cross_correlations.py
```

## Steg 3 — Rebalanserings-thresholds

PLAN § 12.6 låser disse tersklene:

| Klasse | Median \|IC\| | Monotonisitet | Aksjon |
|---|---|---|---|
| **Underperformer** | < 0.05 | < 0.4 | Vurder drop fra YAML eller vekt → 0.05-floor |
| **Outperformer** | > 0.10 | > 0.7 | Vekt-økning innen familie-cap |
| **Redundant** | (n/a) | (n/a) | Hvis pair har \|cross-corr\| > 0.7: behold høyere-IC, drop lavere |

**Sample-krav:** ≥50 obs per (driver, instrument, horizon, direction)
før rebalansering kan utføres. Drivere med <50 obs flagges men
endres ikke (ny driver, kort historikk — vent på mer data).

**Sanity-checks:**
- Ingen vekt går til 0 uten review hvis driver dekker spesiell
  regime-rolle (f.eks. `enso_regime` for agri, `vix_regime` for indices)
- Familie-sum = 1.0 må holde etter hver endring (Pydantic-validering)
- Asset-klasse-spesifikk atferd respekteres (PLAN § 19.3 låste
  beslutninger — ingen FX/crypto-spesifikke regler endres uten
  samtale)

## Steg 4 — YAML-rebalansering

Per instrument (22 stk):

1. Les eksisterende YAML i `config/instruments/<inst>.yaml`
2. For hver familie:
   - Sammenlign drivere mot Steg 1-tabell
   - Identifiser underperformere (kandidater for redusert vekt)
   - Identifiser outperformere (kandidater for økt vekt)
   - Sjekk Steg 2 cross-corr — hvis pair > 0.7, behold høyere-IC
3. Rebalanser vekter slik at familie-sum = 1.0 holder
4. Re-validér via Pydantic-load — feil = hard fail (PLAN § 6.1)
5. Regenerer snapshot-baseline som ny anker (egen commit)
6. Grade-distribusjons-rapport sammenlignes mot pre-rebalanserings-
   state (PLAN § 11.7 smoke-tester)

**Iterer:** etter rebalansering, re-harvest delsett og bekreft positiv
∆IC på ≥1 high-confidence-driver (PLAN § 12.6 test-krav).

## Kritiske eksisterende drivere som har ny familie-vekt-status

Per PLAN § 19.8 (Patch 2) er eksisterende drivere allerede redusert i
12.7 D-fasene for å gjøre plass til nye drivere. Disse vekt-endringene
ER låste — 12.6-rebalansering kan ikke ROULLE TILBAKE 12.7-endringer
uten ny diskusjon med bruker. Eksempler:

- `real_yield` 0.40→0.25 i EURUSD macro (yield_diff la til, B1)
- `dxy_chg5d` 0.50→0.30 i EURUSD macro
- `weather_stress` 1.00→0.55 i Corn/Soybean/Wheat/Cotton weather
  (drought_monitor la til, A9)
- `seasonal_stage` 1.00→0.75 i Coffee/Cocoa/Sugar outlook (ICE
  certified stocks DROPPED, men cecafe_export_change A10 la til
  for Coffee)

12.6-runden måler IC for **det rebalanserte settet** (44 drivere) og
fin-justerer derfra.

## Per-driver fokus-områder for analyzer-runden

Spesielt interesse-områder gitt 14 nye 12.7-drivere som mangler
historisk IC-måling:

| 12.7-driver | Familie | Forventning |
|---|---|---|
| `aaii_extreme` | sentiment (SP500/Nasdaq risk) | Sentiment-extremes ofte mean-revert; svak forward-IC, men lange tail-events skal trigge |
| `vix_term_ratio` | risk (Nasdaq/SP500) | Forventes høy IC på SCALP, lavere på MAKRO |
| `hdd_cdd_anomaly` | weather (NaturalGas) | Sesongforskjell — IC bør splittes per kvartal |
| `cecafe_export_change` | conab (Coffee) | Brazil-cycle, forventes høy IC på SWING+MAKRO |
| `drought_monitor` | weather (Corn/Soybean/Wheat/Cotton) | Forventes høyeste IC blant weather-drivere på MAKRO |
| `agsi_storage_pct` | macro (NaturalGas) | EU-storage-cycle, forventes signifikant negativ-IC for sell-direction |
| `etf_holdings_change` | flows (Gold/Silver) | Confirms flow-driver-hypotese fra session 132 |
| `currency_cross_trend` | macro (Coffee/Sugar/Cocoa) | BRL-rolle på commodities — forventes positiv IC for sell-direction |
| `mining_disruption` | supply (Gold/Silver/Copper/Platinum) | Sjeldent event, lav n men høy IC når aktiv |
| `disease_pressure` | yield (agri) | Sjeldent men kritisk — IC kun rapporterbar med ≥50 obs |
| `net_fed_liq_change` | macro (Gold/SP500/Nasdaq/BTC) | Fed-balance-sheet → risk-asset-flow |
| `yield_diff_10y` | macro (FX) | Carry-trade-forventning, høy IC på SWING+ |
| `nfci_change` | risk (SP500/Nasdaq) | Credit-stress-leading-indicator, forventes høy IC før draws |
| `credit_spread_change` | risk (SP500/Nasdaq/Brent) | Recession-leading-indicator, forventes høy IC på MAKRO |

## Risiko-register

1. **For lite data per (driver, instrument, horizon)-kombo:** ny
   driver fra 12.7 kan ha < 50 obs hvis underliggende data har kort
   historikk (f.eks. AAII fra 1987, nfci fra 1971 — burde være OK,
   men noe-instrument-mangel kan kollapse n).
2. **Sample-bias:** harvest bruker `step_days=14` som default — det
   er 1 sample per 2 uker. Sample-rate er konstant per (instrument,
   horizon), så ingen bias innen, men inter-instrument sammenligning
   krever same step_days.
3. **Look-ahead bias:** `forward_return_pct` hentes fra
   analog_outcomes (eller syntetiseres fra prices). Ref_date er
   as_of_date for `generate_signals` — driver-call ser ikke fremover.
   Skal være clean, men spot-check ved analyzer-execution.
4. **Cross-corr false-positive:** to drivere kan korrelere via felles
   third-cause (f.eks. begge styres av VIX). Cross-corr > 0.7-regel
   er konservativ men ikke perfekt.

## Relasjon til andre PLAN-låser

- **PLAN § 19.3 trading-logikk-låser:** ufravikelige. Rebalansering
  kan ikke flytte cap_grade, gates, eller asymmetri-krav.
- **ADR-007 sentiment-cap:** crypto_sentiment + news_intel begrenset
  til 0.1 vekt i første runde uavhengig av IC.
- **ADR-009 cutover-readiness:** rebalansering må holde sub-fase
  12.6 test-krav (PLAN § 12.6 § 6: empiri-baseline ± 1pp,
  positiv ∆IC på ≥1 driver).
- **Plan-S og scalp-arkitektur:** kommer ETTER 12.6 (PLAN § 19.10).
  Rebalansering bruker kun MAKRO/SWING/SCALP-horisontene per
  PLAN § 5.5.

## Output-artefakter for session 137+

Når analyzer kjøres:

- `docs/driver_performance_<dato>.md` — IC-tabell per driver
- `docs/cross_correlations_<dato>.md` — top-50 cross-asset-signaler
- `docs/12_6_rebalansering_<dato>.md` — rebalanserings-beslutninger,
  per-instrument before/after-vekter, sanity-check-rapport
- `docs/12_6_grade_distribution_<dato>.md` — pre/post grade-dist
  per instrument (matcher session 135 D3-rapport-format)
- Per-instrument YAML-endringer (egen commit per instrument)
- Snapshot-baseline regenerert (`tests/snapshot/baseline_*.json`)

## Estimert tidsbruk session 137+

| Aktivitet | Estimat |
|---|---|
| `analyze_driver_performance.py`-execution | ~5-10 min |
| `analyze_cross_correlations.py`-execution | ~10-20 min |
| Manuell IC-tabell-review + rebalanserings-design | ~1 session |
| YAML-rebalansering (22 instrumenter, batched) | ~2-3 sessions |
| Re-harvest delsett + bekreftelse positiv ∆IC | ~1 session |
| **Totalt** | **~4-5 sessions** |
