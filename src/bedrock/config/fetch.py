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

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

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

    model_config = ConfigDict(extra="forbid")


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
) -> datetime | None:
    """Returner `MAX(ts_column)` fra tabellen, eller None hvis tom.

    Delegerer til `DataStore.latest_observation_ts` (rå-streng) og
    parses til timezone-aware datetime. Timestamp-kolonner lagres som
    ISO-strings (prices) eller YYYY-MM-DD (cot/fundamentals/weather).
    """
    raw = store.latest_observation_ts(table, ts_column)
    if raw is None:
        return None
    return _parse_ts(raw)


def _parse_ts(raw: Any) -> datetime:
    """Parse ts-verdi fra sqlite til timezone-aware datetime."""
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, (int, float)):
        # Unix-timestamp (sek)
        dt = datetime.fromtimestamp(float(raw), tz=UTC)
    elif isinstance(raw, str):
        # ISO-format; støtter 'YYYY-MM-DD' (dato-only) og full
        # 'YYYY-MM-DDTHH:MM:SS[Z/+00:00]'
        cleaned = raw.replace(" ", "T").replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            # Prøv date-only
            dt = datetime.strptime(raw, "%Y-%m-%d")
    else:
        raise FetchConfigError(f"Ukjent timestamp-format: {raw!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def check_staleness(
    name: str,
    spec: FetcherSpec,
    store: Any,
    now: datetime | None = None,
) -> FetcherStatus:
    """Beregn staleness-status for én fetcher."""
    resolved_now = now or datetime.now(UTC)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=UTC)

    latest = latest_observation_ts(store, spec.table, spec.ts_column)

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

    age = resolved_now - latest
    age_hours = age.total_seconds() / 3600.0
    is_stale = age > timedelta(hours=spec.stale_hours)

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
