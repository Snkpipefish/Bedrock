# Pipeline-audit 2026-05-02 (post-Spor F + FRED-fix)

Oversikt over (a) hva som lastes ned, (b) hva som faktisk brukes av drivere/YAML, (c) hva som er overflødig.

## Sammendrag

- **Pipelinen er stort sett konsistent.** 19 fetchere registrert i `fetch.yaml`, alle har tilsvarende moduler i `bedrock.fetch.*`. Ingen savnede tabeller for live-fetchere.
- **Ubrukt-data:** ~5 FRED-serier hentes hver natt uten driver-bruk; én manuell-CSV (`disease_alerts.csv`, `export_events.csv`) er stale (>1 år gammel).
- **Ubrukte drivere (13 stk):** registrert men ikke wired i noe YAML — kandidater for sletting eller wiring i Spor E-arbeidet.
- **2 fetchere/moduler eksisterer i kodebasen uten å være registrert som runners:** `treasury_auctions` (F6 — manual backfill, ikke daglig), `usda_calendar`, `aaii`, `agsi`, `alsi`, `iip`, `manual_events`, `fas_esr`, `drought_monitor`, `nass`. Disse er *ikke* feil — de kjører via dedikerte backfill-scripts eller eksterne triggere.

---

## Del 1: Fetcher-config vs runner-implementasjoner

19 fetchere i `config/fetch.yaml`, alle har `@register_runner(name)` i `fetch_runner.py`. **Ingen mismatch.**

| Fetcher (cron) | Modul | DB-tabell | Siste rad |
|---|---|---|---|
| `prices` (`40 * * * 1-5`) | `bedrock.fetch.prices` | `prices` | 2026-05-01 |
| `cot_disaggregated` (`0 22 * * 5`) | `bedrock.fetch.cot_cftc` | `cot_disaggregated` | 2026-04-28 |
| `cot_legacy` (`0 22 * * 5`) | `bedrock.fetch.cot_cftc` | `cot_legacy` | 2026-04-28 |
| `fundamentals` (`30 2 * * *`) | `bedrock.fetch.fred` | `fundamentals` | 2026-05-01 |
| `weather` (`0 3 * * *`) | `bedrock.fetch.weather` | `weather` | 2026-05-02 |
| `enso` (`0 6 12 * *`) | `bedrock.fetch.enso` | `fundamentals` (NOAA_ONI) | 2026-02-01 |
| `wasde` (`0 19 13 * *`) | `bedrock.fetch.wasde` | `wasde` | 2026-04-10 |
| `crop_progress` (`0 23 * 4-11 1`) | `bedrock.fetch.nass` | `crop_progress` | 2026-04-26 |
| `shipping` (`30 23 * * 1-5`) | `bedrock.fetch.shipping` | `shipping_indices` | 2026-05-01 |
| `calendar_ff` (`15 6,18 * * *`) | `bedrock.fetch.calendar_ff` | `econ_events` | 2026-05-01 |
| `cot_ice` (ukentlig) | `bedrock.fetch.cot_ice` | `cot_ice` | 2026-04-28 |
| `eia_inventories` (ukentlig) | `bedrock.fetch.eia_inventories` | `eia_inventory` | 2026-04-24 |
| `comex` (daglig) | `bedrock.fetch.comex` | `comex_inventory` | 2026-04-30 |
| `seismic` (timesvis) | `bedrock.fetch.seismic` | `seismic_events` | 2026-05-01 |
| `cot_euronext` (ukentlig) | `bedrock.fetch.cot_euronext` | `cot_euronext` | 2026-04-29 |
| `conab` (månedlig) | `bedrock.fetch.conab` | `conab_estimates` | 2026-04-27 |
| `unica` (halvmånedlig) | `bedrock.fetch.unica` | `unica_reports` | 2026-04-27 |
| `news_intel` (timesvis) | `bedrock.fetch.news_intel` | `news_intel` | 2026-05-02 |
| `crypto_sentiment` (daglig) | `bedrock.fetch.crypto_sentiment` | `crypto_sentiment` | 2026-05-02 |

**Stale-tabeller (>30d):** `disease_alerts` (382d), `export_events` (594d) — manuelle CSV-er som ikke har vært oppdatert. `wasde` (22d) er normalt — månedlig.

---

## Del 2: Moduler uten runner-registrering

10 fetch-moduler eksisterer uten `@register_runner` — disse kjører via dedikerte backfill-scripts eller er event-drevne, ikke daglig:

| Modul | Brukstilfelle |
|---|---|
| `treasury_auctions` | Spor F6 — backfill-script `scripts/backfill/treasury_auctions.py` (kjøres manuelt; auksjoner er sjeldne nok at daglig timer er overkill) |
| `aaii` | AAII Sentiment Survey — har egen extension i `bedrock.fetch.aaii`, populeres via `scripts/backfill/aaii.py` |
| `agsi` | EU gas storage — backfill-only via `scripts/backfill/agsi_storage.py` (daglig overlay i NaturalGas via separat job?) |
| `alsi` | EU LNG-terminal storage — backfill via `scripts/backfill/alsi.py` |
| `iip` | EU REMIT supply unavailability — backfill via `scripts/backfill/iip.py` |
| `manual_events` | Operatør-driven import |
| `fas_esr` | USDA FAS Export Sales — backfill via `scripts/backfill/fas_esr.py` |
| `drought_monitor` | USDM ukentlig — backfill via `scripts/backfill/drought_monitor.py` |
| `nass` | NASS yield + grain_stocks — backfill via `scripts/backfill/nass_yield.py` (Spor D); crop_progress har egen runner |
| `usda_calendar` | USDA report-dates kalender |

**Anbefaling:** disse trenger ikke runner-registrering hvis backfillen faktisk kjører manuelt eller via cron utenfor `fetch.yaml`. Verdt å sjekke at alle har en aktiv mekanisme; hvis `agsi/alsi/iip/aaii` skal være daglig-oppdatert, mangler de timers.

---

## Del 3: Ubrukte FRED-serier

Live-fetcher henter 14 unike FRED-serier (~14 calls/dag, ~7 % av FRED's 120 req/min-budsjett). Av disse brukes 9 i drivere:

**Brukt (9):** DGS10, T10YIE, DTWEXBGS, VIXCLS, NFCI*, IRLTLT01\*M156N (4 stk), WALCL, RRPONTSYD, AAA10Y/BAA10Y (kombinerte i `hy_oas_change`)

**Ubrukt fra live-fetch (~3):** `WTREGEN` (Treasury Reserve Account — kombinert i `net_fed_liq_change`-driver i fetcher-Y, men ingen direkte driver-fil-funn).

54 unike series_ids finnes i `fundamentals`-tabellen totalt — flertallet fra historiske backfills (DEXBZUS, DEXCAUS osv.). Disse koster ingen ting i daglig fetch og kan stå uberørt.

**`DGS2` og `VXN` har data i DB men ingen driver bruker dem** — kandidater for sletting eller fremtidig driver.

---

## Del 4: Ubrukte drivere (registrert men ikke wired)

13 av 96 registrerte drivere brukes **ikke** i noen instrument-YAML:

| Driver | FRED-serie det leser | Status |
|---|---|---|
| `cfnai_3mma` | CFNAI | Erstattet av `ism_pmi_level` i Spor F1 (SP500/Nasdaq macro) — kandidat-DELETE |
| `umich_sentiment_z` | UMCSENT | Erstattet av `treasury_auction_demand` i Spor F6 — kandidat-DELETE |
| `nfci_change` | NFCI | Erstattet av `anfci_z` i Spor A10 — kandidat-DELETE |
| `enso_regime` | NOAA_ONI | Erstattet av `noaa_oni_index` i Spor A4, men brukes fortsatt av `analog`-modul (dim-extractor) |
| `cot_oi_change` | (cot_disaggregated) | Levert i Bunke7 #26, aldri wired — kandidat for opportunistisk wiring eller drop |
| `cot_commercial_extreme` | (cot_disaggregated) | Levert i Bunke7 #26, aldri wired — samme |
| `noaa_pdo_index` | PDO | Levert i Bunke4 #17, aldri wired (PDO er multi-decade, mest "interessant" enn actionable) |
| `intraday_atr_h1` | (H1 prices) | Levert i Bunke4 #18, aldri wired (krever H1-data som ikke fetches) |
| `t_bill_3mo_yield` | TB3MS | Levert i Bunke3 #7, aldri wired |
| `continuing_claims_z` | CCSA | Levert i Bunke3 #9, aldri wired (initial_claims_z dekker labor) |
| `vix_term_ratio` | VIX3M, VIXCLS | Levert i Bunke3, aldri wired (vurderes redundant med vol_regime) |
| `fomc_decision_distance` | (econ_events) | Levert i Bunke3 #14, aldri wired |
| `news_intel_severity_veto` | (news_intel) | Hard-veto-driver, deaktivert (krever bevisst veto-policy) |

**Anbefaling:** flag som "Spor E-kandidater" — vurder slett vs. opportunistisk wiring når Spor E åpner ~2026-06-01 (etter live-demo-empiri).

---

## Del 5: Stale manuelle CSV-er

| Fil | Siste oppdatering | Brukstilfelle |
|---|---|---|
| `data/manual/disease_alerts.csv` | 2025-04-15 (382d) | 1-3 events i bruk i agri-instrumenter; ikke kritisk men verdt en operatør-refresh |
| `data/manual/export_events.csv` | 2024-09-15 (594d) | Brukes av `export_event`-driver i grain/agri; oppdatering ville gi friske signaler |
| `data/manual/iri_enso_forecast.csv` | 2026-04-15 (frisk) | Spor F4 — månedlig manuell ingest fra IRI Plumes |
| `data/manual/ism_pmi.csv` | 2026-04 (frisk) | Spor F1 — månedlig manuell ingest fra ISM Manufacturing |

---

## Konklusjon + neste-steg-anbefaling

1. **Pipelinen er sound.** Ingen kritiske mismatcher mellom config og runners.
2. **DGS2 + VXN** lastes men brukes ikke — minor noise.
3. **13 ubrukte drivere** bør evalueres i Spor E-vinduet (slett eller wire).
4. **Manuell-CSV-er for `disease_alerts` + `export_events`** bør refreshes hvis disse signalene er ønsket aktive.
5. **agsi/alsi/iip-fetchere har ikke runner-timer** — sjekk at de har en oppdaterings-kilde (eller registrér en daglig runner).

---

## Oppdatering 2026-05-02 (post-audit fixes)

- **agsi + alsi runners registrert** (commit `d98e250`). Daglig 06:00 / 06:05
  Oslo timer aktivert i user-systemd. Live-verifisert: 145 + 174 rader
  hentet i første kjøring; latest gas_day_start=2026-04-30 (D+1 normal lag).
- **iip_remit** kjører fortsatt fra ukjent mekanisme (~12-16 rader/dag); siden
  data er fersk ble den ikke flyttet til registered-runner ennå. Bør auditeres
  separat for å forstå source-of-truth.
- **UI Drivers-fane** levert (commit `271a1fd`). Endpoint `/api/ui/drivers`
  serverer registry-vs-wirings-payload; UI-fanen "Drivere" viser søk/filter
  med 96 registrert / 83 brukt / 13 ubrukt-tellingen live. Operatør kan nå
  navigere driverlista direkte uten å lese rapport.
