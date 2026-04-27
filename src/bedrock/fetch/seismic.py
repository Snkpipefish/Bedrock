# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""USGS seismic-events fetcher (sub-fase 12.5+ session 109).

Henter jordskjelv M ≥ 4.5 fra US Geological Survey's GeoJSON-feed
(siste 7 dager) og filtrerer på 10 mining-regioner. Cot-explorer's
`fetch_seismic.py` brukte samme kilde + region-bokser; vi porter
direkte med ADR-007 § 4-mønster (manuell CSV-fallback).

Region-filtre er bedrock-canonical og dekker globale mining-hotspots.
Per-metall mapping er driver-laget (`mining_disruption` i macro.py).

Ingen API-key. USGS oppdaterer feeden hvert minutt; vi henter daglig
og bruker INSERT OR REPLACE på event_id for idempotens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import SEISMIC_EVENTS_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
_DEFAULT_TIMEOUT = 30.0
_MANUAL_CSV = Path("data/manual/seismic_events.csv")

_HEADERS = {
    "User-Agent": "bedrock/1.0 (sub-fase 12.5+ session 109)",
    "Accept": "application/geo+json",
}


# ---------------------------------------------------------------------------
# Mining-regioner (bedrock-canonical bounding boxes)
# ---------------------------------------------------------------------------
# Format: (region-navn, min_lat, max_lat, min_lon, max_lon).
# Lifted fra cot-explorer's fetch_seismic.py + utvidet med Sør-Afrika
# (kritisk for platinum) og Russland (palladium/platinum).
MINE_REGIONS: tuple[tuple[str, float, float, float, float], ...] = (
    ("Chile / Peru", -40.0, -14.0, -76.0, -62.0),
    ("Mexico / Mellom-Amerika", 14.0, 32.0, -117.0, -85.0),
    ("USA / Canada", 30.0, 70.0, -130.0, -60.0),
    ("DRC / Zambia", -15.0, 5.0, 22.0, 35.0),
    ("Sør-Afrika", -34.0, -22.0, 16.0, 33.0),
    ("Mongolia / Kina", 38.0, 52.0, 88.0, 122.0),
    ("Indonesia / Papua", -8.0, 2.0, 130.0, 145.0),
    ("Australia", -42.0, -10.0, 113.0, 154.0),
    ("Russland / Sibir", 50.0, 72.0, 60.0, 140.0),
    ("Øst-Afrika", -10.0, 15.0, 25.0, 45.0),
)


def find_mining_region(latitude: float, longitude: float) -> str | None:
    """Returner mining-region-navn hvis (lat, lon) er innenfor noen,
    ellers None.
    """
    for name, mlat, xlat, mlon, xlon in MINE_REGIONS:
        if mlat <= latitude <= xlat and mlon <= longitude <= xlon:
            return name
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_usgs_geojson(payload: Any) -> pd.DataFrame:
    """Parse USGS-GeoJSON til DataFrame med ``SEISMIC_EVENTS_COLS``.

    Events utenfor mining-regions inkluderes med region=None (lagres
    uansett — drivere filtrerer per metall).

    Args:
        payload: dekodet GeoJSON-dict.

    Returns:
        DataFrame med en rad per event. Tom hvis ingen events.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"USGS payload not dict: {type(payload).__name__}")

    features = payload.get("features", [])
    if not isinstance(features, list):
        raise ValueError("USGS payload missing 'features' list")

    rows: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates", [])
        if not isinstance(coords, list) or len(coords) < 2:
            continue

        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue

        depth = None
        if len(coords) > 2 and coords[2] is not None:
            try:
                depth = float(coords[2])
            except (TypeError, ValueError):
                depth = None

        mag = props.get("mag")
        if mag is None:
            continue
        try:
            magnitude = float(mag)
        except (TypeError, ValueError):
            continue

        ts_ms = props.get("time")
        if ts_ms is None:
            continue
        try:
            event_ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue

        event_id = feat.get("id")
        if not event_id:
            continue

        region = find_mining_region(lat, lon)

        rows.append(
            {
                "event_id": str(event_id),
                "event_ts": event_ts,
                "magnitude": magnitude,
                "latitude": lat,
                "longitude": lon,
                "depth_km": depth,
                "place": props.get("place"),
                "region": region,
                "url": props.get("url"),
            }
        )

    df = pd.DataFrame(rows, columns=list(SEISMIC_EVENTS_COLS))
    _log.info("seismic.parsed events=%d", len(df))
    return df


# ---------------------------------------------------------------------------
# Remote fetch
# ---------------------------------------------------------------------------


def fetch_seismic_remote(
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    raw_response: Any = None,  # injection for testing
) -> pd.DataFrame:
    """Hent USGS-feed og parse. Reiser ValueError ved feil.

    `raw_response` (dict) kan injiseres for testing — hopper over HTTP.
    """
    if raw_response is None:
        response = http_get_with_retry(USGS_URL, headers=_HEADERS, timeout=timeout)
        if response.status_code != 200:
            raise ValueError(f"USGS: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"USGS: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    return parse_usgs_geojson(payload)


# ---------------------------------------------------------------------------
# Manuell CSV-fallback
# ---------------------------------------------------------------------------


def fetch_seismic_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert CSV. Returnerer tom DataFrame hvis filen mangler."""
    if not csv_path.exists():
        _log.info("seismic.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(SEISMIC_EVENTS_COLS))

    df = pd.read_csv(csv_path)
    missing = [c for c in SEISMIC_EVENTS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"seismic_events manual CSV mangler kolonner: {sorted(missing)}")

    df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
    return df[list(SEISMIC_EVENTS_COLS)].copy()


# ---------------------------------------------------------------------------
# Combined: API + fallback
# ---------------------------------------------------------------------------


def fetch_seismic(
    *,
    csv_path: Path = _MANUAL_CSV,
) -> pd.DataFrame:
    """Hent USGS-feed; fall tilbake på manuell CSV hvis API feiler.

    Returnerer alltid DataFrame; tom hvis begge mangler. Ingen
    exceptions propageres oppover.
    """
    try:
        df = fetch_seismic_remote()
        if not df.empty:
            return df
    except Exception as exc:
        _log.warning("seismic.api_failed_fallback_to_csv error=%s", exc)

    try:
        return fetch_seismic_manual(csv_path)
    except Exception as exc:
        _log.warning("seismic.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(SEISMIC_EVENTS_COLS))


__all__ = [
    "MINE_REGIONS",
    "USGS_URL",
    "fetch_seismic",
    "fetch_seismic_manual",
    "fetch_seismic_remote",
    "find_mining_region",
    "parse_usgs_geojson",
]
