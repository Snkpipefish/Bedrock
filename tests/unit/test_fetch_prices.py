"""Tester for `bedrock.fetch.prices` — Yahoo Finance-fasaden.

Session 69 (Fase 12): prices.py er nå en tynn fasade rundt
`bedrock.fetch.yahoo`. Tidligere Stooq-baserte tester er fjernet;
Yahoo-spesifikke URL/JSON-tester ligger i
`tests/unit/test_fetch_yahoo.py`.

Disse testene verifiserer kun fasade-kontrakten:
- Public-API-navn (`fetch_prices`, `PriceFetchError`) eksisterer
- De peker på Yahoo-implementasjonen
"""

from __future__ import annotations

from bedrock.fetch import prices, yahoo


def test_fetch_prices_aliases_fetch_yahoo_prices() -> None:
    """``fetch_prices`` er et alias for ``fetch_yahoo_prices``."""
    assert prices.fetch_prices is yahoo.fetch_yahoo_prices


def test_price_fetch_error_aliases_yahoo_fetch_error() -> None:
    """``PriceFetchError`` er et alias for ``YahooFetchError`` slik at
    eksisterende callers (`except PriceFetchError`) fortsatt fungerer."""
    assert prices.PriceFetchError is yahoo.YahooFetchError


def test_public_api_exposes_fetch_prices_and_error() -> None:
    """Modulen eksponerer kun det callers trenger."""
    assert "fetch_prices" in prices.__all__
    assert "PriceFetchError" in prices.__all__
