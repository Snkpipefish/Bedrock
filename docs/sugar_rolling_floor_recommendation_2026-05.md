# Sugar rullerende floor — produksjons-anbefaling (2026-05-06)

*Generert via `scripts/sugar_update_rolling_floor.py --dry-run`. State-fil:
`data/_meta/sugar_rolling_floor.json` (gitignored). Audit-trail:
`data/_meta/sugar_floor_history.jsonl` (committed).*

## Kjøring 2026-05-06

| Felt | Verdi |
|---|---|
| Lookback | 5 år (2021-05-06 → 2026-05-06) |
| Horisont | 180d |
| Target hit-rate | 55% |
| Min samples | 30 |
| Step | 7 dager (ukentlig replay) |
| Total signaler analysert (BUY) | 154 |
| Total signaler analysert (SELL) | 154 |

## Resultat

| Direction | Anbefalt floor | n@floor | hr@floor | Δ vs current |
|---|---:|---:|---:|---:|
| BUY | (ingen) | — | — | — |
| SELL | **7.5** | 141 | 55.3% | **+2.5** |

**BUY:** ingen score-terskel klarer hit-rate ≥ 55% over de siste 5 år ved n ≥ 30.
Antyder svak BUY-signal-kvalitet i dagens regime — beholder default 7.0 (analyst-prior).

**SELL:** floor=7.5 oppnår 55.3% hit-rate (n=141 av 154). Statisk floor=5.0 ville
publisert flere signaler men med dårligere kvalitet. **Δ=+2.5** er signifikant
(> APPLY_THRESHOLD=0.5).

## Beslutning

**IKKE auto-applied.** Overgang fra sell=5 → sell=7.5 er en stor regime-endring
som vil blokkere flere SELL-signaler. Operator bør:

1. Verifisere at endringen passer prod-strategi
2. Kjøre `python scripts/sugar_update_rolling_floor.py --apply` for å oppdatere
   `config/instruments/sugar.yaml` direkte
3. Re-kjøre snapshot-baseline + signals_bot.json regen

## Produksjons-tilnærming

Skriptet er designet for kvartalsvis manuell kjøring eller via systemd-user-timer.
Foreslått cadence:

```ini
# ~/.config/systemd/user/bedrock-rolling-floor-sugar.timer (foreslått, ikke wired ennå)
[Timer]
OnCalendar=*-03,06,09,12-01 06:00:00
Persistent=true
```

Ved hver kjøring:
- Beregner ny rolling-5y-floor for BUY + SELL
- Skriver state til `data/_meta/sugar_rolling_floor.json` (regenererbar — gitignored)
- Skriver historikk-entry til `data/_meta/sugar_floor_history.jsonl` (committed audit-trail)
- Med `--apply`: oppdaterer `sugar.yaml` hvis Δ > 0.5

## Stale-detection

Hvis `--apply` ikke har kjørt på > 6 mnd, viser audit-loggen at YAML-floor er
fra eldre regime. Operator bør re-evaluere.

## Bredere implementering

For å utvide til andre instrumenter:
- Generalisere skriptet til å ta `--instrument` parameter
- Sentralisere YAML-edit i bedrock.config-modulen
- Vurdere schema-utvidelse `dynamic_min_score_publish: rolling_5y` som engine
  leser fra state-fil i stedet for å ha statisk YAML-verdi (eliminerer
  YAML-redigering, men krever schema-migrasjon)
