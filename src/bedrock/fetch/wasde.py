# pyright: reportAttributeAccessIssue=false, reportReturnType=false, reportArgumentType=false, reportCallIssue=false, reportOptionalMemberAccess=false
# pandas-stubs har dårlig dekning av .str-aksessor og .map() på Series med Optional/Unknown.

"""USDA WASDE fetcher (PLAN § 7.3 Fase-4).

WASDE-rapporter publiseres månedlig (~10. hver måned) og inneholder
ending stocks, yield-prognoser, og stocks-to-use ratio for major
commodities (corn, wheat, soybeans, rice, cotton).

USDA publiserer en konsolidert historisk CSV (2010-onward) på
https://www.usda.gov/oce/commodity-markets/wasde. Direkte URL kan
endre seg; auto-fetcher prøver kjente URL-er, fallback til manuell
CSV.

Manuell CSV-fallback: ``data/manual/wasde.csv``.

Bruk:
    from bedrock.fetch.wasde import fetch_wasde
    df = fetch_wasde()
    store.append_wasde(df)
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import structlog

from bedrock.data.schemas import WASDE_COLS

_log = structlog.get_logger(__name__)

# Kjente USDA URL-er for konsolidert historisk WASDE.
# Listen oppdateres når USDA reorganiserer.
_KNOWN_WASDE_URLS: tuple[str, ...] = (
    "https://www.usda.gov/sites/default/files/documents/wasde-historical-data-archive.csv",
    "https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data.csv",
    "https://www.usda.gov/sites/default/files/documents/wasdeAllHistoricalData.csv",
)
_MANUAL_CSV = Path("data/manual/wasde.csv")
_DEFAULT_TIMEOUT = 60

# USDA's konsoliderte CSV bruker disse kolonne-navnene; mapping til våre.
_USDA_TO_OUR_METRIC: dict[str, str] = {
    "Ending Stocks": "ENDING_STOCKS",
    "Production": "PRODUCTION",
    "Yield": "YIELD",
    "Stocks to Use Ratio": "S2U",
}

# Konvertering for marketing-year format (USDA: "2025/26", vi beholder det).
# Commodity-navn fra USDA matcher allerede våre store-bokstav-koder.


def fetch_wasde_api(
    *,
    urls: tuple[str, ...] = _KNOWN_WASDE_URLS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Forsøk å laste ned konsolidert WASDE-CSV fra USDA.

    Prøver hver URL i ``urls`` til en lykkes. Returnerer DataFrame med
    våre kolonne-navn (mapping fra USDA-format).

    Raises:
        RuntimeError: hvis ingen URL-er fungerer.
    """
    last_error: Exception | None = None
    for url in urls:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            return _normalize_usda_csv(df)
        except Exception as exc:
            last_error = exc
            _log.debug("wasde.url_failed", url=url, error=str(exc))
            continue

    raise RuntimeError(
        f"Ingen av {len(urls)} kjente WASDE-URL-er fungerte. Siste feil: {last_error}"
    )


def _normalize_usda_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Konverter USDA's konsoliderte CSV-format til våre WASDE_COLS.

    USDA-kolonner (typisk):
        ReportDate, MarketingYear, ProjEstFlag, Region, Commodity,
        Attribute, Value, Unit
    """
    # Lower-case kolonne-navn for robust matching mot variasjoner.
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    out = pd.DataFrame()
    out["report_date"] = pd.to_datetime(df.get("reportdate", df.get("report_date"))).dt.strftime(
        "%Y-%m-%d"
    )
    out["marketing_year"] = df.get("marketingyear", df.get("marketing_year"))
    out["region"] = df.get("region", "US").str.upper()
    out["commodity"] = df.get("commodity", "").str.upper()
    out["metric"] = (
        df.get("attribute", "").map(_USDA_TO_OUR_METRIC).fillna(df.get("attribute", "").str.upper())
    )
    out["value"] = pd.to_numeric(df.get("value"), errors="coerce")
    out["unit"] = df.get("unit", "").str.upper().fillna("")

    out = out.dropna(subset=["report_date", "value"])
    return out[list(WASDE_COLS)]


def fetch_wasde_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert WASDE-CSV fra ``data/manual/wasde.csv``."""
    if not csv_path.exists():
        _log.info("wasde.manual_csv_missing", path=str(csv_path))
        return pd.DataFrame(columns=list(WASDE_COLS))

    df = pd.read_csv(csv_path)
    missing = set(WASDE_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"wasde.csv mangler kolonner: {sorted(missing)}")
    return df[list(WASDE_COLS)]


def fetch_wasde(
    *,
    csv_path: Path = _MANUAL_CSV,
    try_api_first: bool = True,
) -> pd.DataFrame:
    """Hent WASDE — prøv USDA-CSV først, fallback til manuell.

    Returnerer tom DataFrame hvis hverken API eller CSV gir resultat.
    """
    if try_api_first:
        try:
            return fetch_wasde_api()
        except Exception as exc:
            _log.warning("wasde.api_failed_fallback_to_csv", error=str(exc))

    return fetch_wasde_manual(csv_path)


__all__ = ["fetch_wasde", "fetch_wasde_api", "fetch_wasde_manual"]
