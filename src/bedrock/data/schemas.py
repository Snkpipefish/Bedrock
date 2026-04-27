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
Fase 10 session 57 (ADR-005): `WeatherMonthlyRow` (region × måned, pre-aggregert
fra agri_history) og `AnalogOutcomeRow` (instrument × ref_date × horizon,
forward-return-utfall for K-NN).
Senere sessions: `TradeRow`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


# ---------------------------------------------------------------------------
# WeatherMonthlyRow — pre-aggregert månedlig vær per region (ADR-005)
# ---------------------------------------------------------------------------


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
"""Validerer 'YYYY-MM'-format (ikke 'YYYY-1' eller '2026-13')."""


class WeatherMonthlyRow(BaseModel):
    """Månedlig vær-aggregat per region. Pre-beregnede verdier (hot_days,
    water_bal etc.) som ikke kan utledes fra `WeatherDailyRow` alene uten
    ekstra parametre. Migreres fra `~/cot-explorer/data/agri_history/`
    i Fase 10 session 58.

    `month` er 'YYYY-MM' (ISO month, ikke datetime). Alle målinger er
    valgfrie — kilder kan rapportere ulikt subset.
    """

    region: str
    month: str
    temp_mean: float | None = None  # °C
    temp_max: float | None = None  # °C
    precip_mm: float | None = Field(default=None, ge=0.0)
    et0_mm: float | None = Field(default=None, ge=0.0)
    hot_days: int | None = Field(default=None, ge=0)
    dry_days: int | None = Field(default=None, ge=0)
    wet_days: int | None = Field(default=None, ge=0)
    water_bal: float | None = None  # nedbør - et0 (kan være negativ)

    model_config = ConfigDict(extra="forbid")

    @field_validator("month")
    @classmethod
    def _check_month(cls, v: str) -> str:
        if not _MONTH_RE.match(v):
            raise ValueError(f"month must be 'YYYY-MM', got: {v!r}")
        return v


TABLE_WEATHER_MONTHLY = "weather_monthly"

DDL_WEATHER_MONTHLY = f"""
CREATE TABLE IF NOT EXISTS {TABLE_WEATHER_MONTHLY} (
    region    TEXT NOT NULL,
    month     TEXT NOT NULL,
    temp_mean REAL,
    temp_max  REAL,
    precip_mm REAL,
    et0_mm    REAL,
    hot_days  INTEGER,
    dry_days  INTEGER,
    wet_days  INTEGER,
    water_bal REAL,
    PRIMARY KEY (region, month)
)
"""

WEATHER_MONTHLY_COLS: tuple[str, ...] = (
    "region",
    "month",
    "temp_mean",
    "temp_max",
    "precip_mm",
    "et0_mm",
    "hot_days",
    "dry_days",
    "wet_days",
    "water_bal",
)


# ---------------------------------------------------------------------------
# AnalogOutcomeRow — pre-beregnede forward returns for K-NN (ADR-005)
# ---------------------------------------------------------------------------


class AnalogOutcomeRow(BaseModel):
    """Pre-beregnet forward-utfall for én historisk ref-dato.

    Lagrer rå return (i %, ikke binær hit). Hit-terskel er driver-config
    og anvendes on-the-fly — slik at vi kan justere terskel uten å re-
    backfille tabellen.

    `max_drawdown_pct` er valgfri i skjemaet (NULL hvis beregneren ikke
    kjørte med high-resolution-data), men inkluderes by default per
    ADR-005 — pre-beregning er gratis i samme pass som forward_return.
    """

    instrument: str
    ref_date: date
    horizon_days: int = Field(gt=0)
    forward_return_pct: float
    max_drawdown_pct: float | None = None

    model_config = ConfigDict(extra="forbid")


TABLE_ANALOG_OUTCOMES = "analog_outcomes"

DDL_ANALOG_OUTCOMES = f"""
CREATE TABLE IF NOT EXISTS {TABLE_ANALOG_OUTCOMES} (
    instrument         TEXT    NOT NULL,
    ref_date           TEXT    NOT NULL,
    horizon_days       INTEGER NOT NULL,
    forward_return_pct REAL    NOT NULL,
    max_drawdown_pct   REAL,
    PRIMARY KEY (instrument, ref_date, horizon_days)
)
"""

ANALOG_OUTCOMES_COLS: tuple[str, ...] = (
    "instrument",
    "ref_date",
    "horizon_days",
    "forward_return_pct",
    "max_drawdown_pct",
)


# ---------------------------------------------------------------------------
# PLAN § 7.3 datakilder (session 83+)
# ---------------------------------------------------------------------------

# USDA NASS Crop Progress — ukentlige %-verdier for planted/silking/harvested
# per crop og state. Auto-fetcher krever NASS QuickStats API-key
# (BEDROCK_NASS_API_KEY). Manuell CSV-fallback i data/manual/crop_progress.csv.
TABLE_CROP_PROGRESS = "crop_progress"

DDL_CROP_PROGRESS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_CROP_PROGRESS} (
    week_ending  TEXT    NOT NULL,    -- ISO date (søndag som regel)
    commodity    TEXT    NOT NULL,    -- "CORN", "SOYBEANS", "COTTON", "WHEAT"
    state        TEXT    NOT NULL,    -- "US TOTAL" eller state-kode
    metric       TEXT    NOT NULL,    -- "PLANTED", "SILKING", "HARVESTED", "GOOD_EXCELLENT"
    value_pct    REAL    NOT NULL,    -- 0..100
    PRIMARY KEY (week_ending, commodity, state, metric)
)
"""

CROP_PROGRESS_COLS: tuple[str, ...] = (
    "week_ending",
    "commodity",
    "state",
    "metric",
    "value_pct",
)


# WASDE — månedlige USDA estimater (ending stocks, yield, S2U).
# Auto-fetcher leser fra USDA's konsoliderte CSV (URL i fetcher).
# Manuell CSV-fallback i data/manual/wasde.csv.
TABLE_WASDE = "wasde"

DDL_WASDE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_WASDE} (
    report_date   TEXT    NOT NULL,    -- WASDE rapport-dato (publication date)
    marketing_year TEXT   NOT NULL,    -- "2025/26", "2024/25"
    region        TEXT    NOT NULL,    -- "US", "WORLD"
    commodity     TEXT    NOT NULL,    -- "CORN", "WHEAT", "SOYBEANS", "COTTON", "SUGAR"
    metric        TEXT    NOT NULL,    -- "ENDING_STOCKS", "PRODUCTION", "YIELD", "S2U"
    value         REAL    NOT NULL,    -- enhet varierer per metric (mill bu, %, bu/acre)
    unit          TEXT    NOT NULL,    -- "MIL_BU", "PCT", "BU_ACRE", "MIL_TONS"
    PRIMARY KEY (report_date, marketing_year, region, commodity, metric)
)
"""

WASDE_COLS: tuple[str, ...] = (
    "report_date",
    "marketing_year",
    "region",
    "commodity",
    "metric",
    "value",
    "unit",
)


# Eksport-policy events — manuell kuratert kalender for India/Indonesia/
# Ivory Coast og andre jurisdikasjoner som påvirker globale agri-priser
# via eksport-restriksjoner, kvoter, eller forbud.
# Ren manuell CSV — data/manual/export_events.csv.
TABLE_EXPORT_EVENTS = "export_events"

DDL_EXPORT_EVENTS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_EXPORT_EVENTS} (
    event_date   TEXT    NOT NULL,    -- ISO date for hendelsen
    country      TEXT    NOT NULL,    -- "INDIA", "INDONESIA", "IVORY COAST"
    commodity    TEXT    NOT NULL,    -- "RICE", "PALM OIL", "COCOA", "SUGAR" etc
    event_type   TEXT    NOT NULL,    -- "EXPORT_BAN", "QUOTA", "TARIFF", "SUBSIDY_REMOVED"
    severity     INTEGER NOT NULL,    -- 1-5: 1=mild, 5=major-shock
    bull_bear    TEXT    NOT NULL,    -- "BULL", "BEAR" (for commodity-prisen)
    description  TEXT,
    source_url   TEXT,
    PRIMARY KEY (event_date, country, commodity, event_type)
)
"""

EXPORT_EVENTS_COLS: tuple[str, ...] = (
    "event_date",
    "country",
    "commodity",
    "event_type",
    "severity",
    "bull_bear",
    "description",
    "source_url",
)


# Disease/pest-varsler — coffee rust, wheat stripe rust, locust outbreaks etc.
# Manuell CSV-driven (eksterne services som PestMon/CABI er paid).
# data/manual/disease_alerts.csv.
TABLE_DISEASE_ALERTS = "disease_alerts"

DDL_DISEASE_ALERTS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_DISEASE_ALERTS} (
    alert_date   TEXT    NOT NULL,
    region       TEXT    NOT NULL,    -- "BRAZIL", "VIETNAM", "AUSTRALIA" etc
    commodity    TEXT    NOT NULL,
    pathogen     TEXT    NOT NULL,    -- "COFFEE_RUST", "STRIPE_RUST", "LOCUST"
    severity     INTEGER NOT NULL,    -- 1-5
    yield_impact_pct REAL,            -- estimert yield-tap (kan være null)
    description  TEXT,
    source_url   TEXT,
    PRIMARY KEY (alert_date, region, commodity, pathogen)
)
"""

DISEASE_ALERTS_COLS: tuple[str, ...] = (
    "alert_date",
    "region",
    "commodity",
    "pathogen",
    "severity",
    "yield_impact_pct",
    "description",
    "source_url",
)


# Baltic Dry Index — global shipping/freight indikator. Påvirker
# eksport-cost for grains. Auto-fetcher prøver Yahoo BDI-ticker;
# manuell CSV-fallback (paid feeds som Trading Economics gir bedre data).
TABLE_BDI = "bdi"

DDL_BDI = f"""
CREATE TABLE IF NOT EXISTS {TABLE_BDI} (
    date   TEXT NOT NULL PRIMARY KEY,
    value  REAL NOT NULL,
    source TEXT NOT NULL    -- "YAHOO", "MANUAL", "TRADINGECONOMICS"
)
"""

BDI_COLS: tuple[str, ...] = ("date", "value", "source")


# IGC (International Grains Council) — månedlig Grain Market Report
# med globalt totaltilbud/etterspørsel (production, trade, ending stocks)
# for korn (wheat, maize, rice). Paid PDF-subscription primært;
# manuell CSV-løsning her.
TABLE_IGC = "igc"

DDL_IGC = f"""
CREATE TABLE IF NOT EXISTS {TABLE_IGC} (
    report_date    TEXT    NOT NULL,    -- IGC report publication date
    marketing_year TEXT    NOT NULL,    -- "2025/26"
    grain          TEXT    NOT NULL,    -- "WHEAT", "MAIZE", "RICE", "TOTAL_GRAINS"
    metric         TEXT    NOT NULL,    -- "PRODUCTION", "CONSUMPTION", "ENDING_STOCKS", "TRADE"
    value_mil_tons REAL    NOT NULL,    -- IGC bruker millioner tonn
    PRIMARY KEY (report_date, marketing_year, grain, metric)
)
"""

IGC_COLS: tuple[str, ...] = (
    "report_date",
    "marketing_year",
    "grain",
    "metric",
    "value_mil_tons",
)


# Økonomisk kalender (Forex Factory via faireconomy.media JSON).
# Sub-fase 12.5+ session 105 (ADR-007/008) — første cot-explorer-port.
# Lagrer scheduled high/medium-impact events fra Fed/ECB/BoE/BoJ/RBA/RBNZ
# m.fl. Brukes av `event_distance`-driveren i risk-/cross-familier på
# alle 22 instrumenter.
TABLE_ECON_EVENTS = "econ_events"

DDL_ECON_EVENTS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_ECON_EVENTS} (
    event_ts     TEXT    NOT NULL,    -- ISO-8601 UTC timestamp
    country      TEXT    NOT NULL,    -- "USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"
    title        TEXT    NOT NULL,    -- f.eks. "FOMC Statement", "CPI m/m"
    impact       TEXT    NOT NULL,    -- "High", "Medium", "Low"
    forecast     TEXT,                -- analytiker-forventning (kan være tom)
    previous     TEXT,                -- forrige rapportverdi (kan være tom)
    fetched_at   TEXT    NOT NULL,    -- når raden ble hentet (ISO UTC)
    PRIMARY KEY (event_ts, country, title)
)
"""

ECON_EVENTS_COLS: tuple[str, ...] = (
    "event_ts",
    "country",
    "title",
    "impact",
    "forecast",
    "previous",
    "fetched_at",
)


class EconomicEvent(BaseModel):
    """Én rad i econ_events-tabellen.

    `event_ts` er event-tidspunkt i UTC. `fetched_at` er når raden ble
    hentet (sub-fase 12.5+ session 105). PK på (event_ts, country, title)
    er rimelig unik for kalender-events.
    """

    event_ts: datetime
    country: str = Field(min_length=2, max_length=4)
    title: str = Field(min_length=1)
    impact: str
    forecast: str | None = None
    previous: str | None = None
    fetched_at: datetime

    model_config = ConfigDict(extra="forbid")

    @field_validator("impact")
    @classmethod
    def _impact_valid(cls, v: str) -> str:
        if v not in {"High", "Medium", "Low"}:
            raise ValueError(f"impact must be High/Medium/Low, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# ICE Futures Europe COT (sub-fase 12.5+ session 106)
# ---------------------------------------------------------------------------
# Parallell-tabell til `cot_disaggregated` for ICE-listede kontrakter
# (Brent Crude, Low Sulphur Gasoil, TTF Natural Gas). ICE publiserer
# fredag 18:30 London = 19:30 Oslo for tirsdag-posisjoner.
#
# ICE-rapporten leveres i CFTC disaggregated-format (samme kolonnenavn:
# M_Money_Positions_Long_All, Other_Reportable, PMPU, NonReportable),
# slik at schema-strukturen mirrorer cot_disaggregated. MiFID II-mapping
# (info; ikke separate kolonner):
# - mm_long/short      ≈ Investment Funds (Managed Money)
# - other_long/short   ≈ Investment Firms / andre Other Reportable
# - comm_long/short    ≈ Commercial Undertakings (PMPU)
# - nonrep_long/short  ≈ Non-Reportable
#
# Egen tabell (ikke gjenbruk cot_disaggregated) fordi:
# 1. Datakilde og provenance er forskjellig (ICE vs CFTC).
# 2. Contract-strenger er forskjellige (f.eks. "ice brent crude" vs
#    "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE").
# 3. Driver-laget kan velge kilde uten å filtrere.

TABLE_COT_ICE = "cot_ice"

DDL_COT_ICE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COT_ICE} (
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

COT_ICE_COLS: tuple[str, ...] = (
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


class CotIceRow(BaseModel):
    """En rad fra ICE Futures Europe COT-rapport.

    Schema mirrorer ``CotDisaggregatedRow`` (samme CFTC-disaggregated-
    format). MiFID II-kategorier mappes via dokumentasjon, ikke via
    separate kolonner — se modul-docstring for cot_ice-tabellen.

    `contract` er ICE-canonical (f.eks. ``"ice brent crude"``,
    ``"ice gasoil"``, ``"ice ttf gas"``), ikke Bedrocks instrument-id.
    Mapping skjer i driver-laget.
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


# ---------------------------------------------------------------------------
# EIA Open Data — petroleum + natural gas weekly inventories
# (sub-fase 12.5+ session 107)
# ---------------------------------------------------------------------------
# US energy department's open data API v2 dekker bl.a.:
# - Weekly petroleum stocks (US Crude Oil, Gasoline, Distillate, etc.)
# - Weekly natural gas storage (Lower 48, regions)
#
# Skjema: én rad per (series_id, date). EIA series_ids er stabile
# identifikatorer (f.eks. WCESTUS1 = US Ending Stocks excl. SPR Crude).
# `units` lagres for å fange fysisk dimensjon — pil bekreftet at
# samme series alltid gir samme units, men vi lagrer per rad for å
# tåle EIA-omklassifisering uten data-tap.
#
# Bruk: `eia_stock_change`-driver i macro-familien for energy-instrumenter
# (CrudeOil, Brent, NaturalGas) som co-driver til prising-baserte signaler.

TABLE_EIA_INVENTORY = "eia_inventory"

DDL_EIA_INVENTORY = f"""
CREATE TABLE IF NOT EXISTS {TABLE_EIA_INVENTORY} (
    series_id  TEXT    NOT NULL,    -- f.eks. "WCESTUS1"
    date       TEXT    NOT NULL,    -- ISO YYYY-MM-DD (week-ending)
    value      REAL    NOT NULL,    -- numerisk verdi
    units      TEXT,                -- f.eks. "MBBL", "BCF"
    PRIMARY KEY (series_id, date)
)
"""

EIA_INVENTORY_COLS: tuple[str, ...] = (
    "series_id",
    "date",
    "value",
    "units",
)


class EiaInventoryRow(BaseModel):
    """En rad fra EIA Open Data v2 weekly-inventory-serie.

    `series_id` er EIA-canonical (f.eks. ``"WCESTUS1"`` for US Crude Oil
    Stocks excl. SPR). `date` er week-ending date (typisk fredag for
    petroleum, fredag for natural gas storage). `value` er numerisk;
    `units` er fysisk dimensjon (``"MBBL"``, ``"BCF"``, etc.).
    """

    series_id: str = Field(min_length=1)
    date: date
    value: float
    units: str | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# COMEX warehouse inventories (sub-fase 12.5+ session 108)
# ---------------------------------------------------------------------------
# CME Group's COMEX-divisjon publiserer daglige stats over warehouse-
# inventories for gull (XAU), sølv (XAG) og kobber (HG). Tre verdier:
# - registered  — fysisk metall klart for delivery mot futures-shorts
# - eligible    — metall i godkjente warehouses men ikke "warranted"
#                 til registered-status; krever owner-deklarasjon
# - total       — total stocks i warehouse-systemet (NB: ikke alltid =
#                 registered + eligible; varierer per kilde)
#
# Stress-tolkning: lav `registered/total`-coverage = supply tight
# (mer eligible som ikke er klar til delivery) = bullish for prising.
# `comex_stress`-driver leser denne tabellen.
#
# Schema: én rad per (metal, date). Kobber kan ha registered=total
# fordi CME har fjernet reg/elig-skillet for HG (cot-explorer-presedens).

TABLE_COMEX_INVENTORY = "comex_inventory"

DDL_COMEX_INVENTORY = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COMEX_INVENTORY} (
    metal      TEXT    NOT NULL,    -- "gold", "silver", "copper"
    date       TEXT    NOT NULL,    -- ISO YYYY-MM-DD
    registered REAL    NOT NULL,    -- registered oz/short tons
    eligible   REAL    NOT NULL,    -- eligible oz/short tons (0 hvis copper)
    total      REAL    NOT NULL,    -- total stocks (kan != registered+eligible)
    units      TEXT,                -- "oz" eller "st"
    PRIMARY KEY (metal, date)
)
"""

COMEX_INVENTORY_COLS: tuple[str, ...] = (
    "metal",
    "date",
    "registered",
    "eligible",
    "total",
    "units",
)


class ComexInventoryRow(BaseModel):
    """En rad fra COMEX warehouse inventory-rapport.

    `metal` er bedrock-canonical (``"gold"``, ``"silver"``, ``"copper"``);
    mapping til instrument-id (Gold/Silver/Copper) er driver-laget. `date`
    er observation date (typisk forrige børsdag, COMEX rapporterer T-1).

    For kobber kan `eligible=0` og `total=registered` fordi CME har
    fjernet reg/elig-skillet for HG-kontrakten (cot-explorer-presedens).
    """

    metal: str = Field(min_length=1)
    date: date
    registered: float = Field(ge=0)
    eligible: float = Field(ge=0)
    total: float = Field(ge=0)
    units: str | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Seismic events — USGS earthquake feed (sub-fase 12.5+ session 109)
# ---------------------------------------------------------------------------
# US Geological Survey publiserer åpen GeoJSON-feed med jordskjelv. Vi
# følger M >= 4.5 siste 7 dager og filtrerer på 10 mining-regions for å
# fange supply-disruption-risk for metals-instrumenter (Gold/Silver/
# Copper/Platinum).
#
# Schema: én rad per event_id (USGS-canonical, f.eks. "us7000abcd").
# event_ts lagres som ISO datetime i UTC (USGS publiserer som ms-epoch).
# `region` er bedrock-canonical mining-region-navn (f.eks.
# "Chile / Peru", "Sør-Afrika") — None hvis utenfor mining-regions
# (lagres uansett for full-data-bevaring; driver filtrerer per metall).

TABLE_SEISMIC_EVENTS = "seismic_events"

DDL_SEISMIC_EVENTS = f"""
CREATE TABLE IF NOT EXISTS {TABLE_SEISMIC_EVENTS} (
    event_id   TEXT    NOT NULL,    -- USGS-canonical (us7000abcd)
    event_ts   TEXT    NOT NULL,    -- ISO UTC datetime
    magnitude  REAL    NOT NULL,    -- Richter (typisk 4.5-9.5)
    latitude   REAL    NOT NULL,    -- WGS84 -90..90
    longitude  REAL    NOT NULL,    -- WGS84 -180..180
    depth_km   REAL,                -- km under havflate (nullable)
    place      TEXT,                -- USGS place-streng
    region     TEXT,                -- bedrock-canonical mining-region (NULL hvis utenfor)
    url        TEXT,                -- USGS event-URL
    PRIMARY KEY (event_id)
)
"""

SEISMIC_EVENTS_COLS: tuple[str, ...] = (
    "event_id",
    "event_ts",
    "magnitude",
    "latitude",
    "longitude",
    "depth_km",
    "place",
    "region",
    "url",
)


class SeismicEvent(BaseModel):
    """Ett jordskjelv fra USGS earthquake feed.

    `event_id` er USGS-canonical og brukes som PK for idempotent
    INSERT OR REPLACE. `region` er bedrock-canonical mining-region-
    navn eller None hvis utenfor mining-regions (events lagres
    uansett, drivere filtrerer).
    """

    event_id: str = Field(min_length=1)
    event_ts: datetime
    magnitude: float
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    depth_km: float | None = None
    place: str | None = None
    region: str | None = None
    url: str | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Euronext COT (sub-fase 12.5+ session 110)
# ---------------------------------------------------------------------------
# Euronext publiserer ukentlige MiFID II Commitments-of-Traders-rapporter
# for sine landbruksprodukter (Milling Wheat EBM, Corn EMA, Canola ECO).
# MiFID II-kategorier (Investment Funds ≈ Managed Money, Investment Firms,
# Commercial Undertakings, Other Financial) er likestillingen til CFTC's
# disaggregated-format.
#
# Vi lagrer kun MM-totaler + OI per cot-explorer-presedens — full
# kategori-breakdown er ikke ekstrahert av cot-explorer's HTML-parser
# (rowspan-celler i Euronext-HTML gir parsing-utfordring; de tar ut kun
# Total-raden for Investment Funds-kolonnen).
#
# Schema: én rad per (report_date, contract). `contract` er bedrock-
# canonical: "euronext milling wheat", "euronext corn", "euronext canola".

TABLE_COT_EURONEXT = "cot_euronext"

DDL_COT_EURONEXT = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COT_EURONEXT} (
    report_date  TEXT    NOT NULL,    -- ISO YYYY-MM-DD (fredag-snapshot)
    contract     TEXT    NOT NULL,    -- "euronext milling wheat" etc.
    mm_long      INTEGER NOT NULL,    -- Investment Funds long
    mm_short     INTEGER NOT NULL,    -- Investment Funds short
    open_interest INTEGER NOT NULL,   -- total open interest (alle kategorier)
    PRIMARY KEY (report_date, contract)
)
"""

COT_EURONEXT_COLS: tuple[str, ...] = (
    "report_date",
    "contract",
    "mm_long",
    "mm_short",
    "open_interest",
)


class CotEuronextRow(BaseModel):
    """En rad fra Euronext MiFID II COT-rapport.

    `contract` er bedrock-canonical (f.eks. ``"euronext milling wheat"``,
    ``"euronext corn"``). MM-feltene representerer Investment Funds-
    kategorien (≈ CFTC Managed Money). Open interest er summen over
    alle MiFID II-kategorier.

    Per cot-explorer-presedens lagres kun MM-totaler — Investment Firms
    / Commercial / Other Financial krever robust rowspan-parsing som
    ikke er prioritert (driver-bruken er primært MM-positioning-overlay
    for europeiske grain-kontrakter).
    """

    report_date: date
    contract: str
    mm_long: int = Field(ge=0)
    mm_short: int = Field(ge=0)
    open_interest: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
