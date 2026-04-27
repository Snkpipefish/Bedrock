"""Harvester for full historisk per-driver scoring-data.

Walker (instrument × horizon × direction × ref_date)-kombinasjoner over
full historikk i `analog_outcomes` og kjører `generate_signals` med
AsOfDateStore for hver. Ekstraktér per-driver-verdier fra
`SignalEntry.families[].drivers[].value` og skriver til SQLite-tabellen
`driver_observations` for senere IC/hit-rate-analyse.

Schema-rad per (instrument, ref_date, horizon_days, direction, driver):
- driver_value (rå 0..1 fra driver-call)
- driver_weight (fra YAML)
- driver_contribution (value * weight)
- family_name
- family_score
- group_score (final aggregert score for hele entry)
- grade
- published
- forward_return_pct (hentet fra analog_outcomes — uclippet)

Resumable: PRIMARY KEY (instrument, ref_date, horizon_days, direction,
driver_name) + INSERT OR IGNORE. Stop og restart trygt — hopper over
allerede skrevne kombinasjoner.

Kjør for ett instrument:

    PYTHONPATH=src .venv/bin/python scripts/harvest_driver_observations.py \\
        --instrument Gold --step-days 14 --log /tmp/harvest_Gold.log

Eller alle 22 sekvensielt via wrapper:

    nohup ./scripts/run_full_history_harvest.sh > /tmp/harvest.log 2>&1 &
"""
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import structlog

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore
from bedrock.signal_server.config import load_from_env

_log = structlog.get_logger(__name__)

# Mapping fra horizon_days → orchestrator YAML-horizon-key
_HORIZON_DAYS_TO_NAME: dict[int, str] = {30: "SCALP", 60: "SWING", 90: "MAKRO"}
# Alle 3 horisonter — asymmetri-trader vurderes på tvers av kortsiktig
# (SCALP), mellomsiktig (SWING) og langsiktig (MAKRO). 60d har ingen
# analog_outcomes-data så fwd-return syntetiseres fra prices.
HORIZONS: list[int] = [30, 60, 90]
DIRECTIONS: list[str] = ["buy", "sell"]

DDL_DRIVER_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS driver_observations (
    instrument TEXT NOT NULL,
    ref_date TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    direction TEXT NOT NULL,
    driver_name TEXT NOT NULL,
    family_name TEXT NOT NULL,
    driver_value REAL,
    driver_weight REAL,
    driver_contribution REAL,
    family_score REAL,
    group_score REAL,
    grade TEXT,
    published INTEGER,
    forward_return_pct REAL,
    max_drawdown_pct REAL,
    PRIMARY KEY (instrument, ref_date, horizon_days, direction, driver_name)
);
CREATE TABLE IF NOT EXISTS signal_setups (
    instrument TEXT NOT NULL,
    ref_date TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    direction TEXT NOT NULL,
    score REAL,
    grade TEXT,
    published INTEGER,
    entry REAL,
    sl REAL,
    tp REAL,
    rr REAL,
    atr REAL,
    forward_return_pct REAL,
    PRIMARY KEY (instrument, ref_date, horizon_days, direction)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_drvobs_lookup ON driver_observations (driver_name, instrument, horizon_days, direction);",
    "CREATE INDEX IF NOT EXISTS idx_drvobs_resume ON driver_observations (instrument, horizon_days, direction);",
    "CREATE INDEX IF NOT EXISTS idx_drvobs_refdate ON driver_observations (instrument, ref_date);",
    "CREATE INDEX IF NOT EXISTS idx_setup_lookup ON signal_setups (instrument, ref_date);",
    "CREATE INDEX IF NOT EXISTS idx_setup_published ON signal_setups (published, grade);",
]

_INSERT_SQL = """
INSERT OR IGNORE INTO driver_observations
    (instrument, ref_date, horizon_days, direction, driver_name, family_name,
     driver_value, driver_weight, driver_contribution, family_score,
     group_score, grade, published, forward_return_pct, max_drawdown_pct)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_SETUP_SQL = """
INSERT OR IGNORE INTO signal_setups
    (instrument, ref_date, horizon_days, direction, score, grade, published,
     entry, sl, tp, rr, atr, forward_return_pct)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(DDL_DRIVER_OBSERVATIONS)
    for idx_sql in INDEXES:
        con.execute(idx_sql)
    con.commit()


def already_done_ref_dates(
    con: sqlite3.Connection,
    instrument: str,
    horizon_days: int,
    direction: str,
) -> set[str]:
    """Returner set av ref_date-strings som allerede er populert for kombo."""
    rows = con.execute(
        "SELECT DISTINCT ref_date FROM driver_observations "
        "WHERE instrument = ? AND horizon_days = ? AND direction = ?",
        (instrument, horizon_days, direction),
    ).fetchall()
    return {r[0] for r in rows}


def _outcomes_for_instrument(store: DataStore, instrument: str, horizon_days: int) -> pd.DataFrame:
    """Returner alle ref_dates for (instrument, horizon) med forward_return.

    Foretrekker pre-beregnet ``analog_outcomes`` når tilgjengelig (har
    også max_drawdown). Faller tilbake til å syntetisere fra ``prices``
    for instrumenter uten outcomes (BTC/ETH/NaturalGas/Copper/Platinum
    ved session 116 — listen kan endre seg, så vi sjekker dynamisk).
    """
    df = store.get_outcomes(instrument, horizon_days=horizon_days)
    if not df.empty:
        return df.sort_values("ref_date").reset_index(drop=True)
    return _synthesize_outcomes_from_prices(store, instrument, horizon_days)


def _synthesize_outcomes_from_prices(
    store: DataStore, instrument: str, horizon_days: int
) -> pd.DataFrame:
    """Bygg ref_date + forward_return fra prices-tabellen for instrumenter
    uten analog_outcomes. max_drawdown_pct er NaN siden vi ikke beregner
    intra-period drawdown her.
    """
    try:
        prices = store.get_prices(instrument)
    except KeyError:
        return pd.DataFrame(columns=["ref_date", "forward_return_pct", "max_drawdown_pct"])
    if prices.empty:
        return pd.DataFrame(columns=["ref_date", "forward_return_pct", "max_drawdown_pct"])

    # Sorter ASC + dropp NaN-priser
    prices = prices.sort_index().dropna()
    if len(prices) < horizon_days + 2:
        return pd.DataFrame(columns=["ref_date", "forward_return_pct", "max_drawdown_pct"])

    # For hver ref_date: finn nærmeste close ≥ ref + horizon_days kalenderdager.
    # Trade-day-sampling ville være mer presist; her bruker vi kalender-
    # cutoff for å matche analog_outcomes-konvensjonen.
    rows: list[dict] = []
    cutoff_ts = prices.index.max() - pd.Timedelta(days=horizon_days)
    for ref_ts in prices.index[prices.index <= cutoff_ts]:
        ref_close = float(prices.loc[ref_ts])
        target_ts = ref_ts + pd.Timedelta(days=horizon_days)
        future = prices[prices.index >= target_ts]
        if future.empty:
            continue
        future_close = float(future.iloc[0])
        if ref_close <= 0:
            continue
        fwd_return_pct = (future_close / ref_close - 1.0) * 100.0
        rows.append(
            {
                "ref_date": ref_ts,
                "forward_return_pct": fwd_return_pct,
                "max_drawdown_pct": float("nan"),
            }
        )
    return pd.DataFrame(rows)


def harvest_one(
    *,
    store: DataStore,
    db_path: Path,
    instrument: str,
    horizon_days: int,
    direction: str,
    step_days: int,
    instruments_dir: str,
    progress_every: int = 25,
) -> int:
    """Harvest én (instrument, horizon, direction)-kombo. Returnerer antall
    nye rader skrevet (0 hvis alt var allerede gjort).
    """
    horizon_name = _HORIZON_DAYS_TO_NAME[horizon_days]
    outcomes = _outcomes_for_instrument(store, instrument, horizon_days)
    if outcomes.empty:
        print(
            f"  [{instrument} {horizon_days}d {direction}] no analog_outcomes — skip",
            flush=True,
        )
        return 0

    # Step subsampling
    if step_days > 1:
        outcomes = outcomes.iloc[::step_days].reset_index(drop=True)

    con = sqlite3.connect(db_path)
    ensure_schema(con)
    done = already_done_ref_dates(con, instrument, horizon_days, direction)
    todo = outcomes[~outcomes["ref_date"].dt.strftime("%Y-%m-%d").isin(done)]
    n_total = len(outcomes)
    n_done = len(done)
    n_todo = len(todo)
    print(
        f"  [{instrument} {horizon_days}d {direction}] "
        f"{n_total} total, {n_done} done, {n_todo} todo",
        flush=True,
    )
    if n_todo == 0:
        con.close()
        return 0

    # Late import for å unngå sirkulær
    from bedrock.orchestrator.signals import generate_signals

    new_rows = 0
    t0 = time.time()
    for i, row in enumerate(todo.itertuples(index=False), start=1):
        ref_ts: pd.Timestamp = row.ref_date
        ref_date_str = ref_ts.strftime("%Y-%m-%d")
        as_of_store = AsOfDateStore(store, ref_ts)

        try:
            result = generate_signals(
                instrument,
                as_of_store,
                instruments_dir=instruments_dir,
                horizons=[horizon_name],
                directions=None,
                write_snapshot=False,
                now=ref_ts.to_pydatetime() if hasattr(ref_ts, "to_pydatetime") else None,
            )
        except Exception as exc:
            _log.debug(
                "harvest.generate_signals_skip",
                instrument=instrument,
                ref_date=ref_date_str,
                error=str(exc),
            )
            continue

        # Plukk entry for ønsket direction
        entry = next(
            (
                e
                for e in result.entries
                if getattr(e.direction, "value", str(e.direction)).lower() == direction
            ),
            None,
        )
        if entry is None:
            continue

        forward_return_pct = float(row.forward_return_pct)
        max_dd = row.max_drawdown_pct
        max_dd_val: float | None = None if pd.isna(max_dd) else float(max_dd)

        # Ekstraktér per-driver-verdier fra entry.families
        rows_to_insert: list[Sequence] = []
        for fam_name, fam in entry.families.items():
            for drv in fam.drivers:
                rows_to_insert.append(
                    (
                        instrument,
                        ref_date_str,
                        horizon_days,
                        direction,
                        drv.name,
                        fam_name,
                        float(drv.value),
                        float(drv.weight),
                        float(drv.contribution),
                        float(fam.score),
                        float(entry.score),
                        str(entry.grade),
                        1 if entry.published else 0,
                        forward_return_pct,
                        max_dd_val,
                    )
                )

        if rows_to_insert:
            con.executemany(_INSERT_SQL, rows_to_insert)
            new_rows += len(rows_to_insert)

        # Lagre setup-blob hvis tilgjengelig (entry/SL/TP/RR/ATR)
        setup = entry.setup
        setup_inner = setup.setup if setup is not None else None
        if setup_inner is not None:
            con.execute(
                _INSERT_SETUP_SQL,
                (
                    instrument,
                    ref_date_str,
                    horizon_days,
                    direction,
                    float(entry.score),
                    str(entry.grade),
                    1 if entry.published else 0,
                    float(setup_inner.entry),
                    float(setup_inner.sl),
                    None if setup_inner.tp is None else float(setup_inner.tp),
                    None if setup_inner.rr is None else float(setup_inner.rr),
                    float(setup_inner.atr),
                    forward_return_pct,
                ),
            )

        con.commit()

        if i % progress_every == 0:
            elapsed = time.time() - t0
            eta_min = (elapsed / i) * (n_todo - i) / 60
            print(
                f"    {i}/{n_todo} ({ref_date_str})  "
                f"+{new_rows} rows  ({elapsed:5.1f}s, ETA {eta_min:5.1f}min)",
                flush=True,
            )

    con.close()
    elapsed = time.time() - t0
    print(
        f"  [{instrument} {horizon_days}d {direction}] DONE: {new_rows} rader "
        f"({elapsed / 60:5.1f}min, {n_todo} dates)",
        flush=True,
    )
    return new_rows


def harvest_instrument(
    *,
    store: DataStore,
    db_path: Path,
    instrument: str,
    step_days: int,
    instruments_dir: str,
    horizons: list[int] | None = None,
    directions: list[str] | None = None,
) -> int:
    """Harvest alle (horizon, direction)-kombinasjoner for ett instrument."""
    horizons = horizons or HORIZONS
    directions = directions or DIRECTIONS
    total = 0
    print(f"\n=== {instrument} ===", flush=True)
    for hor in horizons:
        for direction in directions:
            n = harvest_one(
                store=store,
                db_path=db_path,
                instrument=instrument,
                horizon_days=hor,
                direction=direction,
                step_days=step_days,
                instruments_dir=instruments_dir,
            )
            total += n
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--horizon", type=int, action="append", choices=[30, 60, 90], default=None)
    parser.add_argument("--direction", action="append", choices=["buy", "sell"], default=None)
    parser.add_argument("--step-days", type=int, default=14)
    parser.add_argument("--instruments-dir", default="config/instruments")
    args = parser.parse_args()

    cfg = load_from_env()
    store = DataStore(cfg.db_path)

    print(
        f"Harvest start: instrument={args.instrument} step={args.step_days} db={cfg.db_path}",
        flush=True,
    )

    n_total = harvest_instrument(
        store=store,
        db_path=cfg.db_path,
        instrument=args.instrument,
        step_days=args.step_days,
        instruments_dir=args.instruments_dir,
        horizons=args.horizon,
        directions=args.direction,
    )

    print(f"\nFerdig: {args.instrument} +{n_total} rows totalt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
