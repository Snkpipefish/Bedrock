# Sub-fase 12.10 Bunke 1 — Snapshot-diff-rapport

**Dato:** 2026-05-02
**Sammenligning:** baseline pre-Bunke 1 (siste pre-12.10-tag) vs post-Bunke 1 (commits 1068de7…cc860b4)

## Sammendrag

- **Total entries:** 104
- **Score-endringer (≥1e-6):** 80
- **Grade-flips:** 2

## Per asset-class

| Asset-class | Score-endringer | Grade-flips | Stop-criterion (≤5) |
|---|---|---|---|
| crypto | 12 | 0 | ✓ |
| energy | 6 | 0 | ✓ |
| fx | 24 | 1 | ✓ |
| grains | 0 | 0 | ✓ |
| indices | 12 | 0 | ✓ |
| metals | 24 | 1 | ✓ |
| softs | 2 | 0 | ✓ |

## Grade-flips i detalj

- **EURUSD|MAKRO|buy** (fx): C → B (Δscore=+0.037)
- **Copper|SWING|sell** (metals): C → B (Δscore=+0.169)

## Tolkning

Bug-1 påvirker AsOfDateStore (backtest-only) og endrer ikke denne baselinen, som bruker DataStore direkte (live-mode).

Bug-2 min_samples-guards påvirker direkte:
- Sugar unica-familie: unica_change 0.41 → 0.5 (n=1 < min_samples=12)
- Silver/Gold/Copper macro-familie: comex_stress påvirket (n=5 < min_samples=20)
- Wheat cross-/yield-familier: disease_pressure + export_event_active påvirket

Bug-3 er audit-only og endrer ikke score.

Resterende score-endringer er drift fra annen data-akkumulering siden forrige baseline.

**Stop-criterion oppfylt:** alle asset-class har ≤5 grade-flips. Ingen eskalering nødvendig.
