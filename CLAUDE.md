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
4. Bekreft til bruker: "Fortsetter på [task]. Blockers: [...]. Jeg starter med [handling]."
5. Vent på bekreftelse eller ny retning

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

**Gjeldende modus: Nivå 1 (enkel) — Fase 0 til og med Fase 10.**

- Commit direkte til `main`. Ingen feature-branches, ingen PR under utvikling.
- Auto-push-hook (`.githooks/post-commit`) sender hver commit til `origin/main` umiddelbart. Ingen manuell `git push`.
- Commit-format: conventional commits — se `docs/commit_convention.md`
- Én logisk endring per commit. Tester grønne før commit.
- `STATE.md`-commits holdes separate fra kode-commits (type `state:`).
- Aldri: force-push, amend etter push, commit av hemmeligheter.
- Fase-slutt markeres med tag: `v0.X.0-fase-Y`

**Overgang til Nivå 3 (feature-branches + PR) aktiveres ved Fase 10-11** når vi
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
