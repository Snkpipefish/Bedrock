"""Config-lasting for Bedrock.

Delt opp i to ansvar:

- `secrets.py`: hemmeligheter (API-nøkler, koder) — lastes fra
  `~/.bedrock/secrets.env` eller env-vars. Aldri committet.
- Senere faser: YAML-lasting for instrument-regler (Fase 5), bot-thresholds
  (Fase 7), pipeline-timing (Fase 5).

`pydantic-settings` kan vurderes senere for typed config-objekter; for nå
bruker vi python-dotenv til rå nøkkel/verdi-lesing.
"""
