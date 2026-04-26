# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs typer DataFrame-konstruktor med columns=list[str] dårlig.

"""Manuell-CSV-driven event-fetchere (PLAN § 7.3 Fase-5/6).

Tre hendelses-baserte datakilder:

1. **Eksport-policy events** (India/Indonesia/Ivory Coast eksport-
   restriksjoner, kvoter, forbud) — manuelt kuratert kalender.
   ``data/manual/export_events.csv``

2. **Disease/pest-varsler** (coffee rust, wheat stripe rust, locust
   outbreaks) — eksterne services som PestMon/CABI er paid; her
   manuell registrering.
   ``data/manual/disease_alerts.csv``

3. **Baltic Dry Index** (BDI) — auto-fetcher via BDRY ETF (Breakwave
   Dry Bulk Shipping ETF) på Yahoo som proxy for BDI-indeksen
   (~0.9 korrelasjon). Manuell CSV (``data/manual/bdi.csv``) som
   fallback. Bruk ``fetch_bdi_via_bdry()`` for auto-modus.

CLI-kommandoer for append/list er i ``bedrock.cli.manual_events``.

Bruk:
    from bedrock.fetch.manual_events import (
        fetch_export_events, fetch_disease_alerts, fetch_bdi,
        fetch_bdi_via_bdry,
    )
    # Manual CSV-modus:
    df = fetch_export_events()
    store.append_export_events(df)

    # Auto-modus for BDI:
    df = fetch_bdi_via_bdry()
    store.append_bdi(df)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

from bedrock.data.schemas import (
    BDI_COLS,
    DISEASE_ALERTS_COLS,
    EXPORT_EVENTS_COLS,
    IGC_COLS,
)

_log = structlog.get_logger(__name__)

_EXPORT_EVENTS_CSV = Path("data/manual/export_events.csv")
_DISEASE_ALERTS_CSV = Path("data/manual/disease_alerts.csv")
_BDI_CSV = Path("data/manual/bdi.csv")
_IGC_CSV = Path("data/manual/igc.csv")


def _read_manual_csv(csv_path: Path, expected_cols: tuple[str, ...]) -> pd.DataFrame:
    """Les manuell CSV med schema-validering.

    Tom DataFrame returneres hvis filen ikke finnes.
    Kaster ValueError hvis kolonner mangler.
    """
    if not csv_path.exists():
        _log.info("manual.csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(expected_cols))

    df = pd.read_csv(csv_path)
    missing = set(expected_cols) - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} mangler kolonner: {sorted(missing)}")
    return df[list(expected_cols)]


def fetch_export_events(csv_path: Path = _EXPORT_EVENTS_CSV) -> pd.DataFrame:
    """Eksport-policy events fra manuell CSV.

    Schema: ``EXPORT_EVENTS_COLS``.
    Eksempel-rad:
        2024-07-15,INDIA,RICE,EXPORT_BAN,5,BULL,
        "India announces broken rice export ban",
        "https://example.com/news/..."
    """
    return _read_manual_csv(csv_path, EXPORT_EVENTS_COLS)


def fetch_disease_alerts(csv_path: Path = _DISEASE_ALERTS_CSV) -> pd.DataFrame:
    """Disease/pest-varsler fra manuell CSV.

    Schema: ``DISEASE_ALERTS_COLS``.
    Eksempel-rad:
        2024-09-01,BRAZIL,COFFEE,COFFEE_RUST,3,5.0,
        "Hemileia vastatrix outbreak in Minas Gerais",
        "https://example.com/agronomy/..."
    """
    return _read_manual_csv(csv_path, DISEASE_ALERTS_COLS)


def fetch_bdi(csv_path: Path = _BDI_CSV) -> pd.DataFrame:
    """Baltic Dry Index fra manuell CSV.

    Schema: ``BDI_COLS`` — date, value, source. ``source`` markerer
    hvor verdien kommer fra (MANUAL, BDRY, TRADINGECONOMICS, BLOOMBERG).

    Eksempel-rad:
        2025-04-15,1845.0,MANUAL
    """
    return _read_manual_csv(csv_path, BDI_COLS)


def fetch_bdi_via_bdry(
    start_date: str = "2010-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """Auto-fetch BDI via BDRY ETF (Breakwave Dry Bulk Shipping ETF).

    BDRY er en futures-basert ETF som tracker BDI-indeksen med ~0.9
    korrelasjon. Gratis Yahoo-data (BDRY ble lansert i 2018, så
    historikk fra ~2018-onward).

    Returns:
        DataFrame med BDI_COLS-schema (date, value, source='BDRY').
        Verdiene er BDRY close-priser (ikke faktiske BDI-verdier),
        men driver-logikken (% change over window) gir samme signal
        siden korrelasjonen er høy.

    Args:
        start_date: ISO-dato for backfill-start.
        end_date: ISO-dato for slutt (default = i dag).
    """
    from datetime import date as _date

    from bedrock.fetch.yahoo import fetch_yahoo_prices

    end = _date.fromisoformat(end_date) if end_date else _date.today()
    start = _date.fromisoformat(start_date)

    try:
        df = fetch_yahoo_prices("BDRY", start, end, interval="1d")
    except Exception as exc:
        _log.warning("bdi.bdry_fetch_failed", error=str(exc))
        return pd.DataFrame(columns=list(BDI_COLS))

    if df.empty:
        return pd.DataFrame(columns=list(BDI_COLS))

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%d"),
            "value": df["close"].astype("float64"),
            "source": "BDRY",
        }
    )
    return out[list(BDI_COLS)]


def fetch_igc(csv_path: Path = _IGC_CSV) -> pd.DataFrame:
    """IGC (International Grains Council) Grain Market Report fra manuell CSV.

    IGC publiserer månedlig PDF (paid subscription). Manuell CSV-
    populering anbefales for production-bruk.

    Schema: ``IGC_COLS`` — report_date, marketing_year, grain, metric,
    value_mil_tons.

    Eksempel-rad:
        2025-04-25,2025/26,WHEAT,PRODUCTION,800.5
    """
    return _read_manual_csv(csv_path, IGC_COLS)


__all__ = ["fetch_bdi", "fetch_disease_alerts", "fetch_export_events", "fetch_igc"]
