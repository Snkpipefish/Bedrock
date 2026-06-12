"""Tester for `_resolve_direction_conflicts` — retningskonflikt-løseren.

Session 2026-06-12: vinneren velges på NORMALISERT score (score /
max_score), ikke rå score — horisonter har ulik max_score (Gold:
SCALP 4.8 vs MAKRO 5.9) og rå sammenligning ga systematisk fordel til
horisonter med stor skala.
"""

from __future__ import annotations

from datetime import datetime

from bedrock.orchestrator.signals import SignalEntry, _resolve_direction_conflicts
from bedrock.setups.generator import Direction, Horizon, Setup
from bedrock.setups.hysteresis import StableSetup, compute_setup_id
from bedrock.setups.levels import LevelType

NOW = datetime(2026, 6, 12, 12, 0, 0)


def _stable_setup(direction: Direction, horizon: Horizon) -> StableSetup:
    sign = 1.0 if direction == Direction.BUY else -1.0
    setup = Setup(
        instrument="Gold",
        direction=direction,
        horizon=horizon,
        entry=100.0,
        sl=100.0 - sign * 1.0,
        tp=100.0 + sign * 3.0,
        rr=3.0,
        atr=1.0,
        entry_cluster_price=100.0,
        entry_cluster_types=[LevelType.SWING_LOW],
        tp_cluster_price=100.0 + sign * 3.0,
        tp_cluster_types=[LevelType.SWING_HIGH],
    )
    return StableSetup(
        setup_id=compute_setup_id("Gold", direction, horizon),
        first_seen=NOW,
        last_updated=NOW,
        setup=setup,
    )


def _entry(
    direction: Direction,
    horizon: Horizon,
    score: float,
    max_score: float,
    published: bool = True,
    with_setup: bool = True,
) -> SignalEntry:
    return SignalEntry(
        instrument="Gold",
        direction=direction,
        horizon=horizon,
        score=score,
        grade="B",
        max_score=max_score,
        min_score_publish=1.0,
        published=published,
        setup=_stable_setup(direction, horizon) if with_setup else None,
    )


def test_no_conflict_when_single_direction() -> None:
    entries = [
        _entry(Direction.BUY, Horizon.SWING, 3.0, 5.8),
        _entry(Direction.BUY, Horizon.MAKRO, 3.5, 5.9),
    ]
    out = _resolve_direction_conflicts(entries)
    assert all(e.published for e in out)


def test_conflict_winner_chosen_on_normalized_score() -> None:
    """SCALP-BUY 3.0/4.8 (62.5%) skal slå MAKRO-SELL 3.5/5.9 (59.3%)
    selv om rå score er lavere."""
    buy = _entry(Direction.BUY, Horizon.SCALP, 3.0, 4.8)
    sell = _entry(Direction.SELL, Horizon.MAKRO, 3.5, 5.9)
    out = _resolve_direction_conflicts([buy, sell])

    by_dir = {e.direction: e for e in out}
    assert by_dir[Direction.BUY].published is True
    assert by_dir[Direction.SELL].published is False
    assert by_dir[Direction.SELL].skip_reason == "opposite_direction_dominates"
    # Setup bevares for hysterese/UI
    assert by_dir[Direction.SELL].setup is not None


def test_conflict_demotes_all_losers_across_horizons() -> None:
    """Tre published entries (BUY SWING vinner, BUY SCALP + SELL MAKRO):
    kun motsatt retning demoteres — samme retning beholdes."""
    buy_swing = _entry(Direction.BUY, Horizon.SWING, 4.0, 5.8)  # 69%
    buy_scalp = _entry(Direction.BUY, Horizon.SCALP, 2.0, 4.8)  # 42%
    sell_makro = _entry(Direction.SELL, Horizon.MAKRO, 3.0, 5.9)  # 51%
    out = _resolve_direction_conflicts([buy_swing, buy_scalp, sell_makro])

    published = {(e.direction, e.horizon): e.published for e in out}
    assert published[(Direction.BUY, Horizon.SWING)] is True
    assert published[(Direction.SELL, Horizon.MAKRO)] is False
    # NB: dagens regel demoterer kun taperne av retningskampen i samlet
    # pulje — BUY SCALP er på vinnersiden av retningen men har lavere
    # normalisert score enn vinneren, så den demoteres også (én vinner
    # per instrument når konflikt finnes).
    assert published[(Direction.BUY, Horizon.SCALP)] is False


def test_unpublished_and_setupless_entries_ignored() -> None:
    buy = _entry(Direction.BUY, Horizon.SWING, 3.0, 5.8, published=False)
    sell = _entry(Direction.SELL, Horizon.SWING, 2.5, 5.8, with_setup=False)
    out = _resolve_direction_conflicts([buy, sell])
    # Ingen av dem kvalifiserer til konflikt → uendret
    assert out[0].published is False
    assert out[1].published is True


def test_zero_max_score_treated_as_zero_normalized() -> None:
    """Defensivt: max_score=0 skal ikke gi div-0 — entry taper kampen."""
    buy = _entry(Direction.BUY, Horizon.SWING, 3.0, 0.0)
    sell = _entry(Direction.SELL, Horizon.MAKRO, 1.0, 5.9)
    out = _resolve_direction_conflicts([buy, sell])
    by_dir = {e.direction: e for e in out}
    assert by_dir[Direction.SELL].published is True
    assert by_dir[Direction.BUY].published is False
