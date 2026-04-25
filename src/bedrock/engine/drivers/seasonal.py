"""Sesongbasert driver (Sub-fase 12.5 session 74).

Erstatter ``sma200_align``-placeholder i agri-instrumentenes outlook-
familie. Returnerer 0..1-score basert på hvilken måned vi er i,
matcht mot crop-spesifikk kalender.

For Corn (US cornbelt-eksempel):
    Apr-May: planting (vær-sensitivt, høy yield-usikkerhet)
    Jun-Jul: silking/pollination (yield-determinerende)
    Aug-Sep: maturing
    Oct-Nov: harvest (supply-pressure)
    Dec-Mar: storage/inactive (lite signal)

Driveren er asset-class-agnostic — caller spesifiserer
``monthly_scores`` (12-element-liste, indeks 0=januar, 11=desember).
Dette lar Cotton, Wheat, Coffee bruke samme driver med ulike
kalendere uten egen kode.

Eksempel YAML for Corn outlook-familie:

    - name: seasonal_stage
      weight: 1.0
      params:
        # Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
        monthly_scores: [0.3, 0.3, 0.4, 0.6, 0.7, 1.0, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3]
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# Default-kalender for nordlig-halvkule grain crops (US cornbelt).
# Apr-Jul er bull-active (planting + yield-determinerende periode);
# Oct-Mar er low-signal-perioden.
_DEFAULT_MONTHLY_SCORES_NH_GRAIN: list[float] = [
    0.3,  # Jan
    0.3,  # Feb
    0.4,  # Mar
    0.6,  # Apr (planting starter)
    0.7,  # May (planting fortsetter)
    1.0,  # Jun (silking)
    1.0,  # Jul (silking/yield-determinerende)
    0.8,  # Aug (maturing)
    0.6,  # Sep (maturing)
    0.5,  # Oct (harvest)
    0.4,  # Nov (harvest avslutter)
    0.3,  # Dec
]


@register("seasonal_stage")
def seasonal_stage(store: Any, instrument: str, params: dict) -> float:
    """Returner score basert på gjeldende måned vs ``monthly_scores``-tabell.

    Params:
        monthly_scores: 12-element-liste (eller None for å bruke
            ``_DEFAULT_MONTHLY_SCORES_NH_GRAIN``). Indeks 0 = januar.
            Verdier klippes til [0..1].
        as_of: optional ``date`` eller ISO-streng for testbarhet
            (default: ``date.today()``).

    Returns:
        Score 0..1 for nåværende måned. Returnerer 0.0 ved ugyldig
        params.
    """
    scores = params.get("monthly_scores")
    if scores is None:
        scores = _DEFAULT_MONTHLY_SCORES_NH_GRAIN

    if not isinstance(scores, list) or len(scores) != 12:
        _log.warning(
            "seasonal_stage.invalid_monthly_scores",
            instrument=instrument,
            n=len(scores) if isinstance(scores, list) else None,
        )
        return 0.0

    as_of = params.get("as_of")
    if as_of is None:
        today = date.today()
    elif isinstance(as_of, date):
        today = as_of
    else:
        try:
            today = date.fromisoformat(str(as_of))
        except ValueError:
            _log.warning(
                "seasonal_stage.invalid_as_of",
                instrument=instrument,
                as_of=as_of,
            )
            return 0.0

    month_idx = today.month - 1
    raw = float(scores[month_idx])
    return max(0.0, min(1.0, raw))


__all__ = ["seasonal_stage"]
