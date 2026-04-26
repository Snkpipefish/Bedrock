"""Sammenlign bedrock signals.json mot cot-explorer signals-filer.

Kalt daglig under Fase 12 parallell-drift (PLAN § 12.1) for å verifisere
at den nye pipelinen produserer signaler som er forklarbar mot den
gamle. Skriptet er pure: tar inn fil-stier, returnerer en
``CompareReport`` som kan formatteres som markdown eller JSON.

Schema-håndtering:

- Bedrock signals.json: ``list[SignalEntry]`` med felter
  ``instrument`` / ``direction`` / ``horizon`` (lowercase) / ``score`` /
  ``max_score`` / ``grade`` / ``setup.setup.{entry,sl,tp,rr}``.
- Cot-explorer signals.json + agri_signals.json: dict med
  ``signals: [{key,name,action,timeframe|horizon,grade,score,max_score,
  entry,sl,t1,t2,...}]``. ``action`` er uppercase BUY/SELL,
  ``timeframe``/``horizon`` er uppercase MAKRO/SWING/SCALP.

Join-nøkkel: ``(instrument_lower, horizon_lower, direction_lower)``.
Mismatched navn (f.eks. "Cotton" vs "Bomull") ender opp som
``only_old``/``only_new`` — manuelt review fanger oversetting.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GRADE_RANK: dict[str | None, int] = {
    "A+": 0,
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    None: 99,
}

# Toleranser
_SCORE_PCT_TOL = 0.05  # 5 prosentpoeng på normalisert score
_PRICE_REL_TOL = 1e-3  # 0.1 % på pris-felter (entry/sl)


@dataclass(frozen=True)
class NormalizedSignal:
    """Felles representasjon for sammenligning på tvers av schema-versjoner."""

    instrument: str  # lowercase
    horizon: str  # lowercase
    direction: str  # lowercase
    grade: str | None
    score: float
    max_score: float
    entry: float | None
    sl: float | None
    source: str  # "bedrock" | "old"


@dataclass
class DiffEntry:
    """En linje i diff-tabellen."""

    instrument: str
    horizon: str
    direction: str
    kind: str  # only_old | only_new | changed | unchanged
    old: NormalizedSignal | None = None
    new: NormalizedSignal | None = None
    changed_fields: list[str] = field(default_factory=list)


@dataclass
class CompareReport:
    """Aggregert resultat + per-signal diff-tabell."""

    generated_utc: str
    bedrock_path: str
    old_paths: list[str]
    n_old: int
    n_new: int
    n_common: int
    n_only_old: int
    n_only_new: int
    n_changed: int
    n_grade_diff: int
    diff: list[DiffEntry]


# ---------------------------------------------------------------------------
# Normalisering
# ---------------------------------------------------------------------------


def _norm_str(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_bedrock(item: dict[str, Any]) -> NormalizedSignal:
    """Konverter en SignalEntry-dict (bedrock signals.json) til NormalizedSignal."""
    setup_outer = item.get("setup") or {}
    setup_inner = setup_outer.get("setup") if isinstance(setup_outer, dict) else None
    setup_dict = setup_inner if isinstance(setup_inner, dict) else {}

    return NormalizedSignal(
        instrument=_norm_str(item.get("instrument")),
        horizon=_norm_str(item.get("horizon")),
        direction=_norm_str(item.get("direction")),
        grade=item.get("grade"),
        score=_safe_float(item.get("score")),
        max_score=_safe_float(item.get("max_score")),
        entry=_safe_optional_float(setup_dict.get("entry")),
        sl=_safe_optional_float(setup_dict.get("sl")),
        source="bedrock",
    )


def normalize_old(item: dict[str, Any]) -> list[NormalizedSignal]:
    """Konverter en cot-explorer signal-dict til en eller flere NormalizedSignals.

    Cot-explorer's instrument-feltet er inkonsistent:
    - Agri: ``key="Coffee"``, ``name="Kaffe"`` — match via key
    - Financial: ``key="NAS100"``, ``name="Nasdaq"`` — match via name

    For å matche begge mønstre returnerer vi en NormalizedSignal per
    tilgjengelig kandidat (key og name). Compare-logikken bygger
    map-en og overskriver duplikater — alle kandidater matches mot
    bedrock-id-en.
    """
    horizon_raw = item.get("horizon") or item.get("timeframe") or ""
    candidates: list[str] = []
    seen: set[str] = set()
    for fname in ("key", "name"):
        v = item.get(fname)
        if v and isinstance(v, str) and v.strip():
            normalized = _norm_str(v)
            if normalized not in seen:
                seen.add(normalized)
                candidates.append(v.strip())
    if not candidates:
        candidates = [""]

    return [
        NormalizedSignal(
            instrument=_norm_str(name),
            horizon=_norm_str(horizon_raw),
            direction=_norm_str(item.get("action")),
            grade=item.get("grade"),
            score=_safe_float(item.get("score")),
            max_score=_safe_float(item.get("max_score")),
            entry=_safe_optional_float(item.get("entry")),
            sl=_safe_optional_float(item.get("sl")),
            source="old",
        )
        for name in candidates
    ]


# ---------------------------------------------------------------------------
# Lasting
# ---------------------------------------------------------------------------


def load_bedrock_signals(path: Path) -> list[NormalizedSignal]:
    """Les bedrock signals.json. Returnerer tom liste hvis fil mangler."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"forventet liste i {path}, fikk {type(raw).__name__}")
    return [normalize_bedrock(item) for item in raw if isinstance(item, dict)]


def load_old_signals(path: Path) -> list[NormalizedSignal]:
    """Les cot-explorer signals.json eller agri_signals.json.

    Begge filene har struktur ``{"signals": [...]}``. Returnerer tom
    liste hvis fil mangler eller har uventet struktur.
    """
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        signals = raw.get("signals") or []
    elif isinstance(raw, list):
        signals = raw
    else:
        return []
    out: list[NormalizedSignal] = []
    for item in signals:
        if isinstance(item, dict):
            out.extend(normalize_old(item))
    return out


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _key(signal: NormalizedSignal) -> tuple[str, str, str]:
    return (signal.instrument, signal.horizon, signal.direction)


def _close(a: float | None, b: float | None, *, rel_tol: float = _PRICE_REL_TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale < rel_tol


def _score_pct(signal: NormalizedSignal) -> float:
    if signal.max_score <= 0:
        return 0.0
    return signal.score / signal.max_score


def _diff_signals(old: NormalizedSignal, new: NormalizedSignal) -> list[str]:
    """Returner liste over felter som er endret mellom old og new."""
    changes: list[str] = []
    if old.grade != new.grade:
        changes.append("grade")
    if abs(_score_pct(old) - _score_pct(new)) > _SCORE_PCT_TOL:
        changes.append("score_pct")
    if not _close(old.entry, new.entry):
        changes.append("entry")
    if not _close(old.sl, new.sl):
        changes.append("sl")
    return changes


def compare(
    *,
    bedrock_path: Path,
    old_paths: list[Path],
    now: datetime | None = None,
) -> CompareReport:
    """Bygg CompareReport ved å diff-e bedrock signals mot gamle signal-filer.

    ``old_paths`` kan være flere filer; signalene unioniseres på
    join-nøkkel før sammenligning. Hvis samme nøkkel finnes i flere
    gamle filer, vinner siste fil i lista (sjelden i praksis siden
    signals.json + agri_signals.json har disjoint instrumenter).
    """
    bedrock = load_bedrock_signals(bedrock_path)

    old: list[NormalizedSignal] = []
    for path in old_paths:
        old.extend(load_old_signals(path))

    bedrock_map: dict[tuple[str, str, str], NormalizedSignal] = {_key(s): s for s in bedrock}
    old_map: dict[tuple[str, str, str], NormalizedSignal] = {_key(s): s for s in old}

    diff: list[DiffEntry] = []
    n_changed = 0
    n_grade_diff = 0

    all_keys = sorted(set(bedrock_map) | set(old_map))
    for key in all_keys:
        instr, horizon, direction = key
        in_old = key in old_map
        in_new = key in bedrock_map
        if in_old and not in_new:
            diff.append(
                DiffEntry(
                    instrument=instr,
                    horizon=horizon,
                    direction=direction,
                    kind="only_old",
                    old=old_map[key],
                )
            )
        elif in_new and not in_old:
            diff.append(
                DiffEntry(
                    instrument=instr,
                    horizon=horizon,
                    direction=direction,
                    kind="only_new",
                    new=bedrock_map[key],
                )
            )
        else:
            changes = _diff_signals(old_map[key], bedrock_map[key])
            kind = "changed" if changes else "unchanged"
            if changes:
                n_changed += 1
                if "grade" in changes:
                    n_grade_diff += 1
            diff.append(
                DiffEntry(
                    instrument=instr,
                    horizon=horizon,
                    direction=direction,
                    kind=kind,
                    old=old_map[key],
                    new=bedrock_map[key],
                    changed_fields=changes,
                )
            )

    n_only_old = sum(1 for d in diff if d.kind == "only_old")
    n_only_new = sum(1 for d in diff if d.kind == "only_new")
    resolved_now = (now or datetime.now(timezone.utc)).isoformat()

    return CompareReport(
        generated_utc=resolved_now,
        bedrock_path=str(bedrock_path),
        old_paths=[str(p) for p in old_paths],
        n_old=len(old),
        n_new=len(bedrock),
        n_common=len(set(bedrock_map) & set(old_map)),
        n_only_old=n_only_old,
        n_only_new=n_only_new,
        n_changed=n_changed,
        n_grade_diff=n_grade_diff,
        diff=diff,
    )


# ---------------------------------------------------------------------------
# Formatering
# ---------------------------------------------------------------------------


def _grade_str(signal: NormalizedSignal | None) -> str:
    if signal is None or signal.grade is None:
        return "-"
    return str(signal.grade)


def _score_pct_str(signal: NormalizedSignal | None) -> str:
    if signal is None or signal.max_score <= 0:
        return "-"
    return f"{_score_pct(signal):.0%}"


def format_compare_markdown(report: CompareReport, *, max_rows: int = 100) -> str:
    """Bygg menneskelesbar markdown-rapport.

    ``max_rows`` capper antall diff-rader (excluding ``unchanged``).
    Resten utelates med en oppsummerende linje.
    """
    lines: list[str] = [
        "# Signal-diff — bedrock vs cot-explorer",
        "",
        f"- **Generated:** {report.generated_utc}",
        f"- **Bedrock:** `{report.bedrock_path}` ({report.n_new} signals)",
        f"- **Gamle filer:** {' + '.join(f'`{p}`' for p in report.old_paths)} "
        f"({report.n_old} signals totalt)",
        "",
        "## Sammendrag",
        "",
        "| Kategori | Antall |",
        "|---|---:|",
        f"| Felles (instrument+horizon+direction) | {report.n_common} |",
        f"| Kun gammel | {report.n_only_old} |",
        f"| Kun bedrock | {report.n_only_new} |",
        f"| Endret | {report.n_changed} |",
        f"| Grade-endring | {report.n_grade_diff} |",
        "",
        "## Diff",
        "",
        "| Instrument | Horizon | Dir | Kind | Old grade | New grade "
        "| Old score% | New score% | Endrede felter |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]

    relevant = [d for d in report.diff if d.kind != "unchanged"]
    truncated = len(relevant) > max_rows
    for d in relevant[:max_rows]:
        fields = ",".join(d.changed_fields) if d.changed_fields else "-"
        lines.append(
            f"| {d.instrument} | {d.horizon} | {d.direction} | {d.kind} | "
            f"{_grade_str(d.old)} | {_grade_str(d.new)} | "
            f"{_score_pct_str(d.old)} | {_score_pct_str(d.new)} | {fields} |"
        )

    if not relevant:
        lines.append("| _(ingen endringer)_ | | | | | | | | |")
    if truncated:
        lines.append("")
        lines.append(
            f"_({len(relevant) - max_rows} flere rader utelatt; øk `--max-rows` for å se alle)_"
        )

    return "\n".join(lines) + "\n"


def format_compare_json(report: CompareReport) -> str:
    """Komplett audit-trail som JSON. Brukes av monitor-script."""
    return json.dumps(asdict(report), indent=2, default=str)


__all__ = [
    "CompareReport",
    "DiffEntry",
    "NormalizedSignal",
    "compare",
    "format_compare_json",
    "format_compare_markdown",
    "load_bedrock_signals",
    "load_old_signals",
    "normalize_bedrock",
    "normalize_old",
]
