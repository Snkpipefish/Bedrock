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
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import pandas as pd

from bedrock.data.release_calendar import aaii_released_at_iso, cot_released_at_iso
from bedrock.data.schemas import (
    AAII_SENTIMENT_COLS,
    AGSI_STORAGE_COLS,
    ALSI_STORAGE_COLS,
    ANALOG_OUTCOMES_COLS,
    CECAFE_EXPORTS_COLS,
    COMEX_INVENTORY_COLS,
    CONAB_ESTIMATES_COLS,
    COT_DISAGGREGATED_COLS,
    COT_EURONEXT_COLS,
    COT_ICE_COLS,
    COT_LEGACY_COLS,
    COT_TFF_COLS,
    CROP_PROGRESS_COLS,
    CRYPTO_SENTIMENT_COLS,
    DDL_AAII_SENTIMENT,
    DDL_AGSI_STORAGE,
    DDL_ALSI_STORAGE,
    DDL_ANALOG_OUTCOMES,
    DDL_CECAFE_EXPORTS,
    DDL_COMEX_INVENTORY,
    DDL_CONAB_ESTIMATES,
    DDL_COT_DISAGGREGATED,
    DDL_COT_EURONEXT,
    DDL_COT_ICE,
    DDL_COT_LEGACY,
    DDL_COT_TFF,
    DDL_CROP_PROGRESS,
    DDL_CRYPTO_SENTIMENT,
    DDL_DISEASE_ALERTS,
    DDL_DROUGHT_MONITOR,
    DDL_ECON_EVENTS,
    DDL_EIA_INVENTORY,
    DDL_ETF_HOLDINGS,
    DDL_EXPORT_EVENTS,
    DDL_FAS_ESR,
    DDL_FUNDAMENTALS,
    DDL_IGC,
    DDL_IIP_REMIT,
    DDL_NEWS_INTEL,
    DDL_PRICES,
    DDL_SEISMIC_EVENTS,
    DDL_SHIPPING_INDICES,
    DDL_UNICA_REPORTS,
    DDL_WASDE,
    DDL_WEATHER,
    DDL_WEATHER_MONTHLY,
    DISEASE_ALERTS_COLS,
    DROUGHT_MONITOR_COLS,
    ECON_EVENTS_COLS,
    EIA_INVENTORY_COLS,
    ETF_HOLDINGS_COLS,
    EXPORT_EVENTS_COLS,
    FAS_ESR_COLS,
    FUNDAMENTALS_COLS,
    IGC_COLS,
    IIP_REMIT_COLS,
    NEWS_INTEL_COLS,
    SEISMIC_EVENTS_COLS,
    SHIPPING_INDICES_COLS,
    TABLE_AAII_SENTIMENT,
    TABLE_AGSI_STORAGE,
    TABLE_ALSI_STORAGE,
    TABLE_ANALOG_OUTCOMES,
    TABLE_BDI,
    TABLE_CECAFE_EXPORTS,
    TABLE_COMEX_INVENTORY,
    TABLE_CONAB_ESTIMATES,
    TABLE_COT_DISAGGREGATED,
    TABLE_COT_EURONEXT,
    TABLE_COT_ICE,
    TABLE_COT_LEGACY,
    TABLE_COT_TFF,
    TABLE_CROP_PROGRESS,
    TABLE_CRYPTO_SENTIMENT,
    TABLE_DISEASE_ALERTS,
    TABLE_DROUGHT_MONITOR,
    TABLE_ECON_EVENTS,
    TABLE_EIA_INVENTORY,
    TABLE_ETF_HOLDINGS,
    TABLE_EXPORT_EVENTS,
    TABLE_FAS_ESR,
    TABLE_FUNDAMENTALS,
    TABLE_IGC,
    TABLE_IIP_REMIT,
    TABLE_NEWS_INTEL,
    TABLE_PRICES,
    TABLE_SEISMIC_EVENTS,
    TABLE_SHIPPING_INDICES,
    TABLE_UNICA_REPORTS,
    TABLE_WASDE,
    TABLE_WEATHER,
    TABLE_WEATHER_MONTHLY,
    UNICA_REPORTS_COLS,
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
            conn.execute(DDL_COT_TFF)
            conn.execute(DDL_FUNDAMENTALS)
            conn.execute(DDL_WEATHER)
            conn.execute(DDL_WEATHER_MONTHLY)
            conn.execute(DDL_ANALOG_OUTCOMES)
            # PLAN § 7.3 datakilder (session 83+):
            conn.execute(DDL_CROP_PROGRESS)
            conn.execute(DDL_WASDE)
            conn.execute(DDL_EXPORT_EVENTS)
            conn.execute(DDL_DISEASE_ALERTS)
            conn.execute(DDL_IGC)
            # Sub-fase 12.5+ session 105 (ADR-007/008):
            conn.execute(DDL_ECON_EVENTS)
            # Sub-fase 12.5+ session 106 (ADR-008): ICE Futures Europe COT.
            conn.execute(DDL_COT_ICE)
            # Sub-fase 12.5+ session 107 (ADR-008): EIA weekly inventories.
            conn.execute(DDL_EIA_INVENTORY)
            # Sub-fase 12.5+ session 108 (ADR-008): COMEX warehouse inventories.
            conn.execute(DDL_COMEX_INVENTORY)
            # Sub-fase 12.5+ session 109 (ADR-008): USGS seismic events.
            conn.execute(DDL_SEISMIC_EVENTS)
            # Sub-fase 12.5+ session 110 (ADR-008): Euronext MiFID II COT.
            conn.execute(DDL_COT_EURONEXT)
            # Sub-fase 12.5+ session 111 (ADR-008): Conab Brazil crop estimates.
            conn.execute(DDL_CONAB_ESTIMATES)
            # Sub-fase 12.5+ session 112 (ADR-008): UNICA Brazil sugar/ethanol.
            conn.execute(DDL_UNICA_REPORTS)
            # Sub-fase 12.5+ session 113 (ADR-008): Baltic shipping suite
            # (BDI/BCI/BPI/BSI long-format). Erstatter den gamle `bdi`-
            # tabellen via idempotent migrasjon under.
            conn.execute(DDL_SHIPPING_INDICES)
            self._migrate_bdi_to_shipping_indices(conn)
            # Sub-fase 12.5+ session 114 (ADR-008): Google News RSS-articles
            # per kategori. UI-only foreløpig; scoring-driver vurderes etter
            # ≥1 mnds empirisk data.
            conn.execute(DDL_NEWS_INTEL)
            # Sub-fase 12.5+ session 115 (ADR-008): Crypto sentiment-indikatorer
            # (F&G + CoinGecko dominance/mcap). UI-only; scoring-driver
            # vurderes etter ≥1 mnds data.
            conn.execute(DDL_CRYPTO_SENTIMENT)
            # Sub-fase 12.7 D1 A2 (session 130): AGSI EU gas storage.
            conn.execute(DDL_AGSI_STORAGE)
            # Sub-fase 12.7 D2 A12 (session 131): AAII Sentiment Survey.
            conn.execute(DDL_AAII_SENTIMENT)
            # Sub-fase 12.7 D2 A5/A6 (session 132): physical-ETF holdings
            # (GLD/SLV; future-extensible).
            conn.execute(DDL_ETF_HOLDINGS)
            # Sub-fase 12.7 D2 A3 (session 133): FAS Export Sales (ESR).
            conn.execute(DDL_FAS_ESR)
            # Sub-fase 12.7 D2 A9 (session 133): US Drought Monitor.
            conn.execute(DDL_DROUGHT_MONITOR)
            # Sub-fase 12.7 D3 A10 (session 135): Cecafé Brasil kaffe-eksport.
            conn.execute(DDL_CECAFE_EXPORTS)
            # Sub-fase 12.10 follow-up Spor C (session 136): ALSI EU LNG-
            # terminal storage + IIP REMIT supply-unavailability.
            conn.execute(DDL_ALSI_STORAGE)
            conn.execute(DDL_IIP_REMIT)
            # Sub-fase 12.10 Bunke 1 Bug-1: backfill released_at-kolonnen på
            # COT- + AAII-tabellene for eksisterende rader (ALTER TABLE +
            # konvensjons-basert UPDATE). Idempotent.
            self._migrate_released_at_columns(conn)
            conn.commit()

    def _migrate_released_at_columns(self, conn: sqlite3.Connection) -> None:
        """Sub-fase 12.10 Bunke 1 Bug-1: legg til released_at-kolonnen på
        eksisterende COT- og AAII-tabeller hvis den mangler, og backfill
        rader uten verdi via release_calendar-konvensjonen.

        Idempotent: hopper ALTER TABLE hvis kolonnen finnes; UPDATE-
        kjøringen filtrerer på released_at IS NULL slik at allerede
        backfilte rader ikke endres.

        SQLite datetime-aritmetikk: ``datetime(report_date, '+3 days',
        '21:00:00')`` produserer "YYYY-MM-DD HH:MM:SS" UTC-naive — matcher
        `release_calendar.cot_released_at(...).isoformat(sep=' ', ...)`.
        """
        cot_tables = (
            TABLE_COT_DISAGGREGATED,
            TABLE_COT_LEGACY,
            TABLE_COT_TFF,
            TABLE_COT_ICE,
            TABLE_COT_EURONEXT,
        )
        for table in cot_tables:
            if not self._column_exists(conn, table, "released_at"):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN released_at TEXT")
            conn.execute(
                f"""
                UPDATE {table}
                SET released_at = datetime(report_date, '+3 days', '21:00:00')
                WHERE released_at IS NULL
                """
            )

        if not self._column_exists(conn, TABLE_AAII_SENTIMENT, "released_at"):
            conn.execute(f"ALTER TABLE {TABLE_AAII_SENTIMENT} ADD COLUMN released_at TEXT")
        conn.execute(
            f"""
            UPDATE {TABLE_AAII_SENTIMENT}
            SET released_at = datetime(date, '+1 day', '14:00:00')
            WHERE released_at IS NULL
            """
        )

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def _migrate_bdi_to_shipping_indices(self, conn: sqlite3.Connection) -> None:
        """Engangs-migrasjon: kopier alle `bdi`-rader til `shipping_indices`
        med index_code='BDI', deretter dropp `bdi`-tabellen.

        Idempotent — sjekker først om gammel tabell finnes; hvis ikke,
        no-op. Trygt på fresh DB. Kjøres automatisk ved init.
        """
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_BDI,),
        )
        if cursor.fetchone() is None:
            return  # Ingen gammel bdi-tabell → no-op

        # Tell rader før migrasjon (for verifisering)
        n_before = conn.execute(f"SELECT COUNT(*) FROM {TABLE_BDI}").fetchone()[0]

        # Idempotent kopiering: INSERT OR IGNORE i tilfelle delvis kjørt
        # tidligere (skal ikke skje, men forsvarlig).
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {TABLE_SHIPPING_INDICES} (index_code, date, value, source)
            SELECT 'BDI', date, value, source FROM {TABLE_BDI}
            """
        )

        # Verifiser at minst like mange rader nå finnes for BDI som vi
        # hadde før (kan være flere hvis migrasjonen ble kjørt flere
        # ganger, men det er INSERT OR IGNORE så det er idempotent).
        n_after = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_SHIPPING_INDICES} WHERE index_code='BDI'"
        ).fetchone()[0]

        if n_after < n_before:
            raise RuntimeError(
                f"bdi → shipping_indices migrasjon: tapte rader "
                f"(før={n_before}, etter={n_after}). Aborterer."
            )

        # Dropp gammel tabell først etter at vi har verifisert kopi.
        conn.execute(f"DROP TABLE {TABLE_BDI}")

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

    def append_cot_tff(self, df: pd.DataFrame) -> int:
        """Skriv rader til `cot_tff` (Traders in Financial Futures).

        D1 A4 (sub-fase 12.7, session 128). TFF-rapporten dekker
        finansielle futures med trader-typene Dealer/Asset Manager/
        Leveraged Funds/Other Reportables/Non-Reportables.

        Returnerer antall rader. Duplicates på (report_date, contract)
        overskrives via INSERT OR REPLACE.
        """
        return self._append_cot(df, TABLE_COT_TFF, COT_TFF_COLS)

    def get_cot_tff(
        self,
        contract: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner TFF-COT-rader for `contract`, sortert på report_date ASC.

        Parallell til `get_cot` men for TFF-tabellen. Kaster `KeyError`
        hvis ingen rader finnes for `contract`.
        """
        query = f"""
            SELECT * FROM {TABLE_COT_TFF}
            WHERE contract = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(contract,))

        if df.empty:
            raise KeyError(f"No COT-TFF data for contract={contract!r}")

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_cot_tff(self, contract: str | None = None) -> bool:
        """Test-hjelper: sjekk om (contract) har minst én rad i cot_tff."""
        with self._connect() as conn:
            if contract is None:
                cursor = conn.execute(f"SELECT 1 FROM {TABLE_COT_TFF} LIMIT 1")
            else:
                cursor = conn.execute(
                    f"SELECT 1 FROM {TABLE_COT_TFF} WHERE contract = ? LIMIT 1",
                    (contract,),
                )
            return cursor.fetchone() is not None

    def _append_cot(
        self,
        df: pd.DataFrame,
        table: str,
        expected_cols: tuple[str, ...],
    ) -> int:
        # Sub-fase 12.10 Bunke 1 Bug-1: auto-utled released_at fra report_date
        # via release_calendar hvis ikke gitt. Slik trenger ikke fetcher-
        # kallere oppdateres samtidig som schema utvides.
        if "released_at" in expected_cols and "released_at" not in df.columns:
            df = df.copy()
            df["released_at"] = pd.to_datetime(df["report_date"]).apply(
                lambda d: cot_released_at_iso(d)
            )

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
    # COT — Euronext MiFID II (sub-fase 12.5+ session 110)
    # ------------------------------------------------------------------

    def append_cot_euronext(self, df: pd.DataFrame) -> int:
        """Skriv rader til ``cot_euronext``. Returnerer antall rader.

        `df` må ha kolonnene i ``COT_EURONEXT_COLS`` (report_date,
        contract, mm_long, mm_short, open_interest). Idempotent på
        (report_date, contract) via INSERT OR REPLACE.

        Sub-fase 12.10 Bunke 1 Bug-1: ``released_at`` auto-utledes via
        release_calendar hvis ikke gitt.
        """
        if "released_at" not in df.columns:
            df = df.copy()
            df["released_at"] = pd.to_datetime(df["report_date"]).apply(
                lambda d: cot_released_at_iso(d)
            )

        missing = [c for c in COT_EURONEXT_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_cot_euronext: missing columns {missing}. "
                f"Required: {list(COT_EURONEXT_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(COT_EURONEXT_COLS)].copy()
        prepared["report_date"] = pd.to_datetime(prepared["report_date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                row.report_date,
                str(row.contract),
                int(row.mm_long),
                int(row.mm_short),
                int(row.open_interest),
                row.released_at,
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_COT_EURONEXT} "
                f"(report_date, contract, mm_long, mm_short, open_interest, released_at) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_cot_euronext(
        self,
        contract: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner Euronext COT-rader for `contract`, sortert ASC på report_date.

        Returnerer pd.DataFrame med `report_date` som pd.Timestamp.
        Kaster ``KeyError`` hvis ingen rader for ``contract``.
        """
        query = f"""
            SELECT * FROM {TABLE_COT_EURONEXT}
            WHERE contract = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(contract,))

        if df.empty:
            raise KeyError(f"No Euronext COT data for contract={contract!r}")

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_cot_euronext(self, contract: str) -> bool:
        """Test-hjelper: sjekk om `contract` har minst én Euronext-rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_COT_EURONEXT} WHERE contract = ? LIMIT 1",
                (contract,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Conab Brazil crop estimates (sub-fase 12.5+ session 111)
    # ------------------------------------------------------------------

    def append_conab_estimates(self, df: pd.DataFrame) -> int:
        """Skriv rader til ``conab_estimates``. Returnerer antall rader.

        `df` må ha kolonnene i ``CONAB_ESTIMATES_COLS``. Idempotent på
        (report_date, commodity) via INSERT OR REPLACE — Conab kan
        revidere et levantamento ved feil-publisering.
        """
        missing = [c for c in CONAB_ESTIMATES_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_conab_estimates: missing columns {missing}. "
                f"Required: {list(CONAB_ESTIMATES_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(CONAB_ESTIMATES_COLS)].copy()
        prepared["report_date"] = pd.to_datetime(prepared["report_date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                row.report_date,
                str(row.commodity),
                None if pd.isna(row.levantamento) else str(row.levantamento),
                None if pd.isna(row.safra) else str(row.safra),
                float(row.production),
                str(row.production_units),
                None if pd.isna(row.area_kha) else float(row.area_kha),
                None if pd.isna(row.yield_value) else float(row.yield_value),
                None if pd.isna(row.yield_units) else str(row.yield_units),
                None if pd.isna(row.yoy_change_pct) else float(row.yoy_change_pct),
                None if pd.isna(row.mom_change_pct) else float(row.mom_change_pct),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_CONAB_ESTIMATES} "
                f"(report_date, commodity, levantamento, safra, production, "
                f"production_units, area_kha, yield_value, yield_units, "
                f"yoy_change_pct, mom_change_pct) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_conab_estimates(
        self,
        commodity: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner Conab-rader for `commodity`, sortert ASC på report_date.

        Returnerer pd.DataFrame med report_date som pd.Timestamp. Kaster
        ``KeyError`` hvis ingen rader for ``commodity``.
        """
        query = f"""
            SELECT * FROM {TABLE_CONAB_ESTIMATES}
            WHERE commodity = ?
            ORDER BY report_date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(commodity,))

        if df.empty:
            raise KeyError(f"No Conab data for commodity={commodity!r}")

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_conab_estimates(self, commodity: str) -> bool:
        """Test-hjelper: sjekk om `commodity` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_CONAB_ESTIMATES} WHERE commodity = ? LIMIT 1",
                (commodity,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # UNICA Brazil sugar/ethanol reports (sub-fase 12.5+ session 112)
    # ------------------------------------------------------------------

    def append_unica_reports(self, df: pd.DataFrame) -> int:
        """Skriv rader til ``unica_reports``. Returnerer antall rader.

        `df` må ha kolonnene i ``UNICA_REPORTS_COLS``. Idempotent på
        report_date via INSERT OR REPLACE.
        """
        missing = [c for c in UNICA_REPORTS_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_unica_reports: missing columns {missing}. "
                f"Required: {list(UNICA_REPORTS_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(UNICA_REPORTS_COLS)].copy()
        prepared["report_date"] = pd.to_datetime(prepared["report_date"]).dt.strftime("%Y-%m-%d")

        def _opt_str(v: Any) -> str | None:
            return None if pd.isna(v) else str(v)

        def _opt_float(v: Any) -> float | None:
            return None if pd.isna(v) else float(v)

        rows: Sequence[tuple] = [
            (
                row.report_date,
                _opt_str(row.position_date),
                _opt_str(row.period),
                _opt_str(row.crop_year),
                _opt_float(row.mix_sugar_pct),
                _opt_float(row.mix_sugar_pct_prev),
                _opt_float(row.mix_ethanol_pct),
                _opt_float(row.mix_ethanol_pct_prev),
                _opt_float(row.crush_kt),
                _opt_float(row.crush_kt_prev),
                _opt_float(row.crush_yoy_pct),
                _opt_float(row.sugar_production_kt),
                _opt_float(row.sugar_production_kt_prev),
                _opt_float(row.sugar_production_yoy_pct),
                _opt_float(row.ethanol_total_ml),
                _opt_float(row.ethanol_total_ml_prev),
                _opt_float(row.ethanol_total_yoy_pct),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_UNICA_REPORTS} "
                f"({', '.join(UNICA_REPORTS_COLS)}) "
                f"VALUES ({', '.join(['?'] * len(UNICA_REPORTS_COLS))})",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_unica_reports(self, last_n: int | None = None) -> pd.DataFrame:
        """Returner alle UNICA-rapporter sortert ASC på report_date.

        Returnerer pd.DataFrame med report_date som pd.Timestamp. Tom
        DataFrame hvis ingen rader.
        """
        query = f"SELECT * FROM {TABLE_UNICA_REPORTS} ORDER BY report_date ASC"
        with self._connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            return df

        df["report_date"] = pd.to_datetime(df["report_date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_unica_reports(self) -> bool:
        """Test-hjelper: sjekk om tabellen har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(f"SELECT 1 FROM {TABLE_UNICA_REPORTS} LIMIT 1")
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # EIA inventories (sub-fase 12.5+ session 107)
    # ------------------------------------------------------------------

    def append_eia_inventory(self, df: pd.DataFrame) -> int:
        """Skriv EIA-rader til ``eia_inventory``. Returnerer antall rader.

        `df` må ha kolonnene i ``EIA_INVENTORY_COLS`` (series_id, date,
        value, units). Idempotent på (series_id, date) via INSERT OR
        REPLACE.
        """
        missing = [c for c in EIA_INVENTORY_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_eia_inventory: missing columns {missing}. "
                f"Required: {list(EIA_INVENTORY_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(EIA_INVENTORY_COLS)].copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                str(row.series_id),
                row.date,
                float(row.value),
                None if pd.isna(row.units) else str(row.units),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_EIA_INVENTORY} "
                f"(series_id, date, value, units) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_eia_inventory(
        self,
        series_id: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner EIA-rader for `series_id`, sortert ASC på date.

        Returnerer pd.DataFrame med `date` som pd.Timestamp i en kolonne
        (ikke index) — stocks er ukentlige diskrete events, samme
        konvensjon som `get_cot()`.

        Kaster `KeyError` hvis ingen rader finnes for `series_id`.
        """
        query = f"""
            SELECT * FROM {TABLE_EIA_INVENTORY}
            WHERE series_id = ?
            ORDER BY date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(series_id,))

        if df.empty:
            raise KeyError(f"No EIA inventory data for series_id={series_id!r}")

        df["date"] = pd.to_datetime(df["date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_eia_inventory(self, series_id: str) -> bool:
        """Test-hjelper: sjekk om `series_id` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_EIA_INVENTORY} WHERE series_id = ? LIMIT 1",
                (series_id,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # COMEX warehouse inventories (sub-fase 12.5+ session 108)
    # ------------------------------------------------------------------

    def append_comex_inventory(self, df: pd.DataFrame) -> int:
        """Skriv COMEX-rader til ``comex_inventory``. Returnerer antall rader.

        `df` må ha kolonnene i ``COMEX_INVENTORY_COLS`` (metal, date,
        registered, eligible, total, units). Idempotent på (metal, date)
        via INSERT OR REPLACE.
        """
        missing = [c for c in COMEX_INVENTORY_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_comex_inventory: missing columns {missing}. "
                f"Required: {list(COMEX_INVENTORY_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(COMEX_INVENTORY_COLS)].copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        rows: Sequence[tuple] = [
            (
                str(row.metal),
                row.date,
                float(row.registered),
                float(row.eligible),
                float(row.total),
                None if pd.isna(row.units) else str(row.units),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_COMEX_INVENTORY} "
                f"(metal, date, registered, eligible, total, units) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_comex_inventory(
        self,
        metal: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner COMEX-rader for `metal`, sortert ASC på date.

        Returnerer pd.DataFrame med `date` som pd.Timestamp. Kaster
        ``KeyError`` hvis ingen rader for ``metal``.
        """
        query = f"""
            SELECT * FROM {TABLE_COMEX_INVENTORY}
            WHERE metal = ?
            ORDER BY date ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(metal,))

        if df.empty:
            raise KeyError(f"No COMEX inventory data for metal={metal!r}")

        df["date"] = pd.to_datetime(df["date"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_comex_inventory(self, metal: str) -> bool:
        """Test-hjelper: sjekk om `metal` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_COMEX_INVENTORY} WHERE metal = ? LIMIT 1",
                (metal,),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Seismic events (sub-fase 12.5+ session 109)
    # ------------------------------------------------------------------

    def append_seismic_events(self, df: pd.DataFrame) -> int:
        """Skriv USGS-events til ``seismic_events``. Returnerer antall rader.

        `df` må ha kolonnene i ``SEISMIC_EVENTS_COLS``. event_ts kan være
        pd.Timestamp eller ISO-streng. Idempotent på event_id via
        INSERT OR REPLACE.
        """
        missing = [c for c in SEISMIC_EVENTS_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_seismic_events: missing columns {missing}. "
                f"Required: {list(SEISMIC_EVENTS_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(SEISMIC_EVENTS_COLS)].copy()
        prepared["event_ts"] = pd.to_datetime(prepared["event_ts"], utc=True).dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        rows: Sequence[tuple] = [
            (
                str(row.event_id),
                row.event_ts,
                float(row.magnitude),
                float(row.latitude),
                float(row.longitude),
                None if pd.isna(row.depth_km) else float(row.depth_km),
                None if pd.isna(row.place) else str(row.place),
                None if pd.isna(row.region) else str(row.region),
                None if pd.isna(row.url) else str(row.url),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_SEISMIC_EVENTS} "
                f"(event_id, event_ts, magnitude, latitude, longitude, "
                f"depth_km, place, region, url) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_seismic_events(
        self,
        *,
        region: str | None = None,
        regions: Sequence[str] | None = None,
        from_ts: datetime | None = None,
        min_magnitude: float | None = None,
    ) -> pd.DataFrame:
        """Returner events med valgfrie filtre, sortert ASC på event_ts.

        Args:
            region: en spesifikk region (eks. "Chile / Peru"). None = alle.
            regions: liste regioner (eks. ["Chile / Peru", "Sør-Afrika"]).
                Brukes hvis `region` er None.
            from_ts: kun events med event_ts >= from_ts. None = alle.
            min_magnitude: kun events med magnitude >= verdi. None = alle.

        Returnerer DataFrame med event_ts som pd.Timestamp. Tom DataFrame
        hvis ingen rader matcher.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if region is not None:
            clauses.append("region = ?")
            params.append(region)
        elif regions:
            placeholders = ",".join(["?"] * len(regions))
            clauses.append(f"region IN ({placeholders})")
            params.extend(regions)

        if from_ts is not None:
            clauses.append("event_ts >= ?")
            params.append(from_ts.strftime("%Y-%m-%dT%H:%M:%S"))

        if min_magnitude is not None:
            clauses.append("magnitude >= ?")
            params.append(min_magnitude)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM {TABLE_SEISMIC_EVENTS} {where} ORDER BY event_ts ASC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=tuple(params))

        if not df.empty:
            df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
        return df

    def has_seismic_events(self) -> bool:
        """Test-hjelper: sjekk om tabellen har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_SEISMIC_EVENTS} LIMIT 1",
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

    def append_shipping_indices(self, df: pd.DataFrame) -> int:
        """Skriv shipping-index-rader til ``shipping_indices``-tabellen.

        Schema: ``SHIPPING_INDICES_COLS`` — (index_code, date, value, source).
        Idempotent på (index_code, date) via INSERT OR REPLACE. Returnerer
        antall rader skrevet.

        Erstatter den gamle ``append_bdi`` (sub-fase 12.5+ session 113).
        """
        return self._append_generic(df, TABLE_SHIPPING_INDICES, SHIPPING_INDICES_COLS)

    def get_shipping_index(
        self,
        index_code: str,
        last_n: int | None = None,
    ) -> pd.Series:
        """Returner verdi-tidsserie for én shipping-indeks (BDI/BCI/BPI/BSI).

        Sortert ASC på date. Kaster ``KeyError`` hvis ingen rader for
        ``index_code``. Drivere må håndtere det (returnere 0.5 nøytral).

        Erstatter den gamle ``get_bdi`` (sub-fase 12.5+ session 113).
        """
        code = index_code.upper()
        query = (
            f"SELECT date, value FROM {TABLE_SHIPPING_INDICES} "
            f"WHERE index_code = ? ORDER BY date ASC"
        )
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(code,))
        if df.empty:
            raise KeyError(f"No shipping_indices data for index_code={code!r}")
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["value"].astype("float64")
        series.name = None
        if last_n is None:
            return series
        return series.tail(last_n)

    def has_shipping_index(self, index_code: str | None = None) -> bool:
        """Test-hjelper: True hvis det finnes minst én rad.

        Hvis ``index_code`` gitt, sjekker kun for den koden. Ellers
        sjekker hele tabellen.
        """
        with self._connect() as conn:
            if index_code is None:
                cursor = conn.execute(f"SELECT 1 FROM {TABLE_SHIPPING_INDICES} LIMIT 1")
            else:
                cursor = conn.execute(
                    f"SELECT 1 FROM {TABLE_SHIPPING_INDICES} WHERE index_code = ? LIMIT 1",
                    (index_code.upper(),),
                )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # News intel — Google News RSS (sub-fase 12.5+ session 114)
    # ------------------------------------------------------------------

    def append_news_intel(self, df: pd.DataFrame) -> int:
        """Skriv news_intel-rader. Schema: ``NEWS_INTEL_COLS``.

        Idempotent på (url) via INSERT OR IGNORE — beholder den FØRSTE
        fetched_at-tidsstemplet siden samme artikkel kan være til stede
        i RSS-feeden i flere dager. Dette er bevisst forskjellig fra
        de fleste andre tabellene som bruker INSERT OR REPLACE.
        Returnerer antall NYE rader (eksisterende dupes telles ikke).
        """
        if df.empty:
            return 0
        missing = [c for c in NEWS_INTEL_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_news_intel: missing columns {missing}. "
                f"Required: {list(NEWS_INTEL_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(NEWS_INTEL_COLS)].copy()
        prepared["event_ts"] = pd.to_datetime(prepared["event_ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
        prepared["fetched_at"] = pd.to_datetime(prepared["fetched_at"]).dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        def _opt_str(v: Any) -> str | None:
            return None if pd.isna(v) else str(v)

        def _opt_float(v: Any) -> float | None:
            return None if pd.isna(v) else float(v)

        rows: Sequence[tuple] = [
            (
                str(row.url),
                row.event_ts,
                row.fetched_at,
                str(row.category).lower(),
                str(row.title),
                _opt_str(row.source),
                str(row.query_id),
                _opt_str(row.sentiment_label),
                _opt_float(row.disruption_score),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            cursor = conn.executemany(
                f"INSERT OR IGNORE INTO {TABLE_NEWS_INTEL} "
                f"({', '.join(NEWS_INTEL_COLS)}) "
                f"VALUES ({', '.join(['?'] * len(NEWS_INTEL_COLS))})",
                rows,
            )
            n_new = cursor.rowcount
            conn.commit()
        # rowcount returnerer faktisk insertert (skipper IGNORE-ed dupes)
        return n_new if n_new is not None and n_new >= 0 else 0

    def get_news_intel(
        self,
        category: str | None = None,
        from_event_ts: str | None = None,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner news_intel-rader sortert DESC på event_ts (nyeste først).

        Filtrer:
        - ``category``: 'gold'/'silver'/etc — None = alle.
        - ``from_event_ts``: ISO-string; kun artikler ≥ denne tiden.
        - ``last_n``: ta de N siste.

        Returnerer pd.DataFrame med event_ts/fetched_at som timestamps.
        Tom DataFrame hvis ingen rader.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category.lower())
        if from_event_ts is not None:
            clauses.append("event_ts >= ?")
            params.append(from_event_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM {TABLE_NEWS_INTEL} {where} ORDER BY event_ts DESC"
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=tuple(params))

        if df.empty:
            return df
        df["event_ts"] = pd.to_datetime(df["event_ts"])
        df["fetched_at"] = pd.to_datetime(df["fetched_at"])
        if last_n is not None:
            df = df.head(last_n).reset_index(drop=True)
        return df

    def has_news_intel(self) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(f"SELECT 1 FROM {TABLE_NEWS_INTEL} LIMIT 1")
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Crypto sentiment (sub-fase 12.5+ session 115)
    # ------------------------------------------------------------------

    def append_crypto_sentiment(self, df: pd.DataFrame) -> int:
        """Skriv crypto-sentiment-rader. Schema: ``CRYPTO_SENTIMENT_COLS``.

        Idempotent på (indicator, date) via INSERT OR REPLACE — siste
        observasjon for samme dag overskriver (CoinGecko kan revidere
        dominance-tall innen samme UTC-dag).
        """
        return self._append_generic(df, TABLE_CRYPTO_SENTIMENT, CRYPTO_SENTIMENT_COLS)

    def get_crypto_sentiment(
        self,
        indicator: str,
        last_n: int | None = None,
    ) -> pd.Series:
        """Returner verdi-tidsserie for én indikator (sortert ASC på date).

        Kaster ``KeyError`` hvis ingen rader for ``indicator``.
        Drivere må håndtere det (returnere 0.5 nøytral).
        """
        ind = indicator.lower().strip()
        query = (
            f"SELECT date, value FROM {TABLE_CRYPTO_SENTIMENT} "
            f"WHERE indicator = ? ORDER BY date ASC"
        )
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(ind,))
        if df.empty:
            raise KeyError(f"No crypto_sentiment data for indicator={ind!r}")
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["value"].astype("float64")
        series.name = None
        if last_n is None:
            return series
        return series.tail(last_n)

    def has_crypto_sentiment(self, indicator: str | None = None) -> bool:
        """True hvis det finnes minst én rad. Hvis ``indicator`` gitt,
        sjekker kun for den indikatoren."""
        with self._connect() as conn:
            if indicator is None:
                cursor = conn.execute(f"SELECT 1 FROM {TABLE_CRYPTO_SENTIMENT} LIMIT 1")
            else:
                cursor = conn.execute(
                    f"SELECT 1 FROM {TABLE_CRYPTO_SENTIMENT} WHERE indicator = ? LIMIT 1",
                    (indicator.lower().strip(),),
                )
            return cursor.fetchone() is not None

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
    # AGSI EU gas storage (sub-fase 12.7 D1 A2, session 130)
    # ------------------------------------------------------------------

    def append_agsi_storage(self, df: pd.DataFrame) -> int:
        """Skriv AGSI-rader til ``agsi_storage``. Returnerer antall rader.

        `df` må ha kolonnene i ``AGSI_STORAGE_COLS`` (country, gas_day_start,
        gas_in_storage_twh, working_gas_volume_twh, consumption_full_pct,
        injection_twh, withdrawal_twh, net_withdrawal_twh). Idempotent på
        (country, gas_day_start) via INSERT OR REPLACE.
        """
        missing = [c for c in AGSI_STORAGE_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_agsi_storage: missing columns {missing}. "
                f"Required: {list(AGSI_STORAGE_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(AGSI_STORAGE_COLS)].copy()
        prepared["gas_day_start"] = pd.to_datetime(prepared["gas_day_start"]).dt.strftime(
            "%Y-%m-%d"
        )

        def _opt(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                str(row.country).lower(),
                row.gas_day_start,
                _opt(row.gas_in_storage_twh),
                _opt(row.working_gas_volume_twh),
                _opt(row.consumption_full_pct),
                _opt(row.injection_twh),
                _opt(row.withdrawal_twh),
                _opt(row.net_withdrawal_twh),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_AGSI_STORAGE} "
                f"(country, gas_day_start, gas_in_storage_twh, working_gas_volume_twh, "
                f"consumption_full_pct, injection_twh, withdrawal_twh, net_withdrawal_twh) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_agsi_storage(
        self,
        country: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner AGSI-rader for `country`, sortert ASC på gas_day_start.

        `country` er ISO-2 lowercase (``"de"``, ``"nl"``, ...) eller ``"eu"``
        for aggregat. Returnerer pd.DataFrame med `gas_day_start` som
        pd.Timestamp i en kolonne (ikke index) — daglig-kadens, samme
        konvensjon som get_eia_inventory.

        Kaster `KeyError` hvis ingen rader finnes for `country`.
        """
        country_norm = country.lower()
        query = f"""
            SELECT * FROM {TABLE_AGSI_STORAGE}
            WHERE country = ?
            ORDER BY gas_day_start ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(country_norm,))

        if df.empty:
            raise KeyError(f"No AGSI storage data for country={country_norm!r}")

        df["gas_day_start"] = pd.to_datetime(df["gas_day_start"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_agsi_storage(self, country: str) -> bool:
        """Test-hjelper: sjekk om `country` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_AGSI_STORAGE} WHERE country = ? LIMIT 1",
                (country.lower(),),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # ALSI EU LNG-terminal storage (sub-fase 12.10 follow-up Spor C, s136)
    # ------------------------------------------------------------------

    def append_alsi_storage(self, df: pd.DataFrame) -> int:
        """Skriv ALSI-rader til ``alsi_storage``. Returnerer antall rader.

        `df` må ha kolonnene i ``ALSI_STORAGE_COLS``. Idempotent på
        (country, gas_day_start) via INSERT OR REPLACE.
        """
        missing = [c for c in ALSI_STORAGE_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_alsi_storage: missing columns {missing}. "
                f"Required: {list(ALSI_STORAGE_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(ALSI_STORAGE_COLS)].copy()
        prepared["gas_day_start"] = pd.to_datetime(prepared["gas_day_start"]).dt.strftime(
            "%Y-%m-%d"
        )

        def _opt(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                str(row.country).lower(),
                row.gas_day_start,
                _opt(row.inventory_twh),
                _opt(row.dtmi_twh),
                _opt(row.full_pct),
                _opt(row.send_out_twh),
                _opt(row.dtrs_twh),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_ALSI_STORAGE} "
                f"(country, gas_day_start, inventory_twh, dtmi_twh, "
                f"full_pct, send_out_twh, dtrs_twh) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_alsi_storage(
        self,
        country: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner ALSI-rader for `country`, sortert ASC på gas_day_start.

        `country` er ISO-2 lowercase (``"de"``, ``"nl"``, ``"fr"``, ``"it"``,
        ``"es"`` etc.) eller ``"eu"`` for aggregat. Returnerer
        pd.DataFrame med ``gas_day_start`` som pd.Timestamp i en kolonne.

        Kaster `KeyError` hvis ingen rader finnes for `country`.
        """
        country_norm = country.lower()
        query = f"""
            SELECT * FROM {TABLE_ALSI_STORAGE}
            WHERE country = ?
            ORDER BY gas_day_start ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=(country_norm,))

        if df.empty:
            raise KeyError(f"No ALSI storage data for country={country_norm!r}")

        df["gas_day_start"] = pd.to_datetime(df["gas_day_start"])

        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_alsi_storage(self, country: str) -> bool:
        """Test-hjelper: sjekk om `country` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_ALSI_STORAGE} WHERE country = ? LIMIT 1",
                (country.lower(),),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # IIP REMIT supply-unavailability (sub-fase 12.10 follow-up Spor C, s136)
    # ------------------------------------------------------------------

    def append_iip_remit(self, df: pd.DataFrame) -> int:
        """Skriv IIP REMIT UMM-rader til ``iip_remit``. Returnerer antall rader.

        `df` må ha kolonnene i ``IIP_REMIT_COLS``. Idempotent på message_id
        via INSERT OR REPLACE — IIP-meldinger kan revideres.
        """
        missing = [c for c in IIP_REMIT_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_iip_remit: missing columns {missing}. "
                f"Required: {list(IIP_REMIT_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(IIP_REMIT_COLS)].copy()

        def _opt_str(v: object) -> str | None:
            if v is None:
                return None
            if isinstance(v, float) and pd.isna(v):
                return None
            s = str(v)
            return s if s and s.lower() != "nat" else None

        def _opt_float(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        # ISO-format på datetime-kolonner.
        for col in (
            "submitted_ts",
            "published_ts",
            "event_from_ts",
            "event_to_ts",
        ):
            prepared[col] = pd.to_datetime(prepared[col], errors="coerce")
            prepared[col] = prepared[col].dt.strftime("%Y-%m-%d %H:%M:%S")

        rows: Sequence[tuple] = [
            (
                str(row.message_id),
                _opt_str(row.submitted_ts),
                _opt_str(row.published_ts),
                _opt_str(row.event_from_ts),
                _opt_str(row.event_to_ts),
                _opt_str(row.status),
                _opt_str(row.message_type),
                _opt_str(row.unavailability_type),
                _opt_str(row.unavailability_reason),
                _opt_float(row.unavailable_capacity_gwhd),
                _opt_float(row.available_capacity_gwhd),
                _opt_float(row.technical_capacity_gwhd),
                _opt_str(row.balancing_zone_code),
                _opt_str(row.balancing_zone_name),
                _opt_str(row.direction),
                _opt_str(row.asset_code),
                _opt_str(row.asset_name),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_IIP_REMIT} "
                f"({', '.join(IIP_REMIT_COLS)}) "
                f"VALUES ({', '.join('?' * len(IIP_REMIT_COLS))})",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_iip_remit(
        self,
        *,
        balancing_zone_prefix: str | None = None,
        from_published_ts: str | None = None,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Returner IIP REMIT-rader sortert ASC på published_ts.

        Filterargumenter:
            balancing_zone_prefix: case-insensitive prefix-match mot
                balancing_zone_code (f.eks. ``"21YNL"`` for nederlandsk TTF).
            from_published_ts: ISO-streng; kun rader publisert ≥ denne.
            last_n: behold kun siste `n` rader (etter sortering).

        Returnerer tom DataFrame hvis ingen treff (i motsetning til AGSI/ALSI
        som kaster — IIP er event-basert med tomme periodevinduer som
        gyldig tilstand).
        """
        clauses: list[str] = []
        params: list[object] = []
        if balancing_zone_prefix:
            clauses.append("UPPER(balancing_zone_code) LIKE ?")
            params.append(f"{balancing_zone_prefix.upper()}%")
        if from_published_ts:
            clauses.append("published_ts >= ?")
            params.append(from_published_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM {TABLE_IIP_REMIT}
            {where}
            ORDER BY published_ts ASC
        """
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            return df

        for col in (
            "submitted_ts",
            "published_ts",
            "event_from_ts",
            "event_to_ts",
        ):
            df[col] = pd.to_datetime(df[col], errors="coerce")

        if last_n is not None:
            df = df.tail(last_n).reset_index(drop=True)
        return df

    def has_iip_remit(self) -> bool:
        """Test-hjelper: sjekk om iip_remit har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(f"SELECT 1 FROM {TABLE_IIP_REMIT} LIMIT 1")
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # AAII Sentiment Survey (sub-fase 12.7 D2 A12, session 131)
    # ------------------------------------------------------------------

    def append_aaii_sentiment(self, df: pd.DataFrame) -> int:
        """Skriv AAII-rader til ``aaii_sentiment``. Idempotent på date."""
        # Sub-fase 12.10 Bunke 1 Bug-1: auto-utled released_at via release_calendar
        # hvis ikke gitt — eldre fetcher-kallere trenger ikke oppdateres.
        if "released_at" not in df.columns:
            df = df.copy()
            df["released_at"] = pd.to_datetime(df["date"]).apply(lambda d: aaii_released_at_iso(d))

        missing = [c for c in AAII_SENTIMENT_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_aaii_sentiment: missing columns {missing}. "
                f"Required: {list(AAII_SENTIMENT_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(AAII_SENTIMENT_COLS)].copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        def _opt(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                row.date,
                _opt(row.bullish_pct),
                _opt(row.neutral_pct),
                _opt(row.bearish_pct),
                _opt(row.bull_bear_spread),
                row.released_at,
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_AAII_SENTIMENT} "
                f"(date, bullish_pct, neutral_pct, bearish_pct, bull_bear_spread, released_at) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_aaii_sentiment(self, last_n: int | None = None) -> pd.DataFrame:
        """Returner AAII-rader sortert ASC på date.

        Kaster ``KeyError`` hvis tabellen er tom.
        """
        query = f"SELECT * FROM {TABLE_AAII_SENTIMENT} ORDER BY date ASC"
        with self._connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            raise KeyError("No AAII sentiment data")

        df["date"] = pd.to_datetime(df["date"])
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def has_aaii_sentiment(self) -> bool:
        """Test-hjelper: sjekk om tabellen har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(f"SELECT 1 FROM {TABLE_AAII_SENTIMENT} LIMIT 1")
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # ETF holdings (sub-fase 12.7 D2 A5/A6, session 132)
    # ------------------------------------------------------------------

    def append_etf_holdings(self, df: pd.DataFrame) -> int:
        """Skriv ETF-holdings-rader til ``etf_holdings``. Returnerer antall.

        `df` må ha kolonnene i ``ETF_HOLDINGS_COLS``. Idempotent på
        (ticker, date) via INSERT OR REPLACE.
        """
        missing = [c for c in ETF_HOLDINGS_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_etf_holdings: missing columns {missing}. "
                f"Required: {list(ETF_HOLDINGS_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(ETF_HOLDINGS_COLS)].copy()
        prepared["date"] = pd.to_datetime(prepared["date"]).dt.strftime("%Y-%m-%d")

        def _opt(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                str(row.ticker).lower(),
                row.date,
                _opt(row.tonnes_in_trust),
                _opt(row.ounces_in_trust),
                _opt(row.shares_outstanding),
                _opt(row.nav_per_share),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_ETF_HOLDINGS} "
                f"(ticker, date, tonnes_in_trust, ounces_in_trust, "
                f"shares_outstanding, nav_per_share) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_etf_holdings(
        self,
        ticker: str,
        from_date: str | date | None = None,
        to_date: str | date | None = None,
    ) -> pd.DataFrame:
        """Returner ETF-holdings for `ticker`, sortert ASC på date.

        Kaster ``KeyError`` hvis ingen rader finnes for `ticker`.
        """
        ticker_norm = ticker.lower().strip()
        clauses = ["ticker = ?"]
        params: list[Any] = [ticker_norm]
        if from_date is not None:
            clauses.append("date >= ?")
            params.append(str(from_date))
        if to_date is not None:
            clauses.append("date <= ?")
            params.append(str(to_date))

        query = (
            f"SELECT * FROM {TABLE_ETF_HOLDINGS} WHERE {' AND '.join(clauses)} ORDER BY date ASC"
        )
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            raise KeyError(f"No ETF holdings for ticker={ticker_norm!r}")

        df["date"] = pd.to_datetime(df["date"])
        return df

    def has_etf_holdings(self, ticker: str) -> bool:
        """Test-hjelper: sjekk om `ticker` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_ETF_HOLDINGS} WHERE ticker = ? LIMIT 1",
                (ticker.lower().strip(),),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # FAS Export Sales (sub-fase 12.7 D2 A3, session 133)
    # ------------------------------------------------------------------

    def append_fas_esr(self, df: pd.DataFrame) -> int:
        """Skriv FAS ESR-rader. Idempotent på (commodity_code, country_code,
        market_year, week_ending_date) via INSERT OR REPLACE."""
        missing = [c for c in FAS_ESR_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_fas_esr: missing columns {missing}. "
                f"Required: {list(FAS_ESR_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(FAS_ESR_COLS)].copy()
        prepared["week_ending_date"] = pd.to_datetime(prepared["week_ending_date"]).dt.strftime(
            "%Y-%m-%d"
        )

        def _opt_float(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        def _opt_int(v: object) -> int | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return int(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                int(row.commodity_code),
                int(row.country_code),
                int(row.market_year),
                row.week_ending_date,
                _opt_float(row.weekly_exports),
                _opt_float(row.accumulated_exports),
                _opt_float(row.outstanding_sales),
                _opt_float(row.gross_new_sales),
                _opt_float(row.current_my_net_sales),
                _opt_float(row.current_my_total_commitment),
                _opt_float(row.next_my_outstanding_sales),
                _opt_float(row.next_my_net_sales),
                _opt_int(row.unit_id),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_FAS_ESR} "
                f"(commodity_code, country_code, market_year, week_ending_date, "
                f"weekly_exports, accumulated_exports, outstanding_sales, "
                f"gross_new_sales, current_my_net_sales, current_my_total_commitment, "
                f"next_my_outstanding_sales, next_my_net_sales, unit_id) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_fas_esr(
        self,
        commodity_code: int,
        *,
        country_code: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Returner FAS ESR-rader for `commodity_code`, sortert ASC på
        week_ending_date. Aggregerer på tvers av countries (sum) hvis
        `country_code` er None.

        Bruker SQL-aggregat når aggregating — driver-laget får én rad per
        (market_year, week_ending_date) med summen av weekly_exports +
        accumulated_exports + outstanding_sales på tvers av alle countries.
        """
        params: list[object] = [commodity_code]
        clauses = ["commodity_code = ?"]
        if country_code is not None:
            clauses.append("country_code = ?")
            params.append(country_code)
        if from_date is not None:
            clauses.append("week_ending_date >= ?")
            params.append(from_date)
        if to_date is not None:
            clauses.append("week_ending_date <= ?")
            params.append(to_date)
        where = " AND ".join(clauses)

        if country_code is None:
            query = f"""
                SELECT
                    commodity_code,
                    market_year,
                    week_ending_date,
                    SUM(weekly_exports)              AS weekly_exports,
                    SUM(accumulated_exports)         AS accumulated_exports,
                    SUM(outstanding_sales)           AS outstanding_sales,
                    SUM(gross_new_sales)             AS gross_new_sales,
                    SUM(current_my_net_sales)        AS current_my_net_sales,
                    SUM(current_my_total_commitment) AS current_my_total_commitment,
                    SUM(next_my_outstanding_sales)   AS next_my_outstanding_sales,
                    SUM(next_my_net_sales)           AS next_my_net_sales
                FROM {TABLE_FAS_ESR}
                WHERE {where}
                GROUP BY commodity_code, market_year, week_ending_date
                ORDER BY week_ending_date ASC
            """
        else:
            query = f"SELECT * FROM {TABLE_FAS_ESR} WHERE {where} ORDER BY week_ending_date ASC"

        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            raise KeyError(
                f"No FAS ESR data for commodity_code={commodity_code}"
                + (f", country_code={country_code}" if country_code is not None else "")
            )

        df["week_ending_date"] = pd.to_datetime(df["week_ending_date"])
        return df

    def has_fas_esr(self, commodity_code: int) -> bool:
        """Test-hjelper: sjekk om `commodity_code` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_FAS_ESR} WHERE commodity_code = ? LIMIT 1",
                (int(commodity_code),),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # US Drought Monitor (sub-fase 12.7 D2 A9, session 133)
    # ------------------------------------------------------------------

    def append_drought_monitor(self, df: pd.DataFrame) -> int:
        """Skriv USDM-rader. Idempotent på (map_date, aoi)."""
        missing = [c for c in DROUGHT_MONITOR_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_drought_monitor: missing columns {missing}. "
                f"Required: {list(DROUGHT_MONITOR_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(DROUGHT_MONITOR_COLS)].copy()
        prepared["map_date"] = pd.to_datetime(prepared["map_date"]).dt.strftime("%Y-%m-%d")
        for col in ("valid_start", "valid_end"):
            prepared[col] = prepared[col].apply(
                lambda v: pd.to_datetime(v).strftime("%Y-%m-%d") if pd.notna(v) else None
            )

        def _opt(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        rows: Sequence[tuple] = [
            (
                row.map_date,
                str(row.aoi).lower(),
                _opt(row.none_pct),
                _opt(row.d0_pct),
                _opt(row.d1_pct),
                _opt(row.d2_pct),
                _opt(row.d3_pct),
                _opt(row.d4_pct),
                row.valid_start,
                row.valid_end,
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_DROUGHT_MONITOR} "
                f"(map_date, aoi, none_pct, d0_pct, d1_pct, d2_pct, d3_pct, d4_pct, "
                f"valid_start, valid_end) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_drought_monitor(self, aoi: str = "us") -> pd.DataFrame:
        """Returner USDM-rader for `aoi`, sortert ASC på map_date.

        Kaster `KeyError` hvis ingen rader.
        """
        aoi_norm = aoi.lower().strip()
        with self._connect() as conn:
            df = pd.read_sql(
                f"SELECT * FROM {TABLE_DROUGHT_MONITOR} WHERE aoi = ? ORDER BY map_date ASC",
                conn,
                params=(aoi_norm,),
            )
        if df.empty:
            raise KeyError(f"No drought_monitor data for aoi={aoi_norm!r}")
        df["map_date"] = pd.to_datetime(df["map_date"])
        return df

    def has_drought_monitor(self, aoi: str = "us") -> bool:
        """Test-hjelper: sjekk om `aoi` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_DROUGHT_MONITOR} WHERE aoi = ? LIMIT 1",
                (aoi.lower().strip(),),
            )
            return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Cecafé Brasil kaffe-eksport (sub-fase 12.7 D3 A10, session 135)
    # ------------------------------------------------------------------

    def append_cecafe_exports(self, df: pd.DataFrame) -> int:
        """Skriv Cecafé-eksport-rader til ``cecafe_exports``. Idempotent på
        (month, coffee_type) via INSERT OR REPLACE. Returnerer antall rader."""
        missing = [c for c in CECAFE_EXPORTS_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"append_cecafe_exports: missing columns {missing}. "
                f"Required: {list(CECAFE_EXPORTS_COLS)}. Got: {sorted(df.columns)}"
            )

        prepared = df[list(CECAFE_EXPORTS_COLS)].copy()
        prepared["month"] = pd.to_datetime(prepared["month"]).dt.strftime("%Y-%m-%d")

        def _opt_int(v: object) -> int | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return int(v)  # type: ignore[arg-type]

        def _opt_float(v: object) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)  # type: ignore[arg-type]

        def _opt_str(v: object) -> str | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            s = str(v).strip()
            return s if s else None

        rows: Sequence[tuple] = [
            (
                row.month,
                str(row.coffee_type).lower().strip(),
                _opt_int(row.volume_60kg_bags),
                _opt_float(row.fob_value_usd),
                _opt_str(row.source_pdf),
            )
            for row in prepared.itertuples(index=False)
        ]

        with self._connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {TABLE_CECAFE_EXPORTS} "
                f"(month, coffee_type, volume_60kg_bags, fob_value_usd, source_pdf) "
                f"VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        return len(rows)

    def get_cecafe_exports(
        self,
        coffee_type: str = "sum",
        from_month: str | date | None = None,
        to_month: str | date | None = None,
    ) -> pd.DataFrame:
        """Returner Cecafé-rader for `coffee_type`, sortert ASC på month.

        Default `coffee_type='sum'` (Cecafés total — primær for driver).
        Kaster ``KeyError`` hvis ingen rader.
        """
        type_norm = coffee_type.lower().strip()
        clauses = ["coffee_type = ?"]
        params: list[Any] = [type_norm]
        if from_month is not None:
            clauses.append("month >= ?")
            params.append(str(from_month))
        if to_month is not None:
            clauses.append("month <= ?")
            params.append(str(to_month))

        query = (
            f"SELECT * FROM {TABLE_CECAFE_EXPORTS} WHERE {' AND '.join(clauses)} ORDER BY month ASC"
        )
        with self._connect() as conn:
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            raise KeyError(f"No Cecafé exports for coffee_type={type_norm!r}")

        df["month"] = pd.to_datetime(df["month"])
        return df

    def has_cecafe_exports(self, coffee_type: str = "sum") -> bool:
        """Test-hjelper: sjekk om `coffee_type` har minst én rad."""
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT 1 FROM {TABLE_CECAFE_EXPORTS} WHERE coffee_type = ? LIMIT 1",
                (coffee_type.lower().strip(),),
            )
            return cursor.fetchone() is not None

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
