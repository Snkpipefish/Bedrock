# Driver-performance-analyse — 2026-05-01

Per-driver IC + kvartil-hit-rate-analyse fra `driver_observations`-
tabellen. Genereres av `scripts/analyze_driver_performance.py`.

## Kontekst

- Total observasjoner: 453,264
- Instrumenter: 22
- Drivere: 41
- Tidsspenn: 2010-01-25 til 2026-03-31
- Kombinasjoner med n ≥ 30 (kvalifisert): 1680/1680

## Metrikker

- **IC (Information Coefficient)**: Spearman-korr mellom driver_value
  og forward_return_pct. Positiv IC for BUY-retning betyr driver
  predikerer riktig (høy verdi → høy fwd-return). For SELL er korrekt
  IC negativ (høy bull-confidence → lav/negativ fwd-return).
- **Hit Q1/Q4**: hit-rate i bunn-/topp-kvartil av driver-verdier.
- **Monotonisitet**: andel av kvartil-par (Q1→Q2, Q2→Q3, Q3→Q4) der
  hit-rate beveger seg riktig vei. 1.0 = perfekt prediktiv.

## Top-IC-drivere (alle (inst, hor, dir)-kombinasjoner)

| Driver | Family | Instrument | Hor | Dir | n | IC | Hit Q1 | Hit Q4 | Mono |
|---|---|---|---:|---|---:|---:|---:|---:|---:|
| real_yield | macro | Gold | 90d | buy | 284 | -0.541 | 65.9% | 10.6% | 0.00 |
| real_yield | macro | Gold | 90d | sell | 284 | 0.541 | 28.1% | 0.0% | 1.00 |
| real_yield | macro | Copper | 90d | sell | 72 | 0.468 | 57.1% | 15.7% | 1.00 |
| real_yield | macro | Copper | 90d | buy | 72 | -0.468 | 40.6% | 0.0% | 0.00 |
| real_yield | macro | Copper | 60d | buy | 73 | -0.404 | 50.8% | 12.5% | 0.00 |
| real_yield | macro | Copper | 60d | sell | 73 | 0.404 | 57.1% | 25.0% | 1.00 |
| real_yield | macro | Silver | 90d | sell | 284 | 0.382 | 41.8% | 2.1% | 1.00 |
| real_yield | macro | Silver | 90d | buy | 284 | -0.382 | 52.9% | 21.3% | 0.00 |
| real_yield | macro | Gold | 60d | buy | 288 | -0.354 | 50.7% | 21.3% | 0.00 |
| real_yield | macro | Gold | 60d | sell | 288 | 0.354 | 32.2% | 7.8% | 1.00 |
| sma200_align | trend | Copper | 90d | sell | 72 | 0.335 |   -  % |   -  % |   -   |
| sma200_align | trend | Copper | 90d | buy | 72 | -0.335 |   -  % |   -  % |   -   |
| vix_regime | macro | AUDUSD | 90d | sell | 294 | 0.322 | 20.4% | 7.7% | 1.00 |
| vix_regime | macro | AUDUSD | 90d | buy | 294 | -0.322 | 30.7% | 3.7% | 0.00 |
| enso_regime | enso | Corn | 90d | sell | 284 | -0.320 | 18.1% | 41.4% | 0.50 |
| enso_regime | enso | Corn | 90d | buy | 284 | 0.320 | 25.9% | 89.5% | 1.00 |
| credit_spread_change | risk | BTC | 90d | buy | 204 | -0.317 | 63.8% | 0.0% | 0.00 |
| credit_spread_change | risk | BTC | 90d | sell | 204 | -0.317 | 26.6% | 100.0% | 0.00 |
| sma200_align | trend | Copper | 60d | buy | 73 | -0.314 |   -  % |   -  % |   -   |
| sma200_align | trend | Copper | 60d | sell | 73 | 0.314 |   -  % |   -  % |   -   |
| real_yield | macro | Copper | 30d | sell | 75 | 0.304 | 28.6% | 18.5% | 1.00 |
| real_yield | macro | Copper | 30d | buy | 75 | -0.304 | 37.3% | 12.5% | 0.00 |
| cot_z_score | positioning | EURUSD | 90d | sell | 294 | -0.303 | 6.5% | 22.0% | 0.00 |
| cot_z_score | positioning | EURUSD | 90d | buy | 294 | 0.303 | 9.1% | 25.0% | 1.00 |
| real_yield | macro | Gold | 30d | sell | 288 | 0.299 | 28.1% | 9.8% | 1.00 |
| real_yield | macro | Gold | 30d | buy | 288 | -0.299 | 46.5% | 21.3% | 0.50 |
| vix_regime | macro | ETH | 90d | sell | 211 | 0.297 | 54.5% | 27.5% | 0.50 |
| vix_regime | macro | ETH | 90d | buy | 211 | -0.297 | 64.9% | 35.7% | 0.00 |
| vix_regime | macro | AUDUSD | 30d | buy | 299 | -0.289 | 31.1% | 9.1% | 0.50 |
| vix_regime | macro | AUDUSD | 30d | sell | 299 | 0.289 | 19.6% | 7.5% | 1.00 |

## Per-driver-sammendrag (median over alle kombinasjoner)

| Driver | # kombos | Median \|IC\| | Max \|IC\| | Min IC | Max IC | Median mono | Avg n |
|---|---:|---:|---:|---:|---:|---:|---:|
| enso_regime | 42 | 0.185 | 0.320 | -0.320 | 0.320 | 0.50 | 287 |
| vix_regime | 90 | 0.130 | 0.322 | -0.322 | 0.322 | 0.50 | 264 |
| positioning_mm_pct | 36 | 0.130 | 0.228 | -0.228 | 0.228 | 0.67 | 249 |
| cot_ice_mm_pct | 6 | 0.121 | 0.170 | -0.170 | 0.170 | 0.67 | 286 |
| agsi_storage_pct | 6 | 0.119 | 0.166 | -0.166 | 0.166 | 0.50 | 287 |
| real_yield | 90 | 0.118 | 0.541 | -0.541 | 0.541 | 0.50 | 264 |
| drought_monitor | 24 | 0.107 | 0.166 | -0.166 | 0.166 | 0.50 | 287 |
| cot_z_score | 90 | 0.106 | 0.303 | -0.303 | 0.303 | 0.50 | 264 |
| weather_stress | 42 | 0.104 | 0.187 | -0.187 | 0.187 | 0.50 | 287 |
| seasonal_stage | 1 | 0.101 | 0.101 | 0.101 | 0.101 |   -   | 288 |
| net_fed_liq_change | 24 | 0.092 | 0.202 | -0.202 | 0.202 | 0.67 | 248 |
| positioning_lev_funds_pct | 48 | 0.092 | 0.197 | -0.197 | 0.197 | 0.50 | 273 |
| conab_yoy | 16 | 0.091 | 0.160 | -0.160 | 0.160 |   -   | 287 |
| credit_spread_change | 24 | 0.090 | 0.317 | -0.317 | 0.047 | 0.25 | 248 |
| vol_regime | 90 | 0.089 | 0.269 | -0.269 | 0.204 | 0.67 | 264 |
| fas_exports | 24 | 0.082 | 0.139 | -0.139 | 0.139 | 0.50 | 287 |
| crop_progress_stage | 24 | 0.081 | 0.232 | -0.232 | 0.232 | 0.50 | 287 |
| nfci_change | 24 | 0.078 | 0.264 | -0.264 | 0.264 | 0.00 | 248 |
| sma200_align | 90 | 0.075 | 0.335 | -0.335 | 0.335 | 0.00 | 264 |
| dxy_chg5d | 120 | 0.075 | 0.200 | -0.200 | 0.200 | 0.50 | 270 |
| aaii_extreme | 12 | 0.074 | 0.090 | -0.090 | 0.090 | 0.75 | 287 |
| positioning_asset_mgr_pct | 48 | 0.070 | 0.161 | -0.161 | 0.161 | 0.50 | 273 |
| shipping_pressure | 18 | 0.068 | 0.118 | -0.118 | 0.118 | 0.33 | 287 |
| momentum_z | 90 | 0.064 | 0.135 | -0.135 | 0.135 | 0.50 | 264 |
| analog_hit_rate | 90 | 0.064 | 0.277 | -0.277 | 0.172 | 0.50 | 288 |
| etf_holdings_change | 12 | 0.061 | 0.087 | -0.087 | 0.087 | 0.50 | 287 |
| cot_euronext_mm_pct | 12 | 0.057 | 0.085 | -0.085 | 0.085 | 1.00 | 286 |
| range_position | 90 | 0.054 | 0.169 | -0.169 | 0.169 | 0.67 | 264 |
| analog_avg_return | 90 | 0.053 | 0.188 | -0.173 | 0.188 | 0.50 | 288 |
| yield_diff_10y | 24 | 0.052 | 0.147 | -0.147 | 0.147 | 0.25 | 297 |
| wasde_s2u_change | 24 | 0.043 | 0.104 | -0.104 | 0.104 | 0.50 | 287 |
| brl_chg5d | 12 | 0.043 | 0.073 | -0.073 | 0.073 | 0.67 | 287 |
| eia_stock_change | 18 | 0.031 | 0.131 | -0.116 | 0.131 | 0.50 | 281 |
| vix_term_ratio | 12 | 0.029 | 0.038 | -0.038 | 0.030 | 0.00 | 287 |
| cecafe_export_change | 6 | 0.012 | 0.015 | -0.015 | 0.015 | 0.50 | 287 |

## Verste monotonisitet (kandidater for vekt-reduksjon)

| Driver | Family | Instrument | Hor | Dir | n | IC | Hit Q1 | Hit Q4 | Mono |
|---|---|---|---:|---|---:|---:|---:|---:|---:|
| yield_diff_10y | macro | USDJPY | 90d | sell | 294 | -0.037 | 11.3% | 13.3% | 0.00 |
| credit_spread_change | risk | ETH | 90d | buy | 211 | -0.247 | 54.3% | 0.0% | 0.00 |
| credit_spread_change | risk | ETH | 60d | sell | 213 | -0.194 | 39.4% | 81.8% | 0.00 |
| credit_spread_change | risk | ETH | 60d | buy | 213 | -0.194 | 53.2% | 18.2% | 0.00 |
| credit_spread_change | risk | ETH | 30d | sell | 215 | -0.134 | 35.1% | 53.8% | 0.00 |
| credit_spread_change | risk | ETH | 30d | buy | 215 | -0.134 | 55.3% | 30.8% | 0.00 |
| credit_spread_change | risk | BTC | 90d | sell | 204 | -0.317 | 26.6% | 100.0% | 0.00 |
| credit_spread_change | risk | BTC | 90d | buy | 204 | -0.317 | 63.8% | 0.0% | 0.00 |
| credit_spread_change | risk | BTC | 60d | sell | 206 | -0.235 | 33.0% | 70.0% | 0.00 |
| credit_spread_change | risk | BTC | 60d | buy | 206 | -0.235 | 59.6% | 10.0% | 0.00 |
| real_yield | macro | Gold | 60d | buy | 288 | -0.354 | 50.7% | 21.3% | 0.00 |
| credit_spread_change | risk | BTC | 30d | buy | 209 | -0.161 | 50.0% | 23.1% | 0.00 |
| real_yield | macro | Gold | 90d | buy | 284 | -0.541 | 65.9% | 10.6% | 0.00 |
| cot_z_score | positioning | USDJPY | 60d | buy | 298 | 0.022 | 25.5% | 18.6% | 0.00 |
| real_yield | macro | Nasdaq | 60d | buy | 288 | 0.003 | 54.9% | 53.2% | 0.00 |
| cot_z_score | positioning | Silver | 90d | buy | 284 | -0.129 | 43.1% | 30.6% | 0.00 |
| cot_z_score | positioning | Silver | 60d | buy | 288 | -0.152 | 45.2% | 36.7% | 0.00 |
| cot_z_score | positioning | Platinum | 90d | buy | 286 | -0.152 | 35.3% | 19.6% | 0.00 |
| cot_z_score | positioning | Platinum | 60d | buy | 288 | -0.114 | 40.8% | 19.6% | 0.00 |
| cot_z_score | positioning | Platinum | 30d | buy | 289 | -0.119 | 36.2% | 19.6% | 0.00 |
| cot_z_score | positioning | NaturalGas | 90d | sell | 286 | -0.117 | 36.8% | 45.1% | 0.00 |
| real_yield | macro | Silver | 60d | buy | 288 | -0.221 | 49.3% | 34.0% | 0.00 |
| credit_spread_change | risk | ETH | 90d | sell | 211 | -0.247 | 33.0% | 88.9% | 0.00 |
| cot_z_score | positioning | NaturalGas | 30d | buy | 291 | 0.014 | 41.1% | 25.0% | 0.00 |
| real_yield | macro | GBPUSD | 90d | buy | 294 | -0.110 | 16.8% | 12.2% | 0.00 |
| real_yield | macro | EURUSD | 90d | buy | 294 | -0.151 | 16.8% | 8.2% | 0.00 |
| drought_monitor | weather | Wheat | 30d | sell | 288 | -0.097 | 30.2% | 40.9% | 0.00 |
| drought_monitor | weather | Soybean | 90d | sell | 284 | -0.065 | 34.1% | 34.9% | 0.00 |
| drought_monitor | weather | Soybean | 60d | sell | 288 | -0.092 | 29.5% | 36.2% | 0.00 |
| drought_monitor | weather | Soybean | 30d | sell | 288 | -0.078 | 25.9% | 36.9% | 0.00 |

## Anbefalinger

Generert som datapunkt for ADR-009 cutover-readiness-audit (session 117).
Konkrete vekt-justeringer vurderes manuelt; tabellene over flagger
kandidater. Drivere med median monotonisitet < 0.4 og median |IC| < 0.05
bør vurderes for vekt-reduksjon eller fjerning. Drivere med median
monotonisitet > 0.7 og |IC| > 0.1 er sterke prediktorer som kan
vekt-økes.
