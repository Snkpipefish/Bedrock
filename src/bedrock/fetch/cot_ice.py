# pyright: reportArgumentType=false, reportReturnType=false
# pandas-stubs har dårlig dekning av DataFrame-konstruktor med
# columns=list[str] og av .iloc-rad-tilordninger på blandede dtypes.

"""ICE Futures Europe COT fetcher (sub-fase 12.5+ session 106).

Port av ``~/cot-explorer/fetch_ice_cot.py`` til bedrock SQLite-skjema.
ICE publiserer ukentlig (fredag 18:30 London = 19:30 Oslo) en rapport
for tirsdag-posisjoner i ICE-listede futures: Brent Crude, Low Sulphur
Gasoil, og TTF Natural Gas.

CSV-format: ICE leverer en årlig CSV (én fil per år) på
``https://www.ice.com/publicdocs/futures/COTHist{YEAR}.csv`` i CFTC
disaggregated-format (samme kolonnenavn: ``M_Money_Positions_Long_All``,
``Prod_Merc_Positions_Long_All``, etc.). Cot-explorer-referansen
importerer openpyxl, men ``main()`` der bruker kun CSV-parsing — Excel-
koden er død. Vi gjør ikke openpyxl til en avhengighet.

Schema (returnert DataFrame):
- ``report_date``  TEXT (ISO YYYY-MM-DD)
- ``contract``     TEXT  (canonical: "ice brent crude", "ice gasoil", "ice ttf gas")
- ``mm_long`` / ``mm_short``        Managed Money (≈ MiFID II Investment Funds)
- ``other_long`` / ``other_short``  Other Reportable
- ``comm_long`` / ``comm_short``    Producer/Merchant/Processor/User (≈ Commercial Undertakings)
- ``nonrep_long`` / ``nonrep_short`` Non-Reportable
- ``open_interest``

Manuell CSV-fallback (per ADR-007 § 4): hvis ICE blokkerer requesten
eller returnerer tom data, leses ``data/manual/cot_ice.csv`` (samme
schema). Brukere kan populere CSV-en manuelt hvis prod-host ikke når
ICE.

Cadence per ADR-008: ``30 22 * * 5`` Oslo (Fri 22:30, etter ICE 19:30
Oslo + buffer for opplasting). stale_hours=168.

Smart-skip: runneren sjekker ``latest_observation_ts(TABLE_COT_ICE,
"report_date")`` før HTTP-kall. Hvis vi allerede har siste Tuesday-
rapport (ICE rapporterer alltid for forrige tirsdag-snapshot), hopper
runneren over nedlasting og logger ``cot_ice.up_to_date``.
"""

from __future__ import annotations

import csv as _csv
import io as _io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from bedrock.data.schemas import COT_ICE_COLS
from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

# ICE-canonical contract-navn (lowercase). Match-nøkkel → canonical.
# Dekker både fulle og forkortede navn ICE bruker i ulike rapport-versjoner.
ICE_MARKETS: dict[str, str] = {
    "brent crude": "ice brent crude",
    "low sulphur gasoil": "ice gasoil",
    "ttf natural gas": "ice ttf gas",
    # Varianter
    "brent": "ice brent crude",
    "gasoil": "ice gasoil",
    "ttf": "ice ttf gas",
    "natural gas": "ice ttf gas",
}


def _ice_urls(year: int) -> list[str]:
    """ICE-URL-er for current og foregående år. Sekvensiell prøving."""
    return [
        f"https://www.ice.com/publicdocs/futures/COTHist{year}.csv",
        f"https://www.ice.com/publicdocs/futures/COTHist{year - 1}.csv",
    ]


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Referer": "https://www.ice.com/",
}

_MANUAL_CSV = Path("data/manual/cot_ice.csv")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _safe_int(s: Any) -> int:
    """Konverter '12,345' eller '12345.0' til int. Tom → 0."""
    if s is None:
        return 0
    txt = str(s).replace(",", "").strip()
    if not txt:
        return 0
    try:
        return int(float(txt))
    except (ValueError, TypeError):
        return 0


def _normalize_market(name: str) -> str | None:
    """Match ICE-rapport-navn mot canonical key. Ignorer 'and options'-rader."""
    n = (name or "").lower()
    if "and options" in n:
        return None
    for search_key, canonical in ICE_MARKETS.items():
        if search_key in n:
            return canonical
    return None


def _parse_date(raw: str) -> str | None:
    """ICE rapporterer ``MM/DD/YYYY`` eller ``YYMMDD``. Returnerer ISO."""
    if not raw:
        return None
    s = raw.strip()
    for fmt in ("%m/%d/%Y", "%y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_ice_csv(text: str) -> pd.DataFrame:
    """Parse ICE COT CSV-tekst til DataFrame med ``COT_ICE_COLS``-schema.

    Beholder ALLE rader per (report_date, contract) — ikke bare nyeste —
    slik at backfill med flerårig CSV gir full historikk.

    Returnerer tom DataFrame hvis ingen rader matcher ICE-markedene.
    """
    # Strip UTF-8 BOM / Windows-1252-BOM
    text = text.lstrip("\ufeff").lstrip("\ufffe").lstrip("ï»¿")

    reader = _csv.DictReader(_io.StringIO(text))
    rows: list[dict[str, Any]] = []

    for row in reader:
        name = (row.get("Market_and_Exchange_Names") or "").strip()
        contract = _normalize_market(name)
        if contract is None:
            continue

        raw_date = (
            row.get("As_of_Date_Form_MM/DD/YYYY") or row.get("As_of_Date_In_Form_YYMMDD") or ""
        )
        report_date = _parse_date(raw_date)
        if report_date is None:
            continue

        mm_long = _safe_int(row.get("M_Money_Positions_Long_All"))
        mm_short = _safe_int(row.get("M_Money_Positions_Short_All"))
        other_long = _safe_int(row.get("Other_Rept_Positions_Long_All"))
        other_short = _safe_int(row.get("Other_Rept_Positions_Short_All"))
        comm_long = _safe_int(row.get("Prod_Merc_Positions_Long_All"))
        comm_short = _safe_int(row.get("Prod_Merc_Positions_Short_All"))
        nonrep_long = _safe_int(row.get("NonRept_Positions_Long_All"))
        nonrep_short = _safe_int(row.get("NonRept_Positions_Short_All"))
        oi = _safe_int(row.get("Open_Interest_All"))

        # Skipp helt-tomme rader (alle null) — ICE har noen header/separator-
        # rader som passerer market-filteret men har ingen tall.
        if mm_long == 0 and mm_short == 0 and oi == 0:
            continue

        rows.append(
            {
                "report_date": report_date,
                "contract": contract,
                "mm_long": mm_long,
                "mm_short": mm_short,
                "other_long": other_long,
                "other_short": other_short,
                "comm_long": comm_long,
                "comm_short": comm_short,
                "nonrep_long": nonrep_long,
                "nonrep_short": nonrep_short,
                "open_interest": oi,
            }
        )

    df = pd.DataFrame(rows, columns=list(COT_ICE_COLS))
    if not df.empty:
        # Dedupe: hvis samme (report_date, contract) finnes flere ganger
        # (futures-only-rader oppstår noen ganger duplisert), ta siste.
        df = df.drop_duplicates(subset=["report_date", "contract"], keep="last")
        df = df.sort_values(["contract", "report_date"]).reset_index(drop=True)
    _log.info(
        "cot_ice.parsed rows=%d markets=%d",
        len(df),
        df["contract"].nunique() if not df.empty else 0,
    )
    return df


# ---------------------------------------------------------------------------
# Remote fetch (sekvensiell HTTP — ingen parallell mot gratis-kilden)
# ---------------------------------------------------------------------------


def fetch_cot_ice_remote(
    *,
    timeout: float = 30.0,
    raw_text: str | None = None,  # injection-point for testing
    year: int | None = None,
) -> pd.DataFrame:
    """Last ned ICE COT CSV og parser. Reiser ``ValueError`` ved feil.

    Prøver current-year-URL først, så foregående år (i tilfelle januar
    før ny fil er publisert). Sekvensielle requests, ikke parallelle —
    gratis-API-etiquette.

    Args:
        timeout: HTTP-timeout per request.
        raw_text: pre-fetched CSV-tekst for testing. Hopper over HTTP.
        year: override current year (testing).

    Returns:
        DataFrame med ``COT_ICE_COLS``-schema. Aldri tom hvis vellykket.

    Raises:
        ValueError: hvis ingen URL svarer med valid CSV, eller parsing
            gir 0 rader.
    """
    if raw_text is not None:
        df = parse_ice_csv(raw_text)
        if df.empty:
            raise ValueError("cot_ice: parsed 0 rows from injected text")
        return df

    effective_year = year or datetime.now(timezone.utc).year
    last_error: str | None = None

    for url in _ice_urls(effective_year):
        try:
            _log.info("cot_ice.fetching url=%s", url)
            response = http_get_with_retry(url, timeout=timeout)
        except Exception as exc:
            last_error = f"HTTP error from {url}: {exc}"
            _log.warning("cot_ice.http_failed url=%s error=%s", url, exc)
            continue

        if response.status_code != 200:
            last_error = f"HTTP {response.status_code} from {url}"
            _log.warning("cot_ice.bad_status url=%s status=%d", url, response.status_code)
            continue

        body = response.content
        if len(body) < 1000:
            last_error = f"response too small from {url} ({len(body)}B)"
            continue
        if body[:200].lstrip().startswith(b"<"):
            # HTML-feilside (ofte ICE block-page eller 404-render)
            last_error = f"non-CSV response from {url}"
            continue

        text = body.decode("utf-8", errors="replace")
        df = parse_ice_csv(text)
        if df.empty:
            last_error = f"parsed 0 rows from {url}"
            continue

        return df

    raise ValueError(f"cot_ice: all ICE URLs failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Manual CSV fallback (per ADR-007 § 4)
# ---------------------------------------------------------------------------


def fetch_cot_ice_manual(csv_path: Path = _MANUAL_CSV) -> pd.DataFrame:
    """Les manuelt populert CSV fra ``data/manual/cot_ice.csv``.

    CSV må ha kolonner som matcher ``COT_ICE_COLS`` direkte (samme schema
    som ``store.append_cot_ice`` forventer). Returnerer tom DataFrame
    hvis fila ikke finnes.

    Raises:
        ValueError: hvis fila finnes men mangler påkrevde kolonner.
    """
    if not csv_path.exists():
        _log.info("cot_ice.manual_csv_missing path=%s", csv_path)
        return pd.DataFrame(columns=list(COT_ICE_COLS))

    df = pd.read_csv(csv_path)
    missing = [c for c in COT_ICE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"cot_ice manual CSV mangler kolonner: {sorted(missing)}")

    # Normaliser report_date til ISO-streng (DataStore re-normaliserer
    # uansett, men dette holder dataframen forutsigbar for tester).
    df["report_date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
    return df[list(COT_ICE_COLS)].copy()


# ---------------------------------------------------------------------------
# Public combined: prøv remote først, fall tilbake til manuell
# ---------------------------------------------------------------------------


def fetch_cot_ice(
    *,
    timeout: float = 30.0,
    csv_path: Path = _MANUAL_CSV,
) -> pd.DataFrame:
    """Hent ICE COT — prøv remote først, så manuell CSV-fallback.

    Returnerer alltid en DataFrame; tom hvis både remote feiler og
    manuell CSV ikke finnes. Ingen exceptions propageres oppover —
    runneren bestemmer policy via FetchRunResult.
    """
    try:
        return fetch_cot_ice_remote(timeout=timeout)
    except Exception as exc:
        _log.warning("cot_ice.remote_failed_fallback_to_csv error=%s", exc)

    try:
        return fetch_cot_ice_manual(csv_path)
    except Exception as exc:
        _log.warning("cot_ice.manual_csv_failed error=%s", exc)
        return pd.DataFrame(columns=list(COT_ICE_COLS))


__all__ = [
    "ICE_MARKETS",
    "fetch_cot_ice",
    "fetch_cot_ice_manual",
    "fetch_cot_ice_remote",
    "parse_ice_csv",
]
