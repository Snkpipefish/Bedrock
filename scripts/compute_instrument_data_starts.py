"""For hvert instrument, beregn earliest ref_date hvor ALL kritiske drivere
har faktisk data tilgjengelig. Skipper backtest av meningsløse perioder.

Strategi: for hver wired driver i instrumentets YAML, slå opp første dato
hvor underliggende data-source har data i bedrock.db. Returner MAX over
alle drivers — dvs. dagen instrumentet er "fullstendig påkledd".

Drivere uten DB-data-source (analog_*, event_distance, mining_disruption,
seasonal_stage) bidrar ikke — de er kjent å ha kort/ingen historisk
tidsserie eller er kalender-baserte.

Output: `data/_meta/instrument_data_starts.json` — brukes av
`harvest_driver_observations.py` som per-instrument `--from-date`.

Kjør:
    PYTHONPATH=src .venv/bin/python scripts/compute_instrument_data_starts.py
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import yaml

INSTRUMENTS_DIR = Path("config/instruments")
OUTPUT_PATH = Path("data/_meta/instrument_data_starts.json")
DB_PATH = Path("data/bedrock.db")

# Drivere som ikke har minst denne mengden historikk er "supplementary"
# (ny-aktivert, har mindre enn N dager mellom data-start og i dag) og
# blir ikke-kritisk i max()-beregningen. Bruker disse drivere kjøres
# fortsatt fra deres data-start, men de blokkerer ikke instrumentets
# samlede start. Per ADR-007 § 5 skal slike drivere uansett ha lav
# vekt inntil empirisk validert.
SUPPLEMENTARY_DRIVER_MIN_DAYS = 365


def _min_date_query(con: sqlite3.Connection, sql: str, params: tuple) -> str | None:
    try:
        row = con.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])[:10]  # ta YYYY-MM-DD


def _prices_start(con: sqlite3.Connection, instrument: str) -> str | None:
    return _min_date_query(con, "SELECT MIN(ts) FROM prices WHERE instrument = ?", (instrument,))


def _fundamentals_start(con: sqlite3.Connection, series_id: str) -> str | None:
    return _min_date_query(
        con, "SELECT MIN(date) FROM fundamentals WHERE series_id = ?", (series_id,)
    )


def _cot_start(con: sqlite3.Connection, contract: str, report: str) -> str | None:
    table = "cot_disaggregated" if report == "disaggregated" else "cot_legacy"
    return _min_date_query(
        con, f"SELECT MIN(report_date) FROM {table} WHERE contract = ?", (contract,)
    )


def _cot_ice_start(con: sqlite3.Connection, contract: str | None) -> str | None:
    if not contract:
        return None
    return _min_date_query(
        con, "SELECT MIN(report_date) FROM cot_ice WHERE contract = ?", (contract,)
    )


def _cot_euronext_start(con: sqlite3.Connection, contract: str | None) -> str | None:
    if not contract:
        return None
    return _min_date_query(
        con,
        "SELECT MIN(report_date) FROM cot_euronext WHERE contract = ?",
        (contract,),
    )


def _eia_start(con: sqlite3.Connection, series_id: str | None) -> str | None:
    if not series_id:
        return None
    return _min_date_query(
        con, "SELECT MIN(date) FROM eia_inventory WHERE series_id = ?", (series_id,)
    )


def _comex_start(con: sqlite3.Connection, metal: str | None) -> str | None:
    if not metal:
        return None
    return _min_date_query(con, "SELECT MIN(date) FROM comex_inventory WHERE metal = ?", (metal,))


def _shipping_start(con: sqlite3.Connection, index_code: str) -> str | None:
    return _min_date_query(
        con,
        "SELECT MIN(date) FROM shipping_indices WHERE index_code = ?",
        (index_code.upper(),),
    )


def _conab_start(con: sqlite3.Connection, commodity: str | None) -> str | None:
    if not commodity:
        return None
    return _min_date_query(
        con,
        "SELECT MIN(report_date) FROM conab_estimates WHERE commodity = ?",
        (commodity,),
    )


def _unica_start(con: sqlite3.Connection) -> str | None:
    return _min_date_query(con, "SELECT MIN(report_date) FROM unica_reports", ())


def _wasde_start(con: sqlite3.Connection, commodity: str | None) -> str | None:
    if not commodity:
        return None
    return _min_date_query(
        con,
        "SELECT MIN(report_date) FROM wasde WHERE commodity = ?",
        (commodity,),
    )


def _crop_progress_start(con: sqlite3.Connection, commodity: str | None) -> str | None:
    if not commodity:
        return None
    return _min_date_query(
        con,
        "SELECT MIN(week_ending) FROM crop_progress WHERE commodity = ?",
        (commodity,),
    )


def _weather_start(con: sqlite3.Connection, region: str | None) -> str | None:
    if not region:
        return None
    return _min_date_query(
        con,
        "SELECT MIN(month || '-01') FROM weather_monthly WHERE region = ?",
        (region,),
    )


def _enso_start(con: sqlite3.Connection) -> str | None:
    return _min_date_query(con, "SELECT MIN(date) FROM enso", ())


# Mapping driver_name → callable(con, params, instrument_cfg) → start_date | None
def _driver_data_start(
    con: sqlite3.Connection,
    driver_name: str,
    params: dict,
    instrument: str,
    cot_contract: str | None,
    cot_report: str | None,
) -> str | None:
    """Returnerer start-date streng eller None hvis driver er datafri/recent-only."""
    p = params or {}

    if driver_name == "real_yield":
        s_nominal = _fundamentals_start(con, str(p.get("nominal_id", "DGS10")))
        s_inflation = _fundamentals_start(con, str(p.get("inflation_id", "T10YIE")))
        return _max_or_none(s_nominal, s_inflation)
    if driver_name == "dxy_chg5d":
        return _fundamentals_start(con, str(p.get("series_id", "DTWEXBGS")))
    if driver_name == "vix_regime":
        return _fundamentals_start(con, str(p.get("series_id", "VIXCLS")))
    if driver_name == "brl_chg5d":
        return _fundamentals_start(con, "DEXBZUS")
    if driver_name in ("positioning_mm_pct", "cot_z_score"):
        if cot_contract and cot_report:
            return _cot_start(con, cot_contract, cot_report)
        return None
    if driver_name == "cot_ice_mm_pct":
        return _cot_ice_start(con, p.get("contract"))
    if driver_name == "cot_euronext_mm_pct":
        return _cot_euronext_start(con, p.get("contract"))
    if driver_name == "eia_stock_change":
        return _eia_start(con, p.get("series_id"))
    if driver_name == "comex_stress":
        return _comex_start(con, p.get("metal"))
    if driver_name == "shipping_pressure":
        return _shipping_start(con, str(p.get("index", "BDI")))
    if driver_name == "conab_yoy":
        return _conab_start(con, p.get("commodity"))
    if driver_name == "unica_change":
        return _unica_start(con)
    if driver_name == "wasde_s2u_change":
        return _wasde_start(con, p.get("commodity"))
    if driver_name == "crop_progress_stage":
        return _crop_progress_start(con, p.get("usda_commodity"))
    if driver_name == "weather_stress":
        return _weather_start(con, p.get("region"))
    if driver_name == "enso_regime":
        return _enso_start(con)
    if driver_name in ("sma200_align", "momentum_z", "range_position", "vol_regime"):
        return _prices_start(con, instrument)

    # Drivere som er kalender-baserte eller recent-only: ignorer i max()
    # (analog_hit_rate, analog_avg_return, event_distance, mining_disruption,
    # disease_pressure, export_event_active, seasonal_stage, igc_stocks_change)
    return None


def _max_or_none(*dates: str | None) -> str | None:
    valid = [d for d in dates if d is not None]
    if not valid:
        return None
    return max(valid)


DEFAULTS_DIR = Path("config/defaults")


def _resolve_instrument_yaml(yaml_path: Path) -> dict:
    """Last YAML og resolve `inherits:`-kjeder til full config."""
    data = yaml.safe_load(yaml_path.read_text())
    if "inherits" in data:
        # Sjekk både defaults/ og instruments/ for parent
        parent_name = f"{data['inherits']}.yaml"
        parent_path = DEFAULTS_DIR / parent_name
        if not parent_path.exists():
            parent_path = INSTRUMENTS_DIR / parent_name
        parent = _resolve_instrument_yaml(parent_path)
        # Merge: parent first, child override
        merged = {**parent}
        for key, val in data.items():
            if key == "inherits":
                continue
            if key == "families" and isinstance(val, dict) and "families" in merged:
                # Familier overrides per-key
                merged_families = {**merged.get("families", {})}
                for f_name, f_val in val.items():
                    merged_families[f_name] = f_val
                merged["families"] = merged_families
            elif key == "horizons" and isinstance(val, dict) and "horizons" in merged:
                merged_horizons = {**merged.get("horizons", {})}
                for h_name, h_val in val.items():
                    merged_horizons[h_name] = h_val
                merged["horizons"] = merged_horizons
            else:
                merged[key] = val
        return merged
    return data


def compute_for_instrument(con: sqlite3.Connection, yaml_path: Path) -> dict:
    """Beregn per-driver data-start + instrument-level start (max).

    Drivere klassifiseres som:
    - kritisk: data-start eldre enn ``SUPPLEMENTARY_DRIVER_MIN_DAYS`` siden →
      blokkerer instrumentets samlede start
    - supplementary: data-start nyere enn N dager (kort historikk, sannsynligvis
      ny-aktivert i Phase A-C) → ekskluderes fra max-beregning. Kjøres fortsatt
      når deres data finnes, men blokkerer ikke backtest av eldre data
    """
    cfg = _resolve_instrument_yaml(yaml_path)
    instrument = cfg["instrument"]["id"]
    cot_contract = cfg["instrument"].get("cot_contract")
    cot_report = cfg["instrument"].get("cot_report", "disaggregated")

    cutoff_date = date.today() - timedelta(days=SUPPLEMENTARY_DRIVER_MIN_DAYS)
    cutoff_str = cutoff_date.isoformat()

    families = cfg.get("families", {})
    driver_starts: list[dict] = []
    instrument_critical_starts: list[str] = []
    supplementary_drivers: list[str] = []

    for fam_name, fam in families.items():
        drivers = fam.get("drivers", []) or []
        for drv in drivers:
            name = drv.get("name")
            params = drv.get("params") or {}
            weight = drv.get("weight", 1.0)
            if weight == 0 or not name:
                continue
            start = _driver_data_start(con, name, params, instrument, cot_contract, cot_report)
            is_supplementary = start is not None and start > cutoff_str
            driver_starts.append(
                {
                    "driver": name,
                    "family": fam_name,
                    "weight": weight,
                    "data_start": start,
                    "supplementary": is_supplementary,
                }
            )
            if start is not None and weight > 0:
                if is_supplementary:
                    supplementary_drivers.append(f"{name}({start})")
                else:
                    instrument_critical_starts.append(start)

    proposed_start = max(instrument_critical_starts) if instrument_critical_starts else None

    return {
        "instrument": instrument,
        "cot_contract": cot_contract,
        "drivers": driver_starts,
        "proposed_start": proposed_start,
        "supplementary": supplementary_drivers,
    }


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        results: dict[str, dict] = {}
        # Ekskluder family-templates (filer som starter med 'family_')
        for yaml_path in sorted(INSTRUMENTS_DIR.glob("*.yaml")):
            if yaml_path.name.startswith("family_"):
                continue
            try:
                result = compute_for_instrument(con, yaml_path)
            except Exception as e:
                print(f"[{yaml_path.name}] FEIL: {e}")
                continue
            results[result["instrument"]] = result

        # Print rapport
        print(f"{'Instrument':12s} | {'Proposed start':12s} | Drivers (start)")
        print("-" * 100)
        for inst, r in sorted(results.items()):
            ps = r["proposed_start"] or "-"
            drivers_str = ", ".join(
                f"{d['driver']}({d['data_start'] or 'recent'})"
                for d in r["drivers"]
                if d["data_start"] is not None
            )
            if not drivers_str:
                drivers_str = "(ingen DB-baserte drivere)"
            print(f"{inst:12s} | {ps:12s} | {drivers_str[:80]}")

        # Skriv JSON med per-instrument start-mapping
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        mapping = {inst: r["proposed_start"] for inst, r in results.items()}
        OUTPUT_PATH.write_text(
            json.dumps(
                {"computed_at": str(date.today()), "starts": mapping, "details": results},
                indent=2,
            )
        )
        print(f"\nSkrevet: {OUTPUT_PATH}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
