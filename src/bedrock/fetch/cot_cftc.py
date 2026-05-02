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

CFTC_TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
"""Futures Only — Traders in Financial Futures (juni 2006-present).

D1 A4 (sub-fase 12.7, session 128). Per V4-funn (D0-smoke-test):
historikk fra juni 2006, ekte data (non-zero OI + dealer-positioning).
Bedre enn spec-forventet 2010+.
"""


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


# Sub-fase 12.10 follow-up Spor F5 (2026-05-02): Swap Dealer-positioning
# + concentration-of-largest-N-traders. NB: CFTC har en double-underscore
# typo i `swap__positions_short_all` (men single-underscore i long).
# Verifisert via Socrata 2026-05-02. Settes til NaN/NULL hvis felt mangler
# i respons (tidligere kontrakter / pre-2010-rader). swap_* er INTEGER,
# conc_* er REAL (% av OI, kan være neg).
_DISAGG_OPTIONAL_FIELD_MAP: dict[str, str] = {
    "swap_positions_long_all": "swap_long",
    "swap__positions_short_all": "swap_short",
    "conc_net_le_4_tdr_long_all": "conc_net_top4",
    "conc_net_le_8_tdr_long_all": "conc_net_top8",
}
_DISAGG_OPTIONAL_FLOAT_FIELDS: frozenset[str] = frozenset({"conc_net_top4", "conc_net_top8"})

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

# TFF Socrata-feltnavn (verifisert fra A4 smoke-test, session 126).
# 73 felter totalt; vi tar kun net-positioning-typer (dropper _spread).
_TFF_FIELD_MAP: dict[str, str] = {
    "report_date_as_yyyy_mm_dd": "report_date",
    "market_and_exchange_names": "contract",
    "dealer_positions_long_all": "dealer_long",
    "dealer_positions_short_all": "dealer_short",
    "asset_mgr_positions_long": "asset_mgr_long",
    "asset_mgr_positions_short": "asset_mgr_short",
    "lev_money_positions_long": "lev_funds_long",
    "lev_money_positions_short": "lev_funds_short",
    "other_rept_positions_long": "other_long",
    "other_rept_positions_short": "other_short",
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

    Sub-fase 12.10 Spor F5: returnerer i tillegg valgfrie kolonner fra
    `_DISAGG_OPTIONAL_FIELD_MAP` (swap_long/short, conc_net_top4/8) når
    CFTC-responsen inneholder dem; ellers fylles de med NaN/None.
    `append_cot_disaggregated` håndterer disse via separat UPDATE-pass.

    Kaster `CotFetchError` ved HTTP-feil eller malformert JSON.
    """
    return _fetch_cot_socrata(
        url=CFTC_DISAGGREGATED_URL,
        field_map=_DISAGG_FIELD_MAP,
        contract=contract,
        from_date=from_date,
        to_date=to_date,
        report_label="disaggregated",
        optional_field_map=_DISAGG_OPTIONAL_FIELD_MAP,
        optional_float_fields=_DISAGG_OPTIONAL_FLOAT_FIELDS,
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


def fetch_cot_tff(
    contract: str,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Hent Traders in Financial Futures-rapporter for ett kontrakt.

    D1 A4 (sub-fase 12.7, session 128). Returnerer DataFrame som matcher
    `DataStore.append_cot_tff` (kolonner i `schemas.COT_TFF_COLS`).
    Bruker samme HTTP-klient og rate-limit som disaggregated/legacy —
    ingen parallell pipeline.

    Kaster `CotFetchError` ved HTTP-feil eller malformert JSON.
    """
    return _fetch_cot_socrata(
        url=CFTC_TFF_URL,
        field_map=_TFF_FIELD_MAP,
        contract=contract,
        from_date=from_date,
        to_date=to_date,
        report_label="tff",
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
    optional_field_map: dict[str, str] | None = None,
    optional_float_fields: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Felles HTTP + validering + normalisering for begge COT-rapporter.

    Forskjellen mellom disaggregated og legacy ligger i `url` og `field_map`
    (Socrata-feltnavn er ulike). Alt annet er likt.

    `optional_field_map` (Spor F5): valgfrie Socrata-felt som mappes til
    bedrock-kolonner når de finnes i responsen. Manglende felt → NaN/None.
    `optional_float_fields` markerer hvilke valgfrie kolonner som skal
    cast'es til float (default integer).
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

    return _normalize_cot(
        data,
        contract,
        field_map,
        optional_field_map=optional_field_map,
        optional_float_fields=optional_float_fields,
    )


def _normalize_cot(
    rows: list[dict],
    contract: str,
    field_map: dict[str, str],
    optional_field_map: dict[str, str] | None = None,
    optional_float_fields: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Konverter Socrata JSON-rader til Bedrock-schema DataFrame.

    Tom liste → tom DataFrame med korrekte kolonner.
    `field_map` bestemmer schema (disagg vs legacy).
    `optional_field_map` (Spor F5) tilfører valgfrie kolonner — fylles
    med NaN/None hvis Socrata-feltet mangler i responsen.
    """
    expected_cols = list(field_map.values())
    optional_cols = list(optional_field_map.values()) if optional_field_map else []
    float_set = optional_float_fields or frozenset()

    all_cols = expected_cols + optional_cols

    if not rows:
        return pd.DataFrame(columns=all_cols)

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

    if optional_field_map:
        for src, dest in optional_field_map.items():
            if src in df.columns:
                col_series = pd.to_numeric(df[src], errors="coerce")
                if dest in float_set:
                    renamed[dest] = col_series.astype("float64")
                else:
                    # Nullable int — bevarer NaN per rad
                    renamed[dest] = col_series.astype("Int64")
            else:
                # Felt mangler i denne respons-batchen (sannsynlig pre-2010
                # eller kontrakt uten swap-kategori). Fill NaN.
                renamed[dest] = pd.NA

    return renamed[all_cols]
