# ADR-015: Monitor `stale_hours` reflekterer kilde-publiserings-lag, ikke fetch-cadence

Dato: 2026-05-06
Status: accepted
Fase: 12.5 (helse-oppretting, session-tail)
Refererer til: ADR-007 (fetch-port-strategi), ADR-008 (per-fetcher mapping)

## Kontekst

`scripts/monitor_pipeline.py` (via `bedrock.parallel.monitor.check_fetcher_freshness`)
bruker `age_hours = now - max(<ts_column>)` for hver fetcher, og kategoriserer
mot `stale_hours` fra `config/fetch.yaml`:

- `age < stale_hours` → fresh
- `stale_hours ≤ age < 2×stale_hours` → aging (advarsel)
- `age ≥ 2×stale_hours` → stale (FAIL)

Tersklene var historisk satt nær fetch-cadencen (f.eks. `comex: 30` for daglig
fetch), under antakelsen om at fersk fetch ⇒ fersk data.

I praksis publiserer de fleste makro-kilder med strukturell forsinkelse:

| Fetcher | Cron | Kilde-lag | Effekt med gammel terskel |
|---|---|---|---|
| comex | Mon-Fri 22:00 Oslo | CME positions T+1 til T+2 | aging fra Tue 22h, stale fra Wed morning |
| shipping | Mon-Fri 23:30 Oslo | Yahoo D+1 | aging fra Mon 06:30 monitor (helg-effekt) |
| agsi | Daglig 06:00 Oslo | ENTSOG D+1 til D+2 | aging fra ~24h, stale ved Mon morning |
| alsi | Daglig 06:05 Oslo | GIE D+1 til D+2 | samme mønster |

Konsekvensen var at fetcherne kjørte feilfritt (verifisert via `journalctl --user`
2026-05-06: 0/0 failed på alle fire), men monitor flagget RØD daglig pga normal
publiserings-lag fra kilden — ikke pga manglende kjøring eller dataproblem.

Falske RØD-alarmer fra normal-mønster gjør at operatøren venner seg til å
ignorere statusen, og når en *ekte* feil inntreffer (f.eks. en fetcher som
slutter å fyre — som var hva session 2026-05-06 oppdaget for `news_intel` +
`crypto_sentiment`-timere), oppdages den ikke.

## Beslutning

`stale_hours` skal reflektere **maksimum tid fra kildens publiseringssyklus
til vi forventer å ha den dataen**, ikke fetch-cadencen alene.

Operasjonell tommelfingerregel: `stale_hours = kilde-lag + fetch-cadence + margin
for helg eller cron-glipp`.

Konkret bumpet i denne sessionen:

| Fetcher | Gammel | Ny | Begrunnelse |
|---|---|---|---|
| comex | 30 | **60** | T+1 lag + helg-buffer (Fri-data eldre enn 60h Mon morning er reell feil) |
| shipping | 30 | **48** | D+1 Yahoo + Mon-morning helg-buffer |
| agsi | 36 | **60** | ENTSOG D+1 typisk, observert til D+2 |
| alsi | 36 | **60** | GIE D+1 typisk, observert til D+2 |

`fundamentals` (FRED) har allerede `stale_hours: 48` med kommentaren "FRED-data
har 1-3 dagers publiserings-lag" — denne ADR-en formaliserer mønsteret som
allerede var etablert der.

## Konsekvenser

Positive:
- Falske RØD-alarmer eliminert for normalt fetch + publiserings-mønster.
- Reell-feil-deteksjon bevart: en fetcher som *slutter å kjøre* vil treffe
  den nye, høyere terskelen innen 60h og fortsatt flagge stale.
- Monitor-RØD blir igjen et meningsfullt signal som krever handling.

Negative:
- Vinduet for å oppdage en stille fetcher-svikt er bredere (60h vs 30h). For
  daglige fetchers betyr det 1-2 dager i stedet for 12-18 timer.
- En kilde som plutselig flytter publiserings-vinduet ut over D+2 vil ikke
  flagge før etter 60h — forutsetter at vi merker det via signal-kvalitet,
  ikke via monitor.

Nøytrale (men verdt å nevne):
- ADR-en avgrenser ikke alle fetchere. `weather_monthly` (720), `eia_inventories`
  (264), `cot_*` (264) er allerede romslige. Hvis flere fetchers viser samme
  mønster — falsk RØD pga publiserings-lag, ikke svikt — gjelder samme regel.
- Alternativ semantikk (måle siste *fetch-tid* i stedet for `max(ts_column)`)
  ble vurdert, se nedenfor.

## Alternativer vurdert

- **Alternativ A: Bump `stale_hours` til kilde-lag-bevisste verdier (valgt).**
  - Pro: liten endring, beholder semantikken "alarm når data er gammelt".
  - Con: krever per-fetcher kunnskap om publiseringssyklus.

- **Alternativ B: Endre `age_hours`-måling til siste fetch-tid (siste rad
  innsatt i tabellen, eller siste vellykkede systemd-trigger).**
  - Pro: korrekt semantikk — alarmen fyrer hvis fetcher ikke har kjørt,
    uavhengig av kilde-lag.
  - Con: krever endring i `bedrock.parallel.monitor.FetcherStatus`-modell og
    nytt persistens-felt (siste-fetch-tid). Større endring, høyere risiko, og
    skjuler tilfeller der fetcher kjører men ikke får data (smart-skip uten
    publisering oppstrøms). I så fall vil vi *fortsatt* trenge et kilde-lag-mål.
  - Avvist: bumping er nok for nåværende behov; B kan vurderes igjen hvis
    monitor-presisjon trenger ytterligere skjerping.

- **Alternativ C: La det stå, og akseptere RØD som normaltilstand.**
  - Pro: null endring.
  - Con: status-blindhet er den verste utgangen — RØD må bety noe.
  - Avvist.

## Referanser

- `config/fetch.yaml` (linje 126-140 agsi/alsi, 172-178 shipping, 221-227 comex)
- `src/bedrock/parallel/monitor.py:check_fetcher_freshness`
- Session 2026-05-06: oppdaget at `news_intel.timer` + `crypto_sentiment.timer`
  var `linked` men ikke `enabled` (rot-årsak til stale-flagging fra timer-feil
  som ble blandet med kilde-lag-flagging fra terskel-feil)
