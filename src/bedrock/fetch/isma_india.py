"""ISMA India sugar production fetcher (sub-fase 12.11+ analytiker D.5).

Henter ISMA's offentlige resource API og parser indisk sukker-produksjons-
estimater fra press release-titler. ISMA publiserer cumulative production
gjennom sukker-sesongen (oct-sep) i lakh tonnes (1 lakh = 100,000 tonn).

Begrensning: API gir kun siste 18 måneder (~166 datapunkter, 2024-11+).
Eldre data ikke tilgjengelig via free API. Driver vil bygge historikk
fremover (~2 år før YoY-z-score blir meningsfull).

Endpoint:
    https://api.ismaindia.org/api/auth/getallresource

Schema:
    {data: [{title, description, date, category, link, ...}]}

Filter: regex-match "X lakh ton[ne]s" eller "X million tonnes" i title
hvor X ∈ [50, 500] (rimelig sukker-prod range for India).

Lagrer i `fundamentals`-tabellen som series_id="ISMA_INDIA_SUGAR_PROD_LAKH_TONS".
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

API_URL = "https://api.ismaindia.org/api/auth/getallresource"
SERIES_ID = "ISMA_INDIA_SUGAR_PROD_LAKH_TONS"

# Pattern: "274.8 lakh tons", "27.52 million tonne", "195.03 lakh tonnes"
_PRODUCTION_RE = re.compile(
    r"([\d.]+)\s*(lakh|million)\s*ton(?:n?es?|s)?",
    re.IGNORECASE,
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Realistiske bounds for India sukker-prod (lakh tonnes per sesong)
_MIN_PROD_LAKH = 50.0
_MAX_PROD_LAKH = 500.0


class IsmaFetchError(RuntimeError):
    """ISMA-fetch feilet permanent."""


def fetch_isma_india(timeout: float = 30.0) -> pd.DataFrame:
    """Hent ISMA-resources og ekstraher produksjons-tall.

    Returnerer DataFrame med kolonner: series_id, date, value (lakh tonnes).
    Idempotent — samme dato kan ha flere artikler men dedupliseres til
    én verdi per dag (median hvis flere unike).
    """
    try:
        response = http_get_with_retry(API_URL, headers=_HEADERS, timeout=timeout)
    except Exception as exc:
        raise IsmaFetchError(f"Network failure: {exc}") from exc

    if response.status_code != 200:
        raise IsmaFetchError(f"ISMA returned HTTP {response.status_code}: {response.text[:200]!r}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise IsmaFetchError(f"Failed to parse ISMA JSON: {exc}") from exc

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("data") or payload.get("resources") or []
    else:
        items = []
    if not isinstance(items, list):
        raise IsmaFetchError(f"Unexpected ISMA response shape: {type(payload)}")

    return parse_production_values(items)


def parse_production_values(items: list[dict[str, Any]]) -> pd.DataFrame:
    """Parse produksjon-verdier fra item-titler.

    Konverterer "million tonnes" til lakh (1 million = 10 lakh) for
    konsistent enhet.
    """
    rows: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title") or "")
        date_raw = str(item.get("date") or "")
        if not date_raw:
            continue
        # Date kan være ISO eller diverse formater
        try:
            d = datetime.fromisoformat(date_raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                d = datetime.strptime(date_raw[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

        for m in _PRODUCTION_RE.finditer(title):
            value = float(m.group(1))
            unit = m.group(2).lower()
            if unit == "million":
                value *= 10.0  # million tonnes → lakh tonnes
            if not (_MIN_PROD_LAKH <= value <= _MAX_PROD_LAKH):
                continue
            rows.append({"series_id": SERIES_ID, "date": d.isoformat(), "value": value})
            break  # første match per item

    if not rows:
        return pd.DataFrame(columns=["series_id", "date", "value"])

    df = pd.DataFrame(rows)
    # Median per dato hvis flere artikler samme dag (dedup støy)
    df = df.groupby(["series_id", "date"], as_index=False)["value"].median()
    df = df.sort_values("date").reset_index(drop=True)
    return df
