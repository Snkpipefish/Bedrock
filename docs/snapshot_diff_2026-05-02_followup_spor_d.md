# Snapshot-baseline-diff — sub-fase 12.10 follow-up Spor D
**Dato:** 2026-05-02
**Tag (mål):** `v0.12.10-followup-spor-d`
**Anker:** `tests/snapshot/expected/score_baseline.json` post-Spor-C (`v0.12.10-followup-spor-c`).

## Sammendrag

| Metrikk | Verdi |
|---|---|
| Score-endringer | **6** (Corn/Soybean/Wheat × 2 retninger) |
| Grade-flips | **0** (godt under stop-criterion ≤5/asset-class) |
| Asset-klasser berørt | grains (Corn + Soybean + Wheat) |
| Andre asset-klasser | uendret |

Stop-criterion (PLAN § 22.3 + § 22.7): ≤5 grade-flips per asset-class. **0/0 — godt under terskel.**

## Wirings levert

### Corn
- yield-family: `nass_yield_corn_yoy@0.20` (weather/crop_progress 0.50→0.40 hver)
- cross-family: `nass_grain_stocks_quarterly@0.10` (CORN/TOTAL; dxy 0.45→0.35)

### Soybean
- yield-family: `nass_yield_soy_yoy@0.20` (weather/crop_progress 0.25→0.20, wasde 0.50→0.40)
- cross-family: `nass_grain_stocks_quarterly@0.10` (SOYBEANS/TOTAL; dxy 0.55→0.45)

### Wheat
- cross-family: `nass_grain_stocks_quarterly@0.10` (WHEAT/TOTAL; dxy 0.30→0.20)
- yield-family uendret (Wheat har ikke separat NASS-yield-driver registrert; conab/wasde/disease/export-mix beholdes)

## Score-endringer per (instrument, direction)

Agri-instrumenter har én horisont (NONE) i baseline-tabellen.

| key | Pre score | Post score | Δ score | Pre grade | Post grade |
|---|---|---|---|---|---|
| Corn\|NONE\|buy | 8.733 | 8.682 | -0.052 | B | B |
| Corn\|NONE\|sell | 9.067 | 9.118 | +0.052 | B | B |
| Soybean\|NONE\|buy | 8.462 | 8.390 | -0.073 | A | A |
| Soybean\|NONE\|sell | 8.938 | 9.010 | +0.073 | A | A |
| Wheat\|NONE\|buy | 10.058 | 9.988 | -0.070 | A | A |
| Wheat\|NONE\|sell | 4.542 | 4.612 | +0.070 | C | C |

**Hovedfunn:**
- Per-instrument symmetric flip mellom buy/sell — konsistent med ADR-006 directional-polarity.
- Effekten er modest (~0.05-0.07 score-Δ) fordi de nye driverne har vekt 0.10-0.20 og NASS-data live (yield +1.9% YoY; stocks +10.7% YoY) gir mid-range scores (0.35 og 0.15).
- Cross-family endring +0.035 på buy-side (-0.035 på sell) drevet av nass_grain_stocks_quarterly=0.15 (current data peker bear → score ned for buy).
- Yield-family endring liten +0.005 buy-side, -0.005 sell-side fordi nass_yield_corn_yoy=0.35 er nær neutral 0.50.
- Andre 6 asset-klasser (energy/fx/metals/indices/crypto/softs) uendret.

## Live driver-verifisering 2026-05-02

| Driver | Verdi | Tolkning |
|---|---|---|
| nass_yield_corn_yoy | 0.35 | 2025 yield 186.5 vs 2024 ~183 (+1.9% YoY) → mild bear-of-prising |
| nass_yield_soy_yoy | 0.35 | Mild positive YoY → mild bear |
| nass_grain_stocks_quarterly Corn | 0.15 | Mar 2026 (9.02e9) vs Mar 2025 (8.15e9) = +10.7% → bear |
| nass_grain_stocks_quarterly Soy | 0.15 | Tilsvarende stocks-vekst |
| nass_grain_stocks_quarterly Wheat | 0.15 | Tilsvarende stocks-vekst |

Alle 5 (instrument, driver)-kombinasjoner returnerer ikke-default-verdier — signalene aktive.

## Backfill-statistikk

- NASS yield: **443 rader** (CORN/SOYBEANS/WHEAT/COTTON × 9 år 2017-2025; 2026 venter på sesongen)
- NASS grain_stocks: **444 rader** (CORN/SOYBEANS/WHEAT × 10 år 2017-2026 × 4 quartals × 3 categories)

## Total drivere registrert

50 (var 47). Tre nye: `nass_yield_corn_yoy`, `nass_yield_soy_yoy`, `nass_grain_stocks_quarterly`.

## Tester

64 nye tester på Spor D (29 store/proxy + 15 fetcher + 20 driver). Pyright src/: 0 errors.

## Commits

1. `6ac2b99` D1: schema (DDL + Pydantic + DataStore + AsOfDateStore + 29 tester)
2. `2996fa0` D2: nass.py utvidelse (yield_api + grain_stocks_api + 15 tester)
3. `4700ba9` D3: drivere nass_yield_corn_yoy + nass_yield_soy_yoy + nass_grain_stocks_quarterly + 20 tester
4. `eaa1eda` D4: backfill-script + live-ingest (443 + 444 rader) + YAML-wirings (Corn/Soybean/Wheat × 5 wirings)
5. (denne commit) `state(12.10 followup D)`: snapshot-baseline regen + diff-rapport + STATE

Tag: `v0.12.10-followup-spor-d` settes på siste D5-commit.
