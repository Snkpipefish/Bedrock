# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Tester for USGS seismic-fetcher (sub-fase 12.5+ session 109)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.data.schemas import SEISMIC_EVENTS_COLS
from bedrock.fetch.seismic import (
    MINE_REGIONS,
    fetch_seismic,
    fetch_seismic_manual,
    fetch_seismic_remote,
    find_mining_region,
    parse_usgs_geojson,
)


def _ts_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _payload(events: list[dict]) -> dict:
    """Bygg en USGS-stil GeoJSON FeatureCollection."""
    features = []
    for ev in events:
        features.append(
            {
                "id": ev["id"],
                "type": "Feature",
                "properties": {
                    "mag": ev["mag"],
                    "place": ev.get("place", ""),
                    "time": _ts_ms(ev["time"]),
                    "url": ev.get("url", ""),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [ev["lon"], ev["lat"], ev.get("depth", 30.0)],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Mining-region matcher
# ---------------------------------------------------------------------------


def test_find_chile_peru() -> None:
    assert find_mining_region(-23.5, -70.4) == "Chile / Peru"


def test_find_south_africa() -> None:
    """Witwatersrand-basinet i Johannesburg (~-26.2, 28)."""
    assert find_mining_region(-26.2, 28.0) == "Sør-Afrika"


def test_find_australia() -> None:
    assert find_mining_region(-31.95, 115.86) == "Australia"


def test_find_outside_returns_none() -> None:
    """Mid-Atlantic ridge (0, 0) er utenfor alle mining-regioner."""
    assert find_mining_region(0.0, 0.0) is None


def test_find_japan_excluded() -> None:
    """Japan har ingen vesentlig metal-mining → ekskludert."""
    assert find_mining_region(35.7, 139.7) is None


def test_all_regions_present() -> None:
    """Audit: alle 10 forventede regioner er med."""
    names = {r[0] for r in MINE_REGIONS}
    expected = {
        "Chile / Peru",
        "Mexico / Mellom-Amerika",
        "USA / Canada",
        "DRC / Zambia",
        "Sør-Afrika",
        "Mongolia / Kina",
        "Indonesia / Papua",
        "Australia",
        "Russland / Sibir",
        "Øst-Afrika",
    }
    assert expected.issubset(names)


# ---------------------------------------------------------------------------
# parse_usgs_geojson
# ---------------------------------------------------------------------------


def test_parses_typical_event() -> None:
    payload = _payload(
        [
            {
                "id": "us7000abcd",
                "mag": 5.4,
                "lat": -23.5,
                "lon": -70.4,
                "depth": 35.0,
                "place": "100 km W of Antofagasta, Chile",
                "time": datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
                "url": "https://earthquake.usgs.gov/...",
            }
        ]
    )
    df = parse_usgs_geojson(payload)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["event_id"] == "us7000abcd"
    assert row["magnitude"] == 5.4
    assert row["latitude"] == -23.5
    assert row["longitude"] == -70.4
    assert row["depth_km"] == 35.0
    assert row["region"] == "Chile / Peru"


def test_event_outside_mining_region_has_null_region() -> None:
    payload = _payload(
        [
            {
                "id": "us_atlantic",
                "mag": 5.0,
                "lat": 0.0,
                "lon": -30.0,  # Mid-Atlantic ridge
                "time": datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
            }
        ]
    )
    df = parse_usgs_geojson(payload)
    assert len(df) == 1
    assert df["region"].iloc[0] is None


def test_skips_event_without_id() -> None:
    payload = _payload(
        [
            {
                "id": "",  # tom ID droppes
                "mag": 5.0,
                "lat": -23.5,
                "lon": -70.4,
                "time": datetime(2026, 4, 25, tzinfo=timezone.utc),
            }
        ]
    )
    df = parse_usgs_geojson(payload)
    assert df.empty


def test_skips_event_without_magnitude() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "us_no_mag",
                "type": "Feature",
                "properties": {"mag": None, "time": _ts_ms(datetime.now(timezone.utc))},
                "geometry": {"type": "Point", "coordinates": [-70.0, -23.0, 30.0]},
            }
        ],
    }
    df = parse_usgs_geojson(payload)
    assert df.empty


def test_skips_event_without_time() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "us_no_time",
                "type": "Feature",
                "properties": {"mag": 5.0, "time": None},
                "geometry": {"type": "Point", "coordinates": [-70.0, -23.0, 30.0]},
            }
        ],
    }
    df = parse_usgs_geojson(payload)
    assert df.empty


def test_handles_missing_depth() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "us_no_depth",
                "type": "Feature",
                "properties": {
                    "mag": 5.0,
                    "time": _ts_ms(datetime(2026, 4, 25, tzinfo=timezone.utc)),
                },
                "geometry": {"type": "Point", "coordinates": [-70.0, -23.0]},  # 2 coords
            }
        ],
    }
    df = parse_usgs_geojson(payload)
    assert len(df) == 1
    assert pd.isna(df["depth_km"].iloc[0])


def test_raises_on_non_dict_payload() -> None:
    with pytest.raises(ValueError, match="not dict"):
        parse_usgs_geojson([1, 2, 3])


def test_raises_on_missing_features() -> None:
    with pytest.raises(ValueError, match="missing 'features'"):
        parse_usgs_geojson({"type": "FeatureCollection", "features": "wrong"})


def test_handles_empty_features() -> None:
    df = parse_usgs_geojson({"type": "FeatureCollection", "features": []})
    assert df.empty
    assert list(df.columns) == list(SEISMIC_EVENTS_COLS)


# ---------------------------------------------------------------------------
# fetch_seismic_remote
# ---------------------------------------------------------------------------


def test_remote_via_injection() -> None:
    payload = _payload(
        [
            {
                "id": "us_test",
                "mag": 5.4,
                "lat": -23.5,
                "lon": -70.4,
                "time": datetime(2026, 4, 25, tzinfo=timezone.utc),
            }
        ]
    )
    df = fetch_seismic_remote(raw_response=payload)
    assert len(df) == 1


# ---------------------------------------------------------------------------
# fetch_seismic_manual
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_missing(tmp_path: Path) -> None:
    df = fetch_seismic_manual(tmp_path / "nope.csv")
    assert df.empty


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv = tmp_path / "seismic_events.csv"
    pd.DataFrame(
        [
            {
                "event_id": "manual_001",
                "event_ts": "2026-04-25T08:30:00Z",
                "magnitude": 6.0,
                "latitude": -23.0,
                "longitude": -70.0,
                "depth_km": 30.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": "https://example.com/x",
            }
        ]
    ).to_csv(csv, index=False)

    df = fetch_seismic_manual(csv)
    assert len(df) == 1
    assert df["magnitude"].iloc[0] == 6.0


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("event_id,magnitude\nx,5.0\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_seismic_manual(csv)


# ---------------------------------------------------------------------------
# fetch_seismic (combined)
# ---------------------------------------------------------------------------


def test_combined_uses_remote_when_available(tmp_path: Path) -> None:
    df_remote = pd.DataFrame(
        [
            {
                "event_id": "from_api",
                "event_ts": pd.Timestamp("2026-04-25T08:30:00Z"),
                "magnitude": 5.5,
                "latitude": -23.5,
                "longitude": -70.4,
                "depth_km": 30.0,
                "place": "API",
                "region": "Chile / Peru",
                "url": "https://example.com/api",
            }
        ]
    )
    with patch("bedrock.fetch.seismic.fetch_seismic_remote", return_value=df_remote):
        df = fetch_seismic(csv_path=tmp_path / "missing.csv")
    assert df["event_id"].iloc[0] == "from_api"


def test_combined_falls_back_to_csv(tmp_path: Path) -> None:
    csv = tmp_path / "seismic.csv"
    pd.DataFrame(
        [
            {
                "event_id": "from_csv",
                "event_ts": "2026-04-25T08:30:00Z",
                "magnitude": 5.5,
                "latitude": -23.0,
                "longitude": -70.0,
                "depth_km": 30.0,
                "place": "CSV",
                "region": "Chile / Peru",
                "url": "https://example.com/csv",
            }
        ]
    ).to_csv(csv, index=False)

    with patch(
        "bedrock.fetch.seismic.fetch_seismic_remote",
        side_effect=RuntimeError("USGS down"),
    ):
        df = fetch_seismic(csv_path=csv)
    assert df["event_id"].iloc[0] == "from_csv"


def test_combined_returns_empty_when_both_fail(tmp_path: Path) -> None:
    with patch(
        "bedrock.fetch.seismic.fetch_seismic_remote",
        side_effect=RuntimeError("USGS down"),
    ):
        df = fetch_seismic(csv_path=tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == list(SEISMIC_EVENTS_COLS)
