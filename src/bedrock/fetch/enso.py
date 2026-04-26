# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""NOAA ONI (Oceanic Niño Index) fetcher.

ONI er 3-måneders rullende gjennomsnitt av SST-anomalier i Niño 3.4-
regionen, publisert månedlig av NOAA Climate Prediction Center. Brukes
som ENSO-regime-indikator (`enso_regime` per PLAN § 6.5) for grains og
softs analog-matching.

Endepunkt:
    https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt

ASCII-format (whitespace-delt, header på første linje):

    SEAS  YR  TOTAL  ANOM
     DJF 1950  24.55 -1.53
     JFM 1950  24.74 -1.34
     ...

`SEAS` er 3-bokstavers seasonal-label (DJF/JFM/.../NDJ). Konvensjonelt
dater vi observasjonen til den midterste måneden (DJF → Jan, JFM → Feb,
... NDJ → Dec). `ANOM` er ONI-verdien (`value`-kolonnen i bedrocks
fundamentals-skjema).

ADR-005 (Fase 10 session 57): ENSO lagres i eksisterende
`fundamentals`-tabell med `series_id="NOAA_ONI"` istedenfor egen tabell.
Output-DataFrame matcher `DataStore.append_fundamentals`-kontrakten.

Ingen API-nøkkel kreves. Endepunktet oppdateres månedlig av NOAA;
typisk publisering ~10. i måneden for forrige måneds verdi.
"""

from __future__ import annotations

import logging

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

NOAA_ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
"""NOAA CPC ONI ASCII-endepunkt."""

NOAA_ONI_SERIES_ID = "NOAA_ONI"
"""Series-ID som brukes i `fundamentals`-tabellen for ONI-verdier."""

# Mapping fra 3-bokstavers seasonal-label til midterste måned.
# Eksempel: DJF (Dec/Jan/Feb) → Jan (måned 1).
_SEAS_TO_MONTH: dict[str, int] = {
    "DJF": 1,
    "JFM": 2,
    "FMA": 3,
    "MAM": 4,
    "AMJ": 5,
    "MJJ": 6,
    "JJA": 7,
    "JAS": 8,
    "ASO": 9,
    "SON": 10,
    "OND": 11,
    "NDJ": 12,
}


class NoaaOniFetchError(RuntimeError):
    """ONI-fetch feilet (HTTP-feil, malformert ASCII, eller retries brukt opp)."""


def fetch_noaa_oni() -> pd.DataFrame:
    """Hent NOAA ONI ASCII og returner som fundamentals-format.

    Returnerer pd.DataFrame med kolonner `series_id`, `date`, `value`
    matching `DataStore.append_fundamentals`-kontrakten. `series_id` er
    konstanten `NOAA_ONI_SERIES_ID`. `date` er første-i-midt-måneden
    (YYYY-MM-01). `value` er ANOM-kolonnen som float.

    Kaster `NoaaOniFetchError` ved nettverks-feil, ikke-200-respons,
    eller malformert ASCII-innhold.
    """
    _log.info("fetch_noaa_oni url=%s", NOAA_ONI_URL)

    try:
        response = http_get_with_retry(NOAA_ONI_URL)
    except Exception as exc:
        raise NoaaOniFetchError(f"Network failure fetching NOAA ONI: {exc}") from exc

    if response.status_code != 200:
        body_preview = response.text[:200]
        raise NoaaOniFetchError(f"NOAA ONI returned HTTP {response.status_code}: {body_preview!r}")

    return parse_noaa_oni_text(response.text)


def parse_noaa_oni_text(text: str) -> pd.DataFrame:
    """Parse ONI ASCII-innhold til fundamentals-DataFrame.

    Eksponert separat fra `fetch_noaa_oni` slik at testene kan kjøre mot
    statisk fixture uten HTTP. Tom input gir tom DataFrame med riktig
    kolonne-sett.

    Skipper:
    - Header-linja (begynner ikke med en gyldig SEAS-token)
    - Tomme linjer
    - Linjer med 'TOTAL' = -99.9 eller ANOM = -99.9 (NOAAs missing-marker
      for fremtidige måneder; sjeldent, men sett i historiske dumper)
    """
    cols = ["series_id", "date", "value"]
    rows: list[dict[str, object]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        tokens = line.split()
        if len(tokens) < 4:
            # Ugyldig rad — kunne vært header eller corrupt
            continue

        seas = tokens[0]
        if seas not in _SEAS_TO_MONTH:
            # Ikke en datalinje (header eller annen tekst)
            continue

        try:
            year = int(tokens[1])
            anom = float(tokens[3])
        except ValueError:
            _log.warning("noaa_oni.skip_unparseable_line line=%r", line)
            continue

        # NOAA bruker -99.9 som missing-marker i noen historiske dumper
        if anom <= -99.0:
            continue

        # NDJ (Nov/Dec/Jan): konvensjon dater til Dec inneværende år
        # — året i fila refererer til midterste måned, så NDJ 1999
        # = Nov '99 + Dec '99 + Jan '00, midt = Dec 1999.
        month = _SEAS_TO_MONTH[seas]
        date_str = f"{year:04d}-{month:02d}-01"

        rows.append(
            {
                "series_id": NOAA_ONI_SERIES_ID,
                "date": date_str,
                "value": anom,
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)

    return pd.DataFrame(rows, columns=cols)
