# Bedrock — backfill-eksekvering 2026-04

**Session:** 58 (Fase 10 spor A)
**Dato:** 2026-04-25
**DB-fil:** `data/bedrock.db` (3.54 MB)
**Status:** alle kilder backfilt for Gold + Corn, klar for K-NN-impl i session 59

---

## 1. Sammendrag

| Kilde | Tabell | Rader | Date-range | Notater |
|---|---|---:|---|---|
| Yahoo Finance (daglig) | `prices` | 8 200 | 2010-01-04 → 2026-04-24 | Gold (4 101) + Corn (4 099). 16 års daglig OHLCV. |
| CFTC disaggregated | `cot_disaggregated` | 1 702 | 2010 → 2026-04-21 | Gold + Corn (851 hver). Ukentlig CFTC-rapporter. |
| FRED | `fundamentals` | 17 017 | 2010-01-01 → 2026-04-24 | DGS10, DGS2, T10YIE, DTWEXBGS — 4 251–4 256 obs hver. |
| NOAA CPC ONI | `fundamentals` | 914 | **1950**-01-01 → 2026-02-01 | ENSO som `series_id="NOAA_ONI"` (ADR-005 B1). 76 års månedlig historikk. |
| cot-explorer migrering | `weather_monthly` | 2 576 | 2011-01 → 2026-04 | 14 regioner × 184 mnd. Pre-aggregert (water_bal, hot_days etc.). |
| Beregnet fra prices | `analog_outcomes` | 16 160 | 2010 → 2026-03-12 (30d) / 2025-12-12 (90d) | Gold + Corn × {30d, 90d}. forward_return + max_drawdown. |
| **Total ny data** | | **46 569 rader** | | DB vokste fra 0 → 3.54 MB |

Wall-time totalt: **~7 min** for selve backfillen (mye raskere enn opprinnelig 1-2 t-estimat — Yahoo + Socrata + FRED håndterer 16-års-vinduer i én request).

---

## 2. Per-tabell-detaljer

### `prices` (Yahoo Finance, daglig)

| Instrument | Ticker | Bars | Range |
|---|---|---:|---|
| Gold | `GC=F` (COMEX continuous futures) | 4 101 | 2010-01-04 → 2026-04-24 |
| Corn | `ZC=F` (CBOT continuous futures) | 4 099 | 2010-01-04 → 2026-04-24 |

Yahoo leverer ekte OHLCV (open/high/low/close + volume). Ingen pagination
nødvendig for 16-års-vindu. URL-format:
`query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&period1=...&period2=...`

### `cot_disaggregated` (CFTC Socrata API)

| Contract | Reports | Range |
|---|---:|---|
| `GOLD - COMMODITY EXCHANGE INC.` | 851 | 2010 → 2026-04-21 |
| `CORN - CHICAGO BOARD OF TRADE` | 851 | 2010 → 2026-04-21 |

Siste Gold-rapport (sanity): 2026-04-21 mm_long=123 681, mm_short=30 705.

**Bug fikset under session 58:** CFTC endret felt-navn fra
`m_money_positions_long` → `m_money_positions_long_all` (og samme for `_short`).
Bedrock-fetcher ble oppdatert + test-fixtures rebased.

### `fundamentals` (FRED + NOAA ONI)

| series_id | Rows | Range | Beskrivelse |
|---|---:|---|---|
| `DGS10` | 4 255 | 2010-01-01 → 2026-04-23 | 10Y Treasury constant maturity rate |
| `DGS2` | 4 255 | 2010-01-01 → 2026-04-23 | 2Y Treasury constant maturity rate |
| `T10YIE` | 4 256 | 2010-01-01 → 2026-04-24 | 10Y breakeven inflation expectation |
| `DTWEXBGS` | 4 251 | 2010-01-01 → 2026-04-17 | Trade-weighted broad dollar index |
| `NOAA_ONI` | **914** | **1950-01-01** → 2026-02-01 | ENSO Oceanic Niño Index (månedlig) |

NOAA ONI har dypest historikk (76 år, 914 månedlige observasjoner) takket
være NOAA CPCs publiserings-praksis siden 1950. ENSO lagres her
istedenfor i en egen tabell — ADR-005 B1.

### `weather_monthly` (migrering fra `~/cot-explorer/data/agri_history/`)

184 mnd (2011-01 → 2026-04) per region × 14 regioner = **2 576 rader**.

Regioner (alfabetisk): argentina_pampas, australia_wheat, brazil_coffee,
brazil_mato_grosso, canada_prairie, china_wheat, eu_northern,
india_punjab, sea_palm, ukraine_blacksea, us_cornbelt, us_delta_cotton,
us_great_plains, west_africa_cocoa.

Felt: temp_mean, temp_max, precip_mm, et0_mm, hot_days, dry_days,
wet_days, water_bal. Ferdig pre-aggregert i kilden (cot-explorers
ERA5-pipeline). Det 9. JSON-feltet `days` (antall dager i mnd) droppet
under migrering — kan beregnes trivielt fra `month`-stringen.

### `analog_outcomes` (beregnet fra `prices`-tabellen)

For hver historisk pris-bar med full forward-vindu, beregnet
`forward_return_pct = (close_t+H / close_t - 1) × 100` og
`max_drawdown_pct = (min(close_t..t+H) / close_t - 1) × 100`.

**Sanity-statistikk** (per (instrument, horizon)):

| Instrument | Horizon | n | Avg return | Hit-rate (≥3%) | Avg drawdown | Worst drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Gold | 30d | 4 071 | +1.21% | 34.5% | −3.07% | −17.36% |
| Gold | 90d | 4 011 | +3.72% | 52.5% | −4.97% | −25.00% |
| Corn | 30d | 4 069 | +0.58% | 36.6% | −5.67% | −36.48% |
| Corn | 90d | 4 009 | +1.84% | 40.4% | −10.21% | −41.33% |

**Tolkninger:**
- Gold 90d snitt-return +3.72% matcher Gulls langsiktige uptrend i
  perioden 2010-2026.
- Corn drawdowns er ~2× større enn Gold — agri har høyere realisert vol.
- Hit-rate (≥3%) brukes IKKE som lagret felt (per ADR-005 B3): driver
  beregner det on-the-fly fra rå return, slik at terskel kan justeres
  uten re-backfill. Tallene over er kun sanity-baseline for K-NN-driver-
  utvikling i session 60.

---

## 3. Hendelser under eksekvering

### Stooq → Yahoo-bytte (kritisk)

**Symptom:** `bedrock backfill prices --instrument Gold` feilet med
`PriceFetchError: Failed to parse Stooq CSV ... Expected 1 fields in line 6, saw 2`.

**Root cause:** Stooq begynte å kreve API-nøkkel for daglige CSV-
nedlastinger en gang etter at Bedrock fetcher ble skrevet i Fase 3.
Endepunktet returnerer nå en captcha-instruksjon istedenfor CSV.

**Beslutning + fix:** byttet til Yahoo Finance som primærkilde. Port av
cot-explorers `build_price_history.py` (verifisert 15 års produksjons-
historikk). Stooq beholdes som `--source stooq` fallback for fremtid.

**Filer endret:** ny `src/bedrock/fetch/yahoo.py` (180 linjer port + 14
nye tester), `bedrock backfill prices` utvidet med `--source` +
`--interval`, `yahoo_ticker` lagt til i `InstrumentMetadata` (Gold:
`GC=F`, Corn: `ZC=F`).

### CFTC-felt-navn-endring

**Symptom:** `CotFetchError: missing fields ['m_money_positions_long',
'm_money_positions_short']`.

**Root cause:** CFTC splittet `m_money_positions_*` i `_all` / `_old` /
`_other` for kontrakter med hyphenert termin-struktur. Det gamle
felt-navnet finnes ikke lenger; nyeste `_all` (combined) er det
funksjonelt ekvivalente.

**Fix:** `_DISAGG_FIELD_MAP` oppdatert til `m_money_positions_long_all`
+ `m_money_positions_short_all`. Test-fixtures (`test_fetch_cot_cftc.py`
linje 55-69) rebased med sed.

### Ingen problemer

FRED, NOAA, Open-Meteo (ikke kjørt), agri_history-migrering,
outcomes-beregning. Alle gikk uten feil.

---

## 4. Hva som IKKE ble backfilt (bevisst)

- **`prices` for andre instrumenter** enn Gold/Corn — kun disse to har
  YAML-config i `config/instruments/`. Når andre asset-klasser legges
  til (FX, energy, softs), gjenta `bedrock backfill prices --instrument
  <X>` per asset-klasse.
- **`cot_legacy`** — disaggregated er nyere og rikere; legacy er kun
  relevant for kontrakter uten disaggregated-versjon (gjelder ikke
  Gold/Corn).
- **`weather`** (daglig) — vi bruker pre-aggregert månedlig fra
  cot-explorer per ADR-005 B2. Daglig-tabell beholdes for fremtidige
  setup-trigger-formål.
- **Energy / softs / FX-instrumenter** — utsett per audit-beslutning C
  (ingen instrument konfigurert ennå).

---

## 5. Verifisering

```sql
-- Kjørt manuelt 2026-04-25:
SELECT COUNT(*) FROM prices;              -- 8200
SELECT COUNT(*) FROM cot_disaggregated;   -- 1702
SELECT COUNT(*) FROM fundamentals;        -- 17931 (4 FRED + 1 NOAA = 5 series)
SELECT COUNT(*) FROM weather_monthly;     -- 2576
SELECT COUNT(*) FROM analog_outcomes;     -- 16160
```

Idempotens-test: `bedrock backfill prices --instrument Gold --from 2010-01-01`
re-kjørt → INSERT OR REPLACE på PK gir same rad-tall (verifisert ved
manuell re-run).

---

## 6. Klar for session 59

`find_analog_cases`-impl (per ADR-005 B4) kan nå skrives med faktisk
data å query. Test-feedback-loop: K-NN på Gold med (DXY chg5d,
T10YIE-DGS10, DGS10, COT mm-pct) over 4 071 ref-datoer → ekte naboer
+ ekte forward returns.

Backfill-CLI-ene fra denne sessionen blir også brukt periodisk for å
holde DB-en oppdatert: `cron`-entries finnes i `config/fetch.yaml`
(prices: hourly hverdager, cot: lørdag, fundamentals: daily, enso:
12. mnd). Scheduler-runner som faktisk kjører dem hører i Fase 11
per PLAN.

---

## 7. Referanser

- ADR-005: data-skjema for analog-matching
- `docs/data_audit_2026-04.md`: K-NN-feasibility-vurdering
- PLAN § 6.5: analog-matching dim per asset-klasse
- PLAN § 7.3: nye datakilder (USDA, BRL/USD, BDI etc. — fortsatt
  utsatt til behov oppstår)
