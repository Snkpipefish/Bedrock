# pyright: reportAttributeAccessIssue=false, reportReturnType=false, reportArgumentType=false, reportCallIssue=false, reportOptionalMemberAccess=false
# pandas-stubs har dårlig dekning av .str-aksessor og .map() på Series med Optional/Unknown.

"""USDA WASDE fetcher (PLAN § 7.3 Fase-4).

WASDE-rapporter publiseres månedlig (~10. hver måned) og inneholder
ending stocks, yield-prognoser, og stocks-to-use ratio for major
commodities (corn, wheat, soybeans, rice, cotton).

**Auto-fetcher** (session 85): scraper ESMIS-index-siden
(https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates)
for å finne XML-URL-er, laster ned + parser hver måned.

XML-format: hierarkisk med sub-rapporter per commodity/region. Vi
ekstraherer Production/Output, Total Use, Ending Stocks for nåværende
+ neste marketing year.

Manuell CSV-fallback: ``data/manual/wasde.csv``.

Bruk:
    from bedrock.fetch.wasde import fetch_wasde, fetch_wasde_xml_index
    # Backfill historisk:
    df = fetch_wasde_xml_index(years=[2024, 2025, 2026])
    store.append_wasde(df)
    # Eller bruk kombinert wrapper med fallback:
    df = fetch_wasde()
"""

from __future__ import annotations

import re
from datetime import datetime
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import structlog

from bedrock.data.schemas import WASDE_COLS

_log = structlog.get_logger(__name__)

# ESMIS index-side med lenker til alle WASDE-rapporter (PDF/TXT/XLS/XML).
_ESMIS_INDEX = (
    "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"
)
_ESMIS_BASE = "https://esmis.nal.usda.gov"

# Kjente USDA URL-er for konsolidert historisk WASDE (legacy fallback).
_KNOWN_WASDE_URLS: tuple[str, ...] = (
    "https://www.usda.gov/sites/default/files/documents/wasde-historical-data-archive.csv",
    "https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data.csv",
    "https://www.usda.gov/sites/default/files/documents/wasdeAllHistoricalData.csv",
)
_MANUAL_CSV = Path("data/manual/wasde.csv")
_DEFAULT_TIMEOUT = 60

# WASDE sub-rapport-titler vi parser (bruker startswith for robusthet
# mot whitespace-variasjoner og " (Cont'd.)"-suffix).
_RELEVANT_SECTIONS: dict[str, tuple[str, str]] = {
    # title-prefix: (commodity, region)
    "U.S. Wheat Supply": ("WHEAT", "US"),
    "U.S. Feed Grain and Corn Supply": ("CORN", "US"),
    "U.S. Soybeans and Products Supply": ("SOYBEANS", "US"),
    "U.S. Cotton Supply": ("COTTON", "US"),
    "U.S. Sugar Supply": ("SUGAR", "US"),
    "U.S. Rice Supply": ("RICE", "US"),
    "World Wheat Supply": ("WHEAT", "WORLD"),
    "World Corn Supply": ("CORN", "WORLD"),
    "World Cotton Supply": ("COTTON", "WORLD"),
    "World Soybean Supply": ("SOYBEANS", "WORLD"),
    "World Rice Supply": ("RICE", "WORLD"),
}

# WASDE attribute-navn vi ekstraherer (mapping fra XML attribute1 → metric).
_RELEVANT_ATTRIBUTES: dict[str, str] = {
    "Output": "PRODUCTION",
    "Production": "PRODUCTION",
    "Total Supply": "TOTAL_SUPPLY",
    "Total Use": "TOTAL_USE",
    "Total Domestic Use": "DOMESTIC_USE",
    "Ending Stocks": "ENDING_STOCKS",
    "Yield": "YIELD",
}


def _normalize_attr(attr: str) -> str:
    """Strip whitespace + line-breaks + footnote-markers fra attribute-strenger."""
    s = attr.replace("\r\n", " ").replace("\n", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*\d+/", "", s).strip()  # fjerner footnote-markers som "1/"
    return s


def _parse_market_year(raw: str) -> str:
    """Konverter XML market_year1 til standard format.

    Eksempel input: '2024/25 (Est.) ', '2025/26 (Proj.) ', '2023/24'
    Output: '2024/25', '2025/26', '2023/24'
    """
    s = raw.strip()
    m = re.match(r"(\d{4}/\d{2})", s)
    return m.group(1) if m else s


def _parse_report_date(month_year: str) -> str:
    """'April 2026' → '2026-04-10' (USDA publiserer ~10. hver måned)."""
    try:
        dt = datetime.strptime(month_year.strip(), "%B %Y")
        return dt.strftime("%Y-%m-10")
    except ValueError:
        return ""


def _extract_year_attrs(year_group_el) -> dict[str, float]:
    """Ekstraher attribute-verdier fra én m1_year_group (sr08-aggregat-stil).

    For sr08-strukturen: m1_year_group → m1_attribute_group → s3 → Cell.
    """
    attr_values: dict[str, float] = {}
    for s3 in year_group_el.iter("s3"):
        attr = _normalize_attr(s3.get("attribute1", ""))
        cell = s3.find(".//Cell")
        if cell is None:
            continue
        val_str = cell.get("cell_value1", "")
        if not val_str or val_str == "filler":
            continue
        metric = _RELEVANT_ATTRIBUTES.get(attr)
        if metric is None:
            continue
        try:
            attr_values[metric] = float(val_str.replace(",", ""))
        except ValueError:
            pass
    return attr_values


# US-spesifikke attribute-navn → vår metric. Mapper etter normalisering
# (whitespace + footnote-strip).
_US_METRIC_MAP: dict[str, str] = {
    "Production": "PRODUCTION",
    "Output": "PRODUCTION",
    "Yield per Harvested Acre": "YIELD",
    "Yield": "YIELD",
    "Total Supply": "TOTAL_SUPPLY",
    "Supply, Total": "TOTAL_SUPPLY",
    "Supply Total": "TOTAL_SUPPLY",
    "Total Use": "TOTAL_USE",
    "Use, Total": "TOTAL_USE",
    "Total Domestic Use": "DOMESTIC_USE",
    "Domestic Total": "DOMESTIC_USE",
    "Domestic, Total": "DOMESTIC_USE",
    "Ending Stocks": "ENDING_STOCKS",
    "Beginning Stocks": "BEGINNING_STOCKS",
    "Exports": "EXPORTS",
    "Imports": "IMPORTS",
}


def _parse_us_specific_section(report_el, commodity: str) -> dict[str, dict[str, float]]:
    """Parse US-spesifikke seksjoner (sr11-sr17). Commodity er implisitt
    fra sub_report_title.

    WASDE bruker forskjellige tag-navn (attribute1, attribute4, attribute5,
    attribute6) på tvers av seksjoner. Vi finner alle element-tagger som
    starter med "attribute" hvor den bærer en attribute med samme navn
    (f.eks. ``<attribute1 attribute1="Yield">``).

    Hver slik attribute-TAG har deretter year_group → month_group → Cell.
    Vi tar siste month_group som har en numerisk Cell (nyeste estimat).

    Returns:
        Dict mapping marketing_year → dict[metric, value].
    """
    by_year: dict[str, dict[str, float]] = {}

    # WASDE bruker parallelle suffixer: attribute1/market_year1/cell_value1,
    # attribute4/market_year4/cell_value4 etc. Vi finner suffix fra tag-
    # navn ("attributeN") og bruker samme N for alle relaterte attributter.
    for el in report_el.iter():
        tag = el.tag
        if not tag.startswith("attribute"):
            continue
        suffix = tag.removeprefix("attribute")
        if not suffix.isdigit():
            continue
        attr_name_raw = el.get(tag, "")
        if not attr_name_raw:
            continue

        attr_name = _normalize_attr(attr_name_raw)
        metric = _US_METRIC_MAP.get(attr_name)
        if metric is None:
            # Også sjekk lowercase-varianter (WASDE har blanda case)
            metric = _US_METRIC_MAP.get(attr_name.title())
            if metric is None:
                continue

        market_year_attr = f"market_year{suffix}"
        cell_value_attr = f"cell_value{suffix}"

        for yg in el.iter():
            my_raw = yg.attrib.get(market_year_attr, "")
            if not my_raw:
                continue
            my = _parse_market_year(my_raw)
            if not my:
                continue

            value: float | None = None
            for mg in yg.iter():
                cell = mg.find("Cell")
                if cell is None:
                    continue
                val_str = cell.get(cell_value_attr, "")
                if not val_str:
                    continue
                try:
                    value = float(val_str.replace(",", ""))
                except ValueError:
                    continue
            if value is None:
                continue

            # For commodities med flere matriser (Soybeans har Soybeans/
            # Soymeal/Soyoil), behold første verdi per (year, metric).
            # Soybeans-only verdier kommer fra matrix1 typisk.
            if my in by_year and metric in by_year[my]:
                continue
            by_year.setdefault(my, {})[metric] = value

    return by_year


def _emit_rows(
    rows: list[dict],
    report_date: str,
    marketing_year: str,
    region: str,
    commodity: str,
    attrs: dict[str, float],
    unit: str,
) -> None:
    """Konverter (commodity, region, year, attrs) til WASDE-rader."""
    for metric, value in attrs.items():
        rows.append(
            {
                "report_date": report_date,
                "marketing_year": marketing_year,
                "region": region,
                "commodity": commodity,
                "metric": metric,
                "value": value,
                "unit": unit,
            }
        )
    # Beregn S2U
    stocks = attrs.get("ENDING_STOCKS")
    use = attrs.get("TOTAL_USE") or attrs.get("DOMESTIC_USE")
    if stocks and use and use > 0:
        rows.append(
            {
                "report_date": report_date,
                "marketing_year": marketing_year,
                "region": region,
                "commodity": commodity,
                "metric": "S2U",
                "value": stocks / use * 100,
                "unit": "PCT",
            }
        )


def parse_wasde_xml(xml_bytes: bytes) -> pd.DataFrame:
    """Parser én WASDE XML-rapport til DataFrame med våre WASDE_COLS.

    Håndterer to forskjellige WASDE XML-schemas:

    1. **Aggregat-rapporter** (sr08, sr10): matrix1 → m1_commodity_group →
       m1_year_group. Brukes for World/US Total Grains, Oilseeds.

    2. **US-spesifikke rapporter** (sr11-sr17): m1_year_group direkte (uten
       commodity_group). Commodity er implisitt fra sub_report_title.

    World-spesifikke rapporter (sr18+) har en tredje schema med m1_region_group;
    ikke parset her ettersom sr08-aggregatet dekker World-totaler.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        _log.warning("wasde.xml_parse_failed", error=str(exc))
        return pd.DataFrame(columns=list(WASDE_COLS))

    rows: list[dict] = []

    for report in root.iter("Report"):
        title = report.get("sub_report_title", "")
        norm_title = _normalize_attr(title)
        if "(Cont" in norm_title:
            continue

        match = None
        for prefix, (commodity, region) in _RELEVANT_SECTIONS.items():
            if norm_title.startswith(prefix):
                match = (commodity, region)
                break
        if match is None:
            continue

        commodity, region = match
        report_date = _parse_report_date(report.get("Report_Month", ""))
        if not report_date:
            continue

        # Schema 1: aggregat med m1_commodity_group (sr08, sr10)
        commodity_groups = list(report.iter("m1_commodity_group"))
        if commodity_groups:
            for cg in commodity_groups:
                cg_name = cg.get("commodity1", "").strip().lower()
                # Filter — sjekk om denne commodity_group matcher target
                if commodity == "WHEAT" and not cg_name.startswith("wheat"):
                    continue
                if commodity == "CORN" and "corn" not in cg_name:
                    continue
                if commodity == "SOYBEANS" and "soybean" not in cg_name:
                    continue
                if commodity == "COTTON" and "cotton" not in cg_name:
                    continue
                if commodity == "RICE" and "rice" not in cg_name:
                    continue

                for yg in cg.iter("m1_year_group"):
                    my = _parse_market_year(yg.get("market_year1", ""))
                    if not my:
                        continue
                    attrs = _extract_year_attrs(yg)
                    if attrs:
                        _emit_rows(rows, report_date, my, region, commodity, attrs, "MIL_TONS")
        else:
            # Schema 2: US-spesifikk uten commodity_group (sr11-sr17).
            # Bruker dedikert parser som håndterer attribute1-TAG-strukturen.
            us_data = _parse_us_specific_section(report, commodity)
            unit = "MIL_BU" if commodity in ("CORN", "WHEAT", "SOYBEANS") else "MIL_OTHER"
            for my, attrs in us_data.items():
                _emit_rows(rows, report_date, my, region, commodity, attrs, unit)

    df = pd.DataFrame(rows, columns=list(WASDE_COLS))
    if not df.empty:
        df = df.drop_duplicates(
            subset=["report_date", "marketing_year", "region", "commodity", "metric"]
        )
    return df


def fetch_wasde_xml_index(
    years: list[int] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Scraper ESMIS-index for XML-lenker, laster ned + parser hver rapport.

    Args:
        years: filter på publikasjons-år (default: alle på siden, typisk
            siste ~20 rapporter).
        timeout: HTTP-timeout per kall.

    Returns:
        DataFrame med alle WASDE-rader fra alle XML-rapporter parsert.
    """
    try:
        resp = requests.get(_ESMIS_INDEX, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        _log.warning("wasde.index_fetch_failed", error=str(exc))
        return pd.DataFrame(columns=list(WASDE_COLS))

    # Match: /sites/default/release-files/<release_id>/wasdeMMYY.xml
    xml_paths = re.findall(r'href="(/sites/default/release-files/\d+/wasde\d{4}\.xml)"', resp.text)
    if not xml_paths:
        _log.warning("wasde.no_xml_links_found")
        return pd.DataFrame(columns=list(WASDE_COLS))

    all_dfs: list[pd.DataFrame] = []
    for path in xml_paths:
        # File-navn-pattern: wasdeMMYY.xml — MM=måned, YY=2-siffer-år.
        # Filter på years hvis spesifisert.
        m = re.search(r"wasde(\d{2})(\d{2})\.xml$", path)
        if not m:
            continue
        yy = int(m.group(2))
        full_year = 2000 + yy if yy < 80 else 1900 + yy
        if years is not None and full_year not in years:
            continue

        url = _ESMIS_BASE + path
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            df = parse_wasde_xml(r.content)
            if not df.empty:
                all_dfs.append(df)
                _log.info("wasde.parsed", url=path, rows=len(df))
        except Exception as exc:
            _log.warning("wasde.parse_failed", url=path, error=str(exc))
            continue

    if not all_dfs:
        return pd.DataFrame(columns=list(WASDE_COLS))
    return pd.concat(all_dfs, ignore_index=True).drop_duplicates(
        subset=["report_date", "marketing_year", "region", "commodity", "metric"]
    )


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
    try_xml_first: bool = True,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Hent WASDE — prøv ESMIS XML først, deretter konsolidert CSV, fallback til manuell.

    Args:
        csv_path: manuell CSV-sti.
        try_xml_first: prøv ESMIS-XML-scrape før annet.
        years: filter for XML-fetcher (default = alle på ESMIS-siden).

    Returns:
        DataFrame med WASDE-rader. Tom hvis alle metoder feiler.
    """
    if try_xml_first:
        try:
            df = fetch_wasde_xml_index(years=years)
            if not df.empty:
                return df
        except Exception as exc:
            _log.warning("wasde.xml_failed_fallback", error=str(exc))

    try:
        return fetch_wasde_api()
    except Exception as exc:
        _log.warning("wasde.api_failed_fallback_to_csv", error=str(exc))

    return fetch_wasde_manual(csv_path)


__all__ = [
    "fetch_wasde",
    "fetch_wasde_api",
    "fetch_wasde_manual",
    "fetch_wasde_xml_index",
    "parse_wasde_xml",
]
