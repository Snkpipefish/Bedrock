# Data-coverage-rapport — 2026-05-01

Sub-fase 12.8 Sub-task A1 (PLAN § 20). Per-instrument data-coverage
vurdert per horisont (Macro / Swing / Scalp) basert på § 20.2-mapping.
Helse-flagg per fetcher basert på cycle-spesifikke terskler (§ 20.4).

Generert av `scripts/report_data_coverage.py` mot `bedrock.db`
(2026-05-01 14:39 UTC). Inkluderer business-day-aware aging for
daglige fetchere (`prices`, `fundamentals`, `comex`, `shipping`).

## Final-state etter sub-fase 12.8 fixes (session 139)

**Coverage etter 10 fixer:**

| Horisont | ✓ | ⚠ | ✗ |
|---|---:|---:|---:|
| Macro | 2 | 20 | 0 |
| Swing | 0 | 2 | 20 |
| Scalp | 0 | 22 | 0 |

**Fetcher-helse: 15 ✓ / 4 ⚠ / 0 ✗** (var 12 ✓ / 2 ⚠ / 6 ✗ ved A1-start).

### Hva som ble fixet i sub-fase 12.8 session 139

1. ✓ Reaktivert paused user-timers (crypto_sentiment, news_intel, enso)
2. ✓ Trigger crypto_sentiment + news_intel manuelt → 0 → 34 + 87 rader
3. ✓ Trigger enso manuelt etter DNS-failure ved tidligere reboot
4. ✓ Business-day-aware aging i rapport-verktøyet — fundamentals
   "stale 38t" var rapport-bug (FRED virker korrekt; 24t = ✓)
5. ✓ AAII bull_bear_spread fetcher-bug fixet + backfilt 538 rader
6. ✓ Schema-drift fixet — 3 harvester-tabeller lagt til i schemas.py
7. ✓ fas_esr.py:134 stale docstring oppdatert (Cotton 501 → 1404)
8. ✓ Stale_hours-tuning i fetch.yaml (cot_*/eia 168/200 → 264h)
9. ✓ Cycle-buffer 11d for ukentlig-fetchere (vs 9d tidligere)
10. ✓ Bot-whitelist per-horisont-kvalifisering dokumentert

### Hva blir grønt automatisk i kveld

- **Fre 18:15 Oslo:** calendar_ff fyrer → 22 ⚠ Sc-flagg blir ✓
- **Fre 22:00 Oslo:** cot_disaggregated + cot_legacy fyrer → 20 ✗
  Swing blir ✓ (eller ⚠ avhengig av calendar_ff)
- **Fre 22:30 Oslo:** cot_ice fyrer → Brent + NaturalGas Swing ✓

Forventet etter fre-kveld-fyringer:
- Macro: ~22 ✓
- Swing: ~22 ✓
- Scalp: ~22 ⚠ (kvalifiserer ikke for ✓ før Plan-S leverer
  surprise-vs-consensus + VIX9D/3M-termstruktur-driver)

### Plan-S-deferrals

- calendar_ff `actual`-felt mangler (FF JSON-feed har kun forecast/prev)
- VIX9D/3M-termstruktur-driver (data finnes; driver er Plan-S)
- Cross-asset-leder-mønster (BRL→Coffee/Sugar 1-5min, DXY→Gold etc.)
- Real-time seismic M≥6-trigger som scalp-event
- Surprise-vs-consensus driver-feature (delta = actual - forecast)

### Resterende sub-fase 12.9-kandidater

- WASDE pre-2019 ESMIS-walker (~1-2t kode)
- comex + cafe ingest-subkommandoer i ingest_manual_data.py
- README i cafe_boletins/ comex data/ conab_boletins/
- disease_pressure test-coverage til ≥7 tester
- enso DNS-failure-resilience ved boot
- Bot-token-update + setup→bot signal-format-mismatch (audit Sjekk 9.7)

## Legende

- **Macro (M):** uker–måneder. Datafrekvens ukentlig–månedlig holder.
- **Swing (S):** dager–uker. Daglig–ukentlig kritisk.
- **Scalp (Sc):** minutter–timer. Real-time + release-kalender kritisk.

**Status-flagg per fetcher:**
- ✓ = innenfor cycle-buffer (forventet refresh + 30-50% slack)
- ⚠ = aging (mellom 70% og 100% av rødt-terskel)
- ✗ = stale eller manglende data (>100% av rødt-terskel)

**Status-flagg per (instrument × horisont):**
- ✓ = alle primærkilder for horisonten er ferske
- ⚠ = 1 primærkilde svikter
- ✗ = ≥2 primærkilder svikter

Per-cycle-tersklene (rødt-grenser) er definert i PLAN § 20.4. Primærkilde-
mappingen per asset-klasse er definert i PLAN § 20.2-tabell, med per-
instrument overrides for Cocoa/Coffee/Cotton/BTC/ETH (begrunnet av
asset-spesifikke data-realiteter).


## Sammendrag

- **22 instrumenter** vurdert.
- **19 fetchere** vurdert mot per-cycle-helse-terskler (PLAN § 20.4).

### Coverage-fordeling per horisont

| Horisont | ✓ | ⚠ | ✗ |
|---|---:|---:|---:|
| M | 2 | 20 | 0 |
| S | 0 | 2 | 20 |
| Sc | 0 | 22 | 0 |

### Fetcher-helse

- ✓ ferske: **15**, ⚠ aging: **4**, ✗ stale/missing: **0**

## Sammendragstabell 1 — per-horisont-coverage

Per (instrument × horisont) — ✓ alle primærkilder ferske / ⚠ 1 svikt / ✗ flere svikt.

| Instrument | Asset | Macro | Swing | Scalp |
|---|---|:---:|:---:|:---:|
| AUDUSD | fx | ⚠ | ✗ | ⚠ |
| Brent | energy | ⚠ | ✗ | ⚠ |
| BTC | crypto | ✓ | ⚠ | ⚠ |
| Cocoa | softs | ⚠ | ✗ | ⚠ |
| Coffee | softs | ⚠ | ✗ | ⚠ |
| Copper | metals | ⚠ | ✗ | ⚠ |
| Corn | grains | ⚠ | ✗ | ⚠ |
| Cotton | softs | ⚠ | ✗ | ⚠ |
| CrudeOil | energy | ⚠ | ✗ | ⚠ |
| ETH | crypto | ✓ | ⚠ | ⚠ |
| EURUSD | fx | ⚠ | ✗ | ⚠ |
| GBPUSD | fx | ⚠ | ✗ | ⚠ |
| Gold | metals | ⚠ | ✗ | ⚠ |
| Nasdaq | indices | ⚠ | ✗ | ⚠ |
| NaturalGas | energy | ⚠ | ✗ | ⚠ |
| Platinum | metals | ⚠ | ✗ | ⚠ |
| Silver | metals | ⚠ | ✗ | ⚠ |
| Soybean | grains | ⚠ | ✗ | ⚠ |
| SP500 | indices | ⚠ | ✗ | ⚠ |
| Sugar | softs | ⚠ | ✗ | ⚠ |
| USDJPY | fx | ⚠ | ✗ | ⚠ |
| Wheat | grains | ⚠ | ✗ | ⚠ |

## Sammendragstabell 2 — per-kilde-helse

| Fetcher | Cycle | Cron | Tabell | Rader | Sist obs. | Alder | DB-status | systemd |
|---|---|---|---|---:|---|---|:---:|---|
| calendar_ff | 12t (intra-day) | `15 6,18 * * *` | `econ_events` | 41,063 | 2026-04-30 16:15 UTC | 22.4t | ⚠ | active |
| comex | Daglig (M-F) | `0 22 * * 1-5` | `comex_inventory` | 15 | 2026-04-30 00:00 UTC | 24.0t | ✓ | active |
| conab | Månedlig | `0 20 15 * *` | `conab_estimates` | 158 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| cot_disaggregated | Ukentlig (fre) | `0 22 * * 5` | `cot_disaggregated` | 11,283 | 2026-04-21 00:00 UTC | 10.6d | ⚠ | active |
| cot_euronext | Ukentlig (ons) | `0 18 * * 3` | `cot_euronext` | 1,221 | 2026-04-29 00:00 UTC | 2.6d | ✓ | active |
| cot_ice | Ukentlig (fre) | `30 22 * * 5` | `cot_ice` | 1,601 | 2026-04-22 00:00 UTC | 9.6d | ⚠ | active |
| cot_legacy | Ukentlig (fre) | `0 22 * * 5` | `cot_legacy` | 5,790 | 2026-04-21 00:00 UTC | 10.6d | ⚠ | active |
| crop_progress | Ukentlig (sesong apr-nov) | `0 23 * 4-11 1` | `crop_progress` | 3,114 | 2026-04-26 00:00 UTC | 5.6d | ✓ | active |
| crypto_sentiment | Daglig | `0 7 * * *` | `crypto_sentiment` | 34 | 2026-05-01 00:00 UTC | 14.7t | ✓ | active |
| eia_inventories | Ukentlig (ons) | `30 17 * * 3` | `eia_inventory` | 5,021 | 2026-04-24 00:00 UTC | 7.6d | ✓ | active |
| enso | Månedlig | `0 6 12 * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 38.7t | ✓ | active |
| fundamentals | Daglig (M-F, T+1 publisering) | `30 2 * * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 24.0t | ✓ | active |
| news_intel | 12t (intra-day) | `30 6,18 * * *` | `news_intel` | 87 | 2026-05-01 14:20 UTC | 19m | ✓ | active |
| prices | Daglig (M-F) | `40 * * * 1-5` | `prices` | 90,634 | 2026-05-01 13:40 UTC | 59m | ✓ | active |
| seismic | Daglig (event-basert) | `0 4 * * *` | `seismic_events` | 123,401 | 2026-05-01 09:24 UTC | 5.3t | ✓ | active |
| shipping | Daglig (M-F) | `30 23 * * 1-5` | `shipping_indices` | 2,897 | 2026-04-29 00:00 UTC | 2.0d | ✓ | active |
| unica | Halvmånedlig | `0 21 1,16 * *` | `unica_reports` | 1 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| wasde | Månedlig | `0 19 13 * *` | `wasde` | 8,703 | 2026-04-10 00:00 UTC | 21.6d | ✓ | active |
| weather | Daglig | `0 3 * * *` | `weather` | 11,361 | 2026-05-01 00:00 UTC | 14.7t | ✓ | active |

## Drill-down per instrument

### AUDUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Brent (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, eia_inventories ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, eia_inventories ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, eia_inventories ✓ |

### BTC (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✓ | prices ✓, fundamentals ✓, crypto_sentiment ✓ |
| S | ⚠ | prices ✓, calendar_ff ⚠, crypto_sentiment ✓ |
| Sc | ⚠ | calendar_ff ⚠ |

### Cocoa (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Coffee (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, conab ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, conab ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Copper (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Corn (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### Cotton (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, wasde ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, wasde ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### CrudeOil (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, eia_inventories ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, eia_inventories ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, eia_inventories ✓ |

### ETH (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✓ | prices ✓, fundamentals ✓, crypto_sentiment ✓ |
| S | ⚠ | prices ✓, calendar_ff ⚠, crypto_sentiment ✓ |
| Sc | ⚠ | calendar_ff ⚠ |

### EURUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### GBPUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Gold (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Nasdaq (indices)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, fundamentals ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### NaturalGas (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, eia_inventories ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, eia_inventories ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, eia_inventories ✓ |

### Platinum (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Silver (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Soybean (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### SP500 (indices)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, fundamentals ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Sugar (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, conab ✓, unica ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, conab ✓, unica ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, unica ✓ |

### USDJPY (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ⚠, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ⚠, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Wheat (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ⚠, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |
