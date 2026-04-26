# Direction-asymmetric scoring — diff-rapport (session 95b)

Dato: 2026-04-26
Implementasjon av ADR-006.

## Sammendrag

| Fil | Entries | Par med ULIK BUY/SELL pre | Par med ULIK BUY/SELL post |
| --- | ---: | ---: | ---: |
| `signals.json` (financial) | 90 | 0/45 | **45/45** |
| `agri_signals.json` | 42 | 0/21 | **21/21** |
| `signals_bot.json` (whitelist) | 102 | 0/51 | **51/51** |

Bug fullstendig fikset: alle BUY/SELL-par har nå ulik score.

## Score-spread distribusjon

| Fil | Min |abs(BUY-SELL)| | Median | Max |
| --- | ---: | ---: | ---: |
| `signals.json` (financial) | 0.014 | 0.972 | 2.953 |
| `agri_signals.json` | 0.997 | 4.098 | 6.360 |
| `signals_bot.json` | 0.014 | 1.079 | 6.360 |

Agri-instrumenter har større spread fordi additive_sum-aggregator
multipliserer med family_cap (typisk 2.0-5.0), mens financial bruker
horizon-vekter (typisk 0.5-1.3).

## Endringer pre vs post (financial signals.json)

- 34/90 entries har endret grade (38%)
- 11/90 entries har endret published-flag (12%)

## Per-familie effekt (Gold MAKRO som eksempel)

| Familie | Polaritet | BUY | SELL | Diff |
| --- | --- | ---: | ---: | ---: |
| trend | directional | 0.7500 | 0.2500 | +0.50 |
| positioning | directional | 0.3852 | 0.6148 | -0.23 |
| macro | directional | 0.4500 | 0.5500 | -0.10 |
| structure | directional | 0.6624 | 0.3376 | +0.32 |
| risk | **neutral** | 0.7649 | 0.7649 | 0.00 |
| analog | directional | 0.4500 | 0.5500 | -0.10 |

Risk-familien (vol_regime mode=high_is_bull) er neutral fordi trend-
friendly volatilitet er gunstig for både BUY og SELL.

## Implementasjons-detaljer

### Endringer i Engine

- `FinancialFamilySpec.polarity: Literal["directional", "neutral"]`
  default `"directional"`
- `AgriFamilySpec.polarity: Literal["directional", "neutral"]`
  default `"directional"`
- `Engine.score(direction: Direction = Direction.BUY)` — default BUY
  bevarer bakoverkompatibilitet
- `_score_families` flipper `value = 1.0 - raw_value` per driver når
  `direction == SELL` og familiens polarity er `"directional"`.
  `contribution` reaggregreres.

### Endringer i orchestrator

- `signals.py::_compute_scores` returnerer nå
  `dict[(Horizon, Direction), GroupResult]` istedenfor
  `dict[Horizon, GroupResult]`
- `generate_signals` flytter score-call inn i direction-løkken
- `score_instrument` propagerer ny `direction`-arg

### YAML-migrasjon

15 instrumenter med `vol_regime mode: high_is_bull` fikk
`polarity: neutral` på risk-familien:

audusd, brent, btc, copper, crudeoil, eth, eurusd, gbpusd, gold,
nasdaq, naturalgas, platinum, silver, sp500, usdjpy.

Alle andre familier på alle instrumenter beholder default
`polarity: directional`.

## Tester

- 10 nye tester i `tests/unit/test_engine_direction_polarity.py`
- 1 oppdatering i `tests/logical/test_orchestrator_signals.py` (forventer
  nå asymmetri istedenfor `score > 0` for både retninger)
- Total: 1438/1438 grønt (var 1428/1428 + 10 nye + 1 oppdatert)
- Pyright: 0 errors

## Bot-impact

`signals_bot.json` (102 entries → 17 whitelist-instrumenter × ~6 entries)
har nå ulik score for BUY og SELL. Bot-en filtrerer på `published=true`
+ grade — den krever ingen kode-endring. Forventet effekt:

- Færre falske SELL-handler (tidligere fikk SELL alltid samme grade som
  BUY; nå evalueres uavhengig)
- Bedre signal-til-støy-forhold på handelssiden

## Follow-ups (utsatt)

- `analog`-familien har threshold hardkodet til positiv forward-return
  (`forward_return ≥ +X%`). Med flippen blir høy hit-rate for BUY → lav
  hit-rate for SELL mekanisk. For ekte SELL-asymmetri burde threshold
  flippes til `forward_return ≤ -X%`. Krever endring i `_knn`-helper i
  `analog.py`. Flagget i ADR-006 § Spesialtilfeller; gjøres i egen session.
- Per-instrument vurdering av `polarity: neutral` for andre familier
  (eks. `trend.sma200_align` for mean-reverting instrumenter).
  Empirisk: vurder etter 1-2 ukers obs av bot-handler.
