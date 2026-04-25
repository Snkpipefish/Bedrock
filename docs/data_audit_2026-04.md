# Bedrock — fetch-data-audit 2026-04

**Session:** 56 (Fase 10 spor B)
**Forfatter:** Claude Code
**Status:** utkast — venter signering før Spor A (sessions 57-60) starter
**Mandat:** PLAN § 14 tillegg ("ubrukt-data-gjennomgang er Fase 10-oppgave") +
bruker-instruksjon: kartlegg `kilde × leses-av` + K-NN-feasibility per
asset-klasse mot PLAN § 6.5. **Ingen sletting** av fetch-scripts.

---

## 0. TL;DR

Tre kritiske funn for Fase 10:

1. **Bedrock-DB er tom.** `data/bedrock.db` har 0 rader i alle fem
   tabeller (`prices`, `cot_disaggregated`, `cot_legacy`, `fundamentals`,
   `weather`). Ingen backfill er kjørt. K-NN i Spor A har ingen data å
   matche mot før backfill er utført. **Spor A blokkert** inntil
   minimum-backfill er fullført.

2. **Driver-laget bruker kun `get_prices`.** Av DataStore-API-et
   (5 getters) er det kun `get_prices`/`get_prices_ohlc` som faktisk
   leses av drivere. `get_cot`, `get_fundamentals`, `get_weather`
   leses av ingen driver eller endpoint. Skjemaet eksisterer, men
   konsumentene mangler. Dette er forventet — ekte familie-drivere
   (positioning/macro/yield/weather) er placeholders i
   `gold.yaml`/`corn.yaml`.

3. **§ 6.5-dimensjonene er delvis dekket.** Av 12 unike dim-felt
   krevd av § 6.5 er **5 fullt dekket** (eksisterende fetcher + DDL),
   **4 delvis dekket** (kilde finnes i `~/cot-explorer/`, men ikke
   migrert til bedrock-skjema), **3 mangler kilde** (enso_regime,
   unica_mix_change, supply_disruption_level). Per Q2-instruks:
   ingen utvidelse uten godkjenning. Tre brudd flagget under § 5.

Tre asset-klasser er heller ikke konfigurert i `config/instruments/`
(FX, Energy, Softs). Kun Gold (metals) og Corn (grains) eksisterer.
Spor A kan trygt levere K-NN for disse to først; resten er en
oppfølgings-leveranse.

---

## 1. Bedrock fetch-lag — modul-inventar

Sju moduler i `src/bedrock/fetch/`. Alle aktive (importert via
`__init__.py` eller via `bedrock fetch`-CLI). Ingen er døde.

| Modul | Henter | Skriver til | CLI | Cron (fetch.yaml) |
|---|---|---|---|---|
| `prices.py` | Stooq daglige OHLCV | `prices`-tabell via `append_prices` | `bedrock backfill prices` | `40 * * * 1-5` (hverdager hver time) |
| `cot_cftc.py` | CFTC Socrata API (disaggregated + legacy) | `cot_disaggregated` + `cot_legacy` | `bedrock backfill cot_disaggregated` / `..._legacy` | `0 22 * * 5` (fredag etter publisering) |
| `fred.py` | FRED `series/observations` | `fundamentals` | `bedrock backfill fundamentals` | `30 2 * * *` (daglig 02:30 UTC) |
| `weather.py` | Open-Meteo Archive (ERA5) | `weather` | `bedrock backfill weather` | `0 3 * * *` (daglig 03:00 UTC) |
| `usda_calendar.py` | YAML-loader + `usda_blackout`-gate | (in-process gate, ingen DB) | n/a | n/a (event-drevet) |
| `base.py` | felles `http_get_with_retry` | n/a (helper) | n/a | n/a |
| `__init__.py` | side-effekt-import for å registrere `usda_blackout`-gate | n/a | n/a | n/a |

**Kommentar:**
- Ingen "dropp"-kandidater. Hvert script har en eier (DDL-tabell eller
  in-process gate).
- `prices.py` støtter kun `i=d` (daglig) per § 7-PLAN. Intraday er
  ikke en leveranse i Fase 10.

---

## 2. Bedrock DataStore — tabell-status

Fra `src/bedrock/data/schemas.py` + `sqlite3 data/bedrock.db`:

| Tabell | DDL eksisterer | Rader nå | Distinct-nøkkel | Skrives av | Leses av |
|---|---|---|---|---|---|
| `prices` | ✅ | **0** | (instrument, tf, ts) | `prices.py` via `append_prices` | `trend.sma200_align`, `trend.momentum_z`, `currency.currency_cross_trend`, `signal_server.endpoints.prices`, `orchestrator.signals` (`get_prices_ohlc`) |
| `cot_disaggregated` | ✅ | **0** | (report_date, contract) | `cot_cftc.py` | **(ingen)** |
| `cot_legacy` | ✅ | **0** | (report_date, contract) | `cot_cftc.py` | **(ingen)** |
| `fundamentals` | ✅ | **0** | (series_id, date) | `fred.py` | **(ingen)** |
| `weather` | ✅ | **0** | (region, date) | `weather.py` | **(ingen)** |

**Funn:** Skjemaet er komplett, men 4 av 5 tabeller har ingen konsument
i kode-laget i dag. Alle YAML-rule-filer (`gold.yaml`, `corn.yaml`)
bruker `sma200_align`/`momentum_z` som placeholder for ikke-trend-
familier. Dette er konsistent med STATE: ekte positioning/macro/yield/
weather-drivere er ikke skrevet ennå.

**Konsekvens for Fase 10:** vi må enten (a) skrive minst én ekte
driver per familie i Spor A som beviser at K-NN-output er nyttig,
eller (b) levere K-NN som en frittstående `analog`-familie der
neighbors selv brukes som signal — uavhengig av at de andre
familiene fortsatt er placeholders. **(b) er per § 6.5-design**
("egen `analog` driver-familie i scoring") og er den ryddige
veien. Flagget for § 5 nedenfor.

---

## 3. Krys-referanse: kilde × leses-av

Hvor leses faktiske data-felt fra DataStore i kjørende kode?

| Datakilde | Leses av drivere | Leses av endpoints | Leses av UI (indirekte) |
|---|---|---|---|
| `prices` (Stooq) | `trend.sma200_align`, `trend.momentum_z`, `currency.currency_cross_trend` | `signal_server.endpoints.prices` (`/prices`-endpoint), `orchestrator.signals._build_entry` (via `get_prices_ohlc` for setup-bygging) | `web/assets/app.js` ber ikke direkte om `/prices`, men setups (som rendres) er bygd på prisene |
| `cot_disaggregated` | (ingen) | (ingen) | (ingen) |
| `cot_legacy` | (ingen) | (ingen) | (ingen) |
| `fundamentals` (FRED) | (ingen) | (ingen) | (ingen) |
| `weather` (ERA5) | (ingen) | (ingen) | (ingen) |
| `usda_calendar` (YAML) | n/a (gate) | n/a (in-process) | n/a |

**UI-fetch-kall** (fra `web/assets/app.js` + `admin.js`):

| URL | Konsum |
|---|---|
| `/health` | header-pill (status), admin-tab |
| `/api/ui/trade_log` + `/summary` | Skipsloggen (Fane 1) |
| `/api/ui/setups/financial` | Financial setups (Fane 2) |
| `/api/ui/setups/agri` | Soft commodities (Fane 3) |
| `/api/ui/pipeline_health` | Kartrommet (Fane 4) |
| `/admin/rules`, `/admin/rules/<id>`, `/admin/rules/<id>/dry-run`, `/admin/logs` | admin-editor |

UI leser ingen data direkte fra `prices`/`cot`/`fundamentals`/`weather`-
tabeller. Alle fane-data går via signal-pipelinen
(`signals.json`/`agri_signals.json`) eller pipeline-helse-fila.

---

## 4. Eksterne data-reservoarer (`~/cot-explorer/`)

Bedrock skal kjøre parallelt med eksisterende produksjon (invariant
per CLAUDE.md). `~/cot-explorer/data/` har bred dekning som potensielt
kan migreres til bedrock-skjema når vi trenger det. Audit av hva som
faktisk eksisterer:

| Katalog | Format | Historikk | Mulig bedrock-mapping |
|---|---|---|---|
| `data/history/disaggregated/{2010..2025}.json` | per-år JSON | **16 år** | `cot_disaggregated`-tabell — direkte migrerbar |
| `data/history/legacy/` | per-år | (sannsynlig 16 år) | `cot_legacy` |
| `data/history/tff/`, `data/history/supplemental/` | per-år | (sannsynlig 16 år) | ikke i bedrock-skjema (ny tabell) |
| `data/disaggregated/2026-*.json` | datert snapshot | 5 uker | inkrementell — overflødig hvis history migreres |
| `data/macro/latest.json` | snapshot | **1 fil** (kun `2026-03-22.json` + latest) | har VIX, DXY, SPX, EURUSD, +29 andre m/chg1d/chg5d/chg20d, vix_regime, dollar_smile-felt — men **ingen tidserie-historikk** |
| `data/agri_history/<region>.json` | per-region | **184 mnd** (2011-01 → 2026-04) | trenger ny `weather_monthly`-tabell (water_bal/hot_days/dry_days finnes ikke i `WeatherDailyRow`) |
| `data/fundamentals/latest.json` | snapshot | 1 fil | scoring-aggregat (econ_growth/inflation/jobs); ikke direkte FRED-serier |
| `data/conab/latest.json` | snapshot | 1 fil + `_meta` | yoy_change_pct per crop — én observasjon, ingen historikk |
| `data/oilgas/latest.json` | snapshot | 1 fil | brent_wti_spread + risk-scores — snapshot-only |
| `data/geointel/chokepoints.json` | statisk | 1 fil | risk-scores per chokepoint — statisk, ingen tidserie |
| `data/calendar/latest.json` | snapshot | 1 fil | event-liste — overlapper `usda_calendar`-pattern |
| `data/comex/`, `data/euronext_cot/`, `data/ice_cot/`, `data/cot_analytics/` | snapshots | 1-2 filer hver | ulike COT-børser; ikke i bedrock-skjema |

**Funn:** Den eneste eksterne kilden med ekte tidserie-historikk
brukbar for K-NN er:
- `cot-explorer history/disaggregated` + `history/legacy` (2010-2025)
- `cot-explorer agri_history/<14 regions>` (månedlig 2011-2026)

Resten er point-in-time-snapshots eller 5-ukers øyeblikksbilder.

**Migrering-pekere (ikke leveranse i denne audit):** Disse to kildene
kan fylle bedrock.db i Spor A session 57 før K-NN-implementasjonen,
forutsatt at vi aksepterer (a) en ny `weather_monthly`-tabell (krever
ADR + DDL-utvidelse) for agri_history, og (b) at månedlig-aggregert
weather er akseptabelt for `weather_stress`-dimensjonen. Daglig
ERA5-backfill via `bedrock backfill weather` er alternativet — men
da må vi beregne `water_bal`/`hot_days` selv.

---

## 5. K-NN-feasibility per asset-klasse (§ 6.5)

Per Q2: streng kontrakt mot § 6.5. Brudd flagges, ingen stille utvidelse.
Tre forslag pr brudd: (M) manuelt fyll, (D) drop dim, (U) utsett asset-klasse.

Legend for kolonnen "Status":

- ✅ **DEKKET** — bedrock-fetcher + DDL eksisterer, kan backfilles fra
  åpen kilde uten ny kode (kun kjøre `bedrock backfill ...`)
- 🟡 **DELVIS** — kilde finnes (i `~/cot-explorer/` eller via FRED), men
  mangler bedrock-fetcher / DDL-mapping / aggregat. Krever utvikling.
- ❌ **MANGLER** — ingen åpenbar kilde. Krever ny fetcher + ny DDL.

| Asset-klasse | Dim (§ 6.5) | Status | Kilde / kommentar |
|---|---|---|---|
| **metals** (Gold/Silver) | `vix_regime` | 🟡 | Trenger VIX-tidserie. Stooq har `^vix` (`vix.us` ticker?). Ikke i `gold.yaml` i dag. Bedrock-fetcher støtter det via `bedrock backfill prices` hvis ticker tas inn. Selve `regime`-kategorisering (low/elevated/high) hører i driver. |
| | `real_yield_chg5d` | ✅ | DGS10 (FRED) finnes i `gold.yaml`. Realyield = DGS10 minus inflation breakeven (T10YIE). T10YIE er FRED — kan legges til i instrument-yaml uten kode. |
| | `dxy_chg5d` | ✅ | DTWEXBGS (FRED) er allerede i `gold.yaml`. chg5d-beregning hører i driver, ikke i fetcher. |
| | `cot_mm_pct` | ✅ | `cot_disaggregated`-tabell + `cot_contract` "GOLD - COMMODITY EXCHANGE INC." finnes i YAML. mm_pct = mm_long/(mm_long+mm_short). Backfill nødvendig (16 år tilgjengelig fra `cot-explorer/history/`). |
| **FX** | `rate_differential_chg` | 🟡 | US-rente OK (FRED DGS2/DGS10). Foreign rente per valuta (EUR ESTR, JPY JGB, GBP gilts) ikke standardisert i bedrock-fetcher. Krever FRED-serie-mapping per FX-cross. |
| | `vix_regime` | 🟡 | Som metals. |
| | `dxy_chg5d` | ✅ | Som metals. |
| | `term_spread` | ✅ | DGS10 - DGS2 (FRED). Beregning i driver. |
| **energy** (Oil) | `backwardation` | ❌ | Front-back-month spread for olje-futures. cot-explorer `oilgas/latest.json` har `brent_wti_spread`, ikke calendar spread. Krever ny fetcher (ICE/CME front+back contracts). |
| | `supply_disruption_level` | ❌ | Kvalitativ score. cot-explorer `geointel/chokepoints.json` har risk-tags, men statisk + diskret. Mangler tidserie. |
| | `dxy_chg5d` | ✅ | Som metals. |
| | `cot_commercial_pct` | ✅ | `cot_disaggregated.comm_long`/`comm_short`. Samme tabell som metals; mangler bare backfill. |
| **grains** | `weather_stress_key_region` | 🟡 | Bedrock `weather`-tabell har daglig tmax/tmin/precip via Open-Meteo. cot-explorer `agri_history/us_cornbelt.json` har 184 mnd med `temp_mean`/`hot_days`/`dry_days`/`water_bal`. Format-mismatch: bedrock daglig vs ekstern månedlig-aggregat. Begge brukbare; valget styrer skjema. |
| | `enso_regime` | ❌ | NOAA ONI-indeks. Ingen bedrock-fetcher, ingen kilde i `cot-explorer/`. |
| | `conab_yoy` | 🟡 | cot-explorer `conab/latest.json` har `yoy_change_pct` per crop som SNAPSHOT (én observasjon). Ingen historikk → kan ikke brukes for K-NN. CONAB publiserer manuelle PDF/XLS — krever PDF-parser-fetcher (PLAN § 7.3 nevner WASDE som tilsvarende prosjekt). |
| | `dxy_chg5d` | ✅ | Som metals. |
| **softs** | `weather_stress` | 🟡 | Som grains, men regions: `brazil_coffee`, `brazil_mato_grosso`, `sea_palm`, `west_africa_cocoa` (alle eksisterer i `agri_history/`). |
| | `enso_regime` | ❌ | Som grains. |
| | `unica_mix_change` | ❌ | UNICA publiserer halvmånedlig. Ingen kilde i `cot-explorer/`, ingen bedrock-fetcher. Krever ny fetcher + DDL. |
| | `brl_chg5d` | ✅ | BRLUSD via Stooq prices (`brlusd` ticker). chg5d i driver. |

### 5.1 Brudd mot § 6.5 — beslutning kreves

Tre brudd der dim ikke kan dekkes uten stille utvidelse av kontrakten:

**Brudd 1 — energy: `backwardation` + `supply_disruption_level` mangler**
- Forslag M: manuelt fyll. Backwardation kan beregnes hvis vi
  begynner å fetche ICE/CME front+back contracts (krever ny fetcher).
  supply_disruption_level kan vedlikeholdes manuelt i en YAML
  (event-drevet, lite frekvens).
- Forslag D: drop begge. Energy K-NN går da på `dxy_chg5d` +
  `cot_commercial_pct` alene — for tynt for K=5 i meningsfull
  asymmetri.
- Forslag U: utsett energy K-NN til ny fetcher er på plass (egen
  Fase 10.5 eller defer til Fase 11).
- **Anbefaling:** **U (utsett)**. Energy-instrumenter er ikke
  konfigurert i `config/instruments/` i dag, så ingen brukere venter
  på dette. Drop ville ødelagt kontrakten i § 6.5; manuelt fyll
  introduserer arbeid uten klar gevinst før instrumentet faktisk
  trades.

**Brudd 2 — grains/softs: `enso_regime` mangler**
- Forslag M: legg ENSO-fetcher til Spor A som tillegg (NOAA ONI,
  månedlig CSV-endepunkt — billig fetcher).
- Forslag D: drop. Grains K-NN går da på `weather_stress` +
  `conab_yoy` + `dxy_chg5d`. Softs på `weather_stress` +
  `unica_mix_change` + `brl_chg5d`. Begge tape én av fire
  dimensjoner.
- Forslag U: utsett grains/softs K-NN.
- **Anbefaling:** **M (manuelt fyll)** for ENSO. NOAA ONI er gratis
  og månedlig — én tynn fetcher (~150 linjer). Gjør Spor A litt
  tyngre, men forhindrer kvalitets-degradering. **Krever
  brukerens beslutning.**

**Brudd 3 — softs: `unica_mix_change` mangler**
- Forslag M: PDF-parser eller manuelt YAML-fyll.
- Forslag D: drop. Softs K-NN går på `weather_stress` + ENSO (om M
  velges over) + `brl_chg5d`.
- Forslag U: utsett softs K-NN.
- **Anbefaling:** **U (utsett)**. UNICA-PDF-parsing er en betydelig
  oppgave (hører i PLAN § 7.3 som "fase 5/4-tillegg" som ikke er
  bygd ennå). Softs-instrumenter er ikke konfigurert; ingen venter.

### 5.2 Forslag til tillegg-dim utover § 6.5

Ingen identifisert. Audit avdekket ikke en data-rik kilde som
mangler i § 6.5 og som åpenbart burde tilføyes. Hvis vi i Spor A
session 58 oppdager at `vix_term_structure` (allerede i
`macro/latest.json`-snapshot) eller `correlations`-blokk har
prediktiv verdi, flagger vi det da som separat "tillegg-dim Y for
asset-klasse X"-forslag.

### 5.3 K-NN-feasibility-tabell (oppsummering)

| Asset-klasse | Dim totalt | ✅ | 🟡 | ❌ | Konfigurert i `config/instruments/`? | K-NN-klar i Spor A? |
|---|---|---|---|---|---|---|
| **metals** | 4 | 2 | 2 | 0 | ✅ Gold | ✅ etter backfill (sessions 57-58) |
| **FX** | 4 | 2 | 2 | 0 | ❌ | n/a (ingen instrument) |
| **energy** | 4 | 2 | 0 | 2 | ❌ | ❌ utsett (Brudd 1) |
| **grains** | 4 | 1 | 2 | 1 | ✅ Corn | 🟡 betinget av Brudd 2-vedtak |
| **softs** | 4 | 1 | 1 | 2 | ❌ | ❌ utsett (Brudd 3) eller delvis |

**Konklusjon for Spor A-omfang:**
- **Garantert:** K-NN for **metals** (Gold). 4 av 4 dim leverbar med
  bedrock-eksisterende fetchere + 16 års COT-history-migrering.
- **Sannsynlig (krever brukervedtak):** K-NN for **grains** (Corn).
  Avhengig av Brudd 2-vedtak (legg ENSO-fetcher til Spor A
  ja/nei) og hvilken weather-form vi velger
  (daglig Open-Meteo backfill vs månedlig migrering fra
  `agri_history/`).
- **Ikke i Spor A:** energy, softs, FX. Ingen er konfigurert i
  `config/instruments/`; å levere K-NN uten et instrument å score
  er trolig ikke verdt det. Anbefaling: utsett til de
  asset-klassene faktisk introduseres.

---

## 6. Anbefalinger / handlinger

Ingen sletting (per CLAUDE.md). Fire flaggede beslutninger til bruker:

| # | Beslutning | Kontekst |
|---|---|---|
| **A** | **Brudd 2 (ENSO):** legge inn ENSO-fetcher (NOAA ONI) i Spor A, eller utsette grains K-NN? | Påvirker session 57-58 scope. M = +1 fetcher, gir grains-coverage. U = drop grains K-NN i Fase 10. |
| **B** | **Weather-form:** Open-Meteo daglig backfill (eksisterende fetcher, men beregne `hot_days`/`water_bal` i driver) ELLER migrere `cot-explorer/agri_history/` (månedlig + ferdig-aggregert, men krever ny `weather_monthly`-tabell + ADR)? | Påvirker session 57 scope. Daglig = mer fleksibelt + lengre runtime; månedlig = raskere ferdig + format-låst. |
| **C** | **Brudd 1 (energy) + Brudd 3 (softs):** bekrefte utsett — ingen K-NN for disse i Fase 10. | Holder Spor A-scope tett. Re-vurderes når energy/softs-instrumenter faktisk trades. |
| **D** | **Backfill-rekkefølge i session 57:** prices først (alltid behov), så cot_disaggregated (gold + corn contracts), så fundamentals (DGS10, DGS2, T10YIE, DTWEXBGS), så weather (us_cornbelt + Brazil-regions hvis grains/softs er i scope). | Avgjørelse + kjøretid (forventet 1-2 timer for full backfill). |

**Ikke-handlinger (eksplisitt):**
- Ingen fetch-script slettes (CLAUDE.md "ikke dropp fetch-scripts uten godkjenning")
- Ingen DDL-endringer i denne sessionen (krever ADR-005 i session 57)
- Ingen `analog_outcomes`-tabell ennå (også session 57, etter ADR)
- Ingen migrasjon av `cot-explorer`-data i denne sessionen (utføres i session 57 etter beslutning B)

---

## 7. Referanser

- PLAN § 6.5 (analog-matching dim per asset-klasse)
- PLAN § 7 (fetch-laget + § 7.3 nye datakilder)
- PLAN § 14 tillegg ("ubrukt-data-gjennomgang er Fase 10-oppgave")
- STATE current-state (Fase 9 lukket, Fase 10 spor B = denne audit)
- ADR-002 (SQLite + pandas)
- ADR-004 (Python 3.10 baseline)

---

*Slutt audit. Venter på beslutningene A-D før session 57 (ADR-005 +
backfill + outcome-labels) starter.*
