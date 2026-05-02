# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).
"""ALSI (GIE) EU LNG-terminal storage fetcher (sub-fase 12.10 follow-up Spor C, session 136).

Endepunkt:
    https://alsi.gie.eu/api?country={code}&from=YYYY-MM-DD&to=YYYY-MM-DD
    https://alsi.gie.eu/api?type=eu&from=YYYY-MM-DD&to=YYYY-MM-DD   (EU-aggregat)

Header:
    x-key: $AGSI_API_KEY  (samme nøkkel som AGSI/IIP per § 22.1)

Krever API-nøkkel (gratis fra https://alsi.gie.eu/account, samme key dekker
AGSI+ALSI+IIP). Nøkkel lastes via ``bedrock.config.secrets`` (env-var eller
``~/.bedrock/secrets.env``, nøkkel ``AGSI_API_KEY``).

API-returformat (per dag, per country):
- inventory.gwh: LNG i lager (GWh)
- inventory.lng: LNG-volum (1000 m³, ikke lagret)
- dtmi.gwh: Daily Total Maximum Inventory (GWh, capacity ceiling)
- dtmi.lng: capacity i 1000 m³ (ikke lagret)
- sendOut: daglig utsending til grid (GWh/d)
- dtrs: Daily Total Reference Sendout (GWh/d, typisk capacity)
- gasDayStart: ISO YYYY-MM-DD

Konvertering: GWh → TWh (divider med 1000) for konsistens med AGSI.
``full_pct`` beregnes som ``inventory_twh / dtmi_twh * 100`` siden ALSI
ikke returnerer rå %-felt.

Sekvensielle requests med 1.5s pacing-delay per memory:free-api-no-parallel.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import pandas as pd

from bedrock.config.secrets import get_secret
from bedrock.data.schemas import ALSI_STORAGE_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

# Same key as AGSI per § 22.1 (verifisert 2026-05-02).
ALSI_API_KEY_ENV = "AGSI_API_KEY"
ALSI_BASE_URL = "https://alsi.gie.eu/api"
DEFAULT_TIMEOUT = 30.0
REQUEST_PACING_SEC = 1.5

# Default countries: EU-aggregat + 5 store LNG-importører.
DEFAULT_COUNTRIES: tuple[str, ...] = ("eu", "de", "nl", "fr", "it", "es")


class AlsiFetchError(RuntimeError):
    """ALSI-fetch feilet permanent (ikke-retryable, eller retries brukt opp)."""


def _to_float_or_none(v: Any) -> float | None:
    """Robust float-konvertering. ALSI returnerer numerikk som strings."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gwh_to_twh(gwh: float | None) -> float | None:
    if gwh is None:
        return None
    return gwh / 1000.0


def _normalize_record(rec: dict[str, Any], country: str) -> dict[str, Any] | None:
    """Konverter én ALSI-record til ALSI_STORAGE_COLS-format. None hvis ugyldig."""
    gas_day = rec.get("gasDayStart")
    if not gas_day:
        return None

    inventory_obj = rec.get("inventory") or {}
    dtmi_obj = rec.get("dtmi") or {}
    inventory_gwh = (
        _to_float_or_none(inventory_obj.get("gwh")) if isinstance(inventory_obj, dict) else None
    )
    dtmi_gwh = _to_float_or_none(dtmi_obj.get("gwh")) if isinstance(dtmi_obj, dict) else None
    send_out_gwh = _to_float_or_none(rec.get("sendOut"))
    dtrs_gwh = _to_float_or_none(rec.get("dtrs"))

    inventory_twh = _gwh_to_twh(inventory_gwh)
    dtmi_twh = _gwh_to_twh(dtmi_gwh)
    full_pct: float | None = None
    if inventory_twh is not None and dtmi_twh is not None and dtmi_twh > 0:
        full_pct = round(inventory_twh / dtmi_twh * 100.0, 4)

    return {
        "country": country.lower(),
        "gas_day_start": str(gas_day),
        "inventory_twh": inventory_twh,
        "dtmi_twh": dtmi_twh,
        "full_pct": full_pct,
        "send_out_twh": _gwh_to_twh(send_out_gwh),
        "dtrs_twh": _gwh_to_twh(dtrs_gwh),
    }


def fetch_alsi_country_range(
    country: str,
    api_key: str,
    *,
    from_date: date,
    to_date: date,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent ALSI-data for ett land over et dato-range.

    Args:
        country: ISO-2 lowercase eller "eu".
        api_key: GIE API-nøkkel (samme som AGSI/IIP).
        from_date / to_date: inkluderende dato-range.
        timeout: HTTP-timeout sekunder.
        raw_response: pre-parsed JSON for testing. Hopper over HTTP.

    Returns:
        DataFrame med ``ALSI_STORAGE_COLS``. Tom hvis ingen rader.

    Raises:
        AlsiFetchError: ved HTTP-feil eller uventet payload-struktur.
    """
    if raw_response is None:
        # ALSI v2: per-land bruker `?country=<ISO2>`, EU-aggregat under `?type=eu`.
        if country.lower() == "eu":
            params = {
                "type": "eu",
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "size": "300",
            }
        else:
            params = {
                "country": country,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "size": "300",
            }
        try:
            response = http_get_with_retry(
                ALSI_BASE_URL,
                params=params,
                timeout=timeout,
                headers={"x-key": api_key},
            )
        except Exception as exc:
            raise AlsiFetchError(f"alsi.{country}: network failure: {exc}") from exc

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise AlsiFetchError(f"alsi.{country}: HTTP {response.status_code}: {body_preview!r}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AlsiFetchError(f"alsi.{country}: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, dict):
        raise AlsiFetchError(f"alsi.{country}: expected JSON object, got {type(payload).__name__}")

    raw_rows = payload.get("data", [])
    if not isinstance(raw_rows, list):
        raise AlsiFetchError(f"alsi.{country}: 'data' must be list, got {type(raw_rows).__name__}")

    rows: list[dict[str, Any]] = []
    for rec in raw_rows:
        if not isinstance(rec, dict):
            continue
        normalized = _normalize_record(rec, country)
        if normalized is not None:
            rows.append(normalized)

    df = pd.DataFrame(rows, columns=list(ALSI_STORAGE_COLS))
    _log.info("alsi.fetched country=%s rows=%d", country, len(df))
    return df


def fetch_alsi_storage(
    *,
    countries: Sequence[str] = DEFAULT_COUNTRIES,
    api_key: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    pacing_sec: float = REQUEST_PACING_SEC,
) -> pd.DataFrame:
    """Hent ALSI for alle gitte countries sekvensielt og kombinér.

    Default-vinduet er siste 30 dager hvis from/to ikke gitt — passer
    daglig fetcher-bruk. For backfill, bruk ``scripts/backfill/alsi.py``
    med eksplisitte dato-grenser.

    Per memory:free-api-no-parallel-requests sender vi sekvensielt med
    ``pacing_sec`` mellom hver country-request.

    Returnerer kombinert DataFrame. Tom hvis ingen countries leverte
    data. Reiser ``AlsiFetchError`` hvis api_key mangler.
    """
    import time

    key = api_key or get_secret(ALSI_API_KEY_ENV)
    if not key:
        raise AlsiFetchError(
            f"ALSI api_key missing — set env-var {ALSI_API_KEY_ENV} "
            f"or ~/.bedrock/secrets.env entry."
        )

    today = date.today()
    end = to_date or today
    start = from_date or (today - timedelta(days=30))

    frames: list[pd.DataFrame] = []
    for i, country in enumerate(countries):
        if i > 0:
            time.sleep(pacing_sec)
        try:
            df = fetch_alsi_country_range(
                country, key, from_date=start, to_date=end, timeout=timeout
            )
        except AlsiFetchError as exc:
            _log.warning("alsi.country_failed country=%s error=%s", country, exc)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=list(ALSI_STORAGE_COLS))
    return pd.concat(frames, ignore_index=True)
