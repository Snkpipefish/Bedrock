"""`global_state` for /bot/signals — event-blackout per bot-instrument.

Session 2026-09-05. Boten (`src/bedrock/bot/entry.py:_passes_filters`)
nekter nye entries for instrumenter som står i
``global_state.event_blackout`` (makro-kalender fra econ_events) eller
``global_state.usda_blackout`` (USDA-rapporter, kun grains). Denne
modulen bygger dicten server-side slik at boten slipper egen DB-tilgang.

Kontrakt (nøkler boten leser):

```json
{
  "geo_risk_active": false,
  "geo_active": false,
  "vix_regime": "normal",
  "correlation_config": {"max_per_group": 2, "max_total": 20},
  "event_blackout": {
    "GOLD": {"event": "Non-Farm Employment Change", "country": "USD",
             "impact": "High", "minutes_away": 30}
  },
  "usda_blackout": {
    "Corn": {"report": "prospective_plantings", "hours_away": 1.5}
  }
}
```

``minutes_away`` / ``hours_away`` er negative når eventen allerede har
skjedd (vi er i etter-vinduet). Per instrument velges nærmeste event
(minste |avstand|).

Fail-open: feil i oppslagene (DB, YAML, kalender) logges som warning og
gir tomme dicts + ``event_blackout_error`` med feilmeldingen. Endpointet
skal aldri 500-e på grunn av blackout-logikken — heller sende signaler
uten blackout enn ingen signaler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
import yaml

from bedrock.fetch.usda_calendar import clear_usda_calendar_cache, load_usda_calendar
from bedrock.signal_server.bot_adapter import default_global_state
from bedrock.signal_server.config import ServerConfig

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger(__name__)

# Bot-instrument-navn (verdiene i config/bot_whitelist.yaml `mapping:`)
# → kalender-land som utløser blackout. USD er relevant for alt (USD-
# denominert, US-makro driver risk-on/off); FX-par legger til den ikke-
# USD-siden. Whitelistede instrumenter som mangler her får
# DEFAULT_EVENT_COUNTRIES.
DEFAULT_EVENT_COUNTRIES: tuple[str, ...] = ("USD",)

# Events uten land (Jackson Hole, OPEC, G7/G20) lagres med country
# "ALL"/"All" i econ_events. De gjelder alle instrumenter og legges
# alltid til i spørringen og i matchingen.
GLOBAL_EVENT_COUNTRIES: tuple[str, ...] = ("ALL", "All")

# Tie-break for samtidige events (NFP-klyngen 12:30Z: Average Hourly
# Earnings / Non-Farm / Unemployment): headline-titler først, deretter
# alfabetisk. Alle samtidige titler rapporteres, headline først.
_HEADLINE_KEYWORDS: tuple[str, ...] = (
    "non-farm",
    "nonfarm",
    "cpi",
    "fomc",
    "federal funds",
    "interest rate",
    "gdp",
    "unemployment rate",
    "pce",
    "retail sales",
)

INSTRUMENT_EVENT_COUNTRIES: dict[str, list[str]] = {
    # FX
    "EURUSD": ["USD", "EUR"],
    "GBPUSD": ["USD", "GBP"],
    "USDJPY": ["USD", "JPY"],
    "AUDUSD": ["USD", "AUD"],
    # Metals
    "GOLD": ["USD"],
    "SILVER": ["USD"],
    "COPPER": ["USD"],
    "PLATINUM": ["USD"],
    # Energy
    "OIL WTI": ["USD"],
    "OIL BRENT": ["USD"],
    "NATGAS": ["USD"],
    # Indices
    "SPX500": ["USD"],
    "US100": ["USD"],
    # Crypto
    "BTC": ["USD"],
    "ETH": ["USD"],
    # Agri
    "Corn": ["USD"],
    "Wheat": ["USD"],
    "Soybean": ["USD"],
    "Coffee": ["USD"],
    "Cotton": ["USD"],
    "Sugar": ["USD"],
    "Cocoa": ["USD"],
}

# USDA-rapporter påvirker grains direkte. Softs (Coffee/Cocoa/Sugar/
# Cotton) har egne kalendere (ICO/ICCO/USDA Cotton) som ikke er
# modellert her.
USDA_INSTRUMENTS: frozenset[str] = frozenset({"Corn", "Wheat", "Soybean"})

# Lagret event_ts-format i econ_events (store.append_econ_events).
_EVENT_TS_FMT = "%Y-%m-%dT%H:%M:%S"


class EconEventSource(Protocol):
    """Strukturelt interface for `DataStore.get_econ_events` — lar tester
    bruke en fake store uten SQLite."""

    def get_econ_events(
        self,
        countries: Sequence[str] | None = None,
        impact_levels: Sequence[str] | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        title_pattern: str | None = None,
    ) -> pd.DataFrame: ...


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_bot_instruments(whitelist_path: Path) -> list[str]:
    """Bot-instrument-navn fra whitelist-YAML (`mapping:`-verdiene).

    Faller tilbake til nøklene i ``INSTRUMENT_EVENT_COUNTRIES`` hvis
    filen mangler, ikke kan parses eller ikke har `mapping:`-dict —
    blackout-dekning skal ikke avhenge av at YAML-en er lesbar.
    Bevarer YAML-rekkefølgen (deterministisk output), dedupliserer.
    """
    try:
        data = yaml.safe_load(whitelist_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        log.warning(
            "[global_state] kunne ikke lese bot-whitelist %s (%s) — bruker innebygd liste",
            whitelist_path,
            exc,
        )
        return list(INSTRUMENT_EVENT_COUNTRIES)
    mapping = data.get("mapping") if isinstance(data, dict) else None
    if not isinstance(mapping, dict) or not mapping:
        log.warning(
            "[global_state] %s mangler 'mapping:'-dict — bruker innebygd liste",
            whitelist_path,
        )
        return list(INSTRUMENT_EVENT_COUNTRIES)
    seen: dict[str, None] = {}
    for value in mapping.values():
        seen.setdefault(str(value), None)
    return list(seen)


def event_countries_for(instrument: str) -> list[str]:
    """Kalender-land som utløser blackout for et bot-instrument."""
    return list(INSTRUMENT_EVENT_COUNTRIES.get(instrument, DEFAULT_EVENT_COUNTRIES))


def build_event_blackout(
    store: EconEventSource,
    now: datetime,
    cfg: ServerConfig,
    instruments: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Makro-event-blackout per instrument.

    Instrumentet er i blackout når en event med relevant land og impact
    i ``cfg.event_blackout_impact_levels`` ligger i
    ``[now - after_min, now + before_min]``. Ved flere treff velges
    eventen nærmest `now` (minste |minutes_away|); ved likt velges den
    tidligste. Vinduet håndheves i Python også (ikke bare i SQL) slik at
    resultatet er uavhengig av hvordan store-en filtrerer.

    Kaster videre på feil — caller (`build_global_state`) fail-opener.
    """
    now = _ensure_utc(now)
    before = timedelta(minutes=cfg.event_blackout_before_min)
    after = timedelta(minutes=cfg.event_blackout_after_min)
    window_start = now - after
    window_end = now + before

    countries_by_instrument = {
        inst: [*event_countries_for(inst), *GLOBAL_EVENT_COUNTRIES] for inst in instruments
    }
    all_countries = sorted({c for cs in countries_by_instrument.values() for c in cs})
    if not instruments:
        return {}

    df = store.get_econ_events(
        countries=all_countries,
        impact_levels=list(cfg.event_blackout_impact_levels),
        from_ts=window_start.strftime(_EVENT_TS_FMT),
        to_ts=window_end.strftime(_EVENT_TS_FMT),
    )
    if df is None or df.empty:
        return {}

    # Normaliser til liste av (event_ts, country, title, impact, minutes_away)
    events: list[tuple[datetime, str, str, str, int]] = []
    for rec in df.to_dict("records"):
        raw_ts = rec.get("event_ts")
        if raw_ts is None or pd.isna(raw_ts):
            continue
        ts_obj = pd.Timestamp(raw_ts).to_pydatetime()
        if not isinstance(ts_obj, datetime):
            continue
        ts = _ensure_utc(ts_obj)
        if ts < window_start or ts > window_end:
            continue
        minutes_away = round((ts - now).total_seconds() / 60.0)
        events.append(
            (ts, str(rec["country"]), str(rec["title"]), str(rec["impact"]), minutes_away)
        )
    if not events:
        return {}
    events.sort(key=lambda e: e[0])

    result: dict[str, dict[str, Any]] = {}
    for inst, countries in countries_by_instrument.items():
        wanted = set(countries)
        relevant = [ev for ev in events if ev[1] in wanted]
        if not relevant:
            continue
        nearest = min(abs(ev[4]) for ev in relevant)
        co_timed = [ev for ev in relevant if abs(ev[4]) == nearest]
        co_timed.sort(key=lambda ev: (_headline_rank(ev[2]), ev[2]))
        best = co_timed[0]
        titles: list[str] = []
        for ev in co_timed:
            if ev[2] not in titles:
                titles.append(ev[2])
        result[inst] = {
            "event": " + ".join(titles[:3]),
            "country": best[1],
            "impact": best[3],
            "minutes_away": best[4],
        }
    return result


def _headline_rank(title: str) -> int:
    """0 for headline-events (se _HEADLINE_KEYWORDS), ellers 1."""
    low = title.lower()
    return 0 if any(k in low for k in _HEADLINE_KEYWORDS) else 1


# mtime per kalender-sti ved forrige lasting — `load_usda_calendar`
# cacher per prosess uten mtime-sjekk, og serveren lever i uker. Endres
# fila, tømmes cachen før neste lasting.
_USDA_CALENDAR_MTIME_SEEN: dict[Path, float] = {}


def _load_usda_calendar_fresh(path: Path) -> dict[str, list[datetime]]:
    """`load_usda_calendar` med mtime-basert cache-invalidering."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    if _USDA_CALENDAR_MTIME_SEEN.get(path) != mtime:
        clear_usda_calendar_cache()
        _USDA_CALENDAR_MTIME_SEEN[path] = mtime
    return load_usda_calendar(path)


def build_usda_blackout(
    now: datetime,
    cfg: ServerConfig,
    instruments: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """USDA-rapport-blackout for grains (Corn/Wheat/Soybean).

    Vindu ``[now - usda_blackout_hours_after, now + usda_blackout_hours_before]``
    mot alle rapport-typer i ``cfg.usda_calendar_path``. Nærmeste rapport
    per instrument. ``hours_away`` avrundet til 2 desimaler, negativ etter
    publisering.

    Kaster videre på feil (manglende/ugyldig kalender) — caller fail-opener.
    """
    grains = [inst for inst in instruments if inst in USDA_INSTRUMENTS]
    if not grains:
        return {}
    now = _ensure_utc(now)
    before = timedelta(hours=cfg.usda_blackout_hours_before)
    after = timedelta(hours=cfg.usda_blackout_hours_after)

    calendar = _load_usda_calendar_fresh(Path(cfg.usda_calendar_path))
    best: tuple[str, float] | None = None
    for report_type, report_times in calendar.items():
        for report_time in report_times:
            rt = _ensure_utc(report_time)
            if rt < now - after or rt > now + before:
                continue
            hours_away = (rt - now).total_seconds() / 3600.0
            if best is None or abs(hours_away) < abs(best[1]):
                best = (report_type, hours_away)
    if best is None:
        return {}
    entry = {"report": best[0], "hours_away": round(best[1], 2)}
    return {inst: dict(entry) for inst in grains}


def build_global_state(
    store: EconEventSource,
    now: datetime,
    cfg: ServerConfig,
) -> dict[str, Any]:
    """Bygg `global_state` for bot-payloaden.

    Basis fra `default_global_state()` (geo/vix/korrelasjon) +
    ``event_blackout`` og ``usda_blackout`` per whitelistet bot-
    instrument. Med ``cfg.event_blackout_enabled=False`` gjøres ingen
    oppslag og begge dicts er tomme.

    Fail-open: hver oppslags-feil logges (warning), gir tom dict for den
    delen og setter ``event_blackout_error`` (flere feil joines med "; ").
    """
    state = default_global_state()
    if not cfg.event_blackout_enabled:
        return state

    instruments = load_bot_instruments(cfg.bot_whitelist_path)
    errors: list[str] = []

    try:
        state["event_blackout"] = build_event_blackout(store, now, cfg, instruments)
    except Exception as exc:
        log.warning("[global_state] event_blackout feilet (fail-open): %s", exc)
        state["event_blackout"] = {}
        errors.append(f"event_blackout: {exc}")

    try:
        state["usda_blackout"] = build_usda_blackout(now, cfg, instruments)
    except Exception as exc:
        log.warning("[global_state] usda_blackout feilet (fail-open): %s", exc)
        state["usda_blackout"] = {}
        errors.append(f"usda_blackout: {exc}")

    if errors:
        state["event_blackout_error"] = "; ".join(errors)
    return state


def fail_open_global_state(reason: str) -> dict[str, Any]:
    """Defaults + `event_blackout_error` når blackout-bygging ikke kunne
    starte i det hele tatt (DB-fil mangler, store kunne ikke åpnes)."""
    state = default_global_state()
    state["event_blackout_error"] = reason
    return state


__all__ = [
    "DEFAULT_EVENT_COUNTRIES",
    "GLOBAL_EVENT_COUNTRIES",
    "INSTRUMENT_EVENT_COUNTRIES",
    "USDA_INSTRUMENTS",
    "EconEventSource",
    "build_event_blackout",
    "build_global_state",
    "build_usda_blackout",
    "event_countries_for",
    "fail_open_global_state",
    "load_bot_instruments",
]
