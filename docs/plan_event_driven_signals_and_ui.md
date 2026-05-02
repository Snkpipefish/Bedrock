# Plan: event-drevne signal-runs + live UI-oppdateringer fra bot

**Eier:** operatør (Snkpipefish) + Claude Code
**Repo:** Snkpipefish/Bedrock @ main
**Working dir:** `/home/pc/bedrock`
**Skrevet:** 2026-05-02 (session 146)
**Brukes i:** nytt kontekst-vindu (selvstendig — ingen avhengighet til samtalehistorikk)

---

## Bakgrunn (les først)

Bedrock har to deler:

1. **Signal-pipeline** (`bedrock signals-all`): leser SQLite + YAML-config,
   scorer 22 instrumenter × 3 horisonter × 2 retninger = 132 entries,
   skriver `data/signals_bot.json`. Kjøres i dag av systemd-timer
   `bedrock-signals-bot-intraday.timer` hvert 5. min market hours.
   Cache-skip i `cli/signals_all.py:_write_if_changed` (commit `52f5a0a`)
   gjør at filen kun skrives ved faktisk endring.
2. **Bot** (`bedrock-bot.service`): user-systemd. Konsumer
   `signals_bot.json` via signal_server `/bot/signals`-endpoint, åpner/
   lukker posisjoner mot cTrader Open API. Skriver
   `~/bedrock/data/bot/signal_log.json` (trades) ved fill/close.
3. **UI** (`bedrock-server.service`): Flask + waitress på port 5100.
   Leser `signals_bot.json`, `signal_log.json`, monitor-output, viser
   alt i nettleser. UI poll'er `/api/ui/...`-endpoints **hvert 30. sek**
   (`web/assets/app.js:5` `REFRESH_INTERVAL_MS = 30_000`).

Faktiske data-endringer skjer:
- **Signal-input**: når en fetcher kjører (typisk 9-10 ganger per dag,
  gruppert 00:40-07:00 + news_intel 18:30 + ukentlige COT-runs)
- **Bot-state**: når bot åpner/lukker en posisjon (uregelmessig)

Begge cadencene (5 min for signals-all, 30 sek for UI) er
*polling-baserte gjettverdier* fra tidligere sessioner. Faktisk kunne
begge være event-drevne — utløst når noe nytt har skjedd, ikke etter
en klokke.

---

## Mål 1: event-driven signal-runs (Alt B)

### Nåværende tilstand
- `bedrock-signals-bot-intraday.timer` fyrer hvert 5. min Mon-Fri 06-21
  Oslo, kjører `bedrock signals-all --bot-only --output data/signals_bot.json`.
- 192 fyringer/dag, ~1.3 min hver = ~21 t/uke CPU.
- Cache-skip eliminerer disk-IO på no-op-runs men ikke CPU.
- Bot-en bruker live tick-priser kun til entry_zone-sjekk; setup-laget
  trenger ikke 5-min refresh i seg selv.

### Endring som ønskes
Kjør `signals-all --bot-only` **kun** rett etter en fetcher har skrevet
ny data. I praksis: ~10 ganger per dag, presist når relevant DB har
endret seg.

### Fetchers som påvirker setup-laget

Sjekk `config/fetch.yaml` for full liste. Alle disse er user-systemd-
services som `bedrock fetch`-CLI'en kaller. Eksempler:

| Fetcher | Cron (Oslo) | Påvirker setups? |
|---------|-------------|------------------|
| `bedrock-fetch-prices.service` | 00:40 daglig | **Ja** (alle pris-drivere) |
| `bedrock-fetch-fundamentals.service` | 02:30 daglig | **Ja** (FRED → real_yield, dxy_chg5d, vix_regime, etc.) |
| `bedrock-fetch-cot_disaggregated.service` | Fre 22:00 | **Ja** (positioning, cot_z_score) |
| `bedrock-fetch-cot_ice.service` | Fre 22:30 | **Ja** (cot_ice_mm_pct for Brent/NatGas) |
| `bedrock-fetch-weather.service` | 03:00 daglig | **Ja** (weather_stress) |
| `bedrock-fetch-agsi.service` | 06:00 daglig | **Ja** (storage_pct for natgas) |
| `bedrock-fetch-news_intel.service` | 06:30 + 18:30 | **Marginal** (driver ikke wired ennå) |
| `bedrock-fetch-crypto_sentiment.service` | 07:00 daglig | **Ja** (BTC/ETH-drivere) |
| `bedrock-fetch-seismic.service` | 04:00 daglig | **Ja** (mining_disruption) |
| ... (totalt 19 fetcher-runners) | | |

### Implementasjons-skritt

1. **Disable intraday-timer:**
   ```
   systemctl --user disable --now bedrock-signals-bot-intraday.timer
   ```

2. **Trigger signals-all etter hver fetcher.** To valg:

   **Alt B1 — `ExecStartPost` på fetcher-units:**
   I hver fetcher-service-fil (`systemd/bedrock-fetch-*.service`),
   legg til:
   ```ini
   [Service]
   ExecStartPost=/home/pc/bedrock/.venv/bin/bedrock signals-all --bot-only --output data/signals_bot.json
   ```
   Pros: enkelt, deklarativt. Cons: kjører selv om fetcher feilet (men
   `signals-all` er idempotent + cache-skip beskytter).

   **Alt B2 — Path-watcher på SQLite:**
   En ny `bedrock-signals-bot.path` unit som overvåker
   `data/bedrock.db`-mtime, trigger service ved endring:
   ```ini
   [Path]
   PathChanged=/home/pc/bedrock/data/bedrock.db
   Unit=bedrock-signals-bot.service
   [Install]
   WantedBy=paths.target
   ```
   Pros: fanger ALL DB-endring, også manuelle backfills. Cons: kan
   trigge for ofte hvis fetcher gjør mange små writes.

   **Anbefaling:** B1. Eksplisitt og forutsigbart. B2 kan vurderes
   senere hvis vi vil fange manuelle backfill-imports.

3. **Behold én safety-run** for å fange tilfeller hvor en fetcher
   feilet eller ble droppet:
   ```
   # Ny timer: én gang om morgenen kl 08:00 Oslo etter alle morning-fetchers
   bedrock-signals-bot-morning.timer  → OnCalendar=Mon..Fri *-*-* 08:00
   ```

4. **Verifiser:**
   - `journalctl --user -u bedrock-signals-bot.service` skal vise ~10
     runs/dag, gruppert 00:40-08:00 + 18:30 + Fre 22:30.
   - `stat data/signals_bot.json` mtime skal kun bumpe når faktisk
     fetcher har lagt til data.
   - Bot-loggen skal vise samme antall poll-events (bot poll'er
     uavhengig), men `[ALERT]`-events skal kun komme på faktisk endring.

### Filer å endre

- `systemd/bedrock-fetch-*.service` (19 filer) — legg til `ExecStartPost`
- `systemd/bedrock-signals-bot-intraday.timer` — disable
- Ny: `systemd/bedrock-signals-bot-morning.timer` (safety-run)
- `STATE.md` — sub-fase 12.9 D-spor, dokumenter endring
- `README.md` Status-blokken — oppdater "scoret hver 5. min" → "scoret
  ved hver fetcher-completion"

### Tester
- Skriv en pytest som sjekker at hver `bedrock-fetch-*.service`-fil
  har `ExecStartPost=...signals-all --bot-only`. Forhindrer regresjon.

---

## Mål 2: live UI-oppdateringer fra bot

### Nåværende tilstand
- UI poll'er `/api/ui/trade_log`, `/api/ui/bot_status`, `/api/ui/server_status`
  hvert 30. sek (`web/assets/app.js:5`).
- Bot skriver `~/bedrock/data/bot/signal_log.json` ved trade open/close
  (atomic via tempfile + os.replace; se `bot/exit.py:707-715`).
- Bot-status (running/idle/error) leses ad-hoc av `_bot_status_for_ui`
  i `signal_server/endpoints/ui.py:1435+` — basert på `/proc/<pid>/cmdline`-
  scan og siste-trade-mtime.

### Problemer med 30-sek polling
- Alle dagens 24 timer × 60 min × 2 = ~2880 polls/dag, mest no-ops.
- Trade-events kan vises opptil 30 sek for sent.
- UI viser "fersk data" i banneret selv når ingenting har endret seg.

### Endring som ønskes
- UI oppdaterer Skipsloggen, bot-status og setups *umiddelbart* når
  bot/server endrer noe.
- Sleeper resten av tiden (ingen polling).

### To realistiske implementasjoner

**Alt UI1 — Server-Sent Events (SSE):**

Ny endpoint `/api/ui/events` som server EventStream. UI åpner én
EventSource-kobling som holder seg åpen. Server pusher meldinger:

```
event: trade_log_changed
data: {"path": "data/bot/signal_log.json", "mtime": 1777737912}
```

Server detekterer endringer ved file-watcher (`watchdog`-pakken eller
inotify-API). UI lytter:
```js
const es = new EventSource('/api/ui/events');
es.addEventListener('trade_log_changed', () => loadSkipsloggen());
es.addEventListener('signals_changed', () => loadSetups());
es.addEventListener('bot_status_changed', () => loadServerStatus());
```

Pros: én vedvarende kobling, server-pushed, lite overhead. Native
nettleser-støtte. Cons: krever inotify eller polling i Python-server
for å detektere file-changes.

**Alt UI2 — WebSocket (flask-socketio):**

Tyngre dependency, flere muligheter (toveis-kommunikasjon), men
overkill for dette use-caset. Ikke anbefalt.

**Anbefaling: SSE.** Trygt, enkelt, ingen tunge dependencies.

### Hva bot må gjøre

Bot trenger ikke endres — den skriver allerede signal_log.json atomic
når trades åpnes/lukkes. Server-siden detekterer mtime-endring og
pusher event.

### Implementasjons-skritt

1. **Legg til file-watcher i signal_server.** Ny modul
   `src/bedrock/signal_server/file_watcher.py`:
   - Bruker `watchdog`-pakken (legg til i pyproject.toml).
   - Watcher følger:
     - `~/bedrock/data/bot/signal_log.json` (trades)
     - `data/signals_bot.json` (setups)
     - `data/_meta/monitor_<dato>.json` (pipeline-helse)
   - Ved `on_modified`: legg event på en thread-safe queue.

2. **Ny SSE-endpoint i `signal_server/endpoints/ui.py`:**
   ```python
   @ui_bp.get("/api/ui/events")
   def events_stream():
       def generate():
           while True:
               event = event_queue.get()  # blocking
               yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
       return Response(generate(), mimetype="text/event-stream")
   ```

3. **Bot-status-events:** bot-status detekteres p.t. fra /proc/cmdline-
   scan. Triggering på dette er ikke triviell uten polling. Forslag:
   bot kan skrive en lett "heartbeat"-fil hvert 60. sek
   (`~/bedrock/data/bot/heartbeat.json` med `{"ts": ..., "state": "active"}`).
   Watcher trigger event på endring. Krever ~10 LOC i bot/__main__.py.

4. **UI-side i `web/assets/app.js`:**
   - Erstatt `setInterval(loadSkipsloggen, REFRESH_INTERVAL_MS)` med
     `EventSource`-listener.
   - Behold initial-load ved `DOMContentLoaded` (uavhengig av events).
   - Behold 5-min safety-poll for å fange tilfeller hvor SSE-kobling
     drepte (eks. server-restart): `setInterval(loadAll, 5 * 60_000)`.

5. **Verifiser:**
   - Åpne UI, åpne en MARKET-ordre fra bot manuelt eller via test-fyll.
   - Skipsloggen skal oppdatere innen ~1 sek (ikke 30).
   - Browser-DevTools Network-tab: én vedvarende EventSource-kobling,
     ingen 30-sek-polling-bursts.

### Filer å endre

- `pyproject.toml` — legg til `watchdog` dep
- `src/bedrock/signal_server/file_watcher.py` (ny)
- `src/bedrock/signal_server/endpoints/ui.py` — ny `/api/ui/events`
- `src/bedrock/bot/__main__.py` — heartbeat-write hvert 60. sek
- `web/assets/app.js` — EventSource-listener; fjern setInterval; behold
  5-min safety
- `tests/unit/test_signal_server_events.py` (ny) — test SSE-endpoint
- `tests/unit/test_bot_heartbeat.py` (ny) — test heartbeat-write

### Tester
- File-watcher: simulér mtime-endring → forventet event på queue
- SSE-endpoint: åpne kobling, simulér event → motta SSE-payload
- Heartbeat: bot skriver fil med `state` + `ts`-felt; korrupt-handling

---

## Rekkefølge / sekvensering

Mål 1 og Mål 2 er uavhengige — kan implementeres separat.

Foreslått rekkefølge:
1. **Mål 1 (event-driven signals)** først — enklere, sparer mest CPU,
   ingen frontend-arbeid.
2. **Mål 2 (live UI)** etter — krever frontend-endringer + ny dep
   (`watchdog`), tar lengre.

Hver mål skal i sin egen sub-session med egen STATE-entry og egne
commits per logisk skritt (ikke én monster-commit).

## Risiko og fallback

- **Mål 1 risiko:** hvis en fetcher feiler, kjører ikke `ExecStartPost`.
  Mitigert av safety-run kl 08:00 + cache-skip som gjør re-runs
  trygge.
- **Mål 2 risiko:** SSE-kobling kan dø silent ved server-restart eller
  proxy-timeout. Mitigert av 5-min safety-poll i frontend som
  re-establerer EventSource.
- **Generelt:** auto-push-hook pusher hver commit — ingen manuell git
  push nødvendig. CI kjører pyright + pytest på hvert push.

## Suksess-kriterier

**Mål 1:**
- `signals-all`-runs reduseres fra 192/dag → ~10/dag
- `signals_bot.json`-mtime endrer seg kun når faktisk fetcher la til
  ny data
- Bot-loggen viser samme `[ALERT]`-events som før (intet tap av
  signaler)
- 0 regresjoner i pytest

**Mål 2:**
- UI Skipsloggen oppdaterer innen 2 sek etter bot åpner/lukker trade
- UI bot-status reflekterer endring innen 5 sek
- Network-tab i DevTools viser én EventSource-kobling, ingen
  30-sek-polling
- 5-min safety-poll fanger SSE-disconnect (testes ved kill -HUP på
  server)

---

## Kort referanse: relevante filer

| Område | Fil | Linjer |
|--------|-----|--------|
| Signals CLI | `src/bedrock/cli/signals_all.py` | hele |
| Cache-skip | `src/bedrock/cli/signals_all.py` | `_write_if_changed` |
| Adapter | `src/bedrock/signal_server/bot_adapter.py` | `HORIZON_DEFAULTS` |
| Bot entry | `src/bedrock/bot/entry.py` | `_process_watchlist_signal` |
| Bot exit | `src/bedrock/bot/exit.py` | `_log_trade_opened`, `_log_trade_closed` |
| Trade-log | `~/bedrock/data/bot/signal_log.json` | atomic write fra exit.py:707 |
| UI poll | `web/assets/app.js:1406-1407` | setInterval(loadSkipsloggen, ...) |
| UI endpoints | `src/bedrock/signal_server/endpoints/ui.py` | `_read_trade_log`, `bot_status` |
| Systemd timers | `systemd/bedrock-fetch-*.timer`, `bedrock-signals-bot-intraday.timer` | |

## Hvordan starte i nytt kontekst-vindu

```
1. cd /home/pc/bedrock
2. les denne fila: docs/plan_event_driven_signals_and_ui.md
3. les CLAUDE.md (auto-lastet) + STATE.md (topp til første ---)
4. start med Mål 1 — bekreft til operatør hva du tenker, deretter
   implementer skritt for skritt med commits per logisk endring
5. kjør scoped tests etter hver commit
6. når Mål 1 er ferdig + verifisert live → gå til Mål 2
```
