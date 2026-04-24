# Bedrock trading-bot — kjøring

## Forutsetninger

- Python 3.12
- `uv sync` eller eksisterende `.venv` med bot-extras (`ctrader-open-api`,
  `twisted`, `requests`, `pydantic`, `PyYAML`)
- `config/bot.yaml` (valgfri — defaults i `bedrock.bot.config.BotConfig`)
- Signal-server kjørende på URL konfigurert i `startup_only.signal_url`

## Miljøvariabler

### Påkrevd — cTrader-credentials

| Variabel | Beskrivelse |
|---|---|
| `CTRADER_CLIENT_ID` | OAuth client ID fra cTrader dev-portal |
| `CTRADER_CLIENT_SECRET` | OAuth client secret |
| `CTRADER_ACCESS_TOKEN` | Access-token for ønsket konto |
| `CTRADER_ACCOUNT_ID` | cTrader account ID (heltall) |

Lastes via `bedrock.bot.ctrader_client.load_credentials_from_env()`. Mangler
→ `RuntimeError` og bot-exit 1.

### Valgfri

| Variabel | Beskrivelse |
|---|---|
| `BEDROCK_BOT_CONFIG` | Sti til `bot.yaml`. Default: `config/bot.yaml` |
| `SCALP_API_KEY` | API-nøkkel mot signal-server. Env-var-navnet leses fra `startup_only.signal_api_key_env` i bot.yaml (default `SCALP_API_KEY`). Mangel → warning, bot kjører uten nøkkel. |

Secrets skal ligge i `~/.bedrock/secrets.env` som systemd loader via
`EnvironmentFile=`. Aldri commit secrets til repoet.

## Starting

```sh
# Demo (Spotware demo-server)
PYTHONPATH=src .venv/bin/python -m bedrock.bot --demo

# Live (krever 'JA'-bekreftelse interaktivt)
PYTHONPATH=src .venv/bin/python -m bedrock.bot --live

# Med custom config-sti
PYTHONPATH=src .venv/bin/python -m bedrock.bot --demo --config /etc/bedrock/bot.yaml
```

Når `bedrock` er installert via `uv sync` (eller `pip install -e .`) kan
`PYTHONPATH=src` droppes.

## Signaler

| Signal | Effekt |
|---|---|
| `SIGHUP` | Reload `reloadable`-delen av bot.yaml. `startup_only`-endringer logges som warning men aktiveres ikke — krever restart. |
| `SIGTERM` | Clean shutdown. Reactor stoppes, exit 0. |
| `SIGINT` (Ctrl+C) | Samme som SIGTERM. |

SIGHUP-flyt:
1. Les bot.yaml på nytt
2. Valider via Pydantic
3. Muter eksisterende `ReloadableConfig`-instans in-place via
   `apply_reloadable_inplace` — alle bot-moduler ser nye verdier
   umiddelbart (ingen restart)
4. Hvis `startup_only`-felter er endret: logg liste som warning; gamle
   verdier forblir aktive til prosess-restart

Feil under reload (ugyldig YAML etc.) svelges og logges som error —
bot beholder gammel config og fortsetter uforstyrret.

## Systemd-oppsett (eksempel)

```ini
# /etc/systemd/system/bedrock-bot.service
[Unit]
Description=Bedrock trading bot
After=network-online.target

[Service]
Type=simple
User=bedrock
WorkingDirectory=/home/bedrock/bedrock
EnvironmentFile=/home/bedrock/.bedrock/secrets.env
ExecStart=/home/bedrock/bedrock/.venv/bin/python -m bedrock.bot --demo
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=30s
# Ikke sett TimeoutStopSec for kort — bot må få tid til å lukke posisjoner
TimeoutStopSec=60s

[Install]
WantedBy=multi-user.target
```

## Kjørings-logikk (fra start til trade)

1. **Oppstart:** `__main__.main()` parser argparse, laster creds + config,
   instansierer SafetyMonitor → CtraderClient → SignalComms → EntryEngine
   → ExitEngine, wirer alle callbacks.
2. **Reactor starter** via `client.start()` (Twisted). cTrader-klient
   connecter, autentiserer, henter symbol-liste, abonnerer på spots.
3. **EntryEngine.on_symbols_ready** kalles én gang etter symbol-liste
   — initialiserer candle-buffere og indikator-arrays for hvert sid.
4. **Historisk bootstrap:** 50 × 15m candles + 50 × 1H candles per
   symbol. EMA9 + ATR14 beregnes når buffer er full nok.
5. **Polling-loop** fetcher /signals + /kill fra signal-server adaptivt
   (20s hvis SCALP-watchlist aktiv, ellers 60s). `on_signals`-callback
   oppdaterer `EntryEngine.signal_data`.
6. **Per lukket 15m-candle:** `EntryEngine._on_candle_closed` evaluerer
   watchlist-signaler → filters → confirmation → execute. Deretter
   `ExitEngine.manage_open_positions` — P1-P5 exit-prioritet.
7. **Trade execution:** `_execute_trade_impl` gater via daily-loss, oil-
   geo, agri-session, korrelasjon → `client.send_new_order`.
8. **ExecutionEvent:** `ExitEngine.on_execution` flipper state til
   IN_TRADE, amender SL/TP (MARKET), logger åpning.
9. **Management:** trail, BE, weekend-SL-stramming via `amend_sl_tp`;
   partial/full close via `close_position`; PnL akkumuleres.
10. **Signal-mottatt stop:** SIGTERM/SIGINT → reactor stop → exit.

## Feilsøking

| Symptom | Sannsynlig årsak |
|---|---|
| "Mangler miljøvariabler" + exit 1 | En eller flere cTrader-env-vars ikke satt. Sjekk `~/.bedrock/secrets.env`. |
| Exit 78 | Auth-feil fra cTrader (token ugyldig/utløpt). Generer ny access-token og restart. |
| Exit 79 | Reconnect-budsjett overskredet. Indikerer vedvarende nett- eller auth-problem. |
| Exit 80 | > 50% av instrumenter mangler hos megler. Konto feilkonfigurert. |
| Bot-logg viser "SCALP_API_KEY ikke satt" warning | Signal-server autentisering deaktivert. OK for dev; sett env-var for prod. |
| SIGHUP gir "startup_only-felt endret" warning | Config-endring krever restart for å aktivere (signal_url, reconnect-budsjett etc.). |

## Test-kjøring (uten ekte cTrader)

```sh
PYTHONPATH=src .venv/bin/pytest tests/unit/bot/test_main.py -v
```

Smoke-testene bruker `build_bot()` uten å starte reactor — alle moduler
instansieres og callbacks wires, men ingen nettverk åpnes. Bruk dette
for CI-verifisering av wire-up-endringer.
