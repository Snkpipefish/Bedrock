"""Forex Factory økonomisk kalender — fetcher for `econ_events`-tabellen.

Sub-fase 12.5+ session 105 (ADR-007/008) — port av
``~/cot-explorer/fetch_calendar.py``. Henter kommende high/medium-
impact events fra ``nfs.faireconomy.media`` (statisk JSON, denne uke).

Output-skjema følger ``ECON_EVENTS_COLS`` i ``data.schemas``. Idempotent
ved re-kjøring: PK på (event_ts, country, title) deduplikerer via
INSERT OR REPLACE.

Cadence (per ADR-008): ``15 6,18 * * *`` Oslo (06:15 + 18:15 daglig) —
fanger morgen EU/UK + ettermiddag US uten unødvendig nettverksforbruk.
JSON-en endrer seg når nye events blir lagt til eller forecast/previous
fylles inn 1-2 timer før release; daglig 2× er mer enn nok.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Impact-nivåer som lagres. "Low" droppes — for mye støy uten
# pris-impact. Brukeren kan endre via fetch-call hvis de vil ha alt.
DEFAULT_IMPACT_FILTER = ("High", "Medium")


def fetch_calendar_events(
    impact_filter: tuple[str, ...] = DEFAULT_IMPACT_FILTER,
    *,
    timeout: float = 15.0,
    raw_response: Any = None,  # injection-point for testing
) -> pd.DataFrame:
    """Hent uka-kalender fra Forex Factory og returner som DataFrame.

    Returnerer pd.DataFrame med kolonner som matcher ``ECON_EVENTS_COLS``:
        event_ts (UTC ISO string), country, title, impact, forecast,
        previous, fetched_at (UTC ISO string).

    Args:
        impact_filter: hvilke impact-nivåer som skal inkluderes
            (default: High + Medium).
        timeout: HTTP-timeout sekunder.
        raw_response: brukes kun av tester — pre-parsed JSON-liste.
            Hvis satt, hopper over HTTP-kallet helt.

    Returns:
        DataFrame, evt. tom hvis JSON-en mangler events i filter-window.

    Raises:
        requests.RequestException: ved HTTP-feil etter retry.
        ValueError: hvis JSON-strukturen er uventet.
    """
    fetched_at = datetime.now(timezone.utc)

    if raw_response is None:
        response = http_get_with_retry(CALENDAR_URL, timeout=timeout)
        if response.status_code != 200:
            raise ValueError(f"calendar_ff: HTTP {response.status_code} from {CALENDAR_URL}")
        try:
            raw = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(f"calendar_ff: invalid JSON: {exc}") from exc
    else:
        raw = raw_response

    if not isinstance(raw, list):
        raise ValueError(f"calendar_ff: expected JSON list at top level, got {type(raw).__name__}")

    rows: list[dict[str, Any]] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        impact = ev.get("impact", "")
        if impact not in impact_filter:
            continue

        country = ev.get("country", "").strip()
        title = ev.get("title", "").strip()
        date_str = ev.get("date", "")
        if not country or not title or not date_str:
            continue

        # Parser ISO 8601 — FF gir UTC eksplisitt med offset.
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            event_ts = dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            _log.debug("calendar_ff: skipping invalid date %r", date_str)
            continue

        forecast = ev.get("forecast") or None
        previous = ev.get("previous") or None
        # Tom-streng → None for konsistens med Pydantic Optional.
        if isinstance(forecast, str) and not forecast.strip():
            forecast = None
        if isinstance(previous, str) and not previous.strip():
            previous = None

        rows.append(
            {
                "event_ts": event_ts.isoformat(),
                "country": country,
                "title": title,
                "impact": impact,
                "forecast": forecast,
                "previous": previous,
                "fetched_at": fetched_at.isoformat(),
            }
        )

    df = pd.DataFrame(rows, columns=list(ECON_EVENTS_DF_COLS))
    _log.info("calendar_ff: fetched %d events (filter=%s)", len(df), impact_filter)
    return df


# Eksponer kolonne-rekkefølgen for å kunne lage tom DataFrame med
# riktig schema når ingen events matcher filter.
ECON_EVENTS_DF_COLS: tuple[str, ...] = (
    "event_ts",
    "country",
    "title",
    "impact",
    "forecast",
    "previous",
    "fetched_at",
)


__all__ = ["CALENDAR_URL", "DEFAULT_IMPACT_FILTER", "fetch_calendar_events"]
