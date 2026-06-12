"""Config-drevet fetch-cadence per PLAN § 7.2.

`config/fetch.yaml` beskriver når hver fetcher skal kjøre og når data
regnes som foreldet. Session 28 implementerer:

- Pydantic-schema + YAML-loader
- Staleness-check mot eksisterende SQLite-data
- CLI `bedrock fetch status` som rapporterer fersk/stale-status

Senere sessions vil legge til:

- Faktisk orkestrert kjøring (cron-daemon eller systemd-timer)
- Per-instrument stale-sjekker (ikke bare per tabell)
- Retry-backoff for `on_failure: retry_with_backoff`

YAML-format:

```yaml
fetchers:
  prices:
    module: bedrock.fetch.prices
    cron: "40 * * * 1-5"
    stale_hours: 2
    on_failure: retry_with_backoff
    table: prices
    ts_column: ts
```
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_FETCH_CONFIG_PATH = Path("config/fetch.yaml")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


OnFailure = Literal["log_and_skip", "retry_with_backoff", "raise"]


class FetcherSpec(BaseModel):
    """Config for én fetcher.

    `module` er ren identifikator (session 28 kjører ikke fetcheren
    automatisk; navnet brukes i logging og fremtidig scheduler).
    `table` / `ts_column` brukes av staleness-check for å finne siste
    observasjon i SQLite.
    """

    module: str
    cron: str  # 5-felt cron-uttrykk; validering kommer i scheduler-session
    stale_hours: float = Field(gt=0.0)
    on_failure: OnFailure = "log_and_skip"
    table: str
    ts_column: str = "ts"
    # Sett til true for fetchere som henter US-marked-avhengig data
    # (FRED, COMEX, NASS, USDA WASDE, EIA, Yahoo-listede US-ETF-er).
    # Staleness regnes da i US-business-day-timer, så weekends + US-bank-
    # holidays ikke bidrar til alder. Eliminerer false-positive monitor-
    # alarmer som Memorial Day → tirsdag-morgen-alert (session 2026-05-26).
    us_calendar: bool = False
    # Hente-vindu bakover i dager for `bedrock fetch run` (session
    # 2026-06-12). Default (None) gir `stale_hours × 2`-vinduet fra
    # `default_from_date`. Serier med publiserings-lag lengre enn
    # vinduet (NFCI ukentlig ~5d lag, IRLTLT01* månedlig 1-3 mnd lag)
    # faller ellers alltid utenfor og får aldri nye observasjoner.
    lookback_days: float | None = Field(default=None, gt=0.0)
    # Staleness-filter for fetchere som deler tabell (fundamentals):
    # uten filter måles MAX(date) over hele tabellen, og én fetchers
    # data kan maskere at en annen er død. `series_filter` = eksakt
    # series_id-liste, `series_prefix` = prefix-match. Maks én av dem.
    series_filter: list[str] | None = None
    series_prefix: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _series_filter_xor_prefix(self) -> FetcherSpec:
        if self.series_filter is not None and self.series_prefix is not None:
            raise ValueError("series_filter og series_prefix kan ikke kombineres — velg én")
        return self


class FetchConfig(BaseModel):
    """Toppnivå fetch-config."""

    fetchers: dict[str, FetcherSpec]

    model_config = ConfigDict(extra="forbid")


class FetchConfigError(ValueError):
    """YAML parsed men struktur er ugyldig."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_fetch_config(path: Path | str | None = None) -> FetchConfig:
    """Les `config/fetch.yaml` og returner validert FetchConfig."""
    target = Path(path) if path is not None else DEFAULT_FETCH_CONFIG_PATH
    if not target.exists():
        raise FileNotFoundError(f"Fetch config not found: {target}")

    with target.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise FetchConfigError(f"{target}: empty YAML file")
    if not isinstance(raw, dict):
        raise FetchConfigError(f"{target}: expected YAML mapping, got {type(raw).__name__}")

    return FetchConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


class FetcherStatus(BaseModel):
    """Status-rapport for én fetcher."""

    name: str
    module: str
    table: str
    stale_hours: float
    latest_observation: datetime | None
    age_hours: float | None  # None hvis ingen observasjon
    is_stale: bool
    has_data: bool

    model_config = ConfigDict(extra="forbid")


def latest_observation_ts(
    store: Any,
    table: str,
    ts_column: str = "ts",
    series_filter: list[str] | None = None,
    series_prefix: str | None = None,
) -> datetime | None:
    """Returner `MAX(ts_column)` fra tabellen, eller None hvis tom.

    Delegerer til `DataStore.latest_observation_ts` (rå-streng) og
    parses til timezone-aware datetime. Timestamp-kolonner lagres som
    ISO-strings (prices) eller YYYY-MM-DD (cot/fundamentals/weather).

    `series_filter`/`series_prefix` begrenser til rader med matchende
    `series_id` — nødvendig for fetchere som deler fundamentals-tabellen.
    """
    raw = store.latest_observation_ts(
        table,
        ts_column,
        series_filter=series_filter,
        series_prefix=series_prefix,
    )
    if raw is None:
        return None
    return _parse_ts(raw)


def _parse_ts(raw: Any) -> datetime:
    """Parse ts-verdi fra sqlite til timezone-aware datetime."""
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, (int, float)):
        # Unix-timestamp (sek)
        dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
    elif isinstance(raw, str):
        # ISO-format; støtter 'YYYY-MM-DD' (dato-only), 'YYYY-MM'
        # (måneds-aggregat for weather_monthly), og full
        # 'YYYY-MM-DDTHH:MM:SS[Z/+00:00]'
        cleaned = raw.replace(" ", "T").replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            # Prøv date-only først, deretter måned-only
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                dt = datetime.strptime(raw, "%Y-%m")
    else:
        raise FetchConfigError(f"Ukjent timestamp-format: {raw!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_US_HOLIDAYS_CACHE: Any = None


def _us_holidays() -> Any:
    """Lazy-init US-bank-holiday-kalender (cachet på modul-nivå).

    `holidays.US()` returnerer en dict-lignende objekt som auto-utvider
    seg når nye år aksesseres — én instans dekker hele kjøretiden.
    """
    global _US_HOLIDAYS_CACHE
    if _US_HOLIDAYS_CACHE is None:
        import holidays as _holidays

        _US_HOLIDAYS_CACHE = _holidays.US()
    return _US_HOLIDAYS_CACHE


def _is_us_business_day(d: date) -> bool:
    """True hvis dato er hverdag (Mon-Fri) OG ikke US-bank-holiday."""
    if d.weekday() >= 5:
        return False
    return d not in _us_holidays()


def business_hours_between(start: datetime, end: datetime) -> float:
    """Timer mellom `start` og `end` som faller på US-business-days.

    Brukes for `us_calendar=true`-fetchere så weekend + US-holidays
    ikke bidrar til staleness-alder. Beregner per døgn-segment;
    helligdager (Sat/Sun + US-bank) gir 0 timer. Akseptabelt O(N)
    der N er antall døgn mellom — i praksis < 7 for ferskhets-sjekk.
    """
    if end <= start:
        return 0.0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    total_seconds = 0.0
    cur = start
    while cur < end:
        next_midnight = cur.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        seg_end = min(next_midnight, end)
        if _is_us_business_day(cur.date()):
            total_seconds += (seg_end - cur).total_seconds()
        cur = seg_end
    return total_seconds / 3600.0


def check_staleness(
    name: str,
    spec: FetcherSpec,
    store: Any,
    now: datetime | None = None,
) -> FetcherStatus:
    """Beregn staleness-status for én fetcher."""
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)

    latest = latest_observation_ts(
        store,
        spec.table,
        spec.ts_column,
        series_filter=spec.series_filter,
        series_prefix=spec.series_prefix,
    )

    if latest is None:
        return FetcherStatus(
            name=name,
            module=spec.module,
            table=spec.table,
            stale_hours=spec.stale_hours,
            latest_observation=None,
            age_hours=None,
            is_stale=True,
            has_data=False,
        )

    if spec.us_calendar:
        age_hours = business_hours_between(latest, resolved_now)
    else:
        age_hours = (resolved_now - latest).total_seconds() / 3600.0
    # Fremtidsdaterte observasjoner (USDA PSD lagrer marketing-year-
    # projeksjoner datert frem i tid) ga negativ alder. Clamp til 0 —
    # data som dekker fremtiden er per definisjon ikke stale.
    age_hours = max(age_hours, 0.0)
    is_stale = age_hours > spec.stale_hours

    return FetcherStatus(
        name=name,
        module=spec.module,
        table=spec.table,
        stale_hours=spec.stale_hours,
        latest_observation=latest,
        age_hours=age_hours,
        is_stale=is_stale,
        has_data=True,
    )


def status_report(
    config: FetchConfig,
    store: Any,
    now: datetime | None = None,
) -> list[FetcherStatus]:
    """Samlet status for alle fetchere. Sortert etter navn."""
    return [
        check_staleness(name, spec, store, now) for name, spec in sorted(config.fetchers.items())
    ]


__all__ = [
    "DEFAULT_FETCH_CONFIG_PATH",
    "FetchConfig",
    "FetchConfigError",
    "FetcherSpec",
    "FetcherStatus",
    "check_staleness",
    "latest_observation_ts",
    "load_fetch_config",
    "status_report",
]
