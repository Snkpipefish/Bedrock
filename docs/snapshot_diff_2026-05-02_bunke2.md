# Sub-fase 12.10 Bunke 2 — Snapshot-diff-rapport

**Dato:** 2026-05-02
**Sammenligning:** baseline post-Bunke 1 (tag v0.12.10-bunke1) vs post-Bunke 2

## Sammendrag

- **Total entries:** 104
- **Score-endringer (≥1e-6):** 32
- **Grade-flips:** 5

## Per asset-class

| Asset-class | Score-endringer | Grade-flips | Stop-criterion (≤5) |
|---|---|---|---|
| crypto | 0 | 0 | ✓ |
| energy | 0 | 0 | ✓ |
| fx | 0 | 0 | ✓ |
| grains | 2 | 0 | ✓ |
| indices | 0 | 0 | ✓ |
| metals | 24 | 4 | ✓ |
| softs | 6 | 1 | ✓ |

## Grade-flips i detalj

- **Gold|MAKRO|buy** (metals): B → C (Δscore=-0.509)
- **Gold|MAKRO|sell** (metals): B → A (Δscore=+0.659)
- **Gold|SWING|sell** (metals): B → A (Δscore=+0.439)
- **Silver|MAKRO|buy** (metals): A → B (Δscore=-0.479)
- **Coffee|NONE|sell** (softs): A+ → A (Δscore=-0.077)

## Bunke 2-leveranser

### #4 cot_ice_mm_pct wired på 4 softs (4 commits + 1 fetcher-utvidelse)
- Cocoa cross-familie: dxy 0.85→0.65, event 0.15→0.10, **cot_ice_mm_pct@0.25**
- Coffee cross-familie: brl 0.9→0.65, event 0.10, **cot_ice_mm_pct@0.25**
- Sugar cross-familie: brl 0.9→0.65, event 0.10, **cot_ice_mm_pct@0.25**
- Wheat cross-familie: dxy 0.40→0.30, shipping 0.15→0.10, event/eu/fas uendret, **cot_ice_mm_pct@0.15**
- ICE_MARKETS-fetcher utvidet med white sugar / robusta coffee / cocoa / wheat
- Backfill: 2420 nye ICE COT-rader (605 per softs-contract, 2014→2026)

### #5 *_surprise (DEFERRED)
- Forex Factory  har ikke -felt
- FRED PAYEMS/CPIAUCSL/GDP/PCEPI ikke i DB
- Krever cross-source join eller alternativ feed — egen senere session

### #6 news_intel_severity_veto (registrert)
- Driver registrert + 11 tester. Ikke wired i YAMLer fordi disruption_score er NULL p.t.
- Aktiveres når sentiment-scoring av news_intel-artikler er på plass

## Tolkning

Bunke 2 #4 endrer cross-familien for 4 softs-instrumenter. Cocoa/Coffee/Sugar/Wheat får ICE Europe MM-positioning som overlay til CFTC-positioning og BRL/DXY-cross.

Bunke 2 #6 (news_intel_severity_veto) er ikke wired og påvirker ikke baseline.

**Stop-criterion oppfylt:** alle asset-class har ≤5 grade-flips.
