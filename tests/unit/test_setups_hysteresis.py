"""Tester for `bedrock.setups.hysteresis` — stabilitets-filtre."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bedrock.setups.generator import Direction, Horizon, Setup, SetupConfig, build_setup
from bedrock.setups.hysteresis import (
    HysteresisConfig,
    SetupSnapshot,
    StableSetup,
    apply_hysteresis_batch,
    compute_setup_id,
    stabilize_setup,
)
from bedrock.setups.levels import Level, LevelType
from bedrock.setups.snapshot import load_snapshot, save_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2024, 7, 1, 12, 0, 0)
LATER = NOW + timedelta(hours=4)


def _lvl(price: float, type_: LevelType, strength: float = 0.8) -> Level:
    return Level(price=price, type=type_, strength=strength)


def _basic_buy_setup() -> Setup:
    """Gold BUY SCALP @ 102, entry 100, sl 99.7, tp 106."""
    setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.SCALP,
        current_price=102.0,
        atr=1.0,
        levels=[
            _lvl(100.0, LevelType.SWING_LOW, 0.8),
            _lvl(106.0, LevelType.SWING_HIGH, 0.8),
        ],
    )
    assert setup is not None
    return setup


# ---------------------------------------------------------------------------
# compute_setup_id
# ---------------------------------------------------------------------------


def test_setup_id_deterministic() -> None:
    a = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    b = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    assert a == b


def test_setup_id_differs_by_instrument() -> None:
    gold = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    silver = compute_setup_id("Silver", Direction.BUY, Horizon.SCALP)
    assert gold != silver


def test_setup_id_differs_by_direction() -> None:
    buy = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    sell = compute_setup_id("Gold", Direction.SELL, Horizon.SCALP)
    assert buy != sell


def test_setup_id_differs_by_horizon() -> None:
    scalp = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    swing = compute_setup_id("Gold", Direction.BUY, Horizon.SWING)
    makro = compute_setup_id("Gold", Direction.BUY, Horizon.MAKRO)
    assert len({scalp, swing, makro}) == 3


def test_setup_id_is_hex_12_chars() -> None:
    sid = compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)
    assert len(sid) == 12
    assert all(c in "0123456789abcdef" for c in sid)


# ---------------------------------------------------------------------------
# stabilize_setup — no previous
# ---------------------------------------------------------------------------


def test_stabilize_no_previous_returns_new_with_now_timestamps() -> None:
    new = _basic_buy_setup()
    stable = stabilize_setup(new, previous=None, now=NOW)
    assert stable.first_seen == NOW
    assert stable.last_updated == NOW
    assert stable.setup == new
    assert stable.setup_id == compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)


# ---------------------------------------------------------------------------
# stabilize_setup — SL-stabilitet
# ---------------------------------------------------------------------------


def _prev_with(setup: Setup, first_seen: datetime = NOW) -> StableSetup:
    return StableSetup(
        setup_id=compute_setup_id(setup.instrument, setup.direction, setup.horizon),
        first_seen=first_seen,
        last_updated=first_seen,
        setup=setup,
    )


def test_stabilize_keeps_old_sl_when_new_sl_within_buffer() -> None:
    """Ny SL 99.75 vs forrige 99.7; buffer = 0.3 × 1.0 = 0.3. Innenfor → behold 99.7."""
    prev_setup = _basic_buy_setup()  # sl=99.7
    prev = _prev_with(prev_setup)

    # Bygg nytt setup med litt annerledes SL: simulerer at entry ble 100.05
    new = prev_setup.model_copy(update={"sl": 99.75})

    stable = stabilize_setup(new, previous=prev, now=LATER)
    assert stable.setup.sl == 99.7  # beholdt fra prev


def test_stabilize_uses_new_sl_when_delta_exceeds_buffer() -> None:
    """Ny SL 99.3 vs 99.7; delta=0.4 > buffer 0.3 → bruk ny."""
    prev_setup = _basic_buy_setup()
    prev = _prev_with(prev_setup)

    new = prev_setup.model_copy(update={"sl": 99.3})
    stable = stabilize_setup(new, previous=prev, now=LATER)
    assert stable.setup.sl == 99.3


def test_stabilize_keeps_old_tp_when_new_within_buffer() -> None:
    """Ny TP 106.4 vs 106.0; buffer = 0.5 × 1.0 = 0.5. Innenfor → behold 106.0."""
    prev_setup = _basic_buy_setup()  # tp=106
    prev = _prev_with(prev_setup)

    new = prev_setup.model_copy(update={"tp": 106.4})
    stable = stabilize_setup(new, previous=prev, now=LATER)
    assert stable.setup.tp == 106.0


def test_stabilize_uses_new_tp_when_delta_exceeds_buffer() -> None:
    """Ny TP 107 vs 106.0; delta=1.0 > buffer 0.5 → bruk ny 107."""
    prev_setup = _basic_buy_setup()
    prev = _prev_with(prev_setup)

    new = prev_setup.model_copy(update={"tp": 107.0})
    stable = stabilize_setup(new, previous=prev, now=LATER)
    assert stable.setup.tp == 107.0


def test_stabilize_recomputes_rr_after_substitution() -> None:
    """Etter SL/TP-substitusjon må R:R stemme med stabiliserte verdier."""
    prev_setup = _basic_buy_setup()  # entry=100, sl=99.7, tp=106, rr=20
    prev = _prev_with(prev_setup)

    # Ny setup med lett andre SL/TP innenfor buffer → stabilisert tilbake
    new = prev_setup.model_copy(update={"sl": 99.75, "tp": 106.1})
    stable = stabilize_setup(new, previous=prev, now=LATER)

    # Etter stabilisering: sl=99.7, tp=106. R:R = (106-100)/(100-99.7) = 20
    assert stable.setup.rr == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# stabilize_setup — MAKRO + edge cases
# ---------------------------------------------------------------------------


def test_stabilize_makro_setup_tp_stays_none() -> None:
    """MAKRO har tp=None begge steder — ingen TP-sjekk."""
    prev_setup = build_setup(
        instrument="Gold",
        direction=Direction.BUY,
        horizon=Horizon.MAKRO,
        current_price=102.0,
        atr=1.0,
        levels=[_lvl(100.0, LevelType.SWING_LOW, 0.8)],
    )
    assert prev_setup is not None and prev_setup.tp is None
    prev = _prev_with(prev_setup)

    new = prev_setup.model_copy()
    stable = stabilize_setup(new, previous=prev, now=LATER)
    assert stable.setup.tp is None
    assert stable.setup.rr is None


def test_stabilize_first_seen_preserved_when_slot_matches() -> None:
    """first_seen fra prev beholdes; last_updated oppdateres til now."""
    prev_setup = _basic_buy_setup()
    prev = _prev_with(prev_setup, first_seen=NOW)

    new = prev_setup.model_copy(update={"sl": 99.6})  # liten endring (within)
    stable = stabilize_setup(new, previous=prev, now=LATER)

    assert stable.first_seen == NOW  # fra prev
    assert stable.last_updated == LATER


def test_stabilize_disabled_returns_unchanged() -> None:
    """config.enabled=False → null hysterese; ny SL/TP brukes."""
    prev_setup = _basic_buy_setup()
    prev = _prev_with(prev_setup)

    new = prev_setup.model_copy(update={"sl": 99.75, "tp": 106.4})
    stable = stabilize_setup(
        new, previous=prev, now=LATER, config=HysteresisConfig(enabled=False)
    )
    # Disabled → return new values, ignore prev (first_seen = now siden ignorering)
    assert stable.setup.sl == 99.75
    assert stable.setup.tp == 106.4


def test_stabilize_mismatched_previous_raises() -> None:
    """Hvis previous er fra feil slot, skal det detekteres (caller-bug)."""
    gold = _basic_buy_setup()
    # Bygg en previous med feil slot-ID (SELL i stedet for BUY)
    prev_wrong = StableSetup(
        setup_id=compute_setup_id("Gold", Direction.SELL, Horizon.SCALP),
        first_seen=NOW,
        last_updated=NOW,
        setup=gold,  # ironisk; bare setup_id sjekkes
    )
    with pytest.raises(ValueError, match="does not match"):
        stabilize_setup(gold, previous=prev_wrong, now=LATER)


# ---------------------------------------------------------------------------
# apply_hysteresis_batch
# ---------------------------------------------------------------------------


def test_apply_batch_with_no_snapshot() -> None:
    setups = [_basic_buy_setup()]
    out = apply_hysteresis_batch(setups, previous_snapshot=None, now=NOW)
    assert len(out) == 1
    assert out[0].first_seen == NOW
    assert out[0].last_updated == NOW


def test_apply_batch_matches_setups_by_slot() -> None:
    """Snapshot med flere slots; hver setup skal matche sin egen."""
    buy = _basic_buy_setup()
    sell_setup = build_setup(
        instrument="Gold",
        direction=Direction.SELL,
        horizon=Horizon.SCALP,
        current_price=98.0,
        atr=1.0,
        levels=[
            _lvl(100.0, LevelType.SWING_HIGH, 0.8),
            _lvl(94.0, LevelType.SWING_LOW, 0.8),
        ],
    )
    assert sell_setup is not None

    snapshot = SetupSnapshot(
        run_ts=NOW,
        setups=[_prev_with(buy), _prev_with(sell_setup)],
    )

    # Ny batch: en setup per slot, med små endringer
    new_buy = buy.model_copy(update={"sl": 99.75})  # innenfor buffer
    new_sell = sell_setup.model_copy(update={"sl": 100.25})  # innenfor buffer

    out = apply_hysteresis_batch([new_buy, new_sell], previous_snapshot=snapshot, now=LATER)
    assert len(out) == 2
    # begge SL stabilisert tilbake til forrige
    by_id = {s.setup_id: s for s in out}
    buy_stable = by_id[compute_setup_id("Gold", Direction.BUY, Horizon.SCALP)]
    sell_stable = by_id[compute_setup_id("Gold", Direction.SELL, Horizon.SCALP)]
    assert buy_stable.setup.sl == 99.7
    assert sell_stable.setup.sl == 100.3


def test_apply_batch_new_setup_not_in_snapshot() -> None:
    """Setup som ikke fantes i snapshot får previous=None."""
    snapshot = SetupSnapshot(run_ts=NOW, setups=[])
    out = apply_hysteresis_batch([_basic_buy_setup()], previous_snapshot=snapshot, now=LATER)
    assert out[0].first_seen == LATER


# ---------------------------------------------------------------------------
# SetupSnapshot.find
# ---------------------------------------------------------------------------


def test_snapshot_find_returns_matching_slot() -> None:
    buy = _basic_buy_setup()
    snap = SetupSnapshot(run_ts=NOW, setups=[_prev_with(buy)])
    found = snap.find("Gold", Direction.BUY, Horizon.SCALP)
    assert found is not None
    assert found.setup == buy


def test_snapshot_find_returns_none_when_missing() -> None:
    snap = SetupSnapshot(run_ts=NOW, setups=[])
    assert snap.find("Gold", Direction.BUY, Horizon.SCALP) is None


# ---------------------------------------------------------------------------
# Snapshot I/O
# ---------------------------------------------------------------------------


def test_snapshot_save_and_load_roundtrip(tmp_path: Path) -> None:
    buy = _basic_buy_setup()
    snap = SetupSnapshot(run_ts=NOW, setups=[_prev_with(buy)])
    db = tmp_path / "last_run.json"

    save_snapshot(snap, path=db)
    loaded = load_snapshot(path=db)

    assert loaded is not None
    assert loaded.run_ts == NOW
    assert len(loaded.setups) == 1
    assert loaded.setups[0].setup == buy


def test_snapshot_load_missing_file_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.json"
    assert load_snapshot(path=missing) is None


def test_snapshot_save_creates_parent_dirs(tmp_path: Path) -> None:
    snap = SetupSnapshot(run_ts=NOW, setups=[])
    target = tmp_path / "nested" / "subdir" / "last_run.json"
    save_snapshot(snap, path=target)
    assert target.exists()


def test_snapshot_save_is_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    """Etter vellykket save skal .tmp-fila være borte."""
    snap = SetupSnapshot(run_ts=NOW, setups=[])
    target = tmp_path / "last_run.json"
    save_snapshot(snap, path=target)
    assert target.exists()
    assert not target.with_suffix(target.suffix + ".tmp").exists()


# ---------------------------------------------------------------------------
# Pipeline-integrasjon: flere kjøringer bevarer first_seen
# ---------------------------------------------------------------------------


def test_multiple_runs_preserve_first_seen(tmp_path: Path) -> None:
    """Simuler 3 pipeline-kjøringer: first_seen skal låses ved første."""
    snap_path = tmp_path / "last_run.json"
    base_setup = _basic_buy_setup()

    # Run 1: første gang, ingen snapshot
    snap1_setups = apply_hysteresis_batch(
        [base_setup], previous_snapshot=load_snapshot(snap_path), now=NOW
    )
    save_snapshot(SetupSnapshot(run_ts=NOW, setups=snap1_setups), path=snap_path)

    # Run 2: 4 timer senere, liten SL-endring
    run2_setup = base_setup.model_copy(update={"sl": 99.75})
    snap2_setups = apply_hysteresis_batch(
        [run2_setup], previous_snapshot=load_snapshot(snap_path), now=LATER
    )
    save_snapshot(SetupSnapshot(run_ts=LATER, setups=snap2_setups), path=snap_path)

    # Run 3: enda 4 timer senere, annen liten endring
    even_later = LATER + timedelta(hours=4)
    run3_setup = base_setup.model_copy(update={"sl": 99.72})
    snap3_setups = apply_hysteresis_batch(
        [run3_setup], previous_snapshot=load_snapshot(snap_path), now=even_later
    )

    # first_seen skal være NOW (fra run 1), last_updated skal være even_later
    final = snap3_setups[0]
    assert final.first_seen == NOW
    assert final.last_updated == even_later
    # SL skal fortsatt være 99.7 (hysterese holdt den stabil gjennom tre runs)
    assert final.setup.sl == 99.7
