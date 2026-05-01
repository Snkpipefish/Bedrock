"""Sub-fase 12.10 Bunke 1 Bug-1 trinn 2/3:
AsOfDateStore clipper COT- og AAII-getters på publikasjons-tidspunkt
istedenfor report_date for å unngå look-ahead-bias.

Bug-scenario: en CFTC-rapport for tirsdag-snapshot publiseres ikke
før fredag 15:30 ET (~21:00 UTC konservativt). Backtest med
as_of=tirsdag har ingen rett til å se den raden.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.backtest.store_view import AsOfDateStore
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------------
# Fixtures: 4 ukentlige rapporter for hver tabell, alle på tirsdag/onsdag
# ---------------------------------------------------------------------------

# 4 påfølgende tirsdager
TUESDAYS = pd.to_datetime(["2024-01-02", "2024-01-09", "2024-01-16", "2024-01-23"])
WEDNESDAYS = pd.to_datetime(["2024-01-03", "2024-01-10", "2024-01-17", "2024-01-24"])


@pytest.fixture
def seeded_store(tmp_path: Path) -> DataStore:
    store = DataStore(tmp_path / "bedrock.db")

    # CFTC disaggregated
    store.append_cot_disaggregated(
        pd.DataFrame(
            {
                "report_date": TUESDAYS,
                "contract": ["GOLD - COMMODITY EXCHANGE INC."] * 4,
                "mm_long": [100, 110, 120, 130],
                "mm_short": [50] * 4,
                "other_long": [10] * 4,
                "other_short": [10] * 4,
                "comm_long": [10] * 4,
                "comm_short": [10] * 4,
                "nonrep_long": [5] * 4,
                "nonrep_short": [5] * 4,
                "open_interest": [200] * 4,
            }
        )
    )

    # CFTC legacy
    store.append_cot_legacy(
        pd.DataFrame(
            {
                "report_date": TUESDAYS,
                "contract": ["GOLD - COMMODITY EXCHANGE INC."] * 4,
                "noncomm_long": [100, 110, 120, 130],
                "noncomm_short": [50] * 4,
                "comm_long": [10] * 4,
                "comm_short": [10] * 4,
                "nonrep_long": [5] * 4,
                "nonrep_short": [5] * 4,
                "open_interest": [200] * 4,
            }
        )
    )

    # CFTC TFF
    store.append_cot_tff(
        pd.DataFrame(
            {
                "report_date": TUESDAYS,
                "contract": ["S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"] * 4,
                "dealer_long": [100] * 4,
                "dealer_short": [50] * 4,
                "asset_mgr_long": [200] * 4,
                "asset_mgr_short": [100] * 4,
                "lev_funds_long": [80, 90, 100, 110],
                "lev_funds_short": [40] * 4,
                "other_long": [10] * 4,
                "other_short": [10] * 4,
                "nonrep_long": [5] * 4,
                "nonrep_short": [5] * 4,
                "open_interest": [500] * 4,
            }
        )
    )

    # ICE
    store.append_cot_ice(
        pd.DataFrame(
            {
                "report_date": TUESDAYS,
                "contract": ["ice brent crude"] * 4,
                "mm_long": [100, 110, 120, 130],
                "mm_short": [50] * 4,
                "other_long": [10] * 4,
                "other_short": [10] * 4,
                "comm_long": [10] * 4,
                "comm_short": [10] * 4,
                "nonrep_long": [5] * 4,
                "nonrep_short": [5] * 4,
                "open_interest": [200] * 4,
            }
        )
    )

    # Euronext
    store.append_cot_euronext(
        pd.DataFrame(
            {
                "report_date": TUESDAYS,
                "contract": ["euronext milling wheat"] * 4,
                "mm_long": [100, 110, 120, 130],
                "mm_short": [50] * 4,
                "open_interest": [200] * 4,
            }
        )
    )

    # AAII sentiment (onsdag-survey)
    store.append_aaii_sentiment(
        pd.DataFrame(
            {
                "date": WEDNESDAYS,
                "bullish_pct": [40.0, 42.0, 44.0, 46.0],
                "neutral_pct": [30.0] * 4,
                "bearish_pct": [30.0, 28.0, 26.0, 24.0],
                "bull_bear_spread": [10.0, 14.0, 18.0, 22.0],
            }
        )
    )

    return store


# ---------------------------------------------------------------------------
# COT (CFTC disaggregated): tirsdag-rapport ikke synlig før fredag 21:00 UTC
# ---------------------------------------------------------------------------


def test_cot_disaggregated_hides_unpublished_row(seeded_store: DataStore) -> None:
    """as_of=tirsdag (samme dag som siste snapshot) skal IKKE se den raden
    — den er ikke publisert før fredag 21:00 UTC."""
    # 2024-01-23 (siste tirsdag i fixture) — release er 2024-01-26 21:00 UTC
    view = AsOfDateStore(seeded_store, date(2024, 1, 23))
    df = view.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="disaggregated")
    # Skal kun se de 3 første (jan 2/9/16); jan 23 er ikke publisert ennå
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-16")


def test_cot_disaggregated_visible_after_release(seeded_store: DataStore) -> None:
    """as_of=lørdag etter siste publisering — alle 4 rader synlige."""
    view = AsOfDateStore(seeded_store, date(2024, 1, 27))
    df = view.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="disaggregated")
    assert len(df) == 4


def test_cot_disaggregated_friday_morning_hides_today(seeded_store: DataStore) -> None:
    """Fredag morgen — releasen kommer 21:00 UTC samme dag, men midnatt-as_of
    ser den ikke ennå."""
    # 2024-01-19 = fredagen som tirsdag 01-16-raden publiseres
    view = AsOfDateStore(seeded_store, date(2024, 1, 19))
    df = view.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="disaggregated")
    # 01-02 release 01-05 21:00 ≤ 01-19 00:00 ✓
    # 01-09 release 01-12 21:00 ≤ 01-19 00:00 ✓
    # 01-16 release 01-19 21:00 > 01-19 00:00 ✗ (ikke publisert ennå)
    assert len(df) == 2
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-09")


# ---------------------------------------------------------------------------
# COT (CFTC legacy)
# ---------------------------------------------------------------------------


def test_cot_legacy_hides_unpublished_row(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 23))
    df = view.get_cot("GOLD - COMMODITY EXCHANGE INC.", report="legacy")
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-16")


# ---------------------------------------------------------------------------
# COT TFF
# ---------------------------------------------------------------------------


def test_cot_tff_hides_unpublished_row(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 23))
    df = view.get_cot_tff("S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE")
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-16")


def test_cot_tff_all_visible_after_release(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 27))
    df = view.get_cot_tff("S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE")
    assert len(df) == 4


# ---------------------------------------------------------------------------
# COT ICE
# ---------------------------------------------------------------------------


def test_cot_ice_hides_unpublished_row(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 23))
    df = view.get_cot_ice("ice brent crude")
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-16")


# ---------------------------------------------------------------------------
# COT Euronext
# ---------------------------------------------------------------------------


def test_cot_euronext_hides_unpublished_row(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2024, 1, 23))
    df = view.get_cot_euronext("euronext milling wheat")
    assert len(df) == 3
    assert df["report_date"].iloc[-1] == pd.Timestamp("2024-01-16")


# ---------------------------------------------------------------------------
# AAII: onsdag-survey ikke synlig før torsdag 14:00 UTC
# ---------------------------------------------------------------------------


def test_aaii_hides_unpublished_row(seeded_store: DataStore) -> None:
    """as_of=onsdag (samme dag som siste survey-close) — ikke synlig før
    torsdag 14:00 UTC."""
    # 2024-01-24 onsdag — release er 2024-01-25 14:00 UTC
    view = AsOfDateStore(seeded_store, date(2024, 1, 24))
    df = view.get_aaii_sentiment()
    # Skal kun se de 3 første (jan 3/10/17)
    assert len(df) == 3
    assert df["date"].iloc[-1] == pd.Timestamp("2024-01-17")


def test_aaii_thursday_morning_hides_today(seeded_store: DataStore) -> None:
    """Torsdag midnatt — releasen kommer 14:00 UTC samme dag."""
    # 2024-01-25 torsdag — onsdag-rad fra 01-24 publiseres 01-25 14:00 UTC
    view = AsOfDateStore(seeded_store, date(2024, 1, 25))
    df = view.get_aaii_sentiment()
    # Som-of=2024-01-25 00:00 < 01-25 14:00 → siste rad fortsatt skjult
    assert len(df) == 3


def test_aaii_visible_after_release(seeded_store: DataStore) -> None:
    """Fredag morgen — torsdag-publisering har gått — alle 4 synlige."""
    view = AsOfDateStore(seeded_store, date(2024, 1, 26))
    df = view.get_aaii_sentiment()
    assert len(df) == 4


# ---------------------------------------------------------------------------
# Tom retur håndteres riktig
# ---------------------------------------------------------------------------


def test_cot_clipped_to_empty_raises(seeded_store: DataStore) -> None:
    view = AsOfDateStore(seeded_store, date(2023, 12, 1))  # før all data
    with pytest.raises(KeyError, match="as of"):
        view.get_cot("GOLD - COMMODITY EXCHANGE INC.")


def test_aaii_clipped_to_empty_returns_empty(seeded_store: DataStore) -> None:
    """AAII-getter returnerer tom DataFrame, ikke raise (matcher
    underlying DataStore-konvensjon)."""
    view = AsOfDateStore(seeded_store, date(2023, 12, 1))
    df = view.get_aaii_sentiment()
    assert df.empty
