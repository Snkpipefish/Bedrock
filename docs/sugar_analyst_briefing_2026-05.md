# BEDROCK — Analytiker-rapport: SUKKER

**Dato:** 2026-05-05
**Instrument:** Sugar (ICE No.11 via Skilling CFD)
**Aggregering:** `additive_sum` (agri)
**Status etter sub-fase 12.11+:** datafundament komplett (42 UNICA + 184 mnd centro-sul weather)

---

## 1. Scoring-modell (agri)

```
Totalscore = Σ familie_score[f] × familie_tak[f]
```

- Absolutt poengmodell (ikke prosent av maks)
- Karakter: A+ ≥ 11, A ≥ 8, B ≥ 6 (max_score = 16)
- Horisont (SWING/MAKRO) tildeles i setup-generator basert på score-styrke
- **SCALP er ikke aktiv for agri** — fundamenta-data har ikke datafrekvens for scalping
- ADR-006 retning: `directional` familier flippes til `1 - score` for SELL
- Asymmetrisk publish-floor (per session 102): **buy=7, sell=5** — sukker har strukturell SELL-bias (Brasil oversupply + HFCS-substitusjon, BUY-hr 34.9% vs SELL-hr 45% i 90d-backtest fra session 99)

---

## 2. Familier brukt for Sukker

| Familie | Tak | Hva den måler | Drivere |
|---------|----:|---------------|---------|
| **outlook** | 5 | Brasil sesongkalender (zafra apr-nov, entressafra des-mar) | `seasonal_stage` (custom monthly_scores) |
| **yield** | 3 | Brasil Centro-Sul vær + global supply/use | `weather_stress` (0.5), `wasde_s2u_change` (0.5) |
| **positioning** | 2 | CFTC No.11 MM netto% + OI-flow + swap-skew | `positioning_mm_pct` (0.40), `cot_oi_change` (0.35), `cot_swap_dealer_skew` (0.25) |
| **enso** | 2 | NOAA ONI + 3-mnd forecast | `noaa_oni_index` (0.6), `noaa_enso_forecast_3mo` (0.4) |
| **unica** | 2 | Brasil Centro-Sul mølling + sukker-mix | `unica_change` sugar_production_yoy (0.6), `unica_change` mix_sugar_pct (0.4) |
| **cross** | 2 | BRL/oljepris/event-distance/ICE white sugar | `brl_chg5d` (0.50), `momentum_z` (CrudeOil, 0.20), `cot_ice_mm_pct` (0.20), `event_distance` (0.10) |
| **analog** | 2 | K-NN historiske sukker-mønstre (softs) | `analog_hit_rate` (0.5), `analog_avg_return` (0.5) |
| **Total** | **16** | | |

---

## 3. Datakilder for Sukker — historikk-revisjon

### Hva vi har dyp historie på

| Datasett | Rader | Fra | Til | Notat |
|----------|------:|-----|-----|-------|
| **NOAA ONI** (ENSO) | 915 mnd | 1950-01 | 2026-03 | **76 års historikk** — meget solid for regime-modellering |
| **Sukker-pris** (Yahoo SB=F daglig) | 4 109 | 2010-01 | 2026-05 | 16 år OHLCV |
| **CFTC COT Sugar No.11** | 852 ukerap | 2010-01 | 2026-04 | 16 år, MM/Swap/Comm-splitt |
| **ICE White Sugar COT** | 605 ukerap | 2014-09 | 2026-04 | 11.5 år |
| **WASDE sugar** | 1 296 | 2019-05 | 2026-04 | 7 år US/global S/U |
| **Weather monthly Brazil Centro-Sul** | 184 mnd | 2011-01 | 2026-04 | Ribeirão Preto SP-koordinater |
| **UNICA Centro-Sul** | **42 rapporter** | **2012-05** | **2026-04** | **Backfilled via Wayback Machine + Brave** |
| **IRI ENSO Forecast** | 7 mnd | 2025-11 | 2026-04 | Manuell CSV (forward-overlay) |

### Datakilder vi *kan* legge til (gratis/åpne)

- **MAPA / CONAB** — Brasil offisielle sukker-/etanol-balansetall (ikke wired ennå)
- **Indian Sugar Mills Association (ISMA)** — India produksjon + eksportkvote
- **Thai Sugar Millers Corp / OCSB** — Thailand produksjon
- **CEPEA/ESALQ** — Brasil sukker-pris referanse (kassemarked)
- **Brasil ANP** — Etanol-pris (driver etanol vs sukker miks-beslutning)

---

## 4. Markeds-horisont og syklus (research)

### Forward curve (ICE no.11 via Skilling)
- **3 år** fremover listet (per i dag: SBN2026 → SBH2029)
- 5 leveringsmåneder/år: mar, mai, jul, okt, jan
- Front 2-3 måneder dominerer likviditet, men dyp orderbook ~12 mnd ut

### Når markedet faktisk priser inn neste høst
- Brasil zafra: **apr–nov** (høst), **des–mar** (entressafra)
- Pris-discovery for "neste safra" begynner typisk **6-12 mnd før zafra-start**
  - Eks: mai-2026-kontrakten priser inn 2026/27-safra fra ca. mai-2025
- **Oct–March-spreaden** er hovedspreaden — refererer Q3→Q1 supply-dynamikk
- Stock-syklus: peak okt (etter zafra-toppen), tightest mar (entressafra slutter)

### Implikasjon for Bedrock
Vår nåværende MAKRO-horisont (180d) er sannsynligvis for kort. Sukker-traders posisjonerer seg 9–12 mnd i forveien. Backtesten validerer dette: A+ BUY på 90d fungerte (44.6% / +4.69%), men 180d hadde for lite signal. **Nå tester vi h=90/180/270/365** for å finne riktig horisont.

---

## 5. Analyse-spørsmål til analytikeren

### A) Familievekter
- Foreslått total = 16 (uendret). Er fordelingen riktig?
  - outlook=5, yield=3, positioning=2, enso=2, unica=2, cross=2, analog=2

### B) Asymmetrisk publish-floor
- Sukker har strukturell SELL-bias historisk. Floor er buy=7, sell=5.
- **Spørsmål:** Med 12 års UNICA-data nå tilgjengelig, bør floor re-kalibreres?

### C) Sesong-scores i `seasonal_stage`
Nåværende mapping (J–F–M–A–M–J–J–A–S–O–N–D):
```
[0.7, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 0.9, 0.7, 0.6, 0.6]
```
- Mai–aug er peak bull (zafra-start, lager bygges men prisreaksjon)
- Okt–nov bear (zafra-topp, supply-pressure)
- Des–jan bear (lager høyt, men entressafra starter)

**Spørsmål:** Bør vi heller score basert på *forward-syklus* (hvor er vi i prising for neste safra) framfor *current-syklus*?

### D) Region-vekting i `weather_stress`
- I dag: kun Brazil Centro-Sul (185 av 24 mill tonn global produksjon)
- Mangler: India Maharashtra/UP (35 mill t), Thailand (12 mill t), EU-bietsukker

**Spørsmål:** Bør vi bygge multi-region weather med Centro-Sul=0.6, India=0.25, Thailand=0.15?

### E) Etanol-paritet
- Nåværende cross-familie har `momentum_z` på CrudeOil (proxy for etanol-attraktivitet)
- Brasil ANP publiserer faktisk etanol-pris (gratis, daglig)

**Spørsmål:** Bør vi bygge dedikert `ethanol_parity_brl`-driver som beregner sukker-ekvivalent for å fange Brasil mølle-allokering direkte?

### F) Manglende data-overlay
- ISMA månedlig India-balanse (gratis fra isma.org)
- OCSB Thailand
- USDM-tilsvarende for India/Thailand tørke

**Spørsmål:** Hvilke har høyest ROI for sukker-scoring?

---

## 6. Backtest-funn (fra første kjøring, 14 år historikk)

### SWING (h=90d) — virker delvis

**BUY:**
| Grade | n | Hit-rate | Avg return |
|-------|---|----------|-----------|
| A+ | 92 | **44.6%** | **+4.69%** |
| A | 394 | 35.0% | -0.83% |
| B | 3 | 0.0% | -5.09% |

→ A+ BUY har solid edge

**SELL:**
| Grade | n | Hit-rate | Avg return |
|-------|---|----------|-----------|
| A | 175 | 32.0% | **-3.51%** |
| B | 285 | 39.6% | +2.06% |
| C | 29 | 34.5% | +4.00% |

→ Inkonsistent grade-progresjon — A SELL underperformer B SELL på hit-rate

### Pågående
- Re-kjøring med h=90, 180, 270, 365 for å finne riktig MAKRO-horisont
- 180d ga ingen outcomes i første kjøring (manglet backfill — nå fikset)

---

## 7. Konkrete neste steg (mine forslag, åpen for endring)

1. **Bekrefte horisont** etter pågående 4-horisonts-backtest
2. **Re-kalibrere publish-floor** med ny UNICA-historikk
3. **Vurdere seasonal_stage redesign** (forward-syklus)
4. **Multi-region weather** for global sukker-supply
5. **Etanol-paritet-driver** som direkte input til mølle-allokering

---

## 8. Vedlegg — komplett driver-inventar tilgjengelig (96 drivere)

For full liste se rapport `docs/bedrock_drivers_overview_2026-05.md` (eller spør meg om en spesifikk familie).

Hovedkategorier:
- **Trend**: sma200_align, momentum_z (kun finansielle for sukker)
- **Positioning**: positioning_mm_pct, cot_z_score, cot_ice_mm_pct, cot_oi_change, cot_swap_dealer_skew, cot_concentration_top4
- **Macro**: real_yield, dxy_chg5d, brl_chg5d, vix_regime, credit_spread_change, etc.
- **Agri-spesifikke**: seasonal_stage, weather_stress, crop_progress_stage, wasde_s2u_change, conab_yoy, unica_change, fas_exports, drought_monitor, cecafe_export_change, noaa_oni_index, noaa_enso_forecast_3mo
- **Risk/Structure**: vol_regime, range_position, event_distance
- **Analog**: analog_hit_rate, analog_avg_return (K-NN historiske softs-mønstre)

---

*Generert 2026-05-05. Spør for utdypning eller endringer i prioritering.*
