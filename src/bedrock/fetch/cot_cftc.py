"""CFTC Commitments of Traders fetcher (Socrata API).

Fase 3 session 11: kun disaggregated-rapport (Futures Only). Legacy følger i
session 12 — samme mønster, annet datasett + andre Socrata-feltnavn.

Socrata-endepunkt:
    https://publicreporting.cftc.gov/resource/72hh-3qpy.json

Query-parametre (SoQL):
    $where  — filter (market_and_exchange_names + report_date range)
    $order  — report_date_as_yyyy_mm_dd ASC
    $limit  — max 50000 per call; vi paginerer ikke ennå (10 år × ukentlig
              = ~520 rader per kontrakt, godt under grensen)

Feltnavn-mapping (Socrata → Bedrock-schema):
    report_date_as_yyyy_mm_dd → report_date
    market_and_exchange_names → contract
    m_money_positions_long    → mm_long
    m_money_positions_short   → mm_short
    other_rept_positions_long → other_long
    other_rept_positions_short→ other_short
    prod_merc_positions_long  → comm_long    (producer/merchant/processor/user)
    prod_merc_positions_short → comm_short
    nonrept_positions_long_all→ nonrep_long
    nonrept_positions_short_all→ nonrep_short
    open_interest_all         → open_interest
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

CFTC_DISAGGREGATED_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
"""Futures Only - Disaggregated."""

# Kolonne-mapping Socrata → Bedrock-schema (cot_disaggregated-tabellen)
_DISAGG_FIELD_MAP: dict[str, str] = {
    "report_date_as_yyyy_mm_dd": "report_date",
    "market_and_exchange_names": "contract",
    "m_money_positions_long": "mm_long",
    "m_money_positions_short": "mm_short",
    "other_rept_positions_long": "other_long",
    "other_rept_positions_short": "other_short",
    "prod_merc_positions_long": "comm_long",
    "prod_merc_positions_short": "comm_short",
    "nonrept_positions_long_all": "nonrep_long",
    "nonrept_positions_short_all": "nonrep_short",
    "open_interest_all": "open_interest",
}


class CotFetchError(RuntimeError):
    """CFTC-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def build_socrata_query(
    contract: str,
    from_date: date,
    to_date: date,
    limit: int = 50000,
) -> dict[str, str]:
    """Bygg SoQL-parametre for CFTC Socrata. Eksponert for `--dry-run`.

    SoQL støtter enkel-quotet tekst-filter; kontrakt-navn inneholder
    mellomrom og punktum, må derfor wrappes i single-quotes.
    """
    where = (
        f"market_and_exchange_names='{contract}' "
        f"AND report_date_as_yyyy_mm_dd >= '{from_date.isoformat()}' "
        f"AND report_date_as_yyyy_mm_dd <= '{to_date.isoformat()}'"
    )
    return {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": str(limit),
    }


def fetch_cot_disaggregated(
    contract: str,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent disaggregated CFTC-rapporter for ett kontrakt.

    Returnerer DataFrame som matcher `DataStore.append_cot_disaggregated`
    (kolonner i `schemas.COT_DISAGGREGATED_COLS`). Tomme resultater
    returnerer en tom DataFrame (ingen error) — det er rimelig at en ny
    kontrakt ikke har data i hele perioden.

    Kaster `CotFetchError` ved HTTP-feil eller malformert JSON.
    """
    params = build_socrata_query(contract, from_date, to_date)
    _log.info("fetch_cot_disaggregated contract=%s from=%s to=%s", contract, from_date, to_date)

    try:
        response = http_get_with_retry(CFTC_DISAGGREGATED_URL, params=params)
    except Exception as exc:
        raise CotFetchError(f"Network failure fetching COT for {contract}: {exc}") from exc

    if response.status_code != 200:
        raise CotFetchError(
            f"CFTC returned HTTP {response.status_code} for {contract}: "
            f"{response.text[:200]!r}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise CotFetchError(f"Failed to parse CFTC JSON for {contract}: {exc}") from exc

    if not isinstance(data, list):
        raise CotFetchError(
            f"CFTC returned non-list JSON for {contract}: type={type(data).__name__}"
        )

    return _normalize_disaggregated(data, contract)


def _normalize_disaggregated(rows: list[dict], contract: str) -> pd.DataFrame:
    """Konverter Socrata JSON-rader til Bedrock-schema DataFrame.

    Tomme rader-lister returneres som tom DataFrame med korrekte kolonner
    (gjør det trygt for caller å iterere over len()).
    """
    expected_cols = list(_DISAGG_FIELD_MAP.values())

    if not rows:
        return pd.DataFrame(columns=expected_cols)

    df = pd.DataFrame(rows)

    missing_src = [src for src in _DISAGG_FIELD_MAP if src not in df.columns]
    if missing_src:
        raise CotFetchError(
            f"CFTC response for {contract} missing fields: {missing_src}. "
            f"Got: {sorted(df.columns)[:20]}"
        )

    renamed = df[list(_DISAGG_FIELD_MAP)].rename(columns=_DISAGG_FIELD_MAP)

    # Typekonvertering: Socrata returnerer ofte alle tall som streng
    int_cols = [c for c in expected_cols if c not in ("report_date", "contract")]
    for col in int_cols:
        renamed[col] = pd.to_numeric(renamed[col], errors="coerce").fillna(0).astype("int64")

    # report_date kan komme som "2024-01-02T00:00:00.000" — trimmer til dato.
    renamed["report_date"] = pd.to_datetime(renamed["report_date"]).dt.strftime("%Y-%m-%d")

    return renamed[expected_cols]
