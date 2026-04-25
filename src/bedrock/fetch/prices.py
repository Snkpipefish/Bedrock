"""Pris-fetcher (Yahoo Finance).

Session 69 (Fase 12): byttet fra Stooq til Yahoo som eneste pris-kilde.
Stooq begynte å kreve API-nøkkel (session 58); Yahoo-port var allerede
gjort, men dispatcheren (``bedrock fetch run prices``) brukte fortsatt
Stooq. Dette resulterte i at parallell-drift-aktivering (session 67)
viste prises-fetcher som FAIL.

Modulen er nå en tynn fasade rundt ``bedrock.fetch.yahoo`` slik at
eksisterende callers (``cli/backfill.py``, ``config/fetch_runner.py``)
fortsatt kan ``from bedrock.fetch.prices import fetch_prices,
PriceFetchError`` uten endring.

Public API:

- ``fetch_prices(ticker, from_date, to_date, interval)`` — alias for
  ``fetch_yahoo_prices``. ``ticker`` er en Yahoo-formatted ticker
  (f.eks. "GC=F" for Gold, "ZC=F" for Corn). Caller leser typisk
  ``meta.yahoo_ticker`` fra instrument-config.
- ``PriceFetchError`` — alias for ``YahooFetchError``. Beholder samme
  exception-navn for caller-stabilitet.

Yahoo-spesifikk implementasjon (URL-bygging, JSON-parsing) ligger i
``bedrock.fetch.yahoo``.
"""

from __future__ import annotations

from bedrock.fetch.yahoo import (
    YahooFetchError as PriceFetchError,
)
from bedrock.fetch.yahoo import (
    fetch_yahoo_prices as fetch_prices,
)

__all__ = ["PriceFetchError", "fetch_prices"]
