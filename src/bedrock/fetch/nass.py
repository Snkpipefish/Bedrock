# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs typer DataFrame-konstruktor med columns=list[str] dårlig.

"""USDA NASS Crop Progress fetcher (PLAN § 7.3 Fase-4).

Henter ukentlig crop-progress-data (% planted, silking, harvested, good/
excellent condition) fra USDA's NASS QuickStats API.

API-nøkkel: oppslag-rekkefølge (samme mønster som FRED-fetcher):
1. CLI-arg / `api_key`-param,
2. env-var ``BEDROCK_NASS_API_KEY``,
3. ``~/.bedrock/secrets.env`` (KEY=VALUE).

Registrer gratis på https://quickstats.nass.usda.gov/api (krever
email-bekreftelse).

Manuell CSV-fallback: hvis ingen key er funnet, leser fra
``data/manual/crop_progress.csv`` (samme schema som
``CROP_PROGRESS_COLS``). Bruker kan populere manuelt hvis API-key ikke
er tilgjengelig.

Bruk:

    from bedrock.fetch.nass import fetch_crop_progress
    df = fetch_crop_progress(
        commodities=["CORN", "SOYBEANS", "WHEAT", "COTTON"],
        years=[2024, 2025, 2026],
    )
    store.append_crop_progress(df)
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import structlog

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import CROP_PROGRESS_COLS

NASS_API_KEY_ENV = "BEDROCK_NASS_API_KEY"

_log = structlog.get_logger(__name__)

_NASS_BASE = "https://quickstats.nass.usda.gov/api/api_GET/"
_DEFAULT_TIMEOUT = 30
_MANUAL_CSV = Path("data/manual/crop_progress.csv")

# NASS-filtre per metric. Bruker `statisticcat_desc + unit_desc`-paret
# istedenfor `short_desc` fordi short_desc inkluderer commodity-prefix
# som varierer (CORN - ..., CORN, GRAIN - ..., WHEAT, SPRING, (EXCL DURUM) - ...).
# statisticcat_desc + unit_desc er commodity-agnostisk per NASS API-doc:
# https://quickstats.nass.usda.gov/api#param_define.
#
# Sammensatte metrics (GOOD_EXCELLENT = GOOD + EXCELLENT, ingen single
# unit_desc) hentes som to separate calls + summeres per week_ending.
_METRIC_FILTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "PLANTED": (("PROGRESS", "PCT PLANTED"),),
    "SILKING": (("PROGRESS", "PCT SILKING"),),
    "HEADING": (("PROGRESS", "PCT HEADED"),),
    "BLOOMING": (("PROGRESS", "PCT BLOOMING"),),
    "SQUARING": (("PROGRESS", "PCT SQUARING"),),
    "HARVESTED": (("PROGRESS", "PCT HARVESTED"),),
    "GOOD_EXCELLENT": (
        ("CONDITION", "PCT GOOD"),
        ("CONDITION", "PCT EXCELLENT"),
    ),
}

# Per-commodity hvilke metrics er meningsfulle. NASS QuickStats returnerer
# 400 Bad Request hvis (commodity, statisticcat, unit) ikke eksisterer
# (f.eks. WHEAT × SILKING). Maser fra USDA Crop Progress definitions:
# - CORN: planted, silking (blomstring), harvested, good/excellent
# - SOYBEANS: planted, blooming, harvested, good/excellent
# - WHEAT: planted, headed (heading), harvested, good/excellent
# - COTTON: planted, squaring, harvested, good/excellent
_VALID_METRICS_PER_COMMODITY: dict[str, frozenset[str]] = {
    "CORN": frozenset({"PLANTED", "SILKING", "HARVESTED", "GOOD_EXCELLENT"}),
    "SOYBEANS": frozenset({"PLANTED", "BLOOMING", "HARVESTED", "GOOD_EXCELLENT"}),
    "WHEAT": frozenset({"PLANTED", "HEADING", "HARVESTED", "GOOD_EXCELLENT"}),
    "COTTON": frozenset({"PLANTED", "SQUARING", "HARVESTED", "GOOD_EXCELLENT"}),
}


def fetch_crop_progress_api(
    *,
    commodities: Iterable[str],
    years: Iterable[int],
    metrics: Iterable[str] | None = None,
    api_key: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Hent crop-progress fra NASS QuickStats API.

    Args:
        commodities: NASS-kode for crops ("CORN", "SOYBEANS", "WHEAT", "COTTON").
        years: List of years to fetch.
        metrics: Whitelist av metrics (default = alle 4).
        api_key: Override env-var.
        timeout: HTTP-timeout per kall.

    Returns:
        DataFrame med kolonner = ``CROP_PROGRESS_COLS``.

    Raises:
        ValueError: hvis api_key ikke er gitt og BEDROCK_NASS_API_KEY mangler.
        requests.HTTPError: ved API-feil.
    """
    api_key = api_key or get_secret(NASS_API_KEY_ENV)
    if not api_key:
        raise ValueError(
            "BEDROCK_NASS_API_KEY er ikke satt. Registrer gratis på "
            "https://quickstats.nass.usda.gov/api og eksporter env-var."
        )

    metrics = list(metrics) if metrics else list(_METRIC_FILTERS.keys())
    # Per-(commodity, metric, week_ending) accumulator. For GOOD_EXCELLENT
    # summerer vi GOOD + EXCELLENT-verdiene som kommer fra to separate calls.
    # Key: (commodity, state, metric, week_ending) → akkumulert value_pct.
    accum: dict[tuple[str, str, str, str], float] = {}

    for commodity in commodities:
        for metric in metrics:
            filters = _METRIC_FILTERS.get(metric)
            if filters is None:
                _log.warning("nass.unknown_metric", metric=metric)
                continue

            # Skip metrics som ikke gjelder for denne commodity (NASS gir
            # 400 Bad Request på ugyldig kombinasjon).
            valid = _VALID_METRICS_PER_COMMODITY.get(commodity.upper())
            if valid is not None and metric not in valid:
                _log.debug(
                    "nass.skipping_invalid_combo",
                    commodity=commodity,
                    metric=metric,
                )
                continue

            for year in years:
                for statisticcat_desc, unit_desc in filters:
                    params = {
                        "key": api_key,
                        "format": "JSON",
                        "commodity_desc": commodity,
                        "statisticcat_desc": statisticcat_desc,
                        "unit_desc": unit_desc,
                        "agg_level_desc": "NATIONAL",
                        "year": str(year),
                    }

                    try:
                        resp = requests.get(_NASS_BASE, params=params, timeout=timeout)
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        _log.warning(
                            "nass.fetch_failed",
                            commodity=commodity,
                            metric=metric,
                            year=year,
                            statisticcat=statisticcat_desc,
                            unit=unit_desc,
                            error=str(exc),
                        )
                        continue

                    for item in data.get("data", []):
                        week_ending = item.get("week_ending")
                        value = item.get("Value", "")
                        if not week_ending or not value:
                            continue
                        try:
                            value_pct = float(value.replace(",", ""))
                        except ValueError:
                            continue
                        state = item.get("location_desc", "US TOTAL")
                        key = (commodity, state, metric, week_ending)
                        accum[key] = accum.get(key, 0.0) + value_pct

    rows = [
        {
            "week_ending": week_ending,
            "commodity": commodity,
            "state": state,
            "metric": metric,
            "value_pct": value_pct,
        }
        for (commodity, state, metric, week_ending), value_pct in accum.items()
    ]
    df = pd.DataFrame(rows, columns=list(CROP_PROGRESS_COLS))
    return df


def fetch_crop_progress_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt-populert CSV fra ``data/manual/crop_progress.csv``.

    Forventet schema: kolonner matcher ``CROP_PROGRESS_COLS``. Tom
    DataFrame returneres hvis filen ikke finnes.
    """
    if not csv_path.exists():
        _log.info("nass.manual_csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(CROP_PROGRESS_COLS))

    df = pd.read_csv(csv_path)
    missing = set(CROP_PROGRESS_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"crop_progress.csv mangler kolonner: {sorted(missing)}")
    return df[list(CROP_PROGRESS_COLS)]


def fetch_crop_progress(
    *,
    commodities: Iterable[str] | None = None,
    years: Iterable[int] | None = None,
    api_key: str | None = None,
    csv_path: Path = _MANUAL_CSV,
) -> pd.DataFrame:
    """Hent crop-progress data — bruker API hvis key er satt, ellers manuell CSV.

    Args:
        commodities: default ["CORN", "SOYBEANS", "WHEAT", "COTTON"].
        years: default = nåværende-året + forrige.
        api_key: override env-var.
        csv_path: manuell CSV-sti.

    Returns:
        DataFrame med kolonner = ``CROP_PROGRESS_COLS``. Tom DataFrame
        hvis hverken API-key eller CSV finnes.
    """
    if commodities is None:
        commodities = ["CORN", "SOYBEANS", "WHEAT", "COTTON"]
    if years is None:
        current = date.today().year
        years = [current - 1, current]

    api_key_resolved = api_key or get_secret(NASS_API_KEY_ENV)
    if api_key_resolved:
        try:
            return fetch_crop_progress_api(
                commodities=commodities, years=years, api_key=api_key_resolved
            )
        except Exception as exc:
            _log.warning("nass.api_failed_fallback_to_csv", error=str(exc))

    return fetch_crop_progress_manual(csv_path)


__all__ = [
    "NASS_API_KEY_ENV",
    "fetch_crop_progress",
    "fetch_crop_progress_api",
    "fetch_crop_progress_manual",
]
