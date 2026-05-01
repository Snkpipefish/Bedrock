"""Tests for sub-fase 12.10 Bunke 1 Bug-1: COT/AAII release-calendar
konvensjoner brukt av AsOfDateStore for look-ahead-fri backtest."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from bedrock.data.release_calendar import (
    aaii_released_at,
    aaii_released_at_iso,
    cot_released_at,
    cot_released_at_iso,
)

# ---------------------------------------------------------------------------
# COT (CFTC + ICE + Euronext): tirsdag report_date → fredag 21:00 UTC release
# ---------------------------------------------------------------------------


def test_cot_released_at_tuesday_returns_friday_21_utc() -> None:
    # 2026-04-28 er en tirsdag (CFTC-snapshot-dag)
    report_date = date(2026, 4, 28)
    released = cot_released_at(report_date)
    # +3 dager = fredag, 21:00 UTC = 17:00 ET DST = strict-konservativt etter
    # 15:30 ET-publisering
    assert released == datetime(2026, 5, 1, 21, 0, 0)


def test_cot_released_at_accepts_datetime() -> None:
    report_date = datetime(2026, 4, 28, 15, 30)
    released = cot_released_at(report_date)
    assert released == datetime(2026, 5, 1, 21, 0, 0)


def test_cot_released_at_accepts_pandas_timestamp() -> None:
    report_date = pd.Timestamp("2026-04-28")
    released = cot_released_at(report_date)
    assert released == datetime(2026, 5, 1, 21, 0, 0)


def test_cot_released_at_returns_naive_datetime() -> None:
    released = cot_released_at(date(2026, 4, 28))
    assert released.tzinfo is None


def test_cot_released_at_iso_format() -> None:
    iso = cot_released_at_iso(date(2026, 4, 28))
    # SQLite-vennlig ISO 8601 med sekund-presisjon, mellomrom-separator
    assert iso == "2026-05-01 21:00:00"


def test_cot_released_at_year_boundary() -> None:
    # report_date torsdag siste uke 2025 → released 2026 (3 dagers offset)
    report_date = date(2025, 12, 30)  # tirsdag
    released = cot_released_at(report_date)
    assert released == datetime(2026, 1, 2, 21, 0, 0)


# ---------------------------------------------------------------------------
# AAII: onsdag survey-date → torsdag 14:00 UTC release
# ---------------------------------------------------------------------------


def test_aaii_released_at_wednesday_returns_thursday_14_utc() -> None:
    # 2026-04-29 er onsdag (AAII-survey-dag)
    survey_date = date(2026, 4, 29)
    released = aaii_released_at(survey_date)
    # +1 dag = torsdag, 14:00 UTC = ~10am ET
    assert released == datetime(2026, 4, 30, 14, 0, 0)


def test_aaii_released_at_iso_format() -> None:
    iso = aaii_released_at_iso(date(2026, 4, 29))
    assert iso == "2026-04-30 14:00:00"


def test_aaii_released_at_returns_naive_datetime() -> None:
    released = aaii_released_at(date(2026, 4, 29))
    assert released.tzinfo is None


# ---------------------------------------------------------------------------
# Look-ahead-fri-egenskaper (sentral invariant for backtest)
# ---------------------------------------------------------------------------


def test_cot_released_at_strictly_after_report_date() -> None:
    """En COT-rapport er aldri tilgjengelig samme dag som snapshot."""
    report_date = date(2026, 4, 28)
    released = cot_released_at(report_date)
    assert released.date() > report_date


def test_aaii_released_at_strictly_after_survey_date() -> None:
    """AAII-rapport er aldri tilgjengelig samme dag som survey-close."""
    survey_date = date(2026, 4, 29)
    released = aaii_released_at(survey_date)
    assert released.date() > survey_date
