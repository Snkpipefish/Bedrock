# ADR-002: SQLite + pandas som storage-backend (supersederer § 6.1 DuckDB/parquet-valget)

Dato: 2026-04-24
Status: accepted
Fase: 2

## Kontekst

PLAN.md § 6.1 valgte opprinnelig **DuckDB + parquet** som storage-backend
for Bedrock: filbasert, null-tjeneste, pandas-native, med SQL-interface.
Begrunnelsen var at en senere migrering til ArcticDB kunne gjøres som en
endags-jobb hvis vi vokste ut.

Ved oppstart av Fase 2 ble det oppdaget at produksjons-hardwaren (Pentium
T4200, 2008) mangler SSE4.2 og AVX. Både `duckdb`, `pyarrow` (som pandas
trenger for parquet-lesing) og `fastparquet`-pipeline via `cramjam` krasjer
umiddelbart ved import med `Illegal instruction`. Moderne binære wheels for
disse pakkene er bygget med minimum SSE4.2 (pyarrow) eller AVX2 (duckdb),
og pre-kompilert CPU-dispatch hopper ikke tilbake til en fallback på så
gammel hardware.

Dette er ikke en Fase 2-intern diskusjon — alt arbeid i Bedrock må kjøre
på samme hardware i produksjon. Alternativer vurdert:

- Bygge pyarrow/duckdb fra kilde med flags: antagelig fortsatt avhengig av
  SIMD-kall i innebygde biblioteker (Arrow, DuckDB core).
- Finne eldre versjoner fra pre-2021 som ikke krevde SSE4.2: disse er ikke
  kompatible med pandas 2.x og mangler sikkerhetsoppdateringer.
- Parkere Fase 2 til hardware oppgraderes: skyver hele Bedrock-leveransen.

## Beslutning

**SQLite + pandas** som storage-backend. SQLite er del av Python stdlib,
bygget uten SIMD-krav, og har eksistert i 20+ år på all hardware vi bryr oss
om. pandas leser via `pd.read_sql` og skriver via `sqlite3.executemany`
(eller `pd.to_sql`) — ingen mellomledd som krever CPU-features utover det
SQLite selv trenger.

## Konsekvenser

Positive:
- Kjører garantert på nåværende og fremtidig hardware.
- Null eksterne tjenester; én `.db`-fil på disk med WAL-transaksjoner.
- Schema-migrering skjer via vanlige `ALTER TABLE`/ny `CREATE TABLE`-DDL-er
  i `bedrock.data.schemas`.
- `DataStoreProtocol`-kontrakten er uendret fra Fase 1. Drivere og
  setup-generator ser ingen forskjell på om store er SQLite, DuckDB eller
  parquet — `get_prices(instrument, tf, lookback) -> pd.Series`.
- Spørringer mot én instrument/tf er billige: indeksert primary key
  `(instrument, tf, ts)` gir O(log n) oppslag.

Negative:
- Mister DuckDBs kolonnestore-ytelse for aggregert analyse. Analog-søk i
  § 6.5 vil lese hele instrument-historikken inn i pandas og filtrere i
  minnet. På 10 års dagspriser (~2500 rader per instrument × ~25
  instrumenter = 62 500 rader totalt) er dette helt kurant.
- Mister parquet-filformat som "håndterbar filstruktur per kilde". Alt
  ligger i én SQLite-fil; backup = `cp bedrock.db`.
- Ingen SQL CLI utenfor Python (kan brukes `sqlite3 bedrock.db` om ønsket).

Nøytrale (verdt å nevne):
- Ved senere hardware-oppgradering kan vi migrere til DuckDB + parquet uten
  å endre drivere eller Engine: rewrite kun `bedrock.data.store.DataStore`
  for å lese/skrive parquet. En eksport-CLI fra SQLite til parquet er
  trivial (`pd.read_sql(...).to_parquet(...)`). Dette er en endags-jobb,
  samme argument som PLAN § 6.1 opprinnelig brukte for ArcticDB.
- PLAN.md § 6.1, 6.2, 6.3 oppdateres i samme commit som ADR-en legges til.

## Alternativer vurdert

- **Alternativ A — bygge pyarrow/duckdb fra kilde.** Usikker på om det
  hjelper; SIMD-avhengighet kan sitte i tredjeparts-biblioteker innbakt i
  arrow/duckdb (fx. snappy/zstd-varianter). Lang byggetid på svak CPU.
  Forkastet.
- **Alternativ B — CSV + pandas.** Enklest mulig, men ingen indeks, linear
  scan ved hver get_prices. Skalerer dårlig for 10 års historikk over
  25 instrumenter. Forkastet.
- **Alternativ C — parkere Fase 2 til hardware oppgraderes.** Bryter
  momentet og tvinger driver-utvikling til å forbli mot InMemoryStore-stub.
  Forkastet.

## Related: SIMD-sensitive dependency pinning

Binær-wheels for numeriske Python-biblioteker bygges med stadig nyere
CPU-instruksjons-sett. Wheels som fungerte på `pandas 2.3 + numpy 2.2`
i dag kan krasje på samme hardware i morgen hvis en transitiv oppgradering
drar inn en nyere numpy som bruker AVX2 internt.

Vi oppdaget dette konkret under Fase 2 session 6 da `pip install` av
`duckdb`/`pyarrow` også oppgraderte numpy; pandas begynte å `Illegal
instruction`-krasje fordi `pandas.compat.pyarrow` prøver soft-import av
pyarrow ved oppstart.

**Constraint (generelt):** alle SIMD-sensitive avhengigheter pinnes med
øvre grense til nærmeste minor som er verifisert å kjøre på produksjons-
CPU-en. Når en avhengighet legges inn, må vi stille spørsmålet: "bruker
denne pre-kompilert numerisk kode?" Hvis ja → pin til verifisert range.

**Kjente SIMD-sensitive pakker** (per 2026-04-24):

| Pakke | Grunn | Håndtering |
|---|---|---|
| `numpy` | bygges med SIMD (AVX2) fra 2.3+ (varsler allerede i 2.2) | pin `>=2.2,<2.3` |
| `pandas` | avhenger av numpy; har soft-import av pyarrow | unngå pyarrow-wheel |
| `pyarrow` | bygges med SSE4.2 minimum | ikke installere |
| `duckdb` | bygges med AVX2 minimum | ikke installere |
| `fastparquet` | avhenger av cramjam (SIMD) | ikke installere |
| `scipy` | bygges med SIMD i senere versjoner | pin når introdusert |
| `numexpr` | eksplisitt SIMD-bibliotek | pin når introdusert |

**Oppgraderings-policy:** oppgradering av en SIMD-sensitiv avhengighet
krever (1) lokal test `python -c "import X"` på produksjons-CPU-en,
(2) full `pytest` grønn, (3) oppdatering av denne tabellen. Minor-
oppgradering er ikke automatisk trygt selv med grønn CI, fordi CI-runnere
har moderne CPU-er og vil ikke fange krasjen.

## Migreringsvei tilbake til DuckDB/parquet

Hvis hardware oppgraderes og vi ønsker kolonnestore:

1. Skriv eksport-CLI: `bedrock data export-to-parquet data/parquet/`
   (én parquet-fil per tabell, eller per instrument/tf).
2. Rewrite `DataStore.__init__` til å peke på parquet-mappe + åpne DuckDB-
   connection.
3. Bytt ut `pd.read_sql` med `duckdb.sql(...).df()`. Skjema-konstanter
   blir `PRAGMA`-er eller DuckDB-DDL.
4. Ingen endring i drivere, Engine, tester.

## Referanser

- `PLAN.md` § 6 (superseder)
- CPU: `cat /proc/cpuinfo | head -5` — "Pentium(R) Dual-Core CPU T4200"
- Krasj-signatur: `Illegal instruction (core dumped)` ved `import pyarrow`
  eller `import duckdb`.
- `docs/decisions/001-one-engine-two-aggregators.md` (urelatert, ADR-mønster)
