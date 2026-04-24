# Bot-refaktor — migrasjonsplan

**Kilde:** `~/scalp_edge/trading_bot.py` (2977 linjer, README
sist oppdatert 17. april 2026).
**Mål:** `src/bedrock/bot/` splittet i 8 moduler per PLAN § 9.4, agri-ATR-override
fjernet, hardkodede terskler flyttet til `config/bot.yaml`.
**Prinsipp for Fase 8:** **ingen logikk-endring** utover (a) agri-override-fjerning
og (b) konfig-ekstraksjon. Bare rename + flytt. Gammel `~/scalp_edge/trading_bot.py`
kjører uendret i demo-parallell til Fase 11-12 cutover.

Dette dokumentet er produsert i session 39 (Fase 8 session 1) som research —
ingen kode ble skrevet eller modifisert. Alle linjenumre refererer til gammel
`trading_bot.py` slik den var da dokumentet ble skrevet. Bruk
`git log -- ~/scalp_edge/trading_bot.py` hos scalp_edge-repoet for å verifisere
at ingen uventede endringer har skjedd før refaktoreringen starter.

---

## 1. Fil-metadata (oversikt)

| Egenskap | Verdi |
|---|---|
| Total linjer | 2977 |
| Antall klasser (top-level) | 4 (`TradePhase`, `Candle`, `TradeState`, `CandleBuffer`) + `ScalpEdgeBot` |
| Antall top-level funksjoner | 4 (`_net_usd_direction`, `_looks_like_fx_pair`, `_get_group_params`, `_agri_session_ok`, `check_env`) |
| Antall metoder i `ScalpEdgeBot` | 66 |
| Modul-konstanter (dicts + scalars) | ca. 18 (INSTRUMENT_MAP, GROUP_PARAMS, AGRI_SESSION, HORIZON_TTL_SECONDS, …) |
| Eksterne deps | `twisted`, `ctrader-open-api`, `requests` |

Hele filen er én monolitt. Én klasse (`ScalpEdgeBot`) spenner linje 405–2942
(2538 linjer) og inneholder all trading-logikk. Det finnes ingen eksisterende
modul-splitt å bygge videre på.

---

## 2. Topp-nivå struktur (hva bor hvor i dag)

### 2.1 Imports (linje 1-73)

Standard-bibliotek + `requests` + Twisted + cTrader Open API
(applikasjons-/regnskaps-auth, symbols, reconcile, spot, trendbars, orders,
execution, errors, trader). Alle disse går inn i `bot/ctrader_client.py`; ingen
annen modul skal importere protobuf direkte.

### 2.2 Konfigurasjon via env (linje 74-83)

`CLIENT_ID`, `CLIENT_SECRET`, `ACCESS_TOKEN`, `ACCOUNT_ID`, `SIGNAL_URL`,
`SIGNAL_API_KEY`. **Disse beholdes** som env-variabler (cTrader-credentials er
sensitive og skal ikke i YAML per CLAUDE.md + PLAN § 10.6 `.env`-seksjonen).
`SIGNAL_URL` oppdateres i Fase 8 slut til `http://localhost:5100` (ny Bedrock
signal_server). Leses i `bot/__main__.py`.

### 2.3 Logging (linje 85-100)

RotatingFileHandler 10 MB × 5 backups. Skal til `bot/__main__.py`. Logger-navn
endres til `bedrock.bot`.

### 2.4 Modul-konstanter (linje 102-232) — skal til config eller egne moduler

Se seksjon 6 for full mapping. Kort:

- `SUPPORTED_SCHEMA_VERSIONS`, `HORIZON_TTL_SECONDS`, `AUTH_FATAL_ERROR_CODES`,
  `RECONNECT_WINDOW_SEC`, `RECONNECT_MAX_IN_WINDOW`, `MIN_SPREAD_SAMPLES` →
  `config/bot.yaml`
- `INSTRUMENT_MAP`, `PRICE_FEED_MAP`, `INSTRUMENT_TO_PRICE_KEY`,
  `FX_USD_DIRECTION`, `AGRI_INSTRUMENTS`, `AGRI_SUBGROUPS`,
  `INSTRUMENT_GROUP` → `config/bot.yaml` (instrument-seksjoner; disse er
  data, ikke logikk)
- `GROUP_PARAMS`, `AGRI_SESSION`, `AGRI_MAX_POSITIONS`,
  `AGRI_MAX_PER_SUBGROUP`, `AGRI_MAX_SPREAD_ATR` → `config/bot.yaml`
- `ProtoOATrendbarPeriod`-konstanter, `CET` (ZoneInfo) → forblir i kode

### 2.5 Top-level hjelpere (linje 233-321)

- `_net_usd_direction`, `_looks_like_fx_pair` (linje 233-253) → `bot/entry.py`
  helpers
- `_get_group_params` (linje 304-306) → `bot/state.py` (bruker GROUP_PARAMS
  som da er Config-løftet)
- `_agri_session_ok` (linje 308-321) → `bot/entry.py`

### 2.6 Dataclasses (linje 335-398)

`TradePhase`, `Candle`, `TradeState`, `CandleBuffer` → `bot/state.py`. **Ingen
endring i feltene**; kun flytt. `TradeState` kan eventuelt migreres til
Pydantic senere (ikke i Fase 8).

### 2.7 `ScalpEdgeBot` (linje 405-2942)

Se seksjon 3 for detaljert metode-kart.

### 2.8 `check_env` + `__main__` (linje 2949-2977)

→ `bot/__main__.py`. Live-bekreftelses-prompt bevart.

---

## 3. Metode-kart (ScalpEdgeBot) — målt per linje

Alle linjenumre er start-linjen for metode-signaturen.

### 3.1 `bot/ctrader_client.py` (Twisted, Protobuf, reconnect)

| Linje | Metode | Rolle |
|---|---|---|
| 474 | `start` | Reactor-oppstart, heartbeat, watchdog, poll-loop |
| 511 | `_on_connected` | App-auth-req |
| 524 | `_on_disconnected` | Reconnect-budsjett + `_fatal_exit` |
| 539 | `_fatal_exit` | reactor.stop + sys.exit(code) |
| 560 | `_on_message` | Dispatch til per-payloadType-handlers |
| 591 | `_on_app_auth` | Account-auth-req |
| 598 | `_on_account_auth` | Trader-info-req |
| 605 | `_on_trader_info` | Balance, symbols-req |
| 619 | `_on_symbols_list` | Symbol-mapping, subscribe-spots, historiske bars |
| 780 | `_send_reconcile` | Reconcile-req |
| 785 | `_request_historical_bars` | 50×15m-bars |
| 797 | `_request_historical_bars_h1` | 50×1h-bars |
| 809 | `_send` | Send med clientMsgId-tracking |
| 818 | `_on_subscribe_spots` | Logg |
| 821 | `_on_symbol_by_id` | Symbol-detaljer (digits, pip) |
| 840 | `_dump_agri_symbol_info` | Debug-dump |
| 839 | `_send_heartbeat` | Heartbeat-event |

Ansvaret: Transport og protokoll-nivå mot cTrader. Skal ikke kjenne til trade-
logikk eller signal-henting. Ingen logikk-endring i Fase 8.

**Grensesnitt utad:**
- `subscribe_spots(symbol_ids)`, `send_new_order(...)`,
  `amend_sl_tp(position_id, sl, tp)`, `close_position(position_id, volume)`,
  `cancel_order(order_id)`, `reconcile()`.
- Callbacks injiseres: `on_spot`, `on_execution`, `on_order_error`,
  `on_error_res`, `on_reconcile`, `on_historical_bars`.

### 3.2 `bot/entry.py` (signal-prosessering, gates, confirmation)

| Linje | Metode | Rolle |
|---|---|---|
| 870 | `_on_spot` | Router spot-event; oppdater bid/ask/spread-historikk |
| 908 | `_handle_trendbar` | 15m/5m-bar → buffer, EMA9/ATR14 |
| 960 | `_handle_trendbar_h1` | 1h-bar → buffer |
| 991 | `_update_indicators_h1` | EMA9/ATR14 (1h) |
| 1025 | `_get_atr14_h1` | Getter |
| 1029 | `_get_ema9_h1` | Getter med offset |
| 1034 | `_on_historical_bars` | Bootstrap buffer fra historikk |
| 1076 | `_update_indicators` | EMA9/ATR14 (15m) |
| 1114 | `_get_ema9` | Getter |
| 1120 | `_get_atr14` | Getter |
| 1124 | `_get_normal_spread` | Snitt av `spread_history` |
| 1132 | `_update_atr14_5m` | 5m ATR14 |
| 1146 | `_on_candle_closed` | 15m-candle → evaluer watchlist |
| 1198 | `_process_watchlist_signal` | Hovedlogikk: gates → confirmation → trade |
| 1323 | `_passes_filters` | Spread, R:R, session, agri-subgroup, correlation |
| 1384 | `_check_confirmation` | 3-punkt: body, wick, EMA-gradient |
| 1476 | `_save_confirmation_stats` | Persist `confirmation_stats.json` |

Ansvaret: Alt som skjer før en ordre sendes. Bruker `ctrader_client` som
transport, `state` for indikatorer, `safety` for daily-loss, `comms` for signal-
henting. Hovedinngang: `on_candle_closed(symbol_id, candle)`.

### 3.3 `bot/sizing.py` (risiko + lot-tier)

| Linje | Metode | Rolle |
|---|---|---|
| 1734 | `_get_risk_pct` | Full/half/quarter basert på geo/VIX/character/outside |
| 1837 | `_volume_to_lots` | Intern konverter-helper (lot-tier, step-volume) |
| ~1575-1650 | (inline i `_execute_trade`) | Risk%-til-volum-konvertering |

Ansvaret: Ren kalkulering, ingen I/O. Lot-tier-kjedelogikken bor i dag inline i
`_execute_trade` (linje 1491-1733) og skal ekstraheres som `size_volume(rules,
balance, sl_distance, instrument, signal_char, vix, geo, outside_session) ->
int`.

### 3.4 `bot/exit.py` (P1-P5 exit-prioritet)

| Linje | Metode | Rolle |
|---|---|---|
| 2304 | `_manage_open_positions` | **Hovedmotoren (208 linjer, 2304-2511)** som kjører P1-P5 |
| 2531 | `_set_break_even` | P3a |
| 2586 | `_calc_close_volume` | Partial-close volum |
| 2604 | `_compute_progress` | Entry-til-T1 fraksjon |
| 2617 | `_update_trail` | P3.5 trailing (ratchet) |
| 1896 | `_calc_pnl` | Urealisert PnL |
| 1750 | `_weekend_action` | Fredag 19/20 CET regel |
| 1762 | `_compute_weekend_sl` | Strammere SL helg |

Ansvaret: Hva skjer etter entry. Tar inn `state`, `candle`, `atr`, `rules`,
returnerer exit-beslutning (close/amend/none). `_manage_open_positions` er den
største enkelt-metoden og inneholder 5 exit-prioriteter:

- P1: Geo-spike exit (linje 2329-2350)
- P2: Server kill-switch
- P2.5: Weekend-lukke SCALP
- P3: Hard SL/T1
- P3a: Break-even
- P3.5: Trailing post-T1
- P4: EMA9-exit (scalp only)
- P5: Timeout (expiry_candles)
- P5a: Giveback (peak progress reversal)

Refaktor-strategi: Splitt `_manage_open_positions` i per-prioritet-funksjoner i
Fase 9+ (for test-isolering). I Fase 8 **ikke splittes** — kun flyttes.

### 3.5 `bot/state.py` (TradeState, Candle, Buffer, Phase, indicators-state)

Dataclasses fra linje 335-398 + indicator-dicts som bor i `ScalpEdgeBot.__init__`:

- `candle_buffers`, `m5_candle_buffers`, `h1_candle_buffers`
- `ema9`, `atr14`, `atr14_5m`, `ema9_h1`, `atr14_h1`
- `spread_history`, `last_bid`, `last_ask`
- `symbol_info`, `symbol_digits`, `symbol_price_digits`, `symbol_pip`
- `active_states: list[TradeState]`

Ansvaret: Rene data-beholdere + immutable helpers (`_get_group_params`,
`_weekend_action` tidskalkulasjoner). **Ingen I/O.** `TradeState` forblir
dataclass (ikke Pydantic) i Fase 8 — endring til Pydantic krever ADR.

### 3.6 `bot/safety.py` (daily-loss, kill-switch, server-frozen)

| Linje | Metode | Rolle |
|---|---|---|
| 2893 | `_reset_daily_loss_if_new_day` | Midnatt UTC reset |
| 2905 | `_load_daily_loss_state` | Last fra `daily_loss_state.json` ved oppstart |
| 2922 | `_save_daily_loss_state` | Atomic skriv ved tap |
| 2932 | `_daily_loss_limit` | max(pct_of_balance, nok_floor) |
| 2941 | `_daily_loss_exceeded` | Sammenlign med limit |
| — | `server_frozen`, `bot_locked`, `bot_locked_until` | Flagg (satt av `comms`) |
| 2810 | `_record_fetch_failure` | Eskalerende fetch-fail-logging |

Ansvaret: State som ikke er per-trade men per-bot. Eier `~/scalp_edge/
daily_loss_state.json`. I Bedrock flyttes persisterings-path til
`~/bedrock/data/bot/daily_loss_state.json`.

### 3.7 `bot/comms.py` (signal-server-polling)

| Linje | Metode | Rolle |
|---|---|---|
| 2695 | `_fetch_signals_loop` | Self-schedulende med adaptiv intervall |
| 2718 | `_fetch_signals_with_retry` | Tenacity-basert retry |
| 2746 | `_fetch_signals` | HTTP GET, parse, populere watchlist |
| 2074 | `_on_execution` | **NB: dette er execution-event, ikke signal** — hører i `ctrader_client.py` som callback |
| 2039 | `_push_prices` | HTTP POST til `/push-prices` |
| 2034 | `_start_price_loop` | LoopingCall |
| 2023 | `_schedule_price_push` | Initial delay |
| 2010 | `_git_push_log` | **Fjernes** i Bedrock — auto-push-hook dekker dette |

Ansvaret: All HTTP-kommunikasjon med signal_server. Ny URL:
`http://localhost:5100` (Bedrock). Schema-versjon forblir v1 (låst per STATE.md
invariants). **`_git_push_log` fjernes** — Bedrocks `.githooks/post-commit`
dekker auto-push.

### 3.8 `bot/__main__.py` (wire alt sammen)

- Env-sjekk (`check_env`, linje 2949)
- Argparse (`--demo`/`--live`)
- Live-bekreftelses-prompt
- Instansier `ScalpEdgeBot(demo=...)` og `bot.start()`

Kjørebinding: `uv run python -m bedrock.bot --demo`.

### 3.9 Execution + reconcile handlers (spesialtilfelle)

| Linje | Metode | Rolle |
|---|---|---|
| 2074 | `_on_execution` | Execution-event (fill, partial, reject) |
| 2182 | `_on_order_error` | Ordrefeil |
| 2217 | `_on_error_res` | ProtoOAErrorRes |
| 2235 | `_on_reconcile` | Reconcile-response — recover åpne posisjoner |

Disse er cTrader-events, men de muterer `active_states`. Forslag:
`ctrader_client` tar imot callbacks; selve state-mutasjonene bor i `bot/entry.py`
(for nye ordre) og `bot/state.py` (for reconcile-recovery). I Fase 8 kan de
midlertidig bli i samme modul som `_on_message`-dispatcheren for å minimere
endringer — splittes i Fase 9.

### 3.10 Watchdog + reset

| Linje | Metode | Rolle |
|---|---|---|
| 2839 | `_send_heartbeat` | Ctrader heartbeat (25s) |
| 2846 | `_watchdog_check` | Silent-stream-deteksjon |
| 2874 | `_check_symbol_silence` | Per-symbol silence-logging |

Disse hører i `ctrader_client.py` (tranport-laget).

### 3.11 Logging-helpers

| Linje | Metode | Rolle |
|---|---|---|
| 1805 | `_log_trade_opened` | Strukturert entry-log |
| 1847 | `_log_reconcile_opened` | Etter reconcile |
| 1961 | `_log_trade_closed` | Exit-log |
| 1476 | `_save_confirmation_stats` | Aggregert stats-persist |

Disse er spredt per domene (entry/exit/safety). Det er fristende å sentralisere
i `bot/logging_helpers.py`, men **Fase 8-regelen er null logikk-endring** — de
blir i respektive moduler som private helpers.

---

## 4. Agri-ATR-override: eksakt kode-sitat for fjerning

**Metode:** `_recalibrate_agri_levels`. (PLAN.md § 9.1 refererer til denne som
`_calibrate_agri_signal` — faktisk navn er `_recalibrate_agri_levels`.
Oppdatering av PLAN.md anbefalt, men ikke kritisk.)

**Plassering:** `~/scalp_edge/trading_bot.py:2665-2693`.

**Kall-sted:** Søk i filen viser metoden defineres linje 2665 men vises ikke
kalt direkte andre steder — den brukes sannsynligvis gjennom et sig-dispatch i
`_process_watchlist_signal` (linje 1198-1322). Før session 40 starter
refaktoreringen **må** dette call-sitet lokaliseres; grep-verifikasjon etter
flytt bekrefter at ingen caller er igjen.

**Bug-atferd (som er grunn til fjerning):**
1. Tar inn signal med pre-kalkulert `stop`, `t1`, `t2_informational`, `entry_zone`
   fra signal_server (basert på reelle støtte/motstand-nivåer)
2. Henter live 15m-ATR14 fra bot-bufferen
3. **Overstyrer alle fire felt** med `entry ± {1.5, 2.5, 3.5} × live_atr`
4. Resultat: T1 ender alltid 2.5×ATR unna entry, uavhengig av om setup-
   generatoren fant et reelt nivå 5×ATR unna (som hadde gitt bedre R:R)
5. Symptom: agri-trades får små TP-er selv når markedet har plass til mer

**Fix i Fase 8 session 40+:**
- Slett hele metoden `_recalibrate_agri_levels`
- Fjern kall-sitet (når lokalisert)
- Legg til enhetstest: `test_agri_signal_not_overridden` som verifiserer at
  `stop`, `t1`, `t2_informational`, `entry_zone` er identiske inn/ut av
  bot-pipelinen for et test-signal
- Signal-server i Bedrock produserer allerede reelle-nivå-baserte SL/T1 fra
  setup-generator (Fase 4), så det er ingenting som går tapt

**Ikke fjern:**
- `_get_atr14` + `_get_atr14_h1` — disse brukes av trail, break-even, spread-
  filter og er riktige i bot-kontekst.

---

## 5. Hardkodede terskler → `config/bot.yaml`

Nedenfor er alle numeriske terskler som i dag er hardkodet som Python-konstanter,
dict-literaler eller magic-tall inne i metoder. Kolonnen "Status" angir om
verdien også har en `rules.get()`-override-sti fra YAML (altså delvis
parametrisert allerede).

### 5.1 Allerede parametrisert via `rules.get()` (ingen endring, bare flytt default til bot.yaml)

| Python-konstant / bruk | Default | YAML-nøkkel |
|---|---|---|
| `risk_pct_full` (1734, 1744) | `1.0` | `risk_pct.full` |
| `risk_pct_half` (1734, 1743) | `0.5` | `risk_pct.half` |
| `risk_pct_quarter` (1734, 1741) | `0.25` | `risk_pct.quarter` |
| `daily_loss_limit_pct` (2936) | `2.0` | `daily_loss.pct_of_balance` |
| `daily_loss_limit_nok` (2938) | `500` | `daily_loss.minimum_nok` |
| `geo_spike_atr_multiplier` (2330) | `2.0` | (i instrument-rules, ikke bot.yaml — bevart) |
| `min_rr_geo` (1370) | `2.0` | (i instrument-rules — bevart) |
| `stop_multiplier` (1357) | `3.0` (×2 → spread_mult=6) | (i instrument-rules — bevart) |
| `confirmation_min_score` (1303) | `2` | `confirmation.min_score_default` |
| `confirmation_max_candles` (1312) | `6` | `confirmation.max_candles_default` |
| `exit_timeout_full_hours` (1272) | — | (i horizon-config — bevart) |
| `exit_geo_spike_atr_mult` (2329) | `2.0` | (i horizon-config — bevart) |

Disse har allerede en YAML-override-sti via `rules.get()`/`hcfg.get()` fra
`instruments/*.yaml`; defaultene i koden er det vi flytter til `bot.yaml` slik
at nye instrumenter ikke trenger å repetere dem.

### 5.2 Ikke-parametrisert — må legges til config/bot.yaml

| Linje | Konstant / magic value | Nåverdi | YAML-nøkkel (PLAN § 9.3) |
|---|---|---|---|
| 135 | `MIN_SPREAD_SAMPLES` | `10` | `spread.min_samples` |
| 140-144 | `HORIZON_TTL_SECONDS` | 15min/4h/24h | `horizon_ttl.{scalp,swing,makro}` |
| 179 | `AGRI_MAX_PER_SUBGROUP` | `1` | `agri.max_per_subgroup` |
| 172 | `AGRI_MAX_POSITIONS` | `2` | `agri.max_concurrent` |
| 302 | `AGRI_MAX_SPREAD_ATR` | `0.40` | `agri.max_spread_atr_ratio` |
| 128-129 | `RECONNECT_WINDOW_SEC`, `RECONNECT_MAX_IN_WINDOW` | `600`, `5` | `reconnect.{window_sec,max_in_window}` |
| 268-283 | `GROUP_PARAMS` (trail_atr, gb_peak, gb_exit, be_atr, expiry, ema9_exit) | Per-gruppe | `trail_atr_multipliers.*`, `giveback.*`, `break_even.atr_ratio`, `expiry_candles.*` |
| 289-299 | `AGRI_SESSION` | Per-instrument hh:mm-vindu | `agri.session_times_cet.*` |
| 500 | `self._poll_interval` default | `60` | `polling.default_seconds` |
| (inne i fetch-loop) | SCALP-aktiv intervall | `20` | `polling.scalp_active_seconds` |
| 1357 | `spread_mult` agri | `2.5` | `spread.agri_multiplier` |
| 1357 | `stop_multiplier * 2` | `6.0` (default) | `spread.non_agri_multiplier_of_stop` |
| 1367 | `_HORIZON_MIN_RR` | 1.0/1.3/1.5 | `horizon_min_rr.{scalp,swing,makro}` |
| 1415 | body-threshold-andel | `0.30 * atr_5m` | `confirmation.body_threshold_atr_pct` |
| 1429 | EMA-gradient BUY | `>= -0.05` | `confirmation.ema_gradient_buy_min` |
| 1431 | EMA-gradient SELL | `<= +0.05` | `confirmation.ema_gradient_sell_max` |
| 1769,1772 | Weekend-SL | `1.5 * atr` | `weekend.sl_atr_mult` |
| 1776 | Monday-gap-terskel | `2 × ATR` | `monday_gap.atr_multiplier` |
| 2618 | Trail default mult | `1.5` | `trail.default_atr_mult` (kun fallback) |
| 2629+ | Oil min_sl_pips (per PLAN) | `25` | `oil.min_sl_pips` |
| 2629+ | Oil max_spread_mult | `3.0` | `oil.max_spread_mult` |

### 5.3 Skal IKKE i YAML

- `SUPPORTED_SCHEMA_VERSIONS` (109) — kode-kontrakt, ikke konfig
- `AUTH_FATAL_ERROR_CODES` (118-126) — tied to cTrader API
- `M15_PERIOD`, `M5_PERIOD`, `H1_PERIOD` (111-113) — Protobuf-enum
- `INSTRUMENT_MAP`, `PRICE_FEED_MAP`, `INSTRUMENT_TO_PRICE_KEY`,
  `FX_USD_DIRECTION`, `AGRI_INSTRUMENTS`, `AGRI_SUBGROUPS`,
  `INSTRUMENT_GROUP` — data-lookup, YAML ville bare vært støy. Kan flyttes
  til en `bot/instruments.py`-konstant-modul, ikke YAML.
- Heartbeat-intervall `25` (linje 515) — cTrader API-krav
- Watchdog-intervall `30` (linje 518) — implementasjons-detalj

### 5.4 SIGHUP-reload

Per PLAN § 9.3: config re-leses ved SIGHUP. Implementasjons-skisse:

- `bot/__main__.py` registrerer `signal.SIGHUP` handler
- Handler kaller `config.reload()` som re-parser `~/.bedrock/bot.yaml`
- Reactor-callbacks leser `config.get(...)` på hver invokasjon (ingen
  caching-layer)
- **Unntak:** `trail_atr_multipliers.*` er fest i `GROUP_PARAMS`-dict-
  struktur; SIGHUP-reload må rebygge denne dict-en. `bot/state.py` eier
  den, og gir den ut via `get_group_params(instrument) -> dict`.

---

## 6. Target-modulstruktur (endelig)

```
src/bedrock/bot/
├── __init__.py
├── __main__.py          # Entry point, argparse, live-confirm, env-check
├── ctrader_client.py    # Twisted + Protobuf + reconnect + heartbeat + watchdog
├── instruments.py       # INSTRUMENT_MAP, PRICE_FEED_MAP, FX_USD_DIRECTION, etc.
├── state.py             # TradePhase, Candle, TradeState, CandleBuffer,
│                        # indicator-state containers
├── comms.py             # Signal-server HTTP (GET /signals, POST /push-prices)
├── entry.py             # Spot/candle-handlers, filters, confirmation,
│                        # _execute_trade, _get_risk_pct-wrapper
├── sizing.py            # size_volume(rules, balance, sl_dist, ...) → int
├── exit.py              # _manage_open_positions, _update_trail,
│                        # _set_break_even, _calc_pnl, weekend-logikk
├── safety.py            # daily_loss state, kill-switch flags, fetch-fail-tracking
└── config.py            # ConfigLoader(path, reload_on_sighup=True)
```

Merk ekstra moduler i forhold til PLAN § 9.4:
- `instruments.py` — ren data-lookup, ikke verdt å legge i YAML
- `config.py` — dedicated loader for SIGHUP-reload

PLAN § 9.4 nevner 8 filer; denne strukturen er 10 (med `__init__.py` og
`config.py`). `instruments.py` er data, ikke logikk — holder `entry.py` ren.
Avviket er innenfor "implementasjons-beslutninger" (CLAUDE.md § Beslutnings-
retningslinje).

---

## 7. Avhengighetsgraf (hvem importerer hva)

```
__main__ → {ctrader_client, entry, exit, safety, comms, state, config}
entry → {state, safety, comms, sizing, instruments, config}
exit → {state, safety, instruments, config}
safety → {state, config}
comms → {config, state (TradeState)}
sizing → {instruments, config}
ctrader_client → (ingen interne)
state → {instruments}
instruments → (ingen interne)
config → (ingen interne)
```

Ingen sirkulær avhengighet. `ctrader_client` er leaf-modul som alle
business-moduler kaller via callbacks injisert fra `__main__`.

---

## 8. Refaktor-rekkefølge (session 40+)

**Viktig:** alt skjer i Bedrock-repoet (`~/bedrock/src/bedrock/bot/`).
`~/scalp_edge/trading_bot.py` røres ikke. Ny bot kjører på port 5100 mot
Bedrock signal_server; gammel bot fortsetter å kjøre mot port 5000.

1. **Session 40 — skjelett + state + instruments + config.**
   - Opprett `bot/__init__.py`, `bot/state.py`, `bot/instruments.py`, `bot/config.py`
   - Flytt dataclasses uendret
   - Bygg `config.py` med Pydantic-modell for `bot.yaml`
   - Første versjon av `config/bot.yaml` med alle defaults fra § 5.1+5.2
   - Tester: roundtrip YAML → Pydantic → dict

2. **Session 41 — ctrader_client.**
   - Port `ScalpEdgeBot.__init__` transport-felt + `start` +
     tilkoblings-/meldings-dispatcher
   - Uendret logikk; bare klasse-grense rundt Twisted-delen
   - Callbacks exposes: `on_spot`, `on_execution`, `on_reconcile`,
     `on_historical_bars`, `on_order_error`, `on_error_res`
   - Test: mock Twisted-reactor, verifiser at message-dispatch kaller riktig
     callback

3. **Session 42 — safety + comms.**
   - `safety.py`: daily_loss-state + kill + server-frozen + fetch-fail
   - `comms.py`: signal-fetch med tenacity, push_prices
   - Peker på `SIGNAL_URL=http://localhost:5100`
   - **Fjern** `_git_push_log`
   - Tester: mock HTTP, verifiser retry-logikk

4. **Session 43 — entry + sizing (NB: uten agri-override).**
   - Port `_on_spot`, `_handle_trendbar*`, indicator-oppdaterings-metoder
   - Port `_on_candle_closed`, `_process_watchlist_signal`, `_passes_filters`,
     `_check_confirmation`
   - Port `_execute_trade` → split ut `sizing.size_volume`
   - **Slett `_recalibrate_agri_levels`**
   - Tester:
     - `test_agri_signal_not_overridden` (kritisk — bekrefter bug-fix)
     - Confirmation-score på syntetiske candles
     - Spread-filter cold-start-vern
     - R:R-gate per horisont

5. **Session 44 — exit.**
   - Port `_manage_open_positions` + `_update_trail` + `_set_break_even`
     uendret (som én modul, ikke splittet enda)
   - Port `_weekend_action`, `_is_monday_gap`, `_compute_weekend_sl`
   - Tester: P1-P5-prioritet på syntetiske states

6. **Session 45 — __main__ + integrasjons-test.**
   - Wire alt sammen
   - `uv run python -m bedrock.bot --demo` i test-modus (mock Twisted + mock
     signal_server)
   - Smoke-test: bot starter, auth-er, subscribe-spotter, fetch-er signaler,
     lukker rent på SIGTERM
   - **Ikke** kjør mot ekte cTrader demo ennå — det skjer i parallell-drift-
     runden (session 46+)

7. **Session 46+ — parallell-demo-drift + observasjon.**
   - Start ny bot mot ny Bedrock signal_server på port 5100
   - Gammel bot fortsetter uendret mot port 5000
   - Sammenlign trade-log: forvent identisk atferd i FX/metaller/indekser,
     forvent riktigere (reelt-nivå-baserte) TP-er i agri
   - Observasjon-vindu: minst to uker
   - Ved divergens: undersøk, patch i Bedrock-bot, ikke rør gammel

Fase 8 avsluttes (session 47 eller senere) når parallell-drift viser at Bedrock-
bot oppfører seg like bra eller bedre enn gammel.

---

## 9. Test-strategi for Fase 8

Per CLAUDE.md: logiske tester primær, enhetstester sekundær.

### 9.1 Logiske tester (`tests/logical/bot/`)

- `test_agri_signal_preserved_end_to_end.py`: signal med SL=X, T1=Y inn →
  samme SL, T1 ut av bot-pipelinen (ingen override)
- `test_confirmation_accepts_valid_bull_candle.py`: grønn candle med body ≥
  0.30×ATR, low i sone, EMA9 gradient ≥ -0.05 → confirmation passerer
- `test_daily_loss_blocks_entry_at_limit.py`: balance 100000, daily_loss
  2100 → entry blokkert (pct=2.0% = 2000 < 2100)
- `test_weekend_close_scalp_after_friday_2000.py`: fredag 20:05 CET →
  P2.5 lukker SCALP-trade
- `test_geo_spike_exits_before_T1.py`: geo_active + bevegelse mot > 2×ATR →
  P1 triggrer

### 9.2 Enhetstester (`tests/unit/bot/`)

- `test_sizing.py`: `size_volume` per horisont/karakter/VIX-matrise
- `test_config_roundtrip.py`: YAML → Pydantic → YAML stabil
- `test_ctrader_message_dispatch.py`: ProtoOAExecutionEvent → callback kalt

### 9.3 Ikke-tester (bevisst utelatt)

- Live cTrader-mock-kjøring (Twisted-reactor tester er sårbare og flaky;
  bygger smoke-test i session 45 i stedet)
- Ende-til-ende signal-server-integrasjon — dekket av parallell-drift
  (session 46+)

---

## 10. Risiko og åpne spørsmål

### 10.1 Risiko: Twisted-singleton

`reactor` er en global. Hvis tester kjører pytest parallelt kan reactor-state
lekke mellom tester. Mitigering: Twisted-tester i eget file-lock (`pytest-
twisted` eller manuell `@pytest.mark.serial`). **Beslutning utsatt** til
session 41 der vi faktisk setter det opp.

### 10.2 Risiko: reconcile-recovery etter cutover

Hvis Bedrock-bot tar over en åpen posisjon fra gammel bot (via broker), må
`active_states` populeres korrekt fra `ProtoOAReconcileRes`. Dette er allerede
implementert (linje 2235+), men testes aldri uten ekte broker. Mitigering:
parallell-drift (§ 8 punkt 7) med syntetisk "bytt hvilken bot eier posisjonen"-
scenario.

### 10.3 Avklart: SIGHUP-reload-split (session 39)

Bruker har besvart: `bot.yaml` splittes i to top-level seksjoner.

- **`startup_only`** — krever prosess-restart for å ta effekt. SIGHUP gir
  advarsel i logg hvis disse er endret ("restart kreves for å aktivere ny
  verdi"). Eksempler:
  - cTrader host / port
  - Symbol-liste (INSTRUMENT_MAP, PRICE_FEED_MAP)
  - account_id
  - Reconnect-budsjett (`reconnect.{window_sec,max_in_window}`)
  - Signal-server URL
- **`reloadable`** — SIGHUP plukker opp endringer umiddelbart uten restart.
  Eksempler:
  - Terskler: confirmation, trail_atr, giveback, break_even, weekend,
    monday_gap, spread
  - Risk: risk_pct, daily_loss
  - Agri session-tider
  - Horizon-TTL, horizon-min-rr
  - Polling-intervaller

`bot/config.py` Pydantic-modell deler eksplisitt i `BotConfigStartupOnly`
og `BotConfigReloadable` slik at type-systemet reflekterer distinksjonen.
SIGHUP-handler sammenligner gammelt og nytt `startup_only`-objekt; ved
avvik → log.warning + behold gammelt. `reloadable` erstattes atomisk.

### 10.4 Avklart: `_git_push_log` → batch-daglig commit (session 39)

Bruker har besvart: Bedrocks `.githooks/post-commit` dekker push-delen, men
boten må fortsatt gjøre `git add + git commit` selv for trade-logging.
**Batching**: én commit per dag (ved daily_loss-reset midnatt UTC), ikke
én per trade-close — unngår spam-historikk. SSH-tilgang for bot-service
håndteres i Fase 13 cutover (ikke Fase 8).

Implementasjon i session 42:

- `bot/comms.py` (eller `bot/safety.py` nær daily-reset) får
  `_commit_daily_log()` som kalles fra `_reset_daily_loss_if_new_day`
- `git add <trade_log_file>` + `git commit -m "log: bot trades <date>"` —
  én commit per kalenderdag UTC
- Feilmodus: git-kommandoen feiler (tom diff, ingen repo-tilgang) →
  log.warning, ikke fatal
- Post-commit-hook tar push automatisk

---

## 11. Kontrakt mot Fase 11-12 cutover

Fase 11-12 forutsetter at Bedrock-bot er testet i parallell-drift i minst
to uker. Denne planen forbereder følgende for den overgangen:

- Gammel `~/scalp_edge/` rørres aldri av refaktoren
- Bedrock signal_server lytter på port 5100 (allerede verifisert, Fase 7)
- Bedrock-bot får egen prosess-navn (`bedrock-bot` via systemd) slik at
  `pgrep`/`ps` klart skiller gammel og ny
- Cutover = stopp gammel bot + stopp gammel signal_server + verifiser at
  Bedrock-bot fortsetter rent. Rollback = start gammel igjen, stopp Bedrock
- Ingen felles fil-writes: gammel skriver `~/scalp_edge/signal_log.json`;
  ny skriver `~/bedrock/data/signal_log.json`

Disse forutsetningene er ikke nye, men gjentas her slik at refaktor-sessionene
ikke utilsiktet bryter dem.

---

## 12. Endelig sjekkliste før session 40 starter

- [ ] Bruker har godkjent denne planen
- [ ] Claude har verifisert at `~/scalp_edge/` ikke er endret siden dokumentet
      ble skrevet (`ls -la /home/pc/scalp_edge/trading_bot.py` timestamp match)
- [ ] `docs/migration/bot_refactor.md` er committet til main
- [ ] STATE.md er oppdatert med session 39-log og ny next-task = session 40

Session 39 er ren research — produserer kun dette dokumentet og en STATE.md-
oppdatering. Ingen kode-endring; ingen config-endring utenom opprettelse av
denne markdown-filen.
