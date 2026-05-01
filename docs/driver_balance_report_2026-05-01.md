# Driver-balanse-rapport — 2026-05-01

**Generert:** 2026-05-01T22:04:08.922439+00:00
**Antall instrumenter:** 22
**Antall registrerte drivere:** 42

Bruk denne rapporten til å vurdere rebalansering av driver-vekter
og horisont-filtrering. Hver seksjon er selvstendig — du kan
hoppe direkte til den som er relevant for din analyse.

---

## 1. Driver-registry — registrert vs brukt

Alle drivere som er registrert via `@register_driver` i
`src/bedrock/engine/drivers/`, sortert alfabetisk. Kolonnen
**Brukt** viser hvor mange instrumenter har driveren wired
inn i en YAML-familie. Drivere med 0 brukt-count er enten
ny-introdusert eller dead-code-kandidat.

| Driver | Brukt på | Filer (instrumenter) |
|---|---:|---|
| `aaii_extreme` | 2 | Nasdaq, SP500 |
| `agsi_storage_pct` | 1 | NaturalGas |
| `analog_avg_return` | 22 | AUDUSD, BTC, Brent, Cocoa, Coffee, Copper, Corn, Cotton, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, Soybean, Sugar, USDJPY, Wheat |
| `analog_hit_rate` | 22 | AUDUSD, BTC, Brent, Cocoa, Coffee, Copper, Corn, Cotton, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, Soybean, Sugar, USDJPY, Wheat |
| `brl_chg5d` | 2 | Coffee, Sugar |
| `cecafe_export_change` | 1 | Coffee |
| `comex_stress` | 3 | Copper, Gold, Silver |
| `conab_yoy` | 3 | Coffee, Corn, Soybean |
| `cot_euronext_mm_pct` | 2 | Corn, Wheat |
| `cot_ice_mm_pct` | 2 | Brent, NaturalGas |
| `cot_z_score` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `credit_spread_change` | 4 | BTC, ETH, Nasdaq, SP500 |
| `crop_progress_stage` | 4 | Corn, Cotton, Soybean, Wheat |
| `disease_pressure` | 2 | Coffee, Wheat |
| `drought_monitor` | 4 | Corn, Cotton, Soybean, Wheat |
| `dxy_chg5d` | 20 | AUDUSD, BTC, Brent, Cocoa, Copper, Corn, Cotton, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, Soybean, USDJPY, Wheat |
| `eia_stock_change` | 3 | Brent, CrudeOil, NaturalGas |
| `enso_regime` | 7 | Cocoa, Coffee, Corn, Cotton, Soybean, Sugar, Wheat |
| `etf_holdings_change` | 2 | Gold, Silver |
| `event_distance` | 22 | AUDUSD, BTC, Brent, Cocoa, Coffee, Copper, Corn, Cotton, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, Soybean, Sugar, USDJPY, Wheat |
| `export_event_active` | 1 | Wheat |
| `fas_exports` | 4 | Corn, Cotton, Soybean, Wheat |
| `hdd_cdd_anomaly` | 1 | NaturalGas |
| `mining_disruption` | 4 | Copper, Gold, Platinum, Silver |
| `momentum_z` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `net_fed_liq_change` | 4 | BTC, ETH, Nasdaq, SP500 |
| `nfci_change` | 4 | BTC, ETH, Nasdaq, SP500 |
| `positioning_asset_mgr_pct` | 8 | AUDUSD, BTC, ETH, EURUSD, GBPUSD, Nasdaq, SP500, USDJPY |
| `positioning_lev_funds_pct` | 8 | AUDUSD, BTC, ETH, EURUSD, GBPUSD, Nasdaq, SP500, USDJPY |
| `positioning_mm_pct` | 6 | Copper, CrudeOil, Gold, NaturalGas, Platinum, Silver |
| `range_position` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `real_yield` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `seasonal_stage` | 7 | Cocoa, Coffee, Corn, Cotton, Soybean, Sugar, Wheat |
| `shipping_pressure` | 3 | Corn, Soybean, Wheat |
| `sma200_align` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `unica_change` | 1 | Sugar |
| `vix_regime` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `vix_term_ratio` | 0 | _(ubrukt)_ |
| `vol_regime` | 15 | AUDUSD, BTC, Brent, Copper, CrudeOil, ETH, EURUSD, GBPUSD, Gold, Nasdaq, NaturalGas, Platinum, SP500, Silver, USDJPY |
| `wasde_s2u_change` | 5 | Corn, Cotton, Soybean, Sugar, Wheat |
| `weather_stress` | 7 | Cocoa, Coffee, Corn, Cotton, Soybean, Sugar, Wheat |
| `yield_diff_10y` | 4 | AUDUSD, EURUSD, GBPUSD, USDJPY |

⚠ **1 drivere er registrert men ikke brukt** i noen YAML:
`vix_term_ratio`

---

## 2. Family-vekter per instrument × horisont

Family-weights fra `horizons:`-blokken i hver instrument-YAML.
Disse styrer hvor mye HVER FAMILIE bidrar til total-score per
horisont. Family-summen normaliseres ikke automatisk — operatør
velger relativ vektlegging.

### crypto

| Instrument | Horisont | analog | macro | positioning | risk | structure | trend | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | SCALP | 0.30 | 0.50 | 0.40 | 0.70 | 1.40 | 1.50 | 4.80 | 4.8 |
| BTC | SWING | 0.70 | 0.70 | 0.80 | 1.00 | 1.00 | 1.20 | 5.40 | 5.4 |
| BTC | MAKRO | 1.20 | 1.00 | 1.00 | 0.80 | 0.50 | 1.00 | 5.50 | 5.5 |
| ETH | SCALP | 0.30 | 0.50 | 0.40 | 0.70 | 1.40 | 1.50 | 4.80 | 4.8 |
| ETH | SWING | 0.70 | 0.70 | 0.80 | 1.00 | 1.00 | 1.20 | 5.40 | 5.4 |
| ETH | MAKRO | 1.20 | 1.00 | 1.00 | 0.80 | 0.50 | 1.00 | 5.50 | 5.5 |

### energy

| Instrument | Horisont | analog | macro | positioning | risk | structure | trend | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Brent | SCALP | 0.30 | 0.80 | 0.50 | 0.80 | 1.30 | 1.20 | 4.90 | 4.9 |
| Brent | SWING | 0.60 | 1.00 | 1.20 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Brent | MAKRO | 1.00 | 1.30 | 1.50 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| CrudeOil | SCALP | 0.30 | 0.80 | 0.50 | 0.80 | 1.30 | 1.20 | 4.90 | 4.9 |
| CrudeOil | SWING | 0.60 | 1.00 | 1.20 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| CrudeOil | MAKRO | 1.00 | 1.30 | 1.50 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| NaturalGas | SCALP | 0.30 | 0.60 | 0.50 | 1.00 | 1.40 | 1.20 | 5.00 | 5.0 |
| NaturalGas | SWING | 0.60 | 0.80 | 1.00 | 1.20 | 1.20 | 1.00 | 5.80 | 5.8 |
| NaturalGas | MAKRO | 1.00 | 1.00 | 1.30 | 1.00 | 0.50 | 0.80 | 5.60 | 5.6 |

### fx

| Instrument | Horisont | analog | macro | positioning | risk | structure | trend | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AUDUSD | SCALP | 0.30 | 1.00 | 0.50 | 0.60 | 1.30 | 1.20 | 4.90 | 4.9 |
| AUDUSD | SWING | 0.80 | 1.20 | 1.00 | 0.80 | 1.00 | 1.00 | 5.80 | 5.8 |
| AUDUSD | MAKRO | 1.20 | 1.50 | 1.20 | 0.60 | 0.50 | 0.80 | 5.80 | 5.8 |
| EURUSD | SCALP | 0.30 | 1.00 | 0.50 | 0.60 | 1.30 | 1.20 | 4.90 | 4.9 |
| EURUSD | SWING | 0.80 | 1.20 | 1.00 | 0.80 | 1.00 | 1.00 | 5.80 | 5.8 |
| EURUSD | MAKRO | 1.20 | 1.50 | 1.20 | 0.60 | 0.50 | 0.80 | 5.80 | 5.8 |
| GBPUSD | SCALP | 0.30 | 1.00 | 0.50 | 0.60 | 1.30 | 1.20 | 4.90 | 4.9 |
| GBPUSD | SWING | 0.80 | 1.20 | 1.00 | 0.80 | 1.00 | 1.00 | 5.80 | 5.8 |
| GBPUSD | MAKRO | 1.20 | 1.50 | 1.20 | 0.60 | 0.50 | 0.80 | 5.80 | 5.8 |
| USDJPY | SCALP | 0.30 | 1.00 | 0.50 | 0.60 | 1.30 | 1.20 | 4.90 | 4.9 |
| USDJPY | SWING | 0.80 | 1.20 | 1.00 | 0.80 | 1.00 | 1.00 | 5.80 | 5.8 |
| USDJPY | MAKRO | 1.20 | 1.50 | 1.20 | 0.60 | 0.50 | 0.80 | 5.80 | 5.8 |

### grains

| Instrument | Horisont | analog | conab | cross | enso | outlook | weather | yield | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Corn | (agri) | 2.00 | 2.00 | 2.00 | 2.00 | 5.00 | 2.00 | 3.00 | 18.00 | 20.0 |
| Soybean | (agri) | 2.00 | 2.00 | 2.00 | 2.00 | 5.00 | 2.00 | 3.00 | 18.00 | 16.0 |
| Wheat | (agri) | 2.00 | – | 2.00 | 2.00 | 5.00 | 2.00 | 3.00 | 16.00 | 16.0 |

### indices

| Instrument | Horisont | analog | macro | positioning | risk | structure | trend | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Nasdaq | SCALP | 0.30 | 0.80 | 0.50 | 0.80 | 1.30 | 1.20 | 4.90 | 4.9 |
| Nasdaq | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Nasdaq | MAKRO | 1.20 | 1.40 | 1.20 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| SP500 | SCALP | 0.30 | 0.80 | 0.50 | 0.80 | 1.30 | 1.20 | 4.90 | 4.9 |
| SP500 | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| SP500 | MAKRO | 1.20 | 1.40 | 1.20 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |

### metals

| Instrument | Horisont | analog | macro | positioning | risk | structure | trend | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Copper | SCALP | 0.30 | 0.70 | 0.50 | 0.80 | 1.30 | 1.20 | 4.80 | 4.8 |
| Copper | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Copper | MAKRO | 1.20 | 1.30 | 1.30 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| Gold | SCALP | 0.30 | 0.70 | 0.50 | 0.80 | 1.30 | 1.20 | 4.80 | 4.8 |
| Gold | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Gold | MAKRO | 1.20 | 1.30 | 1.30 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| Platinum | SCALP | 0.30 | 0.70 | 0.50 | 0.80 | 1.30 | 1.20 | 4.80 | 4.8 |
| Platinum | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Platinum | MAKRO | 1.20 | 1.30 | 1.30 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |
| Silver | SCALP | 0.30 | 0.70 | 0.50 | 0.80 | 1.30 | 1.20 | 4.80 | 4.8 |
| Silver | SWING | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.80 | 5.8 |
| Silver | MAKRO | 1.20 | 1.30 | 1.30 | 0.80 | 0.50 | 0.80 | 5.90 | 5.9 |

### softs

| Instrument | Horisont | analog | conab | cross | enso | outlook | unica | weather | yield | Sum | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cocoa | (agri) | 2.00 | – | 2.00 | 2.00 | 5.00 | – | 2.00 | 3.00 | 16.00 | 16.0 |
| Coffee | (agri) | 2.00 | 2.00 | 2.00 | 2.00 | 5.00 | – | 2.00 | 3.00 | 18.00 | 16.0 |
| Cotton | (agri) | 2.00 | – | 2.00 | 2.00 | 5.00 | – | 2.00 | 3.00 | 16.00 | 16.0 |
| Sugar | (agri) | 2.00 | – | 2.00 | 2.00 | 5.00 | 2.00 | 2.00 | 3.00 | 18.00 | 16.0 |

---

## 3. Per-driver bruksanalyse

For hver brukte driver: hvilken familie den ligger i, gjennom-
snittlig vekt over instrumentene som bruker den, vekt-spredning
(min..max), horisont-filter (eller 'alle 3'), antall instrumenter.

**Sortert etter bruks-count.** Drivere med lav count + tung
vekt er kandidater for å vurdere om de skal beholdes; drivere
med høy count + uniform vekt er stabile fundamentale.

| Driver | Familie | Antall inst | Vekt-snitt | Vekt-min..max | Horisonter | Total vekt-sum |
|---|---|---:|---:|---|---|---:|
| `event_distance` | cross, risk | 22 | 0.218 | 0.10..0.30 | SCALP+SWING | 4.80 |
| `analog_hit_rate` | analog | 22 | 0.500 | 0.50..0.50 | MAKRO+SWING | 11.00 |
| `analog_avg_return` | analog | 22 | 0.500 | 0.50..0.50 | MAKRO+SWING | 11.00 |
| `dxy_chg5d` | cross, macro | 20 | 0.345 | 0.20..0.85 | alle 3 | 6.90 |
| `sma200_align` | trend | 15 | 0.500 | 0.50..0.50 | alle 3 | 7.50 |
| `momentum_z` | trend | 15 | 0.500 | 0.50..0.50 | alle 3 | 7.50 |
| `cot_z_score` | positioning | 15 | 0.379 | 0.28..0.40 | alle 3 | 5.68 |
| `real_yield` | macro | 15 | 0.213 | 0.10..0.35 | alle 3 | 3.20 |
| `vix_regime` | macro | 15 | 0.123 | 0.05..0.25 | alle 3 | 1.85 |
| `range_position` | structure | 15 | 1.000 | 1.00..1.00 | alle 3 | 15.00 |
| `vol_regime` | risk | 15 | 0.665 | 0.55..0.70 | alle 3 | 9.98 |
| `positioning_lev_funds_pct` | positioning | 8 | 0.375 | 0.30..0.40 | alle 3 | 3.00 |
| `positioning_asset_mgr_pct` | positioning | 8 | 0.187 | 0.15..0.20 | alle 3 | 1.50 |
| `seasonal_stage` | outlook | 7 | 1.000 | 1.00..1.00 | MAKRO | 7.00 |
| `weather_stress` | weather, yield | 7 | 0.614 | 0.20..1.00 | MAKRO+SWING | 8.60 |
| `enso_regime` | enso | 7 | 1.000 | 1.00..1.00 | MAKRO | 7.00 |
| `positioning_mm_pct` | positioning | 6 | 0.570 | 0.42..0.60 | alle 3 | 3.42 |
| `wasde_s2u_change` | conab, yield | 5 | 0.520 | 0.40..0.70 | MAKRO+SWING | 2.60 |
| `yield_diff_10y` | macro | 4 | 0.325 | 0.25..0.35 | MAKRO | 1.30 |
| `net_fed_liq_change` | macro | 4 | 0.275 | 0.25..0.30 | MAKRO | 1.10 |
| `nfci_change` | macro | 4 | 0.200 | 0.20..0.20 | MAKRO | 0.80 |
| `credit_spread_change` | risk | 4 | 0.255 | 0.25..0.26 | MAKRO | 1.02 |
| `mining_disruption` | macro | 4 | 0.163 | 0.10..0.30 | alle 3 | 0.65 |
| `crop_progress_stage` | yield | 4 | 0.300 | 0.20..0.50 | MAKRO+SWING | 1.20 |
| `drought_monitor` | weather | 4 | 0.450 | 0.45..0.45 | MAKRO+SWING | 1.80 |
| `fas_exports` | cross | 4 | 0.175 | 0.15..0.20 | MAKRO+SWING | 0.70 |
| `eia_stock_change` | macro | 3 | 0.300 | 0.30..0.30 | alle 3 | 0.90 |
| `conab_yoy` | conab | 3 | 0.667 | 0.30..1.00 | MAKRO | 2.00 |
| `comex_stress` | macro | 3 | 0.183 | 0.15..0.20 | alle 3 | 0.55 |
| `shipping_pressure` | cross | 3 | 0.150 | 0.15..0.15 | alle 3 | 0.45 |
| `cot_ice_mm_pct` | positioning | 2 | 0.450 | 0.30..0.60 | alle 3 | 0.90 |
| `disease_pressure` | yield | 2 | 0.200 | 0.10..0.30 | alle 3 | 0.40 |
| `brl_chg5d` | cross | 2 | 0.900 | 0.90..0.90 | alle 3 | 1.80 |
| `cot_euronext_mm_pct` | cross | 2 | 0.175 | 0.15..0.20 | alle 3 | 0.35 |
| `etf_holdings_change` | macro | 2 | 0.175 | 0.15..0.20 | alle 3 | 0.35 |
| `aaii_extreme` | positioning | 2 | 0.250 | 0.25..0.25 | SWING | 0.50 |
| `cecafe_export_change` | conab | 1 | 0.300 | 0.30..0.30 | MAKRO | 0.30 |
| `agsi_storage_pct` | macro | 1 | 0.100 | 0.10..0.10 | MAKRO | 0.10 |
| `hdd_cdd_anomaly` | macro | 1 | 0.200 | 0.20..0.20 | alle 3 | 0.20 |
| `unica_change` | unica | 1 | 0.500 | 0.40..0.60 | alle 3 | 1.00 |
| `export_event_active` | yield | 1 | 0.100 | 0.10..0.10 | alle 3 | 0.10 |

---

## 4. Per-horisont effective driver count

Antall drivere som faktisk kjører på hver horisont per
instrument, etter `DriverSpec.horizons`-filter (Fase 3).
MAKRO som har færre drivere enn SCALP er typisk for instrumenter
med tunge event_distance/aaii-drivere som er filtrert bort fra
makro.

| Instrument | SCALP | SWING | MAKRO | Total drivere | Filtrerte |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 11 | 13 | 13 | 14 | 4 |
| BTC | 11 | 13 | 15 | 16 | 6 |
| Brent | 11 | 13 | 12 | 13 | 3 |
| Cocoa | 2 | 6 | 7 | 8 | 7 |
| Coffee | 3 | 7 | 10 | 11 | 9 |
| Copper | 12 | 14 | 13 | 14 | 3 |
| Corn | 4 | 12 | 14 | 15 | 12 |
| Cotton | 2 | 10 | 11 | 12 | 11 |
| CrudeOil | 11 | 13 | 12 | 13 | 3 |
| ETH | 11 | 13 | 15 | 16 | 6 |
| EURUSD | 11 | 13 | 13 | 14 | 4 |
| GBPUSD | 11 | 13 | 13 | 14 | 4 |
| Gold | 13 | 15 | 14 | 15 | 3 |
| Nasdaq | 11 | 14 | 15 | 17 | 7 |
| NaturalGas | 13 | 15 | 15 | 16 | 4 |
| Platinum | 11 | 13 | 12 | 13 | 3 |
| SP500 | 11 | 14 | 15 | 17 | 7 |
| Silver | 13 | 15 | 14 | 15 | 3 |
| Soybean | 3 | 11 | 13 | 14 | 12 |
| Sugar | 4 | 9 | 10 | 11 | 8 |
| USDJPY | 11 | 13 | 13 | 14 | 4 |
| Wheat | 6 | 14 | 15 | 16 | 11 |

---

## 5. Anomalier — kandidat for rebalansering

Automatisk flagging av potensielle issue-r. Manuell vurdering
kreves for hver — flagg betyr 'verdt å se på', ikke 'er bug'.

- **[INFO] [high-weight]** AUDUSD.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** BTC.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Brent.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cocoa.cross.dxy_chg5d: vekt=0.85 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cocoa.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cocoa.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cocoa.weather.weather_stress: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cocoa.yield.weather_stress: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Coffee.cross.brl_chg5d: vekt=0.90 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Coffee.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Coffee.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Coffee.weather.weather_stress: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Copper.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Corn.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Corn.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cotton.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Cotton.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** CrudeOil.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** ETH.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** EURUSD.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** GBPUSD.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Gold.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Nasdaq.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** NaturalGas.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Platinum.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** SP500.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Silver.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Soybean.conab.conab_yoy: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Soybean.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Soybean.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Sugar.cross.brl_chg5d: vekt=0.90 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Sugar.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Sugar.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Sugar.weather.weather_stress: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** USDJPY.structure.range_position: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Wheat.enso.enso_regime: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [high-weight]** Wheat.outlook.seasonal_stage: vekt=1.00 (ev. fragilitet hvis driver feilberegnes)
- **[INFO] [unused]** `vix_term_ratio` registrert men ikke i noen YAML

---

## 6. Asset-class-distribusjon

| Asset class | Instrumenter | Snitt drivere/inst |
|---|---|---:|
| crypto | BTC, ETH | 16.0 |
| energy | Brent, CrudeOil, NaturalGas | 14.0 |
| fx | AUDUSD, EURUSD, GBPUSD, USDJPY | 14.0 |
| grains | Corn, Soybean, Wheat | 15.0 |
| indices | Nasdaq, SP500 | 17.0 |
| metals | Copper, Gold, Platinum, Silver | 14.2 |
| softs | Cocoa, Coffee, Cotton, Sugar | 10.5 |

---

_Generert av_ `scripts/analysis/driver_balance_report.py` _på 2026-05-01._
