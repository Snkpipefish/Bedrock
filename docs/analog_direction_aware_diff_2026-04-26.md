# Analog-driver direction-aware — diff-rapport (session 100)

Dato: 2026-04-26
Implementerer ADR-006 § Spesialtilfeller for `analog`-familien.

## Bakgrunn

ADR-006 (session 95b) flagget at `analog_hit_rate` har threshold hardkodet
til positiv forward-return (+X%). Engine-side flip (1 - hit_rate) for SELL
ga **misvisende SELL-score**:

- Eksempel: Gold 30d har 34.5% BUY-hit-rate (real, fra session 99-backtest).
  Engine-flip ga SELL = 1 - 0.345 = **0.655** — overestimering med ~45pp.
- Reell SELL-hit-rate (forward_return ≤ -3%) er **20.7%**.

## Endringer

### Engine

`_score_families` propagerer nå `_direction` (BUY/SELL) i en kopi av
driver-params. Drivere som er direction-aware leser dette; andre ignorerer.

```python
params_with_dir = {**driver_spec.params, "_direction": direction.value}
raw_value = fn(store, instrument, params_with_dir)
```

### analog-driverne

- `analog_hit_rate`: leser `_direction`. For SELL teller naboer med
  `forward_return ≤ -threshold` istedenfor `≥ +threshold`.
- `analog_avg_return`: leser `_direction`. For SELL flippes avg-fortegn
  før threshold-mapping (samme som eksisterende `direction: invert`).

### YAML-migrasjon

22 instrumenter har nå `polarity: neutral` på `analog`-familien — engine
skal ikke flippe driver-output, fordi driveren håndterer asymmetrien selv.

## Effekt på signals.json (financial)

- 66/90 par endret score (>0.001)
- **38/90 grade-flips** (mest SELL-side dropp)
- Median spread: -0.3 (SELL går ned)
- Min: -1.20 (SELL MAKRO ned)
- Max: +0.84 (BUY mer optimistisk for sterk-bias-instrumenter)

### Topp SELL-dropp (MAKRO)

Tidligere ga engine-flip SELL ~0.5 selv på sterk-BUY-bias-instrumenter:

| Instrument | Pre score | Post score | Delta | Grade |
| --- | ---: | ---: | ---: | --- |
| Copper MAKRO sell | 2.60 | 1.40 | -1.20 | B→C |
| EURUSD MAKRO sell | 3.66 | 2.46 | -1.20 | A→B |
| Nasdaq MAKRO sell | 3.61 | 2.41 | -1.20 | A→B |
| Platinum MAKRO sell | 2.78 | 1.58 | -1.20 | B→C |
| USDJPY MAKRO sell | 3.57 | 2.37 | -1.20 | A→B |
| BTC MAKRO sell | 2.41 | 1.21 | -1.20 | B→C |
| SP500 MAKRO sell | 2.59 | 1.39 | -1.20 | B→C |
| Silver MAKRO sell | 4.01 | 3.05 | -0.96 | A→B |

Alle disse er konsistente med session 99-backtest: instrumenter med
strukturell BUY-bias har lavere SELL-hit-rate enn 50%, så engine-flip-en
overestimerte. Nå gir driveren realistisk SELL-score.

## Bot-impact

`signals_bot.json` har samme retning: SELL-grades dropper for
BUY-bias-instrumenter, færre A/A+ SELL-signaler pushes til bot.
Forventet: bot tar færre falske SELL-handler.

## Tester

- 5 nye direction-aware-tester i `tests/unit/test_analog_drivers.py`
- 1 oppdatert test i `tests/unit/test_engine_smoke.py` (forventer
  `_direction`-key i propagerte params)
- 1 oppdatert test i `tests/unit/test_analog_realdata.py` (Silver har
  outcomes etter session 99 — bruker oppdiktet "Foobar" istedenfor)
- Total: 1450/1450 grønt
- Pyright 0 errors

## Designvalg

Vurderte tre alternativer:

1. **Endre driver-kontrakt** til `(store, instrument, params, direction)` —
   bryter 22 driver-signaturer + ~150 tester. For invasiv.
2. **Invertere fortegnet på `forward_return_pct` i `analog_outcomes`** for
   SELL — krever per-direction-data-lag, dobbelt lagring.
3. **Engine propagerer `_direction` i params** ✅ valgt — minst invasiv,
   bevarer driver-kontrakt, kun analog-familien er affected.

`polarity: neutral` på YAML-siden gjør at engine ikke flipper analog-
driverens output (ADR-006 standard-flip). Andre familier beholder
default `directional`-polaritet.

## Follow-ups

- (Optional) `analog_avg_return.score_thresholds` har asymmetriske
  default-terskler — kan utvides med ekspliserte SELL-terskler hvis
  observasjon viser systematisk skjevhet.
- (Optional) Gold/SP500/Nasdaq strukturell BUY-bias er real (session 99
  backtest); kan vurderes asymmetrisk publish-floor i tillegg.
