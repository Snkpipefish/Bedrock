"""Publikasjons-tidspunkt-konvensjoner for forsinket-publiserte rapporter.

Sub-fase 12.10 Bunke 1 Bug-1: COT-rapporter publiseres med ~3 dagers
etterslep (CFTC fredag 15:30 ET for tirsdag-snapshot). AAII publiseres
torsdag formiddag for onsdag-snapshot. AsOfDateStore må filtrere på
faktisk publiserings-tidspunkt, ikke `report_date`, for å unngå
look-ahead i backtest.

Modulen eksponerer rene konvensjons-funksjoner — ingen DB-lookup,
ingen tz-databaser. Vi gir en konservativ buffer mot DST og publiserings-
forsinkelser slik at backtest aldri ser data før det realistisk var
tilgjengelig.

Konvensjoner:
- CFTC (disaggregated/legacy/TFF) + ICE + Euronext: report_date (Tue) +
  3 dager @ 21:00 UTC. Buffer mot 15:30 ET (= 19:30/20:30 UTC vinter/DST)
  + ICE/Euronext-publikasjoner senere på fredag.
- AAII: survey_date (Wed) + 1 dag @ 14:00 UTC. AAII publiserer torsdag
  ~10am ET (= 14:00/15:00 UTC).

Disse er bevisst konservative; en backtest som ser raden 1-2 timer
senere enn faktisk publisering er fortsatt look-ahead-fri.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

# Konvensjons-konstanter — endres aldri uten å regenerere baseline.
_COT_RELEASE_LAG_DAYS = 3
_COT_RELEASE_TIME_UTC = time(hour=21, minute=0)

_AAII_RELEASE_LAG_DAYS = 1
_AAII_RELEASE_TIME_UTC = time(hour=14, minute=0)


def cot_released_at(report_date: date | datetime | pd.Timestamp) -> datetime:
    """Returner naive UTC datetime når en COT-rapport for ``report_date``
    realistisk var publisert.

    Aksepterer både ``date``, ``datetime`` og ``pd.Timestamp``. Returnerer
    naive ``datetime`` på UTC for sammenligning med
    ``AsOfDateStore._as_of`` (som også er naive UTC).
    """
    d = _to_date(report_date)
    released = datetime.combine(d, _COT_RELEASE_TIME_UTC, tzinfo=timezone.utc)
    released = released + timedelta(days=_COT_RELEASE_LAG_DAYS)
    # Returnér naive (tz-stripped) for konsistens med AsOfDateStore-internals
    return released.replace(tzinfo=None)


def aaii_released_at(survey_date: date | datetime | pd.Timestamp) -> datetime:
    """Returner naive UTC datetime når en AAII-survey for ``survey_date``
    realistisk var publisert (torsdag ~14:00 UTC = ~10am ET)."""
    d = _to_date(survey_date)
    released = datetime.combine(d, _AAII_RELEASE_TIME_UTC, tzinfo=timezone.utc)
    released = released + timedelta(days=_AAII_RELEASE_LAG_DAYS)
    return released.replace(tzinfo=None)


def cot_released_at_iso(report_date: date | datetime | pd.Timestamp) -> str:
    """ISO 8601-streng for SQLite-lagring (sekund-presisjon, ingen tz-suffix)."""
    return cot_released_at(report_date).isoformat(sep=" ", timespec="seconds")


def aaii_released_at_iso(survey_date: date | datetime | pd.Timestamp) -> str:
    return aaii_released_at(survey_date).isoformat(sep=" ", timespec="seconds")


def _to_date(value: date | datetime | pd.Timestamp) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    return value
