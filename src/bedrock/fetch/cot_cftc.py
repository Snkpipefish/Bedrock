# pyright: reportAttributeAccessIssue=false, reportReturnType=false, reportCallIssue=false, reportArgumentType=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""CFTC Commitments of Traders fetcher (Socrata API).

Dekker begge rapport-typene:

- **Disaggregated** (Futures Only, dataset `72hh-3qpy`, 2010-present):
  managed money, other reportable, producer/merchant/commercial, non-
  reportable.
- **Legacy** (Futures Only, dataset `6dca-aqww`, 2006-present):
  non-commercial, commercial, non-reportable.

Fetcherne er tynne wrappere rundt en felles `_fetch_cot_socrata`-helper som
håndterer HTTP-henting + JSON-validering + normalisering. Forskjellen mellom
dem er kun URL + field-map (Socrata → Bedrock-schema).

Query-parametre (SoQL):
    $where  — filter (market_and_exchange_names + report_date range)
    $order  — report_date_as_yyyy_mm_dd ASC
    $limit  — max 50000 per call; vi paginerer ikke ennå (10 år × ukentlig
              = ~520 rader per kontrakt, godt under grensen)
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset-URL-er
# ---------------------------------------------------------------------------

CFTC_DISAGGREGATED_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
"""Futures Only — Disaggregated (2010-present)."""

CFTC_LEGACY_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
"""Futures Only — Legacy (2006-present)."""


# ---------------------------------------------------------------------------
# Field-mapping Socrata → Bedrock-schema
# ---------------------------------------------------------------------------

_DISAGG_FIELD_MAP: dict[str, str] = {
    "report_date_as_yyyy_mm_dd": "report_date",
    "market_and_exchange_names": "contract",
    # CFTC endret feltnavn (oppdaget 2026-04-25): m_money_positions_*_all
    # erstatter m_money_positions_* (de splittet "all" / "old" / "other"
    # for kontrakter med hyphenert termin-struktur). Vi bruker _all
    # (combined) — matcher Bedrock-skjemaets `mm_long`/`mm_short`.
    "m_money_positions_long_all": "mm_long",
    "m_money_positions_short_all": "mm_short",
    "other_rept_positions_long": "other_long",
    "other_rept_positions_short": "other_short",
    "prod_merc_positions_long": "comm_long",
    "prod_merc_positions_short": "comm_short",
    "nonrept_positions_long_all": "nonrep_long",
    "nonrept_positions_short_all": "nonrep_short",
    "open_interest_all": "open_interest",
}

_LEGACY_FIELD_MAP: dict[str, str] = {
    "report_date_as_yyyy_mm_dd": "report_date",
    "market_and_exchange_names": "contract",
    "noncomm_positions_long_all": "noncomm_long",
    "noncomm_positions_short_all": "noncomm_short",
    "comm_positions_long_all": "comm_long",
    "comm_positions_short_all": "comm_short",
    "nonrept_positions_long_all": "nonrep_long",
    "nonrept_positions_short_all": "nonrep_short",
    "open_interest_all": "open_interest",
}


class CotFetchError(RuntimeError):
    """CFTC-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


# ---------------------------------------------------------------------------
# Query-bygger (delt)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Offentlige fetch-funksjoner
# ---------------------------------------------------------------------------


def fetch_cot_disaggregated(
    contract: str,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent disaggregated CFTC-rapporter for ett kontrakt.

    Returnerer DataFrame som matcher `DataStore.append_cot_disaggregated`
    (kolonner i `schemas.COT_DISAGGREGATED_COLS`). Tom respons = tom
    DataFrame.

    Kaster `CotFetchError` ved HTTP-feil eller malformert JSON.
    """
    return _fetch_cot_socrata(
        url=CFTC_DISAGGREGATED_URL,
        field_map=_DISAGG_FIELD_MAP,
        contract=contract,
        from_date=from_date,
        to_date=to_date,
        report_label="disaggregated",
    )


def fetch_cot_legacy(
    contract: str,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent legacy CFTC-rapporter for ett kontrakt.

    Returnerer DataFrame som matcher `DataStore.append_cot_legacy`
    (kolonner i `schemas.COT_LEGACY_COLS`). Tom respons = tom DataFrame.

    Kaster `CotFetchError` ved HTTP-feil eller malformert JSON.
    """
    return _fetch_cot_socrata(
        url=CFTC_LEGACY_URL,
        field_map=_LEGACY_FIELD_MAP,
        contract=contract,
        from_date=from_date,
        to_date=to_date,
        report_label="legacy",
    )


# ---------------------------------------------------------------------------
# Intern helper
# ---------------------------------------------------------------------------


def _fetch_cot_socrata(
    url: str,
    field_map: dict[str, str],
    contract: str,
    from_date: date,
    to_date: date,
    report_label: str,
) -> pd.DataFrame:
    """Felles HTTP + validering + normalisering for begge COT-rapporter.

    Forskjellen mellom disaggregated og legacy ligger i `url` og `field_map`
    (Socrata-feltnavn er ulike). Alt annet er likt.
    """
    params = build_socrata_query(contract, from_date, to_date)
    _log.info(
        "fetch_cot_%s contract=%s from=%s to=%s",
        report_label,
        contract,
        from_date,
        to_date,
    )

    try:
        response = http_get_with_retry(url, params=params)
    except Exception as exc:
        raise CotFetchError(
            f"Network failure fetching COT ({report_label}) for {contract}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise CotFetchError(
            f"CFTC returned HTTP {response.status_code} for {contract} "
            f"({report_label}): {response.text[:200]!r}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise CotFetchError(
            f"Failed to parse CFTC JSON for {contract} ({report_label}): {exc}"
        ) from exc

    if not isinstance(data, list):
        raise CotFetchError(
            f"CFTC returned non-list JSON for {contract} ({report_label}): "
            f"type={type(data).__name__}"
        )

    return _normalize_cot(data, contract, field_map)


def _normalize_cot(
    rows: list[dict],
    contract: str,
    field_map: dict[str, str],
) -> pd.DataFrame:
    """Konverter Socrata JSON-rader til Bedrock-schema DataFrame.

    Tom liste → tom DataFrame med korrekte kolonner.
    `field_map` bestemmer skjema (disagg vs legacy).
    """
    expected_cols = list(field_map.values())

    if not rows:
        return pd.DataFrame(columns=expected_cols)

    df = pd.DataFrame(rows)

    missing_src = [src for src in field_map if src not in df.columns]
    if missing_src:
        raise CotFetchError(
            f"CFTC response for {contract} missing fields: {missing_src}. "
            f"Got: {sorted(df.columns)[:20]}"
        )

    renamed = df[list(field_map)].rename(columns=field_map)

    # Socrata returnerer ofte alle tall som strenger
    int_cols = [c for c in expected_cols if c not in ("report_date", "contract")]
    for col in int_cols:
        renamed[col] = pd.to_numeric(renamed[col], errors="coerce").fillna(0).astype("int64")

    # "2024-01-02T00:00:00.000" → "2024-01-02"
    renamed["report_date"] = pd.to_datetime(renamed["report_date"]).dt.strftime("%Y-%m-%d")

    return renamed[expected_cols]
