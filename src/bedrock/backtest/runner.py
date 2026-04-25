"""Backtest-runner — leser analog_outcomes og bygger BacktestResult.

Session 62: `run_outcome_replay` (kun outcomes-tabellen).
Session 63: `run_orchestrator_replay` (full Engine-kjøring as-of-date
per ref_date — populerer score/grade/published på BacktestSignal).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd
import structlog

from bedrock.backtest.config import BacktestConfig
from bedrock.backtest.result import BacktestResult, BacktestSignal
from bedrock.backtest.store_view import AsOfDateStore

if TYPE_CHECKING:
    from bedrock.data.store import DataStore

_log = structlog.get_logger(__name__)


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


# ---------------------------------------------------------------------------
# run_orchestrator_replay (session 63)
# ---------------------------------------------------------------------------


# Mapping fra horizon_days → YAML-horizon-streng. Brukes til å plukke
# riktig horizon-blokk i orchestrator-output for hver ref_date.
_HORIZON_DAYS_TO_NAME: dict[int, str] = {
    30: "SCALP",  # SCALP er kortest — brukes for 30d-vindu
    60: "SWING",
    90: "MAKRO",  # MAKRO matcher 90d
}


def _horizon_name_for_days(horizon_days: int) -> str:
    """Velg orchestrator-horizon-navn som best matcher backtest-horisonten.

    For horizon_days som ikke er nøyaktig 30/60/90, plukk nærmeste.
    Default for ukjente: SCALP (siden den oftest er den korteste).
    """
    if horizon_days in _HORIZON_DAYS_TO_NAME:
        return _HORIZON_DAYS_TO_NAME[horizon_days]
    # Nærmest matchende
    closest = min(_HORIZON_DAYS_TO_NAME, key=lambda d: abs(d - horizon_days))
    return _HORIZON_DAYS_TO_NAME[closest]


def run_orchestrator_replay(
    store: DataStore,
    config: BacktestConfig,
    *,
    instruments_dir: str | None = None,
    direction: str = "buy",
    step_days: int = 1,
    max_iterations: int | None = None,
) -> BacktestResult:
    """Re-kjør orchestrator as-of-date for hver ref_date i vinduet og
    bygg BacktestSignal med score/grade/published populert.

    Itererer over ref_dates i `analog_outcomes`-tabellen (kun datoer
    der vi har faktisk forward_return å sammenligne mot). For hver:
    1. Bygg `AsOfDateStore(store, ref_date)` — clipper alt fremover
    2. Kjør `generate_signals(instrument, as_of_store, ...)`
    3. Plukk SignalEntry for (`direction`, horizon-matching-config.horizon_days)
    4. Slå opp ekte forward_return fra `store.get_outcomes` (uclippet,
       siden vi vil sammenligne mot det som faktisk skjedde)
    5. Bygg BacktestSignal med score/grade/published + forward_return + hit

    Args:
        store: Underliggende DataStore med full historikk
        config: BacktestConfig (instrument, horizon_days, dato-vindu, terskel)
        instruments_dir: Sti til config/instruments/ (default
            "config/instruments")
        direction: "buy" eller "sell" — kun ett rapporters per ref_date
        step_days: Steg mellom ref_dates (default 1 = hver dag).
            Sett høyere for å spare tid (5 = ukentlig, 21 = månedlig).
        max_iterations: Hard cap for å unngå runaway. None = alle datoer
            i vinduet.

    Returns:
        BacktestResult med signaler som har score, grade, published OG
        forward_return populert (alle felter).

    Note: orchestrator-replay er BETYDELIG tregere enn outcome-replay
    (sekunder per ref_date pga K-NN + setup-bygger + alle drivere). For
    et 12-mnd-vindu på Gold med step_days=1 må man regne med flere min
    wall-time. Vurder step_days=5 som default-akselerasjon.
    """
    inst_dir = instruments_dir or "config/instruments"
    horizon_name = _horizon_name_for_days(config.horizon_days)

    # Hent ref_dates fra outcomes-tabellen (full historikk)
    outcomes = store.get_outcomes(config.instrument, horizon_days=config.horizon_days)
    if outcomes.empty:
        return BacktestResult(config=config, signals=[])

    if config.from_date is not None:
        outcomes = outcomes[outcomes["ref_date"] >= pd.Timestamp(config.from_date)]
    if config.to_date is not None:
        outcomes = outcomes[outcomes["ref_date"] <= pd.Timestamp(config.to_date)]
    if outcomes.empty:
        return BacktestResult(config=config, signals=[])

    outcomes = outcomes.sort_values("ref_date").reset_index(drop=True)

    # Step-down: hvis step_days > 1, plukk hver N-te ref_date
    if step_days > 1:
        outcomes = outcomes.iloc[::step_days].reset_index(drop=True)

    if max_iterations is not None:
        outcomes = outcomes.head(max_iterations)

    # Late import for å unngå sirkulær (orchestrator → engine →
    # drivers → cli → ...)
    from bedrock.orchestrator.signals import generate_signals

    threshold = config.outcome_threshold_pct
    direction_lower = direction.lower()
    signals: list[BacktestSignal] = []

    for row in outcomes.itertuples(index=False):
        ref_ts: pd.Timestamp = row.ref_date
        ref_date_obj: date = ref_ts.date() if hasattr(ref_ts, "date") else ref_ts
        as_of_store = AsOfDateStore(store, ref_ts)

        try:
            result = generate_signals(
                config.instrument,
                as_of_store,
                instruments_dir=inst_dir,
                horizons=[horizon_name],
                directions=None,  # default [BUY, SELL]
                write_snapshot=False,
                now=ref_ts.to_pydatetime() if hasattr(ref_ts, "to_pydatetime") else None,
            )
        except Exception as exc:
            _log.debug("orchestrator_replay.skip", ref_date=str(ref_date_obj), error=str(exc))
            continue

        # Plukk entry for ønsket direction. `e.direction` er en Direction-
        # enum; bruk `.value` (string "buy"/"sell") i stedet for str(...)
        # som gir "Direction.BUY".
        entry = next(
            (
                e
                for e in result.entries
                if getattr(e.direction, "value", str(e.direction)).lower() == direction_lower
            ),
            None,
        )
        if entry is None:
            continue

        forward_return_pct = float(row.forward_return_pct)
        max_dd = row.max_drawdown_pct
        max_dd = None if pd.isna(max_dd) else float(max_dd)

        signals.append(
            BacktestSignal(
                ref_date=ref_date_obj,
                instrument=config.instrument,
                horizon_days=config.horizon_days,
                forward_return_pct=forward_return_pct,
                max_drawdown_pct=max_dd,
                hit=forward_return_pct >= threshold,
                score=float(entry.score),
                grade=str(entry.grade),
                published=bool(entry.published),
            )
        )

    return BacktestResult(config=config, signals=signals)
