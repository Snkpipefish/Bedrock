# Kryss-asset-korrelasjons-analyse — 2026-05-01

Forward-looking IC-matrise: alle prediktorer (features +
driver-verdier) vs alle targets (forward_return per instrument ×
horisont). Spearman-korrelasjon, ref_date-aligned, look-ahead-strict.

## Datakilder

- `feature_snapshots`: 587 ref_dates × 45 features
- `driver_observations`: 453,264 rader
- Targets: 66 (instrument × horisont)-kombinasjoner
- Prediktorer: 325
- Min observasjoner per par: 50

## Top-50 sterkeste signaler (forward-looking)

Sortert på |IC|. Positiv IC = prediktor og target stiger sammen
(BUY-egnet for instrumentet hvis target er fwd-return). Negativ IC
= prediktor stiger når target faller (SELL-egnet, eller flipped
BUY-prediksjon).

| # | Predictor | Target | Hor | n | IC |
|---:|---|---|---:|---:|---:|
| 1 | driver.real_yield.AUDUSD | USDJPY | 90d | 52 | +0.756 |
| 2 | driver.real_yield.CrudeOil | Gold | 90d | 227 | -0.641 |
| 3 | price.Coffee | Coffee | 90d | 52 | -0.627 |
| 4 | driver.sma200_align.CrudeOil | Sugar | 90d | 63 | -0.606 |
| 5 | driver.real_yield.Platinum | Gold | 90d | 113 | -0.597 |
| 6 | driver.real_yield.SP500 | Gold | 90d | 142 | -0.573 |
| 7 | driver.real_yield.Nasdaq | Gold | 90d | 142 | -0.573 |
| 8 | driver.real_yield.NaturalGas | Gold | 90d | 142 | -0.573 |
| 9 | cot.mm_net_pct.Sugar | Coffee | 90d | 52 | +0.562 |
| 10 | driver.enso_regime.Coffee | Corn | 90d | 104 | +0.556 |
| 11 | price.AUDUSD | Coffee | 90d | 52 | +0.555 |
| 12 | price.Cotton | Coffee | 90d | 52 | +0.554 |
| 13 | price.Gold | Coffee | 90d | 52 | -0.551 |
| 14 | price.Copper | Coffee | 90d | 52 | -0.544 |
| 15 | driver.real_yield.Silver | Gold | 90d | 284 | -0.541 |
| 16 | driver.real_yield.Gold | Gold | 90d | 284 | -0.541 |
| 17 | cot.mm_net_pct.Copper | Cocoa | 90d | 69 | -0.535 |
| 18 | driver.enso_regime.Coffee | Corn | 60d | 104 | +0.535 |
| 19 | driver.real_yield.AUDUSD | USDJPY | 60d | 52 | +0.534 |
| 20 | driver.vol_regime.Gold | Coffee | 90d | 52 | -0.533 |
| 21 | driver.real_yield.Gold | Coffee | 90d | 52 | +0.515 |
| 22 | driver.real_yield.Silver | Coffee | 90d | 52 | +0.515 |
| 23 | driver.real_yield.CrudeOil | Coffee | 90d | 52 | +0.515 |
| 24 | cot.mm_net_pct.Cotton | Coffee | 90d | 52 | +0.509 |
| 25 | driver.real_yield.CrudeOil | Silver | 90d | 227 | -0.509 |
| 26 | shipping.BDI | Silver | 90d | 139 | -0.504 |
| 27 | price.Nasdaq | Coffee | 90d | 52 | -0.503 |
| 28 | driver.enso_regime.Coffee | Corn | 30d | 104 | +0.502 |
| 29 | price.BTC | SP500 | 90d | 60 | +0.501 |
| 30 | driver.enso_regime.Coffee | Silver | 90d | 52 | +0.499 |
| 31 | price.Cotton | Coffee | 60d | 56 | +0.492 |
| 32 | price.BTC | Nasdaq | 90d | 60 | +0.491 |
| 33 | driver.sma200_align.Platinum | Wheat | 90d | 113 | -0.489 |
| 34 | price.Silver | Coffee | 90d | 52 | -0.486 |
| 35 | price.SP500 | Coffee | 90d | 52 | -0.482 |
| 36 | driver.real_yield.Copper | Copper | 90d | 72 | -0.468 |
| 37 | driver.weather_stress.Coffee | CrudeOil | 90d | 52 | -0.466 |
| 38 | price.AUDUSD | Gold | 90d | 284 | -0.462 |
| 39 | driver.enso_regime.Coffee | CrudeOil | 90d | 52 | +0.461 |
| 40 | driver.real_yield.AUDUSD | USDJPY | 30d | 52 | +0.459 |
| 41 | driver.sma200_align.Gold | Coffee | 90d | 52 | -0.459 |
| 42 | price.USDJPY | Coffee | 90d | 52 | -0.459 |
| 43 | driver.vix_regime.GBPUSD | AUDUSD | 90d | 52 | -0.456 |
| 44 | driver.vix_regime.USDJPY | AUDUSD | 90d | 52 | +0.456 |
| 45 | driver.positioning_mm_pct.CrudeOil | Sugar | 90d | 63 | -0.454 |
| 46 | cot.mm_net_pct.Coffee | Coffee | 90d | 52 | -0.442 |
| 47 | cot.mm_net_pct.Platinum | Coffee | 90d | 52 | +0.441 |
| 48 | driver.vix_regime.USDJPY | AUDUSD | 60d | 52 | +0.440 |
| 49 | driver.vix_regime.GBPUSD | AUDUSD | 60d | 52 | -0.440 |
| 50 | driver.real_yield.CrudeOil | Gold | 60d | 231 | -0.439 |

## Per-prediktor-sammendrag

Hvilke prediktorer er **robuste** (sterke på tvers av mange
targets, ikke bare én):

| Predictor | # targets | # strong (|IC| > 0.1) | Median |IC| | Max |IC| |
|---|---:|---:|---:|---:|
| driver.real_yield.Gold | 42 | 36 | 0.183 | 0.541 |
| driver.real_yield.Silver | 42 | 36 | 0.183 | 0.541 |
| driver.real_yield.CrudeOil | 42 | 33 | 0.157 | 0.641 |
| driver.vix_regime.Platinum | 36 | 32 | 0.214 | 0.429 |
| fred.VIXCLS | 42 | 29 | 0.144 | 0.330 |
| driver.vix_regime.Gold | 42 | 28 | 0.150 | 0.360 |
| driver.vix_regime.Silver | 42 | 28 | 0.150 | 0.360 |
| driver.vix_regime.CrudeOil | 42 | 28 | 0.145 | 0.295 |
| price.BTC | 36 | 27 | 0.175 | 0.501 |
| driver.weather_stress.Cotton | 39 | 27 | 0.151 | 0.415 |
| driver.enso_regime.Cotton | 39 | 26 | 0.165 | 0.350 |
| driver.real_yield.Platinum | 36 | 26 | 0.150 | 0.597 |
| cot.mm_net_pct.Cocoa | 42 | 26 | 0.134 | 0.286 |
| driver.dxy_chg5d.Gold | 42 | 26 | 0.117 | 0.424 |
| driver.dxy_chg5d.Silver | 42 | 26 | 0.117 | 0.424 |
| price.Cocoa | 42 | 25 | 0.127 | 0.375 |
| fred.DGS10 | 42 | 25 | 0.122 | 0.429 |
| cot.mm_net_pct.Soybean | 42 | 25 | 0.122 | 0.366 |
| driver.vix_regime.Nasdaq | 33 | 24 | 0.166 | 0.349 |
| driver.vix_regime.NaturalGas | 33 | 24 | 0.166 | 0.349 |
| driver.vix_regime.SP500 | 33 | 24 | 0.166 | 0.349 |
| driver.sma200_align.SP500 | 33 | 24 | 0.139 | 0.310 |
| price.Brent | 42 | 24 | 0.123 | 0.420 |
| driver.enso_regime.Corn | 36 | 23 | 0.150 | 0.348 |
| fred.T10YIE | 42 | 23 | 0.117 | 0.397 |
| cot.mm_net_pct.Silver | 42 | 23 | 0.113 | 0.346 |
| driver.dxy_chg5d.Platinum | 36 | 22 | 0.132 | 0.296 |
| driver.positioning_mm_pct.Platinum | 36 | 22 | 0.117 | 0.438 |
| price.Soybean | 42 | 22 | 0.107 | 0.382 |
| driver.analog_hit_rate.CrudeOil | 42 | 22 | 0.103 | 0.361 |
| driver.enso_regime.Soybean | 33 | 21 | 0.141 | 0.364 |
| driver.enso_regime.Wheat | 33 | 21 | 0.141 | 0.364 |
| driver.sma200_align.Nasdaq | 33 | 21 | 0.133 | 0.339 |
| driver.sma200_align.Platinum | 36 | 21 | 0.115 | 0.489 |
| price.CrudeOil | 42 | 21 | 0.113 | 0.429 |
| cot.mm_net_pct.Platinum | 42 | 21 | 0.101 | 0.441 |
| driver.analog_hit_rate.Gold | 42 | 21 | 0.089 | 0.370 |
| driver.drought_monitor.Soybean | 33 | 20 | 0.136 | 0.265 |
| driver.drought_monitor.Wheat | 33 | 20 | 0.136 | 0.265 |
| driver.crop_progress_stage.Corn | 36 | 20 | 0.116 | 0.291 |
| driver.cot_z_score.Platinum | 36 | 20 | 0.106 | 0.413 |
| price.GBPUSD | 42 | 20 | 0.099 | 0.374 |
| price.SP500 | 42 | 20 | 0.096 | 0.482 |
| driver.dxy_chg5d.CrudeOil | 42 | 20 | 0.096 | 0.424 |
| driver.analog_avg_return.CrudeOil | 42 | 20 | 0.094 | 0.257 |
| cot.mm_net_pct.Corn | 42 | 20 | 0.087 | 0.339 |
| driver.dxy_chg5d.Soybean | 33 | 19 | 0.121 | 0.285 |
| driver.dxy_chg5d.Wheat | 33 | 19 | 0.121 | 0.285 |
| driver.weather_stress.Corn | 36 | 19 | 0.105 | 0.306 |
| driver.crop_progress_stage.Cotton | 39 | 19 | 0.100 | 0.415 |

## Per-target detalj (top-5 prediktorer)

### AUDUSD 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.range_position.GBPUSD | 52 | -0.373 |
| driver.momentum_z.GBPUSD | 52 | -0.319 |
| driver.vix_regime.USDJPY | 52 | +0.311 |
| driver.vix_regime.GBPUSD | 52 | -0.311 |
| driver.vix_regime.AUDUSD | 299 | -0.289 |

### AUDUSD 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.GBPUSD | 52 | -0.440 |
| driver.vix_regime.USDJPY | 52 | +0.440 |
| driver.range_position.GBPUSD | 52 | -0.358 |
| driver.momentum_z.GBPUSD | 52 | -0.308 |
| driver.vix_regime.AUDUSD | 298 | -0.282 |

### AUDUSD 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.GBPUSD | 52 | -0.456 |
| driver.vix_regime.USDJPY | 52 | +0.456 |
| driver.vix_regime.AUDUSD | 294 | -0.322 |
| driver.analog_hit_rate.GBPUSD | 52 | -0.293 |
| driver.cot_z_score.GBPUSD | 52 | +0.248 |

### BTC 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.credit_spread_change.BTC | 209 | -0.161 |
| driver.cot_z_score.BTC | 209 | -0.154 |
| driver.nfci_change.BTC | 209 | -0.146 |
| driver.range_position.BTC | 209 | +0.113 |
| driver.momentum_z.BTC | 209 | +0.113 |

### BTC 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.credit_spread_change.BTC | 206 | -0.235 |
| driver.nfci_change.BTC | 206 | -0.195 |
| driver.vol_regime.BTC | 206 | +0.145 |
| driver.cot_z_score.BTC | 206 | -0.129 |
| driver.sma200_align.BTC | 206 | +0.072 |

### BTC 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.credit_spread_change.BTC | 204 | -0.317 |
| driver.nfci_change.BTC | 204 | -0.264 |
| driver.vol_regime.BTC | 204 | +0.164 |
| driver.range_position.BTC | 204 | +0.137 |
| driver.cot_z_score.BTC | 204 | -0.131 |

### Brent 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.vol_regime.Brent | 287 | +0.133 |
| driver.vix_regime.Brent | 287 | +0.130 |
| driver.range_position.Brent | 287 | +0.121 |
| driver.dxy_chg5d.Brent | 287 | +0.108 |
| driver.momentum_z.Brent | 287 | +0.108 |

### Brent 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.vol_regime.Brent | 287 | +0.184 |
| driver.vix_regime.Brent | 287 | +0.147 |
| driver.real_yield.Brent | 287 | +0.128 |
| driver.cot_ice_mm_pct.Brent | 287 | -0.121 |
| driver.cot_z_score.Brent | 287 | -0.079 |

### Brent 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.Brent | 283 | +0.259 |
| driver.real_yield.Brent | 283 | +0.192 |
| driver.cot_ice_mm_pct.Brent | 283 | -0.170 |
| driver.dxy_chg5d.Brent | 283 | +0.144 |
| driver.vol_regime.Brent | 283 | +0.111 |

### Cocoa 30d

| Predictor | n | IC |
|---|---:|---:|
| cot.mm_net_pct.Copper | 73 | -0.347 |
| price.Cocoa | 162 | -0.261 |
| driver.enso_regime.Coffee | 123 | -0.195 |
| driver.momentum_z.CrudeOil | 105 | -0.193 |
| price.Platinum | 162 | -0.193 |

### Cocoa 60d

| Predictor | n | IC |
|---|---:|---:|
| cot.mm_net_pct.Copper | 73 | -0.421 |
| price.Sugar | 161 | +0.274 |
| price.GBPUSD | 161 | -0.255 |
| driver.enso_regime.Coffee | 123 | -0.253 |
| cot.mm_net_pct.Sugar | 161 | +0.228 |

### Cocoa 90d

| Predictor | n | IC |
|---|---:|---:|
| cot.mm_net_pct.Copper | 69 | -0.535 |
| price.GBPUSD | 157 | -0.350 |
| price.Sugar | 157 | +0.345 |
| cot.mm_net_pct.Sugar | 157 | +0.319 |
| driver.crop_progress_stage.Cotton | 169 | +0.317 |

### Coffee 30d

| Predictor | n | IC |
|---|---:|---:|
| price.Cotton | 56 | +0.391 |
| price.Coffee | 56 | -0.390 |
| price.Copper | 56 | -0.385 |
| driver.weather_stress.Sugar | 82 | -0.379 |
| cot.mm_net_pct.Sugar | 56 | +0.365 |

### Coffee 60d

| Predictor | n | IC |
|---|---:|---:|
| price.Cotton | 56 | +0.492 |
| cot.mm_net_pct.Sugar | 56 | +0.435 |
| price.Coffee | 56 | -0.433 |
| driver.weather_stress.Sugar | 82 | -0.430 |
| price.Copper | 56 | -0.401 |

### Coffee 90d

| Predictor | n | IC |
|---|---:|---:|
| price.Coffee | 52 | -0.627 |
| cot.mm_net_pct.Sugar | 52 | +0.562 |
| price.AUDUSD | 52 | +0.555 |
| price.Cotton | 52 | +0.554 |
| price.Gold | 52 | -0.551 |

### Copper 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.Copper | 75 | -0.304 |
| driver.positioning_mm_pct.Copper | 75 | +0.228 |
| driver.cot_z_score.Copper | 75 | +0.210 |
| driver.sma200_align.Copper | 75 | -0.158 |
| driver.vol_regime.Copper | 75 | -0.124 |

### Copper 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.Copper | 73 | -0.404 |
| driver.sma200_align.Copper | 73 | -0.314 |
| driver.positioning_mm_pct.Copper | 73 | +0.179 |
| driver.vol_regime.Copper | 73 | -0.147 |
| driver.range_position.Copper | 73 | -0.132 |

### Copper 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.Copper | 72 | -0.468 |
| driver.sma200_align.Copper | 72 | -0.335 |
| driver.vol_regime.Copper | 72 | -0.232 |
| driver.positioning_mm_pct.Copper | 72 | +0.195 |
| driver.range_position.Copper | 72 | -0.161 |

### Corn 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.enso_regime.Coffee | 104 | +0.502 |
| driver.weather_stress.Wheat | 158 | -0.318 |
| driver.weather_stress.Cotton | 93 | -0.312 |
| price.Corn | 142 | -0.284 |
| price.Soybean | 142 | -0.251 |

### Corn 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.enso_regime.Coffee | 104 | +0.535 |
| driver.weather_stress.Wheat | 158 | -0.330 |
| driver.weather_stress.Cotton | 93 | -0.309 |
| price.Corn | 142 | -0.303 |
| driver.enso_regime.Cotton | 93 | +0.301 |

### Corn 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.enso_regime.Coffee | 104 | +0.556 |
| price.Corn | 142 | -0.425 |
| price.Soybean | 142 | -0.368 |
| driver.analog_hit_rate.CrudeOil | 158 | -0.361 |
| driver.weather_stress.Wheat | 158 | -0.358 |

### Cotton 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.eia_stock_change.NaturalGas | 93 | +0.363 |
| driver.enso_regime.Cocoa | 169 | +0.353 |
| driver.analog_hit_rate.Gold | 198 | -0.343 |
| driver.analog_avg_return.Gold | 198 | -0.322 |
| driver.enso_regime.Sugar | 210 | +0.288 |

### Cotton 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.enso_regime.Cocoa | 169 | +0.378 |
| driver.analog_hit_rate.Gold | 198 | -0.370 |
| driver.analog_avg_return.Gold | 198 | -0.365 |
| price.Brent | 198 | -0.327 |
| driver.enso_regime.Sugar | 210 | +0.321 |

### Cotton 90d

| Predictor | n | IC |
|---|---:|---:|
| price.CrudeOil | 198 | -0.429 |
| price.Brent | 198 | -0.420 |
| driver.enso_regime.Sugar | 206 | +0.395 |
| driver.enso_regime.Cocoa | 169 | +0.384 |
| driver.analog_hit_rate.Gold | 198 | -0.358 |

### CrudeOil 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.seasonal_stage.Coffee | 56 | -0.429 |
| driver.conab_yoy.Coffee | 56 | +0.390 |
| driver.analog_hit_rate.Coffee | 56 | +0.362 |
| driver.weather_stress.Coffee | 56 | -0.341 |
| driver.analog_avg_return.Coffee | 56 | +0.332 |

### CrudeOil 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.seasonal_stage.Coffee | 56 | -0.429 |
| driver.conab_yoy.Coffee | 56 | +0.390 |
| driver.analog_hit_rate.Coffee | 56 | +0.383 |
| driver.weather_stress.Coffee | 56 | -0.357 |
| driver.analog_avg_return.Coffee | 56 | +0.339 |

### CrudeOil 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.weather_stress.Coffee | 52 | -0.466 |
| driver.enso_regime.Coffee | 52 | +0.461 |
| driver.weather_stress.Sugar | 63 | -0.429 |
| driver.vix_regime.Platinum | 113 | +0.390 |
| driver.enso_regime.Soybean | 190 | +0.364 |

### ETH 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.ETH | 215 | -0.201 |
| driver.credit_spread_change.ETH | 215 | -0.134 |
| driver.net_fed_liq_change.ETH | 215 | +0.127 |
| driver.nfci_change.ETH | 215 | -0.124 |
| driver.cot_z_score.ETH | 215 | -0.119 |

### ETH 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.ETH | 213 | -0.262 |
| driver.credit_spread_change.ETH | 213 | -0.194 |
| driver.nfci_change.ETH | 213 | -0.189 |
| driver.net_fed_liq_change.ETH | 213 | +0.175 |
| driver.cot_z_score.ETH | 213 | -0.146 |

### ETH 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.ETH | 211 | -0.297 |
| driver.credit_spread_change.ETH | 211 | -0.247 |
| driver.nfci_change.ETH | 211 | -0.213 |
| driver.net_fed_liq_change.ETH | 211 | +0.202 |
| driver.cot_z_score.ETH | 211 | -0.200 |

### EURUSD 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.cot_z_score.EURUSD | 299 | +0.238 |
| driver.positioning_lev_funds_pct.EURUSD | 299 | +0.173 |
| driver.positioning_asset_mgr_pct.EURUSD | 299 | +0.125 |
| driver.vol_regime.USDJPY | 268 | -0.125 |
| driver.dxy_chg5d.EURUSD | 299 | +0.120 |

### EURUSD 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.cot_z_score.EURUSD | 298 | +0.270 |
| driver.positioning_lev_funds_pct.EURUSD | 298 | +0.157 |
| driver.real_yield.GBPUSD | 267 | -0.134 |
| driver.real_yield.USDJPY | 267 | +0.132 |
| driver.positioning_asset_mgr_pct.EURUSD | 298 | +0.123 |

### EURUSD 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.cot_z_score.EURUSD | 294 | +0.303 |
| driver.real_yield.USDJPY | 263 | +0.201 |
| driver.real_yield.GBPUSD | 263 | -0.196 |
| driver.positioning_lev_funds_pct.EURUSD | 294 | +0.175 |
| driver.positioning_lev_funds_pct.GBPUSD | 263 | +0.159 |

### GBPUSD 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.momentum_z.USDJPY | 299 | -0.143 |
| driver.positioning_lev_funds_pct.EURUSD | 268 | +0.137 |
| driver.analog_avg_return.EURUSD | 268 | +0.118 |
| driver.sma200_align.USDJPY | 299 | -0.114 |
| driver.positioning_asset_mgr_pct.USDJPY | 299 | +0.111 |

### GBPUSD 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.positioning_lev_funds_pct.EURUSD | 267 | +0.176 |
| driver.cot_z_score.EURUSD | 267 | +0.148 |
| driver.positioning_asset_mgr_pct.USDJPY | 298 | +0.146 |
| driver.sma200_align.EURUSD | 267 | +0.131 |
| driver.vix_regime.AUDUSD | 52 | -0.130 |

### GBPUSD 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.sma200_align.AUDUSD | 52 | -0.349 |
| driver.cot_z_score.AUDUSD | 52 | -0.311 |
| driver.vix_regime.AUDUSD | 52 | -0.283 |
| driver.vol_regime.AUDUSD | 52 | +0.230 |
| driver.real_yield.AUDUSD | 52 | -0.226 |

### Gold 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.CrudeOil | 231 | -0.379 |
| driver.real_yield.Nasdaq | 142 | -0.372 |
| driver.real_yield.NaturalGas | 142 | -0.372 |
| driver.real_yield.SP500 | 142 | -0.372 |
| driver.real_yield.Platinum | 113 | -0.338 |

### Gold 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.CrudeOil | 231 | -0.439 |
| driver.real_yield.Nasdaq | 142 | -0.403 |
| driver.real_yield.NaturalGas | 142 | -0.403 |
| driver.real_yield.SP500 | 142 | -0.403 |
| driver.real_yield.Platinum | 113 | -0.395 |

### Gold 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.CrudeOil | 227 | -0.641 |
| driver.real_yield.Platinum | 113 | -0.597 |
| driver.real_yield.Nasdaq | 142 | -0.573 |
| driver.real_yield.SP500 | 142 | -0.573 |
| driver.real_yield.NaturalGas | 142 | -0.573 |

### Nasdaq 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.Platinum | 113 | +0.230 |
| price.Cocoa | 142 | -0.220 |
| driver.vix_regime.SP500 | 288 | -0.195 |
| driver.vix_regime.NaturalGas | 288 | +0.195 |
| driver.vix_regime.Nasdaq | 288 | -0.195 |

### Nasdaq 60d

| Predictor | n | IC |
|---|---:|---:|
| price.Cocoa | 142 | -0.294 |
| price.BTC | 60 | +0.283 |
| driver.enso_regime.Corn | 158 | +0.256 |
| driver.vix_regime.Platinum | 113 | +0.238 |
| driver.enso_regime.Cotton | 93 | +0.217 |

### Nasdaq 90d

| Predictor | n | IC |
|---|---:|---:|
| price.BTC | 60 | +0.491 |
| price.Cocoa | 142 | -0.353 |
| driver.enso_regime.Corn | 158 | +0.322 |
| driver.enso_regime.Cotton | 93 | +0.260 |
| driver.cot_z_score.Nasdaq | 284 | -0.252 |

### NaturalGas 30d

| Predictor | n | IC |
|---|---:|---:|
| price.NaturalGas | 144 | -0.286 |
| driver.wasde_s2u_change.Wheat | 247 | -0.278 |
| driver.vix_regime.Platinum | 113 | -0.261 |
| driver.vix_regime.Silver | 142 | -0.247 |
| driver.vix_regime.Gold | 142 | -0.247 |

### NaturalGas 60d

| Predictor | n | IC |
|---|---:|---:|
| price.NaturalGas | 142 | -0.310 |
| driver.vix_regime.Platinum | 113 | -0.310 |
| driver.cot_z_score.Platinum | 113 | +0.290 |
| driver.vol_regime.NaturalGas | 288 | -0.269 |
| cot.mm_net_pct.Soybean | 142 | +0.260 |

### NaturalGas 90d

| Predictor | n | IC |
|---|---:|---:|
| price.NaturalGas | 142 | -0.362 |
| cot.mm_net_pct.Soybean | 142 | +0.328 |
| driver.cot_z_score.Platinum | 113 | +0.319 |
| driver.cot_z_score.Silver | 142 | +0.298 |
| cot.mm_net_pct.Silver | 142 | +0.298 |

### Platinum 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.weather_stress.Cotton | 122 | -0.201 |
| driver.analog_avg_return.Cotton | 122 | +0.198 |
| driver.cot_z_score.NaturalGas | 113 | +0.196 |
| driver.vol_regime.NaturalGas | 113 | +0.177 |
| driver.brl_chg5d.Coffee | 120 | +0.172 |

### Platinum 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.vol_regime.NaturalGas | 113 | +0.275 |
| driver.positioning_mm_pct.NaturalGas | 113 | +0.271 |
| driver.sma200_align.NaturalGas | 113 | +0.247 |
| driver.cot_z_score.NaturalGas | 113 | +0.246 |
| driver.vix_term_ratio.SP500 | 113 | +0.235 |

### Platinum 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.positioning_mm_pct.NaturalGas | 113 | +0.345 |
| driver.vix_term_ratio.SP500 | 113 | +0.307 |
| driver.vix_term_ratio.Nasdaq | 113 | +0.307 |
| driver.cot_z_score.NaturalGas | 113 | +0.302 |
| driver.enso_regime.Cotton | 122 | +0.292 |

### SP500 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.Platinum | 113 | +0.268 |
| driver.vix_regime.SP500 | 288 | -0.262 |
| driver.vix_regime.NaturalGas | 288 | +0.262 |
| driver.vix_regime.Nasdaq | 288 | -0.262 |
| price.Cocoa | 142 | -0.255 |

### SP500 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.Platinum | 113 | +0.332 |
| price.Cocoa | 142 | -0.313 |
| driver.enso_regime.Cotton | 93 | +0.307 |
| driver.enso_regime.Corn | 158 | +0.305 |
| driver.vix_regime.SP500 | 288 | -0.279 |

### SP500 90d

| Predictor | n | IC |
|---|---:|---:|
| price.BTC | 60 | +0.501 |
| price.Cocoa | 142 | -0.371 |
| driver.enso_regime.Cotton | 93 | +0.350 |
| driver.enso_regime.Corn | 158 | +0.332 |
| driver.vix_regime.CrudeOil | 182 | +0.295 |

### Silver 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.conab_yoy.Coffee | 56 | -0.346 |
| driver.real_yield.SP500 | 142 | -0.274 |
| driver.real_yield.NaturalGas | 142 | -0.274 |
| driver.real_yield.Nasdaq | 142 | -0.274 |
| driver.wasde_s2u_change.Wheat | 154 | +0.267 |

### Silver 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.conab_yoy.Coffee | 56 | -0.366 |
| driver.enso_regime.Coffee | 56 | +0.334 |
| shipping.BDI | 143 | -0.322 |
| driver.real_yield.CrudeOil | 231 | -0.319 |
| driver.wasde_s2u_change.Wheat | 154 | +0.306 |

### Silver 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.CrudeOil | 227 | -0.509 |
| shipping.BDI | 139 | -0.504 |
| driver.enso_regime.Coffee | 52 | +0.499 |
| driver.real_yield.Nasdaq | 142 | -0.411 |
| driver.real_yield.SP500 | 142 | -0.411 |

### Soybean 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.weather_stress.Cotton | 122 | -0.377 |
| driver.weather_stress.Corn | 158 | -0.296 |
| driver.weather_stress.Wheat | 288 | -0.244 |
| driver.dxy_chg5d.Platinum | 113 | +0.226 |
| fred.VIXCLS | 154 | +0.215 |

### Soybean 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.weather_stress.Cotton | 122 | -0.375 |
| driver.weather_stress.Wheat | 288 | -0.277 |
| driver.weather_stress.Corn | 158 | -0.259 |
| driver.enso_regime.Cotton | 122 | +0.254 |
| cot.mm_net_pct.Cocoa | 154 | -0.253 |

### Soybean 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.Platinum | 113 | +0.429 |
| driver.weather_stress.Cotton | 122 | -0.415 |
| price.Soybean | 150 | -0.382 |
| driver.vix_regime.Gold | 150 | +0.360 |
| driver.vix_regime.Silver | 150 | +0.360 |

### Sugar 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.vix_regime.CrudeOil | 63 | +0.242 |
| driver.enso_regime.Coffee | 82 | +0.227 |
| driver.analog_hit_rate.CrudeOil | 63 | -0.215 |
| driver.positioning_mm_pct.Gold | 120 | -0.206 |
| cot.mm_net_pct.Soybean | 120 | +0.205 |

### Sugar 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.sma200_align.CrudeOil | 63 | -0.290 |
| driver.vix_regime.CrudeOil | 63 | +0.245 |
| driver.positioning_mm_pct.Gold | 120 | -0.234 |
| driver.enso_regime.Coffee | 82 | +0.221 |
| driver.brl_chg5d.Coffee | 82 | +0.199 |

### Sugar 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.sma200_align.CrudeOil | 63 | -0.606 |
| driver.positioning_mm_pct.CrudeOil | 63 | -0.454 |
| driver.cot_z_score.CrudeOil | 63 | -0.408 |
| fred.VIXCLS | 120 | +0.330 |
| driver.vix_regime.Silver | 120 | +0.328 |

### USDJPY 30d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.AUDUSD | 52 | +0.459 |
| driver.analog_avg_return.AUDUSD | 52 | +0.182 |
| driver.analog_hit_rate.GBPUSD | 299 | +0.169 |
| driver.analog_hit_rate.AUDUSD | 52 | +0.162 |
| driver.real_yield.GBPUSD | 299 | +0.160 |

### USDJPY 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.AUDUSD | 52 | +0.534 |
| driver.momentum_z.AUDUSD | 52 | +0.208 |
| driver.vix_regime.AUDUSD | 52 | +0.202 |
| driver.analog_hit_rate.GBPUSD | 298 | +0.189 |
| driver.vol_regime.AUDUSD | 52 | -0.188 |

### USDJPY 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.real_yield.AUDUSD | 52 | +0.756 |
| driver.real_yield.USDJPY | 294 | -0.271 |
| driver.real_yield.GBPUSD | 294 | +0.270 |
| driver.real_yield.EURUSD | 263 | +0.223 |
| driver.analog_hit_rate.AUDUSD | 52 | +0.221 |

### Wheat 30d

| Predictor | n | IC |
|---|---:|---:|
| price.Wheat | 154 | -0.257 |
| cot.mm_net_pct.Corn | 154 | -0.257 |
| price.Corn | 154 | -0.237 |
| driver.positioning_mm_pct.Platinum | 113 | -0.219 |
| price.Soybean | 154 | -0.215 |

### Wheat 60d

| Predictor | n | IC |
|---|---:|---:|
| driver.positioning_mm_pct.Platinum | 113 | -0.337 |
| driver.cot_z_score.Platinum | 113 | -0.316 |
| cot.mm_net_pct.Corn | 154 | -0.298 |
| price.Wheat | 154 | -0.296 |
| driver.cot_z_score.Gold | 154 | -0.293 |

### Wheat 90d

| Predictor | n | IC |
|---|---:|---:|
| driver.sma200_align.Platinum | 113 | -0.489 |
| driver.positioning_mm_pct.Platinum | 113 | -0.438 |
| driver.cot_z_score.Platinum | 113 | -0.413 |
| price.BTC | 68 | +0.389 |
| price.Wheat | 150 | -0.375 |


## Tolking

- |IC| > 0.10: signifikant prediksjon (sannsynligvis ikke støy)
- |IC| > 0.20: sterk prediksjon — vurder for scoring-vekt
- |IC| < 0.05: trolig støy — vurder vekt-reduksjon

**Forward-looking validering:** alle target-radioer er fwd-return
MÅLT ETTER ref_date. Prediktor-verdier er kjent PÅ ref_date.
Ingen look-ahead bias. Korrelasjon her er prediksjonskraft, ikke
samtidighet.
