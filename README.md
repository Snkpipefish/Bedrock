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
- **Bot mottar kun `published=True`** (score ≥ publish-floor). Demo-flagget
  som tidligere sendte alle entries (`BEDROCK_BOT_INCLUDE_UNPUBLISHED`)
  er av. Conflict-gate i orchestrator demoter svakere retning når både
  BUY og SELL klarerer publish-floor på samme (instrument, horizon) —
  forhindrer whipsaw på range-bound instrumenter.
- **Dedup per `(instrument, direction, horizon)`** — SCALP/SWING/MAKRO er
  uavhengige slots. En åpen scalp-buy hindrer ikke ny swing-buy eller
  makro-buy på samme instrument; samme triplet blokkeres fortsatt.
- **Trailing-stop per horisont × asset-gruppe.** SCALP bruker M15-ATR med
  2.5–3.5× mult (rask exit), SWING og MAKRO bruker H1-ATR med 3.5–7.0×
  mult (MAKRO ≈ 1.2–1.5×ATR-D1 for å overleve normale dagspullbacks).
  Mer volatile assets (natgas, crypto, edelmetaller, oil) får bredere
  trail enn FX/indeks. Definert i
  `src/bedrock/signal_server/bot_adapter.py:TRAIL_MULT_BY_HORIZON_GROUP`.

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

## Drivere og aggregatorer

**Drivere** er rene Python-funksjoner som returnerer en score `0..1` for ett
instrument i ett tidsvindu. Kontrakt (låst fra Fase 1):

```python
@register("driver_navn")
def driver_navn(store: DataStore, instrument: str, params: dict) -> float:
    ...
```

96 drivere er registrert per i dag, fordelt på domener:

| Domene | Eksempler |
|---|---|
| `positioning` | `positioning_mm_pct`, `cot_z_score`, `cot_ice_mm_pct` (CFTC + ICE COT MM-net %) |
| `macro` | `real_yield`, `dxy_chg5d`, `vix_regime`, `eia_stock_change`, `comex_stress`, `mining_disruption` |
| `structure` | `range_position`, `sma200_align`, `ema_stack` |
| `risk` | `vol_regime`, `event_distance`, `vix_term_ratio` |
| `agronomy` | `weather_stress`, `enso_regime`, `seasonal_stage`, `crop_progress_stage`, `wasde_s2u_change`, `disease_pressure`, `bdi_chg30d` |
| `currency` | `brl_chg5d`, `dxy_chg5d` (delt med macro) |
| `analog` | `analog_hit_rate`, `analog_avg_return` (k-NN over historiske outcomes) |
| `sentiment` | `aaii_bull_bear_z`, `news_intel_severity`, `crypto_sentiment_z` |
| `flow` | `treasury_auction_demand`, `seismic_disruption_pgm` |

**Aggregatorer** er den motsatte siden: én scoring-motor (`bedrock.engine`)
samler driverne i **familier** (positioning/macro/structure/risk/...),
beregner gjennomsnitt med YAML-vekter, og rapporterer en `GroupResult`
per (instrument, horisont, retning). To aggregator-typer eksisterer:

- **`FinancialRules`** — for FX/metals/energy/indices/crypto. Familier:
  positioning, macro, structure, risk, analog, sentiment.
- **`AgriRules`** — for grains/softs. Familier: outlook, weather, yield,
  cross, positioning, analog. Tar hensyn til sesong-fase + WASDE-rytme.

Hver instrument-YAML i `config/instruments/*.yaml` velger drivere ved
**navn** (ikke kode), tildeler **vekter** og setter **horisont-spesifikke
publish-floors** (asymmetrisk per BUY/SELL siden ADR-006). Engine bruker
`polarity: directional|neutral` per familie for å vite om driver-scoren
skal flippes ved SELL — neutral familier (vol_regime, analog) håndterer
asymmetri internt.

Se `docs/driver_authoring.md` + `docs/rule_authoring.md` for full kontrakt.

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

For en full step-by-step guide (engelsk) for å klone og kjøre på egen
maskin, se [INSTALL.md](INSTALL.md). Kort versjon:

```bash
# Installer uv
curl -LsSf https://astral.sh/uv/install.sh | sh

cd ~/bedrock
uv sync --all-extras
uv run pre-commit install

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

## Dokumentasjon

- `CLAUDE.md` — agentinstruks for AI-assistert utvikling (session-disciplin)
- `PLAN.md` — full masterplan med fase-roadmap (Fase 0 → Fase 13 cutover).
  **Merk:** planen er endret en del underveis (sub-faser 12.5–12.10 vokste
  organisk, nye datakilder/Spor er lagt til, Fase 13-cutover-design ble
  reformet i sub-fase 12.9). Bør revideres ved en senere anledning for å
  matche faktisk kode-tilstand før en ny stor fase åpnes.
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
