"""BacktestConfig — pydantic-validert input til run_outcome_replay.

Holder alt som styrer ett backtest-kjør: instrument, horizon, dato-
vindu, hit-terskel, output-format. Validering ved konstruksjon slik at
CLI/programmatisk-bruk får like feilmeldinger.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReportFormat = Literal["markdown", "json"]


class BacktestConfig(BaseModel):
    """Input til ett backtest-run.

    `from_date` / `to_date`: inklusive grenser på `ref_date`-kolonnen
    i `analog_outcomes`-tabellen. Default = (None, None) betyr hele
    tilgjengelige historikken for instrumentet.

    `outcome_threshold_pct`: terskel for "hit" (samme semantikk som
    `analog_hit_rate`-driveren). Default 3.0 per § 6.5.

    `report_format`: kontrollerer hva `report.format_*` skal produsere.
    """

    instrument: str
    horizon_days: int = Field(gt=0)
    from_date: date | None = None
    to_date: date | None = None
    outcome_threshold_pct: float = 3.0
    report_format: ReportFormat = "markdown"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_date_window(self) -> BacktestConfig:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError(f"from_date {self.from_date} må være ≤ to_date {self.to_date}")
        return self
