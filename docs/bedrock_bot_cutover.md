# Bedrock-bot cutover — sub-fase 12.9

**Status:** ÅPEN 2026-05-01 etter sub-fase 12.8 LUKKET. Erstatter
scalp_edge-bot som bedrocks cTrader-trading-grensesnitt.

**Trigger:** scalp_edge-bot har siden 2026-04-28 vært i auth-failure
crash-loop (CH_ACCESS_TOKEN_INVALID). Bruker har bekreftet at
scalp_edge skal retires — vi tar over det som trengs i bedrock-bot.

## Eksisterende state

**Bedrock-bot (`src/bedrock/bot/`, 4950 linjer, 11 moduler)** er en
komplett refaktor av scalp_edge per PLAN Fase 8 (sessions 41-46).

Ferdig:

- ✓ `ctrader_client.py` — Open API + auth + position-tracking +
  CH_ACCESS_TOKEN_INVALID-deteksjon
- ✓ `entry.py` (1338 linjer) — ordre-plassering med agri-ATR-override-
  bug fjernet (Fase 8-prinsipp)
- ✓ `exit.py` (944 linjer) — TP/SL/breakeven/trailing
- ✓ `sizing.py` — position-størrelse
- ✓ `safety.py` — gates + daily-loss + signal-staleness
- ✓ `instruments.py` — symbol-mapping (bedrock-id → cTrader-name)
- ✓ `comms.py` — signal-fetching via HTTP `/signals` med
  schema-versjon-sjekk (1.0/2.0/2.1)
- ✓ `state.py` — daily_loss-persistens
- ✓ `__main__.py` — entry-point med `--demo`/`--live` +
  SIGTERM/SIGHUP-handlere
- ✓ `config.py` — BotConfig (yaml) + StartupOnlyConfig (env)

Manglende (sub-fase 12.9-arbeid):

1. **HTTP `/signals`-endpoint** som bot fetcher fra. `bedrock server`
   (sub-fase 12.5+ session 93) leverer `/api/ui/...` på port 5100,
   ikke `/signals`. Trenger ny route som returnerer
   `signals_bot.json` wrappet i `{schema_version: "2.1", tekniske: [...], agri: [...]}`.
2. **Refresh-token-auto-flow** i ctrader_client.py. Eksisterende
   bot leser kun `CTRADER_ACCESS_TOKEN` fra env. cTrader-tokens
   expirer ~30 dager; uten refresh må bruker generere ny manuelt
   hver måned. Implementér: ved CH_ACCESS_TOKEN_INVALID, kall
   `https://connect.spotware.com/apps/token` med `grant_type=refresh_token`,
   skriv ny token til `~/.bedrock/secrets.env`, retry auth.
3. **Credentials-mønstret etter FRED/NASS** — `get_secret()` fra
   `~/.bedrock/secrets.env`. Eksisterende env-var-navn:
   - `CTRADER_CLIENT_ID`
   - `CTRADER_CLIENT_SECRET`
   - `CTRADER_ACCESS_TOKEN`
   - `CTRADER_REFRESH_TOKEN` (NY — for auto-refresh)
   - `CTRADER_ACCOUNT_ID`
4. **Systemd user-service** for bedrock-bot, mønstret etter
   `~/scalp_edge/start_bot.sh`. Auto-restart på exit ≠ 78 (FATAL).
5. **`bedrock-server.service` utvidet** med `/signals`-route.
6. **End-to-end-test mot demo-konto** før retire av scalp_edge:
   - Verify auth (auth + refresh-flow)
   - Verify signal-fetch (parse + schema 2.1)
   - Verify ordre-plassering på 1 paper-money-trade
   - Verify TP/SL-hit + position-close
   - Verify daily_loss-persistence

## Sub-task-tabell (revidert 2026-05-01 etter audit)

| Task | Innhold | Estimat |
|---|---|---|
| **D1a** | Schema-adapter `signals_bot.json` (bedrock) → bot-signal-format (scalp_edge) | 4-6t |
| **D1b** | HTTP `/signals`-endpoint i `bedrock server` som returnerer adapter-output | 1-2t |
| **D2** | Refresh-token-flow i `ctrader_client.py` | 2-3t |
| **D3** | `bot.yaml`-config + secrets-env-mønster | 30 min |
| **D4** | Systemd user-service `bedrock-bot.service` | 30 min |
| **D5** | End-to-end demo-test | 1-2t |
| **D6** | scalp_edge retire — disable timer + arkiver kode | 30 min |

Totalt 9-15t, sannsynlig 2-3 sessioner.

## D1a — schema-adapter detail (ny scope etter audit)

Bedrock-bot's `entry.py` venter signal-payload som scalp_edge's
signal_server.py produserer. Bedrocks `signals_bot.json` har et helt
annet format. Adapter må bygges.

**Bot-format (input til bot, fra scalp_edge signal_server.py):**

```json
{
  "schema_version": "2.1",
  "signals": [
    {
      "id": "<unique-id>",
      "instrument": "GOLD",
      "direction": "buy",
      "horizon": "SWING",
      "status": "watchlist",
      "entry_zone": [3380.5, 3382.0],
      "stop": 3375.0,
      "t1": 3395.0,
      "expiry_candles": 96,
      "horizon_config": {...},
      "confirmation_candle_limit": 12,
      "correlation_group": "metals",
      "created_at": "2026-05-01T01:39:34Z"
    }
  ],
  "valid_until": "2026-05-01T13:00:00Z",
  "global_state": {"geo_risk_active": false, ...},
  "rules": {"vix_regime": "normal", ...}
}
```

**Bedrock-format (`signals_bot.json` per session 92):**

```json
[
  {
    "instrument": "AUDUSD",
    "direction": "buy",
    "horizon": "makro",
    "score": 4.29,
    "grade": "A",
    "max_score": 5.8,
    "min_score_publish": 3.5,
    "published": true,
    "setup": {
      "setup_id": "8a69313f2fbf",
      "first_seen": "2026-05-01T01:39:34Z",
      "setup": {
        "instrument": "AUDUSD",
        "direction": "buy",
        "horizon": "makro",
        "entry": 0.7178,
        "sl": 0.7167,
        "tp": null,
        "rr": null,
        "atr": 0.00355,
        "entry_cluster_price": 0.7178,
        "entry_cluster_types": ["prior_high", "swing_high"]
      }
    },
    "skip_reason": null,
    "gates_triggered": [],
    "families": {...},
    "active_families": 6,
    "analog": {...},
    "asset_class": "fx"
  }
]
```

**Adapter-mapping:**

| Bot-felt | Bedrock-kilde | Transform |
|---|---|---|
| `id` | `setup.setup_id` | direkte |
| `instrument` | `instrument` | bot-mapping (AUDUSD→AUDUSD, Gold→GOLD via `bot_whitelist.yaml`) |
| `direction` | `direction` | direkte |
| `horizon` | `horizon` | UPPER (`makro`→`MAKRO`) |
| `status` | (ny) | "watchlist" alltid (eller "active" om bot fortolkning) |
| `entry_zone` | `setup.setup.entry` | `[entry - atr*0.5, entry + atr*0.5]` (cluster) |
| `stop` | `setup.setup.sl` | direkte |
| `t1` | `setup.setup.tp` | direkte (eller null for MAKRO trailing-only) |
| `expiry_candles` | (ny) | per-horisont default (SCALP=24, SWING=96, MAKRO=336) |
| `horizon_config` | (ny) | hard-kodet per horisont |
| `confirmation_candle_limit` | (ny) | hard-kodet per horisont |
| `correlation_group` | (ny via mapping) | per asset_class (`fx`, `metals`, `agri`, `indices`, `energy`, `crypto`) |
| `created_at` | `setup.first_seen` | direkte |
| `valid_until` (top) | (ny) | now + min(expiry_candles) |
| `global_state` (top) | (ny) | `{geo_risk_active: false, vix_regime: "normal"}` (eller hentet fra bedrock fundamentals) |
| `rules` (top) | (ny) | hard-kodet for bot-default |

**Filter:** kun `published: true` entries inkluderes i adapter-output.

**Ny modul:** `src/bedrock/signal_server/bot_adapter.py` med:

```python
def adapt_to_bot_format(
    bedrock_signals: list[dict],
    horizon_defaults: dict,
    asset_class_map: dict,
) -> dict:
    """Transformer bedrocks signals_bot.json til bot-signal-format."""
```

Test-coverage: én test per (input-felt, horisont, asset-klasse)-kombinasjon.

## Migrasjons-orden

1. **Først D2** (refresh-token-flow) — løser auth-issue permanent.
2. **Så D1** (signal-endpoint) — fjerner avhengighet til `signal_server.py`
   som boten ikke lenger trenger.
3. **D3 + D4** — config + service-aktivering parallelt.
4. **D5** — full demo-test med skjerm-overvåking.
5. **D6** — disable scalp_edge etter at bedrock-bot har kjørt rent
   ≥24t på demo.

## Brukers ansvar

- **D2 forberedelse:** Generer ny `access_token` + `refresh_token` via
  `~/scalp_edge/get_token.py`-mønsteret, legg i
  `~/.bedrock/secrets.env`:
  ```
  CTRADER_CLIENT_ID=...
  CTRADER_CLIENT_SECRET=...
  CTRADER_ACCESS_TOKEN=...
  CTRADER_REFRESH_TOKEN=...
  CTRADER_ACCOUNT_ID=...
  ```
- **D5 verifisering:** Skjerm-overvåking under første demo-test.
- **D6 godkjenning:** Bekrefte at bedrock-bot kjører rent ≥24t før
  scalp_edge disables.

## Hva tas fra scalp_edge

| scalp_edge-fil | Status i bedrock-bot |
|---|---|
| `trading_bot.py` (2977 lin) | ✓ Refactored til 11 moduler i `src/bedrock/bot/` |
| `signal_server.py` (974 lin) | ⚠ ERSTATTES av `/signals`-route i bedrock-server (D1) |
| `get_token.py` | ⚠ TILPASSES til `bedrock cli oauth-token`-kommando (D2 valgfri — kan beholdes som standalone-script) |
| `start_bot.sh` | ✗ ERSTATTES av systemd-service (D4) |
| `signal_log.json` | ✓ Bedrock-bot logger til `state.py` |
| `latest_signals.json` | ✓ Bedrock genererer `signals_bot.json` direkte |
| `live_prices.json` | ✗ Bot fetcher live priser fra cTrader (ikke fra fil) |
| `confirmation_stats.json` | ✗ Erstattes av bedrock-bot's interne state |
| `daily_loss_state.json` | ✓ `state.py` har persistens |

## Stop-criterion sub-fase 12.9

- D1: bedrock-server eksponerer `/signals` som bedrock-bot kan
  fetche (curl-test grønt)
- D2: refresh-token-flow tester grønt — simulert
  CH_ACCESS_TOKEN_INVALID → auto-refresh → reconnect
- D3+D4: bot starter via `systemctl --user start bedrock-bot.service`
  uten env-var-feil
- D5: demo-test ≥24t uten crash, ≥1 trade plassert + lukket
- D6: scalp_edge timer disabled; arkiv-tag `scalp-edge-final-2026-05-01`

Etter 12.9 LUKKET: tag `v0.12.9-fase-12.9-LUKKET`. Plan-S kan starte.

## Audit-funn fra scalp_edge-loggen 2026-05-01

```
2026-04-28 13:19:38 [WARNING] [SERVER FEIL] Access token expired
2026-04-28 13:19:38 [ERROR] [FATAL] Auth-feil fra cTrader (kode=CH_ACCESS_TOKEN_INVALID):
                            Access token expired. Generer ny token og restart manuelt.
2026-04-28 13:19:38 [WARNING] [FRAKOBLET] — prøver igjen om 10 sek...
```

Crash-loop hver 1-2 timer siden 28. apr 13:19 (~80 timer crash-loop).
Schema-mismatch også observert: scalp_edge mottar `schema_version='2.2'`
fra signal_server.py men støtter kun {1.0, 2.0, 2.1}.

Bedrock-bot har samme SUPPORTED_SCHEMA_VERSIONS — så D1's nye
`/signals`-route må produsere 2.1, ikke 2.2.
