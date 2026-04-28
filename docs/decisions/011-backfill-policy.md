# ADR-011: Backfill-policy for sub-fase 12.7-fetchere

Dato: 2026-04-28
Status: accepted
Fase: 12.7 R1 (session 119)
Refererer til: ADR-007 (fetch-port-strategi), ADR-008 (per-fetcher
mapping), PLAN § 19, `docs/horizon_refactor_audit.md`

## Kontekst

Sub-fase 12.7 Spor D (D0-D3, PLAN § 19.4) tar inn 13 nye fetchere + 5
utvidelser av eksisterende. Hver av disse trenger historikk fylt opp
før driver-laget kan bruke dataen meningsfullt.

To distinkte typer "backfill" eksisterer i kodebasen:

1. **Produksjons-`bedrock backfill <source>`-CLI** (`src/bedrock/cli/
   backfill.py`). Levert i Fase 3+ med stabil kontrakt: `--from`,
   `--to`, `--db`, `--dry-run`-mønster. Brukes av sysadmin og
   eventuelt cron for repeat-bruk når noko går galt med produksjons-
   fetcher-data eller når en fetcher porteres til bedrock og må
   re-fylle historikk på en kontrollert måte. Dette er et
   produksjons-overflate.

2. **Engangs-historikk-fyll** for et nytt fetcher-sett som
   introduseres i 12.7. Disse skal kjøres manuelt én gang (eller noen
   få ganger under utvikling), pacing-tunet for gratis API-er, ofte
   med ymse hacky-håndtering for arkiv-format-pussigheter, og er
   ikke ment å vedlikeholdes som en del av produksjons-overflaten.

Uten en eksplisitt policy vil samme begrep ("backfill") dekke begge
typer arbeid og det blir uklart om en ny fetcher skal få et nytt
`bedrock backfill <source>`-subkommando-entry eller bare et engangs-
script.

## Beslutning

Sub-fase 12.7-fetchere bruker **engangs-skripts** plassert i
`scripts/backfill/<source>.py`, separat fra produksjons-CLI-en, etter
disse retningslinjene:

### 1. Cutoff

Alle nye fetchere fyller historikk fra **2010-01-01** og framover (til
nåtid). Eldre data hentes ikke automatisk; instrumenter med kortere
data-historikk (typisk CFTC pre-2022 for visse kontrakter, jf. PLAN
§ 19.5 og STATE Data-gjeld) flagges som fundamental gap som må
aksepteres.

### 2. Kjøre-modus

Skriptene er **manuelt kjørbare** (ingen cron, ingen systemd-timer
automatisk). De forventes å bli kjørt én gang per fetcher-introduksjon,
typisk i samme session som fetcheren first-time-portes. Re-runs er
greit hvis man vil utvide vinduet eller fyller hull, men er ikke
planlagt vedlikehold.

### 3. HTTP-pacing

**Sekvensielle requests, ≥1.5 sekunders sleep mellom kall.** Ingen
parallelle HTTP-pakker mot gratis-kilder. Memory:
`free-api-no-parallel-requests` — gratis kilder krever sekvensielle
HTTP-kall. Eksisterende café-backfill (`backfill_conab_cafe.py`,
session 113) er presedens med 1.5s pacing + exponential backoff på
403-throttle.

Retry: kun exponential backoff på 4xx/5xx — **ingen fancy retry-
policy** utover dette. Skriptet får lov til å feile midt i kjøring;
operatør kjører på nytt med justerte fra/til-grenser.

### 4. Plassering og separation-of-concerns

- **Engangs-skripts:** `scripts/backfill/<source>.py`. Hver
  fetcher får sin egen fil. Filen har lov til å være "shitty":
  manuell kjøring, hardkodet sleep, ingen produksjons-grade
  feilhåndtering, ingen Pydantic-validering ved input.

- **Produksjons-CLI (`bedrock backfill <source>`)** er for
  produksjons-refresh + repeat-bruk og fortsetter uendret med
  etablert `--from`/`--to`/`--db`/`--dry-run`-kontrakt. Fasen for å
  promotere et engangs-script til CLI-subkommando er **ikke** en
  del av 12.7. Hvis en fetcher senere viser seg å trenge gjentatt
  kontrollert backfill (eks. porting til bedrock fra en gammel
  pipeline), kan den promoteres som egen leveranse — egen ADR ved
  behov.

- **Engangs-skripts skal ikke importeres fra produksjons-koden.**
  Eneste vei kode-kontakt er via `bedrock.data.store.DataStore` (og
  evt. `bedrock.data.repositories`) for å skrive til samme SQLite-
  fil. Ingen produksjons-modul har lov til å avhenge av et script i
  `scripts/backfill/`.

### 5. Format og naming

Filer heter `scripts/backfill/<source>.py` der `<source>` matcher
fetcher-navnet i `fetch.yaml` (eks. `baker_hughes.py`, `agsi.py`,
`fas_export_sales.py`). Hver fil har en `if __name__ == "__main__"`-
guard, en kommandolinje-flag for db-sti (default
`data/bedrock.db`), og en docstring øverst som forklarer kilde-URL,
cutoff, format-quirks, og forventet kjøre-tid.

### 6. Ingen produksjons-fetcher-forurensing

`src/bedrock/fetch/<source>.py` (produksjons-fetcher) skal **ikke**
inneholde kode som er skrevet for engangs-historikk. Hvis en
historikk-arbeidsmodus krever vesentlig annen logikk enn daglig
incremental-fetch, settes den i `scripts/backfill/<source>.py` og
ikke importeres tilbake. Dette holder produksjons-fetcher-koden
enkel og test-bar.

## Konsekvenser

### Positive

- Klar separasjon mellom produksjons-overflate (CLI) og engangs-
  arbeid (scripts).
- Engangs-skripts kan være pragmatiske og ufullkomne uten å skitne
  til produksjons-koden.
- Sekvensiell pacing matcher gratis-API-virkeligheten — vi unngår
  bans og mystiske 403-er som ville gjøre data-fyll uforutsigbar.
- 2010-cutoff er tilstrekkelig for 12m+36m percentil-vinduer
  (PLAN § 19.3) over flere fed-sykluser uten å invitere uendelig
  arkiv-arbeid for marginal nytte.

### Negative

- To måter å gjøre "backfill" på krever at neste utvikler vet
  forskjellen. Mitigeres av denne ADR-en + commit-konvensjon
  (engangs-skripts commit-meldinger heter
  `scripts(backfill): <source> historikk-fyll`).
- Engangs-skripts vedlikeholdes ikke som tester eller CI-kjørt kode.
  Hvis en kilde endrer URL-mønster eller schema senere, kan re-runs
  feile uten varsling. Akseptert: backfill-arbeidet er av-natur
  manuell og lav-frekvent.

### Nøytrale

- Eksisterende backfill-skripts (`backfill_conab_cafe.py`,
  `backfill_cftc_name_drift.py`, `backfill_euronext_optimized.py`,
  `backfill_tier2_history.py`, `backfill_usgs_seismic_history.py` —
  ligger i `scripts/`) fungerer som presedens. Disse kan flyttes til
  `scripts/backfill/` ved senere oppslag eller forbli for å bevare
  commit-historikken; ikke en del av 12.7-scope.

## Alternativer vurdert

### Alt α — All backfill via `bedrock backfill <source>`

Hver ny 12.7-fetcher får et nytt subkommando i produksjons-CLI-en.

- Pro: Én overflate, ensartet kontrakt.
- Con: Pro-forma `--from`/`--to`/`--dry-run`-implementasjon for
  hver kilde der vi i praksis bare vil kjøre én engangs-fyll. Bloat
  i CLI-en. Innfører testkrav på kode som ikke er produksjons-
  kritisk. Bryter "ingen logikk i produksjons-overflate som ikke er
  produksjons-relatert"-prinsippet.

### Alt β — Inline backfill i fetcher-koden

Hver fetcher har en "first-run-mode" som gjør historikk-fyll og en
"daily-mode" som gjør incremental.

- Pro: Én kodebase per kilde.
- Con: Forurenser produksjons-fetcher-koden med engangs-logikk.
  Vanskelig å test-isolere. Hvis 12.7-arkiv-format avviker mye fra
  daglig-format (typisk CSV vs PDF, eller arkiv-CSV med annet
  schema enn dagens CSV), tvinger denne tilnærmingen fram
  monstrøse if-grener.

### Alt γ (valgt) — Engangs-skripts i `scripts/backfill/<source>.py`

Beskrevet over.

## Referanser

- PLAN § 19 — sub-fase 12.7 master-plan.
- PLAN § 19.3 — låste beslutninger (12m+36m percentil-vinduer
  motiverer 2010-cutoff).
- `docs/horizon_refactor_audit.md` — kontekst for R1-leveransen.
- `scripts/backfill_conab_cafe.py` — presedens for sekvensiell
  pacing + 403-throttle backoff.
- Memory: `feedback_free_api_no_parallel.md` — gratis kilder krever
  sekvensielle HTTP-kall.
- ADR-007, ADR-008 — fetch-port-strategi som denne ADR-en
  utfyller.
