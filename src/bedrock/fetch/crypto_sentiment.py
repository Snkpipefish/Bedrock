# pyright: reportArgumentType=false, reportReturnType=false

"""Crypto sentiment fetcher (sub-fase 12.5+ session 115).

Henter to gratis-kilder:

- **alternative.me Fear & Greed Index** (F&G 0..100) — daglig
  oppdatert. Henter siste 30 verdier slik at vi har historikk fra
  første kjøring.

- **CoinGecko global API** — BTC/ETH-dominance, total market cap,
  24h endring. Daglig publiserings-cadence.

UI-only foreløpig per ADR-008 § 115. Schema (long-format `(indicator,
date, value, source)`) er scoring-ready slik at en fremtidig
``crypto_sentiment_pressure``-driver kan beregne contrarian-pressure
basert på F&G ekstreme verdier (<25 bullish, >75 bearish).

Sekvensielle HTTP-kall per memory-feedback (gratis-kilder skal ikke
parallelliseres). Manuell CSV-fallback fra dag 1 per ADR-007 § 4.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from bedrock.data.schemas import CRYPTO_SENTIMENT_COLS

_log = structlog.get_logger(__name__)

_MANUAL_CSV = Path("data/manual/crypto_sentiment.csv")
_FNG_BASE = "https://api.alternative.me/fng/"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3/global"
_DEFAULT_TIMEOUT = 12.0
_REQUEST_PACING_SEC = 1.5  # gratis-kilde: sekvensielt

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _http_get_json(url: str, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any] | None:
    """HTTP GET → JSON. Returnerer None ved feil (logget)."""
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        TimeoutError,
    ) as exc:
        _log.warning("crypto_sentiment.http_failed", url=url, error=str(exc))
        return None


def fetch_fear_and_greed(
    limit: int = 30,
    raw_response: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Hent siste N verdier av Fear & Greed Index fra alternative.me.

    Args:
        limit: antall historiske dager (default 30).
        raw_response: hvis gitt, brukes istedenfor HTTP-kall (testing).

    Returns:
        DataFrame med ``CRYPTO_SENTIMENT_COLS`` (indicator='crypto_fng',
        date, value, source='ALTERNATIVE_ME'). Tom DataFrame ved feil.
    """
    if raw_response is None:
        url = f"{_FNG_BASE}?limit={int(limit)}&format=json"
        raw_response = _http_get_json(url)
    if raw_response is None:
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))

    entries = raw_response.get("data") or []
    rows: list[dict[str, Any]] = []
    for e in entries:
        try:
            ts = int(e["timestamp"])
            value = float(e["value"])
        except (KeyError, ValueError, TypeError):
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        rows.append(
            {
                "indicator": "crypto_fng",
                "date": d.isoformat(),
                "value": value,
                "source": "ALTERNATIVE_ME",
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))
    return pd.DataFrame(rows)[list(CRYPTO_SENTIMENT_COLS)]


def fetch_coingecko_global(
    fetched_at: date | None = None,
    raw_response: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Hent CoinGecko global market data.

    Returnerer 4 indikatorer for ``fetched_at``-dato:
    - btc_dominance, eth_dominance (%)
    - total_mcap_usd (absolutt USD)
    - total_mcap_chg24h_pct (%)

    Args:
        fetched_at: dato-stempel (default = today UTC).
        raw_response: hvis gitt, brukes istedenfor HTTP-kall.

    Returns:
        DataFrame med ``CRYPTO_SENTIMENT_COLS`` (4 rader). Tom ved feil.
    """
    if raw_response is None:
        raw_response = _http_get_json(_COINGECKO_BASE)
    if raw_response is None:
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))

    fetched_at = fetched_at or datetime.now(timezone.utc).date()
    cg = raw_response.get("data") or {}

    pct_map = cg.get("market_cap_percentage") or {}
    mcap_map = cg.get("total_market_cap") or {}

    btc_dom = pct_map.get("btc")
    eth_dom = pct_map.get("eth")
    total_usd = mcap_map.get("usd")
    chg24h = cg.get("market_cap_change_percentage_24h_usd")

    rows: list[dict[str, Any]] = []
    for indicator, value in (
        ("btc_dominance", btc_dom),
        ("eth_dominance", eth_dom),
        ("total_mcap_usd", total_usd),
        ("total_mcap_chg24h_pct", chg24h),
    ):
        if value is None:
            continue
        try:
            v = float(value)
        except (ValueError, TypeError):
            continue
        rows.append(
            {
                "indicator": indicator,
                "date": fetched_at.isoformat(),
                "value": v,
                "source": "COINGECKO",
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))
    return pd.DataFrame(rows)[list(CRYPTO_SENTIMENT_COLS)]


def fetch_crypto_sentiment(
    fetched_at: date | None = None,
    fng_limit: int = 30,
    raw_fng: dict[str, Any] | None = None,
    raw_coingecko: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Hent F&G + CoinGecko i én operasjon.

    Sekvensielt: F&G først, så CoinGecko (gratis-API-etiquette,
    ikke parallelle kall).

    Returns:
        Combined DataFrame med ``CRYPTO_SENTIMENT_COLS``. Tom hvis
        begge kildene feiler.
    """
    parts: list[pd.DataFrame] = []

    fng_df = fetch_fear_and_greed(limit=fng_limit, raw_response=raw_fng)
    if not fng_df.empty:
        parts.append(fng_df)

    cg_df = fetch_coingecko_global(fetched_at=fetched_at, raw_response=raw_coingecko)
    if not cg_df.empty:
        parts.append(cg_df)

    if not parts:
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))

    combined = pd.concat(parts, ignore_index=True)
    return combined[list(CRYPTO_SENTIMENT_COLS)]


def fetch_crypto_sentiment_manual_csv(
    csv_path: Path = _MANUAL_CSV,
) -> pd.DataFrame:
    """Manuell CSV-fallback per ADR-007 § 4.

    Forventet schema: ``CRYPTO_SENTIMENT_COLS``.
    """
    if not csv_path.exists():
        _log.info("crypto_sentiment.manual_csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(CRYPTO_SENTIMENT_COLS))

    df = pd.read_csv(csv_path)
    missing = set(CRYPTO_SENTIMENT_COLS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{csv_path.name} mangler kolonner: {sorted(missing)}. "
            f"Påkrevd: {list(CRYPTO_SENTIMENT_COLS)}"
        )
    return df[list(CRYPTO_SENTIMENT_COLS)]


__all__ = [
    "fetch_coingecko_global",
    "fetch_crypto_sentiment",
    "fetch_crypto_sentiment_manual_csv",
    "fetch_fear_and_greed",
]
