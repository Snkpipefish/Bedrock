"""DataStore — datalag-API for drivere og setup-generator.

Fase 1-utgave: kun en in-memory `InMemoryStore` for testing av drivere uten
DuckDB-avhengighet. Fase 2 introduserer den *ekte* `DataStore` som leser
parquet via DuckDB; den vil implementere samme `get_prices`-signatur slik
at drivere ikke må endres.

API-kontrakt (stabil på tvers av faser):

    store.get_prices(instrument: str, tf: str = "D1", lookback: int | None = None) -> pd.Series

- Returnerer en `pd.Series` av close-priser indeksert på ts (tidsstempel).
- `lookback` = max antall siste bars å returnere. `None` = alle.
- Ukjent (instrument, tf) kaster `KeyError`.
- Fase 2 utvider med `get_prices(..., from_="2016-01-01")` og ny metode
  `get_cot(...)`, `get_weather(...)` etc. Disse ligger på den samme
  Protocol-klassen.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class DataStoreProtocol(Protocol):
    """Kontrakten alle drivere skriver mot. Formaliserer `StoreProtocol`
    som tidligere lå i `bedrock.engine.drivers`."""

    def get_prices(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.Series: ...


class InMemoryStore:
    """Minimal in-memory store for tester og driver-utvikling i Fase 1.

    Lagrer pris-serier per `(instrument, tf)`-nøkkel. Produksjon vil bruke
    DuckDB/parquet via `bedrock.data.store.DataStore` (Fase 2).
    """

    def __init__(self) -> None:
        self._prices: dict[tuple[str, str], pd.Series] = {}

    def add_prices(
        self,
        instrument: str,
        tf: str,
        prices: pd.Series | list[float],
    ) -> None:
        """Legg inn (eller overskriv) pris-serie for `(instrument, tf)`."""
        if isinstance(prices, list):
            prices = pd.Series(prices, dtype="float64")
        self._prices[(instrument, tf)] = prices

    def get_prices(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.Series:
        """Returner pris-serie. `lookback`=N gir siste N bars.

        Kaster `KeyError` hvis `(instrument, tf)` ikke finnes. Drivere må
        håndtere dette — per driver-kontrakt skal feil resultere i 0.0 +
        logg, ikke propagere unntak.
        """
        key = (instrument, tf)
        try:
            series = self._prices[key]
        except KeyError:
            raise KeyError(f"No prices for instrument={instrument!r} tf={tf!r}") from None
        if lookback is None:
            return series
        return series.tail(lookback)

    def has_prices(self, instrument: str, tf: str) -> bool:
        """Test-hjelper: sjekk om (instrument, tf) er lagt inn."""
        return (instrument, tf) in self._prices
