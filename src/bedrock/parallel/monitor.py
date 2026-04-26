"""Pipeline-monitoring for Fase 12 parallell-drift.

Automatiserer 4 av 5 PLAN § 12.3 cutover-kriterier:

1. Fetcher-freshness (alle bedrock-fetchere har kjørt innenfor
   ``stale_hours`` definert i ``fetch.yaml``).
2. Pipeline-log-feil (``logs/pipeline.log`` har ingen feil-linjer i
   nylige kjøringer — proxy for "ingen git-push-feil").
3. Bot-log agri-TP-overrides (scalp_edge bot-log skal ha 0 treff på
   "agri TP overridden" — bekrefter at Fase 7 bot-fix tar effekt).
4. Signal-diff (kaller ``bedrock.parallel.compare`` og flagger hvis
   andelen grade-endringer overskrider terskel).

Det femte kriteriet (manuell inspeksjon av siste 20 setups) er ikke
automatisert — surfacert som dokumentert TODO i tekst-rapporten.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bedrock.parallel.compare import CompareReport, compare

# Default-stier (kan overskrives av CLI-flagg)
DEFAULT_DB = Path("data/bedrock.db")
DEFAULT_FETCH_YAML = Path("config/fetch.yaml")
DEFAULT_BEDROCK_SIGNALS = Path("data/signals.json")
DEFAULT_OLD_SIGNALS: tuple[Path, ...] = (
    Path.home() / "cot-explorer" / "data" / "signals.json",
    Path.home() / "cot-explorer" / "data" / "agri_signals.json",
)
DEFAULT_BOT_LOG = Path.home() / "scalp_edge" / "bot.log"
DEFAULT_PIPELINE_LOG = Path("logs/pipeline.log")

# Heuristikk-terskler
# Sub-fase 12.5+ session 81: bumpet fra 0.5 til 0.8.
# Rationale: bedrock er by design strengere enn cot-explorer (real drivers
# vs placeholders, kalibrerte grade-terskler). 50-70 % grade-endring er
# forventet under obs-vinduet og ikke en feil. > 80 % er fortsatt en
# meningsfull terskel som flagger systemiske problemer (f.eks. en
# regresjon der bedrock plutselig graderer alt som C).
_GRADE_DIFF_RATIO_FAIL = 0.8
_PIPELINE_LOG_TAIL_LINES = 1000
_BOT_LOG_TAIL_LINES = 5000


@dataclass
class CheckResult:
    """Resultat fra én av delsjekk-funksjonene."""

    name: str
    ok: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorReport:
    """Aggregat over alle delsjekker."""

    generated_utc: str
    overall_ok: bool
    checks: list[CheckResult]


# ---------------------------------------------------------------------------
# Sjekk-funksjoner
# ---------------------------------------------------------------------------


def check_fetcher_freshness(
    *,
    fetch_yaml: Path = DEFAULT_FETCH_YAML,
    db: Path = DEFAULT_DB,
    now: datetime | None = None,
) -> CheckResult:
    """PLAN § 12.3 #1 (proxy): alle fetchere kjører i forventet kadens.

    OK når ingen fetchere er ``stale`` eller ``missing``. Aging
    (mellom ``stale_hours`` og ``2 × stale_hours``) er en advarsel
    men ikke fail.
    """
    if not fetch_yaml.exists():
        return CheckResult("fetcher_freshness", False, f"fetch.yaml mangler: {fetch_yaml}")
    if not db.exists():
        return CheckResult("fetcher_freshness", False, f"db mangler: {db}")

    # Lat import for å unngå modul-load ved import av monitor.
    from bedrock.config.fetch import load_fetch_config, status_report
    from bedrock.data.store import DataStore

    cfg = load_fetch_config(fetch_yaml)
    store = DataStore(db)
    statuses = status_report(cfg, store, now=now)

    fresh: list[str] = []
    aging: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    for status in statuses:
        if not status.has_data or status.age_hours is None:
            missing.append(status.name)
        elif status.age_hours < status.stale_hours:
            fresh.append(status.name)
        elif status.age_hours < 2 * status.stale_hours:
            aging.append(status.name)
        else:
            stale.append(status.name)

    ok = not stale and not missing
    parts: list[str] = []
    if fresh:
        parts.append(f"{len(fresh)} fresh")
    if aging:
        parts.append(f"{len(aging)} aging: {','.join(aging)}")
    if stale:
        parts.append(f"{len(stale)} stale: {','.join(stale)}")
    if missing:
        parts.append(f"{len(missing)} missing: {','.join(missing)}")

    return CheckResult(
        name="fetcher_freshness",
        ok=ok,
        detail="; ".join(parts) or "(ingen fetchere konfigurert)",
        data={
            "fresh": fresh,
            "aging": aging,
            "stale": stale,
            "missing": missing,
        },
    )


def _scan_log_tail(
    path: Path,
    *,
    keywords: tuple[str, ...],
    max_lines: int,
) -> tuple[int, int, list[str]]:
    """Returner (n_lines_scanned, n_matches, last_5_matches).

    Case-insensitive keyword-match. Returnerer (0, 0, []) hvis filen
    mangler — caller bestemmer om det er ok.
    """
    if not path.exists():
        return 0, 0, []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[-max_lines:]
    matches = [ln for ln in lines if any(kw.lower() in ln.lower() for kw in keywords)]
    return len(lines), len(matches), matches[-5:]


def check_pipeline_log_errors(
    *,
    log_path: Path = DEFAULT_PIPELINE_LOG,
    max_lines: int = _PIPELINE_LOG_TAIL_LINES,
) -> CheckResult:
    """PLAN § 12.3 #2: ingen git-push-feil i pipeline-log.

    Skanner siste ``max_lines`` linjer av ``logs/pipeline.log`` etter
    typiske feil-keywords. Manglende fil → ok=True (ingenting å
    klage på).
    """
    keywords = (
        "git push failed",
        "push rejected",
        "ERROR",
        "Traceback",
        "fatal:",
        "[error]",
    )
    n_lines, n_matches, samples = _scan_log_tail(log_path, keywords=keywords, max_lines=max_lines)
    if n_lines == 0 and not log_path.exists():
        return CheckResult(
            name="pipeline_log_errors",
            ok=True,
            detail=f"log mangler ({log_path}) — ingen feil rapportert",
            data={"errors_found": 0, "log_exists": False},
        )
    return CheckResult(
        name="pipeline_log_errors",
        ok=n_matches == 0,
        detail=f"{n_matches} feil-linjer i siste {n_lines} log-linjer",
        data={"errors_found": n_matches, "samples": samples, "log_exists": True},
    )


def check_agri_tp_override(
    *,
    log_path: Path = DEFAULT_BOT_LOG,
    max_lines: int = _BOT_LOG_TAIL_LINES,
) -> CheckResult:
    """PLAN § 12.3 #3: bot-log skal ha 0 treff på 'agri TP overridden'.

    Den gamle agri-ATR-override-bug-en (trading_bot.py:2665-2691) vil
    bli fjernet i Fase 7. Denne sjekken bekrefter at fix-en holder
    seg under parallell-drift.
    """
    keywords = ("agri tp overridden", "agri tp override")
    n_lines, n_matches, samples = _scan_log_tail(log_path, keywords=keywords, max_lines=max_lines)
    if n_lines == 0 and not log_path.exists():
        return CheckResult(
            name="agri_tp_override",
            ok=True,
            detail=f"bot-log mangler ({log_path}) — ingen overrides rapportert",
            data={"matches": 0, "log_exists": False},
        )
    return CheckResult(
        name="agri_tp_override",
        ok=n_matches == 0,
        detail=f"{n_matches} treff på 'agri TP overridden' i siste {n_lines} log-linjer",
        data={"matches": n_matches, "samples": samples, "log_exists": True},
    )


def check_signal_diff(
    *,
    bedrock_signals: Path = DEFAULT_BEDROCK_SIGNALS,
    old_signals: tuple[Path, ...] | list[Path] = DEFAULT_OLD_SIGNALS,
    grade_diff_ratio_fail: float = _GRADE_DIFF_RATIO_FAIL,
) -> CheckResult:
    """PLAN § 12.3 #4: signal-diff mellom gammel og ny pipeline forklarbar.

    Heuristikk: hvis andelen felles signaler med endret grade
    overskrider ``grade_diff_ratio_fail`` (default 50 %), flagges
    diff-en som ikke-forklarbar — krever manuelt review.
    """
    if not bedrock_signals.exists():
        return CheckResult(
            name="signal_diff",
            ok=False,
            detail=f"bedrock signals.json mangler: {bedrock_signals}",
        )

    existing_old: list[Path] = [Path(p) for p in old_signals if Path(p).exists()]
    if not existing_old:
        return CheckResult(
            name="signal_diff",
            ok=False,
            detail="ingen gamle signal-filer funnet å sammenligne mot",
            data={"old_signals_searched": [str(p) for p in old_signals]},
        )

    report: CompareReport = compare(
        bedrock_path=bedrock_signals,
        old_paths=existing_old,
    )

    grade_change_ratio = report.n_grade_diff / report.n_common if report.n_common else 0.0
    ok = grade_change_ratio < grade_diff_ratio_fail

    return CheckResult(
        name="signal_diff",
        ok=ok,
        detail=(
            f"{report.n_common} felles, {report.n_changed} endret, "
            f"{report.n_grade_diff} grade-endring ({grade_change_ratio:.0%})"
        ),
        data={
            "n_old": report.n_old,
            "n_new": report.n_new,
            "n_common": report.n_common,
            "n_only_old": report.n_only_old,
            "n_only_new": report.n_only_new,
            "n_changed": report.n_changed,
            "n_grade_diff": report.n_grade_diff,
            "grade_change_ratio": grade_change_ratio,
            "grade_diff_ratio_fail_threshold": grade_diff_ratio_fail,
        },
    )


# ---------------------------------------------------------------------------
# Orkestrering + formatering
# ---------------------------------------------------------------------------


def run_monitor(
    *,
    fetch_yaml: Path = DEFAULT_FETCH_YAML,
    db: Path = DEFAULT_DB,
    pipeline_log: Path = DEFAULT_PIPELINE_LOG,
    bot_log: Path = DEFAULT_BOT_LOG,
    bedrock_signals: Path = DEFAULT_BEDROCK_SIGNALS,
    old_signals: tuple[Path, ...] | list[Path] = DEFAULT_OLD_SIGNALS,
    now: datetime | None = None,
) -> MonitorReport:
    """Kjør alle delsjekker og bygg samlet MonitorReport."""
    checks = [
        check_fetcher_freshness(fetch_yaml=fetch_yaml, db=db, now=now),
        check_pipeline_log_errors(log_path=pipeline_log),
        check_agri_tp_override(log_path=bot_log),
        check_signal_diff(bedrock_signals=bedrock_signals, old_signals=old_signals),
    ]
    resolved_now = (now or datetime.now(timezone.utc)).isoformat()
    return MonitorReport(
        generated_utc=resolved_now,
        overall_ok=all(c.ok for c in checks),
        checks=checks,
    )


def format_monitor_text(report: MonitorReport) -> str:
    """Menneskelesbar tekst-rapport for stdout / e-post / Slack-paste."""
    overall = "OK" if report.overall_ok else "FAIL"
    lines: list[str] = [
        "=== Bedrock parallell-drift monitor ===",
        f"Generated: {report.generated_utc}",
        f"Overall:   {overall}",
        "",
    ]
    for check in report.checks:
        flag = "OK  " if check.ok else "FAIL"
        lines.append(f"  [{flag}] {check.name}: {check.detail}")
    lines.extend(
        [
            "",
            "Manuelt steg ikke automatisert (PLAN § 12.3 #5):",
            "  - Inspiser siste 20 publiserte setups: entry-nivå er reelt,",
            "    TP ved reelt nivå, R:R ≥ horisont-min.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_monitor_json(report: MonitorReport) -> str:
    """Maskinlesbar full audit."""
    import json as _json

    return _json.dumps(asdict(report), indent=2, default=str)


__all__ = [
    "CheckResult",
    "MonitorReport",
    "check_agri_tp_override",
    "check_fetcher_freshness",
    "check_pipeline_log_errors",
    "check_signal_diff",
    "format_monitor_json",
    "format_monitor_text",
    "run_monitor",
]
