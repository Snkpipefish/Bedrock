# pyright: reportArgumentType=false
"""Tester for *_surprise-drivere (sub-fase 12.10 follow-up Spor B, session 138)."""

from __future__ import annotations

import pandas as pd
import pytest

from bedrock.engine.drivers import get, is_registered
from bedrock.engine.drivers.event_surprise import _parse_value


@pytest.mark.parametrize(
    "driver_name",
    ["nfp_surprise", "cpi_surprise", "gdp_surprise", "pce_surprise"],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name)
    assert callable(get(driver_name))


# ---------------------------------------------------------------------------
# _parse_value
# ---------------------------------------------------------------------------


def test_parse_value_jobs_thousand() -> None:
    assert _parse_value("115K") == 115.0
    assert _parse_value("+108K") == 108.0
    assert _parse_value("-48K") == -48.0


def test_parse_value_pct() -> None:
    assert _parse_value("0.2%") == 0.2
    assert _parse_value("3.0%") == 3.0
    assert _parse_value("-2.4%") == -2.4


def test_parse_value_invalid() -> None:
    assert _parse_value(None) is None
    assert _parse_value("") is None
    assert _parse_value("abc") is None
    assert _parse_value(float("nan")) is None


def test_parse_value_million_billion() -> None:
    """M og B suffix multipliseres med 1000/1000000 for konsistens med K-base."""
    assert _parse_value("1M") == 1000.0
    assert _parse_value("0.5B") == 500_000.0


# ---------------------------------------------------------------------------
# Stub-store + helper
# ---------------------------------------------------------------------------


class _EventStore:
    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df

    def get_econ_events(
        self,
        countries=None,
        impact_levels=None,
        from_ts=None,
        to_ts=None,
        title_pattern=None,
    ):
        if self._df is None:
            return pd.DataFrame()
        df = self._df.copy()
        if countries:
            df = df[df["country"].isin(countries)]
        if title_pattern:
            df = df[df["title"] == title_pattern]
        return df.reset_index(drop=True)


def _events_df(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    """Rows: (event_ts, country, title, forecast, actual)."""
    return pd.DataFrame(
        [
            {
                "event_ts": pd.Timestamp(ts, tz="UTC"),
                "country": c,
                "title": t,
                "impact": "High",
                "forecast": f,
                "previous": None,
                "actual": a,
                "fetched_at": pd.Timestamp(ts, tz="UTC"),
            }
            for (ts, c, t, f, a) in rows
        ]
    )


# ---------------------------------------------------------------------------
# nfp_surprise
# ---------------------------------------------------------------------------


def test_nfp_positive_surprise_high_score() -> None:
    """Actual 250K vs forecast 100K → +150K → step >+100K → 1.0."""
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", "+250K"),
        ]
    )
    score = fn(_EventStore(df), "SP500", {})
    assert score == 1.0


def test_nfp_negative_surprise_low_score() -> None:
    """Actual -50K vs forecast 100K → -150K → step ≤-100 → 0.0."""
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", "-50K"),
        ]
    )
    score = fn(_EventStore(df), "SP500", {})
    assert score == 0.0


def test_nfp_neutral_when_in_match() -> None:
    """Actual 100K vs forecast 100K → 0 → 0.5."""
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", "+100K"),
        ]
    )
    assert fn(_EventStore(df), "SP500", {}) == 0.5


def test_nfp_takes_latest_event() -> None:
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-03-07 13:30", "USD", "Non-Farm Employment Change", "150K", "+50K"),
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", "+250K"),
        ]
    )
    # Latest = April → +150 → 1.0
    assert fn(_EventStore(df), "SP500", {}) == 1.0


def test_nfp_skips_events_outside_lookback() -> None:
    """Latest event er for gammel → 0.5 (defensive)."""
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2025-01-04 12:30", "USD", "Non-Farm Employment Change", "100K", "+250K"),
        ]
    )
    # Default lookback 30d, latest event er 2025-01-04 — lookback fra event_max
    # gjør at alle inkluderes likevel (cutoff = event_max - 30d = 2024-12-04)
    # → siste event innenfor → 1.0
    assert fn(_EventStore(df), "SP500", {}) == 1.0


def test_nfp_no_data_returns_neutral() -> None:
    fn = get("nfp_surprise")
    assert fn(_EventStore(None), "SP500", {}) == 0.5
    assert fn(_EventStore(pd.DataFrame()), "SP500", {}) == 0.5


def test_nfp_missing_actual_returns_neutral() -> None:
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", None),
        ]
    )
    assert fn(_EventStore(df), "SP500", {}) == 0.5


def test_nfp_bull_when_low_inverts() -> None:
    fn = get("nfp_surprise")
    df = _events_df(
        [
            ("2026-04-04 12:30", "USD", "Non-Farm Employment Change", "100K", "+250K"),
        ]
    )
    high = fn(_EventStore(df), "SP500", {"bull_when": "high"})
    low = fn(_EventStore(df), "EURUSD", {"bull_when": "low"})
    assert high == 1.0
    assert low == 0.0


# ---------------------------------------------------------------------------
# cpi_surprise
# ---------------------------------------------------------------------------


def test_cpi_positive_surprise_high_score() -> None:
    """+0.1 pp surprise → step (0.1, 0.75) → 0.75."""
    fn = get("cpi_surprise")
    df = _events_df(
        [
            ("2026-04-10 12:30", "USD", "CPI m/m", "0.2%", "0.3%"),
        ]
    )
    assert fn(_EventStore(df), "SP500", {}) == 0.75


def test_cpi_strong_surprise_max_score() -> None:
    """+0.2 pp surprise → step >+0.1 → 1.0."""
    fn = get("cpi_surprise")
    df = _events_df(
        [
            ("2026-04-10 12:30", "USD", "CPI m/m", "0.2%", "0.4%"),
        ]
    )
    assert fn(_EventStore(df), "SP500", {}) == 1.0


def test_cpi_negative_surprise() -> None:
    fn = get("cpi_surprise")
    df = _events_df(
        [
            ("2026-04-10 12:30", "USD", "CPI m/m", "0.3%", "0.0%"),
        ]
    )
    # -0.3 pp → step ≤-0.3 → 0.0
    assert fn(_EventStore(df), "SP500", {}) == 0.0


# ---------------------------------------------------------------------------
# gdp_surprise
# ---------------------------------------------------------------------------


def test_gdp_positive_surprise() -> None:
    fn = get("gdp_surprise")
    df = _events_df(
        [
            ("2026-04-25 12:30", "USD", "Advance GDP q/q", "2.0%", "3.5%"),
        ]
    )
    # +1.5 pp → step >+0.5 → 1.0
    assert fn(_EventStore(df), "SP500", {}) == 1.0


def test_gdp_negative_surprise() -> None:
    fn = get("gdp_surprise")
    df = _events_df(
        [
            ("2026-04-25 12:30", "USD", "Advance GDP q/q", "2.5%", "0.5%"),
        ]
    )
    # -2.0 pp → step ≤-1.5 → 0.0
    assert fn(_EventStore(df), "SP500", {}) == 0.0


# ---------------------------------------------------------------------------
# pce_surprise
# ---------------------------------------------------------------------------


def test_pce_positive_surprise() -> None:
    fn = get("pce_surprise")
    df = _events_df(
        [
            ("2026-04-30 12:30", "USD", "Core PCE Price Index m/m", "0.2%", "0.3%"),
        ]
    )
    # +0.1 pp → 0.75
    assert fn(_EventStore(df), "SP500", {}) == 0.75


def test_pce_uses_default_title_pattern() -> None:
    """Driveren bruker 'Core PCE Price Index m/m' som default."""
    fn = get("pce_surprise")
    captured: dict = {}

    class _Capture(_EventStore):
        def get_econ_events(self, countries=None, **kw):
            captured["title_pattern"] = kw.get("title_pattern")
            return pd.DataFrame()

    fn(_Capture(), "SP500", {})
    assert captured["title_pattern"] == "Core PCE Price Index m/m"


# ---------------------------------------------------------------------------
# Custom params
# ---------------------------------------------------------------------------


def test_custom_thresholds_override() -> None:
    fn = get("cpi_surprise")
    df = _events_df(
        [
            ("2026-04-10 12:30", "USD", "CPI m/m", "0.2%", "0.3%"),
        ]
    )
    # +0.1 pp surprise. Default ≤0.1 → 0.75. Custom: ≤0.05 → 1.0
    custom = [(0.05, 1.0), (1.0, 0.5)]
    score = fn(_EventStore(df), "SP500", {"thresholds": custom})
    # +0.1 > 0.05 og ≤1.0 → 0.5
    assert score == 0.5
