# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false, reportGeneralTypeIssues=false
# pandas-stubs har dårlig dekning av itertuples() (NamedTuple med dynamiske
# attributter), DatetimeIndex.dt-aksessor, Series-vs-DataFrame-narrowing
# etter set_index, og NDFrame.__bool__-ambiguitet. Disse er konsekvent
# false-positive — koden er korrekt, men typene følger ikke med.

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
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd

from bedrock.data.schemas import (
    ANALOG_OUTCOMES_COLS,
    BDI_COLS,
    COT_DISAGGREGATED_COLS,
    COT_ICE_COLS,
    COT_LEGACY_COLS,
    CROP_PROGRESS_COLS,
    DDL_ANALOG_OUTCOMES,
    DDL_BDI,
    DDL_COT_DISAGGREGATED,
    DDL_COT_ICE,
    DDL_COT_LEGACY,
    DDL_CROP_PROGRESS,
    DDL_DISEASE_ALERTS,
    DDL_ECON_EVENTS,
    DDL_EXPORT_EVENTS,
    DDL_FUNDAMENTALS,
    DDL_IGC,
    DDL_PRICES,
    DDL_WASDE,
    DDL_WEATHER,
    DDL_WEATHER_MONTHLY,
    DISEASE_ALERTS_COLS,
    ECON_EVENTS_COLS,
    EXPORT_EVENTS_COLS,
    FUNDAMENTALS_COLS,
    IGC_COLS,
    TABLE_ANALOG_OUTCOMES,
    TABLE_BDI,
    TABLE_COT_DISAGGREGATED,
    TABLE_COT_ICE,
    TABLE_COT_LEGACY,
    TABLE_CROP_PROGRESS,
    TABLE_DISEASE_ALERTS,
    TABLE_ECON_EVENTS,
    TABLE_EXPORT_EVENTS,
    TABLE_FUNDAMENTALS,
    TABLE_IGC,
    TABLE_PRICES,
    TABLE_WASDE,
    TABLE_WEATHER,
    TABLE_WEATHER_MONTHLY,
    WASDE_COLS,
    WEATHER_COLS,
    WEATHER_MONTHLY_COLS,
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
            conn.execute(DDL_WEATHER_MONTHLY)
            conn.execute(DDL_ANALOG_OUTCOMES)
            # PLAN § 7.3 datakilder (session 83+):
            conn.execute(DDL_CROP_PROGRESS)
            conn.execute(DDL_WASDE)
            conn.execute(DDL_EXPORT_EVENTS)
            conn.execute(DDL_DISEASE_ALERTS)
            conn.execute(DDL_BDI)
            conn.execute(DDL_IGC)
            # Sub-fase 12.5+ session 105 (ADR-007/008):
            conn.execute(DDL_ECON_EVENTS)
            # Sub-fase 12.5+ session 106 (ADR-008): ICE Futures Europe COT.
            conn.execute(DDL_COT_ICE)
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
                f"append_prices: df must have columns 'ts' and 'close'. Got: {sorted(df.columns)}"
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

    def get_prices_ohlc(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.DataFrame:
        """Returner full OHLCV DataFrame for `(instrument, tf)`.

        Indeks: `ts` som `pd.DatetimeIndex`, ascending.
        Kolonner: `open`, `high`, `low`, `close`, `volume` (alle float64;
        NULL fra DB kommer ut som NaN).

        `lookback`=N gir siste N bars. Kaster `KeyError` hvis ukjent.

        Brukes av `bedrock.setups.levels` (Fase 4) som trenger high/low
        for swing-deteksjon og prior H/L. `get_prices` (close-only) er
        fortsatt primær for drivere som ikke bryr seg om OHLCV.
        """
        query = f"""
            SELECT ts, open, high, low, close, volume FROM {TABLE_PRICES}
            WHERE instrument = ? AND tf = ?
            ORDER BY ts ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(instrument, tf))

        if df.empty:
            raise KeyError(f"No prices for instrument={instrument!r} tf={tf!r}")

        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        df = df.astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            }
        )

        if lookback is None:
            return df
        return df.tail(lookback)

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
    # COT — ICE Futures Europe (sub-fase 12.5+ session 106)
    # ------------------------------------------------------------------

    def append_cot_ice(self, df: pd.DataFrame) -> int:
        """Skriv rader til `cot_ice`. Returnerer antall rader.

        Schema er parallelt med `cot_disaggregated` — samme kolonnesett.
        Idempotent på (report_date, contract) via INSERT OR REPLACE.
        """
        return self._append_cot(df, TABLE_COT_ICE, COT_ICE_COLS)

    def get_cot_ice(
        self,
        contract: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner ICE COT-rader for `contract`, sortert ASC på report_date.

        Returnerer pd.DataFrame med `report_date` som pd.Timestamp i en
        kolonne (ikke index), tilsvarende `get_cot()`-konvensjonen.

        Kaster `KeyError` hvis ingen rader finnes for `contract`.
        """
        query = f"""
            SELECT * FROM {TABLE_COT_ICE}
            WHERE contract = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(contract,))

        if df.empty:
            raise KeyError(f"No ICE COT data for contract={contract!r}")

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_cot_ice(self, contract: str) -> bool:
        """Test-hjelper: sjekk om `contract` har minst én ICE COT-rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_COT_ICE} WHERE contract = ? LIMIT 1",
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
                f"append_weather: df must have 'region' and 'date'. Got: {sorted(df.columns)}"
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

    # ------------------------------------------------------------------
    # Weather monthly (pre-aggregert per region per måned, ADR-005)
    # ------------------------------------------------------------------

    def append_weather_monthly(self, df: pd.DataFrame) -> int:
        """Skriv månedlig vær-aggregat. `df` må ha region + month;
        resterende felt valgfri. INSERT OR REPLACE på (region, month).

        `month` må være 'YYYY-MM'-streng (samme format som SQL-kolonnen).
        Caller validerer format via `WeatherMonthlyRow` ved migrering;
        denne metoden trygger på Pydantic-pipelinen.
        """
        if "region" not in df.columns or "month" not in df.columns:
            raise ValueError(
                f"append_weather_monthly: df must have 'region' and 'month'. "
                f"Got: {sorted(df.columns)}"
            )

        prepared = df.reindex(columns=list(WEATHER_MONTHLY_COLS)).copy()

        def _to_int_or_none(v: object) -> int | None:
            if v is None or pd.isna(v):
                return None
            return int(v)

        def _to_float_or_none(v: object) -> float | None:
            if v is None or pd.isna(v):
                return None
            return float(v)

        rows: Sequence[tuple] = [
            (
                row.region,
                row.month,
                _to_float_or_none(row.temp_mean),
                _to_float_or_none(row.temp_max),
                _to_float_or_none(row.precip_mm),
                _to_float_or_none(row.et0_mm),
                _to_int_or_none(row.hot_days),
                _to_int_or_none(row.dry_days),
                _to_int_or_none(row.wet_days),
                _to_float_or_none(row.water_bal),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_WEATHER_MONTHLY} "
                f"(region, month, temp_mean, temp_max, precip_mm, et0_mm, "
                f"hot_days, dry_days, wet_days, water_bal) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_weather_monthly(
        self,
        region: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner månedlig vær-aggregat for region (sortert på month ASC).

        `last_n` = N gir de N nyeste månedene. Kaster `KeyError` hvis
        region ikke har noen rader. `month`-kolonnen returneres som
        ren str ('YYYY-MM'); caller velger selv om den vil parse til
        Period/Timestamp.
        """
        query = f"""
            SELECT region, month, temp_mean, temp_max, precip_mm, et0_mm,
                   hot_days, dry_days, wet_days, water_bal
            FROM {TABLE_WEATHER_MONTHLY}
            WHERE region = ?
            ORDER BY month ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(region,))

        if df.empty:
            raise KeyError(f"No monthly weather for region={region!r}")

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_weather_monthly(self, region: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_WEATHER_MONTHLY} WHERE region = ? LIMIT 1",
                (region,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Analog outcomes (forward returns per ref_date × horizon, ADR-005)
    # ------------------------------------------------------------------

    def append_outcomes(self, df: pd.DataFrame) -> int:
        """Skriv pre-beregnede forward-utfall. `df` må ha kolonnene
        instrument, ref_date, horizon_days, forward_return_pct.
        `max_drawdown_pct` er valgfri (NULL hvis ikke beregnet).

        Idempotent via PK (instrument, ref_date, horizon_days).
        """
        required = ("instrument", "ref_date", "horizon_days", "forward_return_pct")
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_outcomes: missing columns {missing}. "
                f"Required: {list(required)}. Got: {sorted(df.columns)}"
            )

        prepared = df.reindex(columns=list(ANALOG_OUTCOMES_COLS)).copy()
        prepared["ref_date"] = pd.to_datetime(prepared["ref_date"]).dt.strftime("%Y-%m-%d")

        def _to_float_or_none(v: object) -> float | None:
            if v is None or pd.isna(v):
                return None
            return float(v)

        rows: Sequence[tuple] = [
            (
                str(row.instrument),
                row.ref_date,
                int(row.horizon_days),
                float(row.forward_return_pct),
                _to_float_or_none(row.max_drawdown_pct),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_ANALOG_OUTCOMES} "
                f"(instrument, ref_date, horizon_days, forward_return_pct, "
                f"max_drawdown_pct) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_outcomes(
        self,
        instrument: str,
        ref_dates: Sequence[str | date | pd.Timestamp] | None = None,
        horizon_days: int | None = None,
    ) -> pd.DataFrame:
        """Hent forward-utfall for instrument.

        `ref_dates`: hvis gitt, batch-lookup på de spesifikke datoene
        (matcher `ref_date`-kolonnen). Manglende rader rapporteres ikke.
        Hvis None, returneres alle rader for instrumentet.

        `horizon_days`: filtrer på spesifikk horisont. Hvis None,
        returneres alle horisonter.

        Returnerer pd.DataFrame med ref_date som pd.Timestamp i kolonne
        (ikke index — matcher get_cot-pattern). Tom DataFrame hvis ingen
        treff (ingen exception — caller forventer kanskje partial hit
        ved batch-lookup).
        """
        clauses = ["instrument = ?"]
        params: list[object] = [instrument]

        if horizon_days is not None:
            clauses.append("horizon_days = ?")
            params.append(int(horizon_days))

        if ref_dates is not None:
            normalized = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in ref_dates]
            if not normalized:
                # Caller passed an empty sequence — return empty frame
                # without hitting DB. Saves a query.
                return pd.DataFrame(
                    columns=list(ANALOG_OUTCOMES_COLS),
                )
            placeholders = ",".join(["?"] * len(normalized))
            clauses.append(f"ref_date IN ({placeholders})")
            params.extend(normalized)

        query = f"""
            SELECT instrument, ref_date, horizon_days, forward_return_pct,
                   max_drawdown_pct
            FROM {TABLE_ANALOG_OUTCOMES}
            WHERE {" AND ".join(clauses)}
            ORDER BY ref_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=tuple(params))

        if df.empty:
            return df

        df["ref_date"] = pd.to_datetime(df["ref_date"])
        return df

    def has_outcomes(self, instrument: str, horizon_days: int | None = None) -> bool:
        clauses = ["instrument = ?"]
        params: list[object] = [instrument]
        if horizon_days is not None:
            clauses.append("horizon_days = ?")
            params.append(int(horizon_days))
        query = f"SELECT 1 FROM {TABLE_ANALOG_OUTCOMES} WHERE {' AND '.join(clauses)} LIMIT 1"
        with self._connect() as conn:
            cursor = conn.execute(query, tuple(params))
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # PLAN § 7.3 datakilder (session 83+) — generisk append + get
    # ------------------------------------------------------------------

    def _append_generic(
        self,
        df: pd.DataFrame,
        table: str,
        cols: tuple[str, ...],
    ) -> int:
        """Generisk INSERT OR REPLACE for nye § 7.3-tabeller.

        Schema-validering: alle kolonner i ``cols`` må finnes i ``df``.
        Returnerer antall innsatte rader. Tom DataFrame → 0.
        """
        if df.empty:
            return 0
        missing = set(cols) - set(df.columns)
        if missing:
            raise ValueError(f"{table}: df mangler kolonner: {sorted(missing)}")

        prepared = df.reindex(columns=list(cols))
        rows: Sequence[tuple] = [tuple(r) for r in prepared.itertuples(index=False, name=None)]
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()
        return len(rows)

    def append_crop_progress(self, df: pd.DataFrame) -> int:
        """Skriv NASS Crop Progress-rader. Schema: ``CROP_PROGRESS_COLS``."""
        return self._append_generic(df, TABLE_CROP_PROGRESS, CROP_PROGRESS_COLS)

    def get_crop_progress(
        self,
        commodity: str,
        state: str = "US TOTAL",
        metric: str | None = None,
    ) -> pd.DataFrame:
        """Hent crop-progress-rader for én commodity (+ optional metric)."""
        query = f"""
            SELECT * FROM {TABLE_CROP_PROGRESS}
            WHERE commodity = ? AND state = ?
        """
        params: list = [commodity, state]
        if metric is not None:
            query += " AND metric = ?"
            params.append(metric)
        query += " ORDER BY week_ending ASC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        df["week_ending"] = pd.to_datetime(df["week_ending"])
        return df

    def append_wasde(self, df: pd.DataFrame) -> int:
        """Skriv WASDE-rader. Schema: ``WASDE_COLS``."""
        return self._append_generic(df, TABLE_WASDE, WASDE_COLS)

    def get_wasde(
        self,
        commodity: str,
        metric: str,
        region: str = "US",
    ) -> pd.DataFrame:
        """Hent WASDE-tidsserie for (commodity, metric, region)."""
        query = f"""
            SELECT * FROM {TABLE_WASDE}
            WHERE commodity = ? AND metric = ? AND region = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(commodity, metric, region))
        df["report_date"] = pd.to_datetime(df["report_date"])
        return df

    def append_export_events(self, df: pd.DataFrame) -> int:
        return self._append_generic(df, TABLE_EXPORT_EVENTS, EXPORT_EVENTS_COLS)

    def get_export_events(
        self,
        commodity: str | None = None,
        country: str | None = None,
        from_date: str | None = None,
    ) -> pd.DataFrame:
        """Hent eksport-policy events (alle, eller filtrert)."""
        query = f"SELECT * FROM {TABLE_EXPORT_EVENTS} WHERE 1=1"
        params: list = []
        if commodity:
            query += " AND commodity = ?"
            params.append(commodity)
        if country:
            query += " AND country = ?"
            params.append(country)
        if from_date:
            query += " AND event_date >= ?"
            params.append(from_date)
        query += " ORDER BY event_date DESC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        if not df.empty:
            df["event_date"] = pd.to_datetime(df["event_date"])
        return df

    def append_disease_alerts(self, df: pd.DataFrame) -> int:
        return self._append_generic(df, TABLE_DISEASE_ALERTS, DISEASE_ALERTS_COLS)

    def get_disease_alerts(
        self,
        commodity: str | None = None,
        from_date: str | None = None,
    ) -> pd.DataFrame:
        query = f"SELECT * FROM {TABLE_DISEASE_ALERTS} WHERE 1=1"
        params: list = []
        if commodity:
            query += " AND commodity = ?"
            params.append(commodity)
        if from_date:
            query += " AND alert_date >= ?"
            params.append(from_date)
        query += " ORDER BY alert_date DESC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        if not df.empty:
            df["alert_date"] = pd.to_datetime(df["alert_date"])
        return df

    def append_igc(self, df: pd.DataFrame) -> int:
        return self._append_generic(df, TABLE_IGC, IGC_COLS)

    def get_igc(
        self,
        grain: str,
        metric: str,
    ) -> pd.DataFrame:
        """IGC-tidsserie for (grain, metric). Sortert ASC."""
        query = f"""
            SELECT * FROM {TABLE_IGC}
            WHERE grain = ? AND metric = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(grain, metric))
        if not df.empty:
            df["report_date"] = pd.to_datetime(df["report_date"])
        return df

    def append_bdi(self, df: pd.DataFrame) -> int:
        return self._append_generic(df, TABLE_BDI, BDI_COLS)

    def get_bdi(self, last_n: int | None = None) -> pd.Series:
        """Returner BDI-tidsserie sortert ASC. Kaster KeyError hvis tom."""
        query = f"SELECT date, value FROM {TABLE_BDI} ORDER BY date ASC"
        with self._connect() as conn:
            df = pd.read_sql(query, conn)
        if df.empty:
            raise KeyError("No BDI data")
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["value"].astype("float64")
        series.name = None
        if last_n is None:
            return series
        return series.tail(last_n)

    # ------------------------------------------------------------------
    # Økonomisk kalender (sub-fase 12.5+ session 105)
    # ------------------------------------------------------------------

    def append_econ_events(self, df: pd.DataFrame) -> int:
        """Skriv kalender-events til ``econ_events``. Schema:
        ``ECON_EVENTS_COLS``. Idempotent på (event_ts, country, title).

        ``event_ts`` og ``fetched_at`` normaliseres til ISO-streng.
        """
        if df.empty:
            return 0
        prepared = df.copy()
        if "event_ts" in prepared.columns:
            prepared["event_ts"] = pd.to_datetime(prepared["event_ts"], utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        if "fetched_at" in prepared.columns:
            prepared["fetched_at"] = pd.to_datetime(prepared["fetched_at"], utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        return self._append_generic(prepared, TABLE_ECON_EVENTS, ECON_EVENTS_COLS)

    def get_econ_events(
        self,
        countries: Sequence[str] | None = None,
        impact_levels: Sequence[str] | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> pd.DataFrame:
        """Hent kalender-events. Returnerer pd.DataFrame med
        `event_ts` som tz-aware UTC pd.Timestamp i en kolonne (ikke index).

        Filtre er optional; alle returnerer hele tabellen sortert ASC på
        event_ts. Tom resultat → tom DataFrame med kolonner intakt.
        """
        query = f"SELECT * FROM {TABLE_ECON_EVENTS} WHERE 1=1"
        params: list = []
        if countries:
            placeholders = ", ".join(["?"] * len(countries))
            query += f" AND country IN ({placeholders})"
            params.extend(countries)
        if impact_levels:
            placeholders = ", ".join(["?"] * len(impact_levels))
            query += f" AND impact IN ({placeholders})"
            params.extend(impact_levels)
        if from_ts is not None:
            query += " AND event_ts >= ?"
            params.append(from_ts)
        if to_ts is not None:
            query += " AND event_ts <= ?"
            params.append(to_ts)
        query += " ORDER BY event_ts ASC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        if not df.empty:
            df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
            df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
        return df

    # ------------------------------------------------------------------
    # Generisk staleness-accessor (fase 6 session 28)
    # ------------------------------------------------------------------

    def latest_observation_ts(self, table: str, ts_column: str = "ts") -> str | None:
        """Returner `MAX(ts_column)` fra `table` som rå-streng, eller None
        hvis tabellen er tom/ikke finnes.

        Brukes av `bedrock.config.fetch` for staleness-sjekker. Caller
        ansvar for å parse resultatet til datetime.
        """
        with self._connect() as conn:
            # Sjekk at tabellen finnes (unngår SQL-feil)
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists is None:
                return None

            # Tabell/kolonne-identifikatorer må interpoleres (sqlite
            # param-binding er kun for verdier). Verdier stammer fra
            # Pydantic-validert YAML, ikke request-input.
            row = conn.execute(f"SELECT MAX({ts_column}) FROM {table}").fetchone()

        if row is None or row[0] is None:
            return None
        return row[0]
