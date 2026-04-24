"""Fetch-laget for Bedrock.

Rå I/O mot eksterne datakilder (Stooq, CFTC, FRED, værtjenester, etc.).
Ingen scoring eller forretningslogikk her — kun henting + normalisering
til DataFrame/Series-format som matcher `bedrock.data.schemas`.

Fase 3 session 10: kun `prices` (Stooq CSV) som demo for backfill-CLI.
Fase 6 (session 27+) utvider med kalender-datakilder og config-drevet
cadence (se PLAN § 7).
"""

# Side-effekt-import: registrerer `usda_blackout`-gate i gates-registry
# slik at den er tilgjengelig via get_gate() uten eksplisitt import fra
# caller. Ligger nederst for å unngå sirkulær-import.
# ruff: noqa: E402, F401
from bedrock.fetch import usda_calendar  # noqa: E402
