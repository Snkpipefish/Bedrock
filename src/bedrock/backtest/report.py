"""BacktestReport — aggregat-stats + format-utskrift (markdown / JSON).

Holdt separat fra `BacktestResult` slik at resultatet kan re-aggregeres
med ulike terskler / vinduer uten re-replay.
"""

from __future__ import annotations

import json
from statistics import mean, median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bedrock.backtest.result import BacktestResult, BacktestSignal


class BacktestReport(BaseModel):
    """Aggregert sammendrag av et backtest-kjør.

    Per-grade- og per-horizon-breakdown er TODO inntil
    `run_orchestrator_replay` populerer score/grade. I session 62 er
    feltene tilgjengelige men tomme for outcome-replay-output.
    """

    n_signals: int
    n_hits: int  # forward_return_pct >= outcome_threshold_pct
    hit_rate_pct: float  # 0..100
    avg_return_pct: float
    median_return_pct: float
    best_return_pct: float
    worst_return_pct: float
    avg_drawdown_pct: float | None = None  # None hvis ingen drawdown-data
    worst_drawdown_pct: float | None = None
    n_published: int | None = None  # populeres av orchestrator-replay
    by_grade: dict[str, dict[str, float]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def summary_stats(result: BacktestResult) -> BacktestReport:
    """Aggreger BacktestResult til en BacktestReport.

    Tom `signals`-liste → BacktestReport med n_signals=0 og 0/0.0 for
    aggregat (ingen exception). Caller (CLI/UI) håndterer "ingen data"-
    visning.
    """
    sigs = result.signals
    n = len(sigs)

    if n == 0:
        return BacktestReport(
            n_signals=0,
            n_hits=0,
            hit_rate_pct=0.0,
            avg_return_pct=0.0,
            median_return_pct=0.0,
            best_return_pct=0.0,
            worst_return_pct=0.0,
            avg_drawdown_pct=None,
            worst_drawdown_pct=None,
        )

    returns = [s.forward_return_pct for s in sigs]
    hits = sum(1 for s in sigs if s.hit)

    drawdowns = [s.max_drawdown_pct for s in sigs if s.max_drawdown_pct is not None]
    avg_dd = mean(drawdowns) if drawdowns else None
    worst_dd = min(drawdowns) if drawdowns else None

    n_pub = (
        sum(1 for s in sigs if s.published is True)
        if any(s.published is not None for s in sigs)
        else None
    )

    # Per-grade-breakdown — kun når grade-felt er populert (orchestrator-replay)
    by_grade: dict[str, dict[str, float]] = {}
    grade_buckets: dict[str, list[BacktestSignal]] = {}
    for s in sigs:
        if s.grade is None:
            continue
        grade_buckets.setdefault(s.grade, []).append(s)

    for grade, bucket in grade_buckets.items():
        bucket_returns = [s.forward_return_pct for s in bucket]
        bucket_hits = sum(1 for s in bucket if s.hit)
        by_grade[grade] = {
            "n_signals": float(len(bucket)),
            "n_hits": float(bucket_hits),
            "hit_rate_pct": bucket_hits / len(bucket) * 100.0,
            "avg_return_pct": mean(bucket_returns),
        }

    return BacktestReport(
        n_signals=n,
        n_hits=hits,
        hit_rate_pct=hits / n * 100.0,
        avg_return_pct=mean(returns),
        median_return_pct=median(returns),
        best_return_pct=max(returns),
        worst_return_pct=min(returns),
        avg_drawdown_pct=avg_dd,
        worst_drawdown_pct=worst_dd,
        n_published=n_pub,
        by_grade=_sorted_grade_dict(by_grade),
    )


def _sorted_grade_dict(d: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Sortér grade-dict etter rangering (A+ først, så A, B, C, D)."""
    rank = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    return dict(sorted(d.items(), key=lambda kv: rank.get(kv[0], 99)))


# ---------------------------------------------------------------------------
# Format-utskrift
# ---------------------------------------------------------------------------


def format_markdown(result: BacktestResult, report: BacktestReport) -> str:
    """Render BacktestReport som markdown-tabell + summary-tekst.

    Format:

        # Backtest: <instrument> · h=<H>d
        Vindu: <from> .. <to>  (<n> signaler)
        Hit-terskel: <threshold>%

        | Metric | Value |
        |---|---:|
        ...

    Hvis n_signals == 0 returneres en tydelig "Ingen data"-melding.
    """
    cfg = result.config
    window = _window_str(cfg.from_date, cfg.to_date)

    if report.n_signals == 0:
        return (
            f"# Backtest: {cfg.instrument} · h={cfg.horizon_days}d\n\n"
            f"Vindu: {window}\n\n"
            f"**Ingen outcomes funnet.** Sjekk at `analog_outcomes` er backfilt "
            f"for instrument={cfg.instrument!r} horizon_days={cfg.horizon_days}."
        )

    lines: list[str] = [
        f"# Backtest: {cfg.instrument} · h={cfg.horizon_days}d",
        "",
        f"- **Vindu:** {window}",
        f"- **Antall signaler:** {report.n_signals}",
        f"- **Hit-terskel:** ≥ {cfg.outcome_threshold_pct:.1f}%",
    ]
    if report.n_published is not None:
        lines.append(f"- **Publisert (score ≥ floor):** {report.n_published} av {report.n_signals}")
    lines.append("")

    rows = [
        ("Hit-rate", f"{report.hit_rate_pct:.1f}% ({report.n_hits}/{report.n_signals})"),
        ("Avg return", f"{_signed_pct(report.avg_return_pct)}"),
        ("Median return", f"{_signed_pct(report.median_return_pct)}"),
        ("Best return", f"{_signed_pct(report.best_return_pct)}"),
        ("Worst return", f"{_signed_pct(report.worst_return_pct)}"),
    ]
    if report.avg_drawdown_pct is not None:
        rows.append(("Avg drawdown", f"{_signed_pct(report.avg_drawdown_pct)}"))
    if report.worst_drawdown_pct is not None:
        rows.append(("Worst drawdown", f"{_signed_pct(report.worst_drawdown_pct)}"))

    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for label, value in rows:
        lines.append(f"| {label} | {value} |")

    if report.by_grade:
        lines.extend(
            [
                "",
                "## Per grade",
                "",
                "| Grade | n | Hit-rate | Avg return |",
                "|---|---:|---:|---:|",
            ]
        )
        for grade, stats in report.by_grade.items():
            lines.append(
                f"| {grade} | {int(stats['n_signals'])} | "
                f"{stats['hit_rate_pct']:.1f}% | "
                f"{_signed_pct(stats['avg_return_pct'])} |"
            )

    return "\n".join(lines) + "\n"


def format_json(result: BacktestResult, report: BacktestReport) -> str:
    """Render BacktestReport + signaler som JSON-streng (indent=2).

    `signals` inkluderes som liste — full output, ikke trunkert.
    Caller (CLI) kan separere full og summary om nødvendig.
    """
    payload: dict[str, Any] = {
        "config": json.loads(result.config.model_dump_json()),
        "report": json.loads(report.model_dump_json()),
        "signals": [json.loads(s.model_dump_json()) for s in result.signals],
    }
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signed_pct(v: float) -> str:
    """Format som '+1.23%' eller '-1.23%'."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _window_str(from_date: object, to_date: object) -> str:
    f = str(from_date) if from_date is not None else "(start)"
    t = str(to_date) if to_date is not None else "(idag)"
    return f"{f} .. {t}"
