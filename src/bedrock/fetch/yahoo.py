# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""Yahoo Finance pris-fetcher.

Port av cot-explorers `build_price_history.py` (verifisert i produksjon
gjennom 15 års historikk-bygging). Bedrock erstatter Stooq som
primærkilde i Fase 10 session 58 — Stooq begynte å kreve API-nøkkel
som blokkerte backfill.

Endepunkt:
    https://query1.finance.yahoo.com/v8/finance/chart/{ticker}

Ingen auth, ingen API-nøkkel. Returnerer JSON med timestamp + OHLCV.

Konvensjoner overtatt fra cot-explorer:
- Bruker `urllib.request` (ikke `requests`) for å matche bevist
  produksjons-implementasjon. `requests` ville krevd ekstra dep
  for bare GET med User-Agent.
- User-Agent "Mozilla/5.0" + Accept "application/json" — Yahoo
  returnerer 403 uten User-Agent.
- 15 sekunders timeout.
- Ingen parallell henting (per bruker-instruks): gratis APIer
  feiler med parallelle kall. Caller (CLI) må kjøre sekvensielt
  med 1-2 sek sleep mellom symboler.

Format-mismatch løses i `fetch_yahoo_prices`: Yahoo gir oss epoch-
timestamps + nullable OHLCV-arrays. Vi kaster rader hvor `close` er
None (helger eller manglende observasjoner), og returnerer DataFrame
matching `DataStore.append_prices`-kontrakten (kolonner ts, open,
high, low, close, volume).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Literal

import pandas as pd

_log = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
"""Yahoo Finance chart-endepunkt-base."""

YahooInterval = Literal["1d", "1wk", "1mo"]
"""Støttede intervaller. Yahoo har flere men disse er de vi bruker."""

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}
"""Headers som Yahoo aksepterer. Tomme headers gir 403."""


class YahooFetchError(RuntimeError):
    """Yahoo-fetch feilet permanent (HTTP-feil eller malformert JSON)."""


def build_yahoo_url(
    ticker: str,
    from_date: date,
    to_date: date,
    interval: YahooInterval = "1d",
) -> str:
    """Bygg Yahoo Chart-URL. Eksponert for `--dry-run`-bruk.

    Datoer konverteres til Unix-epoch (UTC midnatt). Yahoo bruker
    halvåpne intervaller [period1, period2), så `to_date + 1 dag`
    inkluderer `to_date` selv.
    """
    period1 = int(datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    period2 = int(
        datetime.combine(to_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() + 86400
    )
    encoded = urllib.parse.quote(ticker, safe="")
    return f"{YAHOO_CHART_URL}/{encoded}?interval={interval}&period1={period1}&period2={period2}"


def fetch_yahoo_prices(
    ticker: str,
    from_date: date,
    to_date: date,
    interval: YahooInterval = "1d",
    timeout_sec: float = 15.0,
) -> pd.DataFrame:
    """Hent OHLCV-bars fra Yahoo Finance.

    Returnerer pd.DataFrame matching `DataStore.append_prices`-kontrakten:
    kolonner `ts`, `open`, `high`, `low`, `close`, `volume`. `ts` er
    pd.Timestamp i UTC.

    Rader hvor `close` er None (helger, holidays) ekskluderes — de gir
    ingen mening i en pris-tidserie og ville lekke som NaN i drivere.

    Kaster `YahooFetchError` ved nettverks-feil eller malformert JSON.
    """
    url = build_yahoo_url(ticker, from_date, to_date, interval)
    _log.info(
        "fetch_yahoo_prices ticker=%s interval=%s from=%s to=%s",
        ticker,
        interval,
        from_date,
        to_date,
    )

    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            payload = r.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise YahooFetchError(f"Network failure for {ticker}: {exc}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise YahooFetchError(f"Failed to parse Yahoo JSON for {ticker}: {exc}") from exc

    return parse_yahoo_chart(data, ticker)


def parse_yahoo_chart(data: dict, ticker: str) -> pd.DataFrame:
    """Konverter Yahoo Chart-respons til Bedrock-prisformat.

    Eksponert separat fra `fetch_yahoo_prices` slik at testene kan
    kjøre mot statisk fixture uten HTTP. Robust mot mangelende felt
    og None-verdier i OHLCV-arrays.
    """
    cols = ["ts", "open", "high", "low", "close", "volume"]

    chart = data.get("chart")
    if not isinstance(chart, dict):
        raise YahooFetchError(f"Yahoo response missing 'chart' for {ticker}")

    err = chart.get("error")
    if err is not None:
        raise YahooFetchError(f"Yahoo returned error for {ticker}: {err}")

    results = chart.get("result")
    if not results:
        # Tom result-liste betyr at ticker ikke finnes / ingen data i området
        return pd.DataFrame(columns=cols)

    res = results[0]
    timestamps = res.get("timestamp") or []
    indicators = res.get("indicators") or {}
    quote_blocks = indicators.get("quote") or [{}]
    quote = quote_blocks[0]

    opens = quote.get("open") or [None] * len(timestamps)
    highs = quote.get("high") or [None] * len(timestamps)
    lows = quote.get("low") or [None] * len(timestamps)
    closes = quote.get("close") or [None] * len(timestamps)
    volumes = quote.get("volume") or [None] * len(timestamps)

    rows: list[dict[str, object]] = []
    for i, ts in enumerate(timestamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append(
            {
                "ts": ts_dt,
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": float(c),
                "volume": volumes[i] if i < len(volumes) else None,
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)

    return pd.DataFrame(rows, columns=cols)
