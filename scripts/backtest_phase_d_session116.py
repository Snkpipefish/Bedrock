"""Session 116 — Phase D backtest-validering.

Kjører `run_orchestrator_replay` for alle 22 instrumenter × {30d, 90d} ×
{buy, sell} på 12-måneders vindu med step_days=5 (ukentlig sampling).
Måler scoring-distribusjon og publish-rate med Phase A-C-fetchere
(calendar_ff/cot_ice/eia/comex/seismic/cot_euronext/conab/unica/
shipping_pressure-rebrand) wired inn.

Tre kjørselsmodi:

1. ``baseline``: re-kjøring av session 99 outcome-replay (rask
   sanity-check at analog_outcomes-tabellen er uendret).
2. ``orchestrator`` (default): full orchestrator-replay-sweep på 22 inst.
3. ``spike``: per-driver-bidrag-spike via temp YAML-kopier der den
   navngitte driverens vekt settes til 0.0 i alle berørte instrumenter.

Output:

- ``data/_meta/backtest_phase_d_orchestrator.json`` — råresultater
- ``data/_meta/backtest_phase_d_baseline.json``     — session 99 reprise
- ``data/_meta/backtest_phase_d_spike_<driver>.json`` — én per spike
- ``docs/backtest_phase_d_2026-04.md`` — sammenstilt rapport (genereres av
  separat ``--render``-flagg når alle JSON-er finnes)

Kjør:

    PYTHONPATH=src .venv/bin/python scripts/backtest_phase_d_session116.py \\
        --mode orchestrator --output data/_meta/backtest_phase_d_orchestrator.json

Per-driver-spike-eksempel:

    PYTHONPATH=src .venv/bin/python scripts/backtest_phase_d_session116.py \\
        --mode spike --driver event_distance \\
        --output data/_meta/backtest_phase_d_spike_event_distance.json
"""
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import tempfile
import time
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

import yaml

from bedrock.backtest.config import BacktestConfig
from bedrock.backtest.runner import (
    run_orchestrator_replay,
    run_outcome_replay,
)
from bedrock.data.store import DataStore
from bedrock.signal_server.config import load_from_env

# 22 instrumenter (matcher config/instruments/*.yaml; navn er bedrock-id)
ALL_INSTRUMENTS: list[str] = [
    # FX
    "EURUSD",
    "USDJPY",
    "GBPUSD",
    "AUDUSD",
    # Metals
    "Gold",
    "Silver",
    "Copper",
    "Platinum",
    # Energy
    "CrudeOil",
    "Brent",
    "NaturalGas",
    # Indices
    "SP500",
    "Nasdaq",
    # Grains
    "Corn",
    "Wheat",
    "Soybean",
    # Softs
    "Cotton",
    "Sugar",
    "Coffee",
    "Cocoa",
    # Crypto
    "BTC",
    "ETH",
]

# Subset med analog_outcomes-data (session 99-whitelist). De øvrige 5
# (BTC/ETH/NaturalGas/Copper/Platinum) kan kjøres orchestrator-replay,
# men har ingen forward_return å måle hit mot.
WHITELIST_17: list[str] = [
    "EURUSD",
    "USDJPY",
    "GBPUSD",
    "AUDUSD",
    "Gold",
    "Silver",
    "CrudeOil",
    "Brent",
    "SP500",
    "Nasdaq",
    "Corn",
    "Wheat",
    "Soybean",
    "Coffee",
    "Cotton",
    "Sugar",
    "Cocoa",
]

# Hit-rate-terskel per horizon. Matcher session 99 + analog-driver.
THRESHOLDS_PCT: dict[int, float] = {
    30: 3.0,
    90: 5.0,
}

HORIZONS: list[int] = [30, 90]
DIRECTIONS: list[str] = ["buy", "sell"]

# 8 nye drivere fra Phase A-C (sessions 105-115). shipping_pressure er
# rebrand av bdi_chg30d (session 113) — separer som egen spike fordi
# vekt er flyttet/utvidet, ikke ny.
PHASE_AC_DRIVERS: list[str] = [
    "event_distance",  # session 105
    "cot_ice_mm_pct",  # session 106
    "eia_stock_change",  # session 107
    "comex_stress",  # session 108
    "mining_disruption",  # session 109
    "cot_euronext_mm_pct",  # session 110
    "conab_yoy",  # session 111
    "unica_change",  # session 112
    "shipping_pressure",  # session 113 (rebrand av bdi_chg30d)
]


# ---------------------------------------------------------------------------
# Spike-mode helpers
# ---------------------------------------------------------------------------


def _zero_driver_in_yaml(yaml_path: Path, driver_name: str) -> int:
    """Sett vekt = 0.0 for alle forekomster av driver_name i en YAML-fil.

    Returnerer antall vekt-justeringer gjort. Bevarer YAML-strukturen
    så engine fortsatt kan laste filen (driveren vil score 0 og ikke
    bidra til family-score).
    """
    raw = yaml.safe_load(yaml_path.read_text())
    n_zeroed = 0
    families = raw.get("families") or {}
    for _fam_name, fam in families.items():
        drivers = fam.get("drivers") or []
        for drv in drivers:
            if drv.get("name") == driver_name:
                drv["weight"] = 0.0
                n_zeroed += 1
    if n_zeroed > 0:
        yaml_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    return n_zeroed


def _build_spike_instruments_dir(
    src_dir: Path, driver_name: str, dst_root: Path
) -> tuple[Path, list[str]]:
    """Kopier alle YAMLs til dst_root/instruments og null ut `driver_name`.

    Returnerer (instruments_dir, impacted_instruments) der impacted er
    listen av instrumenter (bedrock-id) der driver-vekt ble justert.
    """
    dst_dir = dst_root / "instruments"
    dst_dir.mkdir(parents=True, exist_ok=True)
    impacted: list[str] = []
    for src_yaml in sorted(src_dir.glob("*.yaml")):
        dst_yaml = dst_dir / src_yaml.name
        shutil.copy2(src_yaml, dst_yaml)
        n = _zero_driver_in_yaml(dst_yaml, driver_name)
        if n > 0:
            # Mapper filename → instrument-id (les yaml igjen for sikker mapping)
            inst_id = yaml.safe_load(dst_yaml.read_text())["instrument"]["id"]
            impacted.append(inst_id)
    # Family-fil (family_financial.yaml etc) må også kopieres siden
    # `inherits:` peker på dem.
    for src_extra in sorted(src_dir.glob("family_*.yaml")):
        # Allerede kopiert via *.yaml-glob, men være eksplisitt
        if not (dst_dir / src_extra.name).exists():
            shutil.copy2(src_extra, dst_dir / src_extra.name)
    return dst_dir, impacted


# ---------------------------------------------------------------------------
# Orchestrator-mode
# ---------------------------------------------------------------------------


def _direction_aware_hit(forward_return_pct: float, threshold_pct: float, direction: str) -> bool:
    if direction == "buy":
        return forward_return_pct >= threshold_pct
    return forward_return_pct <= -threshold_pct


def _run_one(
    store: DataStore,
    instrument: str,
    horizon_days: int,
    direction: str,
    from_date: date,
    to_date: date,
    step_days: int,
    instruments_dir: str | None,
) -> dict:
    """Kjør én (instrument, horizon, direction)-replay og returner agg-stats."""
    config = BacktestConfig(
        instrument=instrument,
        horizon_days=horizon_days,
        from_date=from_date,
        to_date=to_date,
        outcome_threshold_pct=THRESHOLDS_PCT[horizon_days],
    )
    t0 = time.time()
    result = run_orchestrator_replay(
        store,
        config,
        instruments_dir=instruments_dir,
        direction=direction,
        step_days=step_days,
    )
    elapsed = time.time() - t0
    threshold = THRESHOLDS_PCT[horizon_days]

    n = len(result.signals)
    if n == 0:
        return {
            "instrument": instrument,
            "horizon_days": horizon_days,
            "direction": direction,
            "n": 0,
            "hit_rate_pct": None,
            "publish_rate_pct": None,
            "avg_score": None,
            "avg_published_score": None,
            "grade_counts": {},
            "elapsed_s": elapsed,
        }

    hits = sum(
        1
        for s in result.signals
        if _direction_aware_hit(s.forward_return_pct, threshold, direction)
    )
    published = [s for s in result.signals if s.published is True]
    scores = [s.score for s in result.signals if s.score is not None]
    pub_scores = [s.score for s in published if s.score is not None]

    grade_counts: dict[str, int] = {}
    for s in result.signals:
        g = s.grade or "?"
        grade_counts[g] = grade_counts.get(g, 0) + 1

    return {
        "instrument": instrument,
        "horizon_days": horizon_days,
        "direction": direction,
        "n": n,
        "hit_rate_pct": (hits / n) * 100.0,
        "publish_rate_pct": (len(published) / n) * 100.0,
        "avg_score": statistics.mean(scores) if scores else None,
        "avg_published_score": statistics.mean(pub_scores) if pub_scores else None,
        "grade_counts": grade_counts,
        "elapsed_s": elapsed,
    }


def run_orchestrator_sweep(
    store: DataStore,
    instruments: Iterable[str],
    from_date: date,
    to_date: date,
    step_days: int = 5,
    instruments_dir: str | None = None,
) -> list[dict]:
    """Kjør full sweep over (instrument, horizon, direction) og returner liste."""
    rows: list[dict] = []
    insts = list(instruments)
    total = len(insts) * len(HORIZONS) * len(DIRECTIONS)
    i = 0
    overall_t0 = time.time()
    for inst in insts:
        for horizon_days in HORIZONS:
            for direction in DIRECTIONS:
                i += 1
                t0 = time.time()
                row = _run_one(
                    store=store,
                    instrument=inst,
                    horizon_days=horizon_days,
                    direction=direction,
                    from_date=from_date,
                    to_date=to_date,
                    step_days=step_days,
                    instruments_dir=instruments_dir,
                )
                elapsed = time.time() - t0
                cum = time.time() - overall_t0
                hit_str = (
                    f"{row['hit_rate_pct']:5.1f}%" if row["hit_rate_pct"] is not None else "  -  "
                )
                pub_str = (
                    f"{row['publish_rate_pct']:5.1f}%"
                    if row["publish_rate_pct"] is not None
                    else "  -  "
                )
                print(
                    f"[{i:3d}/{total}] {inst:12s} {horizon_days:3d}d "
                    f"{direction:4s}  n={row['n']:3d}  hit={hit_str}  pub={pub_str}  "
                    f"({elapsed:5.1f}s, cum {cum / 60:5.1f}min)",
                    flush=True,
                )
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Baseline-mode (re-aggregering på analog_outcomes — session 99 reprise)
# ---------------------------------------------------------------------------


def run_baseline_aggregation(store: DataStore) -> list[dict]:
    """Re-kjør session 99-stil aggregering på analog_outcomes-tabellen.

    Måler kun forward_return-distribusjon (uten orchestrator-scoring).
    Bekrefter at session 99-tall reproduseres fra dagens DB. Skal være
    ~uendret (analog_outcomes har ikke vokst i Phase A-C).
    """
    rows: list[dict] = []
    for inst in WHITELIST_17:
        for horizon_days in HORIZONS:
            threshold = THRESHOLDS_PCT[horizon_days]
            cfg = BacktestConfig(
                instrument=inst,
                horizon_days=horizon_days,
                outcome_threshold_pct=threshold,
            )
            for direction in DIRECTIONS:
                result = run_outcome_replay(store, cfg)
                n = len(result.signals)
                if n == 0:
                    rows.append(
                        {
                            "instrument": inst,
                            "horizon_days": horizon_days,
                            "direction": direction,
                            "n": 0,
                            "hit_rate_pct": None,
                            "avg_return_pct": None,
                            "stdev_return_pct": None,
                        }
                    )
                    continue
                hits = sum(
                    1
                    for s in result.signals
                    if _direction_aware_hit(s.forward_return_pct, threshold, direction)
                )
                returns = [s.forward_return_pct for s in result.signals]
                rows.append(
                    {
                        "instrument": inst,
                        "horizon_days": horizon_days,
                        "direction": direction,
                        "n": n,
                        "hit_rate_pct": (hits / n) * 100.0,
                        "avg_return_pct": statistics.mean(returns),
                        "stdev_return_pct": (statistics.stdev(returns) if n > 1 else 0.0),
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_window() -> tuple[date, date]:
    """Standardvindu: siste 12 måneder fra i dag (i.e. ref_date-rangen)."""
    today = date.today()
    # Siste 12 mnd. analog_outcomes har data tom ~2026-03-12 for 30d og
    # ~2025-12-12 for 90d, så `to_date` blir auto-clipped.
    return today - timedelta(days=365), today


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["orchestrator", "baseline", "spike"],
        default="orchestrator",
    )
    parser.add_argument(
        "--driver",
        help="Driver-navn for spike-mode (kun gyldig med --mode spike)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSON-output-fil",
    )
    parser.add_argument(
        "--instruments",
        nargs="*",
        default=None,
        help="Subset av instrumenter (default: alle 22). Spike-mode bruker "
        "alltid alle 22 (zero-driver-mock påvirker kun de relevante).",
    )
    parser.add_argument(
        "--step-days", type=int, default=5, help="Step mellom ref_dates (default 5)"
    )
    parser.add_argument(
        "--from-date",
        type=lambda s: date.fromisoformat(s),
        default=None,
    )
    parser.add_argument(
        "--to-date",
        type=lambda s: date.fromisoformat(s),
        default=None,
    )
    args = parser.parse_args()

    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    if args.mode == "baseline":
        print(f"# Baseline-aggregering ({len(WHITELIST_17)} instrumenter, full historikk)")
        rows = run_baseline_aggregation(store)
        payload = {"mode": "baseline", "rows": rows}
    elif args.mode == "spike":
        if not args.driver:
            parser.error("--driver er påkrevd i spike-mode")
        from_d, to_d = args.from_date or _default_window()[0], args.to_date or _default_window()[1]
        print(
            f"# Spike-mode: zero-out '{args.driver}' i alle YAMLs "
            f"({from_d}..{to_d}, step={args.step_days})"
        )
        with tempfile.TemporaryDirectory(prefix="bedrock_spike_") as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            spike_dir, impacted = _build_spike_instruments_dir(
                Path("config/instruments"), args.driver, tmpdir
            )
            print(f"  Påvirket {len(impacted)} instrumenter: {impacted}")
            insts = args.instruments or impacted or ALL_INSTRUMENTS
            rows = run_orchestrator_sweep(
                store,
                insts,
                from_date=from_d,
                to_date=to_d,
                step_days=args.step_days,
                instruments_dir=str(spike_dir),
            )
            payload = {
                "mode": "spike",
                "driver": args.driver,
                "impacted_instruments": impacted,
                "rows": rows,
            }
    else:  # orchestrator
        from_d, to_d = args.from_date or _default_window()[0], args.to_date or _default_window()[1]
        insts = args.instruments or ALL_INSTRUMENTS
        print(
            f"# Orchestrator-replay sweep ({len(insts)} inst × "
            f"{len(HORIZONS)} hor × {len(DIRECTIONS)} dir, "
            f"vindu {from_d}..{to_d}, step={args.step_days})"
        )
        rows = run_orchestrator_sweep(
            store,
            insts,
            from_date=from_d,
            to_date=to_d,
            step_days=args.step_days,
        )
        payload = {
            "mode": "orchestrator",
            "from_date": from_d.isoformat(),
            "to_date": to_d.isoformat(),
            "step_days": args.step_days,
            "rows": rows,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nSkrevet: {args.output} ({len(rows)} rader)")


if __name__ == "__main__":
    main()
