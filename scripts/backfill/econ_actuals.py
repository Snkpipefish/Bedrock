"""Cross-source-join: populer econ_events.actual fra FRED-observasjoner.

Sub-fase 12.10 follow-up Spor B (session 138). Per ADR-014.

For hver event-tittel-pattern joiner skriptet:
- econ_events-rader (FF-fetched) der actual IS NULL og title matcher pattern
- mot mest nylige FRED-observasjon før event_ts (men innen 60 dager)
- og beregner "actual" i samme format som FF.forecast (K, %, etc.)

Mappings:
- "Non-Farm Employment Change" (USD) → PAYEMS MoM Δ → "{N}K" (tusen)
- "CPI m/m" + "Core CPI m/m" (USD) → CPIAUCSL MoM % → "{X.X}%"
- "Advance GDP q/q" + "Prelim GDP q/q" + "Final GDP q/q" (USD) → GDP QoQ
  annualized % → "{X.X}%"
- "Core PCE Price Index m/m" (USD) → PCEPI MoM % → "{X.X}%"

Idempotent: skriptet hopper over rader hvor actual allerede er satt, slik
at ny FF-data + ny FRED-data kan akkumuleres uten å overskrive.

Kjør: PYTHONPATH=src .venv/bin/python scripts/backfill/econ_actuals.py
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd

from bedrock.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

DEFAULT_DB = "data/bedrock.db"


@dataclass(frozen=True)
class EventMapping:
    """Mapping fra econ_events title-pattern til FRED-serie + format-funksjon."""

    title_patterns: tuple[str, ...]  # SQL LIKE-patterns (med %% for substring)
    country: str
    fred_series: str
    metric_kind: str  # "mom_delta_thousand" | "mom_pct" | "qoq_ann_pct"


MAPPINGS: tuple[EventMapping, ...] = (
    EventMapping(
        title_patterns=("Non-Farm Employment Change",),
        country="USD",
        fred_series="PAYEMS",
        metric_kind="mom_delta_thousand",
    ),
    EventMapping(
        title_patterns=("CPI m/m", "Core CPI m/m"),
        country="USD",
        fred_series="CPIAUCSL",
        metric_kind="mom_pct",
    ),
    EventMapping(
        title_patterns=(
            "Advance GDP q/q",
            "Prelim GDP q/q",
            "Final GDP q/q",
        ),
        country="USD",
        fred_series="GDP",
        metric_kind="qoq_ann_pct",
    ),
    EventMapping(
        title_patterns=("Core PCE Price Index m/m",),
        country="USD",
        fred_series="PCEPI",
        metric_kind="mom_pct",
    ),
)


def _format_actual(metric_kind: str, current: float, previous: float) -> str | None:
    """Beregn 'actual'-string i samme format som FF.forecast.

    Returnerer None hvis verdiene ikke kan beregnes (NaN/zero).
    """
    if pd.isna(current) or pd.isna(previous):
        return None
    if metric_kind == "mom_delta_thousand":
        # PAYEMS: thousands of jobs → MoM delta direkte (PAYEMS er allerede
        # i tusen). FF-format: "115K".
        delta = round(current - previous)
        return f"{delta:+d}K" if delta != 0 else "0K"
    if metric_kind == "mom_pct":
        if previous == 0.0:
            return None
        pct = (current - previous) / previous * 100.0
        return f"{pct:.1f}%"
    if metric_kind == "qoq_ann_pct":
        if previous <= 0.0:
            return None
        # Annualisert QoQ %: ((current/previous)^4 - 1) * 100
        try:
            ratio = current / previous
            ann_pct = (ratio**4 - 1) * 100.0
        except (ValueError, OverflowError):
            return None
        return f"{ann_pct:.1f}%"
    return None


def _populate_for_mapping(
    store: DataStore,
    mapping: EventMapping,
) -> tuple[int, int]:
    """Populer actual for én EventMapping. Returner (skanned, oppdatert)."""
    try:
        fred_series = store.get_fundamentals(mapping.fred_series)
    except KeyError:
        _log.warning("missing FRED series %s — skip", mapping.fred_series)
        return (0, 0)

    fred_df = fred_series.to_frame(name="value").reset_index().rename(columns={"index": "date"})
    fred_df["date"] = pd.to_datetime(fred_df["date"]).dt.tz_localize(None)
    fred_df = fred_df.sort_values("date").reset_index(drop=True)

    scanned = 0
    updated = 0
    for pattern in mapping.title_patterns:
        events = store.get_econ_events(
            countries=[mapping.country],
            title_pattern=pattern,
        )
        if events.empty:
            continue
        # Filtrer ut rader med actual allerede satt — idempotent.
        events = events[events["actual"].isna() | (events["actual"] == "")]
        if events.empty:
            continue

        # Vindu for å plukke siste FRED-obs før event. Quarterly-serier
        # (GDP) har period-start opptil ~100 dager før publisering; monthly
        # ~30-45 dager.
        window_days = 150 if mapping.metric_kind == "qoq_ann_pct" else 60

        for _, ev in events.iterrows():
            scanned += 1
            event_dt = ev["event_ts"].tz_convert(None) if ev["event_ts"].tzinfo else ev["event_ts"]
            window_start = event_dt - timedelta(days=window_days)
            mask = (fred_df["date"] <= event_dt) & (fred_df["date"] > window_start)
            relevant = fred_df[mask]
            if len(relevant) < 2:
                continue
            current = float(relevant.iloc[-1]["value"])
            previous = float(relevant.iloc[-2]["value"])
            actual = _format_actual(mapping.metric_kind, current, previous)
            if actual is None:
                continue
            event_ts_str = event_dt.strftime("%Y-%m-%dT%H:%M:%S")
            n = store.update_econ_event_actual(
                event_ts=event_ts_str,
                country=mapping.country,
                title=ev["title"],
                actual=actual,
            )
            if n > 0:
                updated += 1

    return (scanned, updated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        _log.error("DB finnes ikke: %s", db_path)
        return 1

    store = DataStore(db_path)
    _log.info("Cross-source-join: %d mappings", len(MAPPINGS))

    total_scanned = 0
    total_updated = 0
    for mapping in MAPPINGS:
        scanned, updated = _populate_for_mapping(store, mapping)
        total_scanned += scanned
        total_updated += updated
        _log.info(
            "%s (%s): scanned=%d updated=%d",
            mapping.fred_series,
            ", ".join(mapping.title_patterns),
            scanned,
            updated,
        )

    _log.info("Ferdig: %d/%d events fikk actual.", total_updated, total_scanned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
