"""US Treasury auction-results fetcher (Spor F6 — sub-fase 12.10 follow-up).

Henter US Treasury auction-results fra TreasuryDirect's offentlige API.
Gratis, ingen API-key. Returnerer DataFrame som matcher
``DataStore.append_treasury_auctions`` (kolonner i
``schemas.TREASURY_AUCTIONS_COLS``).

API-endepunkt:
    GET https://www.treasurydirect.gov/TA_WS/securities/auctioned
        ?format=json
        &pagesize=N

Sortert nyeste-først. Pagesize default 250 (API-default), max ~1000 per kall.
For full historikk (10 år ≈ 5000 auksjoner) iterer over `daysago`-vinduer
eller bruk `&pagesize=1000` med flere `&page=N`-kall.

Per memory-feedback (gratis-API) kjører backfill-scripts sekvensielt
mellom kall. Field-mapping (camelCase JSON → snake_case schema):
- auctionDate → auction_date
- securityType → security_type   (Bill/Note/Bond/TIPS/FRN)
- securityTerm → security_term   ("13-Week", "10-Year", etc.)
- bidToCoverRatio → bid_to_cover_ratio
- indirectBidderAccepted / totalAccepted → indirect_pct (0..1)
- primaryDealerAccepted / totalAccepted → primary_dealer_pct
- offeringAmount → offering_amount
- totalAccepted → total_accepted
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from bedrock.data.schemas import TREASURY_AUCTIONS_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

TREASURY_AUCTIONS_URL = "https://www.treasurydirect.gov/TA_WS/securities/auctioned"
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_PAGESIZE = 250


class TreasuryFetchError(RuntimeError):
    """TreasuryDirect-fetch feilet permanent."""


def fetch_treasury_auctions(
    *,
    pagesize: int = _DEFAULT_PAGESIZE,
    days_ago: int | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent én side av Treasury-auction-results.

    Args:
        pagesize: antall rader per kall (API-default 250).
        days_ago: optional filter — kun auksjoner siste N dager.
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed JSON-list for testing. Hopper over HTTP.

    Returns:
        DataFrame med ``TREASURY_AUCTIONS_COLS``. Tom hvis ingen auksjoner
        i vinduet.

    Raises:
        TreasuryFetchError: ved HTTP-feil eller uventet response-struktur.
    """
    if raw_response is None:
        params = {"format": "json", "pagesize": str(pagesize)}
        if days_ago is not None:
            params["days"] = str(days_ago)
        try:
            response = http_get_with_retry(TREASURY_AUCTIONS_URL, params=params, timeout=timeout)
        except Exception as exc:
            raise TreasuryFetchError(f"Network failure: {exc}") from exc
        if response.status_code != 200:
            raise TreasuryFetchError(
                f"HTTP {response.status_code} from TreasuryDirect: {response.text[:200]!r}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TreasuryFetchError(f"Invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, list):
        raise TreasuryFetchError(f"Expected JSON array, got {type(payload).__name__}")

    return _normalize_treasury_rows(payload)


def _normalize_treasury_rows(rows: list[dict]) -> pd.DataFrame:
    """Konverter TreasuryDirect JSON-rader til Bedrock-schema DataFrame."""
    if not rows:
        return pd.DataFrame(columns=list(TREASURY_AUCTIONS_COLS))

    out_rows: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        auction_date = r.get("auctionDate")
        sec_type = r.get("securityType")
        sec_term = r.get("securityTerm")
        if not (auction_date and sec_type and sec_term):
            continue

        total_accepted = _to_float(r.get("totalAccepted"))
        indirect_acc = _to_float(r.get("indirectBidderAccepted"))
        primary_acc = _to_float(r.get("primaryDealerAccepted"))
        indirect_pct = (
            indirect_acc / total_accepted if (indirect_acc is not None and total_accepted) else None
        )
        primary_pct = (
            primary_acc / total_accepted if (primary_acc is not None and total_accepted) else None
        )

        out_rows.append(
            {
                "auction_date": _normalize_date(auction_date),
                "security_type": str(sec_type),
                "security_term": str(sec_term),
                "cusip": str(r["cusip"]) if r.get("cusip") else None,
                "bid_to_cover_ratio": _to_float(r.get("bidToCoverRatio")),
                "indirect_pct": indirect_pct,
                "primary_dealer_pct": primary_pct,
                "offering_amount": _to_float(r.get("offeringAmount")),
                "total_accepted": total_accepted,
            }
        )

    df = pd.DataFrame(out_rows, columns=list(TREASURY_AUCTIONS_COLS))
    _log.info("treasury_auctions.fetched rows=%d", len(df))
    return df


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_date(s: Any) -> str:
    """TreasuryDirect leverer ofte ISO-prefiksede strenger; normaliser til YYYY-MM-DD."""
    return pd.to_datetime(str(s)).strftime("%Y-%m-%d")


__all__ = [
    "TREASURY_AUCTIONS_URL",
    "TreasuryFetchError",
    "fetch_treasury_auctions",
]
