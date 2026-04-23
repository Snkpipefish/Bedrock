"""Fetch-laget for Bedrock.

Rå I/O mot eksterne datakilder (Stooq, CFTC, FRED, værtjenester, etc.).
Ingen scoring eller forretningslogikk her — kun henting + normalisering
til DataFrame/Series-format som matcher `bedrock.data.schemas`.

Fase 3 session 10: kun `prices` (Stooq CSV) som demo for backfill-CLI.
Fase 5 introduserer full modul-struktur + config-drevet cadence
(se PLAN § 7).
"""
