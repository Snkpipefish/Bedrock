# Data-coverage-rapport — 2026-05-01

Sub-fase 12.8 Sub-task A1 (PLAN § 20). Per-instrument data-coverage
vurdert per horisont (Macro / Swing / Scalp) basert på § 20.2-mapping.
Helse-flagg per fetcher basert på cycle-spesifikke terskler (§ 20.4).

Generert av `scripts/report_data_coverage.py` mot `bedrock.db`
(2026-05-01 14:16 UTC). Inkluderer business-day-aware aging for
daglige fetchere (`prices`, `fundamentals`, `comex`, `shipping`)
slik at en fredag-rad ikke flagges stale på en lørdag/søndag.

## Key findings (Sub-task A1 → A2-input)

**Initial flagging korrigert etter to oppdagelser 2026-05-01 14:15 UTC.**

### Funn 1 — FRED virker faktisk

`journalctl --user -u bedrock-fetch-fundamentals.service` viser at
fetcheren fyrte 13:04 UTC og hentet 22 nye rader (DGS10, T10YIE,
VIXCLS, AAA10Y/BAA10Y, NFCI, WALCL, RRPONTSYD osv) — `Summary: 14/14
ok, 0 failed`. Tidlig "stale 38t"-flagging var en rapport-bug:
business-day-aware aging er nå i scriptet (`BUSINESS_DAY_FETCHERS`).
FRED-data er T+1 fra US-børs-close, så 30. apr 00:00 UTC er siste
rad fra fredag morgen frem til lørdag.

### Funn 2 — to user-timers er paused fra tidligere testing

`systemctl --user is-active`-sjekk avdekker:

| Timer | Status | Rader |
|---|---|---:|
| `bedrock-fetch-crypto_sentiment.timer` | `enabled=linked active=inactive` | 0 |
| `bedrock-fetch-news_intel.timer` | `enabled=linked active=inactive` | 0 |
| `bedrock-fetch-calendar_ff.timer` (user) | `linked, inactive` | n/a (system-versjonen er aktiv) |

Re-aktivering: `systemctl --user start bedrock-fetch-{crypto_sentiment,news_intel}.timer`.

### Funn 3 — what-if-fresh: alle 22 ✓

Med scriptet `--what-if-fresh "fundamentals,cot_disaggregated,cot_legacy,cot_ice,eia_inventories,calendar_ff,enso,crypto_sentiment,news_intel"`
(simulerer at alle pending fyrer eller blir reaktivert) blir
**alle 22 instrumenter ✓ på alle 3 horisonter (M/S/Sc)**.

Pipelinen har **strukturelt full coverage** for hele whitelist'en.
Røde flagg er transient-state (ventende fre-fyringer + paused user-
timers + business-day-bug), ikke strukturelle data-mangler.

### Reelle gjenværende issues for A2 (session 140)

1. **Re-aktiver paused user-timers** (`crypto_sentiment`, `news_intel`).
   Trivielt — én systemctl-kommando hver. Verifiser at fetcher
   skriver rader etter neste fyring.
2. **`enso`-service "exit-code"** — timer er aktiv, men service-
   subprocess feiler. Diagnose i logg + fix.
3. **`bedrock-monitor.service` failed** — kjent siden session 137.
4. **`eia_inventories` ⚠ 7.6d** — etter ons 29. apr-fyring burde DB
   ha 29. apr-rad. Sjekk EIA week-18-helligdag eller smart-skip-bug.
5. **`cot_*`-fetchere stale 10.6d** — fyrer fre 22:00 i kveld;
   forventet ✓ etter. Vurder buffer-økning til 12d for å unngå
   falsk-positiv fre morgen.
6. **`calendar_ff` aging 22t** — fyrer 18:15 i kveld; forventet ✓
   etter. Marginalt utenfor buffer.

### Anbefalt A2-rekkefølge

1. **5 minutter:** start de 2 paused user-timers.
2. **30 minutter:** diagnose enso + monitor failed services.
3. **Resten av A2 per § 20.5** (WASDE pre-2019, schema-drift, AAII-bug,
   comex/cafe-ingest, fas_esr-docstring, disease_pressure-tester).

Re-kjør `python scripts/report_data_coverage.py` etter hver fix for
å verifisere at flagget snur fra ✗/⚠ til ✓.



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
| M | 0 | 19 | 3 |
| S | 0 | 0 | 22 |
| Sc | 0 | 19 | 3 |

### Fetcher-helse

- ✓ ferske: **12**, ⚠ aging: **2**, ✗ stale/missing: **5**

## Sammendragstabell 1 — per-horisont-coverage

Per (instrument × horisont) — ✓ alle primærkilder ferske / ⚠ 1 svikt / ✗ flere svikt.

| Instrument | Asset | Macro | Swing | Scalp |
|---|---|:---:|:---:|:---:|
| AUDUSD | fx | ⚠ | ✗ | ⚠ |
| Brent | energy | ✗ | ✗ | ✗ |
| BTC | crypto | ⚠ | ✗ | ⚠ |
| Cocoa | softs | ⚠ | ✗ | ⚠ |
| Coffee | softs | ⚠ | ✗ | ⚠ |
| Copper | metals | ⚠ | ✗ | ⚠ |
| Corn | grains | ⚠ | ✗ | ⚠ |
| Cotton | softs | ⚠ | ✗ | ⚠ |
| CrudeOil | energy | ✗ | ✗ | ✗ |
| ETH | crypto | ⚠ | ✗ | ⚠ |
| EURUSD | fx | ⚠ | ✗ | ⚠ |
| GBPUSD | fx | ⚠ | ✗ | ⚠ |
| Gold | metals | ⚠ | ✗ | ⚠ |
| Nasdaq | indices | ⚠ | ✗ | ⚠ |
| NaturalGas | energy | ✗ | ✗ | ✗ |
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
| calendar_ff | 12t (intra-day) | `15 6,18 * * *` | `econ_events` | 41,063 | 2026-04-30 16:15 UTC | 22.0t | ⚠ | active |
| comex | Daglig (M-F) | `0 22 * * 1-5` | `comex_inventory` | 15 | 2026-04-30 00:00 UTC | 24.0t | ✓ | active |
| conab | Månedlig | `0 20 15 * *` | `conab_estimates` | 158 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| cot_disaggregated | Ukentlig (fre) | `0 22 * * 5` | `cot_disaggregated` | 11,283 | 2026-04-21 00:00 UTC | 10.6d | ✗ | active |
| cot_euronext | Ukentlig (ons) | `0 18 * * 3` | `cot_euronext` | 1,221 | 2026-04-29 00:00 UTC | 2.6d | ✓ | active |
| cot_ice | Ukentlig (fre) | `30 22 * * 5` | `cot_ice` | 1,601 | 2026-04-22 00:00 UTC | 9.6d | ✗ | active |
| cot_legacy | Ukentlig (fre) | `0 22 * * 5` | `cot_legacy` | 5,790 | 2026-04-21 00:00 UTC | 10.6d | ✗ | active |
| crop_progress | Ukentlig (sesong apr-nov) | `0 23 * 4-11 1` | `crop_progress` | 3,114 | 2026-04-26 00:00 UTC | 5.6d | ✓ | active |
| crypto_sentiment | Daglig | `0 7 * * *` | `crypto_sentiment` | 0 | — | — | ✗ | active |
| eia_inventories | Ukentlig (ons) | `30 17 * * 3` | `eia_inventory` | 5,021 | 2026-04-24 00:00 UTC | 7.6d | ⚠ | active |
| enso | Månedlig | `0 6 12 * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 38.3t | ✓ | exit-code |
| fundamentals | Daglig (M-F, T+1 publisering) | `30 2 * * *` | `fundamentals` | 46,717 | 2026-04-30 00:00 UTC | 24.0t | ✓ | active |
| news_intel | 12t (intra-day) | `30 6,18 * * *` | `news_intel` | 0 | — | — | ✗ | active |
| prices | Daglig (M-F) | `40 * * * 1-5` | `prices` | 90,634 | 2026-05-01 13:40 UTC | 35m | ✓ | active |
| seismic | Daglig (event-basert) | `0 4 * * *` | `seismic_events` | 123,401 | 2026-05-01 09:24 UTC | 4.9t | ✓ | active |
| shipping | Daglig (M-F) | `30 23 * * 1-5` | `shipping_indices` | 2,897 | 2026-04-29 00:00 UTC | 2.0d | ✓ | active |
| unica | Halvmånedlig | `0 21 1,16 * *` | `unica_reports` | 1 | 2026-04-27 00:00 UTC | 4.6d | ✓ | active |
| wasde | Månedlig | `0 19 13 * *` | `wasde` | 8,703 | 2026-04-10 00:00 UTC | 21.6d | ✓ | active |
| weather | Daglig | `0 3 * * *` | `weather` | 11,361 | 2026-05-01 00:00 UTC | 14.3t | ✓ | active |

## Drill-down per instrument

### AUDUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Brent (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✓, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### BTC (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, fundamentals ✓, crypto_sentiment ✗ |
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
| M | ⚠ | prices ✓, cot_disaggregated ✗, fundamentals ✓, comex ✓ |
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
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✓, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### ETH (crypto)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, fundamentals ✓, crypto_sentiment ✗ |
| S | ✗ | prices ✓, calendar_ff ⚠, crypto_sentiment ✗ |
| Sc | ⚠ | calendar_ff ⚠ |

### EURUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### GBPUSD (fx)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Gold (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Nasdaq (indices)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, fundamentals ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### NaturalGas (energy)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ✗ | prices ✓, cot_disaggregated ✗, fundamentals ✓, eia_inventories ⚠ |
| S | ✗ | prices ✓, cot_disaggregated ✗, eia_inventories ⚠, calendar_ff ⚠ |
| Sc | ✗ | calendar_ff ⚠, eia_inventories ⚠ |

### Platinum (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, fundamentals ✓, comex ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, comex ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, seismic ✓ |

### Silver (metals)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, fundamentals ✓, comex ✓ |
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
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, fundamentals ✓, calendar_ff ⚠ |
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
| M | ⚠ | prices ✓, cot_legacy ✗, fundamentals ✓ |
| S | ✗ | prices ✓, cot_legacy ✗, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠ |

### Wheat (grains)

| Horisont | Status | Primærkilder (status) |
|---|:---:|---|
| M | ⚠ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, shipping ✓ |
| S | ✗ | prices ✓, cot_disaggregated ✗, wasde ✓, crop_progress ✓, weather ✓, calendar_ff ⚠ |
| Sc | ⚠ | calendar_ff ⚠, wasde ✓ |
