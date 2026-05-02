"""Backfill ISM Manufacturing PMI (monthly headline) for Spor F1.

Leser manuelt-populert CSV ``data/manual/ism_pmi.csv`` med kolonnene
``report_month,headline_pmi,source`` og lagrer ``headline_pmi`` i
``fundamentals``-tabellen under series_id ``ISM_PMI``. Driver
``ism_pmi_level`` i ``macro_bunke3`` leser denne via samme
``store.get_fundamentals``-API som FRED-baserte drivere.

Per ADR-007 § 4 manuell CSV-fallback. ISM Manufacturing PMI publiseres
første virkedag i måneden (08:00 ET) — bruker registrerer headline-
PMI fra ISM Report on Business (https://www.ismworld.org/...).
FRED-serien NAPMPMI returnerer 404 (ISM trakk gratis-feeden), så
manuell ingestion er eneste gratis-metode.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill/ism_pmi.py
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

SERIES_ID = "ISM_PMI"
DEFAULT_CSV = Path("data/manual/ism_pmi.csv")


def load_ism_csv(csv_path: Path) -> pd.DataFrame:
    """Les manuelt CSV og produserer DataFrame i FUNDAMENTALS_COLS-format.

    Forventet input-kolonner: ``report_month,headline_pmi``.
    Output-kolonner: ``series_id,date,value``. Bruker den første dagen
    i ``report_month`` som date (canonical ISM-publisering = first
    virkedag, men 1. brukes som kanonisk).
    """
    df = pd.read_csv(csv_path)
    required = {"report_month", "headline_pmi"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"ism_pmi CSV mangler kolonner: {sorted(missing)} (har: {sorted(df.columns)})"
        )

    out = pd.DataFrame(
        {
            "series_id": SERIES_ID,
            "date": pd.to_datetime(df["report_month"]).dt.strftime("%Y-%m-01"),
            "value": pd.to_numeric(df["headline_pmi"], errors="coerce"),
        }
    )
    out = out.dropna(subset=["value"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/bedrock.db")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        _log.error("CSV mangler: %s", args.csv)
        return 1

    df = load_ism_csv(args.csv)
    if df.empty:
        _log.warning("Ingen gyldige rader i %s", args.csv)
        return 0

    store = DataStore(Path(args.db))
    n = store.append_fundamentals(df)
    _log.info(
        "%s: %d rader skrevet (%s..%s)",
        SERIES_ID,
        n,
        df["date"].min(),
        df["date"].max(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
