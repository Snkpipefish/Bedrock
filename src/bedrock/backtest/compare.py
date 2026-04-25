"""compare_signals — diff to BacktestResult-kjøringer.

Fase 11 session 65 leveranse. Brukes til regelsett-impact-tester
(PLAN § 11.5): kjør samme historikk mot v1- og v2-YAML, og rapporter
hvor mye signalene flyttet. Brukes både i tests (assertion på max
endring) og i PR-output for å vise hva en regel-redigering faktisk
gjorde.

Diff er på ref_date-nivå. Tre kategorier:
- `only_v1`: ref_date finnes i v1, mangler i v2 (signal forsvant)
- `only_v2`: ref_date finnes i v2, mangler i v1 (signal kom til)
- `changed`: ref_date i begge, men score/grade/published/hit endret

Identiske ref_dates uten endring tellas, men ikke listes i diff_rows.

`compare_signals` aksepterer to BacktestResult og returnerer
CompareReport. Hverken sortering eller instrumentet sjekkes — caller
ansvarer for at v1/v2 er meningsfullt sammenlignbare (samme instrument
+ horizon). Hvis instrumenter er forskjellige loggers en advarsel.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from bedrock.backtest.result import BacktestResult, BacktestSignal

_log = structlog.get_logger(__name__)


_GRADE_RANK: dict[str, int] = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4}


def _grade_rank(grade: str | None) -> int:
    """Lavere tall = bedre grade. Ukjent grade rangeres lavest (99)."""
    if grade is None:
        return 99
    return _GRADE_RANK.get(grade, 99)


DiffKind = Literal["only_v1", "only_v2", "changed"]


class DiffRow(BaseModel):
    """Én rad i compare-diff: ett ref_date hvor v1 og v2 avviker."""

    ref_date: date
    kind: DiffKind
    score_v1: float | None = None
    score_v2: float | None = None
    grade_v1: str | None = None
    grade_v2: str | None = None
    published_v1: bool | None = None
    published_v2: bool | None = None
    hit_v1: bool | None = None
    hit_v2: bool | None = None
    forward_return_pct_v1: float | None = None
    forward_return_pct_v2: float | None = None

    model_config = ConfigDict(extra="forbid")


class CompareReport(BaseModel):
    """Aggregat + detaljer fra compare_signals.

    Aggregatfelter brukes i tester (assertions); `diff_rows` brukes
    i markdown-rapporten + audit.
    """

    label_v1: str
    label_v2: str

    n_signals_v1: int
    n_signals_v2: int

    n_only_v1: int  # ref_dates kun i v1
    n_only_v2: int  # ref_dates kun i v2
    n_common: int  # ref_dates i begge
    n_changed: int  # av n_common, hvor noe endret seg

    # Score-/grade-statistikk (kun blant felles)
    n_score_changed: int
    n_grade_changed: int
    n_grade_promoted: int  # v2 bedre enn v1 (lavere rank)
    n_grade_demoted: int  # v2 dårligere enn v1 (høyere rank)

    # Published-overgang
    n_published_added: int  # ble published i v2 (var ikke i v1)
    n_published_removed: int  # var published i v1, ikke i v2

    # Hit-overgang (forward_return identisk per definisjon, men hit-flag
    # kan endres hvis terskel forskjellig)
    n_hit_changed: int

    # Per § 11.5: brukt i `assert diff.signal_count_delta < 0.10 * len(v1)`
    signal_count_delta: int  # |n_v2 - n_v1|

    diff_rows: list[DiffRow] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _signals_by_ref_date(signals: list[BacktestSignal]) -> dict[date, BacktestSignal]:
    """Indekser signaler på ref_date. Hvis duplikater (samme ref_date),
    siste vinner — det skjer ikke i normal bruk siden orchestrator-
    replay produserer én entry per ref_date per direction."""
    return {s.ref_date: s for s in signals}


def _has_meaningful_change(s1: BacktestSignal, s2: BacktestSignal) -> bool:
    """Er endringen mellom s1 og s2 meningsfull (ikke bare numerisk støy)?

    Vi sammenligner score med toleranse 1e-9 (Pydantic float-rep).
    Grade/published/hit sammenlignes som-er.
    """
    if s1.grade != s2.grade:
        return True
    if s1.published != s2.published:
        return True
    if s1.hit != s2.hit:
        return True
    s1_score = s1.score if s1.score is not None else 0.0
    s2_score = s2.score if s2.score is not None else 0.0
    return abs(s1_score - s2_score) > 1e-9


def compare_signals(
    v1: BacktestResult,
    v2: BacktestResult,
    *,
    label_v1: str = "v1",
    label_v2: str = "v2",
) -> CompareReport:
    """Diff to BacktestResult-kjøringer ref_date for ref_date.

    Args:
        v1: Baseline-kjøring (oftest "før regelendring")
        v2: Sammenligning-kjøring (oftest "etter regelendring")
        label_v1: Etikett for v1 i rapport (default "v1")
        label_v2: Etikett for v2 i rapport (default "v2")

    Returns:
        CompareReport med aggregat + diff_rows. Bruk
        `format_compare_markdown(report)` for rendering.

    Note: instrument og horizon i v1.config og v2.config sjekkes ikke
    formelt — caller har ansvaret for at v1/v2 er sammenlignbare.
    Hvis de avviker logges advarsel.
    """
    if v1.config.instrument != v2.config.instrument:
        _log.warning(
            "compare_signals.instrument_mismatch",
            v1=v1.config.instrument,
            v2=v2.config.instrument,
        )
    if v1.config.horizon_days != v2.config.horizon_days:
        _log.warning(
            "compare_signals.horizon_mismatch",
            v1=v1.config.horizon_days,
            v2=v2.config.horizon_days,
        )

    map_v1 = _signals_by_ref_date(v1.signals)
    map_v2 = _signals_by_ref_date(v2.signals)

    keys_v1 = set(map_v1)
    keys_v2 = set(map_v2)
    only_v1 = keys_v1 - keys_v2
    only_v2 = keys_v2 - keys_v1
    common = keys_v1 & keys_v2

    diff_rows: list[DiffRow] = []
    n_score_changed = 0
    n_grade_changed = 0
    n_grade_promoted = 0
    n_grade_demoted = 0
    n_published_added = 0
    n_published_removed = 0
    n_hit_changed = 0
    n_changed = 0

    for ref_date in sorted(only_v1):
        s1 = map_v1[ref_date]
        diff_rows.append(
            DiffRow(
                ref_date=ref_date,
                kind="only_v1",
                score_v1=s1.score,
                grade_v1=s1.grade,
                published_v1=s1.published,
                hit_v1=s1.hit,
                forward_return_pct_v1=s1.forward_return_pct,
            )
        )

    for ref_date in sorted(only_v2):
        s2 = map_v2[ref_date]
        diff_rows.append(
            DiffRow(
                ref_date=ref_date,
                kind="only_v2",
                score_v2=s2.score,
                grade_v2=s2.grade,
                published_v2=s2.published,
                hit_v2=s2.hit,
                forward_return_pct_v2=s2.forward_return_pct,
            )
        )

    for ref_date in sorted(common):
        s1 = map_v1[ref_date]
        s2 = map_v2[ref_date]
        if not _has_meaningful_change(s1, s2):
            continue

        n_changed += 1

        # Score
        s1_score = s1.score if s1.score is not None else 0.0
        s2_score = s2.score if s2.score is not None else 0.0
        if abs(s1_score - s2_score) > 1e-9:
            n_score_changed += 1

        # Grade
        if s1.grade != s2.grade:
            n_grade_changed += 1
            r1 = _grade_rank(s1.grade)
            r2 = _grade_rank(s2.grade)
            if r2 < r1:
                n_grade_promoted += 1
            elif r2 > r1:
                n_grade_demoted += 1
            # r2 == r1 betyr ingen change — håndtert ovenfor

        # Published
        if s1.published != s2.published:
            if s2.published is True and s1.published is not True:
                n_published_added += 1
            elif s1.published is True and s2.published is not True:
                n_published_removed += 1

        # Hit
        if s1.hit != s2.hit:
            n_hit_changed += 1

        diff_rows.append(
            DiffRow(
                ref_date=ref_date,
                kind="changed",
                score_v1=s1.score,
                score_v2=s2.score,
                grade_v1=s1.grade,
                grade_v2=s2.grade,
                published_v1=s1.published,
                published_v2=s2.published,
                hit_v1=s1.hit,
                hit_v2=s2.hit,
                forward_return_pct_v1=s1.forward_return_pct,
                forward_return_pct_v2=s2.forward_return_pct,
            )
        )

    return CompareReport(
        label_v1=label_v1,
        label_v2=label_v2,
        n_signals_v1=len(v1.signals),
        n_signals_v2=len(v2.signals),
        n_only_v1=len(only_v1),
        n_only_v2=len(only_v2),
        n_common=len(common),
        n_changed=n_changed,
        n_score_changed=n_score_changed,
        n_grade_changed=n_grade_changed,
        n_grade_promoted=n_grade_promoted,
        n_grade_demoted=n_grade_demoted,
        n_published_added=n_published_added,
        n_published_removed=n_published_removed,
        n_hit_changed=n_hit_changed,
        signal_count_delta=abs(len(v1.signals) - len(v2.signals)),
        diff_rows=diff_rows,
    )


def format_compare_markdown(report: CompareReport, *, max_rows: int = 50) -> str:
    """Render CompareReport som markdown.

    `max_rows` capper diff-tabellen. Default 50 — for full audit, sett
    høyere eller bruk `format_compare_json`.
    """
    lines: list[str] = []
    lines.append(f"# Compare: {report.label_v1} → {report.label_v2}\n")
    lines.append(
        f"- **Signaler:** {report.n_signals_v1} ({report.label_v1}) → "
        f"{report.n_signals_v2} ({report.label_v2}) "
        f"(Δ = {report.signal_count_delta})\n"
    )
    lines.append(
        f"- **Felles ref_dates:** {report.n_common} (av disse {report.n_changed} endret)\n"
    )
    lines.append(
        f"- **Kun i {report.label_v1}:** {report.n_only_v1} · "
        f"**kun i {report.label_v2}:** {report.n_only_v2}\n"
    )
    lines.append("")
    lines.append("## Aggregat (blant felles ref_dates)\n")
    lines.append("| Endring | Antall |")
    lines.append("|---|---:|")
    lines.append(f"| Score endret | {report.n_score_changed} |")
    lines.append(f"| Grade endret | {report.n_grade_changed} |")
    lines.append(f"| Grade promoted | {report.n_grade_promoted} |")
    lines.append(f"| Grade demoted | {report.n_grade_demoted} |")
    lines.append(f"| Published lagt til | {report.n_published_added} |")
    lines.append(f"| Published fjernet | {report.n_published_removed} |")
    lines.append(f"| Hit endret | {report.n_hit_changed} |")
    lines.append("")

    if not report.diff_rows:
        lines.append("*Ingen forskjeller å rapportere.*\n")
        return "\n".join(lines)

    lines.append(f"## Diff (første {min(len(report.diff_rows), max_rows)} rader)\n")
    lines.append(
        f"| Ref date | Kind | Score {report.label_v1} → {report.label_v2} | "
        f"Grade {report.label_v1} → {report.label_v2} | Pub | Hit |"
    )
    lines.append("|---|---|---:|---|---|---|")
    for row in report.diff_rows[:max_rows]:
        score_cell = (
            f"{_fmt_float(row.score_v1)} → {_fmt_float(row.score_v2)}"
            if row.kind == "changed"
            else (
                f"{_fmt_float(row.score_v1)} → -"
                if row.kind == "only_v1"
                else f"- → {_fmt_float(row.score_v2)}"
            )
        )
        grade_cell = (
            f"{row.grade_v1 or '-'} → {row.grade_v2 or '-'}"
            if row.kind != "only_v2"
            else f"- → {row.grade_v2 or '-'}"
        )
        pub_cell = (
            f"{_fmt_bool(row.published_v1)} → {_fmt_bool(row.published_v2)}"
            if row.kind == "changed"
            else (
                f"{_fmt_bool(row.published_v1)} → -"
                if row.kind == "only_v1"
                else f"- → {_fmt_bool(row.published_v2)}"
            )
        )
        hit_cell = (
            f"{_fmt_bool(row.hit_v1)} → {_fmt_bool(row.hit_v2)}"
            if row.kind == "changed"
            else (
                f"{_fmt_bool(row.hit_v1)} → -"
                if row.kind == "only_v1"
                else f"- → {_fmt_bool(row.hit_v2)}"
            )
        )
        lines.append(
            f"| {row.ref_date} | {row.kind} | {score_cell} | "
            f"{grade_cell} | {pub_cell} | {hit_cell} |"
        )

    if len(report.diff_rows) > max_rows:
        lines.append("")
        lines.append(
            f"*({len(report.diff_rows) - max_rows} flere rader utelatt — "
            f"bruk `format_compare_json` for full audit)*\n"
        )

    return "\n".join(lines)


def _fmt_float(v: float | None) -> str:
    return "-" if v is None else f"{v:.3f}"


def _fmt_bool(v: bool | None) -> str:
    if v is None:
        return "-"
    return "✓" if v else "✗"


def format_compare_json(report: CompareReport) -> str:
    """JSON-rendering av full CompareReport. For audit + persistens."""
    return report.model_dump_json(indent=2)
