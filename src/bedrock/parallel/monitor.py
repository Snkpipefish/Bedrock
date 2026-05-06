"""Pipeline-monitoring for Fase 12 parallell-drift.

Automatiserer 3 av 5 PLAN § 12.3 cutover-kriterier:

1. Fetcher-freshness (alle bedrock-fetchere har kjørt innenfor
   ``stale_hours`` definert i ``fetch.yaml``).
2. Pipeline-log-feil (``logs/pipeline.log`` har ingen feil-linjer i
   nylige kjøringer — proxy for "ingen git-push-feil").
3. Bot-log agri-TP-overrides (scalp_edge bot-log skal ha 0 treff på
   "agri TP overridden" — bekrefter at Fase 7 bot-fix tar effekt).

Tidligere 4. punkt (signal-diff mot cot-explorer) ble fjernet i
sub-fase 12.9 follow-up: parallel-drift er over og bedrock + cot-explorer
deler fortsatt noe infrastruktur, så diffen ga falske alarmer uten
operasjonell verdi. Modulen ``bedrock.parallel.compare`` består og brukes
fortsatt av ``scripts/compare_signals_daily.py`` for ad-hoc-bruk.

Det femte kriteriet (manuell inspeksjon av siste 20 setups) er ikke
automatisert — surfacert som dokumentert TODO i tekst-rapporten.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default-stier (kan overskrives av CLI-flagg)
DEFAULT_DB = Path("data/bedrock.db")
DEFAULT_FETCH_YAML = Path("config/fetch.yaml")
DEFAULT_BOT_LOG = Path.home() / "scalp_edge" / "bot.log"
DEFAULT_PIPELINE_LOG = Path("logs/pipeline.log")

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


# ---------------------------------------------------------------------------
# Orkestrering + formatering
# ---------------------------------------------------------------------------


def run_monitor(
    *,
    fetch_yaml: Path = DEFAULT_FETCH_YAML,
    db: Path = DEFAULT_DB,
    pipeline_log: Path = DEFAULT_PIPELINE_LOG,
    bot_log: Path = DEFAULT_BOT_LOG,
    now: datetime | None = None,
) -> MonitorReport:
    """Kjør alle delsjekker og bygg samlet MonitorReport."""
    checks = [
        check_fetcher_freshness(fetch_yaml=fetch_yaml, db=db, now=now),
        check_pipeline_log_errors(log_path=pipeline_log),
        check_agri_tp_override(log_path=bot_log),
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
    "format_monitor_json",
    "format_monitor_text",
    "run_monitor",
]
