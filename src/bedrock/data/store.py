"""DataStore — datalag-API for drivere og setup-generator.

Fase 2 session 6: SQLite-backet implementasjon som erstatter Fase 1-stub-en
(InMemoryStore). Se ADR-002 for hvorfor SQLite og ikke DuckDB+parquet.

API-kontrakten (`DataStoreProtocol.get_prices`) er uendret fra Fase 1; alle
drivere skrevet mot den fortsetter å funke uendret.

Backend-detaljer:

- Én SQLite-fil på disk (`db_path`). Billig, null-tjeneste, transaksjonell.
- `prices`-tabellen (se `schemas.DDL_PRICES`) har PK (instrument, tf, ts) slik
  at repeated `append_prices` dedupliserer automatisk via INSERT OR REPLACE.
- Pandas-native lesing via `pd.read_sql`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import pandas as pd

from bedrock.data.schemas import DDL_PRICES, TABLE_PRICES


class DataStoreProtocol(Protocol):
    """Kontrakten alle drivere skriver mot. Fase 2s `DataStore` implementerer
    denne. Fase 1s `InMemoryStore` gjorde det samme (slettet i session 6).
    Drivere skal aldri type-hinte mot den konkrete klassen; kun mot protokollen.
    """

    def get_prices(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.Series: ...


class DataStore:
    """SQLite-backet DataStore.

    Bruk:

        store = DataStore(Path("data/bedrock.db"))
        store.append_prices("Gold", "D1", df)
        close = store.get_prices("Gold", "D1", lookback=250)
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Ny connection per kall. SQLite-connections er ikke thread-safe,
        og bedrock-pipelinen kjører enkelttråd i hovedsak — null connection-
        pooling er akseptabelt kost."""
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(DDL_PRICES)
            conn.commit()

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    def append_prices(
        self,
        instrument: str,
        tf: str,
        df: pd.DataFrame,
    ) -> int:
        """Skriv pris-barer til `prices`-tabellen. Returnerer antall rader
        skrevet (etter dedupe).

        `df` må ha kolonner `ts` og `close`. `open`/`high`/`low`/`volume`
        er valgfrie (fylles med NULL hvis de mangler).

        Duplicate (instrument, tf, ts) overskrives takket være INSERT OR
        REPLACE + PK — idempotent re-run av backfill er trygt.
        """
        if "ts" not in df.columns or "close" not in df.columns:
            raise ValueError(
                f"append_prices: df must have columns 'ts' and 'close'. "
                f"Got: {sorted(df.columns)}"
            )

        required_cols = ["ts", "open", "high", "low", "close", "volume"]
        prepared = df.reindex(columns=required_cols).copy()
        # Normaliser ts til ISO-streng for SQLite TEXT-kolonne.
        prepared["ts"] = pd.to_datetime(prepared["ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S")

        rows: Sequence[tuple] = [
            (
                instrument,
                tf,
                row.ts,
                None if pd.isna(row.open) else float(row.open),
                None if pd.isna(row.high) else float(row.high),
                None if pd.isna(row.low) else float(row.low),
                float(row.close),
                None if pd.isna(row.volume) else float(row.volume),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {TABLE_PRICES}
                    (instrument, tf, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()

        return len(rows)

    def get_prices(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.Series:
        """Returner close-pris-serie for `(instrument, tf)`, indeksert på ts
        (ascending). `lookback` = N gir siste N bars (eller hele serien hvis
        N > rad-antall).

        Kaster `KeyError` hvis `(instrument, tf)` ikke finnes. Drivere må
        håndtere det — per driver-kontrakt skal de returnere 0.0 og logge.
        """
        query = f"""
            SELECT ts, close FROM {TABLE_PRICES}
            WHERE instrument = ? AND tf = ?
            ORDER BY ts ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(instrument, tf))

        if df.empty:
            raise KeyError(f"No prices for instrument={instrument!r} tf={tf!r}")

        df["ts"] = pd.to_datetime(df["ts"])
        series = df.set_index("ts")["close"].astype("float64")
        series.name = None  # drivere forventer "nakent" Series-navn

        if lookback is None:
            return series
        return series.tail(lookback)

    def has_prices(self, instrument: str, tf: str) -> bool:
        """Test-hjelper: sjekk om (instrument, tf) har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_PRICES} WHERE instrument = ? AND tf = ? LIMIT 1",
                (instrument, tf),
            )
            return cursor.fetchone() is not None
