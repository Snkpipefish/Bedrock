# ADR-014: Cross-source data-arkitektur for *_surprise-drivere

Dato: 2026-05-02
Status: accepted
Fase: 12.10 follow-up Spor B (session 138)
Refererer til: PLAN § 22.6 Spor B, ADR-007 (fetch-port-strategi), ADR-008
(per-fetcher mapping), ADR-011 (backfill-policy)

## Kontekst

Sub-fase 12.10 §22.2 #5 spesifiserer 4 nye drivere i en ny `event`-familie
på SP500/Nasdaq/USDJPY/EURUSD:
- `nfp_surprise` (Non-Farm Payrolls actual vs forecast)
- `cpi_surprise` (CPI m/m actual vs forecast)
- `gdp_surprise` (GDP q/q actual vs forecast)
- `pce_surprise` (PCE Price Index actual vs forecast)

**Blocker:** Forex Factory `ff_calendar_thisweek.json` (eksisterende kilde
for `econ_events`-tabellen, drevet av `event_distance`-driveren) returnerer
KUN `forecast`/`previous`-felt — ikke `actual`. Dette er en velkjent FF-
begrensning (FF holder actual bak innloggings-screen for "premium"-brukere).

For å bygge surprise-drivere trenger vi **cross-source-join**: forecast
fra FF (det markedet konsensus forventet før event) × actual fra alternativ
kilde.

## Vurderte alternativer

### Alternativ A: Lisensiert calendar-feed (TradingEconomics, DailyFX, etc.)

- ✅ Én kilde, alt i ett: forecast + actual + previous
- ❌ Krever betalt API-key (~50-200 USD/mnd for TE)
- ❌ Bryter ADR-007 § 4 (gratis-only-default)

**Avvist** — vi har gratis-policy for kilder.

### Alternativ B: FRED cross-reference for actual

- ✅ FRED er gratis, stabilt, har lange historikker (10+ år)
- ✅ FRED-fetcher allerede portet (`bedrock.fetch.fred`)
- ✅ Hver av de 4 events har en motpart-FRED-serie:
  - NFP → `PAYEMS` (Total Nonfarm Employment, MoM Δ)
  - CPI → `CPIAUCSL` (CPI All Urban Consumers, MoM %)
  - GDP → `GDP` (GDP Q/Q advance/preliminary/final)
  - PCE → `PCEPI` (PCE Chain-Type Price Index, MoM %)
- ❌ Krever kobling-logikk: matche FF-event til FRED-observasjon på dato
- ❌ FRED-serier publiseres typisk samme dag som event (BLS/BEA-rapporter
  går simultant til FF og FRED), så timing-mismatch er liten

**Akseptert** — gratis, presedens, og koblings-logikken er overkommelig.

### Alternativ C: Web-scrape FF historisk-arkiv

- ✅ Gratis
- ❌ FF har anti-scraping (CAPTCHA, rate-limits)
- ❌ Skjørt — bryter når FF endrer HTML

**Avvist** — fragility.

## Beslutning

Bruk **Alternativ B**. Cross-source-join FF.forecast × FRED.actual.

### Schema-tillegg

`econ_events`-tabellen utvides med `actual`-kolonne:

```sql
ALTER TABLE econ_events ADD COLUMN actual TEXT;
```

`actual` er nullable. Eksisterende rader (skrevet via FF-fetcher) får
NULL inntil `populate_econ_actuals.py`-skriptet kjøres.

PK på (event_ts, country, title) endres ikke — én rad per event, populeres
av FF først (forecast), deretter actual via cross-source-join.

### Cross-source-join-logikk

Ny skript: `scripts/backfill/econ_actuals.py`. Per (event-title-pattern,
FRED-serie):

1. Henter alle econ_events der title matcher pattern + country=USD.
2. For hver event-rad, finn FRED-observasjon der observation_date er
   nærmest event-datoen (innenfor ±5 dager — FRED-data publiseres samme
   dag som BLS/BEA, men tidssone-skifte kan flytte 1 dag).
3. Beregn FRED-verdien som "actual" for surprise-drivere:
   - **PAYEMS:** MoM Δ (current - previous month) i tusen
   - **CPIAUCSL:** MoM % endring × 100
   - **GDP:** QoQ % endring (annualized, fra FRED-rapporten)
   - **PCEPI:** MoM % endring × 100
4. Skriv `actual` tilbake til econ_events via UPDATE.

### Driver-implementasjon

Felles helper `_econ_surprise_score(...)` med params:
- `title_pattern` (REQUIRED): substring som matcher FF-title (f.eks.
  "Non-Farm Employment Change", "CPI m/m", "GDP q/q Advance",
  "Core PCE Price Index m/m").
- `country` (REQUIRED): typisk "USD".
- `bull_when` (REQUIRED): "high" eller "low" — markedsreaksjon avhenger
  av asset:
  - SP500/Nasdaq: NFP høyt = bull (jobbvekst), CPI høyt = bear (Fed
    hawkish), GDP høyt = bull, PCE høyt = bear.
  - USDJPY: alle høye = bull (USD styrker seg på hawkish overraskelser).
  - EURUSD: alle høye = bear (USD opp = EURUSD ned).
- `lookback_days` (default 30): kun events innenfor siste N dager.
- `forecast_threshold` (default 0.0): minimum |forecast| for å beregne
  surprise (unngår divisjon på ~0).

Surprise = (actual - forecast) / max(|forecast|, threshold). Mappes til
0..1 via z-score-step (eller direkte step-trapp).

Defensive 0.5 hvis ingen events i vinduet eller actual mangler.

### Per-driver wirings

4 nye drivere, alle i samme `event`-familie:
- `nfp_surprise`, `cpi_surprise`, `gdp_surprise`, `pce_surprise`

Initial wirings (per § 22.2 #5 spec):
- SP500/Nasdaq event-familie: alle 4 drivere @ 0.25 hver = 1.00
- USDJPY/EURUSD event-familie: alle 4 drivere @ 0.25 hver = 1.00

### Backfill-omfang

Per ADR-011 § 1: 10-år rolling cutoff (2016-05 → 2026-05). FRED-historikk:
- PAYEMS: 1939+ (full historikk)
- CPIAUCSL: 1947+
- GDP: 1947+
- PCEPI: 1959+

Alle har full 10-år dekning. FF-historikk har gap (FF-arkivet er ikke
backfilt i bedrock — kun siste 7 dager). For å ha forecasts for 10 år
av events må vi enten:

- (a) Forhåndspublisert FF-arkiv via Wayback Machine (skjørt)
- (b) Hente FF-data forløpende fremover, og bygge surprise-historikk
  over tid

**Beslutning:** Akseptér gap. Drivere starter "live" når FF-fetchere har
samlet ≥3 mnd historikk. For å validere drivere før det, bruk **konstant-
forecast-tilnærming**: anta forecast = forrige rapports actual + sesongtrend.
Dette gir grov surprise-historikk for backtest-formål.

For initial-implementasjon i denne sub-fasen: drivere bruker kun (event,
actual)-rader hvor begge er kjente. Ingen kunstig forecast-fyll. Score er
defensive 0.5 hvis ingen surprise-events i lookback.

## Konsekvenser

### Positive

- Gratis kilde-mix (FF for forecast, FRED for actual).
- Bygger på eksisterende infrastruktur (econ_events + bedrock.fetch.fred).
- Nye drivere registrert i `event`-familien — ny bruk av `polarity:
  directional` (event-asymmetri er positiv-modulert i samme retning som
  market-bias).

### Negative

- Avhengighet av FF-kilde for forecast-historikk. Hvis FF endrer endpoint
  eller blokkerer, mister vi forecast-feed.
- Cross-source-join kan ha subtile timing-mismatches (FRED reviderer
  PAYEMS retroaktivt; FF logger original-rapport). Dokumenter via
  load_time-kolonner senere hvis nødvendig.
- Initial drivere har lav data-tetthet (NFP er månedlig = ~12 events/år;
  GDP kvartalsvis = ~4 events/år). Lookback-vindu må passe — default 30
  dager fanger NFP/CPI men savner ofte GDP.

### Neutral

- ADR følger samme mønster som tidligere ADR-er (kort kontekst, vurderte
  alternativer, beslutning + konsekvenser).
