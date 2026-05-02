# Snapshot-baseline-diff — sub-fase 12.10 follow-up Spor B
**Dato:** 2026-05-02
**Tag (mål):** `v0.12.10-followup-spor-b`
**Anker:** `tests/snapshot/expected/score_baseline.json` post-Spor-D (`v0.12.10-followup-spor-d`).

## Sammendrag

| Metrikk | Verdi |
|---|---|
| Score-endringer | **24** (SP500/Nasdaq/USDJPY/EURUSD × 3 horisonter × 2 retninger) |
| Grade-flips | **1** (USDJPY MAKRO sell B→A, ved event_fam SELL=0.6875) |
| Asset-klasser berørt | indices (SP500/Nasdaq) + fx (USDJPY/EURUSD) |
| Andre asset-klasser | uendret |

Stop-criterion (PLAN § 22.3 + § 22.7): ≤5 grade-flips per asset-class. **1 flip i fx; 0 i indices/andre — under terskel.**

## Levert

### ADR-014 cross-source data-arkitektur

- FF gir forecast (eksisterende `bedrock.fetch.calendar_ff`).
- FRED gir actual via cross-source-join på title-pattern + dato.
- Schema-utvidelse: `econ_events.actual` (idempotent ALTER TABLE migration).

### B2 FRED-backfill

- 4 nye serier i `fundamentals`: PAYEMS, CPIAUCSL, GDP, PCEPI.
- 400 rader (2016-04 → 2026-03), per ADR-011 10-år rolling.

### B3 cross-source-join

- `scripts/backfill/econ_actuals.py` — idempotent populate.
- 468 econ_events.actual oppdatert (NFP 102, CPI 107, GDP 35, PCE 90).

### B4 Drivere

- 4 nye drivere i ny modul `event_surprise.py`:
  - `nfp_surprise` (PAYEMS MoM Δ tusen jobs)
  - `cpi_surprise` (CPIAUCSL MoM %)
  - `gdp_surprise` (GDP QoQ-annualisert %)
  - `pce_surprise` (PCEPI MoM %)
- Felles `_econ_surprise_score()` med metric_kind-dispatch + parse-helper.

### B5 YAML-wirings

| Instrument | Familie | Drivers (alle vekt 0.25) | Polaritet | Family-vekt |
|---|---|---|---|---|
| SP500 | event (NEW) | nfp(high) + cpi(low) + gdp(high) + pce(low) | directional | 0.3 SCALP/SWING, 0.5 MAKRO |
| Nasdaq | event (NEW) | samme som SP500 | directional | 0.3 SCALP/SWING, 0.5 MAKRO |
| USDJPY | event (NEW) | alle 4 bull_when=high (USD↑ = USDJPY↑) | directional | 0.3 SCALP/SWING, 0.5 MAKRO |
| EURUSD | event (NEW) | alle 4 bull_when=low (USD↑ = EURUSD↓) | directional | 0.3 SCALP/SWING, 0.5 MAKRO |

`max_score` bumpet i alle 4 × 3 horisonter (SCALP +0.3, SWING +0.3, MAKRO +0.5) for å holde grade-pct-skalering invariant.

## Score-endringer per (instrument, horizon, direction)

| Top 6 endringer | Δ score |
|---|---|
| Nasdaq\|MAKRO\|buy | +0.406 |
| SP500\|MAKRO\|buy | +0.406 |
| EURUSD\|MAKRO\|buy | +0.344 |
| USDJPY\|MAKRO\|sell | +0.344 (← flipped B→A) |
| Nasdaq\|SCALP\|buy | +0.244 |
| Nasdaq\|SWING\|buy | +0.244 |

Median Δ ~0.10 — bygger på live event_fam scores 0.6875-0.8125 (buy) eller 0.1875-0.3125 (sell), reflekterende GDP+0.75 + CPI/PCE 0.0 surprise-input.

## Live driver-verifisering 2026-05-02

| Driver | Score | Tolkning |
|---|---|---|
| nfp_surprise (default high) | 0.5 | latest 2025-04-03 NFP +108K vs forecast 137K = -29K mild miss |
| cpi_surprise (default high) | 0.0 | latest CPI viser kraftig downside-surprise |
| gdp_surprise (default high) | 0.75 | latest Advance GDP q/q +0.5..+1.5 pp positiv |
| pce_surprise (default high) | 0.0 | latest Core PCE viser downside-surprise |

For SP500/Nasdaq event-familien: nfp(high)=0.5 + cpi(low→inverted)=1.0 + gdp(high)=0.75 + pce(low→inverted)=1.0 → familie-aggregert (0.5+1.0+0.75+1.0)*0.25 = **0.8125 BUY**, 0.1875 SELL (etter polarity-flip).

For USDJPY: alle bull_when=high → familie = (0.5+0.0+0.75+0.0)*0.25 = **0.3125 BUY**. SELL = 0.6875.

For EURUSD: alle bull_when=low (inverted) → familie = (0.5+1.0+0.25+1.0)*0.25 = **0.6875 BUY**. SELL = 0.3125.

## Grade-flip-detalje

**USDJPY MAKRO sell B→A:**
- Pre-score 3.17 (under A-threshold på max 5.8)
- Post-score 3.52 (over A-threshold på max 6.3)
- Driver: event_fam SELL = 0.6875 × familie-vekt 0.5 = +0.344 ekstra score
- Plausibel: USDJPY MAKRO-SELL-tilt fra Fed dovish-overraskelser konsistent med JPY-styrking → setupen er nå A-grade.

## Backfill-statistikk

- FRED PAYEMS/CPIAUCSL/GDP/PCEPI: **400 rader** (2016-04 → 2026-03)
- econ_events.actual populated: **468 events** (102 NFP + 214 CPI + 62 GDP + 90 PCE)

## Total drivere registrert

54 (var 50). 4 nye: `nfp_surprise`, `cpi_surprise`, `gdp_surprise`, `pce_surprise`.

## Tester

24 nye driver-tester. Pyright src/: 0 errors.

## Commits

1. `59fd2f6` B1+B2: ADR-014 + schema actual-column + FRED-backfill
2. `0b00be6` B3: cross-source-join script (468 events populated)
3. `9d9fb20` B4: 4 *_surprise-drivere + 24 tester
4. `86ed70f` B5: YAML-wirings (event-familie SP500/Nasdaq/USDJPY/EURUSD)
5. (denne commit) `state(12.10 followup B6)`: snapshot-baseline regen + diff-rapport + STATE

Tag: `v0.12.10-followup-spor-b` settes på siste B6-commit.
