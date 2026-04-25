# ADR-005: Data-skjema for analog-matching (Fase 10)

Dato: 2026-04-25
Status: accepted
Fase: 10 (Spor A, session 57)

## Kontekst

Fase 10 (PLAN § 6.5) introduserer analog-matching: K-NN per asset-klasse
mot historiske tilstander, output som `analog`-driver-familie i scoring +
narrative i UI. Dette krever tre nye data-områder utover dagens DataStore:

1. **Forward-return-utfall (outcome-labels)** for hver historiske dato per
   instrument — slik at K-NN kan rapportere "av N matcher steg Y/N >3% innen
   30d, snitt +X%".

2. **Månedlig vær-aggregat** — § 6.5 trenger `weather_stress` per region
   (us_cornbelt, brazil_coffee, ...). Bedrocks eksisterende `weather`-tabell
   er daglig (tmax/tmin/precip via Open-Meteo). `~/cot-explorer/data/agri_history/`
   har derimot ferdig pre-aggregert månedlig data (184 mnd × 14 regioner) med
   `temp_mean`, `temp_max`, `precip_mm`, `et0_mm`, `hot_days`, `dry_days`,
   `wet_days`, `water_bal`. Per audit-beslutning B (2026-04-25): vi
   migrerer det månedlige aggregatet for K-NN-bruk, og beholder daglig
   `weather`-tabellen for fremtidig setup-generering. Det gir formel-
   konsistens med cot-explorer under parallell-drift.

3. **ENSO-tidserie (NOAA ONI)** — § 6.5 trenger `enso_regime` for grains +
   softs. Dette er én månedlig serie av ENSO-indeksen.

I tillegg trenger vi en API-kontrakt for `find_analog_cases` slik at
session 59 (K-NN-impl), session 60 (analog-driver-familie) og session
61 (UI-rendering) har et fast målpunkt.

Bruker har bekreftet (a) ENSO i `fundamentals` med `series_id="NOAA_ONI"`
istedenfor egen tabell, (b) `max_drawdown_pct` skal med i outcome-skjema.

## Beslutning

### B1: ENSO lagres i eksisterende `fundamentals`-tabell

`series_id = "NOAA_ONI"` følger samme (series_id, date, value)-pattern som
FRED-data. Ingen ny tabell, ingen ny DataStore-getter, ingen ny DDL.
`get_fundamentals("NOAA_ONI", last_n=...)` returnerer pd.Series av månedlige
ENSO-verdier — eksakt det K-NN-driveren trenger.

Fundamentals-tabellen vil dermed inneholde to typer serier:
- FRED-økonomiske (DGS10, DTWEXBGS, DGS2, T10YIE, ...)
- NOAA ONI

Hvis vi senere får > 3 ikke-økonomiske serier i samme tabell, splitter vi
til en generisk `timeseries`-tabell med `source` som ekstra kolonne. Ikke
nå — premature.

### B2: Ny `weather_monthly`-tabell

Dedikert tabell, ikke utvidelse av `weather`-tabellen. Begrunnelse:

- Daglig vs månedlig granularitet er strukturelt ulike — pakke dem i samme
  tabell krever en `period`-kolonne og fylle daglig-felt med NULL for
  månedlige rader (eller omvendt).
- Daglig `weather` brukes (i fremtiden) for setup-trigger-logic
  (vær-event-vinduer); månedlig `weather_monthly` brukes for K-NN-
  feature-extraction. Forskjellige konsumenter, forskjellige queries.
- Pre-aggregerte felt (`hot_days`, `dry_days`, `water_bal`) er ikke en
  funksjon av kolonnene i `weather` (`tmax`/`tmin`/`precip`/`gdd`) —
  de er beregnet med ekstra parametre (terskler) som hører i fetch-
  laget eller ekstern aggregator. Lagrer dem som data, ikke som derived.

**DDL:**

```sql
CREATE TABLE IF NOT EXISTS weather_monthly (
    region    TEXT NOT NULL,
    month     TEXT NOT NULL,    -- "YYYY-MM"
    temp_mean REAL,
    temp_max  REAL,
    precip_mm REAL,
    et0_mm    REAL,
    hot_days  INTEGER,
    dry_days  INTEGER,
    wet_days  INTEGER,
    water_bal REAL,
    PRIMARY KEY (region, month)
)
```

**Pydantic-schema:** `WeatherMonthlyRow` med samme felt, alle målinger
valgfri (NULL-able). `month` er `str` matching regex `r"^\d{4}-\d{2}$"`
for å fange typo-feil ved migrering.

**Region-konvensjon:** samme som `weather`-tabellen. 14 regioner fra
`agri_history/` (us_cornbelt, brazil_mato_grosso, brazil_coffee,
sea_palm, west_africa_cocoa, ...). Region-id er en logisk tag, ikke en
GPS-koordinat.

**API:**
- `append_weather_monthly(df) -> int` — `df` må ha kolonnene `region`,
  `month`; resterende felt valgfri. INSERT OR REPLACE på PK.
- `get_weather_monthly(region, last_n=None) -> pd.DataFrame` —
  sortert på month ASC. Multi-column. Kaster `KeyError` hvis region
  ikke finnes (samme pattern som `get_weather`).

### B3: Ny `analog_outcomes`-tabell

Lagrer pre-beregnede forward-utfall for hver historiske ref-dato. Driver-
laget bruker dette til å rapportere hit-rate + snitt-return for
K-NN-naboer.

**DDL:**

```sql
CREATE TABLE IF NOT EXISTS analog_outcomes (
    instrument          TEXT    NOT NULL,
    ref_date            TEXT    NOT NULL,    -- "YYYY-MM-DD"
    horizon_days        INTEGER NOT NULL,    -- 30 eller 90 (eller annet)
    forward_return_pct  REAL    NOT NULL,    -- (close_t+H / close_t - 1) * 100
    max_drawdown_pct    REAL,                -- min(close_t..t+H / close_t - 1) * 100, NULL hvis ikke beregnet
    PRIMARY KEY (instrument, ref_date, horizon_days)
)
```

**Pydantic-schema:** `AnalogOutcomeRow`. `forward_return_pct` påkrevd
(grunnen til at raden eksisterer); `max_drawdown_pct` valgfri (NULL hvis
beregner droppet det av kostnadshensyn — selv om vi per Q-svar inkluderer
det by default).

**Hvorfor lagre `forward_return_pct` istedenfor å beregne on-the-fly fra
`prices`?**

- K-NN spør om "outcomes for N naboer". Naivt JOIN ville krevd N pris-
  oppslag per query. Med pre-beregnet tabell er det én SELECT.
- Forward-return-vinduet kan strekke utover slutten av prishistorikken
  (en obs fra forrige uke har ennå ikke 30 dagers forward); ved
  pre-beregning kan vi rett og slett unnlate å skrive raden — caller
  trenger ikke håndtere "missing future data".
- Hit-terskel (`outcome_threshold_pct`, default 3%) hører i driver-
  config (per bruker-svar Q3 i tidligere session): driver beregner
  `hit = forward_return_pct >= threshold`. Lagrer rå return, ikke
  binary hit.

**API:**
- `append_outcomes(df) -> int` — kolonner instrument, ref_date,
  horizon_days, forward_return_pct, max_drawdown_pct (siste valgfri).
- `get_outcomes(instrument, ref_dates, horizon_days) -> pd.DataFrame`
  — batch-lookup. `ref_dates` er liste/sequence av ISO-datoer (typisk
  K-NN-naboer). Returnerer rader for de som finnes; manglende
  rapporteres ikke (ingen exception).
- `has_outcomes(instrument, horizon_days) -> bool` — staleness-helper.

### B4: `find_analog_cases`-API-kontrakt (impl venter til session 59)

```python
def find_analog_cases(
    self,
    instrument: str,
    query_dims: dict[str, float],
    asset_class: str,
    *,
    k: int = 5,
    dim_weights: dict[str, float] | None = None,
    horizon_days: int = 30,
    min_history_days: int = 365,
) -> pd.DataFrame:
    """Returner K nærmeste historiske naboer for instrument basert på
    weighted Euclidean distance på normaliserte dim-verdier.

    Returnerer pd.DataFrame med kolonner:
        ref_date, similarity, forward_return_pct, max_drawdown_pct

    `query_dims` er {dim_name: current_value}, hentet fra ferskeste
    observasjoner i DataStore.

    `dim_weights` default = uniform 1.0 per dim. § 6.5-vekter kan
    overstyres via driver-params eller asset-klasse-config.

    `horizon_days` matches mot `analog_outcomes.horizon_days` —
    forskjellige drivere kan be om ulike horisonter (30/90).

    `min_history_days` filtrerer bort referanse-datoer som er for
    nye til å ha gjennomgått full forward-return-vindu (avhengig av
    horizon_days + buffer).

    Tom DataFrame hvis ingen kandidater (instrument mangler outcomes,
    eller historikken er for kort).
    """
```

**Normalisering:** z-score per dim over hele historikken, slik at
weighted Euclidean ikke domineres av dimensjoner med stor amplitude
(f.eks. real_yield_chg5d i basispoints vs cot_mm_pct i 0..100).
Normaliserings-statistikk beregnes ved query-tid (ikke pre-cached) i
første versjon — billig nok for K=5 og ~3000-5000 historiske datoer
per instrument.

**Asset-klasse-til-dim-mapping:** hardkodet i en konstant i
`bedrock.data.analog` (ny modul, session 59). Følger PLAN § 6.5-tabellen
slavisk per Q2-instruks (audit-rapport § 5.1). Brudd på § 6.5 håndteres
som flagg i audit, ikke som stille fallback.

### B5: Eksempel-driverer (session 60, ikke i denne ADR)

For å illustrere hvordan K-NN-output kobles til scoring:

```python
@register("analog_hit_rate")
def analog_hit_rate(store, instrument, params):
    asset_class = params["asset_class"]
    threshold = params.get("outcome_threshold_pct", 3.0)
    horizon = params.get("outcome_window_days", 30)
    k = params.get("analog_k", 5)
    # ... extract query_dims ...
    neighbors = store.find_analog_cases(
        instrument, query_dims, asset_class,
        k=k, horizon_days=horizon,
    )
    if neighbors.empty:
        return 0.0
    hit_rate = (neighbors["forward_return_pct"] >= threshold).mean()
    # Map hit_rate (0..1) til driver-score (0..1) via terskel-trapp
    return _grade_hit_rate(hit_rate)
```

`outcome_threshold_pct` + `outcome_window_days` per asset-klasse-
overstyrbar via `config/defaults/`-inheritance (per Q3-svar).

## Konsekvenser

**Brudd på invariant:** STATE invariants sier "DataStore-API låst (fra Fase 2)
... Schema-endring krever ADR + migrerings-plan." Denne ADR-en er det
formelle skjema-endrings-grunnlaget. Tre nye API-funksjoner
(`append_weather_monthly`, `get_weather_monthly`, `append_outcomes`,
`get_outcomes`, `has_outcomes`, `find_analog_cases`) — alle additiver,
ingen breaking. To nye DDL-tabeller — additive, eksisterende getters
uberørt.

**Migrering:**
- `weather_monthly`: backfill fra `~/cot-explorer/data/agri_history/<region>.json`
  (session 58). Engangsoperasjon, idempotent via INSERT OR REPLACE på PK.
- `analog_outcomes`: backfill fra `prices`-tabellen (session 58, etter
  prices er backfillet). Beregnes i Python (rolling-window over Series).
- ENSO: `bedrock backfill enso --from 2010` (ny CLI-subkommando, session
  58). Idempotent.

**Driver-laget:** uberørt i denne sessionen. Eksisterende `sma200_align`/
`momentum_z`/`currency_cross_trend` rører ikke nye tabeller. Nye
`analog`-drivere kommer i session 60.

**Test-strategi:** alle nye API-funksjoner har unit-tester med
in-memory SQLite. NOAA ONI-fetcher har logical test mot static
ASCII-fixture (ikke ekte HTTP) per bedrock-konvensjon.

## Alternativer vurdert

**A1 (forkastet): Egen `enso`-tabell.** Ville krevd ny DDL + ny getter.
ONI er strukturelt en (key, date, value)-tidserie — passer i
`fundamentals` uten å introdusere kompleksitet. Splitt utsettes til
> 3 ikke-økonomiske serier (per bruker-bekreftelse).

**A2 (forkastet): Utvide `weather`-tabellen med månedlig-felt og en
`period`-kolonne.** Ville krevd å fylle daglig-felt med NULL for
månedlige rader (eller omvendt). Lager en sparse, vanskelig-å-query
tabell. Separasjon er klart bedre.

**A3 (forkastet): Lagre `hit`-binary i `analog_outcomes` istedenfor rå
`forward_return_pct`.** Per Q3-svar er terskel driver-config; å baking
den inn i data ville låse oss til én terskel og kreve re-backfill ved
endring.

**A4 (forkastet): Lagre `forward_return_pct` i en separat tabell per
horisont (`analog_outcomes_30d`, `analog_outcomes_90d`).** PK
(instrument, ref_date) ville da vært naturlig. Men § 6.5 nevner ikke
hvor mange horisonter vi ender opp med — kan bli 7d/14d/30d/60d/90d.
N tabeller skalerer dårlig. PK-tillegg `horizon_days` er den ryddige
løsningen.

**A5 (forkastet): Pre-cache normaliserings-statistikk for K-NN.**
Premature optimization. Z-score over ~5000 datoer × 4 dim er ms-skala
i pandas. Cacher hvis profilering viser behov.

## Referanser

- PLAN § 6.5 (analog-matching dim per asset-klasse)
- `docs/data_audit_2026-04.md` § 5 (K-NN-feasibility per asset-klasse)
- `docs/data_audit_2026-04.md` § 6 (beslutninger A-D)
- ADR-002 (SQLite-valg)
- STATE invariants (DataStore-API-lås fra Fase 2)
