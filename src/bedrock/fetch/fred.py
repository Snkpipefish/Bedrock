# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""FRED (Federal Reserve Economic Data) observations fetcher.

Endepunkt:
    https://api.stlouisfed.org/fred/series/observations

Krever API-nøkkel (gratis fra https://fred.stlouisfed.org/docs/api/api_key.html).
Nøkkel lastes via `bedrock.config.secrets` (env-var eller
`~/.bedrock/secrets.env`, nøkkel `FRED_API_KEY`).

FRED rapporterer missing observations som `"."` i value-feltet;
vi konverterer til NaN slik at `DataStore.append_fundamentals` lagrer NULL.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
"""FRED observations-endepunkt."""

_FRED_MISSING_MARKER = "."
"""FRED's sentinel for manglende observasjon."""


class FredFetchError(RuntimeError):
    """FRED-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def build_fred_params(
    series_id: str,
    api_key: str,
    from_date: date,
    to_date: date,
    limit: int = 100_000,
) -> dict[str, str]:
    """Bygg URL-parametre for FRED. Eksponert for `--dry-run`-masking."""
    return {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": from_date.isoformat(),
        "observation_end": to_date.isoformat(),
        "limit": str(limit),
    }


def fetch_fred_series(
    series_id: str,
    api_key: str,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent en FRED-serie og returner som DataFrame matching
    `DataStore.append_fundamentals`-schema (series_id, date, value).

    Missing observations (FRED-marker `"."`) blir NaN i DataFrame,
    NULL i DB. Datoer sortert ASC per FRED default.

    Kaster `FredFetchError` ved HTTP-feil eller malformert JSON.
    """
    params = build_fred_params(series_id, api_key, from_date, to_date)
    _log.info(
        "fetch_fred_series series_id=%s from=%s to=%s",
        series_id,
        from_date,
        to_date,
    )

    try:
        response = http_get_with_retry(FRED_OBSERVATIONS_URL, params=params)
    except Exception as exc:
        raise FredFetchError(f"Network failure fetching FRED {series_id}: {exc}") from exc

    if response.status_code != 200:
        # FRED gir feilkode + JSON error body med beskrivelse; inkluder litt.
        body_preview = response.text[:200]
        raise FredFetchError(
            f"FRED returned HTTP {response.status_code} for {series_id}: {body_preview!r}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise FredFetchError(f"Failed to parse FRED JSON for {series_id}: {exc}") from exc

    if not isinstance(data, dict) or "observations" not in data:
        raise FredFetchError(
            f"FRED response for {series_id} missing 'observations' block. "
            f"Keys: {sorted(data) if isinstance(data, dict) else type(data).__name__}"
        )

    return _normalize_fred(data["observations"], series_id)


def _normalize_fred(observations: list[dict], series_id: str) -> pd.DataFrame:
    """Konverter FRED observations-liste til Bedrock-schema.

    Tom observations-liste → tom DataFrame med riktig kolonne-sett.
    FRED's `"."` → NaN.
    """
    cols = ["series_id", "date", "value"]

    if not observations:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(observations)

    if "date" not in df.columns or "value" not in df.columns:
        raise FredFetchError(
            f"FRED observations for {series_id} missing 'date' or 'value' fields. "
            f"Got: {sorted(df.columns)}"
        )

    # "." → NaN; resten til float.
    values = df["value"].replace(_FRED_MISSING_MARKER, pd.NA)
    values = pd.to_numeric(values, errors="coerce")

    return pd.DataFrame(
        {
            "series_id": [series_id] * len(df),
            "date": df["date"],
            "value": values,
        }
    )
