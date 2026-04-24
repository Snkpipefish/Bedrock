"""USDA rapport-kalender: loader + `usda_blackout`-gate.

Fase 6 session 27: første kalender-gate. Leser `config/calendars/usda.yaml`
(hardkodet per år per bruker-valg) og kapper grade rundt USDA-rapport-
tidspunkter.

Bevisst minimalistisk:
- Kun `prospective_plantings` støttet (bruker valgte dette i session 27)
- Andre rapport-typer støttes strukturelt (loader aksepterer hvilken
  som helst top-level-key), men har ikke YAML-innhold eller egne
  gates. Utvides når behov oppstår.

YAML-form for kalenderen:

    prospective_plantings:
      - 2026-03-31T16:00:00Z
      - 2027-03-30T16:00:00Z
    grain_stocks:  # valgfri
      - 2026-06-28T16:00:00Z

YAML-form for gate i instrument-reglene:

    gates:
      - name: usda_blackout
        params:
          report_types: [prospective_plantings]
          hours: 3
          calendar_path: config/calendars/usda.yaml
        cap_grade: C
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from bedrock.engine.gates import GateContext, gate_register


DEFAULT_CALENDAR_PATH = Path("config/calendars/usda.yaml")


class UsdaCalendarError(ValueError):
    """YAML parsed men datoer er ugyldig format."""


# ---------------------------------------------------------------------------
# Loader + cache
# ---------------------------------------------------------------------------

_CACHE: dict[Path, dict[str, list[datetime]]] = {}


def load_usda_calendar(
    path: Path | str | None = None,
) -> dict[str, list[datetime]]:
    """Les USDA-kalender fra YAML.

    Returnerer `{report_type: [datetime, ...]}`. Alle datetimes er
    timezone-aware (UTC). Sorterer listen slik at tidlige datoer
    kommer først.

    Caches basert på absolutt sti. For å tvinge reload, bruk
    `clear_usda_calendar_cache()`.

    Reiser `UsdaCalendarError` ved ugyldig format, `FileNotFoundError`
    ved manglende fil.
    """
    target = Path(path) if path is not None else DEFAULT_CALENDAR_PATH
    absolute = target.resolve()

    if absolute in _CACHE:
        return _CACHE[absolute]

    if not absolute.exists():
        raise FileNotFoundError(f"USDA calendar not found: {absolute}")

    with absolute.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        result: dict[str, list[datetime]] = {}
    elif not isinstance(raw, dict):
        raise UsdaCalendarError(
            f"{absolute}: expected YAML mapping at root, got "
            f"{type(raw).__name__}"
        )
    else:
        result = _parse_calendar_dict(raw, source=str(absolute))

    _CACHE[absolute] = result
    return result


def clear_usda_calendar_cache() -> None:
    """Tømmer loader-cachen. Nyttig i tester og når YAML endres."""
    _CACHE.clear()


def _parse_calendar_dict(
    raw: dict[str, Any], source: str
) -> dict[str, list[datetime]]:
    result: dict[str, list[datetime]] = {}
    for report_type, dates in raw.items():
        if not isinstance(dates, list):
            raise UsdaCalendarError(
                f"{source}: {report_type!r} must be a list, got "
                f"{type(dates).__name__}"
            )
        parsed: list[datetime] = []
        for item in dates:
            parsed.append(_parse_datetime(item, source, report_type))
        parsed.sort()
        result[report_type] = parsed
    return result


def _parse_datetime(value: Any, source: str, report_type: str) -> datetime:
    if isinstance(value, datetime):
        # pyyaml kan parse tidsstempler direkte til datetime
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise UsdaCalendarError(
                f"{source}: ugyldig dato i {report_type!r}: {value!r}"
            ) from exc
    else:
        raise UsdaCalendarError(
            f"{source}: {report_type!r} inneholder ikke-dato-verdi: "
            f"{value!r} ({type(value).__name__})"
        )

    # Sikre timezone-awareness — anta UTC hvis ikke spesifisert
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


@gate_register("usda_blackout")
def _usda_blackout(context: GateContext, params: dict[str, Any]) -> bool:
    """Utløses hvis `context.now` er innenfor ±`hours` av en USDA-rapport.

    Params:
    - `calendar_path` (str, optional): default `config/calendars/usda.yaml`
    - `report_types` (list[str], optional): hvilke rapport-typer som
      teller. Default: alle typer i kalenderen.
    - `hours` (float, default 3): symmetrisk vindu (pre + post).

    Asymmetrisk vindu kan gis via `hours_before` og `hours_after` som
    overstyrer `hours`.

    Hvis `context.now` er None, returnerer gaten `False` (ikke utløst)
    — blackout kan bare håndheves med et kjent tidspunkt.
    """
    if context.now is None:
        return False

    path = params.get("calendar_path", DEFAULT_CALENDAR_PATH)
    calendar = load_usda_calendar(path)

    requested_types = params.get("report_types")
    if requested_types is None:
        report_types = list(calendar.keys())
    else:
        report_types = list(requested_types)

    hours = float(params.get("hours", 3.0))
    hours_before = float(params.get("hours_before", hours))
    hours_after = float(params.get("hours_after", hours))

    window_before = timedelta(hours=hours_before)
    window_after = timedelta(hours=hours_after)

    now = _ensure_aware(context.now)

    for rt in report_types:
        for report_time in calendar.get(rt, []):
            if (report_time - window_before) <= now <= (report_time + window_after):
                return True
    return False


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = [
    "DEFAULT_CALENDAR_PATH",
    "UsdaCalendarError",
    "clear_usda_calendar_cache",
    "load_usda_calendar",
]
