"""Tester for NOAA ONI ENSO-fetcher (Fase 10 ADR-005).

Dekker parsing av ASCII-format mot statisk fixture (ingen ekte HTTP).
"""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.fetch.enso import (
    NOAA_ONI_SERIES_ID,
    NoaaOniFetchError,
    fetch_noaa_oni,
    parse_noaa_oni_text,
)

# Lite utdrag fra reelt NOAA-format. Kommentarer er ikke en del av reelle filer.
SAMPLE_TEXT = """SEAS  YR  TOTAL  ANOM
 DJF 1950  24.55 -1.53
 JFM 1950  24.74 -1.34
 FMA 1950  25.43 -1.16
 NDJ 1950  24.10 -1.16
 DJF 2024  26.40  1.94
 JFM 2024  26.81  1.49
"""


def test_parse_basic() -> None:
    df = parse_noaa_oni_text(SAMPLE_TEXT)
    assert list(df.columns) == ["series_id", "date", "value"]
    assert len(df) == 6
    assert (df["series_id"] == NOAA_ONI_SERIES_ID).all()


def test_parse_seas_to_month_mapping() -> None:
    df = parse_noaa_oni_text(SAMPLE_TEXT)
    # DJF 1950 → 1950-01-01
    assert df.loc[0, "date"] == "1950-01-01"
    # JFM 1950 → 1950-02-01
    assert df.loc[1, "date"] == "1950-02-01"
    # FMA 1950 → 1950-03-01
    assert df.loc[2, "date"] == "1950-03-01"
    # NDJ 1950 → 1950-12-01 (midt = Des inneværende år)
    assert df.loc[3, "date"] == "1950-12-01"


def test_parse_value_correctly_converted() -> None:
    df = parse_noaa_oni_text(SAMPLE_TEXT)
    assert df.loc[0, "value"] == pytest.approx(-1.53)
    assert df.loc[4, "value"] == pytest.approx(1.94)


def test_parse_skips_header() -> None:
    df = parse_noaa_oni_text(SAMPLE_TEXT)
    # Ingen rad har 'SEAS' som dato
    assert "SEAS" not in df["date"].tolist()


def test_parse_skips_blank_and_short_lines() -> None:
    text = """SEAS  YR  TOTAL  ANOM
 DJF 1950  24.55 -1.53

 short line
 JFM 1950  24.74 -1.34
"""
    df = parse_noaa_oni_text(text)
    assert len(df) == 2


def test_parse_skips_missing_marker() -> None:
    text = """SEAS  YR  TOTAL  ANOM
 DJF 2026  26.10 -99.9
 JFM 2026  26.20  1.50
"""
    df = parse_noaa_oni_text(text)
    assert len(df) == 1
    assert df.loc[0, "value"] == pytest.approx(1.50)


def test_parse_skips_unparseable_value(caplog: pytest.LogCaptureFixture) -> None:
    text = """SEAS  YR  TOTAL  ANOM
 DJF 1950  24.55 NOT_A_NUMBER
 JFM 1950  24.74 -1.34
"""
    with caplog.at_level("WARNING"):
        df = parse_noaa_oni_text(text)
    assert len(df) == 1
    # Verifiser at unparseable-linja ble logget
    assert any("noaa_oni" in rec.message for rec in caplog.records)


def test_parse_empty_text_returns_empty_frame() -> None:
    df = parse_noaa_oni_text("")
    assert df.empty
    assert list(df.columns) == ["series_id", "date", "value"]


def test_parse_only_header_returns_empty() -> None:
    df = parse_noaa_oni_text("SEAS  YR  TOTAL  ANOM\n")
    assert df.empty


def test_parse_output_compatible_with_fundamentals_schema() -> None:
    """Output skal kunne pipes direkte til append_fundamentals
    (kolonner series_id, date, value) — ADR-005 B1."""
    df = parse_noaa_oni_text(SAMPLE_TEXT)
    # Sjekker at vi kan caste til Pydantic FredSeriesRow uten endring
    from datetime import date as _date

    from bedrock.data.schemas import FredSeriesRow

    for _, row in df.iterrows():
        validated = FredSeriesRow(
            series_id=row["series_id"],
            date=_date.fromisoformat(row["date"]),
            value=float(row["value"]),
        )
        assert validated.series_id == NOAA_ONI_SERIES_ID


def test_fetch_noaa_oni_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_noaa_oni: monkey-patche http_get_with_retry, ingen ekte HTTP."""

    class FakeResp:
        status_code = 200
        text = SAMPLE_TEXT

    monkeypatch.setattr(
        "bedrock.fetch.enso.http_get_with_retry",
        lambda url, **kwargs: FakeResp(),
    )
    df = fetch_noaa_oni()
    assert len(df) == 6
    assert df.loc[0, "series_id"] == NOAA_ONI_SERIES_ID


def test_fetch_noaa_oni_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 503
        text = "service unavailable"

    monkeypatch.setattr(
        "bedrock.fetch.enso.http_get_with_retry",
        lambda url, **kwargs: FakeResp(),
    )
    with pytest.raises(NoaaOniFetchError, match="503"):
        fetch_noaa_oni()


def test_fetch_noaa_oni_network_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, **kwargs: object) -> object:
        raise ConnectionError("network down")

    monkeypatch.setattr("bedrock.fetch.enso.http_get_with_retry", boom)
    with pytest.raises(NoaaOniFetchError, match="Network failure"):
        fetch_noaa_oni()


def test_fetch_noaa_oni_appendable_to_store(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Integrasjon: fetcher → DataStore.append_fundamentals → get_fundamentals."""
    from bedrock.data.store import DataStore

    class FakeResp:
        status_code = 200
        text = SAMPLE_TEXT

    monkeypatch.setattr(
        "bedrock.fetch.enso.http_get_with_retry",
        lambda url, **kwargs: FakeResp(),
    )

    store = DataStore(tmp_path / "bedrock.db")
    df = fetch_noaa_oni()
    n = store.append_fundamentals(df)
    assert n == 6

    series = store.get_fundamentals(NOAA_ONI_SERIES_ID)
    assert len(series) == 6
    # DJF 1950 → 1950-01-01
    assert series.index[0] == pd.Timestamp("1950-01-01")
    assert series.iloc[0] == pytest.approx(-1.53)
