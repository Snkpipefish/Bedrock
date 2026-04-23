"""Pris-fetcher mot Stooq.

Stooq-endepunktet er et enkelt CSV-endepunkt, ingen auth, ingen JS. Støtter
daglige/ukentlige/månedlige bars.

URL-format:
    https://stooq.com/q/d/l/?s={ticker}&d1={YYYYMMDD}&d2={YYYYMMDD}&i=d

Returnerer CSV med header `Date,Open,High,Low,Close,Volume`. Vi returnerer
en `pd.DataFrame` som matcher `DataStore.append_prices`-kontrakten
(kolonner `ts, open, high, low, close, volume`).

Fase 3 session 10: kun daily (`i=d`). Andre intervaller kan legges til når
driver-scenarier krever det.
"""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

STOOQ_CSV_URL = "https://stooq.com/q/d/l/"


class PriceFetchError(RuntimeError):
    """Fetch av pris-data feilet permanent (ikke-retryable, eller retries brukt opp)."""


def build_stooq_url_params(
    ticker: str,
    from_date: date,
    to_date: date,
    interval: str = "d",
) -> dict[str, str]:
    """Bygg URL-parametre for Stooq CSV-endepunkt.

    Eksponert separat slik at `--dry-run` i CLI kan vise nøyaktig hvilken URL
    som ville blitt hentet uten å faktisk gjøre HTTP-kall.
    """
    return {
        "s": ticker.lower(),
        "d1": from_date.strftime("%Y%m%d"),
        "d2": to_date.strftime("%Y%m%d"),
        "i": interval,
    }


def fetch_prices(
    ticker: str,
    from_date: date,
    to_date: date,
    interval: str = "d",
) -> pd.DataFrame:
    """Hent daglige OHLCV-barer fra Stooq og returner som DataFrame.

    Kolonner: `ts` (pd.Timestamp), `open`, `high`, `low`, `close`, `volume`.

    Kaster `PriceFetchError` ved:
    - HTTP-feil som ikke løser seg på 3 retries
    - Stooq returnerer "No data" / tom respons
    - CSV er malformert
    """
    params = build_stooq_url_params(ticker, from_date, to_date, interval)
    _log.info(
        "fetch_prices ticker=%s from=%s to=%s interval=%s",
        ticker,
        from_date,
        to_date,
        interval,
    )

    try:
        response = http_get_with_retry(STOOQ_CSV_URL, params=params)
    except Exception as exc:
        raise PriceFetchError(f"Network failure fetching {ticker}: {exc}") from exc

    if response.status_code != 200:
        raise PriceFetchError(
            f"Stooq returned HTTP {response.status_code} for {ticker}: {response.text[:200]!r}"
        )

    text = response.text.strip()
    if not text or text.lower().startswith("no data"):
        raise PriceFetchError(f"Stooq returned no data for ticker={ticker!r}")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        raise PriceFetchError(f"Failed to parse Stooq CSV for {ticker}: {exc}") from exc

    return _normalize_stooq_df(df, ticker)


def _normalize_stooq_df(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Konverter Stooq's CSV-kolonner (`Date,Open,High,Low,Close,Volume`) til
    Bedrock-format (`ts,open,high,low,close,volume`)."""
    expected = {"Date", "Open", "High", "Low", "Close"}
    missing = expected - set(df.columns)
    if missing:
        raise PriceFetchError(
            f"Stooq CSV for {ticker} missing columns {missing}. Got: {list(df.columns)}"
        )

    out = pd.DataFrame(
        {
            "ts": pd.to_datetime(df["Date"]),
            "open": df["Open"].astype("float64"),
            "high": df["High"].astype("float64"),
            "low": df["Low"].astype("float64"),
            "close": df["Close"].astype("float64"),
            # Volume kan mangle for FX (Stooq skriver blankt / mangler kolonnen).
            "volume": (
                df["Volume"].astype("float64")
                if "Volume" in df.columns
                else pd.Series([None] * len(df), dtype="float64")
            ),
        }
    )
    return out
