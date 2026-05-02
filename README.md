# Bedrock

Trading-system som samler markedsdata, scorer asymmetriske setups på reelle
støtte/motstandsnivåer, og handler godkjente setups via cTrader-bot.
Config-drevet scoring (YAML + Python-driver-registry) gjør at nye regler
legges til uten kode-endring.

> ⚠️ **Forskningskode — ikke produksjonsklar for andre brukere.**
> Dette er forfatterens personlige trading-stack, åpen kun for
> innsyn/studie. Hovedlogikk, sizing-parametre og INSTRUMENT_MAP er
> tilpasset én spesifikk megler-konto (Skilling cTrader). Ingen
> garanti for korrekthet, lønnsomhet, eller kompatibilitet med annen
> oppsett. Trading med ekte penger på basis av denne koden kan føre
> til **totalt tap**. Se [LICENSE](LICENSE) for full disclaimer.
> Kjør aldri `--live` uten ≥24t demo-soak + manuell verifikasjon.

## Status

**Fase 12 — parallell-drift** (sub-fase 12.10 follow-up Spor F LUKKET).
Bedrock kjører nå live demo-bot mot cTrader/Skilling med **22 instrumenter**
på tvers av FX, metals, energy, indices, crypto og soft commodities.
Cot-explorer (forgjenger) kjøres parallelt inntil cutover i Fase 13.

Live-tall (per 2026-05-02):
- **22 instrumenter** scoret hver 5. min (market hours), 132 setup-entries
  per syklus (3 horisonter × 2 retninger × 22 instrumenter)
- **96 registrerte drivere**, 83 wired i instrument-YAMLer
- **19 fetch-runners** (FRED, CFTC COT, ICE COT, EIA, COMEX, NASS, WASDE,
  AGSI/ALSI, BDI, USGS seismic, NOAA ENSO, Forex Factory calendar, ...)
- **2814 tester** grønne, pyright `src/` 0 errors
- Web-UI live på `127.0.0.1:5100/` (faner: Setups financial / agri /
  Skipsloggen / Kartrommet / Drivere / Admin)

Se `STATE.md` for løpende sesjonshistorikk og `PLAN.md` for full roadmap.

## Arkitektur

```
fetch/        → SQLite (data/bedrock.db)
                    ↓
engine/ + drivers (96 registrerte) + YAML-regler (config/instruments/*.yaml)
                    ↓
orchestrator/ → score per (instrument, horizon, direction) med direction-
                asymmetric scoring (ADR-006) + asymmetrisk publish-floor
                    ↓
setups/       → entry/SL/TP fra ekte støtte/motstand + hysterese
                    ↓
signal_server/ (Flask + waitress) → /bot/signals adapter-payload
                    ↓
bot/          → cTrader Open API (Twisted reactor) → demo/live trades
                    ↓
web/ + UI-endpoints → Skipsloggen / Setups / Pipeline-helse / Drivere / Admin
```

Detaljert mappetre i `PLAN.md § 3.1`.

## Komponenter

| Modul | Funksjon |
|---|---|
| `bedrock.fetch` | Datakilde-fetchere med smart-skip + retry; CSV-fallback for fragile kilder |
| `bedrock.data` | DataStore — SQLite-wrapper med låst API for prices/COT/fundamentals/weather/outcomes |
| `bedrock.engine` | Scoring-motor + driver-registry; én motor, to aggregatorer (financial/agri) |
| `bedrock.setups` | Asymmetric setup-bygger med hysterese + slot-hash-stabilitet |
| `bedrock.orchestrator` | Glue mellom engine + setups, returnerer `OrchestratorResult` med (horizon, direction)-entries |
| `bedrock.signal_server` | Flask + waitress; `/bot/signals` adapter, `/api/ui/*` UI, `/admin/rules` editor |
| `bedrock.bot` | cTrader Open API klient, candle-buffere, posisjons-management, daily-loss-state |
| `bedrock.cli` | `bedrock backfill *`, `bedrock signals-all`, `bedrock server`, `bedrock systemd install` |

## Datakilder (per Spor F-lukking)

| Kategori | Kilder |
|---|---|
| **Pris** | Yahoo Finance (daily + intraday) |
| **CFTC COT** | Disaggregated + legacy Commitments of Traders (auto-discovery via YAMLer) |
| **ICE COT** | Brent, Gasoil, soft commodities (smart-skip på siste tirsdag) |
| **Macro/Yield** | FRED (DGS10, T10YIE, DXY, VIX, AAA10Y/BAA10Y, NFCI, WALCL, IRLTLT01\*, …) |
| **Energy** | EIA Open Data v2 (crude/gasoline/natgas inventories), AGSI+/ALSI EU gas storage, IIP remit |
| **Metals** | COMEX warehouse (metalcharts.org), USGS seismic (mining-region-vekter) |
| **Agri** | USDA NASS (crop progress + condition), USDA WASDE (S2U via ESMIS XML), NOAA ENSO ONI, ERA5 weather, Conab (Brazil), UNICA (sugar), IGC stocks, Drought Monitor, FAS ESR exports, BDI via BDRY ETF, manuell event-CSV |
| **Sentiment** | AAII investor sentiment, FedSpeak news intel, crypto sentiment, treasury auction demand |
| **Calendar** | Forex Factory high-impact econ-events |

## Oppsett

```bash
# Installer uv
curl -LsSf https://astral.sh/uv/install.sh | sh

cd ~/bedrock
uv sync --all-extras
uv run pre-commit install

# Hemmeligheter (ikke i repo) — kopier mal og fyll inn
cp .env.example ~/.bedrock/secrets.env
chmod 600 ~/.bedrock/secrets.env
# Rediger inn FRED_API_KEY, BEDROCK_NASS_API_KEY, BEDROCK_EIA_API_KEY,
# CTRADER_CLIENT_ID/CLIENT_SECRET/ACCESS_TOKEN/REFRESH_TOKEN/ACCOUNT_ID, ...

# Backfill data (eksempel)
uv run bedrock backfill prices --from 2020-01-01
uv run bedrock backfill cot --from 2020-01-01
uv run bedrock backfill crop-progress --year 2024 --year 2025 --year 2026

# Generer signals
uv run bedrock signals-all --bot-only --output data/signals_bot.json

# Start UI/signal-server
uv run bedrock server --host 127.0.0.1 --port 5100

# Tester
uv run pytest                                # full suite (~2 min)
uv run pytest -k "instrument or whitelist"   # scoped
uv run ruff check . && uv run pyright src/
```

## Drift (systemd)

`bedrock systemd install` genererer + linker user-units fra
`config/fetch.yaml`. Aktive timers (per 2026-05-02):

```
bedrock-fetch-prices.timer            (daglig 00:40)
bedrock-fetch-fundamentals.timer      (daglig 02:30)
bedrock-fetch-weather.timer           (daglig 03:00)
bedrock-fetch-seismic.timer           (daglig 04:00)
bedrock-fetch-agsi.timer              (daglig 06:00)
bedrock-fetch-alsi.timer              (daglig 06:05)
bedrock-monitor-alert.timer           (daglig 06:40)
bedrock-fetch-crypto_sentiment.timer  (daglig 07:00)
bedrock-fetch-news_intel.timer        (2× daglig 06:30/18:30)
bedrock-signals-bot-intraday.timer    (Mon-Fri *5min 06-21 Oslo)
+ wasde / nass-crop-progress / bdi / cot_ice / eia_inventories / comex /
  calendar_ff / enso / outcomes-roll
```

`bedrock-server.service` (system-unit) holder UI online 24/7.
`bedrock-bot.service` (user-unit) handler demo via cTrader.

## Sikkerhet

- **Hemmeligheter aldri i repo.** `~/.bedrock/secrets.env` (chmod 600)
  ligger utenfor repo og blokkeres av `.gitignore` (`.env`, `*.env`,
  `secrets/`, `~/.bedrock/`).
- Python leser via `bedrock.config.secrets.get_secret(name)` —
  prioriterer env-var, faller tilbake til `~/.bedrock/secrets.env`.
  Aldri hardkodet, aldri i YAML, aldri i UI.
- Bot-credentials (cTrader Open API) leses via systemd
  `EnvironmentFile=` fra samme fil; auto-refresh av `CTRADER_ACCESS_TOKEN`
  håndteres av `bedrock.bot.refresh.py` (skriver tilbake til
  secrets.env).
- Admin-UI gated bak `ADMIN_CODE_HASH` (SHA-256, ikke klartekst);
  endepunkter deaktivert hvis hash ikke satt.

## Dokumentasjon

- `CLAUDE.md` — agentinstruks for AI-assistert utvikling (session-disciplin)
- `PLAN.md` — full masterplan med fase-roadmap (Fase 0 → Fase 13 cutover)
- `STATE.md` — sesjonshistorikk (newest first), invariants, åpne spørsmål
- `docs/decisions/` — Architecture Decision Records (ADR-001 .. ADR-008)
- `docs/commit_convention.md` — conventional commits
- `docs/branch_strategy.md` — Nivå 1 (commit-til-main) → Nivå 3 (PR-flyt) ved Fase 12
- `docs/driver_authoring.md` — `(store, instrument, params) → float`
- `docs/rule_authoring.md` — YAML-schema for instrument-regler

## Lisens

All Rights Reserved. Se [LICENSE](LICENSE) for full tekst inkl.
no-warranty- og trading-disclaimer.

Klone for personlig studie er OK; redistribusjon, hosting eller
kommersiell bruk krever skriftlig samtykke fra forfatter.
