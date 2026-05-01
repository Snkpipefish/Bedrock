# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).
"""AAII Sentiment Survey fetcher (sub-fase 12.7 D2 A12, session 131).

Endepunkt:
    https://www.aaii.com/files/surveys/sentiment.xls

AAII publiserer sin ukentlige investor-sentiment-survey som .xls-fil.
Filen har historikk fra 1987+ og oppdateres torsdager. Schema (etter
header-rader) — typisk:
    Reported Date | Bullish | Neutral | Bearish | Bull-Bear Spread
    | ... (eldre kolonner trimmes vekk)

Driver (`aaii_extreme`) bruker bullish_pct + bearish_pct til mean-
reversion-scoring. Per pattern-doc § 3.2: "extreme_contrarian_score" er
driver-intern output-konvensjon, ikke ny polarity-type.

Per ADR-007 § 4: fragile HTML/XLS-skraping ⇒ manuell CSV-fallback fra
dag 1. Fallback-fil i `data/manual/aaii_sentiment.csv`.

Sekvensiell HTTP-pacing per memory:`free-api-no-parallel-requests`.
"""

from __future__ import annotations

import io
import logging
from datetime import date
from typing import Any

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

AAII_URL = "https://www.aaii.com/files/surveys/sentiment.xls"
DEFAULT_TIMEOUT = 60.0  # filen er ~1.1 MB; gi den litt rom

AAII_COLS = ("date", "bullish_pct", "neutral_pct", "bearish_pct", "bull_bear_spread")


class AaiiFetchError(RuntimeError):
    """AAII-fetch feilet permanent."""


def _parse_aaii_excel(blob: bytes) -> pd.DataFrame:
    """Parse AAII sentiment.xls til DataFrame med AAII_COLS.

    AAII-filen har inkonsistente header-rader øverst (titler, blanke rader)
    og blandede ark. Strategi:
    1. Prøv xlrd-engine først (filen er .xls fra 1987-format).
    2. Fall-back til openpyxl hvis filen er .xlsx-formattert.
    3. Hopp over header-rader: skann etter rad som har en parsbar dato i
       første kolonne.
    4. Behold de 4 numeriske kolonnene som inneholder bullish/neutral/
       bearish/spread (typisk kolonne B-E etter datokolonnen).
    """
    # Prøv xlrd først
    df_raw: pd.DataFrame | None = None
    last_error: Exception | None = None
    for engine in ("xlrd", "openpyxl"):
        try:
            df_raw = pd.read_excel(
                io.BytesIO(blob),
                engine=engine,
                sheet_name=0,
                header=None,
            )
            break
        except Exception as exc:
            last_error = exc
            continue

    if df_raw is None or df_raw.empty:
        raise AaiiFetchError(f"could not parse AAII xls: {last_error}")

    # Finn første rad med parsbar dato i kolonne 0.
    first_data_row: int | None = None
    for idx in range(min(20, len(df_raw))):
        val = df_raw.iat[idx, 0]
        try:
            parsed = pd.to_datetime(val, errors="coerce")
            if parsed is not None and not pd.isna(parsed):
                first_data_row = idx
                break
        except Exception:
            continue

    if first_data_row is None:
        raise AaiiFetchError("no data rows with parsable date in first 20 rows")

    df = df_raw.iloc[first_data_row:].copy()
    df.columns = [f"col{i}" for i in range(df.shape[1])]

    # Forventet kolonne-rekkefølge: date, bullish, neutral, bearish, [spread]
    # Plukk de første 4 numeriske kolonner etter dato.
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df["col0"], errors="coerce")
    out["bullish_pct"] = pd.to_numeric(df.get("col1"), errors="coerce")
    out["neutral_pct"] = pd.to_numeric(df.get("col2"), errors="coerce")
    out["bearish_pct"] = pd.to_numeric(df.get("col3"), errors="coerce")
    # AAII Excel col4 har vist seg å være "Total" (bull + neutral + bear ≈ 100),
    # ikke spread. Beregn alltid fra bullish - bearish — det er den canonical
    # AAII bull-bear-spread-definisjonen. Sub-fase 12.8 fix.
    out["bull_bear_spread"] = out["bullish_pct"] - out["bearish_pct"]

    out = out.dropna(subset=["date", "bullish_pct"])

    # AAII rapporterer i prosent (0-100) som 0.40-style decimal eller
    # 40.0-style int. Detekter format: hvis median ≤ 1.0, multipliser med 100.
    if not out["bullish_pct"].empty and out["bullish_pct"].median() <= 1.0:
        out["bullish_pct"] = out["bullish_pct"] * 100.0
        out["neutral_pct"] = out["neutral_pct"] * 100.0
        out["bearish_pct"] = out["bearish_pct"] * 100.0
        out["bull_bear_spread"] = out["bull_bear_spread"] * 100.0

    out = out.sort_values("date").reset_index(drop=True)
    return out[list(AAII_COLS)]


def fetch_aaii_sentiment(
    *,
    timeout: float = DEFAULT_TIMEOUT,
    raw_response: Any = None,
) -> pd.DataFrame:
    """Hent AAII Sentiment Survey og returner DataFrame med AAII_COLS.

    Args:
        timeout: HTTP-timeout sekunder.
        raw_response: pre-fetched bytes (eller pre-parsed DataFrame) for
            testing. Hvis bytes: parses som xls. Hvis DataFrame: returneres
            direkte.

    Returns:
        DataFrame med kolonner ``date, bullish_pct, neutral_pct,
        bearish_pct, bull_bear_spread``. Dato sortert ASC.

    Raises:
        AaiiFetchError: ved HTTP-feil eller parse-feil.
    """
    if raw_response is None:
        try:
            response = http_get_with_retry(
                AAII_URL,
                timeout=timeout,
                headers={"User-Agent": "Bedrock-data-fetch/1.0 (research)"},
            )
        except Exception as exc:
            raise AaiiFetchError(f"network failure: {exc}") from exc
        if response.status_code != 200:
            raise AaiiFetchError(f"HTTP {response.status_code} from {AAII_URL}")
        blob = response.content
    elif isinstance(raw_response, pd.DataFrame):
        return raw_response[list(AAII_COLS)].copy()
    elif isinstance(raw_response, bytes):
        blob = raw_response
    else:
        raise AaiiFetchError(
            f"raw_response must be bytes or DataFrame, got {type(raw_response).__name__}"
        )

    df = _parse_aaii_excel(blob)
    _log.info("aaii.fetched rows=%d range=%s..%s", len(df), df["date"].min(), df["date"].max())
    return df


def filter_from_date(df: pd.DataFrame, from_date: date | None) -> pd.DataFrame:
    """Filtrer DataFrame til datoer ≥ from_date. None = ingen filtering."""
    if from_date is None:
        return df
    cutoff = pd.Timestamp(from_date)
    return df[df["date"] >= cutoff].reset_index(drop=True)
