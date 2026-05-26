# pyright: reportArgumentType=false, reportReturnType=false, reportAttributeAccessIssue=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]) og
# Series-vs-DataFrame-narrowing etter boolean-mask.

"""Shipping-indices fetcher (sub-fase 12.5+ session 113).

Henter Baltic-suiten av tørrbulk-fraktindekser. Per session 2026-05-26
har vi droppet BCI/BPI/BSI fra aktiv fyling — kun BDI vedlikeholdes:

- **BDI** (Baltic Dry Index, composite) — auto-fetch via BDRY ETF på Yahoo
  (~0.9 korrelasjon med ekte BDI). Lansert 2018; full historikk derfra.
  Alle eksisterende rules (wheat/corn/soybean/cotton/cocoa) bruker
  eksplisitt ``index=BDI`` for shipping_pressure-driveren.

BCI/BPI/BSI er Baltic Exchange-publiserte og kun tilgjengelig via betalte
feeds. Tidligere holdt vi en manuell CSV-fallback (``data/manual/
shipping_indices.csv``), men den ble ikke vedlikeholdt — de tre kodene
ble frosset på 2026-04-24-data, noe som ga falskt inntrykk av "4 indekser
aktive" mot downstream-konsumenter (cot-explorer). Per ADR-007 § 4
beholder vi muligheten for manuell CSV i koden (``fetch_shipping_manual_csv``),
men ``_VALID_INDICES`` ekskluderer nå BCI/BPI/BSI så ingen død data fylles
inn. Schema-konstanten ``_VALID_SHIPPING_INDEX_CODES`` i data/schemas.py
beholdes for forward-compat hvis en ekte feed dukker opp.

Schema for output: ``SHIPPING_INDICES_COLS`` (index_code, date, value, source).

Konsoliderer den gamle ``manual_events.fetch_bdi_via_bdry`` (session 89)
inn i Baltic-suiten.
"""

from __future__ import annotations

from datetime import date as _date
from pathlib import Path

import pandas as pd
import structlog

from bedrock.data.schemas import SHIPPING_INDICES_COLS

_log = structlog.get_logger(__name__)

_MANUAL_CSV = Path("data/manual/shipping_indices.csv")

# BCI/BPI/BSI er fjernet fra aktiv fyling (session 2026-05-26): ingen
# vedlikeholdt feed, manuell CSV ble ikke oppdatert. BDI er den eneste
# koden som faktisk forbrukes av drivere (alle rules: index=BDI).
_VALID_INDICES = ("BDI",)


def fetch_bdi_via_bdry(
    start_date: str = "2018-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """BDI-historikk via BDRY ETF på Yahoo.

    BDRY = Breakwave Dry Bulk Shipping ETF, futures-basert. Tracker BDI
    med ~0.9 korrelasjon. Driver-logikken (% change over window) er
    invariant under høy korrelasjon — gir samme retning-signal.

    Returns:
        DataFrame med ``SHIPPING_INDICES_COLS``-schema:
        (index_code='BDI', date, value, source='BDRY').
        Tom DataFrame hvis Yahoo-kall feiler eller returnerer 0 rader.
    """
    from bedrock.fetch.yahoo import fetch_yahoo_prices

    end = _date.fromisoformat(end_date) if end_date else _date.today()
    start = _date.fromisoformat(start_date)

    try:
        df = fetch_yahoo_prices("BDRY", start, end, interval="1d")
    except Exception as exc:
        _log.warning("shipping.bdry_fetch_failed", error=str(exc))
        return pd.DataFrame(columns=list(SHIPPING_INDICES_COLS))

    if df.empty:
        return pd.DataFrame(columns=list(SHIPPING_INDICES_COLS))

    out = pd.DataFrame(
        {
            "index_code": "BDI",
            "date": pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%d"),
            "value": df["close"].astype("float64"),
            "source": "BDRY",
        }
    )
    return out[list(SHIPPING_INDICES_COLS)]


def fetch_shipping_manual_csv(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt-populert shipping-indices-CSV.

    Forventet format:
        index_code,date,value,source
        BDI,2026-05-22,1850.0,MANUAL

    Filtrerer mot ``_VALID_INDICES`` (case-insensitive). Per session
    2026-05-26 er det kun BDI som aksepteres; rader med andre koder
    ignoreres lydløst. Returnerer tom DataFrame hvis filen ikke finnes.

    Raises:
        ValueError: hvis CSV-en mangler påkrevde kolonner.
    """
    if not csv_path.exists():
        _log.info("shipping.manual_csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(SHIPPING_INDICES_COLS))

    df = pd.read_csv(csv_path)
    missing = set(SHIPPING_INDICES_COLS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{csv_path.name} mangler kolonner: {sorted(missing)}. "
            f"Påkrevd: {list(SHIPPING_INDICES_COLS)}"
        )

    df = df[list(SHIPPING_INDICES_COLS)].copy()
    df["index_code"] = df["index_code"].astype(str).str.upper()
    df = df[df["index_code"].isin(_VALID_INDICES)].reset_index(drop=True)
    return df


def fetch_shipping_indices(
    start_date: str = "2018-01-01",
    end_date: str | None = None,
    csv_path: Path = _MANUAL_CSV,
) -> pd.DataFrame:
    """Hent full Baltic-suite: BDI fra Yahoo BDRY + BCI/BPI/BSI fra manuell CSV.

    Resultatet er konkatenert til én DataFrame som kan skrives med
    ``DataStore.append_shipping_indices``. Tom DataFrame hvis ingen
    kilde leverer data.
    """
    parts: list[pd.DataFrame] = []

    bdi = fetch_bdi_via_bdry(start_date=start_date, end_date=end_date)
    if not bdi.empty:
        parts.append(bdi)

    manual = fetch_shipping_manual_csv(csv_path)
    if not manual.empty:
        parts.append(manual)

    if not parts:
        return pd.DataFrame(columns=list(SHIPPING_INDICES_COLS))

    combined = pd.concat(parts, ignore_index=True)
    return combined[list(SHIPPING_INDICES_COLS)]


__all__ = [
    "fetch_bdi_via_bdry",
    "fetch_shipping_indices",
    "fetch_shipping_manual_csv",
]
