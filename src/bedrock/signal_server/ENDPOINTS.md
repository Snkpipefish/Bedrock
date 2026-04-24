# Signal-server endepunkt-inventar

Kilde: `~/scalp_edge/signal_server.py` (974 linjer). Hver endepunkt-
gruppe flyttes til egen modul i `bedrock.signal_server.endpoints.*`
gjennom Fase 7 sessions.

## Status per endepunkt

| Gruppe | Endepunkt | Metode | Status | Modul (planlagt) |
|---|---|---|---|---|
| meta | `/health` | GET | **implementert** (session 33) | `app.py` |
| meta | `/status` | GET | **implementert** (session 33) | `app.py` |
| alerts | `/push-alert` | POST | **implementert** (session 35) | `endpoints/alerts.py` |
| alerts | `/push-agri-alert` | POST | **implementert** (session 35) | `endpoints/alerts.py` |
| signals | `/signals` | GET | **implementert** (session 34) | `endpoints/signals.py` |
| signals | `/agri-signals` | GET | **implementert** (session 34) | `endpoints/signals.py` |
| signals | `/invalidate` | POST | pending | `endpoints/signals.py` |
| kills | `/kill` | POST | pending | `endpoints/kills.py` |
| kills | `/clear_kills` | POST | pending | `endpoints/kills.py` |
| prices | `/push-prices` | POST | pending | `endpoints/prices.py` |
| prices | `/prices` | GET | pending | `endpoints/prices.py` |
| uploads | `/upload` | POST | pending | `endpoints/uploads.py` |
| rules (ny) | `/admin/rules` | GET/PUT | pending | `endpoints/rules.py` |

## Session-plan (foreløpig)

- Session 33 ✓ — app-factory + `/health` + `/status` + ENDPOINTS.md
- Session 34 ✓ — `endpoints/signals.py`: `/signals`, `/agri-signals`
  (read-only, Pydantic-validering av fil-innhold)
- Session 35 ✓ — `endpoints/alerts.py`: `/push-alert`, `/push-agri-alert`
  (skriv-path; Pydantic body-validering; atomic append)
- Session 36 — `endpoints/kills.py` + `/invalidate`
- Session 37 — `endpoints/prices.py` + `endpoints/uploads.py`
- Session 38 — `endpoints/rules.py` (PLAN § 8.3 — ny funksjonalitet,
  YAML-editering via UI)

Schema-valdiering (Pydantic) på innkommende body er en del av hver
endepunkt-session. Gammel scalp_edge aksepterte ustrukturert JSON —
bedrock krever validert Pydantic-model eller 400-respons.

## Port-konvensjon under parallell-drift

- Gammel `scalp_edge.signal_server`: **5000**
- Bedrock signal-server: **5100** (se `config.py` default)

Bot og UI må peke på riktig server. Ved cutover (Fase 13) byttes
bot-config til 5100 og gammel server skrus av.
