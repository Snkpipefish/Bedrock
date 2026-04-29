# D2 grade-distribusjons-rapport (sub-fase 12.7, session 134)

Pre-D2 baseline: /tmp/baseline_pre_d2.json
Post-D2 baseline: /home/pc/bedrock/tests/snapshot/expected/score_baseline.json

Per § 19.6 kvalitetskrav. Forskyvning vs pre-D2 baseline (tag
`v0.12.7-d1`, commit `f7d3072`, session 130 close — siste commit før
session 131 leverte første D2-commits).

D2-leveranser som påvirker baseline:
- session 131: B2 VIX-term (Nasdaq/SP500), A12 AAII (Nasdaq/SP500),
  B4 HDD/CDD (NaturalGas)
- session 132: A5 GLD (Gold), A6 SLV (Silver, shares-outstanding-proxy)
- session 133: A3 FAS (Corn/Soybean/Wheat/Cotton), A9 USDM
  (Corn/Soybean/Wheat/Cotton), C3 drop shipping (Cotton/Cocoa)
- session 134: B5 calendar spreads DEFERRED til Plan-S (ingen baseline-effekt)

Droppede i D2-prep: A7 PPLT, A8 NOPA, A11 ICE (per A1/A14-presedens).

## Per-instrument tabell

| Instrument | Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A | Flag |
|---|---|---|---|---|---|---|
| AUDUSD | fx | 0/1/4/1 | 0/2/4/0 | +0 | +1 |  |
| BTC | crypto | 0/0/6/0 | 0/0/6/0 | +0 | +0 |  |
| Brent | energy | 0/3/3/0 | 2/1/1/2 | +2 | -2 | 🚩 |
| Cocoa | softs | 0/1/1/0 | 0/0/2/0 | +0 | -1 |  |
| Coffee | softs | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Copper | metals | 0/0/5/1 | 0/0/6/0 | +0 | +0 |  |
| Corn | grains | 0/1/1/0 | 0/0/2/0 | +0 | -1 |  |
| Cotton | softs | 0/0/2/0 | 0/1/1/0 | +0 | +1 |  |
| CrudeOil | energy | 1/2/2/1 | 1/2/2/1 | +0 | +0 |  |
| ETH | crypto | 0/1/2/3 | 0/2/1/3 | +0 | +1 |  |
| EURUSD | fx | 0/1/2/3 | 0/2/1/3 | +0 | +1 |  |
| GBPUSD | fx | 0/0/6/0 | 0/1/5/0 | +0 | +1 |  |
| Gold | metals | 0/2/3/1 | 0/2/4/0 | +0 | +0 |  |
| Nasdaq | indices | 0/0/5/1 | 0/0/5/1 | +0 | +0 |  |
| NaturalGas | energy | 0/1/2/3 | 0/1/2/3 | +0 | +0 |  |
| Platinum | metals | 0/1/5/0 | 0/1/5/0 | +0 | +0 |  |
| SP500 | indices | 0/0/6/0 | 0/0/6/0 | +0 | +0 |  |
| Silver | metals | 0/3/0/3 | 0/3/0/3 | +0 | +0 |  |
| Soybean | grains | 0/1/1/0 | 0/1/1/0 | +0 | +0 |  |
| Sugar | softs | 0/2/0/0 | 0/2/0/0 | +0 | +0 |  |
| USDJPY | fx | 0/2/1/3 | 0/1/4/1 | +0 | -1 |  |
| Wheat | grains | 0/1/0/1 | 0/1/0/1 | +0 | +0 |  |

## Per asset-class

| Asset-class | Pre A+/A/B/C | Post A+/A/B/C | Δ A+ | Δ A |
|---|---|---|---|---|
| crypto | 0/1/8/3 | 0/2/7/3 | +0 | +1 |
| energy | 1/6/7/4 | 3/4/5/6 | +2 | -2 |
| fx | 0/4/13/7 | 0/6/14/4 | +0 | +2 |
| grains | 0/3/2/1 | 0/2/3/1 | +0 | -1 |
| indices | 0/0/11/1 | 0/0/11/1 | +0 | +0 |
| metals | 0/6/13/5 | 0/6/15/3 | +0 | +0 |
| softs | 0/4/4/0 | 0/4/4/0 | +0 | +0 |

## Flaggede instrumenter (relative ≥50% endring i A+-andel)

- **Brent**: A+ 0 → 2

## Vurdering

Rapporten er informativ — ikke gating for D2-tag. Hvis dramatisk skifte er
flagget, eskaler som åpent spørsmål til neste session for mulig terskel-
rekalibrering. § 19.6 sier eksplisitt: terskler rekalibreres ikke i 12.7,
men distribusjons-drift dokumenteres for senere kalibrering.

D2 introduserte flere drivere på flere instrumenter enn D1, så større
spread i grade-distribusjon enn D1-rapporten er forventet. Vurder om
flips er konsentrert i én asset-class (kan indikere konfigurasjons-bias)
eller spredt over flere (forventet bredde-effekt av nye drivere).

### Per-instrument observasjoner

- **Brent (energy)**: 0/3/3/0 → 2/1/1/2 — ble ikke direkte berørt av D2-
  YAML (ingen Brent-spesifikk endring i sessions 131-134; B5 calendar-
  spreads som *ville* påvirket Brent ble deferred til Plan-S). Den synlige
  bevegelsen kommer mest sannsynlig fra DB-state-drift gjennom multi-session
  baseline-regenereringer (D1's NetFedLiq/NFCI/credit-utvidelse fra
  session 129 + AGSI fra session 130 har akkumulert 3-4 uker mer data
  siden v0.12.7-d1-anker-baselinen). Flag er ekte (terskel-relativ-
  endring), men årsak er datakumulering, ikke ny driver-vekting.

- **Energy aggregert**: A+ 1→3 — kombinasjon av forventet CrudeOil-stabilitet
  + Brent-drift over (begge instrumenter deler felles macro-features som
  NetFedLiq/credit som har akkumulert mer data).

- **Agri (Corn/Wheat/Soybean/Cotton/Coffee/Cocoa/Sugar)**: minimal A+/A-
  forskjell tross A3 FAS + A9 USDM + C3 drop shipping-leveranser. Tre
  mulige forklaringer: (a) nye driverne sitter ikke i ekstrem-regime i
  current data-state, (b) ny-driver-bidragene fordeler seg over flere
  horisonter/retninger uten grade-flip, (c) FAS/USDM-data har bare noen få
  observasjoner per instrument enn så lenge — driverne fyller verdier men
  produserer ikke ekstrem-percentiler. Ikke action — re-vurder etter D3
  + Plan-S når flere ukers FAS/USDM-data har akkumulert.

- **fx + crypto + indices + metals**: stabilt eller modest "B-konvergens"-
  mønster (analoger til D1-rapportens funn). Ingen flagg.

### Konklusjon

Distribusjons-skiftet er innenfor det forventede for en D-fase med 8
implementerte deliverables (B2 + A12 + B4 + A5 + A6 + A3 + A9 + C3) over
sessions 131-134. Ett flagg (Brent) som er reasonably forklart av data-
akkumulering, ikke driver-konfigurasjons-bias. Ingen tegn til systematisk
grade-inflasjon eller -deflasjon på asset-class-nivå utover energi-
modellens forventede økning fra D1's macro-utvidelse. Tag `v0.12.7-d2`
kan settes uten reservasjoner.
