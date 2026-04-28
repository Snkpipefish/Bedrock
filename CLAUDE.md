# Bedrock — instruksjoner for Claude Code

Denne fila auto-lastes i hver session. Hold den kort — hver token her spises hver gang.

## Hva Bedrock er

Trading-system som samler markedsdata, genererer asymmetriske setups på reelle
støtte/motstandsnivåer, sender godkjente setups til cTrader-bot via signal_server,
og viser bot-logg + setups + pipeline-helse i web-UI. Config-drevet scoring (YAML +
driver-registry) slik at nye regler kan legges til uten kode-endring.

## Start av session (følg alltid)

1. Les denne fila (auto)
2. Les `STATE.md` fra topp til første `---`
3. Les relevant fase-seksjon i `PLAN.md` for gjeldende task
4. **Pipeline-helse-blikk** (sub-fase 12.6): kjør `bash scripts/session_health.sh`.
   Skriptet listet failed bedrock-services + dagens `overall_ok` fra monitor.
   Hvis output sier "RØD", flagg det som blocker før task — ikke bygg ny kode på
   et trasig datagrunnlag. Skriptet gjør ingen endringer, kun leser status.
5. Bekreft til bruker: "Fortsetter på [task]. Helse: [grønn|rød — X]. Blockers: [...]. Jeg starter med [handling]."
6. Vent på bekreftelse eller ny retning

## Slutt av session (følg alltid)

1. Commit alt ferdig kode til `main`.
   **Auto-push-hook** pusher automatisk til `origin/main` etter hver commit.
   Manuell `git push` er ikke nødvendig. Se `.githooks/README.md`.
2. Oppdater `STATE.md`:
   - Ny entry øverst i session log (dato, hva ble gjort, commits, neste)
   - Oppdater `Current state`-blokken
   - Legg til open questions
   - Oppdater invariants hvis relevant
3. Commit `STATE.md` separat med melding `state: session N avsluttet`
4. Fortell bruker: "Session logget. Neste: [X]."

## Git-regler (kort)

**Gjeldende modus: Nivå 1 (enkel) — Fase 0 til og med Fase 11.**

- Commit direkte til `main`. Ingen feature-branches, ingen PR under utvikling.
- Auto-push-hook (`.githooks/post-commit`) sender hver commit til `origin/main` umiddelbart. Ingen manuell `git push`.
- Commit-format: conventional commits — se `docs/commit_convention.md`
- Én logisk endring per commit. Tester grønne før commit.
- `STATE.md`-commits holdes separate fra kode-commits (type `state:`).
- Aldri: force-push, amend etter push, commit av hemmeligheter.
- Fase-slutt markeres med tag: `v0.X.0-fase-Y`

**Overgang til Nivå 3 (feature-branches + PR) aktiveres ved Fase 11-12** når vi
nærmer oss live-cutover. Da aktiveres også branch-beskyttelse på main, og Claude
Code bytter til feature-branch-flyt. Se `docs/branch_strategy.md` for full oppsett.

## Kode-konvensjoner

- Python 3.12, type hints på alle offentlige signaturer
- `ruff` for lint+format, `pyright` for types (nivå error)
- Pydantic v2 for alle data-schemaer
- Pytest for tester, pattern: `test_<hva>_<scenario>`
- Alle drivere bruker `@register("navn")` og signatur
  `(store: DataStore, instrument: str, params: dict) → float`
- Ingen hardkodede terskler — alt via YAML eller `Config`-objekt
- `tenacity` for retry, `structlog` for logging
- Aldri `bare except`. Minst `except Exception as e` med logging

## Test-filosofi

- **Logiske tester** ("gitt X-data, forvent Y-atferd") er primær testsuite
- Enhetstester er sekundære — kun for komplekse interne funksjoner
- Snapshot-tester i `tests/snapshot/` fanger utilsiktet drift
- Ingen PR mergas hvis tester ikke er grønne

## YAML-regler for config

- YAML har ALDRI logikk. Ingen uttrykk, ingen `eval`, ingen betingelser.
- YAML velger driver (ved navn) + parametre + vekt. Python beregner.
- Alle YAML-filer valideres med Pydantic-schema ved lasting — feil = hard fail

## Filer som eies av sessioner vs bruker

| Fil | Eier | Endringskadens |
|---|---|---|
| `PLAN.md` | Bruker + Claude Code (etter samtale) | Sjelden, alltid i egen commit |
| `STATE.md` | Claude Code (hver session) | Hver session |
| `CLAUDE.md` (denne) | Bruker, delvis Claude Code | Kun ved endret prosess |
| `config/instruments/*.yaml` | Bruker via admin-UI + Claude Code | Ofte, alltid med dry-run først |
| `src/**/*.py` | Claude Code | Fase-drevet |

## Beslutnings-retningslinje

Claude Code har full kontekst (PLAN, STATE, kode, docs) og skal ta
implementasjons-beslutninger selv. Brukerens tid er dyr; Claude's
standardmodus er **bestem og kjør**, ikke "forelegg valg".

### Bestem selv (ikke spør)

- **Rekkefølge på sub-tasks innen en åpen fase.** Bruk dependencies,
  risiko-for-omarbeid, og leveranse-verdi til å prioritere. Forklar kort
  (1-2 setninger) hvorfor rekkefølgen er valgt.
- **Mappe-plassering og modul-navngivning.** Følg eksisterende struktur
  (`src/bedrock/<domene>/<fil>.py`).
- **Intern modul-struktur, klasser vs funksjoner, helpers vs inline.**
  Optimer for lesbarhet og test-isolering.
- **Test-organisering.** `unit/` for små komponent-tester, `logical/`
  for atferds-tester, `snapshot/` for drift-fangst. Nye testfiler
  følger eksisterende navnekonvensjon.
- **Refactor vs nyskriv.** Når en komponent endres, vurder selv om
  eksisterende kode skal utvides eller byttes ut.
- **Pydantic-modell-struktur.** Felt-navn, valgfrihet, validering — så
  lenge det holder signal-schema v1 og låste API-kontrakter.

### Spør brukeren (via AskUserQuestion)

- **Trading-logikk og preferanser.** Horisont-terskler, R:R-minima,
  grade-terskler, asset-klasse-spesifikk atferd, hvor "harde" gates
  skal være. Disse påvirker faktiske trade-beslutninger.
- **UX-valg synlige for bruker.** CLI-flagge-navn, output-format,
  kommando-hierarki, admin-UI-interaksjoner.
- **Sikkerhet og secrets.** Hvor nøkler hentes fra, hva som logges,
  hva som maskes, tilgangs-grenser.
- **Scope-utvidelser utover gjeldende task.** Hvis Claude oppdager at
  en bedre løsning krever å gjøre mer enn det som er spurt om — flagg
  det, ikke bare utvid scope stille.

### Når i tvil

Foretrekk å bestemme selv og forklare kort, framfor å spørre. En
feil-rekkefølge er billig å rette (commit + re-order); en
avbrutt-for-å-spørre koster brukerens oppmerksomhet hver gang.

## Ikke-gjør (kommer fra tidligere feil)

- Ikke kopier scalp_edge-bot-logikk blindt. Fjern agri ATR-override (gammel bug).
- Ikke lag setup-persistence som lifecycle. Bruk determinisme + hysterese på generator.
- Ikke introduser nye HTML-filer. Vi har én UI (`index.html`) + én admin (`admin.html`).
- Ikke dropp fetch-scripts uten uttrykkelig godkjenning. Ubrukt data er billig;
  sletting kan være dyrt.
- Ikke legg logikk i YAML. Hvis du ser deg selv skrive uttrykk, legg det i en driver.

## Pekere

- Full masterplan: `PLAN.md`
- Commit-konvensjon: `docs/commit_convention.md`
- Branch-strategi: `docs/branch_strategy.md`
- Driver-forfattelse: `docs/driver_authoring.md`
- Rule-forfattelse: `docs/rule_authoring.md`
- Arkitektur-beslutninger: `docs/decisions/`
