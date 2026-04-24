"""Logiske tester for valutakryss-drivere.

Samme mønster som `test_trend_drivers.py`: kurerte pris-serier,
forvent eksakt score-band per driver-spec.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.store import DataStore
from bedrock.engine.drivers.currency import currency_cross_trend


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def _add_closes(
    store: DataStore,
    instrument: str,
    tf: str,
    closes: Sequence[float],
) -> None:
    ts = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"ts": ts, "close": list(closes)})
    store.append_prices(instrument, tf, df)


def _pct_step(base: float, pct_change: float, *, lookback: int = 30) -> list[float]:
    """Bygg serie der `close_now / close_then - 1 == pct_change`.

    Driveren sammenligner `prices.iloc[-1]` mot `prices.iloc[-(lookback+1)]`.
    Vi padder med `base` slik at alt BORTSETT fra siste bar ligger på
    base-nivå; siste bar settes til `base * (1 + pct_change)`.

    Returnerer serie med (lookback + 10) bars — nok til å overstige
    lookback+1-minimumet uten ekstra støy.
    """
    bars = lookback + 10
    result = [base] * (bars - 1)
    result.append(base * (1.0 + pct_change))
    return result


# ---------------------------------------------------------------------------
# Score-bånd (direct)
# ---------------------------------------------------------------------------


def test_strong_bull_over_10pct_returns_one(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.15))  # +15 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 1.0


def test_exactly_10pct_returns_one(store: DataStore) -> None:
    """+10 %-grensen er inkluderende -> 1.0."""
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.10))
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 1.0


def test_moderate_bull_5_to_10pct_returns_high(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.07))  # +7 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.8


def test_weak_bull_2_to_5pct_returns_mid_high(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.03))  # +3 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.65


def test_flat_returns_midpoint(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", [0.20] * 40)
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.5


def test_weak_bear_returns_below_mid(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, -0.01))  # -1 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.35


def test_moderate_bear_returns_low(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, -0.03))  # -3 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.2


def test_strong_bear_returns_zero(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, -0.10))  # -10 %
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.0


# ---------------------------------------------------------------------------
# direction: invert
# ---------------------------------------------------------------------------


def test_invert_flips_bull_to_bear(store: DataStore) -> None:
    """USDBRL opp = BRL ned = bearish softs. invert snur fortegn."""
    _add_closes(store, "USDBRL", "D1", _pct_step(5.0, 0.15))  # +15 %
    score = currency_cross_trend(
        store,
        "Sugar",
        {"source": "USDBRL", "lookback": 30, "direction": "invert"},
    )
    assert score == 0.0  # invert: +15 % → -15 % → under -5 % → 0.0


def test_invert_flips_bear_to_bull(store: DataStore) -> None:
    _add_closes(store, "USDBRL", "D1", _pct_step(5.0, -0.15))
    score = currency_cross_trend(
        store,
        "Sugar",
        {"source": "USDBRL", "lookback": 30, "direction": "invert"},
    )
    assert score == 1.0


def test_invalid_direction_returns_zero(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.15))
    score = currency_cross_trend(
        store,
        "Sugar",
        {"source": "BRLUSD", "lookback": 30, "direction": "sideways"},
    )
    assert score == 0.0


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_missing_source_returns_zero(store: DataStore) -> None:
    score = currency_cross_trend(store, "Sugar", {"lookback": 30})
    assert score == 0.0


def test_short_history_returns_zero(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.15, lookback=5))
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.0


def test_unknown_source_returns_zero(store: DataStore) -> None:
    score = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 0.0


def test_default_lookback_is_thirty(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.15))
    score_default = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD"}
    )
    score_explicit = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    assert score_default == score_explicit == 1.0


def test_custom_tf_is_used(store: DataStore) -> None:
    _add_closes(store, "BRLUSD", "H4", _pct_step(0.20, 0.15))
    score_default = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30}
    )
    score_h4 = currency_cross_trend(
        store, "Sugar", {"source": "BRLUSD", "lookback": 30, "tf": "H4"}
    )
    assert score_default == 0.0
    assert score_h4 == 1.0


def test_instrument_argument_is_ignored(store: DataStore) -> None:
    """Driver leser fra params[source], ikke fra instrument-argumentet."""
    _add_closes(store, "BRLUSD", "D1", _pct_step(0.20, 0.15))
    _add_closes(store, "Coffee", "D1", _pct_step(1.0, -0.50))  # -50 %
    score = currency_cross_trend(
        store, "Coffee", {"source": "BRLUSD", "lookback": 30}
    )
    assert score == 1.0  # basert på BRLUSD, ikke Coffee
