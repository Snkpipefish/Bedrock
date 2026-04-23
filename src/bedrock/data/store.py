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
from typing import Literal, Protocol

import pandas as pd

from bedrock.data.schemas import (
    COT_DISAGGREGATED_COLS,
    COT_LEGACY_COLS,
    DDL_COT_DISAGGREGATED,
    DDL_COT_LEGACY,
    DDL_FUNDAMENTALS,
    DDL_PRICES,
    DDL_WEATHER,
    FUNDAMENTALS_COLS,
    TABLE_COT_DISAGGREGATED,
    TABLE_COT_LEGACY,
    TABLE_FUNDAMENTALS,
    TABLE_PRICES,
    TABLE_WEATHER,
    WEATHER_COLS,
)

CotReport = Literal["disaggregated", "legacy"]


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
            conn.execute(DDL_COT_DISAGGREGATED)
            conn.execute(DDL_COT_LEGACY)
            conn.execute(DDL_FUNDAMENTALS)
            conn.execute(DDL_WEATHER)
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

    # ------------------------------------------------------------------
    # COT (Commitments of Traders) — CFTC
    # ------------------------------------------------------------------

    def append_cot_disaggregated(self, df: pd.DataFrame) -> int:
        """Skriv rader til `cot_disaggregated`. Returnerer antall rader.

        `df` må ha alle kolonner i `COT_DISAGGREGATED_COLS`. Duplicates på
        (report_date, contract) overskrives via INSERT OR REPLACE (PK).
        """
        return self._append_cot(df, TABLE_COT_DISAGGREGATED, COT_DISAGGREGATED_COLS)

    def append_cot_legacy(self, df: pd.DataFrame) -> int:
        """Skriv rader til `cot_legacy`. Returnerer antall rader."""
        return self._append_cot(df, TABLE_COT_LEGACY, COT_LEGACY_COLS)

    def _append_cot(
        self,
        df: pd.DataFrame,
        table: str,
        expected_cols: tuple[str, ...],
    ) -> int:
        missing = [c for c in expected_cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_cot: {table} missing columns {missing}. "
                f"Required: {list(expected_cols)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(expected_cols)].copy()
        # Normaliser report_date til ISO YYYY-MM-DD string.
        prepared["report_date"] = pd.to_datetime(prepared["report_date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [tuple(row) for row in prepared.itertuples(index=False)]
        placeholders = ", ".join("?" * len(expected_cols))
        cols_sql = ", ".join(expected_cols)

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_cot(
        self,
        contract: str,
        report: CotReport = "disaggregated",
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner COT-rader for `contract`, sortert på report_date ASC.

        `report="disaggregated"` (default) eller `"legacy"`.
        `last_n` = N gir de N nyeste rapportene (eller hele historikken).

        Returnerer pd.DataFrame med `report_date` som pd.Timestamp i en
        kolonne (ikke index) — rapporter er diskrete ukentlige events, ikke
        en kontinuerlig tidsserie, så indeksering på dato ville gitt lite
        merverdi og forvirret drivere som forventer rå kolonner.

        Kaster `KeyError` hvis ingen rader finnes for (contract, report).
        """
        if report == "disaggregated":
            table = TABLE_COT_DISAGGREGATED
        elif report == "legacy":
            table = TABLE_COT_LEGACY
        else:
            raise ValueError(f"Unknown COT report type: {report!r}")

        query = f"""
            SELECT * FROM {table}
            WHERE contract = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(contract,))

        if df.empty:
            raise KeyError(f"No COT data for contract={contract!r} report={report!r}")

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_cot(self, contract: str, report: CotReport = "disaggregated") -> bool:
        """Test-hjelper: sjekk om (contract, report) har minst én rad."""
        table = TABLE_COT_DISAGGREGATED if report == "disaggregated" else TABLE_COT_LEGACY
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {table} WHERE contract = ? LIMIT 1",
                (contract,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Fundamentals (FRED-stil tidsserier)
    # ------------------------------------------------------------------

    def append_fundamentals(self, df: pd.DataFrame) -> int:
        """Skriv FRED-observasjoner. `df` må ha kolonner series_id, date, value.

        `value` kan være None (FRED rapporterer ofte missing). Dedupe på
        (series_id, date) via INSERT OR REPLACE.
        """
        missing = [c for c in FUNDAMENTALS_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_fundamentals: missing columns {missing}. "
                f"Required: {list(FUNDAMENTALS_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(FUNDAMENTALS_COLS)].copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                row.series_id,
                row.date,
                None if pd.isna(row.value) else float(row.value),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_FUNDAMENTALS} "
                f"(series_id, date, value) VALUES (?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_fundamentals(
        self,
        series_id: str,
        last_n: int | None = None,
    ) -> pd.Series:
        """Returner pd.Series (value indeksert på date) for en FRED-serie.

        Kaster `KeyError` hvis `series_id` ikke finnes. NULL-verdier fra
        FRED kommer ut som NaN i Series (pandas-native).
        """
        query = f"""
            SELECT date, value FROM {TABLE_FUNDAMENTALS}
            WHERE series_id = ?
            ORDER BY date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(series_id,))

        if df.empty:
            raise KeyError(f"No fundamentals for series_id={series_id!r}")

        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["value"].astype("float64")
        series.name = None

        if last_n is None:
            return series
        return series.tail(last_n)

    def has_fundamentals(self, series_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_FUNDAMENTALS} WHERE series_id = ? LIMIT 1",
                (series_id,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Weather (daglige region-observasjoner)
    # ------------------------------------------------------------------

    def append_weather(self, df: pd.DataFrame) -> int:
        """Skriv daglige vær-observasjoner. `df` må ha region, date; tmax,
        tmin, precip, gdd er valgfrie."""
        if "region" not in df.columns or "date" not in df.columns:
            raise ValueError(
                f"append_weather: df must have 'region' and 'date'. "
                f"Got: {sorted(df.columns)}"
            )

        prepared = df.reindex(columns=list(WEATHER_COLS)).copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                row.region,
                row.date,
                None if pd.isna(row.tmax) else float(row.tmax),
                None if pd.isna(row.tmin) else float(row.tmin),
                None if pd.isna(row.precip) else float(row.precip),
                None if pd.isna(row.gdd) else float(row.gdd),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_WEATHER} "
                f"(region, date, tmax, tmin, precip, gdd) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_weather(
        self,
        region: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner vær-observasjoner for region (sortert på date ASC).

        Returnerer pd.DataFrame med `date`-kolonne som pd.Timestamp.
        Multi-column (tmax/tmin/precip/gdd); drivere velger selv hvilken
        kolonne de trenger. Kaster `KeyError` hvis region mangler.
        """
        query = f"""
            SELECT date, tmax, tmin, precip, gdd FROM {TABLE_WEATHER}
            WHERE region = ?
            ORDER BY date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(region,))

        if df.empty:
            raise KeyError(f"No weather for region={region!r}")

        df["date"] = pd.to_datetime(df["date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_weather(self, region: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_WEATHER} WHERE region = ? LIMIT 1",
                (region,),
            )
            return cursor.fetchone() is not None
