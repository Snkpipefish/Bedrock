# Grade-distribusjons-rapport — sub-fase 12.6 post-rebalansering

Sammenligner score-baseline mot **samme DB-tilstand** før og etter
session 138 YAML-rebalansering. Begge baselines genereres av
`scripts/snapshot/score_baseline.py` mot identisk `data/bedrock.db`.
Endringer skyldes utelukkende rebalansering — drift fra data eller
kode er kontrollert ut.

## Sammendrag

- Pre-rebalansering rader:    104
- Post-rebalansering rader:   104
- Uendret (score + grade):    80
- Endret:                     24
- Grade-flip:                 2

## Endringer per instrument

| Instrument | Rader endret |
|---|---:|
| AUDUSD | 6 |
| Copper | 6 |
| Nasdaq | 6 |
| SP500 | 6 |

## Detaljerte endringer

| Instrument | Hor | Dir | Pre score | Post score | ΔScore | Pre grade | Post grade | Grade-flip? |
|---|---|---|---:|---:|---:|---|---|:---:|
| AUDUSD | MAKRO | buy | 4.1617 | 4.1429 | -0.0187 | A | A |  |
| AUDUSD | MAKRO | sell | 1.1657 | 1.1845 | +0.0187 | C | C |  |
| AUDUSD | SCALP | buy | 3.7881 | 3.7756 | -0.0125 | A+ | A+ |  |
| AUDUSD | SCALP | sell | 0.9543 | 0.9668 | +0.0125 | C | C |  |
| AUDUSD | SWING | buy | 4.2897 | 4.2747 | -0.0150 | A | A |  |
| AUDUSD | SWING | sell | 1.1602 | 1.1752 | +0.0150 | C | C |  |
| Copper | MAKRO | buy | 2.6480 | 2.6155 | -0.0325 | B | B |  |
| Copper | MAKRO | sell | 1.8659 | 1.8984 | +0.0325 | C | C |  |
| Copper | SCALP | buy | 2.4335 | 2.4160 | -0.0175 | B | B |  |
| Copper | SCALP | sell | 1.8804 | 1.8979 | +0.0175 | B | B |  |
| Copper | SWING | buy | 2.7409 | 2.7159 | -0.0250 | B | B |  |
| Copper | SWING | sell | 2.0265 | 2.0515 | +0.0250 | C | B | ★ |
| Nasdaq | MAKRO | buy | 2.3434 | 2.2528 | -0.0906 | B | B |  |
| Nasdaq | MAKRO | sell | 2.5743 | 2.4837 | -0.0906 | B | B |  |
| Nasdaq | SCALP | buy | 2.9908 | 2.9003 | -0.0906 | A | A |  |
| Nasdaq | SCALP | sell | 1.8268 | 1.7363 | -0.0906 | B | B |  |
| Nasdaq | SWING | buy | 2.8667 | 2.7535 | -0.1132 | B | B |  |
| Nasdaq | SWING | sell | 2.4054 | 2.2922 | -0.1132 | B | B |  |
| SP500 | MAKRO | buy | 2.7719 | 2.6635 | -0.1084 | B | B |  |
| SP500 | MAKRO | sell | 2.0310 | 1.9226 | -0.1084 | C | C |  |
| SP500 | SCALP | buy | 3.3551 | 3.2467 | -0.1084 | A | A |  |
| SP500 | SCALP | sell | 1.3478 | 1.2394 | -0.1084 | C | C |  |
| SP500 | SWING | buy | 3.2937 | 3.1582 | -0.1355 | A | B | ★ |
| SP500 | SWING | sell | 1.8349 | 1.6994 | -0.1355 | C | C |  |

## Tolking

- **Grade-flips fra rebalansering** er den primære cutover-validering: bare instrumenter som faktisk endrer publish-status er praktisk berørt.
- **Score-deltas uten grade-flip** er ren tone-justering — driver-vekt-shift gir lavere/høyere score men under/over samme grade-terskel.
- **Instrumenter ikke i tabellen** har bit-identisk score+grade pre→post — driver-output for de aktive driverne i de berørte familiene var like under begge vekt-sett (typisk: alle drivere returnerer 0.5 default).
