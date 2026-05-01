# Driver-rebalansering — kombinert plan

**Status:** Utkast for ny session-kontekst. Ingen kode levert ennå.
**Dato:** 2026-05-02
**Sub-fase:** 12.10 (foreslått, åpnes etter sub-fase 12.9 D6 lukker)
**Inputs:**
- Bruker-utkast (2026-05-02) — familie-restrukturering + ~70 nye drivere + endringer på eksisterende
- `docs/driver_balance_report_2026-05-01.md` (rapport min)
- `docs/data_utilization_report_2026-05-01.md` (rapport min)

---

## 0. Utgangspunkt — hva er bekreftet før denne planen

- **Arkitektur:** ny driver = 1 funksjon med `@register("name")` + 1 YAML-linje. Ingen kjerne-kode-endringer.
- **YAML-modell:** Pydantic-validert, hver familie summerer til 1.0 i dag. Endring til 2-nivå-taksonomi (top-level + sub-family) krever schema-utvidelse.
- **Data-tilgang:** 16 eksterne kilder katalogisert. FRED, NASS, EIA, AGSI har keys (AGSI mangler — må registreres). Public/no-key: USGS, ICE-CSV, ForexFactory, AAII, NOAA, Treasury Direct, CBOE.
- **DB-rader:** 953k rader på 33 tabeller. 8 tabeller har lite/ingen driver-bruk (`crypto_sentiment`, `news_intel` har data; andre er meta-internal).
- **Sub-fase 12.9 Fase 3** etablerte at horisont-filter på driver-nivå fungerer (17 drivere migrert).

---

## 1. Familie-restrukturering (FORSLAG A — bruker)

**Beslutning:** GO på 2-nivå taksonomi. Erstatter dagens flate `families: {trend, positioning, macro, structure, risk, analog}`.

**Ny taksonomi:**

| Top-level | Sub-family | Eksisterende drivere som flytter inn | Nye drivere (ref §2) |
|---|---|---|---|
| `positioning` | `cot` | cot_z_score, positioning_mm_pct, cot_ice_mm_pct, cot_euronext_mm_pct, positioning_asset_mgr_pct, positioning_lev_funds_pct | cot_oi_change, cot_concentration_top4, cot_commercial_extreme, cot_swap_dealer_skew, cot_ice_{cocoa,coffee,sugar,wheat} |
| `positioning` | `sentiment` | aaii_extreme | crypto_sentiment_extreme, news_intel_severity_veto |
| `positioning` | `options` | — (nytt) | cboe_skew_z, cboe_pcr_total_extreme, cboe_pcr_equity_only, cboe_vix_term_curve |
| `macro` | `yields` | yield_diff_10y, real_yield | t10y3m, t_bill_3mo_yield, treasury_btc_10y, treasury_indirect_pct |
| `macro` | `credit` | credit_spread_change | hy_oas_change |
| `macro` | `liquidity` | net_fed_liq_change | anfci_z (erstatter nfci_change), m2_yoy |
| `macro` | `growth` | — | ism_pmi_level, industrial_production_yoy, cfnai_3mma, umich_sentiment_z, jolts_openings_yoy |
| `macro` | `labor` | — | initial_claims_z, continuing_claims_z |
| `macro` | `volatility` | vix_regime | vix9d_vix_ratio, move_index_z, vvix_z, gvz_z, ovx_z |
| `macro` | `fx` | dxy_chg5d, brl_chg5d | dollar_index_breadth |
| `energy` | `inventory` | eia_stock_change, agsi_storage_pct | eia_distillate_change, eia_propane_change, agsi_{germany,netherlands,italy}_pct, agsi_withdrawal_rate, agsi_injection_rate |
| `energy` | `supply` | — | eia_refinery_utilization_z, eia_natgas_processing, eia_imports_crude |
| `energy` | `demand` | — | eia_petroleum_supplied, eia_gasoline_demand |
| `agri` | `supply` | drought_monitor, weather_stress | usdm_state_{iowa,texas,california,kansas_ndakota}, nass_yield_{corn,soy}_yoy, nass_grain_stocks_quarterly |
| `agri` | `export` | fas_exports, conab_yoy, cecafe_export_change, unica_export_change, unica_crush_change | fas_exports_{china,eu} (split) |
| `agri` | `progress` | crop_progress_stage, seasonal_stage | — |
| `agri` | `disease` | disease_pressure, export_event_active | — |
| `climate` | `enso` | enso_regime → erstattes | noaa_oni_index, noaa_enso_forecast_3mo |
| `climate` | `regional` | hdd_cdd_anomaly | noaa_pdo_index |
| `exogenous` | `seismic` | mining_disruption | seismic_m6_global_24h, seismic_chile_peru_copper |
| `technical` | `trend` | sma200_align, momentum_z | (sma200_align utvides med slope) |
| `technical` | `range` | range_position | — |
| `technical` | `volatility` | vol_regime | intraday_atr_h1 |
| `event` | `distance` | event_distance, bdi_chg30d (flytt fra cross) | treasury_quarterly_refunding |
| `event` | `surprise` | — | nfp_surprise, cpi_surprise, gdp_surprise, pce_surprise, fomc_decision_distance |
| `analog` | (beholdes) | analog_hit_rate, analog_avg_return | — |

**Schema-konsekvens:** ny `FamilySpec.subfamilies: dict[str, SubFamilySpec]` med vekt-summering på begge nivåer. Engine endres for to-nivå-aggregat. Pydantic-migrasjon: tillate både flat (legacy) og 2-nivå i overgangsperioden.

**Konsekvens for vekting:** YAML får per-instrument-overrides på top-level (eks. `families.macro.weight: 0.30`) og sub-family (eks. `families.macro.subfamilies.credit.weight: 0.25`). Driver-vekter normaliseres innen sub-family.

**Estimat:** 2-3 dager (schema + engine + Pydantic-migrasjon + 22 YAML-er).

---

## 2. Nye drivere — kombinert liste prioritert

Sammenlignet med utkastet ditt + mine HØY/MED/LAV-anbefalinger:

### 2.1 KRITISK — uke 1 (eliminere bug + lavt-hengende frukt)

| # | Driver | Family | Hor. | Kilde | Estimat | Avhengighet |
|---|---|---|---|---|---|---|
| 1 | `cot_ice_cocoa` | positioning.cot | M, Sw | ICE Public CSV (allerede pulled) | 2t | Ingen |
| 2 | `cot_ice_coffee` | positioning.cot | M, Sw | Samme | 2t | Ingen |
| 3 | `cot_ice_sugar` | positioning.cot | M, Sw | Samme | 2t | Ingen |
| 4 | `cot_ice_wheat` | positioning.cot | M, Sw | Samme | 2t | Ingen |
| 5 | `nfp_surprise` | event.surprise | Sc | calendar_ff (allerede pulled) | 4t | Krever forecast/actual-felt verifisering |
| 6 | `cpi_surprise` | event.surprise | Sc | Samme | 2t | Etter #5 |
| 7 | `news_intel_severity_veto` | positioning.sentiment | Sc | news_intel-tabell | 4t | Veto-driver, ingen kalibrering |

**Total uke 1: ~18t fordelt på 5 dager.** Alle bruker eksisterende data, kun ny driver-logikk + YAML-wiring.

### 2.2 HØY — uke 2 (verdifulle, krever ny fetcher)

| # | Driver | Family | Hor. | Kilde | Estimat |
|---|---|---|---|---|---|
| 8 | `t10y3m` | macro.yields | M | FRED T10Y3M | 4t |
| 9 | `hy_oas_change` | macro.credit | M, Sw | FRED BAMLH0A0HYM2 | 4t |
| 10 | `initial_claims_z` | macro.labor | Sc, Sw | FRED ICSA | 4t |
| 11 | `continuing_claims_z` | macro.labor | Sw | FRED CCSA | 2t (etter #10) |
| 12 | `ism_pmi_level` | macro.growth | M | FRED NAPM | 4t |
| 13 | `industrial_production_yoy` | macro.growth | M | FRED INDPRO | 2t |
| 14 | `umich_sentiment_z` | macro.growth | Sw | FRED UMCSENT | 2t |
| 15 | `anfci_z` | macro.liquidity | Sw | FRED ANFCI (erstatter nfci_change) | 4t |
| 16 | `vix9d_vix_ratio` | macro.volatility | Sc | FRED VIX9DCLS / VIXCLS | 4t |

**Total uke 2: ~30t.** Alle FRED med eksisterende key. Reuser `fetch/fred.py`-loader, kun config-utvidelse + nye driver-funksjoner.

### 2.3 MEDIUM — uke 3-4 (krever ny fetcher infrastruktur)

| # | Driver | Family | Hor. | Kilde | Estimat |
|---|---|---|---|---|---|
| 17 | `cboe_skew_z` | positioning.options | Sw, Sc | CBOE CSV | 6t |
| 18 | `cboe_pcr_total_extreme` | positioning.options | Sc, Sw | CBOE | 3t |
| 19 | `cboe_pcr_equity_only` | positioning.options | Sc | CBOE | 2t |
| 20 | `move_index_z` | macro.volatility | Sw | Yahoo `^MOVE` | 4t |
| 21 | `vvix_z` | macro.volatility | Sc | Yahoo `^VVIX` | 2t |
| 22 | `gvz_z` | macro.volatility | Sw | Yahoo `^GVZ` | 2t |
| 23 | `ovx_z` | macro.volatility | Sw | Yahoo `^OVX` | 2t |
| 24 | `noaa_oni_index` | climate.enso | M | NOAA CPC ONI-CSV (erstatter enso_regime) | 6t |
| 25 | `noaa_enso_forecast_3mo` | climate.enso | M | NOAA CPC ENSO advisory | 4t |
| 26 | `usdm_state_iowa` | agri.supply | Sw, M | USDM CSV per-state | 4t |
| 27 | `usdm_state_texas` | agri.supply | Sw, M | Samme | 2t (etter #26) |
| 28 | `usdm_state_california` | agri.supply | M | Samme | 2t |
| 29 | `usdm_state_kansas_ndakota` | agri.supply | Sw | Samme | 2t |

**Total uke 3-4: ~41t.** Krever 4 nye fetcher-moduler (CBOE, Yahoo MOVE/VVIX, NOAA, USDM-per-state).

### 2.4 LAV — måned 2+ (større arbeid eller mindre verdi)

| # | Driver | Estimat | Notat |
|---|---|---|---|
| 30 | `eia_distillate_change` | 4t | Krever EIA-config-utvidelse |
| 31 | `eia_propane_change` | 2t | Etter #30 |
| 32 | `eia_refinery_utilization_z` | 4t | EIA |
| 33 | `eia_petroleum_supplied` | 4t | EIA demand-proxy |
| 34 | `eia_natgas_processing` | 4t | EIA |
| 35 | `eia_gasoline_demand` | 2t | EIA |
| 36 | `eia_imports_crude` | 2t | EIA |
| 37 | `nass_yield_corn_yoy` | 6t | NASS schema-utvidelse |
| 38 | `nass_yield_soy_yoy` | 2t | Etter #37 |
| 39 | `nass_grain_stocks_quarterly` | 6t | NASS |
| 40 | `cot_oi_change` | 4t | Eksisterende COT-tabell |
| 41 | `cot_concentration_top4` | 6t | CFTC Disaggregated long-form schema-utvidelse |
| 42 | `cot_commercial_extreme` | 4t | Eksisterende |
| 43 | `cot_swap_dealer_skew` | 4t | Disaggregated |
| 44 | `agsi_germany_pct` | 4t | **Krever AGSI-key først** |
| 45 | `agsi_netherlands_pct` | 2t | Etter #44 |
| 46 | `agsi_italy_pct` | 2t | |
| 47 | `agsi_withdrawal_rate` | 4t | |
| 48 | `agsi_injection_rate` | 2t | |
| 49 | `cboe_vix_term_curve` | 4t | Utvidelse av eksisterende |
| 50 | `dollar_index_breadth` | 6t | Multi-FRED-serie |
| 51 | `t_bill_3mo_yield` | 2t | FRED DTB3 |
| 52 | `cfnai_3mma` | 2t | FRED CFNAIMA3 |
| 53 | `jolts_openings_yoy` | 2t | FRED JTSJOL |
| 54 | `m2_yoy` | 2t | FRED M2SL |
| 55 | `treasury_btc_10y` | 6t | Treasury Direct API |
| 56 | `treasury_indirect_pct` | 2t | Etter #55 |
| 57 | `treasury_quarterly_refunding` | 4t | Calendar-style |
| 58 | `seismic_m6_global_24h` | 2t | Eksisterende seismic, ny terskel |
| 59 | `seismic_chile_peru_copper` | 2t | Spesialisering av mining_disruption |
| 60 | `gdp_surprise` | 2t | calendar_ff |
| 61 | `pce_surprise` | 2t | calendar_ff |
| 62 | `fomc_decision_distance` | 4t | calendar_ff under-signal |
| 63 | `intraday_atr_h1` | 4t | Yahoo 1h |
| 64 | `noaa_pdo_index` | 6t | NOAA PDO |
| 65 | `crypto_sentiment_extreme` | 2t | Vent til 100+ rader (~aug 2026) |
| 66 | `fas_exports_china` | 6t | FAS schema-utvidelse |
| 67 | `fas_exports_eu` | 2t | Etter #66 |

**Total LAV: ~120t = 3 uker.**

---

## 3. Endringer på eksisterende drivere

Sammenlignet med utkast (kategori "Kritiske/Høy/Medium/Lav"):

### 3.1 KRITISK — uke 1 (parallelt med 2.1)

| # | Endring | Drivere berørt | Estimat |
|---|---|---|---|
| K1 | `min_samples`-guard på drivere som leser <100-rad-tabeller | unica_export_change, disease_pressure, export_event_active, comex_stress | 6t |
| K2 | COT `released_at`-fix (3-dagers look-ahead) | cot_z_score, cot_euronext_mm_pct, cot_ice_mm_pct, positioning_*, aaii_extreme (7 drivere + schema-utvidelse) | 1d |
| K3 | Verifiser `event_distance` ikke leser future actual | event_distance | 2t |

### 3.2 HØY — uke 2

| # | Endring | Estimat |
|---|---|---|
| H1 | `enso_regime` → erstatt med `noaa_oni_index` (parallelt med #24) | 4t (samme commit) |
| H2 | `weather_stress`: lookback_months 1 → 6 | 1t |
| H3 | `nfci_change` → erstatt med `anfci_z` (#15) | 4t (samme commit) |
| H4 | `mining_disruption`: legg til M ≥ 5.5-terskel + region-mask | 4t |
| H5 | Konsolider multi-lookback-instances (~25 stk): per-driver én primær window eller eksplisitt ensemble med vekt-rasjonale | 1-2d |

### 3.3 MEDIUM — uke 3-4

| # | Endring | Estimat |
|---|---|---|
| M1 | `comex_stress`: disable til 6mnd historikk (`min_samples=180`) | 1t |
| M2 | `vix_regime`: eksponer som regime-classifier for vekting av andre drivere | 2-3d (krever aggregator-arkitektur-endring) |
| M3 | `momentum_z`: regime-conditional lookback (20d høy-vol, 100d lav-vol) | 2d |
| M4 | `sma200_align`: legg til slope-komponent | 2t |
| M5 | `range_position`: ATR-normalisert med 14-20d lookback | 4t |
| M6 | `bdi_chg30d`: utvid med 90d-trend + 12mo-MA-regime | 2t |
| M7 | `hdd_cdd_anomaly`: per-instrument-vekt heller enn global | 1d |

### 3.4 LAV — måned 2+

| # | Endring | Estimat |
|---|---|---|
| L1 | `aaii_extreme`: bytt til 8-uker-MA-divergens | 4t |
| L2 | `drought_monitor`: gjør CONUS-aggregat sekundær til state-level (etter #26-29) | 1t |
| L3 | `shipping_pressure` ↔ `shipping_indices` table-name verifisering | 1t |
| L4 | `fas_exports`: per-destinasjon-split (parallelt med #66-67) | inkludert i 2.4 |

### 3.5 STORARBEID — separat sub-fase

| # | Endring | Estimat | Notat |
|---|---|---|---|
| S1 | ALFRED-vintage-migrasjon for FRED-drivere (eliminere revisjons-leakage) | 1-2 uker | Krever ny `fundamentals_vintage`-tabell + scoring-flagg for live vs backtest |
| S2 | Regime-conditional weighting i scoring-aggregator (jf. M2 utvidet) | 1-2 uker | Erstatter statisk family_weights med `vix_regime`-styrt dynamisk vekting |

---

## 4. Avhengigheter + rekkefølge

```
Sub-fase 12.10 åpner ─┬─ Uke 1 (parallelt):
                      │   • 2.1 (#1-7): 7 kritiske drivere
                      │   • 3.1 (K1-K3): bug-fixer
                      │   • SCHEMA: 2-nivå-taksonomi (§ 1)
                      │
                      ├─ Uke 2:
                      │   • 2.2 (#8-16): 9 FRED-drivere
                      │   • 3.2 (H1-H5): høy-prio endringer
                      │
                      ├─ Uke 3-4:
                      │   • 2.3 (#17-29): 13 medium-prio drivere
                      │   • 3.3 (M1-M7): medium-prio endringer
                      │   • Skaff AGSI-key parallelt
                      │
                      ├─ Måned 2:
                      │   • 2.4 (#30-67): 38 lav-prio drivere
                      │   • 3.4 (L1-L4): lav-prio endringer
                      │
                      └─ Måned 3+ (ny sub-fase):
                          • S1 ALFRED-vintage
                          • S2 Regime-conditional weighting
```

**Snapshot-baseline-regen** etter hver hovedmilepæl (uke 1, 2, 4, måned 2). Grade-distribusjons-rapport per asset-class for å fange systematisk bias.

---

## 5. Estimat-totaler

| Bunke | Antall drivere | Endringer | Estimat | Forventet leveranse |
|---|---:|---:|---|---|
| Uke 1 (KRITISK) | 7 nye | 4 fixer | ~25t | Eliminere look-ahead + lavt-hengende frukt |
| Uke 2 (HØY) | 9 nye | 5 endringer | ~35t | FRED-utvidelse + regime-replacements |
| Uke 3-4 (MEDIUM) | 13 nye | 7 endringer | ~50t | CBOE/Yahoo-vol + state-level USDM + NOAA |
| Måned 2 (LAV) | 38 nye | 4 endringer | ~120t | EIA-utvidelse + COT-disaggregated + AGSI |
| Måned 3+ (S-arbeid) | — | 2 store | ~3-4 uker | ALFRED-vintage + regime-vekting |
| Familie-restrukt § 1 | — | schema | ~2-3d | Engine-endring + 22 YAML-er |
| **Total uke 1-4** | **29 drivere** | **16 endringer** | **~110t (~3 uker)** | Bedrock-2.0 candidate |
| **Total inkl. måned 2** | **67 drivere** | **20 endringer** | **~230t (~6 uker)** | Komplett |

---

## 6. Beslutningspunkter for ny session

Spørsmål som må avklares før koding starter:

1. **Familie-restrukturering først, eller iterativt?**
   - **A**: Schema-endring i uke 1, deretter wire alle nye drivere mot ny taksonomi → kontekstuell ren start
   - **B**: Behold flat taksonomi til måned 2 → minimerer rebase-risiko ved bug-fix

2. **AGSI-key**: skaff registrering før uke 3 (gratis, ~1d) — ellers utelat AGSI-utvidelser fra uke 3-4-bunken

3. **ALFRED-vintage (S1)**: kritisk for backtest-troverdighet, men ~1-2 uker isolert. Egen sub-fase 12.11?

4. **Regime-conditional weighting (S2)**: arkitektonisk skifte. Vurder å låse i ADR før implementasjon.

5. **Snapshot-baseline-rytme**: regen etter hver uke, eller etter hver bunke (1/2/4/måned)?

6. **Prioritering i rekkefølge eller etter type?**
   - Foreslått: kritiske bug-fixer FØR nye drivere, deretter prioritert etter forventet IC-impact (FRED HØY først, EIA-detaljer LAV sist).

7. **Live vs paper?** Skal driver-tilskudd kjøre live-mat på demo-konto kontinuerlig under utviklingen, eller frosset til måned 2 er ferdig?

---

## 7. Status-felt for ny session

Når sub-fase 12.10 åpnes, kopier denne planen og merk status:

```
| # | Driver | Status | Commit | Notat |
|---|---|---|---|---|
| 1 | cot_ice_cocoa | PENDING | – | – |
| 2 | cot_ice_coffee | PENDING | – | – |
...
```

Stop-criterion sub-fase 12.10:
- Uke 1 + uke 2 + uke 3-4 alle lukket = **Bedrock-2.0 candidate**
- Snapshot-baseline regen + grade-distribusjons-rapport viser ingen systematisk bias
- 22 instrument-YAMLer migrert til 2-nivå-taksonomi
- Pyright 0 errors, ny-tester grønne

---

## 8. Hva denne planen IKKE dekker

Med vilje utelatt:
- **Trade-execution-side** (bot.yaml-lot-sizing, exit-policies) — egen sub-fase
- **UI-arbeidet** for å eksponere 67 nye drivere i Datakilder-fane — håndteres incremental etter hvert som drivere lander
- **Data-retention/historic-backup-policy** — kjøres parallelt
- **Live-konto-cutover** — etter D6 + minst én måned demo-validering

---

_Sist oppdatert: 2026-05-02. Klar for ny session-kontekst._
