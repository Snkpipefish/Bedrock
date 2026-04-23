# Bedrock

Trading-system med config-drevet scoring, asymmetriske setups på reelle nivåer,
cTrader-bot-integrasjon, og web-UI for bot-logg + setups + pipeline-helse.

## Komponenter

- **Scoring-motor** (én motor, to aggregatorer) — leser YAML-regler + Python-drivere
- **Setup-generator** — bygger entry/SL/TP på reelle støtte/motstand fra historikk
- **Data-lag** — DuckDB + parquet for tidsserier og analog-matching
- **Fetch-laget** — alle eksisterende datakilder (CFTC COT, Euronext, ICE, FRED, ERA5, Conab, UNICA, ...)
- **Signal-server** — Flask-broker med `/signals`, `/push-alert`, `/kill`, `/admin/rules`
- **Bot** — refaktorert cTrader-klient, bevart logikk, config-drevet
- **UI** — 4 faner (Skipsloggen / Financial / Soft commodities / Kartrommet) + skjult admin

## Status

Prosjektet er i Fase 0. Se `PLAN.md` for full roadmap, `STATE.md` for nåværende status.

## For utvikling

Start: les `CLAUDE.md` (session-disciplin) + `STATE.md` (nåværende task) + relevant
fase i `PLAN.md`.

### Oppsett

```bash
# Installer uv hvis ikke allerede
curl -LsSf https://astral.sh/uv/install.sh | sh

cd ~/bedrock
uv sync --all-extras
uv run pre-commit install

# Kjør tester
uv run pytest

# Lint + type-check
uv run ruff check .
uv run pyright
```

### Commit og branch

Les `docs/commit_convention.md` og `docs/branch_strategy.md`. Kort:

```bash
git checkout -b feat/engine-core
# ... arbeid, commits ...
git push -u origin feat/engine-core
gh pr create --base main
```

## Relatert

- Forgjenger og inspirasjon: `~/cot-explorer/` (GitHub Pages-dashboard, slås av ved Fase 11)
- Gamle bot og server: `~/scalp_edge/` (integreres, ikke kopieres blindt)

## Lisens

Proprietær — ikke for redistribusjon.
