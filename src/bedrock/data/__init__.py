"""Datalag for Bedrock.

Denne modulen vokser seg full i Fase 2 (DuckDB + parquet + backfill).
I Fase 1 er kun en minimal in-memory `DataStore` (se `store.py`) tilgjengelig
så drivere kan utvikles mot en stabil API-kontrakt uten å vente på hele
DuckDB-laget.

API-et `get_prices(instrument, tf, lookback)` som defineres her holdes likt
når den ekte DataStore kommer — drivere skal ikke trenge endringer.
"""
