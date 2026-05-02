# Sub-fase 12.10 Bunke 9 — Snapshot-diff-rapport

**Dato:** 2026-05-02
**Sammenligning:** baseline post-Bunke 8 vs post-Bunke 9 (+ FRED/Yahoo/NOAA/EIA-backfills som har påvirket live-data siden Bunke 3)

## Sammendrag
- Total entries: 104
- Score-endringer (≥1e-6): 24 (alle metals)
- **Grade-flips: 0** ✓ stop-criterion oppfylt

## Per asset-class
| Asset-class | Score-endringer | Grade-flips |
|---|---|---|
| crypto | 0 | 0 |
| energy | 0 | 0 |
| fx | 0 | 0 |
| grains | 0 | 0 |
| indices | 0 | 0 |
| metals | 24 | 0 |
| softs | 0 | 0 |

## Tolkning
24 metals-score-endringer kommer fra Bunke 9 #33 (mining_disruption min_magnitude
4.5 → 5.5) som gir litt færre events innenfor lookback-vinduet. Ingen grade-flips —
endringene er små nok til å holde seg innenfor eksisterende grade-buckets.

#35 comex_stress min_samples=180 påvirker ikke baseline siden tester via
DataStore-direct (ikke AsOfDateStore) ser hele tabellen — men comex_inventory
har p.t. 4 rader i live-DB, så driveren returnerer nå 0.5 (var ~stress-base
før). Effekten på Gold/Silver/Copper macro-familie er at comex_stress-bidraget
er deaktivert til ≥180 dager backfill er på plass.

## Sub-fase 12.10 Bunke 9 status
2 av 13 endringer levert som driver-default-bumps:
- #33 mining_disruption M ≥ 5.5
- #35 comex_stress min_samples=180

11 endringer DEFERRED:
- #30, #31, #32, #34, #42 (YAML-rebalanseringer per § 22.1 live-demo-validering)
- #36-#41 (substantial driver-impl-rewrites for senere session)
