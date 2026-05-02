"""Backfill IRI ENSO Plumes 3-month-ahead forecast (Spor F4).

Leser manuelt-populert CSV ``data/manual/iri_enso_forecast.csv`` med
kolonnene ``issue_date,target_period,nino34_mean_c`` og lagrer
``nino34_mean_c`` i ``fundamentals``-tabellen under series_id
``IRI_ENSO_FCST_3MO``. Dette gjør at driver
``noaa_enso_forecast_3mo`` kan lese forecasten via samme
``store.get_fundamentals``-API som ``noaa_oni_index``.

Kilde: https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/
IRI publiserer månedlig (rundt 20.) ensemble-mean Niño 3.4 SST-anomali
for forecast-vinduet ~3 mnd fram. Bruker leser av ensemble-mean fra
plume-grafen og legger inn én rad per måned.

Per ADR-007 § 4 manuell CSV-fallback (samme pattern som
ism_pmi.csv-flyten i Spor F1).

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/backfill/iri_enso_forecast.py
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

SERIES_ID = "IRI_ENSO_FCST_3MO"
DEFAULT_CSV = Path("data/manual/iri_enso_forecast.csv")


def load_iri_csv(csv_path: Path) -> pd.DataFrame:
    """Les manuelt CSV og produserer DataFrame i FUNDAMENTALS_COLS-format.

    Forventet input-kolonner: ``issue_date,target_period,nino34_mean_c``.
    Output-kolonner: ``series_id,date,value``.
    """
    df = pd.read_csv(csv_path)
    required = {"issue_date", "nino34_mean_c"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"iri_enso_forecast CSV mangler kolonner: {sorted(missing)} (har: {sorted(df.columns)})"
        )

    out = pd.DataFrame(
        {
            "series_id": SERIES_ID,
            "date": pd.to_datetime(df["issue_date"]).dt.strftime("%Y-%m-%d"),
            "value": pd.to_numeric(df["nino34_mean_c"], errors="coerce"),
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

    df = load_iri_csv(args.csv)
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
