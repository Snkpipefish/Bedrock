# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).
"""IIP REMIT supply-unavailability fetcher (sub-fase 12.10 follow-up Spor C, session 136).

GIE Inside Information Platform (IIP) publiserer REMIT Urgent Market
Messages (UMM) om unavailability av gas-supply-infrastruktur (storage,
LNG-terminals, processing plants, pipelines).

Endepunkt:
    https://iip.gie.eu/api/?page={N}&size={M}

Header:
    x-key: $AGSI_API_KEY  (samme nøkkel som AGSI/ALSI per § 22.1)

API-arkivet starter ~2022-01-31. Ny page=1 = nyeste meldinger;
meldinger sortert DESC på published. ``last_page`` reflekterer
faktisk side-tall ved gitt ``size``-parameter.

API-returformat (per UMM):
- messageId (i `message.messageId`): IIP-kanonisk PK
- submitted: når melding ble sendt til IIP
- published: look-ahead-safe truth (når markedet så meldingen)
- from / to: event-vindu
- status: "Active"/"Inactive"
- messageType: f.eks. "Gas storage facility unavailability"
- unavailabilityType: "Planned"/"Unplanned"
- unavailable.capacity / available.capacity / technical.capacity (GWh/d)
- balancingZone[0].code / .name: marked-zone-id
- direction: "Entry"/"Exit"/"Both"
- asset.code / asset.name: berørt asset
- unavailabilityReason / remarks: free-text

Sekvensielle requests med 1.5s pacing-delay per memory:free-api-no-parallel.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import IIP_REMIT_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

IIP_API_KEY_ENV = "AGSI_API_KEY"
IIP_BASE_URL = "https://iip.gie.eu/api/"
DEFAULT_TIMEOUT = 30.0
REQUEST_PACING_SEC = 1.5
DEFAULT_PAGE_SIZE = 50  # API-default; verifisert å fungere uten timeout


class IipFetchError(RuntimeError):
    """IIP-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def _to_float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _capacity_gwhd(obj: Any) -> float | None:
    """Hent capacity i GWh/d. ALSI/IIP returnerer dict {capacity, unit}.

    Verifiserer at unit er 'GWh/d' eller manglende. Returnerer None hvis
    annen unit (vi normaliserer ikke MW/MWh — ekstrem sjelden i praksis).
    """
    if not isinstance(obj, dict):
        return None
    raw = obj.get("capacity")
    unit = (obj.get("unit") or "").strip()
    if unit and unit.lower() not in ("gwh/d", "gwh", ""):
        return None
    return _to_float_or_none(raw)


def _normalize_record(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Konverter én IIP UMM til IIP_REMIT_COLS-format. None hvis ugyldig."""
    msg_obj = rec.get("message") or {}
    msg_id = msg_obj.get("messageId") if isinstance(msg_obj, dict) else None
    if not msg_id:
        return None

    bz_list = rec.get("balancingZone") or []
    bz_obj = bz_list[0] if isinstance(bz_list, list) and bz_list else {}
    if not isinstance(bz_obj, dict):
        bz_obj = {}

    asset_obj = rec.get("asset") or {}
    if not isinstance(asset_obj, dict):
        asset_obj = {}

    return {
        "message_id": str(msg_id),
        "submitted_ts": _to_str_or_none(rec.get("submitted")),
        "published_ts": _to_str_or_none(rec.get("published")),
        "event_from_ts": _to_str_or_none(rec.get("from")),
        "event_to_ts": _to_str_or_none(rec.get("to")),
        "status": _to_str_or_none(rec.get("status")),
        "message_type": (
            _to_str_or_none(msg_obj.get("messageType")) if isinstance(msg_obj, dict) else None
        ),
        "unavailability_type": (
            _to_str_or_none(msg_obj.get("unavailabilityType"))
            if isinstance(msg_obj, dict)
            else None
        ),
        "unavailability_reason": _to_str_or_none(rec.get("unavailabilityReason")),
        "unavailable_capacity_gwhd": _capacity_gwhd(rec.get("unavailable")),
        "available_capacity_gwhd": _capacity_gwhd(rec.get("available")),
        "technical_capacity_gwhd": _capacity_gwhd(rec.get("technical")),
        "balancing_zone_code": _to_str_or_none(bz_obj.get("code")),
        "balancing_zone_name": _to_str_or_none(bz_obj.get("name")),
        "direction": _to_str_or_none(rec.get("direction")),
        "asset_code": _to_str_or_none(asset_obj.get("code")),
        "asset_name": _to_str_or_none(asset_obj.get("name")),
    }


def fetch_iip_page(
    page: int,
    api_key: str,
    *,
    size: int = DEFAULT_PAGE_SIZE,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> tuple[pd.DataFrame, int]:
    """Hent én side IIP UMM-meldinger.

    Returns:
        Tuple (df, last_page) der ``last_page`` er totalt antall sider for
        gitt ``size``. df har IIP_REMIT_COLS som kolonner.

    Raises:
        IipFetchError: ved HTTP-feil eller uventet payload-struktur.
    """
    if raw_response is None:
        try:
            response = http_get_with_retry(
                IIP_BASE_URL,
                params={"page": page, "size": size},
                timeout=timeout,
                headers={"x-key": api_key},
            )
        except Exception as exc:
            raise IipFetchError(f"iip.page={page}: network failure: {exc}") from exc

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise IipFetchError(f"iip.page={page}: HTTP {response.status_code}: {body_preview!r}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise IipFetchError(f"iip.page={page}: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, dict):
        raise IipFetchError(f"iip.page={page}: expected JSON object, got {type(payload).__name__}")

    raw_rows = payload.get("data", [])
    if not isinstance(raw_rows, list):
        raise IipFetchError(f"iip.page={page}: 'data' must be list, got {type(raw_rows).__name__}")

    rows: list[dict[str, Any]] = []
    for rec in raw_rows:
        if not isinstance(rec, dict):
            continue
        normalized = _normalize_record(rec)
        if normalized is not None:
            rows.append(normalized)

    df = pd.DataFrame(rows, columns=list(IIP_REMIT_COLS))
    last_page = int(payload.get("last_page", 1) or 1)
    _log.info("iip.fetched page=%d rows=%d last_page=%d", page, len(df), last_page)
    return df, last_page


def fetch_iip_remit(
    *,
    api_key: str | None = None,
    max_pages: int | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    pacing_sec: float = REQUEST_PACING_SEC,
    timeout: float = DEFAULT_TIMEOUT,
    stop_before_published_ts: str | None = None,
) -> pd.DataFrame:
    """Hent IIP UMM-meldinger sekvensielt fra side 1 og fremover.

    Default henter alle sider (full historikk siden ~2022-01-31). For
    daglig fetcher-bruk gir ``max_pages=1`` siste 50 meldinger; for
    backfill droppes ``max_pages``.

    Stop-criteria:
        max_pages: stopp etter N sider (default: alle).
        stop_before_published_ts: ISO-streng. Stopp når en page returnerer
            kun meldinger publisert <= denne (effektiv inkrementell mode).

    Sekvensielle requests med ``pacing_sec`` mellom hver page per
    memory:free-api-no-parallel.

    Returnerer kombinert DataFrame. Tom hvis ingen meldinger.
    Reiser ``IipFetchError`` hvis api_key mangler.
    """
    import time

    key = api_key or get_secret(IIP_API_KEY_ENV)
    if not key:
        raise IipFetchError(
            f"IIP api_key missing — set env-var {IIP_API_KEY_ENV} or ~/.bedrock/secrets.env entry."
        )

    frames: list[pd.DataFrame] = []
    page = 1
    last_page: int | None = None

    while True:
        if page > 1:
            time.sleep(pacing_sec)
        try:
            df, last_page = fetch_iip_page(page, key, size=page_size, timeout=timeout)
        except IipFetchError as exc:
            _log.warning("iip.page_failed page=%d error=%s", page, exc)
            page += 1
            if max_pages is not None and page > max_pages:
                break
            continue

        if not df.empty:
            frames.append(df)

            if stop_before_published_ts is not None:
                pub_max = df["published_ts"].max()
                if pub_max is not None and str(pub_max) < stop_before_published_ts:
                    _log.info(
                        "iip.stop_before_pub_ts page=%d max_pub=%s threshold=%s",
                        page,
                        pub_max,
                        stop_before_published_ts,
                    )
                    break

        if max_pages is not None and page >= max_pages:
            break
        if last_page is not None and page >= last_page:
            break
        page += 1

    if not frames:
        return pd.DataFrame(columns=list(IIP_REMIT_COLS))
    combined = pd.concat(frames, ignore_index=True)
    # Dedup på message_id (siste vinner — viktig hvis API revurderer mid-fetch).
    combined = combined.drop_duplicates(subset=["message_id"], keep="last").reset_index(drop=True)
    return combined
