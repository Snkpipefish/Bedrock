"""Setup-generator for Bedrock.

Fase 4 (PLAN § 5) i trinn:

- `levels.py` (session 16): nivå-detektor — swing highs/lows, prior
  weekly/daily/monthly H/L, round numbers. Råliste, ingen clustering.
- `generator.py` (session 17+): setup-bygger — tar nivå-liste + nåpris
  + direction + horisont → entry/SL/TP. Nivå-clustering (merge av
  overlappende swing + round number) lever her.
- (senere sessions): ATR-bånd, asymmetri-gate, hysterese + determinisme,
  horisont-klassifisering.

Kritisk prinsipp: generatoren er *deterministisk* — samme input gir
samme output. Konsistens mellom kjøringer kommer fra hysterese på
snapshot, ikke fra persistent lifecycle-state.
"""
