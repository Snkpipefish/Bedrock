"""Fetch-laget for Bedrock.

Rå I/O mot eksterne datakilder (Yahoo Finance, CFTC, FRED, værtjenester,
NOAA ENSO, USDA-kalender). Ingen scoring eller forretningslogikk her —
kun henting + normalisering til DataFrame/Series-format som matcher
`bedrock.data.schemas`.

Fase 3 session 10: første demo-fetcher for backfill-CLI.
Fase 6 (session 27+) la til config-drevet cadence (se PLAN § 7).
Fase 10 session 58: Yahoo-port erstattet Stooq som pris-kilde.
Fase 12 session 69: Stooq fjernet helt; `prices.py` er nå tynn fasade
rundt `yahoo.py`.
"""

# Side-effekt-import: registrerer `usda_blackout`-gate i gates-registry
# slik at den er tilgjengelig via get_gate() uten eksplisitt import fra
# caller. Ligger nederst for å unngå sirkulær-import.
# ruff: noqa: F401
from bedrock.fetch import usda_calendar
