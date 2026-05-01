# Data-utnyttelse-rapport — 2026-05-01

**Generert:** 2026-05-01T22:25:19.998329+00:00
**SQLite-DB:** `data/bedrock.db` (1,131,477 rader på tvers av 33 tabeller)

Komplementær til `driver_balance_report` — fokuserer på data-
siden: hva henter vi inn, hva bruker vi, hvilke kilder kan vi
utvide til.

---

## 1. SQLite-tabeller — innhold + driver-bruk

Alle tabeller i `data/bedrock.db` med rad-antall, tids-vindu (hvis
relevant tids-kolonne finnes) og hvilke drivere som leser fra dem.
Tabeller uten driver-bruk er datakilder vi ikke utnytter scoring-
messig — de kan likevel være input til UI eller andre drivere.

| Tabell | Rader | Tids-kolonne | Min..Max | Drivere som leser |
|---|---:|---|---|---|
| `aaii_sentiment` | 538 | date | 2016-01-07..2026-04-30 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `agsi_storage` | 18,270 | gas_day_start | 2016-04-26..2026-04-27 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `analog_outcomes` | 138,508 | – | – | _(ikke brukt)_ |
| `cecafe_exports` | 668 | month | 2012-05-01..2026-03-01 | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `comex_inventory` | 15 | date | 2026-04-24..2026-04-30 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `conab_estimates` | 158 | report_date | 2022-06-15..2026-04-27 | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `cot_disaggregated` | 11,297 | report_date | 2010-01-05..2026-04-28 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `cot_euronext` | 1,221 | report_date | 2018-04-25..2026-04-29 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `cot_ice` | 1,603 | report_date | 2011-01-04..2026-04-28 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `cot_legacy` | 5,798 | report_date | 2010-01-05..2026-04-28 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `cot_tff` | 3,276 | report_date | 2016-01-05..2026-04-21 | aaii_extreme, cot_euronext_mm_pct, cot_ice_mm_pct, cot_z_score, positioning_asset_mgr_pct, positioning_lev_funds_pct, positioning_mm_pct |
| `crop_progress` | 3,114 | week_ending | 2009-10-25..2026-04-26 | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `crypto_sentiment` | 34 | date | 2026-04-02..2026-05-01 | _(ikke brukt)_ |
| `disease_alerts` | 3 | – | – | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `driver_observations` | 453,351 | – | – | _(ikke brukt)_ |
| `drought_monitor` | 539 | – | – | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `econ_events` | 41,063 | event_ts | 2007-01-01T01:00:00..2026-05-01T14:00:00 | event_distance, vol_regime |
| `eia_inventory` | 5,021 | date | 1982-08-20..2026-04-24 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `etf_holdings` | 10,632 | date | 2004-11-18..2026-04-28 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `export_events` | 6 | – | – | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `fas_esr` | 100,378 | – | – | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `feature_snapshots` | 23,601 | – | – | _(ikke brukt)_ |
| `fundamentals` | 46,717 | date | 1950-01-01..2026-04-30 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, enso_regime, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, weather_stress, yield_diff_10y |
| `igc` | 0 | report_date | – | _(ikke brukt)_ |
| `news_intel` | 102 | event_ts | 2022-12-15T08:00:00..2026-05-01T16:26:04 | _(ikke brukt)_ |
| `prices` | 90,670 | ts | 2010-01-01T00:00:00..2026-05-01T21:29:24 | momentum_z, sma200_align |
| `seismic_events` | 123,401 | event_ts | 2010-01-01T02:08:21..2026-05-01T09:24:24 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `shipping_indices` | 2,899 | date | 2014-08-28..2026-05-01 | _(ikke brukt)_ |
| `signal_setups` | 25,953 | – | – | _(ikke brukt)_ |
| `unica_reports` | 1 | report_date | 2026-04-27..2026-04-27 | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `wasde` | 8,703 | report_date | 2019-05-10..2026-04-10 | cecafe_export_change, conab_yoy, crop_progress_stage, disease_pressure, drought_monitor, export_event_active, fas_exports, shipping_pressure, unica_change, wasde_s2u_change |
| `weather` | 11,361 | date | 2016-01-01..2026-05-01 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, yield_diff_10y |
| `weather_monthly` | 2,576 | month | 2011-01..2026-04 | agsi_storage_pct, brl_chg5d, comex_stress, credit_spread_change, dxy_chg5d, eia_stock_change, enso_regime, etf_holdings_change, hdd_cdd_anomaly, mining_disruption, net_fed_liq_change, nfci_change, real_yield, vix_regime, vix_term_ratio, weather_stress, yield_diff_10y |

**8 tabeller har ingen driver-lesere (per regex-skann):**
`analog_outcomes, crypto_sentiment, driver_observations, feature_snapshots, igc, news_intel, shipping_indices, signal_setups`

**Caveat — regex-detektoren har false-positive:** drivere som
leser via custom helper-modul (eks. `find_analog_cases` fra
`bedrock.data.analog`) i stedet for direkte `store.get_*`
blir ikke fanget. Manuell verifisering anbefales:

- `analog_outcomes` (138k rader): **brukes** av `analog_hit_rate`+`analog_avg_return`
  via `find_analog_cases` (regex-miss)
- `shipping_indices` (2,899 rader): **brukes** av `bdi_chg30d`
- `crypto_sentiment` (34 rader): **ikke brukt** — kandidat for ny driver
- `news_intel` (102 rader): **ikke brukt** — kun UI-rendering, kandidat for sentiment-driver
- `igc` (0 rader): **tom** — fetcher droppet eller ikke kjørt
- `driver_observations` (453k), `feature_snapshots` (23k), `signal_setups` (26k): **meta-internal** (harvesting + persistens), ikke driver-input

---

## 2. Per-driver data-kilder

For hver driver: hvilke `store.get_*`-kall den gjør (= hvilke
tabeller den leser). Drivere uten data-kall er rene tekniske/
matematiske transformasjoner over input-params.

| Driver | Tabeller (via store.get_*) |
|---|---|
| `aaii_extreme` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `agsi_storage_pct` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `brl_chg5d` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `cecafe_export_change` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `comex_stress` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `conab_yoy` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `cot_euronext_mm_pct` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `cot_ice_mm_pct` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `cot_z_score` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `credit_spread_change` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `crop_progress_stage` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `disease_pressure` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `drought_monitor` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `dxy_chg5d` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `eia_stock_change` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `enso_regime` | fundamentals, weather_monthly |
| `etf_holdings_change` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `event_distance` | econ_events, prices_ohlc |
| `export_event_active` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `fas_exports` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `hdd_cdd_anomaly` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `mining_disruption` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `momentum_z` | prices |
| `net_fed_liq_change` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `nfci_change` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `positioning_asset_mgr_pct` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `positioning_lev_funds_pct` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `positioning_mm_pct` | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff |
| `range_position` | prices_ohlc |
| `real_yield` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `shipping_pressure` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `sma200_align` | prices |
| `unica_change` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `vix_regime` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `vix_term_ratio` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |
| `vol_regime` | econ_events, prices_ohlc |
| `wasde_s2u_change` | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde |
| `weather_stress` | fundamentals, weather_monthly |
| `yield_diff_10y` | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather |

---

## 3. Historikk-utnyttelse — har vs bruker

For drivere med eksplisitt `lookback_*` eller `window_*`-
parameter: sammenlign default-verdi (rader brukt per kall)
mot DB-historikk-dybde for relevant tabell. Stort gap =
muligheter for langsiktige-features.

| Driver | Lookback-default | Tabeller | Tilgjengelig dybde | Utnyttelse |
|---|---|---|---|---|
| `aaii_extreme` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `agsi_storage_pct` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `agsi_storage_pct` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `agsi_storage_pct` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `agsi_storage_pct` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `brl_chg5d` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `brl_chg5d` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `brl_chg5d` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `brl_chg5d` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `cecafe_export_change` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `cecafe_export_change` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `cecafe_export_change` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `comex_stress` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `comex_stress` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `comex_stress` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `comex_stress` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `conab_yoy` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `conab_yoy` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `conab_yoy` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `cot_euronext_mm_pct` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `cot_ice_mm_pct` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `cot_z_score` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `credit_spread_change` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `credit_spread_change` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `credit_spread_change` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `credit_spread_change` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `crop_progress_stage` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `crop_progress_stage` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `crop_progress_stage` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `disease_pressure` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `disease_pressure` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `disease_pressure` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `drought_monitor` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `drought_monitor` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `drought_monitor` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `dxy_chg5d` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `dxy_chg5d` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `dxy_chg5d` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `dxy_chg5d` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `eia_stock_change` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `eia_stock_change` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `eia_stock_change` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `eia_stock_change` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `enso_regime` | `lookback_months=1` (rader) | fundamentals, weather_monthly | 76y (46,717 rader) | – |
| `etf_holdings_change` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `etf_holdings_change` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `etf_holdings_change` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `etf_holdings_change` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `export_event_active` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `export_event_active` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `export_event_active` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `fas_exports` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `fas_exports` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `fas_exports` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `hdd_cdd_anomaly` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `hdd_cdd_anomaly` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `hdd_cdd_anomaly` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `hdd_cdd_anomaly` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `mining_disruption` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `mining_disruption` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `mining_disruption` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `mining_disruption` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `net_fed_liq_change` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `net_fed_liq_change` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `net_fed_liq_change` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `net_fed_liq_change` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `nfci_change` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `nfci_change` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `nfci_change` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `nfci_change` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `positioning_asset_mgr_pct` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `positioning_lev_funds_pct` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `positioning_mm_pct` | `lookback_weeks=52` (uker) | aaii_sentiment, cot, cot_euronext, cot_ice, cot_tff | 10y (538 rader) | – |
| `real_yield` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `real_yield` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `real_yield` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `real_yield` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `shipping_pressure` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `shipping_pressure` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `shipping_pressure` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `unica_change` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `unica_change` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `unica_change` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `vix_regime` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_regime` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_regime` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_regime` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_term_ratio` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_term_ratio` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_term_ratio` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `vix_term_ratio` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `wasde_s2u_change` | `lookback_days=60` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `wasde_s2u_change` | `lookback_days=90` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `wasde_s2u_change` | `window_days=30` (dager) | cecafe_exports, conab_estimates, crop_progress, disease_alerts, drought_monitor, export_events, fas_esr, shipping_index, unica_reports, wasde | 13y (668 rader) | – |
| `weather_stress` | `lookback_months=1` (rader) | fundamentals, weather_monthly | 76y (46,717 rader) | – |
| `yield_diff_10y` | `lookback_days=7` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `yield_diff_10y` | `lookback_days=30` (dager) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `yield_diff_10y` | `lookback_weeks=52` (uker) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |
| `yield_diff_10y` | `window=5` (rader) | agsi_storage, comex_inventory, eia_inventory, etf_holdings, fundamentals, seismic_events, weather | 10y (18,270 rader) | – |

---

## 4. Eksterne API-kilder — tilgjengelig + utnyttet

Alle kjente eksterne datakilder med vurdering av dagens bruk
og hva mer som er tilgjengelig (med samme keys / public).
Kandidater for nye drivere er linjene i 'Tilgjengelig mer'-
kolonnen.

### FRED (Federal Reserve)

- **URL:** https://fred.stlouisfed.org/docs/api/fred/
- **Auth:** `FRED_API_KEY` (✓ key satt)
- **I bruk i dag:** DGS10, T10YIE, DTWEXBGS, VIXCLS, NFCI, WALCL, WTREGEN, DGS2, foreign 10Y, AAA10Y, BAA10Y, RRPONTSYD
- **Tilgjengelig mer:** 800,000+ økonomiske serier — manglende: M2, industrial production, ISM PMI, employment data, housing starts, retail sales, CPI sub-components, yield-spread (3M-10Y), TED spread, real GDP, consumer confidence (UMCSENT), federal funds futures (DFEDTAR)

### USDA NASS QuickStats

- **URL:** https://quickstats.nass.usda.gov/api
- **Auth:** `BEDROCK_NASS_API_KEY` (✓ key satt)
- **I bruk i dag:** Crop Progress (PLANTED/SILKING/HARVESTED/GOOD_EXCELLENT) for CORN/SOYBEAN/WHEAT/COTTON
- **Tilgjengelig mer:** Yields, production estimates, prices received, stocks (grain in storage), exports, imports, planted vs harvested area, cattle inventory, hog inventory, dairy production

### EIA (Energy Information Administration)

- **URL:** https://api.eia.gov/v2
- **Auth:** `BEDROCK_EIA_API_KEY` (✓ key satt)
- **I bruk i dag:** WCESTUS1 (Crude Stocks), WGTSTUS1 (Gasoline), NW2_EPG0_SWO_R48_BCF (NatGas)
- **Tilgjengelig mer:** Distillate stocks, propane stocks, ethanol, refinery utilization, refinery inputs (crude+gasoline runs), imports/exports, petroleum products supplied (demand proxy), natural gas processing, electricity demand

### AGSI+ (EU Gas Storage)

- **URL:** https://agsi.gie.eu/api
- **Auth:** `BEDROCK_AGSI_API_KEY` (✗ ingen key)
- **I bruk i dag:** EU-aggregat consumption_full_pct (current vs capacity)
- **Tilgjengelig mer:** Per-land breakdown (DE, NL, IT, FR, AT, ES, PL etc.), withdrawal/injection rates, full vs working capacity, trend over time

### FAS (Foreign Agricultural Service)

- **URL:** https://api.fas.usda.gov
- **Auth:** `FAS_API_KEY` (✓ key satt)
- **I bruk i dag:** Weekly export sales (CORN/SOYBEAN/WHEAT/COTTON)
- **Tilgjengelig mer:** Production estimates per land, beginning stocks, domestic consumption, ending stocks, imports/exports per produkt

### cTrader Open API (Spotware)

- **URL:** https://connect.spotware.com
- **Auth:** `CTRADER_ACCESS_TOKEN` (✓ key satt)
- **I bruk i dag:** Live priser via bot (kun runtime, ikke lagret)
- **Tilgjengelig mer:** Historiske 1m/5m/15m/1h/D candles, depth-of-book, trade-history, deals-history (eget regnskap). Disse kan loaststs til DB for backtest hvis ønsket

### Yahoo Finance

- **URL:** https://query1.finance.yahoo.com
- **Auth:** `(ingen key — public)` ((public, ingen key))
- **I bruk i dag:** Daily price-data for alle 22 instrumenter via yfinance
- **Tilgjengelig mer:** Intraday 1m/5m/15m/1h (siste 60 dager max for 1m), options chains (volatilitet-skew), earnings dates, dividend history (for indeks-konstruksjoner)

### USGS Earthquake (seismic)

- **URL:** https://earthquake.usgs.gov/fdsnws/event/1
- **Auth:** `(ingen key — public)` ((public, ingen key))
- **I bruk i dag:** Mag ≥ 4.5 siste 7 dager, mining-region-mapped
- **Tilgjengelig mer:** Tilbake til 1900 (M ≥ 4.0), GeoJSON med detaljerte metadata (depth, rms, quality)

### ICE Public CSV (cot_ice)

- **URL:** https://www.theice.com/marketdata/reports/cot
- **Auth:** `(ingen key)` ((public, ingen key))
- **I bruk i dag:** ICE Brent + Gasoil COT ukentlig
- **Tilgjengelig mer:** Cocoa, Coffee, Wheat, Sugar, Dubai 1st line (også på public CSV — kan utvides)

### Forex Factory Calendar

- **URL:** https://faireconomy.media
- **Auth:** `(ingen key — JSON-feed)` ((public, ingen key))
- **I bruk i dag:** Event-distance + High/Medium impact-events
- **Tilgjengelig mer:** Forecast/previous/actual-felt for surprise-driver (ikke implementert)

### AAII Sentiment

- **URL:** https://www.aaii.com/sentimentsurvey
- **Auth:** `(ingen key — public XLSX)` ((public, ingen key))
- **I bruk i dag:** Bullish/Bearish % weekly
- **Tilgjengelig mer:** Historisk neutral-andel + 8-week-MA (kunne brukes for divergens-driver)

### ESMIS (USDA WASDE)

- **URL:** https://usda.library.cornell.edu
- **Auth:** `(ingen key — XML-feed)` ((public, ingen key))
- **I bruk i dag:** Månedlige supply/use-tabeller for 6 commodities
- **Tilgjengelig mer:** Monthly Coffee/Cocoa via separate WASDE-segment (ikke pulled)

### BDRY ETF (Yahoo proxy for BDI)

- **URL:** yahoo!Finance
- **Auth:** `(ingen key)` ((public, ingen key))
- **I bruk i dag:** Baltic Dry Index proxy (ikke direkte BDI)
- **Tilgjengelig mer:** Direkte BDI fra Baltic Exchange er kommersielt; BDRY er gratis approximation (~0.9 corr)

### Cecafé (Brazil coffee)

- **URL:** https://www.cecafe.com.br
- **Auth:** `(ingen key)` ((public, ingen key))
- **I bruk i dag:** Månedlig PDF-skraping for eksport-volum
- **Tilgjengelig mer:** Per-region (Sul de Minas, Cerrado etc.), per-grade differensial

### Conab (Brazil agri)

- **URL:** https://www.conab.gov.br
- **Auth:** `(ingen key)` ((public, ingen key))
- **I bruk i dag:** Årlige produksjon-estimater for Soybean/Corn/Coffee
- **Tilgjengelig mer:** Cotton, Sugar, månedlige Crop Progress-rapporter

### USDM (Drought Monitor)

- **URL:** https://droughtmonitor.unl.edu
- **Auth:** `(ingen key — CSV)` ((public, ingen key))
- **I bruk i dag:** CONUS-aggregat ukentlig
- **Tilgjengelig mer:** Per-state breakdown (Iowa for corn, Texas for cotton, California for almonds, etc.)

---

## 5. Arkitektur — er det enkelt å legge til/fjerne drivere?

**Ja, arkitekturen er bygd for det.** Per `docs/driver_authoring.md`:

### Legge til en driver (eks. ny FRED-serie):

1. Skriv funksjon i `src/bedrock/engine/drivers/<kategori>.py`:
   ```python
   @register("my_new_driver")
   def my_new_driver(store, instrument, params):
       series = store.get_fundamentals("MY_FRED_ID", lookback=...)
       return clip(z_score(series), 0, 1)
   ```
2. Oppdater fetch.yaml hvis ny datakilde må hentes:
   ```yaml
   fundamentals:
     fred_series_ids:
       - MY_FRED_ID
   ```
3. Wire inn i instrument-YAML:
   ```yaml
   families:
     macro:
       drivers:
         - {name: my_new_driver, weight: 0.3, horizons: [MAKRO]}
   ```
4. Re-generer baseline + signals:
   ```
   .venv/bin/python scripts/snapshot/score_baseline.py
   .venv/bin/bedrock signals-all
   ```

**Ingen kjerne-kode-endringer.** Engine slår opp via registry-
dict; YAML-felt valideres av Pydantic uten hardkodede driver-
navn-listinger noe sted.

### Fjerne en driver (eks. for å slanke en familie):

1. Slett driver-entryen fra instrument-YAML(ene)
2. (Valgfritt) Slett funksjonen fra `drivers/*.py` hvis ingen
   andre instrumenter bruker den
3. Re-generer baseline

Ingen migrasjons-script trengs — Pydantic-validering fanger
dangling-references ved oppstart.

### Verifisert i denne sessionen:

- Sub-fase 12.9 Fase 3 la til `horizons:`-felt på DriverSpec
  uten å touche kjerne-engine-loops
- Sub-fase 12.5+ session 138 droppet 2 dead-drivere
  (`currency_cross_trend`, `igc_stocks_change`) ved kun YAML-
  fjern + slette driver-fil. Ingen migrasjons-arbeid.
- 17 drivere fikk horisont-filter via 1-fils YAML-script
  (`/tmp/migrate_horizons.py`). Lap-tid ~3 sek.

---

## 6. Anbefalte data-utvidelser (kandidat-drivere)

Basert på Seksjon 4: kilder vi har tilgang til men ikke
utnytter. Sortert etter forventet IC og tilgjengelighet.
Implementasjon estimat-time = ~2-4 timer per driver inkl.
schema + fetcher + driver + tester.

| Prioritet | Driver-idé | Kilde | Bruk |
|---|---|---|---|
| **HØY** | `industrial_production_yoy` | FRED INDPRO | Macro-regime confirmation, korrelert med Copper/CrudeOil-prising |
| **HØY** | `ism_pmi` | FRED NAPM | Manufacturing PMI; ledende indikator for risk-on/off |
| **HØY** | `umich_consumer_sentiment` | FRED UMCSENT | Tidlig sentiment-skifte, swing-driver |
| **HØY** | `forecast_surprise` (NFP/CPI) | calendar_ff forecast/actual | Scalp-trigger ved release |
| **MED** | `eia_distillate_change` | EIA series | NatGas/Brent supply-side, ukentlig |
| **MED** | `nass_yields_yoy` | USDA NASS | Agri yield-estimat-divergens |
| **MED** | `agsi_per_country` | AGSI per-land | NatGas regional supply (DE/NL/IT) |
| **MED** | `usdm_per_state` | USDM per-stat | Cotton (TX), Corn (IA) — mer presist |
| **LAV** | `seismic_global_M6_24h` | USGS | Real-time scalp-trigger, sjelden |
| **LAV** | `cot_ice_cocoa/coffee/sugar` | ICE Public CSV | Allerede pulled, bare wire driver |
| **LAV** | `vix_options_skew` | Yahoo VIX9D vs VIX | Volatilitet-skew som scalp-bias |

**Ikke-anbefalt:** Kommersielle kilder (Bloomberg, Reuters,
LSEG, ICE Premium). Bedrock-prinsipp er gratis-kilder + manuell
CSV-fallback der HTTP feiler (ADR-007).

---

_Generert av_ `scripts/analysis/data_utilization_report.py` _på 2026-05-01._
