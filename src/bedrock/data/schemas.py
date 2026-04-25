"""Data-schemaer for DataStore.

Pydantic-modeller for validering + SQL-tabell-DDL for lagring. Bedrock bruker
SQLite som storage-backend (se ADR-002); DDL-konstantene under brukes av
`DataStore._init_schema()` når SQLite-fila initialiseres.

Fase 2 session 6: `PriceBar` / `prices`-tabell.
Fase 2 session 7: `CotDisaggregatedRow`/`CotLegacyRow` — to separate tabeller
pga ulik kolonnestruktur i CFTC disaggregated (managed money + other +
commercial + non-reportable) vs legacy (non-commercial + commercial +
non-reportable). NULL-sprawl unngås ved å holde dem separate.
Fase 2 session 8: `FredSeriesRow` (fundamentals, én verdi per (series_id, date))
og `WeatherDailyRow` (region × daglig observasjon: tmax/tmin/precip/gdd).
Senere sessions: `TradeRow`.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# PriceBar — én OHLCV-bar for (instrument, tf, ts)
# ---------------------------------------------------------------------------


class PriceBar(BaseModel):
    """Én pris-bar. `close` er påkrevd; OHLV er valgfritt (noen kilder gir
    kun close)."""

    ts: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float | None = Field(default=None, ge=0.0)

    model_config = ConfigDict(extra="forbid")


TABLE_PRICES = "prices"
"""Tabellnavn i SQLite-db."""

DDL_PRICES = f"""
CREATE TABLE IF NOT EXISTS {TABLE_PRICES} (
    instrument TEXT    NOT NULL,
    tf         TEXT    NOT NULL,
    ts         TEXT    NOT NULL,
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL    NOT NULL,
    volume     REAL,
    PRIMARY KEY (instrument, tf, ts)
)
"""
"""DDL for prices-tabellen.

- `ts` lagres som ISO-8601 TEXT (SQLite har ikke native timestamp). pandas
  parser til pd.Timestamp ved lesing.
- Primary key (instrument, tf, ts) gir dedupe på nye appends via
  `INSERT OR REPLACE` uten egen index-opprettelse.
"""


# ---------------------------------------------------------------------------
# COT Disaggregated (CFTC, 2010-present)
# ---------------------------------------------------------------------------


class CotDisaggregatedRow(BaseModel):
    """En rad fra CFTCs disaggregated COT-rapport.

    Kolonner følger CFTC-kategorier:
    - `mm_*`: Managed Money (hedge funds, CTA-er)
    - `other_*`: Other Reportable (firma-spekulanter utenfor MM)
    - `comm_*`: Producer/Merchant/Processor/User (commercials)
    - `nonrep_*`: Non-Reportable (små traders)

    `contract` er CFTC's navn (f.eks. "GOLD - COMMODITY EXCHANGE INC."),
    ikke Bedrocks instrument-navn. Mapping skjer i driver-laget.
    """

    report_date: date
    contract: str

    mm_long: int = Field(ge=0)
    mm_short: int = Field(ge=0)
    other_long: int = Field(ge=0)
    other_short: int = Field(ge=0)
    comm_long: int = Field(ge=0)
    comm_short: int = Field(ge=0)
    nonrep_long: int = Field(ge=0)
    nonrep_short: int = Field(ge=0)
    open_interest: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


TABLE_COT_DISAGGREGATED = "cot_disaggregated"

DDL_COT_DISAGGREGATED = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COT_DISAGGREGATED} (
    report_date    TEXT    NOT NULL,
    contract       TEXT    NOT NULL,
    mm_long        INTEGER NOT NULL,
    mm_short       INTEGER NOT NULL,
    other_long     INTEGER NOT NULL,
    other_short    INTEGER NOT NULL,
    comm_long      INTEGER NOT NULL,
    comm_short     INTEGER NOT NULL,
    nonrep_long    INTEGER NOT NULL,
    nonrep_short   INTEGER NOT NULL,
    open_interest  INTEGER NOT NULL,
    PRIMARY KEY (report_date, contract)
)
"""
"""DDL for cot_disaggregated-tabellen.

- `report_date` lagres som ISO YYYY-MM-DD TEXT.
- Primary key (report_date, contract) gir dedupe ved re-runs av fetch.
"""


# ---------------------------------------------------------------------------
# COT Legacy (CFTC, 2006-present)
# ---------------------------------------------------------------------------


class CotLegacyRow(BaseModel):
    """En rad fra CFTCs legacy COT-rapport (com/noncom/nonrep-oppdeling).

    Kolonner:
    - `noncomm_*`: Non-Commercial (store spekulanter, inkl. hedge funds)
    - `comm_*`: Commercial (producers/merchants)
    - `nonrep_*`: Non-Reportable

    Brukes for kontrakter CFTC ikke har disaggregated-versjon for, og for
    historikk før 2010.
    """

    report_date: date
    contract: str

    noncomm_long: int = Field(ge=0)
    noncomm_short: int = Field(ge=0)
    comm_long: int = Field(ge=0)
    comm_short: int = Field(ge=0)
    nonrep_long: int = Field(ge=0)
    nonrep_short: int = Field(ge=0)
    open_interest: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


TABLE_COT_LEGACY = "cot_legacy"

DDL_COT_LEGACY = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COT_LEGACY} (
    report_date    TEXT    NOT NULL,
    contract       TEXT    NOT NULL,
    noncomm_long   INTEGER NOT NULL,
    noncomm_short  INTEGER NOT NULL,
    comm_long      INTEGER NOT NULL,
    comm_short     INTEGER NOT NULL,
    nonrep_long    INTEGER NOT NULL,
    nonrep_short   INTEGER NOT NULL,
    open_interest  INTEGER NOT NULL,
    PRIMARY KEY (report_date, contract)
)
"""


# ---------------------------------------------------------------------------
# Konstanter / oppslag
# ---------------------------------------------------------------------------

CotReportType = str  # Literal["disaggregated", "legacy"] — definert i store.py

COT_DISAGGREGATED_COLS: tuple[str, ...] = (
    "report_date",
    "contract",
    "mm_long",
    "mm_short",
    "other_long",
    "other_short",
    "comm_long",
    "comm_short",
    "nonrep_long",
    "nonrep_short",
    "open_interest",
)
"""Forventet kolonne-rekkefølge for append_cot_disaggregated."""

COT_LEGACY_COLS: tuple[str, ...] = (
    "report_date",
    "contract",
    "noncomm_long",
    "noncomm_short",
    "comm_long",
    "comm_short",
    "nonrep_long",
    "nonrep_short",
    "open_interest",
)
"""Forventet kolonne-rekkefølge for append_cot_legacy."""


# ---------------------------------------------------------------------------
# Fundamentals (FRED-stil: series_id × date × value)
# ---------------------------------------------------------------------------


class FredSeriesRow(BaseModel):
    """En observasjon i en FRED-serie.

    `series_id` er FRED's kode (f.eks. "DGS10" for 10Y treasury yield,
    "DXY" for dollar-indeks). `value` kan være None — FRED rapporterer
    ofte manglende observasjoner (helgedager, ikke-rapporterte perioder).
    """

    series_id: str
    date: date
    value: float | None = None

    model_config = ConfigDict(extra="forbid")


TABLE_FUNDAMENTALS = "fundamentals"

DDL_FUNDAMENTALS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_FUNDAMENTALS} (
    series_id  TEXT NOT NULL,
    date       TEXT NOT NULL,
    value      REAL,
    PRIMARY KEY (series_id, date)
)
"""
"""DDL for fundamentals-tabellen.

`value` er NULL-able (FRED-serier har ofte missing observations).
`date` lagres som ISO YYYY-MM-DD TEXT; parses til pd.Timestamp ved lesing.
PK (series_id, date) gir dedupe.
"""

FUNDAMENTALS_COLS: tuple[str, ...] = ("series_id", "date", "value")


# ---------------------------------------------------------------------------
# Weather (daglige observasjoner per region)
# ---------------------------------------------------------------------------


class WeatherDailyRow(BaseModel):
    """Daglig vær-observasjon per region.

    `region` er et logisk navn (f.eks. "us_cornbelt", "brazil_mato_grosso")
    — ikke en GPS-koordinat. Aggregering fra rådata til region-nivå gjøres
    i fetch-laget, ikke her.

    Alle målinger er valgfrie; noen kilder rapporterer bare tmax/tmin, andre
    også nedbør og GDD (growing-degree-days).
    """

    region: str
    date: date
    tmax: float | None = None  # °C
    tmin: float | None = None  # °C
    precip: float | None = Field(default=None, ge=0.0)  # mm
    gdd: float | None = Field(default=None, ge=0.0)  # growing-degree-days

    model_config = ConfigDict(extra="forbid")


TABLE_WEATHER = "weather"

DDL_WEATHER = f"""
CREATE TABLE IF NOT EXISTS {TABLE_WEATHER} (
    region  TEXT NOT NULL,
    date    TEXT NOT NULL,
    tmax    REAL,
    tmin    REAL,
    precip  REAL,
    gdd     REAL,
    PRIMARY KEY (region, date)
)
"""

WEATHER_COLS: tuple[str, ...] = ("region", "date", "tmax", "tmin", "precip", "gdd")
