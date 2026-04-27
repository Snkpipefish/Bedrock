# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""COMEX warehouse-inventory fetcher (sub-fase 12.5+ session 108).

Henter daglige stocks for gull (XAU), sølv (XAG), og kobber (HG) fra
metalcharts.org's JSON-API. Cot-explorer's `fetch_comex.py` brukte
samme API som primær + heavymetalstats/goldsilver som fallbacks; vi
porter kun primær-kilden + bruker manuell CSV som fallback (per
ADR-007 § 4 — fragile HTML-skraper-fallbacks gir mer drift enn nytte).

API-mønster:
    1. GET https://metalcharts.org/api/security/token
       -> {"token": "..."}
    2. Header `X-MC-Token: <token>` for alle påfølgende kall.
    3. GET https://metalcharts.org/api/comex/inventory?symbol=XAU&type=latest
       -> {"success": true, "data": {"registered": ..., "eligible": ...,
                                      "total": ..., "date": "...", ...}}

Sekvensielle HTTP per memory-feedback (gratis-API → ingen parallell).
Manuell CSV-fallback i ``data/manual/comex_inventory.csv``.

Symbol-mapping (cot-explorer-presedens):
- XAU -> gold (oz)
- XAG -> silver (oz)
- HG  -> copper (st = short tons; reg/elig-skillet fjernet av CME)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import COMEX_INVENTORY_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

_MC_BASE = "https://metalcharts.org"
_DEFAULT_TIMEOUT = 30.0
_REQUEST_PACING_SEC = 1.5
_MANUAL_CSV = Path("data/manual/comex_inventory.csv")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Symbol-katalog
# ---------------------------------------------------------------------------


class _MetalSpec:
    __slots__ = ("label", "metal", "symbol", "units")

    def __init__(self, symbol: str, metal: str, units: str, label: str):
        self.symbol = symbol
        self.metal = metal
        self.units = units
        self.label = label


DEFAULT_METALS: tuple[_MetalSpec, ...] = (
    _MetalSpec("XAU", "gold", "oz", "COMEX Gold Stocks (troy oz)"),
    _MetalSpec("XAG", "silver", "oz", "COMEX Silver Stocks (troy oz)"),
    _MetalSpec("HG", "copper", "st", "COMEX Copper Stocks (short tons)"),
)


# ---------------------------------------------------------------------------
# Token + per-metal fetch (sekvensiell)
# ---------------------------------------------------------------------------


def _fetch_token(timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Hent X-MC-Token fra metalcharts.org. Returnerer token-strengen."""
    response = http_get_with_retry(
        f"{_MC_BASE}/api/security/token",
        headers=_HEADERS,
        timeout=timeout,
    )
    if response.status_code != 200:
        raise ValueError(f"comex.token: HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("comex.token: payload not a dict")
    token = payload.get("token")
    if not token or not isinstance(token, str):
        raise ValueError("comex.token: missing 'token' field")
    return token


def fetch_comex_metal(
    spec: _MetalSpec,
    token: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    raw_response: Any = None,  # injection for testing
) -> pd.DataFrame:
    """Hent siste rad for ett metall. Returnerer DataFrame med 0..1 rad.

    Cot-explorer's `fetch_comex.py` har en spesial-håndtering for kobber
    der CME har fjernet reg/elig-skillet — `total` brukes som
    `registered`, `eligible` settes til 0. Samme logikk her.

    Args:
        spec: hvilket metall.
        token: X-MC-Token fra _fetch_token().
        timeout: HTTP-timeout.
        raw_response: pre-parsed JSON-dict for testing.

    Returns:
        DataFrame med 1 rad (eller 0 hvis API ga uventet payload).

    Raises:
        ValueError: ved HTTP-feil eller uventet response-struktur.
    """
    if raw_response is None:
        headers = dict(_HEADERS)
        headers["X-MC-Token"] = token
        response = http_get_with_retry(
            f"{_MC_BASE}/api/comex/inventory",
            params={"symbol": spec.symbol, "type": "latest"},
            headers=headers,
            timeout=timeout,
        )
        if response.status_code != 200:
            raise ValueError(f"comex.{spec.symbol}: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"comex.{spec.symbol}: invalid JSON: {exc}") from exc
    else:
        payload = raw_response

    if not isinstance(payload, dict):
        raise ValueError(f"comex.{spec.symbol}: expected JSON object, got {type(payload).__name__}")

    if not payload.get("success"):
        _log.warning("comex.api_unsuccessful symbol=%s payload=%s", spec.symbol, payload)
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))

    data = payload.get("data")
    if not isinstance(data, dict):
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))

    raw_date = data.get("date")
    if not raw_date:
        _log.warning("comex.missing_date symbol=%s", spec.symbol)
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))

    iso_date = str(raw_date)[:10]

    raw_reg = data.get("registered") or 0
    raw_elig = data.get("eligible") or 0
    raw_total = data.get("total") or 0

    try:
        reg = float(raw_reg)
        elig = float(raw_elig)
        total = float(raw_total)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"comex.{spec.symbol}: non-numeric values: {exc}") from exc

    # Kobber-spesifikk: CME har fjernet reg/elig-skillet for HG.
    # API kan returnere reg=0 + elig=0 + total>0 → bruk total som
    # registered, eligible=0 (cot-explorer-presedens).
    if spec.symbol == "HG" and reg == 0 and elig == 0 and total > 0:
        reg = total
        elig = 0.0

    df = pd.DataFrame(
        [
            {
                "metal": spec.metal,
                "date": iso_date,
                "registered": reg,
                "eligible": elig,
                "total": total,
                "units": spec.units,
            }
        ],
        columns=list(COMEX_INVENTORY_COLS),
    )
    _log.info(
        "comex.fetched metal=%s date=%s reg=%.0f elig=%.0f total=%.0f",
        spec.metal,
        iso_date,
        reg,
        elig,
        total,
    )
    return df


def fetch_comex(
    *,
    metals: Sequence[_MetalSpec] = DEFAULT_METALS,
    timeout: float = _DEFAULT_TIMEOUT,
    pacing_sec: float = _REQUEST_PACING_SEC,
    csv_path: Path = _MANUAL_CSV,
    token: str | None = None,
) -> pd.DataFrame:
    """Hent alle metall sekvensielt. Faller tilbake på manuell CSV ved feil.

    Mellom hver request settes pacing-delay (default 1.5s). Per-metall-
    feil aborterer ikke kjøringen — failed metaller logges.

    Returnerer kombinert DataFrame. Tom hvis både API og CSV ga 0 rader.
    """
    api_df = pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))
    try:
        api_df = _fetch_via_api(metals=metals, timeout=timeout, pacing_sec=pacing_sec, token=token)
    except Exception as exc:
        _log.warning("comex.api_failed_fallback_to_csv error=%s", exc)

    if not api_df.empty:
        return api_df

    try:
        return fetch_comex_manual(csv_path)
    except Exception as exc:
        _log.warning("comex.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))


def _fetch_via_api(
    *,
    metals: Sequence[_MetalSpec],
    timeout: float,
    pacing_sec: float,
    token: str | None,
) -> pd.DataFrame:
    """Helper: hent token + iterer metaller sekvensielt."""
    if token is None:
        token = _fetch_token(timeout=timeout)

    frames: list[pd.DataFrame] = []
    for i, spec in enumerate(metals):
        if i > 0:
            time.sleep(pacing_sec)
        try:
            df = fetch_comex_metal(spec, token, timeout=timeout)
        except Exception as exc:
            _log.warning("comex.metal_failed symbol=%s error=%s", spec.symbol, exc)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Manuell CSV-fallback
# ---------------------------------------------------------------------------


def fetch_comex_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert CSV fra ``data/manual/comex_inventory.csv``.

    Returnerer tom DataFrame hvis filen mangler. Reiser ``ValueError``
    hvis filen finnes men mangler påkrevde kolonner.
    """
    if not csv_path.exists():
        _log.info("comex.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(COMEX_INVENTORY_COLS))

    df = pd.read_csv(csv_path)
    missing = [c for c in COMEX_INVENTORY_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"comex_inventory manual CSV mangler kolonner: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[list(COMEX_INVENTORY_COLS)].copy()


__all__ = [
    "DEFAULT_METALS",
    "_MetalSpec",
    "fetch_comex",
    "fetch_comex_manual",
    "fetch_comex_metal",
]
