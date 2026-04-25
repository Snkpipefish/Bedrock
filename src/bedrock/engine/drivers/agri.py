"""Agri-familie drivere (Sub-fase 12.5 session 72 / Block B).

Erstatter ``sma200_align``-placeholder i agri-instrumentenes weather +
enso-familier. Bruker ``DataStore.get_weather_monthly()`` (15+ års
historikk per region) og NOAA ONI fra fundamentals-tabellen.

Drivere implementert:

- ``weather_stress``: kombinerer ``hot_days`` + ``dry_days`` + (negativ)
  ``water_bal`` til en 0..1-stress-score. Asset-class-agnostic — for
  Corn er høy stress = bull (lavere yield-forventning → høyere pris).
  For andre crops (irrigert ris, irrigert hvete) kan tolkningen være
  motsatt og må håndteres via ``invert``-param i YAML.

- ``enso_regime``: klassifiserer NOAA ONI til La Niña / nøytral /
  El Niño. Mappet til 0..1 via params. Default tolker La Niña som
  bull (US-drought-risk → Corn). ``invert=True`` for crops som
  nyter godt av El Niño (f.eks. Argentinsk hvete).

Begge drivere er defensive: feil i instrument-lookup, manglende data
eller utilstrekkelig historikk → 0.0 + log.

Driver-signatur per ``engine/drivers/__init__.py``-kontrakten.
"""

from __future__ import annotations

from typing import Any

import structlog

from bedrock.engine.drivers import register

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Felles helper: instrument → weather_region
# ---------------------------------------------------------------------------


def _resolve_weather_region(instrument: str) -> str | None:
    """Slå opp ``weather_region`` fra instrument-config.

    Returnerer regionnavn eller ``None`` hvis lookup feiler.
    Lazy-import (samme mønster som ``analog.py`` og ``positioning.py``).
    """
    from bedrock.cli._instrument_lookup import find_instrument

    try:
        cfg = find_instrument(instrument, "config/instruments")
    except Exception as exc:
        _log.warning(
            "agri.instrument_lookup_failed",
            instrument=instrument,
            error=str(exc),
        )
        return None

    region = cfg.instrument.weather_region
    if not region:
        _log.debug("agri.no_weather_region", instrument=instrument)
        return None
    return region


# ---------------------------------------------------------------------------
# weather_stress
# ---------------------------------------------------------------------------


# Stress-koeffisienter for kombinert score. Tunet for å gi rimelig
# fordeling: ekstreme måneder (>20 hot_days, >25 dry_days, water_bal
# < -100mm) skal gi score nær 1.0.
_DEFAULT_STRESS_WEIGHTS = {
    "hot_days": 0.4,  # multipliseres med hot_days/30
    "dry_days": 0.4,  # multipliseres med dry_days/31 (typisk maxdager)
    "water_bal": 0.2,  # negativ water_bal = stress; klippet til [-150, 0] / 150
}


@register("weather_stress")
def weather_stress(store: Any, instrument: str, params: dict) -> float:
    """Kombinert vær-stress-score (0..1) basert på siste måned i regionen.

    Score = w1 × min(1, hot_days/30) + w2 × min(1, dry_days/31)
            + w3 × min(1, max(0, -water_bal/150))

    Default-vekter: hot=0.4, dry=0.4, water=0.2 (sum=1).

    Params:
        weights: optional ``{"hot_days": w1, "dry_days": w2,
            "water_bal": w3}`` for å overstyre default-vekter.
            Vekter normaliseres ikke automatisk — caller må sørge
            for at sum ≤ 1 hvis output skal holdes i [0..1].
        invert: ``False`` (default) — høy stress = høy score.
            ``True`` for crops der lite stress er bull.
        lookback_months: hvor mange måneder data som kreves for
            å returnere score (default 1 — siste måned).

    Defensiv 0.0-retur ved manglende region, manglende data, eller
    månedstall som ikke kan parses.
    """
    region = _resolve_weather_region(instrument)
    if region is None:
        return 0.0

    lookback = int(params.get("lookback_months", 1))
    invert = bool(params.get("invert", False))
    weights = params.get("weights") or _DEFAULT_STRESS_WEIGHTS

    try:
        df = store.get_weather_monthly(region, last_n=lookback)
    except KeyError:
        _log.warning(
            "weather_stress.no_data",
            instrument=instrument,
            region=region,
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "weather_stress.fetch_failed",
            instrument=instrument,
            region=region,
            error=str(exc),
        )
        return 0.0

    if df.empty:
        return 0.0

    latest = df.iloc[-1]

    hot = float(latest.get("hot_days") or 0)
    dry = float(latest.get("dry_days") or 0)
    water = latest.get("water_bal")
    water_val = float(water) if water is not None else 0.0

    hot_norm = min(1.0, hot / 30.0)
    dry_norm = min(1.0, dry / 31.0)
    # Negativ water_bal = mangel = stress. Klippet til [-150, 0]/150.
    water_norm = min(1.0, max(0.0, -water_val / 150.0))

    w_hot = float(weights.get("hot_days", 0.4))
    w_dry = float(weights.get("dry_days", 0.4))
    w_water = float(weights.get("water_bal", 0.2))

    score = w_hot * hot_norm + w_dry * dry_norm + w_water * water_norm
    score = max(0.0, min(1.0, score))

    if invert:
        return round(1.0 - score, 4)
    return round(score, 4)


# ---------------------------------------------------------------------------
# enso_regime
# ---------------------------------------------------------------------------


# Default ENSO-thresholds (NOAA ONI):
# ONI ≤ -0.5  = La Niña
# -0.5 < ONI < +0.5 = nøytral
# ONI ≥ +0.5  = El Niño
#
# Default-mapping (Corn-tolkning):
# La Niña sterk (ONI ≤ -1.0)  → 1.0 (US-drought-risk → bull Corn)
# La Niña moderat (-1.0..-0.5) → 0.75
# Nøytral                       → 0.5
# El Niño moderat (+0.5..+1.0) → 0.25
# El Niño sterk (ONI ≥ +1.0)   → 0.0
_DEFAULT_ENSO_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (-1.0, 1.0),
    (-0.5, 0.75),
    (0.5, 0.5),
    (1.0, 0.25),
)


@register("enso_regime")
def enso_regime(store: Any, instrument: str, params: dict) -> float:
    """ENSO-regime fra NOAA ONI, mappet til 0..1.

    Params:
        series: FRED-serie (default ``NOAA_ONI``)
        invert: ``False`` (default — La Niña er bull) eller ``True``
            (El Niño er bull, f.eks. for argentinsk hvete).
        thresholds: optional override-liste av ``[[oni_max, score], ...]``
            tolket som "ONI ≤ oni_max → score" (siden ONI er
            monotont fra mest-La Niña til mest-El Niño).

    Default-mapping (asset = Corn): La Niña = bull = høy score,
    El Niño = bear = lav score.
    """
    series_id = params.get("series", "NOAA_ONI")
    invert = bool(params.get("invert", False))

    try:
        series = store.get_fundamentals(series_id).dropna()
    except KeyError:
        _log.warning(
            "enso_regime.series_missing",
            instrument=instrument,
            series=series_id,
        )
        return 0.0
    except Exception as exc:
        _log.warning(
            "enso_regime.fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return 0.0

    if series.empty:
        return 0.0

    current = float(series.iloc[-1])

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_ENSO_THRESHOLDS
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    # ONI er monotont: gå fra laveste (mest-La Niña) opp mot høyeste.
    score = 0.0
    matched = False
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            matched = True
            break
    if not matched:
        # Verdi over alle tersklene (sterk El Niño) → 0.0
        score = 0.0

    if invert:
        return round(1.0 - score, 4)
    return round(score, 4)


__all__ = ["enso_regime", "weather_stress"]
