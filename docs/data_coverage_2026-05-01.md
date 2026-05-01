# Data-coverage-rapport — 2026-05-01

Sub-fase 12.8 Sub-task A1 (PLAN § 20). Per-instrument data-coverage
vurdert per horisont (Macro / Swing / Scalp) basert på § 20.2-mapping.
Helse-flagg per fetcher basert på cycle-spesifikke terskler (§ 20.4).

Generert av `scripts/report_data_coverage.py` mot `bedrock.db`
(2026-05-01 14:06 UTC).

## Key findings (Sub-task A1 → A2-input)

**0/22 instrumenter har full coverage på noen horisont.** Pipelinen er
strukturelt rødt grunnet flere uavhengige fetcher-issues. Sortert
etter blast-radius:

1. **`fundamentals` (FRED) flagget stale** (38t alder, terskel 36t) —
   påvirker MAKRO for **alle** 22 instrumenter siden DGS10/T10YIE/
   DTWEXBGS/VIXCLS er obligatoriske inputs. Fetcheren ble flagget OK
   på systemd ("active") men siste rad er fra 30. apr 00:00 UTC. Cron
   fyrer daglig 02:30 UTC, så 1. mai-rad burde vært inne. Sjansen er
   at FRED-fetcher silent-failer ved API-key-issue eller series-fetch-
   feil. Anbefalt A2-fix: hard-fail-policy (per § 20.6 sub-task B,
   men kan flyttes til A2 hvis kritisk).
2. **`cot_disaggregated` + `cot_legacy` + `cot_ice` stale 10.6d**
   (terskel 9d). Disse fyrer fredager 22:00 — siste fyring fre 24.
   apr OK; fre 1. mai (i kveld) er kommende. Forventet rødt-flagg
   fredag morgen er normalt — buffer kan utvides til 12d for å unngå
   falsk positiv. Sub-task B-fix.
3. **`crypto_sentiment` + `news_intel` 0 rader** — fetcher kjører
   ("active" på systemd) men skriver ingen data. Sjekk fetcher-loggen
   for silent-fail; manuell bekreftelse om endpoint endret.
4. **`eia_inventories` ⚠ 7.6d** — siste rad 24. apr, men ons 29.
   apr-fyring burde gitt nye rader. Sjekk smart-skip-logikk eller
   EIA-pause i week 18 (ukentlig holiday-mønster).
5. **`enso` på user-systemd har "exit-code"-status** — én av to
   failed services som er kjent. Diagnose i sub-task B.
6. **`calendar_ff` aging 21.8t** — fyrte 30. apr 16:15 UTC, neste
   18:15 i dag. Marginalt utenfor buffer. Sub-task B kan stramme
   stale_hours hvis vi vil ha skarpere flagging.

**Per-horisont-fordeling:**

| Horisont | ✓ | ⚠ | ✗ |
|---|---:|---:|---:|
| Macro | 0 | 7 | 15 |
| Swing | 0 | 0 | 22 |
| Scalp | 0 | 19 | 3 |

**Asset-klasse-mønstre:**
- **Energy (Brent/CrudeOil/NaturalGas)** = ✗ på alle tre horisonter
  — kombinerer eia + fundamentals + cot_disaggregated-svikt.
- **Crypto (BTC/ETH)** = ✗ på M/S — `crypto_sentiment` tom + `fundamentals` stale.
- **Agri (grains/softs)** = ⚠ på M (best av asset-klassene fordi
  weather + wasde + conab + shipping er fersk; svikten er bare
  cot_disaggregated som fyrer i kveld).
- **FX/Indices/Metals** = ✗ på M — `fundamentals`-stale dominerer.

**Anbefalinger for A2 (session 140):**
- Prioritet 1: **diagnose fundamentals-fetcher silent-fail** — størst
  blast-radius. Hvis FRED-API-key er issue, fix umiddelbart.
- Prioritet 2: **diagnose news_intel + crypto_sentiment 0-rader** —
  fetcher tilsynelatende kjører men skriver ingenting.
- Prioritet 3: A2-scope per § 20.5 (WASDE pre-2019, schema-drift,
  AAII-bug, comex/cafe ingest, fas_esr docstring, disease_pressure-
  tester) — viktig men ikke blast-kritisk.

Re-kjør rapport (`PYTHONPATH=src .venv/bin/python scripts/report_data_coverage.py`)
etter hver A2-fix for å verifisere at flagget snur.

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
| M | 0 | 7 | 15 |
| S | 0 | 0 | 22 |
| Sc | 0 | 19 | 3 |

### Fetcher-helse

- ✓ ferske: **11**, ⚠ aging: **2**, ✗ stale/missing: **6**

## Sammendragstabell 1 — per-horisont-coverage

Per (instrument × horisont) — ✓ alle primærkilder ferske / ⚠ 1 svikt / ✗ flere svikt.

| Instrument | Asset | Macro | Swing | Scalp |
|---|---|:---:|:---:|:---:|
| AUDUSD | fx | ✗ | ✗ | ⚠ |
| Brent | energy | ✗ | ✗ | ✗ |
| BTC | crypto | ✗ | ✗ | ⚠ |
| Cocoa | softs | ⚠ | ✗ | ⚠ |
| Coffee | softs | ⚠ | ✗ | ⚠ |
| Copper | metals | ✗ | ✗ | ⚠ |
| Corn | grains | ⚠ | ✗ | ⚠ |
| Cotton | softs | ⚠ | ✗ | ⚠ |
| CrudeOil | energy | ✗ | ✗ | ✗ |
| ETH | crypto | ✗ | ✗ | ⚠ |
| EURUSD | fx | ✗ | ✗ | ⚠ |
| GBPUSD | fx | ✗ | ✗ | ⚠ |
| Gold | metals | ✗ | ✗ | ⚠ |
| Nasdaq | indices | ✗ | ✗ | ⚠ |
| NaturalGas | energy | ✗ | ✗ | ✗ |
| Platinum | metals | ✗ | ✗ | ⚠ |
| Silver | metals | ✗ | ✗ | ⚠ |
| Soybean | grains | ⚠ | ✗ | ⚠ |
| SP500 | indices | ✗ | ✗ | ⚠ |
| Sugar | softs | ⚠ | ✗ | ⚠ |
| USDJPY | fx | ✗ | ✗ | ⚠ |
| Wheat | grains | ⚠ | ✗ | ⚠ |

## Sammendragstabell 2 — per-kilde-helse

| Fetcher | Cycle | Cron | Tabell | Rader | Sist obs. | Alder | DB-status | systemd |
|---|---|---|---|---:|---|---|:---:|---|
| calendar_ff | 12t (intra-day) | `15 6,18 * * *` | `econ_events` | 41,063 | 2026-04-30 16:15 UTC | 21.8t | ⚠ | active |
| comex | Daglig (M-F) | `0 22 * * 1-5` | `comex_inventory` | 15 | 2026-04-30 00:00 UTC | 38.1t | ✓ | active |
| conab | Månedlig | `0 20 15 * *` | `conab_estimates` | 158 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| cot_disaggregated | Ukentlig (fre) | `0 22 * * 5` | `cot_disaggregated` | 11,283 | 2026-04-21 00:00 UTC | 10.6d | ✗ | active |
| cot_euronext | Ukentlig (ons) | `0 18 * * 3` | `cot_euronext` | 1,221 | 2026-04-29 00:00 UTC | 2.6d | ✓ | active |
| cot_ice | Ukentlig (fre) | `30 22 * * 5` | `cot_ice` | 1,601 | 2026-04-22 00:00 UTC | 9.6d | ✗ | active |
| cot_legacy | Ukentlig (fre) | `0 22 * * 5` | `cot_legacy` | 5,790 | 2026-04-21 00:00 UTC | 10.6d | ✗ | active |
| crop_progress | Ukentlig (sesong apr-nov) | `0 23 * 4-11 1` | `crop_progress` | 3,114 | 2026-04-26 00:00 UTC | 5.6d | ✓ | active |
| crypto_sentiment | Daglig | `0 7 * * *` | `crypto_sentiment` | 0 | — | — | ✗ | active |
| eia_inventories | Ukentlig (ons) | `30 17 * * 3` | `eia_inventory` | 5,021 | 2026-04-24 00:00 UTC | 7.6d | ⚠ | active |
| enso | Månedlig | `0 6 12 * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 38.1t | ✓ | exit-code |
| fundamentals | Daglig | `30 2 * * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 38.1t | ✗ | active |
| news_intel | 12t (intra-day) | `30 6,18 * * *` | `news_intel` | 0 | — | — | ✗ | active |
| prices | Daglig (M-F) | `40 * * * 1-5` | `prices` | 90,634 | 2026-05-01 13:40 UTC | 26m | ✓ | active |
| seismic | Daglig (event-basert) | `0 4 * * *` | `seismic_events` | 123,401 | 2026-05-01 09:24 UTC | 4.7t | ✓ | active |
| shipping | Daglig (M-F) | `30 23 * * 1-5` | `shipping_indices` | 2,897 | 2026-04-29 00:00 UTC | 2.6d | ✓ | active |
| unica | Halvmånedlig | `0 21 1,16 * *` | `unica_reports` | 1 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| wasde | Månedlig | `0 19 13 * *` | `wasde` | 8,703 | 2026-04-10 00:00 UTC | 21.6d | ✓ | active |
| weather | Daglig | `0 3 * * *` | `weather` | 11,361 | 2026-05-01 00:00 UTC | 14.1t | ✓ | active |

## Drill-down per instrument

### AUDUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Brent (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### BTC (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, fundamentals ✗, crypto_sentiment ✗ |
| S | ✗ | prices ✓, calendar_ff ⚠, crypto_sentiment ✗ |
| Sc | ⚠ | calendar_ff ⚠ |

### Cocoa (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Coffee (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, conab ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, conab ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Copper (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Corn (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### Cotton (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, wasde ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, wasde ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### CrudeOil (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### ETH (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, fundamentals ✗, crypto_sentiment ✗ |
| S | ✗ | prices ✓, calendar_ff ⚠, crypto_sentiment ✗ |
| Sc | ⚠ | calendar_ff ⚠ |

### EURUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### GBPUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Gold (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Nasdaq (indices)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### NaturalGas (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### Platinum (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Silver (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✗, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Soybean (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |

### SP500 (indices)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Sugar (softs)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, conab ✓, unica ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, conab ✓, unica ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, unica ✓ |

### USDJPY (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_legacy ✗, fundamentals ✗ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Wheat (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |
