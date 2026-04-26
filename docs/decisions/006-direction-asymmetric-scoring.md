# ADR-006: Direction-asymmetrisk scoring

Dato: 2026-04-26
Status: proposed
Fase: post-12 (session 95a, design-spike)

## Kontekst

Live-systemet (session 93+) genererer signals.json med både `BUY`- og `SELL`-
entries per `(instrument, horizon)`. Empirisk inspeksjon av
`data/signals.json` (90 entries) og `data/signals_bot.json` (etter session 92
whitelist) viser:

| Fil | Par med begge retninger | Par med identisk score |
| --- | --- | --- |
| `signals.json` (financial) | 45 | **45 / 45** |
| `signals_bot.json` (whitelist) | 51 | **51 / 51** |

Eksempel fra AUDUSD:

```
('AUDUSD', 'makro'): BUY=3.455783  SELL=3.455783  diff=0.00e+00
('AUDUSD', 'scalp'): BUY=3.482213  SELL=3.482213  diff=0.00e+00
('AUDUSD', 'swing'): BUY=3.789998  SELL=3.789998  diff=0.00e+00
```

Bot-en konsumerer begge retninger via `signals_bot.json` og handler på dem
direkte. Med identiske scores er halvparten av signal-volumet matematisk
nonsens — score reflekterer kun "hvor sterkt setupet er" som BUY-confidence,
mens SELL-leggen er en mekanisk speiling uten egen vurdering.

### Rotårsak

Tre lag konspirerer:

1. **Driver-kontrakt (`engine/drivers/__init__.py`):**
   `(store, instrument, params) → float ∈ [0,1]`.
   Driveren har ikke kjennskap til retning. By design returnerer
   den "bull-of-instrument-confidence", hvor "bull" er gitt av
   YAML-params (`bull_when`, `mode`, `invert`).

2. **`Engine.score(instrument, store, rules, horizon=...)`
   (`engine/engine.py`):**
   Tar ikke `direction`-argument. Aggregerer drivere → families →
   `GroupResult` med én `score` og én `grade`.

3. **`generate_signals` (`orchestrator/signals.py:251-272`):**
   Pre-computer `scores_by_horizon: dict[Horizon, GroupResult]` UTENFOR
   direction-løkken, så looper `for direction in [BUY, SELL]` og bruker
   samme `group_result` for begge:

   ```python
   scores_by_horizon = _compute_scores(cfg, store, horizons_list, engine)
   ...
   for horizon in horizons_list:
       group_result = scores_by_horizon[horizon]
       for direction in directions_list:
           entry = _build_entry(..., group_result=group_result, ...)
   ```

Dvs. `score`, `grade`, `families`, `active_families` på `SignalEntry` er
identisk uavhengig av `direction`. Kun `setup` (S/R-nivå-basert SL/TP) og
`build_setup`-utfall varierer mellom retningene — der bygger generator-en
faktisk asymmetrisk.

### Driver-landskapet

Av 22 drivere har de fleste en **direction-konfigurerbar** monoton skala:

| Driver | Asymmetri-mekanisme i dag | Naturlig retning |
| --- | --- | --- |
| `positioning_mm_pct` | Ingen — alltid bull-of-MM-long | Direksjonell (long-bias) |
| `cot_z_score` | Ingen — alltid bull-of-MM-long | Direksjonell |
| `real_yield` | `bull_when: low/high` | Direksjonell (asset-spesifikk) |
| `dxy_chg5d` | `bull_when: negative/positive` | Direksjonell |
| `brl_chg5d` | `bull_when: positive/negative` | Direksjonell |
| `vix_regime` | `invert: true/false` | Direksjonell |
| `range_position` | `mode: continuation/mean_revert` | Direksjonell |
| `vol_regime` | `mode: high_is_bull/low_is_bull` | Kontekst (kan tolkes begge veier) |
| `weather_stress` | `invert: true/false` | Direksjonell (yield-bias) |
| `enso_regime` | `invert: true/false` | Direksjonell |
| `wasde_s2u_change` | Sign-baked-in (S2U-fall = bull) | Direksjonell |
| `seasonal_stage` | Asset-spesifikk fenologi | Direksjonell (tidsfase) |
| `analog_hit_rate` | Threshold på forward-return | **Direksjonell men hardkodet til BUY** (forward_return >= +X%) |
| `analog_avg_return` | Mean av forward-return | **Direksjonell men hardkodet til BUY** |
| `momentum_z`, `sma200_align` | (Bull-only by definition) | Direksjonell |

Observasjon: drivere er **konfigurert** for én retning per instrument-YAML.
Gold-YAML peker drivere mot "Gold-bull". Det finnes ingen "Gold-SELL-YAML".

## Beslutning (anbefaling)

**Alt C — Engine-side flip på family-nivå med per-family `polarity`-flagg.**

Tre endringer:

### 1. `Engine.score` får `direction`-arg

```python
def score(
    self,
    instrument: str,
    store: Any,
    rules: Rules,
    horizon: str | None = None,
    direction: Direction = Direction.BUY,  # NY
) -> GroupResult:
```

Default er `BUY` for å bevare bakoverkompatibilitet med eksisterende tester
(de fleste kaller `score()` uten direction). `score_instrument` og
`generate_signals._compute_scores` propagerer `direction` videre.

### 2. `FinancialFamilySpec` / `AgriFamilySpec` får `polarity`-flagg

```python
class FinancialFamilySpec(BaseModel):
    drivers: list[DriverSpec]
    polarity: Literal["directional", "neutral"] = "directional"  # NY
```

`directional` (default): familien er en bull-of-instrument-confidence-skala.
For `direction=SELL` flippes hver drivers `value` til `1.0 - value`, og
familie-scoren regnes på nytt.

`neutral`: familien er kontekst (eks. en "regime"-familie som scorer høyt
i lav-vol-miljøer uavhengig av retning). Score er identisk for BUY og SELL.

### 3. `generate_signals` flytter score-call inn i direction-løkken

```python
for horizon in horizons_list:
    for direction in directions_list:
        group_result = engine.score(
            cfg.instrument.id, store, cfg.rules,
            horizon=_yaml_key_from_horizon(horizon),
            direction=direction,
        )
        entry = _build_entry(..., group_result=group_result, ...)
```

Dette dobler antallet `Engine.score`-kall per signals.json-regenerering
(ca. 22 instr × 3 horisonter × 2 retninger = 132 kall vs 66 i dag).
Drivere er allerede defensive + cachet på FRED/COT/prises gjennom `store`,
så marginalkostnaden er liten — målt 50-200ms per kall i tidligere sessioner.

### Hvorfor invertering på driver-nivå (ikke family-nivå)

Alternativet er å invertere `family_score` direkte:
`family_score_sell = total_family_weight - family_score_buy`. Det er enklere
men mister explain-trace for SELL: `DriverResult.value` ville fortsatt vise
bull-confidence, ikke bear-confidence. UI-modal (Fase 9 session 52) viser
driver-tabellen — den ville være misvisende.

Per-driver flip gir hver `DriverResult` en meningsfull `value` for sin
retning ("dxy_chg5d viser 0.75 bear-confidence for Gold-SELL").

### Spesialtilfeller

- **`analog_hit_rate` / `analog_avg_return`** har threshold hardkodet til
  positiv forward-return (BUY-bias). Disse kan ikke flippes naivt — for
  SELL bør threshold være `forward_return ≤ -outcome_threshold_pct`.
  Flagger som follow-up: `analog`-familien får `polarity: directional` MED
  egen invert-logikk i `_knn`-helper. Implementeres i 95b.

- **`vol_regime` med `mode: high_is_bull`** for Gold: høy ATR-percentil =
  trend-friendly. For Gold-SELL er det også trend-friendly (begge veier).
  Risk-familien bør derfor flagges `polarity: neutral` for Gold; flippes
  ikke. Per-instrument-vurdering i 95b.

## Alternativer som ble vurdert

### Alt A: Per-driver `direction`-arg

Endre kontrakt til `(store, instrument, params, direction) → float`. Hver
driver implementerer sin egen direction-håndtering.

- Pro: Maksimal presisjon — hver driver kan ha egen direction-logikk.
- Con: Bryter 22 driver-signaturer + alle eksisterende driver-tester (~150
  test-cases). Mange drivere ville gjøre `if direction == SELL: return
  1.0 - score` — meningsløs duplisering.
- Con: Driver-kontrakten ble bevisst holdt enkel (PLAN § 4 design-prinsipp:
  driver = pure function av data + params).

### Alt B: Per-direction YAML-config

Hvert instrument får `directions: { BUY: {...}, SELL: {...} }`-blokk i YAML
med separate driver-config per retning. SELL-blokken har f.eks.
`dxy_chg5d.bull_when: positive` (USD-styrke = bull SELL Gold).

- Pro: Maksimal eksplisitthet. Trader-mental-modell krystallklart per retning.
- Con: Dobler YAML-filsstørrelse. Mye duplisering for kontekst-drivere
  (vol_regime, vix_regime som er retnings-uavhengige).
- Con: Bruker har eksplisitt akseptert i CLAUDE.md "ingen logikk i YAML" —
  hver direction-spesifikk parameter ville gjøre YAML-en mer kompleks.
- Con: Krever 22 instrument-YAMLs duplisert — admin-UI (Fase 9 session 54-55)
  må re-tenkes.

### Alt C: Engine-side flip med per-family polaritet (anbefalt)

Sett over.

- Pro: Liten YAML-overhead (én ny `polarity`-felt per familie).
- Pro: Bevarer driver-kontrakten uendret.
- Pro: Per-driver inverted `value` gir meningsfull explain-trace begge veier.
- Pro: Kan rulles ut én familie av gangen (default: `directional`, så
  whitelist-instrumenter får override til `neutral` etter behov).
- Con: Familier som blander direksjonelle og nøytrale drivere må splittes.
  I praksis: ingen sånne familier i dagens 22 YAMLs (verifisert 2026-04-26).
- Con: Antagelsen om "1 - value er meningsfull bear-confidence" holder for
  monotone drivere men ikke for non-monotone (eks. seasonal_stage som
  scorer høyt i visse fenologi-faser uavhengig av direction). Disse må
  flagges per familie.

## Konsekvenser

### For 95b-implementasjon

1. **Schema-endringer (additivt):** `FinancialFamilySpec.polarity` +
   `AgriFamilySpec.polarity` med default `"directional"`.
2. **Engine-endring:** `Engine.score(direction=...)`, ny intern flip-logikk
   i `_score_families`.
3. **`generate_signals`-endring:** Flytt score-call inn i direction-løkken.
4. **YAML-migrasjon:** 22 YAMLs gjennomgås. Forventede `polarity: neutral`-
   markeringer (preliminær):
   - Gold/Silver/Platinum: `risk` neutral (vol = trend-friendly begge veier)
   - Alle: `analog` direkte med egen invert-logikk i 95b
5. **Tester:**
   - Eksisterende tester bevarer BUY-default-oppførsel — ingen brudd.
   - Nye logical-tester: "SELL-score for Gold når MM er ekstrem long er
     høy (contrarian)", "neutral-familie er identisk for BUY og SELL".
   - Snapshot-test for Gold-MAKRO BUY vs SELL viser asymmetri.

### For backtest-rammeverket (Fase 11)

`run_orchestrator_replay` allerede har `direction`-arg som propageres til
`generate_signals`. Etter 95b vil per-direction-replay vise reell
asymmetri. Tidligere Corn-A+/buy-invertert-funn (Fase 11 session 64) bør
re-evalueres — kan hende det var BUY/SELL-forveksling ikke driver-bug.

### For bot-en

Etter 95b vil `signals_bot.json` ha BUY/SELL-par med ulik score. Bot-en
har ikke logikk-endring — den filtrerer på `published=true && grade ∈ {B,A,A+}`
allerede. Forventet effekt: færre falske SELL-handler (tidligere ble
SELL alltid produsert med samme score som BUY, dvs. samme grade).

## Estimert størrelse

- ADR-006 + spike-script (denne session 95a): **liten** (ferdig).
- 95b implementasjon: **medium** — ca. 3-4 timer kode + 2-3 timer test.
  - Engine + signals.py: 100-150 linjer.
  - YAML-schema + 22 YAML-migrasjoner: ~50 linjer YAML totalt.
  - Tester: 30-50 nye logical/unit/snapshot.
  - Regenerering av signals.json + diff-rapport.

## Status etter 95a

- ADR levert.
- Bug-en empirisk bekreftet (45/45 + 51/51 par).
- Driver-landskapet kartlagt.
- Spike-script `scripts/spike_session95a_buy_sell_asymmetry.py` demonstrerer
  flip-mekanikken på ekte Gold-data (BUY-score vs flippet SELL-score).
- Ingen produksjonskode endret. Klar for 95b.

## Referanser

- `src/bedrock/engine/engine.py` — Engine.score()
- `src/bedrock/orchestrator/signals.py:251-272` — bug-lokasjonen
- `src/bedrock/engine/drivers/__init__.py` — driver-kontrakten
- ADR-001 (one engine, two aggregators) — bakgrunn for `polarity`-design
- PLAN § 4.2 (Gold-YAML), § 4.3 (Corn-YAML)
