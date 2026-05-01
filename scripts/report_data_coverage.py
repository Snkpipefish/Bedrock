"""Data-coverage-rapport per (instrument × horisont) — sub-fase 12.8 Sub-task A1.

Genererer Markdown-rapport som per-instrument viser:

1. **Sammendragstabell 1 — per-horisont-coverage** (M / S / Sc): én rad per
   instrument, ✓ / ⚠ / ✗ basert på primærkilder for hver horisont per
   PLAN § 20.2-mapping.
2. **Sammendragstabell 2 — per-kilde-helse**: én rad per fetcher, cron-tid,
   sist oppdatert (DB-rad-MAX), helse-flagg basert på cycle-buffer per
   PLAN § 20.4.
3. **Drill-down per instrument**: tabell med rader/tidsspenn/sist-oppdatert
   per data-kategori, + per-horisont-vurdering.

Helse-cycles per PLAN § 20.4:

| Cycle           | Forventet refresh | Aging-buffer | Rødt hvis    |
|-----------------|-------------------|--------------|--------------|
| Daglig          | 24t               | +12t         | siste rad >36t |
| Ukentlig        | 7d                | +2d          | siste rad >9d  |
| Månedlig        | 30d               | +10d         | siste rad >40d |
| Halvmånedlig    | 14d               | +6d          | siste rad >20d |
| Event-basert    | varierer          | —            | ingen ny rad >7d |

Per-horisont-kvalifisering per § 20.2-mapping:

- **Macro**: COT-percentiler ferske + FRED-relevant ferske + structurals ferske
- **Swing**: weekly-release-cycle for asset-klassen fungerende
- **Scalp**: calendar_ff forecast-felt populert + asset-relevante real-time-detektorer

Bruk:

    PYTHONPATH=src .venv/bin/python scripts/report_data_coverage.py
        [--db data/bedrock.db]
        [--out docs/data_coverage_<date>.md]
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bedrock.config.fetch import load_fetch_config
from bedrock.config.instruments import load_instrument_config

UTC = timezone.utc

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENTS_DIR = REPO_ROOT / "config" / "instruments"
DEFAULT_DB = REPO_ROOT / "data" / "bedrock.db"
DEFAULT_OUT = REPO_ROOT / "docs" / f"data_coverage_{date.today().isoformat()}.md"

# ---------------------------------------------------------------------------
# Cycle-mapping per fetcher (PLAN § 20.4 + fetch.yaml-praksis)
# ---------------------------------------------------------------------------

# Format: fetcher_name → ("cycle_label", red_threshold_hours)
# For business-day-aware fetchere brukes business_days (M-F) i stedet for
# wallclock-timer; se BUSINESS_DAY_FETCHERS-settet.
#
# Ukentlig-tersklene er 11d (ikke 9d) for å gi buffer fra publish-dato +
# 7 dager til neste publish-dato. CFTC publiserer fredag 15:30 ET (= fre
# 21:30 Oslo) for tirsdag-snapshot; bedrock-cron fyrer fre 22:00 Oslo.
# Med 11d-terskel forblir flagget ✓ frem til neste mandag morgen.
CYCLE_PER_FETCHER: dict[str, tuple[str, float]] = {
    "prices": ("Daglig (M-F)", 36),
    "cot_disaggregated": ("Ukentlig (fre)", 11 * 24),
    "cot_legacy": ("Ukentlig (fre)", 11 * 24),
    "cot_ice": ("Ukentlig (fre)", 11 * 24),
    "cot_euronext": ("Ukentlig (ons)", 11 * 24),
    "fundamentals": ("Daglig (M-F, T+1 publisering)", 36),
    "weather": ("Daglig", 36),
    "enso": ("Månedlig", 40 * 24),
    "wasde": ("Månedlig", 40 * 24),
    "crop_progress": ("Ukentlig (sesong apr-nov)", 11 * 24),
    "shipping": ("Daglig (M-F)", 4 * 24),
    "calendar_ff": ("12t (intra-day)", 30),
    "eia_inventories": ("Ukentlig (ons)", 11 * 24),
    "comex": ("Daglig (M-F)", 4 * 24),
    "seismic": ("Daglig (event-basert)", 7 * 24),
    "conab": ("Månedlig", 40 * 24),
    "unica": ("Halvmånedlig", 20 * 24),
    "news_intel": ("12t (intra-day)", 30),
    "crypto_sentiment": ("Daglig", 36),
}

# Fetchere som har sesong-ekskludering (off-season → ⚠ ikke ✗)
SEASONAL_FETCHERS = {"crop_progress"}

# Fetchere som publiserer kun forretningsdager (M-F) — aging mål mot
# siste forretnings-dag, ikke wallclock-timer. FRED-data er T+1 fra
# US-børs-close, så fredag-rad er siste tilgjengelig fra fredag morgen
# norsk tid frem til lørdag tidlig.
BUSINESS_DAY_FETCHERS = {"prices", "fundamentals", "comex", "shipping"}

# ---------------------------------------------------------------------------
# Per-asset-klasse horisont-mapping (PLAN § 20.2)
# ---------------------------------------------------------------------------

# Per asset-klasse: liste over fetchere som er primær for hver horisont.
# "primær" = ●●● i § 20.2-tabellen (ikke sekundær eller marginal).
# Coverage = ✓ hvis ALLE primære er ferske; ⚠ hvis 1-2 svikter; ✗ hvis flere svikter.

PRIMARY_PER_HORIZON: dict[str, dict[str, list[str]]] = {
    # asset_class → horisont → fetchere
    "metals": {
        "M": ["prices", "cot_disaggregated", "fundamentals", "comex"],
        "S": ["prices", "cot_disaggregated", "comex", "calendar_ff"],
        "Sc": ["calendar_ff", "seismic"],  # seismic = real-time mining-trigger
    },
    "energy": {
        "M": ["prices", "cot_disaggregated", "fundamentals", "eia_inventories"],
        "S": ["prices", "cot_disaggregated", "eia_inventories", "calendar_ff"],
        "Sc": ["calendar_ff", "eia_inventories"],  # ons EIA-event er kjerne
    },
    "indices": {
        "M": ["prices", "cot_legacy", "fundamentals"],  # B1 inputs i fundamentals
        "S": ["prices", "cot_legacy", "fundamentals", "calendar_ff"],
        "Sc": ["calendar_ff"],
    },
    "fx": {
        "M": ["prices", "cot_legacy", "fundamentals"],  # yield-diff fra FRED
        "S": ["prices", "cot_legacy", "calendar_ff"],
        "Sc": ["calendar_ff"],
    },
    "crypto": {
        "M": ["prices", "fundamentals", "crypto_sentiment"],  # F&G regime
        "S": ["prices", "calendar_ff", "crypto_sentiment"],
        "Sc": ["calendar_ff"],
    },
    "grains": {
        "M": [
            "prices",
            "cot_disaggregated",
            "wasde",
            "crop_progress",
            "weather",
            "shipping",
        ],
        "S": [
            "prices",
            "cot_disaggregated",
            "wasde",
            "crop_progress",
            "weather",
            "calendar_ff",
        ],
        "Sc": ["calendar_ff", "wasde"],  # WASDE-release-event
    },
    "softs": {
        "M": [
            "prices",
            "cot_disaggregated",
            "conab",
            "unica",
            "weather",
            "shipping",
        ],
        "S": [
            "prices",
            "cot_disaggregated",
            "conab",
            "unica",
            "weather",
            "calendar_ff",
        ],
        "Sc": ["calendar_ff", "unica"],
    },
}


# Instrument-spesifikke overrides (e.g. softs som bruker BRL/Coffee/Sugar-spesifikt)
# Ikke alle softs trenger UNICA (kun Sugar); ikke alle softs trenger CONAB Café (kun Coffee).
PER_INSTRUMENT_OVERRIDE: dict[str, dict[str, list[str]]] = {
    # SP500/Nasdaq har AAII-input via fundamentals (NFCI etc) men ikke kart aaii_sentiment-tabell
    # — fanges via fundamentals-fetcher.
    # Cocoa har ingen UNICA/CONAB Café-data; faller tilbake på softs-default uten unica.
    "Cocoa": {
        "M": ["prices", "cot_disaggregated", "weather", "shipping"],
        "S": ["prices", "cot_disaggregated", "weather", "calendar_ff"],
        "Sc": ["calendar_ff"],
    },
    "Coffee": {
        "M": ["prices", "cot_disaggregated", "conab", "weather", "shipping"],
        "S": ["prices", "cot_disaggregated", "conab", "weather", "calendar_ff"],
        "Sc": ["calendar_ff"],
    },
    "Cotton": {
        "M": ["prices", "cot_disaggregated", "wasde", "weather", "shipping"],
        "S": ["prices", "cot_disaggregated", "wasde", "weather", "calendar_ff"],
        "Sc": ["calendar_ff", "wasde"],
    },
    # ETH/BTC: F&G + calendar_ff
    "ETH": {
        "M": ["prices", "fundamentals", "crypto_sentiment"],
        "S": ["prices", "calendar_ff", "crypto_sentiment"],
        "Sc": ["calendar_ff"],
    },
    "BTC": {
        "M": ["prices", "fundamentals", "crypto_sentiment"],
        "S": ["prices", "calendar_ff", "crypto_sentiment"],
        "Sc": ["calendar_ff"],
    },
}


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------


@dataclass
class FetcherHealth:
    name: str
    cycle_label: str
    cron: str
    table: str
    last_observation: datetime | None
    rows: int
    age_hours: float | None
    status: str  # "✓" | "⚠" | "✗"
    systemd_last_run: datetime | None
    systemd_status: str  # "active" | "failed" | "inactive" | "missing"


@dataclass
class InstrumentCoverage:
    inst_id: str
    asset_class: str
    horizon_status: dict[str, str]  # "M"|"S"|"Sc" → "✓"|"⚠"|"✗"
    primary_fetchers: dict[str, list[str]]
    fetcher_health_per_horizon: dict[str, list[tuple[str, str]]]  # horisont → [(fetcher, status)]


# ---------------------------------------------------------------------------
# DB / systemd helpers
# ---------------------------------------------------------------------------


def _query_table_state(
    con: sqlite3.Connection, table: str, ts_column: str
) -> tuple[int, datetime | None]:
    """Returner (row_count, latest_ts) for én tabell."""
    cur = con.cursor()
    try:
        cur.execute(f'SELECT COUNT(*), MAX("{ts_column}") FROM "{table}"')
        row = cur.fetchone()
    except sqlite3.OperationalError:
        return 0, None
    n = row[0]
    raw = row[1]
    if raw is None:
        return n, None
    # Parse various timestamp formats
    parsed = _parse_ts(raw)
    return n, parsed


def _parse_ts(raw: Any) -> datetime | None:
    """Parse timestamp fra ulike SQLite-formater til UTC datetime."""
    if raw is None:
        return None
    s = str(raw).strip()
    # Forex Factory event_ts har timezone i form "2026-04-30T14:30:00+00:00"
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    # Som fallback: forsøk fromisoformat
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def _query_systemd(fetcher: str) -> tuple[datetime | None, str]:
    """Spør systemctl om timer-status. Returnerer (last_run, status_label).

    Sjekker både system- og user-timere. Lite robust — feil → ("missing").
    """
    timer_unit = f"bedrock-fetch-{fetcher}.timer"
    service_unit = f"bedrock-fetch-{fetcher}.service"

    last_run: datetime | None = None
    status_label = "missing"

    for scope in ("--user", "--system"):
        try:
            # Sjekk om timer eksisterer
            res = subprocess.run(
                [
                    "systemctl",
                    scope,
                    "show",
                    timer_unit,
                    "--property=LastTriggerUSec,Result,ActiveState",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = res.stdout
            if not out.strip() or "LoadError" in out:
                continue

            # Parse properties
            props: dict[str, str] = {}
            for line in out.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    props[k.strip()] = v.strip()

            last_us = props.get("LastTriggerUSec", "")
            if last_us and last_us not in ("0", "n/a"):
                # Format eks: "Fri 2026-05-01 06:15:15 CEST"
                try:
                    last_dt = datetime.strptime(last_us, "%a %Y-%m-%d %H:%M:%S %Z")
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=UTC)
                    last_run = last_dt
                except ValueError:
                    pass

            # Sjekk service-result
            res2 = subprocess.run(
                ["systemctl", scope, "show", service_unit, "--property=Result,ActiveState"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in res2.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "Result":
                        if v.strip() == "success":
                            status_label = "active"
                        elif v.strip() == "failed":
                            status_label = "failed"
                        elif v.strip() == "":
                            # Service har ikke kjørt enda
                            status_label = "inactive"
                        else:
                            status_label = v.strip()
            break  # første hit vinner
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return last_run, status_label


# ---------------------------------------------------------------------------
# Health-flag-logikk
# ---------------------------------------------------------------------------


def _last_business_day(now: datetime) -> datetime:
    """Forrige forretnings-dag (M-F) før `now`. Inkluderer dagens dato hvis M-F."""
    cur = now.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur.weekday() > 4:  # 5=Sat, 6=Sun
        cur = (
            cur.replace(day=cur.day - 1)
            if cur.day > 1
            else cur.replace(month=cur.month - 1, day=28)
        )
    return cur


def _classify_health(
    fetcher: str,
    last_obs: datetime | None,
    rows: int,
    now: datetime,
) -> tuple[str, float | None]:
    """Returner (status_flag, age_hours_or_None) for én fetcher.

    Business-day-aware: BUSINESS_DAY_FETCHERS måles mot siste M-F-dag
    før `now` istedenfor mot wallclock-now. Dette unngår at en fredag-
    rad flagges stale på en mandag morgen før ny fyring har skjedd.
    """
    if last_obs is None or rows == 0:
        return "✗", None

    if fetcher in BUSINESS_DAY_FETCHERS:
        # Mål alder mot siste forretnings-dag (00:00 UTC) som er det
        # eldste vi forventer å ha rad for.
        ref = _last_business_day(now)
        # Hvis fetcheren publiserer T+1 (FRED), så aksepterer vi at
        # siste rad er fra forrige forretnings-dag før ref.
        # Bruker wallclock-alder hvis last_obs >= ref (fersk i dag),
        # ellers wallclock-alder fra ref-dato.
        if last_obs >= ref:
            age_hours = (now - last_obs).total_seconds() / 3600
        else:
            age_hours = (ref - last_obs).total_seconds() / 3600
    else:
        age_hours = (now - last_obs).total_seconds() / 3600

    cycle, red_threshold = CYCLE_PER_FETCHER.get(fetcher, ("Ukjent", 24))
    yellow_threshold = red_threshold * 0.7

    if fetcher in SEASONAL_FETCHERS:
        month = now.month
        if month not in range(4, 12):
            if age_hours > red_threshold:
                return "⚠", age_hours
            return "✓", age_hours

    if age_hours > red_threshold:
        return "✗", age_hours
    if age_hours > yellow_threshold:
        return "⚠", age_hours
    return "✓", age_hours


def _aggregate_horizon_status(
    primary_fetchers: list[str], health_map: dict[str, FetcherHealth]
) -> tuple[str, list[tuple[str, str]]]:
    """Aggregér per-fetcher-status til én horisont-status.

    Regel:
    - Alle primærkilder ✓ → ✓
    - 1 svikt (⚠ eller ✗) → ⚠
    - 2+ svikt → ✗
    """
    statuses: list[tuple[str, str]] = []
    fail_count = 0
    for f in primary_fetchers:
        h = health_map.get(f)
        if h is None:
            statuses.append((f, "✗ (mangler)"))
            fail_count += 1
            continue
        statuses.append((f, h.status))
        if h.status != "✓":
            fail_count += 1
    if fail_count == 0:
        return "✓", statuses
    if fail_count == 1:
        return "⚠", statuses
    return "✗", statuses


# ---------------------------------------------------------------------------
# Build coverage
# ---------------------------------------------------------------------------


def _resolve_primary(inst_id: str, asset_class: str) -> dict[str, list[str]]:
    """Per-instrument override hvis registrert, ellers asset-klasse-default."""
    if inst_id in PER_INSTRUMENT_OVERRIDE:
        return PER_INSTRUMENT_OVERRIDE[inst_id]
    return PRIMARY_PER_HORIZON.get(asset_class, {"M": [], "S": [], "Sc": []})


def build_coverage(
    db_path: Path, force_fresh: set[str] | None = None
) -> tuple[dict[str, FetcherHealth], list[InstrumentCoverage]]:
    """Bygg fetcher-helse-map + per-instrument-coverage.

    `force_fresh`: navn på fetchere som tvinges til status="✓" (hypotetisk
    "what if X virker"-modus). Brukes for å forutse coverage etter
    pending fixes uten å vente på neste cron-fyring.
    """
    fetch_cfg = load_fetch_config()
    con = sqlite3.connect(db_path)

    now = datetime.now(UTC)
    health_map: dict[str, FetcherHealth] = {}
    forced = force_fresh or set()

    for name, spec in fetch_cfg.fetchers.items():
        rows, last_obs = _query_table_state(con, spec.table, spec.ts_column)
        status, age = _classify_health(name, last_obs, rows, now)
        sd_last, sd_status = _query_systemd(name)
        cycle_label = CYCLE_PER_FETCHER.get(name, ("Ukjent", 24))[0]
        if name in forced:
            status = "✓"  # what-if-override
            cycle_label = f"{cycle_label} [forced ✓]"
        health_map[name] = FetcherHealth(
            name=name,
            cycle_label=cycle_label,
            cron=spec.cron,
            table=spec.table,
            last_observation=last_obs,
            rows=rows,
            age_hours=age,
            status=status,
            systemd_last_run=sd_last,
            systemd_status=sd_status,
        )
    con.close()

    # Per-instrument
    coverages: list[InstrumentCoverage] = []
    for yaml_path in sorted(INSTRUMENTS_DIR.glob("*.yaml")):
        cfg = load_instrument_config(yaml_path)
        inst = cfg.instrument
        primary = _resolve_primary(inst.id, inst.asset_class)

        horizon_status: dict[str, str] = {}
        per_horizon_health: dict[str, list[tuple[str, str]]] = {}
        for hor in ("M", "S", "Sc"):
            agg, statuses = _aggregate_horizon_status(primary.get(hor, []), health_map)
            horizon_status[hor] = agg
            per_horizon_health[hor] = statuses

        coverages.append(
            InstrumentCoverage(
                inst_id=inst.id,
                asset_class=inst.asset_class,
                horizon_status=horizon_status,
                primary_fetchers=primary,
                fetcher_health_per_horizon=per_horizon_health,
            )
        )
    return health_map, coverages


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _fmt_age(age: float | None) -> str:
    if age is None:
        return "—"
    if age < 1:
        return f"{int(age * 60)}m"
    if age < 48:
        return f"{age:.1f}t"
    return f"{age / 24:.1f}d"


def render_summary_table(coverages: list[InstrumentCoverage]) -> str:
    lines = [
        "## Sammendragstabell 1 — per-horisont-coverage",
        "",
        "Per (instrument × horisont) — ✓ alle primærkilder ferske / ⚠ 1 svikt / ✗ flere svikt.",
        "",
        "| Instrument | Asset | Macro | Swing | Scalp |",
        "|---|---|:---:|:---:|:---:|",
    ]
    for c in coverages:
        lines.append(
            f"| {c.inst_id} | {c.asset_class} "
            f"| {c.horizon_status['M']} "
            f"| {c.horizon_status['S']} "
            f"| {c.horizon_status['Sc']} |"
        )
    return "\n".join(lines)


def render_fetcher_table(health_map: dict[str, FetcherHealth]) -> str:
    lines = [
        "## Sammendragstabell 2 — per-kilde-helse",
        "",
        "| Fetcher | Cycle | Cron | Tabell | Rader | Sist obs. | Alder | DB-status | systemd |",
        "|---|---|---|---|---:|---|---|:---:|---|",
    ]
    for name in sorted(health_map.keys()):
        h = health_map[name]
        lines.append(
            f"| {h.name} | {h.cycle_label} | `{h.cron}` | `{h.table}` "
            f"| {h.rows:,} | {_fmt_dt(h.last_observation)} | {_fmt_age(h.age_hours)} "
            f"| {h.status} | {h.systemd_status} |"
        )
    return "\n".join(lines)


def render_drilldown(
    coverages: list[InstrumentCoverage], health_map: dict[str, FetcherHealth]
) -> str:
    lines = ["## Drill-down per instrument", ""]
    for c in coverages:
        lines.append(f"### {c.inst_id} ({c.asset_class})")
        lines.append("")
        lines.append("| Horisont | Status | Primærkilder (status) |")
        lines.append("|---|:---:|---|")
        for hor in ("M", "S", "Sc"):
            statuses = c.fetcher_health_per_horizon[hor]
            sources = ", ".join(f"{f} {s}" for f, s in statuses) if statuses else "—"
            lines.append(f"| {hor} | {c.horizon_status[hor]} | {sources} |")
        lines.append("")
    return "\n".join(lines)


def render_aggregate_summary(
    coverages: list[InstrumentCoverage], health_map: dict[str, FetcherHealth]
) -> str:
    """Kort tellerblokk øverst."""
    n_inst = len(coverages)
    by_status: dict[str, dict[str, int]] = {h: defaultdict(int) for h in ("M", "S", "Sc")}
    for c in coverages:
        for h in ("M", "S", "Sc"):
            by_status[h][c.horizon_status[h]] += 1

    n_fetchers = len(health_map)
    fetcher_status = defaultdict(int)
    for h in health_map.values():
        fetcher_status[h.status] += 1

    lines = [
        "## Sammendrag",
        "",
        f"- **{n_inst} instrumenter** vurdert.",
        f"- **{n_fetchers} fetchere** vurdert mot per-cycle-helse-terskler (PLAN § 20.4).",
        "",
        "### Coverage-fordeling per horisont",
        "",
        "| Horisont | ✓ | ⚠ | ✗ |",
        "|---|---:|---:|---:|",
    ]
    for h in ("M", "S", "Sc"):
        lines.append(f"| {h} | {by_status[h]['✓']} | {by_status[h]['⚠']} | {by_status[h]['✗']} |")
    lines.append("")
    lines.append("### Fetcher-helse")
    lines.append("")
    lines.append(
        f"- ✓ ferske: **{fetcher_status['✓']}**, ⚠ aging: **{fetcher_status['⚠']}**, "
        f"✗ stale/missing: **{fetcher_status['✗']}**"
    )
    return "\n".join(lines)


def render_legend() -> str:
    return """## Legende

- **Macro (M):** uker–måneder. Datafrekvens ukentlig–månedlig holder.
- **Swing (S):** dager–uker. Daglig–ukentlig kritisk.
- **Scalp (Sc):** minutter–timer. Real-time + release-kalender kritisk.

**Status-flagg per fetcher:**
- ✓ = innenfor cycle-buffer (forventet refresh + 30-50% slack)
- ⚠ = aging (mellom 70% og 100% av rødt-terskel)
- ✗ = stale eller manglende data (>100% av rødt-terskel)

**Status-flagg per (instrument × horisont):**
- ✓ = alle primærkilder for horisonten er ferske
- ⚠ = 1 primærkilde svikter
- ✗ = ≥2 primærkilder svikter

Per-cycle-tersklene (rødt-grenser) er definert i PLAN § 20.4. Primærkilde-
mappingen per asset-klasse er definert i PLAN § 20.2-tabell, med per-
instrument overrides for Cocoa/Coffee/Cotton/BTC/ETH (begrunnet av
asset-spesifikke data-realiteter).
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--what-if-fresh",
        type=str,
        default=None,
        help="Komma-separert liste over fetchere som tvinges til ✓ "
        "(hypotetisk 'what if X virker' — for å se coverage etter pending fixes)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB ikke funnet: {args.db}")

    force_fresh = (
        {s.strip() for s in args.what_if_fresh.split(",") if s.strip()}
        if args.what_if_fresh
        else None
    )

    print(f"Leser fetch.yaml + instrument-YAMLs + DB ({args.db}) ...")
    if force_fresh:
        print(f"  What-if-fresh override på: {sorted(force_fresh)}")
    health_map, coverages = build_coverage(args.db, force_fresh=force_fresh)

    print(f"  Vurdert {len(health_map)} fetchere mot {len(coverages)} instrumenter.")

    out_lines: list[str] = [
        f"# Data-coverage-rapport — {date.today().isoformat()}",
        "",
        "Sub-fase 12.8 Sub-task A1 (PLAN § 20). Per-instrument data-coverage",
        "vurdert per horisont (Macro / Swing / Scalp) basert på § 20.2-mapping.",
        "Helse-flagg per fetcher basert på cycle-spesifikke terskler (§ 20.4).",
        "",
        f"Generert av `scripts/report_data_coverage.py` mot `{args.db.name}`",
        f"({datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}).",
        "",
        render_legend(),
        "",
        render_aggregate_summary(coverages, health_map),
        "",
        render_summary_table(coverages),
        "",
        render_fetcher_table(health_map),
        "",
        render_drilldown(coverages, health_map),
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out_lines))
    print(f"\nSkrevet: {args.out}")


if __name__ == "__main__":
    main()
