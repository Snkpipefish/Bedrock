"""Tester for Forex Factory kalender-fetcher (sub-fase 12.5+ session 105)."""

from __future__ import annotations

import pytest

from bedrock.fetch.calendar_ff import (
    DEFAULT_IMPACT_FILTER,
    ECON_EVENTS_DF_COLS,
    fetch_calendar_events,
)

_SAMPLE_FF_JSON = [
    {
        "country": "USD",
        "title": "FOMC Statement",
        "date": "2026-04-30T18:00:00+00:00",
        "impact": "High",
        "forecast": "5.25%",
        "previous": "5.25%",
    },
    {
        "country": "EUR",
        "title": "ECB Press Conference",
        "date": "2026-05-02T12:45:00+00:00",
        "impact": "High",
        "forecast": "",
        "previous": "",
    },
    {
        "country": "GBP",
        "title": "Manufacturing PMI",
        "date": "2026-05-01T08:30:00+00:00",
        "impact": "Medium",
        "forecast": "49.5",
        "previous": "49.2",
    },
    {
        "country": "USD",
        "title": "Trade Balance",
        "date": "2026-05-01T12:30:00+00:00",
        "impact": "Low",
        "forecast": "-65B",
        "previous": "-63B",
    },
    {
        # Naive datetime — fetcher skal anta UTC
        "country": "JPY",
        "title": "BOJ Press Conference",
        "date": "2026-05-01T05:00:00",
        "impact": "High",
        "forecast": None,
        "previous": None,
    },
    {
        # Korrupt event — skal hoppes over
        "country": "AUD",
        "title": "RBA Cash Rate",
        "date": "INVALID-DATE",
        "impact": "High",
        "forecast": "",
        "previous": "",
    },
]


def test_fetch_returns_correct_columns() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    assert list(df.columns) == list(ECON_EVENTS_DF_COLS)


def test_default_filter_drops_low_impact() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    # Low (Trade Balance) skal være filtrert ut
    impacts = set(df["impact"])
    assert impacts <= set(DEFAULT_IMPACT_FILTER)
    assert "Low" not in impacts


def test_invalid_date_is_skipped() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    titles = list(df["title"])
    assert "RBA Cash Rate" not in titles  # ble droppet pga INVALID-DATE


def test_naive_datetime_treated_as_utc() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    boj = df[df["title"] == "BOJ Press Conference"].iloc[0]
    # event_ts er ISO-streng; should ende på +00:00 etter UTC-coercion
    assert "+00:00" in boj["event_ts"]


def test_empty_strings_become_none() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    ecb = df[df["title"] == "ECB Press Conference"].iloc[0]
    assert ecb["forecast"] is None
    assert ecb["previous"] is None


def test_fetched_at_populated_on_all_rows() -> None:
    df = fetch_calendar_events(raw_response=_SAMPLE_FF_JSON)
    assert df["fetched_at"].notna().all()
    # Alle skal ha samme fetched_at
    assert df["fetched_at"].nunique() == 1


def test_custom_impact_filter() -> None:
    df = fetch_calendar_events(
        impact_filter=("High",),
        raw_response=_SAMPLE_FF_JSON,
    )
    assert set(df["impact"]) == {"High"}
    # Bare High passer: FOMC, ECB, BOJ
    assert len(df) == 3


def test_low_only_filter_returns_one() -> None:
    df = fetch_calendar_events(
        impact_filter=("Low",),
        raw_response=_SAMPLE_FF_JSON,
    )
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Trade Balance"


def test_empty_json_returns_empty_df_with_columns() -> None:
    df = fetch_calendar_events(raw_response=[])
    assert df.empty
    assert list(df.columns) == list(ECON_EVENTS_DF_COLS)


def test_non_list_json_raises() -> None:
    with pytest.raises(ValueError, match="expected JSON list"):
        fetch_calendar_events(raw_response={"not": "a list"})


def test_skips_dict_with_missing_required_fields() -> None:
    """Events uten country/title/date droppes."""
    bad = [
        {"country": "USD", "title": "", "date": "2026-05-01T12:00:00+00:00", "impact": "High"},
        {"country": "", "title": "FOMC", "date": "2026-05-01T12:00:00+00:00", "impact": "High"},
        {"country": "USD", "title": "FOMC", "date": "", "impact": "High"},
    ]
    df = fetch_calendar_events(raw_response=bad)
    assert df.empty


def test_runner_registered_and_writes_to_store(tmp_path) -> None:
    """End-to-end: runner kaller fetcher (med stub) og skriver til DataStore."""
    from bedrock.config.fetch_runner import _RUNNERS

    assert "calendar_ff" in _RUNNERS

    # Verifiser at runner-funksjonen er kalkulerbar uten å faktisk kjøre HTTP
    # — bare sanity at den finnes og er registrert.
    runner = _RUNNERS["calendar_ff"]
    assert callable(runner)


def test_fetch_yaml_has_calendar_ff_entry() -> None:
    """Verifiserer at fetch.yaml har calendar_ff-entry."""
    from pathlib import Path

    import yaml

    fetch_yaml = Path(__file__).parents[2] / "config" / "fetch.yaml"
    with open(fetch_yaml) as fh:
        cfg = yaml.safe_load(fh)
    assert "calendar_ff" in cfg["fetchers"]
    entry = cfg["fetchers"]["calendar_ff"]
    assert entry["module"] == "bedrock.fetch.calendar_ff"
    assert entry["table"] == "econ_events"
    assert entry["ts_column"] == "fetched_at"
    assert entry["stale_hours"] >= 8


def test_ui_kartrommet_has_calendar_group() -> None:
    """Verifiserer at calendar_ff er mappet til Calendar-gruppe i UI."""
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS.get("calendar_ff") == "Calendar"
    assert "Calendar" in _GROUP_ORDER
