"""BacktestSignal + BacktestResult — pydantic output fra backtest-kjør.

`BacktestSignal` er én rad i resultatet (én ref_date × én horizon).
For session 62 outcome-replay har vi forward_return + max_drawdown +
hit-flag, men ingen score/grade/published (de kommer i orchestrator-
replay). Feltene er valgfrie så samme modell kan brukes både i
session 62-utgaven og senere full-pipeline.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from bedrock.backtest.config import BacktestConfig


class BacktestSignal(BaseModel):
    """Én simulert signal-observasjon i backtest.

    `score`/`grade`/`published` er None for session 62 outcome-replay
    (vi har ingen orchestrator-output). Når `run_orchestrator_replay`
    er ferdig (senere session), skal disse populeres.
    """

    ref_date: date
    instrument: str
    horizon_days: int
    forward_return_pct: float
    max_drawdown_pct: float | None = None
    hit: bool  # forward_return_pct >= outcome_threshold_pct (fra config)
    score: float | None = None  # populeres av orchestrator-replay senere
    grade: str | None = None
    published: bool | None = None

    model_config = ConfigDict(extra="forbid")


class BacktestResult(BaseModel):
    """Full output fra ett backtest-kjør — config + alle signaler.

    Aggregat-stats (hit-rate, avg-return etc.) beregnes separat i
    `report.summary_stats` slik at `BacktestResult` kan re-aggregeres
    med ulike terskler uten å kjøre backtest på nytt.
    """

    config: BacktestConfig
    signals: list[BacktestSignal] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
