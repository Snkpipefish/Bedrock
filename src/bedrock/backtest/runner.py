"""Backtest-runner — leser analog_outcomes og bygger BacktestResult.

Session 62: kun `run_outcome_replay`. Senere sessions vil legge til
`run_orchestrator_replay` som faktisk re-kjører orchestrator as-of-date
for hver dato i vinduet (krever as-of-date DataStore-view).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from bedrock.backtest.config import BacktestConfig
from bedrock.backtest.result import BacktestResult, BacktestSignal

if TYPE_CHECKING:
    from bedrock.data.store import DataStore


def run_outcome_replay(
    store: DataStore,
    config: BacktestConfig,
) -> BacktestResult:
    """Bygg BacktestResult fra eksisterende `analog_outcomes`-tabell.

    Itererer over alle ref_dates for (instrument, horizon_days) i
    config-vinduet og bygger én BacktestSignal per rad. Hit-flag
    beregnes on-the-fly fra `outcome_threshold_pct` slik at samme
    tabell kan re-aggregeres med ulike terskler uten re-backfill.

    Tom tabell (ingen outcomes) → BacktestResult med tom
    signals-liste (ikke exception).
    """
    df = store.get_outcomes(
        config.instrument,
        horizon_days=config.horizon_days,
    )

    if df.empty:
        return BacktestResult(config=config, signals=[])

    # Filter på dato-vindu
    if config.from_date is not None:
        df = df[df["ref_date"] >= pd.Timestamp(config.from_date).tz_localize(None)]
    if config.to_date is not None:
        df = df[df["ref_date"] <= pd.Timestamp(config.to_date).tz_localize(None)]

    if df.empty:
        return BacktestResult(config=config, signals=[])

    threshold = config.outcome_threshold_pct
    signals: list[BacktestSignal] = []
    for row in df.itertuples(index=False):
        # ref_date kommer som pd.Timestamp; konverter til date for
        # Pydantic-modellen (date-validator)
        ref_date = row.ref_date
        if hasattr(ref_date, "date"):
            ref_date = ref_date.date()

        max_dd = row.max_drawdown_pct
        if pd.isna(max_dd):
            max_dd = None
        else:
            max_dd = float(max_dd)

        signals.append(
            BacktestSignal(
                ref_date=ref_date,
                instrument=config.instrument,
                horizon_days=config.horizon_days,
                forward_return_pct=float(row.forward_return_pct),
                max_drawdown_pct=max_dd,
                hit=bool(row.forward_return_pct >= threshold),
            )
        )

    # Sorter på dato (defensiv — DB returnerer ASC, men sikrer)
    signals.sort(key=lambda s: s.ref_date)
    return BacktestResult(config=config, signals=signals)
