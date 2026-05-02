# Sub-fase 12.10 Bunke 3 — Snapshot-diff-rapport

**Dato:** 2026-05-02
**Sammenligning:** baseline post-Bunke 2 vs post-Bunke 3

## Sammendrag

- **Total entries:** 104
- **Score-endringer (≥1e-6):** 0
- **Grade-flips:** 0

## Per asset-class

| Asset-class | Score-endringer | Grade-flips |
|---|---|---|
| crypto | 0 | 0 |
| energy | 0 | 0 |
| fx | 0 | 0 |
| grains | 0 | 0 |
| indices | 0 | 0 |
| metals | 0 | 0 |
| softs | 0 | 0 |

## Tolkning

Bunke 3 leverer 14 nye drivere som er **registrert men IKKE YAML-wired**. Score-endringer i denne diff-en er drift fra annen data-akkumulering siden Bunke 2-baseline (FRED-backfill 26 537 nye rader, ICE COT softs 2420 rader).

## Bunke 3-leveranser

### Drivere implementert (14 av 15 i spec):
- #7 yields: t10y3m, t_bill_3mo_yield
- #8 credit: hy_oas_change
- #9 labor: initial_claims_z, continuing_claims_z
- #10 growth: industrial_production_yoy, cfnai_3mma, umich_sentiment_z, jolts_openings_yoy
- #11 liquidity: anfci_z, m2_yoy
- #12 vol: vix9d_vix_ratio
- #13 fx: dollar_index_breadth
- #14 calendar: fomc_decision_distance

### DEFERRED:
- #10 ism_pmi_level: FRED NAPMPMI-serien returnerer 404 (deprecated/restricted). Krever alternativ ISM-data-kilde — flagget i PLAN/STATE.

### Backfill:
- 19 nye FRED-serier × 26 537 rader (DGS3MO/TB3MS/BAMLH0A0HYM2/ICSA/CCSA/INDPRO/CFNAI/UMCSENT/JTSJOL/ANFCI/M2SL/8 DEX-pairs)

### YAML-wirings: ikke wired i denne bunken.
Per § 22.1: validering mot live-demo. Wirings tas i follow-up-session basert på empirisk demo-resultat.
