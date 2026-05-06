"""UN Comtrade fetcher — månedlig handelsdata via gratis preview-endpoint.

Adresserer USDA PSD årlig-lag-problem (sub-fase 12.11+ punkt 3 / OOS 2023):
USDA FAS PSD oppdaterer sukker-eksport årlig (~oktober), så India-eksport-
forbud Q3 2023 ble ikke fanget før oktober 2024-rapporten. UN Comtrade gir
månedlig data (~2-4 mnd lag) — fanger policy-events kvartal-tidlig.

API: https://comtradeapi.un.org/public/v1/preview/C/M/HS
- C = Commodity, M = Monthly, HS = Harmonized System klassifisering
- Public preview-endpoint krever INGEN nøkkel (~500 records/call gratis tier)
- Rate limit: ingen offisiell, men gratis-API-etiquette (0.5s pacing)

Bruk for sukker:
    fetch_india_sugar_exports(from_year=2010) → fundamentals-rader
    series_id="COMTRADE_INDIA_SUGAR_EXPORTS_KG_MONTHLY"
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import pandas as pd

from bedrock.fetch.base import http_get_with_retry

_log = logging.getLogger(__name__)

API_BASE = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"

# Reporter codes (UN M49)
REPORTER_INDIA = 699
REPORTER_BRAZIL = 76
REPORTER_THAILAND = 764

# Sugar HS-codes (alle 1701 underkategorier — raw + refined cane sugar)
SUGAR_HS_CODES = ["170111", "170112", "170113", "170114", "170191", "170199"]

# Flow codes
FLOW_EXPORT = "X"
FLOW_IMPORT = "M"

# Partner code 0 = World aggregate (sum av alle partnere)
PARTNER_WORLD = 0


class ComtradeFetchError(RuntimeError):
    """Comtrade API-fetch feilet."""


def fetch_comtrade_period(
    reporter_code: int,
    period: str,
    cmd_codes: list[str],
    flow_code: str = FLOW_EXPORT,
    partner_code: int = PARTNER_WORLD,
    *,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Hent Comtrade-data for én rapporteringsperiode.

    Args:
        reporter_code: M49-kode for rapporterende land (699=India)
        period: "YYYYMM" for månedlig, "YYYY" for årlig
        cmd_codes: HS-koder å aggregere over (e.g. SUGAR_HS_CODES)
        flow_code: "X"=export, "M"=import
        partner_code: 0=verden (default), eller spesifikk partner

    Returns:
        Liste av rå records fra API. Hver record har felt: refMonth, refYear,
        cmdCode, fobvalue, netWgt, partnerCode, etc.

    Raises:
        ComtradeFetchError ved network/parse-feil.
    """
    cmd_str = ",".join(cmd_codes)
    params: dict[str, str | int] = {
        "reporterCode": reporter_code,
        "period": period,
        "cmdCode": cmd_str,
        "flowCode": flow_code,
        "partnerCode": partner_code,
    }

    try:
        response = http_get_with_retry(API_BASE, params=params, timeout=timeout)
    except Exception as exc:
        raise ComtradeFetchError(
            f"comtrade {reporter_code}/{period}: network failure: {exc}"
        ) from exc

    if response.status_code != 200:
        raise ComtradeFetchError(f"comtrade {reporter_code}/{period}: HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ComtradeFetchError(f"comtrade {reporter_code}/{period}: invalid JSON: {exc}") from exc

    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ComtradeFetchError(f"comtrade {reporter_code}/{period}: 'data' is not a list")

    return data


def fetch_india_sugar_exports(
    from_year: int = 2010,
    to_year: int | None = None,
    pacing_sec: float = 0.5,
) -> pd.DataFrame:
    """Hent India sugar månedlig eksport-historikk som fundamentals-DataFrame.

    Returnerer rader for to series_id (begge månedlige, ~10 dager etter månedsslutt
    når UN Comtrade publiserer ~2 mnd lag):
    - COMTRADE_INDIA_SUGAR_EXPORTS_USD_MONTHLY (FOB-verdi i USD)
    - COMTRADE_INDIA_SUGAR_EXPORTS_KG_MONTHLY (netto vekt i kg)

    Aggregert over alle 1701-HS-koder (raw + refined cane sugar).

    Args:
        from_year: tidligste år (default 2010 — Comtrade har data fra 2010+)
        to_year: siste år (default = inneværende år)
        pacing_sec: pause mellom kall (gratis-API-etiquette)

    Returns:
        DataFrame med (series_id, date, value)-rader. Date er måned-startdato
        (YYYY-MM-01). Tom DataFrame hvis ingen data.
    """
    if to_year is None:
        to_year = date.today().year

    rows: list[dict[str, Any]] = []
    first = True

    for year in range(from_year, to_year + 1):
        # Bygg comma-separert månedsliste for hele året
        months = ",".join(f"{year}{m:02d}" for m in range(1, 13))
        if not first:
            time.sleep(pacing_sec)
        first = False

        try:
            records = fetch_comtrade_period(
                REPORTER_INDIA,
                months,
                SUGAR_HS_CODES,
                FLOW_EXPORT,
                PARTNER_WORLD,
            )
        except ComtradeFetchError as exc:
            _log.warning("comtrade.year_failed year=%s error=%s", year, exc)
            continue

        # Aggreger per måned (sum over HS-koder)
        monthly_agg: dict[str, dict[str, float]] = {}
        for rec in records:
            period = str(rec.get("period", ""))
            if not period or len(period) != 6:
                continue
            partner = rec.get("partnerCode")
            # Bare verdens-aggregat (partnerCode=0); andre partner-rader er
            # delsum per land
            if partner != PARTNER_WORLD:
                continue

            agg = monthly_agg.setdefault(period, {"usd": 0.0, "kg": 0.0})
            fob = rec.get("fobvalue") or 0.0
            kg = rec.get("netWgt") or 0.0
            try:
                agg["usd"] += float(fob)
                agg["kg"] += float(kg)
            except (TypeError, ValueError):
                continue

        for period, vals in monthly_agg.items():
            yr = int(period[:4])
            mo = int(period[4:6])
            date_str = f"{yr:04d}-{mo:02d}-01"
            rows.append(
                {
                    "series_id": "COMTRADE_INDIA_SUGAR_EXPORTS_USD_MONTHLY",
                    "date": date_str,
                    "value": vals["usd"],
                }
            )
            rows.append(
                {
                    "series_id": "COMTRADE_INDIA_SUGAR_EXPORTS_KG_MONTHLY",
                    "date": date_str,
                    "value": vals["kg"],
                }
            )

        _log.info("comtrade.year_ok year=%s months=%d", year, len(monthly_agg))

    if not rows:
        return pd.DataFrame(columns=["series_id", "date", "value"])

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["series_id", "date"], keep="last")
    return df.sort_values(["series_id", "date"]).reset_index(drop=True)
