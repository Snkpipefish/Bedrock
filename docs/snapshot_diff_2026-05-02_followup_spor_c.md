# Snapshot-baseline-diff — sub-fase 12.10 follow-up Spor C
**Dato:** 2026-05-02
**Tag (mål):** `v0.12.10-followup-spor-c`
**Anker:** `tests/snapshot/expected/score_baseline.json` post-Spor-A11 (`v0.12.10-followup-a11`).

## Sammendrag

| Metrikk | Verdi |
|---|---|
| Score-endringer | **12** (av 104 (instrument, horizon, direction)-kombinasjoner) |
| Grade-flips | **0** (godt under stop-criterion ≤5/asset-class) |
| Asset-klasser berørt | energy (NaturalGas + Brent) |
| Andre asset-klasser | uendret |

Stop-criterion (PLAN § 22.3 + § 22.7): ≤5 grade-flips per asset-class. **0/0 — godt under terskel.**

## Wirings levert

### NaturalGas macro (15 drivere, sum=1.00)

Tre nye drivere lagt til:
- `alsi_eu_pct@0.05` (MAKRO-only) — LNG-buffer parallel til AGSI
- `alsi_storage_change@0.05` (alle horisonter) — LNG drawdown-momentum
- `iip_supply_unavailability@0.05` (alle horisonter) — REMIT supply-side stress

Trim:
- `eia_stock_change` 0.25→0.15 (-0.10)
- `dxy_chg5d` 0.15→0.10 (-0.05)

### Brent macro (11 drivere, sum=1.00)

Én ny driver lagt til:
- `iip_supply_unavailability@0.05` (alle horisonter) — REMIT spillover (gas→olje-substitusjon under europeiske kriser)

Trim:
- `dxy_chg5d` 0.15→0.10 (-0.05)

ALSI ikke lagt til Brent — LNG-storage er mindre direkte koblet til Brent-prising vs EIA crude-rapport.

## Score-endringer per (instrument, horizon, direction)

| key | Δ macro-family | Δ score | Pre grade | Post grade |
|---|---|---|---|---|
| Brent\|SCALP\|buy | +0.0125 | +0.0100 | A | A |
| Brent\|SCALP\|sell | -0.0125 | -0.0100 | B | B |
| Brent\|SWING\|buy | +0.0125 | +0.0125 | A | A |
| Brent\|SWING\|sell | -0.0125 | -0.0125 | B | B |
| Brent\|MAKRO\|buy | +0.0125 | +0.0163 | A | A |
| Brent\|MAKRO\|sell | -0.0125 | -0.0163 | B | B |
| NaturalGas\|SCALP\|buy | +0.0967 | +0.0580 | B | B |
| NaturalGas\|SCALP\|sell | -0.0967 | -0.0580 | B | B |
| NaturalGas\|SWING\|buy | +0.0967 | +0.0774 | B | B |
| NaturalGas\|SWING\|sell | -0.0967 | -0.0774 | B | B |
| NaturalGas\|MAKRO\|buy | +0.0750 | +0.0750 | C | C |
| NaturalGas\|MAKRO\|sell | -0.0750 | -0.0750 | B | B |

**Hovedfunn:**
- NG macro-family øker ~0.10 buy-side (synker tilsvarende sell-side) — drevet av to bidrag: `alsi_storage_change=0.75` (5d drawdown) + `iip_supply_unavailability=0.75` (active EU REMIT-stress). `alsi_eu_pct=0.5` neutral i MAKRO. Dette er mindre i SCALP/SWING (ikke-MAKRO inkluderer ikke alsi_eu_pct).
- Brent macro-family øker bare ~0.013 fordi kun IIP er wired (én driver vs tre i NG).
- Ingen grade-flips: deltaene er små og holder seg innenfor eksisterende grade-bånd.

## Live driver-verifisering 2026-05-02

| Driver | Verdi | Tolkning |
|---|---|---|
| alsi_eu_pct (eu) | 0.50 | EU LNG 52.9% full → nøytral 30-55%-range |
| alsi_eu_pct (de) | 0.25 | DE 55-75%-range = mild bear |
| alsi_eu_pct (es) | 0.25 | ES 55-75%-range = mild bear |
| alsi_storage_change (eu, 5d) | 0.75 | -5..-10% WoW = bull |
| alsi_storage_change (eu, 14d) | 1.00 | ≤-10% over 14d = sterk bull |
| iip_supply_unavailability (active) | 0.75 | 2000-5000 GWh/d EU-stress = bull |
| iip_supply_unavailability (recent 30d) | 1.00 | >5000 GWh/d publisert siste 30d |

Alle tre nye drivere returnerer ikke-default-verdier — signalene aktive.

## Backfill-statistikk

- ALSI: **21924 rader** (6 countries × ~3654 dager 2016-04 → 2026-04). Per ADR-011 10-år rolling.
- IIP REMIT: **10628 rader** (full arkiv 2022-01-31 → 2026-05-02, 213 sider).

## Total drivere registrert

47 (var 44). Tre nye: `alsi_eu_pct`, `alsi_storage_change`, `iip_supply_unavailability`.

## Tester

95 nye tester på Spor C (32 store/proxy + 37 fetcher + 26 driver). Pyright src/: 0 errors.

## Commits

1. `feat(12.10 followup C1)`: schema (DDL + Pydantic + DataStore + AsOfDateStore + 32 tester)
2. `feat(12.10 followup C2)`: fetchere alsi.py + iip.py + 37 tester
3. `feat(12.10 followup C3)`: drivere alsi_eu_pct + alsi_storage_change + iip_supply_unavailability + 26 tester
4. `feat(12.10 followup C4a)`: backfill-scripts + live-ingest (21924 + 10628 rader)
5. `feat(12.10 followup C4b)`: YAML-wirings (NaturalGas + Brent macro)
6. (denne commit) `state(12.10 followup C5)`: snapshot-baseline regen + diff-rapport

Tag: `v0.12.10-followup-spor-c` settes på siste C5-commit.
