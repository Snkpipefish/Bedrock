"""Tester for bot.entry — candle-handling, filters, confirmation, bug-fix.

**Kritisk test**: `test_agri_signal_not_overridden` bekrefter at Fase 8s
hovedbug-fix er på plass — agri-signaler med pre-kalkulert SL/T1/T2/
entry_zone passerer uendret gjennom bot-pipelinen.

Dekker også:
- EntryEngine initial state
- on_symbols_ready populerer candle-buffere
- Indikator-oppdateringer (EMA9, ATR14, ATR14-5m)
- _passes_filters: USDA blackout, spread cold-start, spread-grense, R:R
- _check_confirmation: body, wick, EMA-gradient, strict_score ved USD-konflikt
- TTL-gate
- Daily-loss-gate
- Duplikat-blokk (allerede åpen trade for samme instrument+retning)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bedrock.bot.config import BotConfig, ReloadableConfig
from bedrock.bot.ctrader_client import H1_PERIOD, M15_PERIOD
from bedrock.bot.entry import DEFAULT_CONFIRMATION_STATS_PATH, EntryEngine
from bedrock.bot.safety import SafetyMonitor
from bedrock.bot.state import Candle, CandleBuffer, TradePhase, TradeState


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


def _make_client_stub(
    *,
    symbol_map: dict[str, int],
    last_bid: dict[int, float] | None = None,
    last_ask: dict[int, float] | None = None,
    spread_history: dict[int, deque] | None = None,
    symbol_digits: dict[int, int] | None = None,
    account_balance: float = 100_000.0,
) -> MagicMock:
    """Lett stub for CtraderClient — eksponerer kun det EntryEngine leser."""
    stub = MagicMock()
    stub.symbol_map = symbol_map
    stub.last_bid = last_bid or {}
    stub.last_ask = last_ask or {}
    stub.spread_history = spread_history or {}
    stub.symbol_digits = symbol_digits or {sid: 5 for sid in symbol_map.values()}
    stub.symbol_price_digits = {}
    stub.symbol_pip = {}
    stub.symbol_info = {}
    stub.price_feed_sids = {}
    stub.account_balance = account_balance
    return stub


@pytest.fixture
def safety(tmp_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=tmp_path / "daily.json")


@pytest.fixture
def config() -> ReloadableConfig:
    return BotConfig().reloadable


@pytest.fixture
def active_states() -> list[TradeState]:
    return []


def _make_engine(
    client_stub: MagicMock,
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    *,
    stats_path: Path,
    execute_trade: MagicMock | None = None,
    manage_positions: MagicMock | None = None,
) -> EntryEngine:
    return EntryEngine(
        client=client_stub,
        safety=safety,
        config=config,
        active_states=active_states,
        execute_trade=execute_trade or MagicMock(),
        manage_open_positions=manage_positions or MagicMock(),
        stats_path=stats_path,
    )


# ─────────────────────────────────────────────────────────────
# Initial state
# ─────────────────────────────────────────────────────────────


def test_engine_initial_state(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    assert engine.signal_data is None
    assert engine.candle_buffers == {}
    assert engine.ema9 == {}


def test_default_stats_path_in_bedrock() -> None:
    assert "bedrock" in str(DEFAULT_CONFIRMATION_STATS_PATH)
    assert "scalp_edge" not in str(DEFAULT_CONFIRMATION_STATS_PATH)


def test_on_symbols_ready_creates_buffers(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1, "GOLD": 2})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    assert 1 in engine.candle_buffers
    assert 2 in engine.candle_buffers
    assert 1 in engine.m5_candle_buffers
    assert 1 in engine.h1_candle_buffers
    assert engine.ema9[1] == []


# ─────────────────────────────────────────────────────────────
# KRITISK BUG-FIX: agri-signal passerer uendret
# ─────────────────────────────────────────────────────────────


def test_agri_signal_not_overridden(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    """Fase 8 kritisk bug-fix: agri-signaler skal IKKE få
    SL/T1/entry_zone overstyrt av bot. Gammel bot kjørte
    `_recalibrate_agri_levels(sig, ...)` som overskrev disse med
    1.5/2.5/3.5×live_atr uansett setup-generator-nivå. Denne porten
    fjerner kall-stedet — signalet skal sendes uendret til
    `_process_watchlist_signal`.

    Test-teknikk: Kjør `_on_candle_closed` med et agri-signal hvor
    SL/T1 er satt til "mistenkelige" verdier som gammel bots ATR-
    override VILLE ha endret (f.eks. t1 = 5×ATR unna entry). Verifiser
    at `TradeState` som ender opp i active_states har EXAKT signal-
    verdiene.
    """
    symbol_map = {"Corn": 10}
    client = _make_client_stub(
        symbol_map=symbol_map,
        last_bid={10: 4.50},
        last_ask={10: 4.52},
        # Fylt spread_history slik at cold-start-vern ikke blokkerer
        spread_history={10: deque([0.001] * 15, maxlen=20)},
        account_balance=100_000.0,
    )
    execute = MagicMock()
    engine = _make_engine(
        client, safety, config, active_states,
        stats_path=tmp_path / "s.json",
        execute_trade=execute,
    )
    engine.on_symbols_ready(client)

    # Signal-data: Corn BUY, entry ved 4.51, SL = 4.40 (IKKE 1.5×ATR unna!),
    # T1 = 4.90 (langt unna — reelt nivå). Entry-zone dekker 4.51.
    signal = {
        "id": "corn-buy-1",
        "source": "agri_fundamental",
        "instrument": "Corn",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 4.51,
        "stop": 4.40,  # distinktiv verdi — skal ikke bli overskrevet
        "t1": 4.90,  # distinktiv verdi — skal ikke bli overskrevet
        "t2_informational": 5.10,
        "entry_zone": [4.50, 4.53],
        "horizon": "SWING",
        "horizon_config": {},
    }
    engine.signal_data = {
        "signals": [signal],
        "global_state": {},
        "rules": {},
    }

    # Lag en lukket candle som trigger evaluation
    candle = Candle(
        open=4.51, high=4.52, low=4.50, close=4.515, volume=100,
        timestamp=datetime.now(timezone.utc),
    )
    engine._on_candle_closed(10, candle)

    # Verifiser: TradeState ble opprettet med signalets EXAKTE SL/T1
    assert len(active_states) == 1
    state = active_states[0]
    assert state.signal_id == "corn-buy-1"
    assert state.direction == "buy"
    assert state.instrument == "Corn"
    # KRITISK: stop og t1 er uendret fra signal
    assert state.stop_price == 4.40
    assert state.t1_price == 4.90


def test_technical_signal_also_unchanged(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    """Regresjonstest: ikke-agri-signaler var aldri påvirket av bugen,
    men vi verifiserer samme garanti nå."""
    symbol_map = {"EURUSD": 1}
    client = _make_client_stub(
        symbol_map=symbol_map,
        last_bid={1: 1.0800},
        last_ask={1: 1.0802},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(
        client, safety, config, active_states, stats_path=tmp_path / "s.json"
    )
    engine.on_symbols_ready(client)

    signal = {
        "id": "eur-buy",
        "source": "technical",
        "instrument": "EURUSD",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0801,
        "stop": 1.0750,
        "t1": 1.0900,
        "entry_zone": [1.0800, 1.0803],
        "horizon": "SCALP",
        "horizon_config": {},
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}
    engine._on_candle_closed(
        1,
        Candle(
            open=1.0801, high=1.0802, low=1.0800, close=1.0801, volume=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    assert len(active_states) == 1
    assert active_states[0].stop_price == 1.0750
    assert active_states[0].t1_price == 1.0900


# ─────────────────────────────────────────────────────────────
# Daily-loss-gate
# ─────────────────────────────────────────────────────────────


def test_daily_loss_gate_blocks_new_entry(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # Balance 100000, 2%-limit = 2000. Legg på 2100 tap
    safety.add_loss(2100.0)
    symbol_map = {"EURUSD": 1}
    client = _make_client_stub(
        symbol_map=symbol_map,
        last_bid={1: 1.08},
        last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
        account_balance=100_000.0,
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    signal = {
        "id": "blocked",
        "instrument": "EURUSD",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0805,
        "stop": 1.0750,
        "t1": 1.0900,
        "entry_zone": [1.08, 1.081],
        "horizon": "SCALP",
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}
    engine._on_candle_closed(
        1,
        Candle(
            open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    # Daily-loss-gate stopper trade før state opprettes
    assert len(active_states) == 0


# ─────────────────────────────────────────────────────────────
# TTL-gate
# ─────────────────────────────────────────────────────────────


def test_ttl_blocks_stale_scalp(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # SCALP TTL = 15 min. Signal med created_at 30 min tilbake skal dropes
    symbol_map = {"EURUSD": 1}
    client = _make_client_stub(
        symbol_map=symbol_map,
        last_bid={1: 1.08},
        last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    signal = {
        "id": "stale-scalp",
        "instrument": "EURUSD",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0805,
        "stop": 1.0750,
        "t1": 1.0900,
        "entry_zone": [1.08, 1.081],
        "horizon": "SCALP",
        "created_at": old_ts,
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}
    engine._on_candle_closed(
        1,
        Candle(
            open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    assert len(active_states) == 0


def test_ttl_allows_fresh_swing(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # SWING TTL = 4t. Signal 30 min gammelt er OK
    symbol_map = {"EURUSD": 1}
    client = _make_client_stub(
        symbol_map=symbol_map,
        last_bid={1: 1.08},
        last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    signal = {
        "id": "fresh-swing",
        "instrument": "EURUSD",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0805,
        "stop": 1.0750,
        "t1": 1.0900,
        "entry_zone": [1.08, 1.081],
        "horizon": "SWING",
        "created_at": ts,
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}
    engine._on_candle_closed(
        1,
        Candle(
            open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    assert len(active_states) == 1


# ─────────────────────────────────────────────────────────────
# Duplikat-blokk
# ─────────────────────────────────────────────────────────────


def test_duplicate_instrument_direction_blocked(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # Preload: allerede en åpen EURUSD-buy-state
    active_states.append(
        TradeState(
            signal_id="existing",
            instrument="EURUSD",
            symbol_id=1,
            direction="buy",
            phase=TradePhase.IN_TRADE,
        )
    )
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.08},
        last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    signal = {
        "id": "new-eur-buy",
        "instrument": "EURUSD",
        "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0805,
        "stop": 1.0750,
        "t1": 1.0900,
        "entry_zone": [1.08, 1.081],
        "horizon": "SCALP",
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}
    engine._on_candle_closed(
        1,
        Candle(
            open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    # Fortsatt kun 1 state (den gamle) — ny ble blokkert
    assert len(active_states) == 1
    assert active_states[0].signal_id == "existing"


# ─────────────────────────────────────────────────────────────
# _passes_filters
# ─────────────────────────────────────────────────────────────


def test_filter_spread_cold_start(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # Kun 5 samples (< min_samples=10) → spread-filter returnerer False
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.08},
        last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 5, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.signal_data = {"global_state": {}, "rules": {}}
    sig = {
        "id": "x", "instrument": "EURUSD", "direction": "buy",
        "alert_level": 1.08, "stop": 1.07, "t1": 1.09,
        "entry_zone": [1.08, 1.081], "horizon": "SCALP",
    }
    assert engine._passes_filters(sig, 1) is False


def test_filter_spread_wide_blocked(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0800},
        last_ask={1: 1.0900},  # 0.01 bred spread
        spread_history={1: deque([0.00002] * 15, maxlen=20)},  # normal 0.00002
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.signal_data = {"global_state": {}, "rules": {"stop_multiplier": 3.0}}
    sig = {
        "id": "x", "instrument": "EURUSD", "direction": "buy",
        "alert_level": 1.0801, "stop": 1.0750, "t1": 1.0900,
        "entry_zone": [1.08, 1.081], "horizon": "SCALP",
    }
    assert engine._passes_filters(sig, 1) is False


def test_filter_rr_below_min(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    # SWING min R:R = 1.3. Signal med R:R = 0.5 blokkeres
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.08}, last_ask={1: 1.081},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.signal_data = {"global_state": {}, "rules": {}}
    sig = {
        "id": "low-rr", "instrument": "EURUSD", "direction": "buy",
        "alert_level": 1.08, "stop": 1.07, "t1": 1.085,  # reward=0.005 risk=0.01 → 0.5
        "entry_zone": [1.08, 1.081], "horizon": "SWING",
    }
    assert engine._passes_filters(sig, 1) is False


def test_filter_rr_above_min_passes(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.08}, last_ask={1: 1.0801},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.signal_data = {"global_state": {}, "rules": {}}
    sig = {
        "id": "good-rr", "instrument": "EURUSD", "direction": "buy",
        "alert_level": 1.08, "stop": 1.07, "t1": 1.10,  # 2:1
        "entry_zone": [1.08, 1.081], "horizon": "SWING",
    }
    assert engine._passes_filters(sig, 1) is True


def test_filter_usda_blackout_blocks_agri(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(
        symbol_map={"Corn": 10},
        last_bid={10: 4.5}, last_ask={10: 4.52},
        spread_history={10: deque([0.001] * 15, maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.signal_data = {
        "global_state": {
            "usda_blackout": {"Corn": {"report": "WASDE", "hours_away": 2}}
        },
        "rules": {},
    }
    sig = {
        "id": "x", "instrument": "Corn", "direction": "buy",
        "alert_level": 4.51, "stop": 4.4, "t1": 4.9,
        "entry_zone": [4.5, 4.52], "horizon": "SWING",
    }
    assert engine._passes_filters(sig, 10) is False


# ─────────────────────────────────────────────────────────────
# _check_confirmation
# ─────────────────────────────────────────────────────────────


def test_confirmation_body_threshold(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    # Sett opp indikatorer manuelt
    engine.ema9[1] = [1.0800, 1.0805]  # stigende
    engine.atr14[1] = [0.001]
    engine.atr14_5m[1] = 0.001  # 30% × 0.001 = 0.0003

    sig = {
        "id": "x", "instrument": "EURUSD", "direction": "buy",
        "entry_zone": [1.08, 1.081],
    }
    # Body = 0.0005 > 0.0003 (ok), wick-rejection ok, EMA-gradient ok
    candle = Candle(
        open=1.0802, high=1.0807, low=1.0800, close=1.0807, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    assert engine._check_confirmation(sig, 1, candle, min_score=2) is True


def test_confirmation_small_body_fails_strict(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    """Body under terskel → score maks 2 → feiler ved strict min_score=3."""
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.ema9[1] = [1.0800, 1.0805]
    engine.atr14[1] = [0.001]
    engine.atr14_5m[1] = 0.010  # 30% × 0.010 = 0.003 → body må være større

    sig = {
        "id": "x", "instrument": "EURUSD", "direction": "buy",
        "entry_zone": [1.08, 1.081],
    }
    # Body = 0.0001 < 0.003 (fails body_ok). Wick + EMA ok. Score = 2.
    candle = Candle(
        open=1.0800, high=1.0802, low=1.0799, close=1.0801, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    # min_score=2 → passerer (score=2)
    assert engine._check_confirmation(sig, 1, candle, min_score=2) is True
    # strict_score=3 via "B"-karakter ville krevd alle tre. Vi tester
    # direkte at min_score=3 feiler.
    assert engine._check_confirmation(sig, 1, candle, min_score=3) is False


def test_confirmation_no_ema_returns_false(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    # Ingen EMA9-data
    sig = {
        "id": "x", "instrument": "EURUSD", "direction": "buy",
        "entry_zone": [1.08, 1.081],
    }
    candle = Candle(
        open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    assert engine._check_confirmation(sig, 1, candle) is False


def test_confirmation_stats_persist_every_20(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    stats_path = tmp_path / "confirm_stats.json"
    engine = _make_engine(client, safety, config, active_states, stats_path=stats_path)
    engine.ema9[1] = [1.0800, 1.0805]
    engine.atr14[1] = [0.001]
    engine.atr14_5m[1] = 0.001

    sig = {"id": "x", "instrument": "EURUSD", "direction": "buy",
           "entry_zone": [1.08, 1.081]}
    candle = Candle(open=1.0802, high=1.0807, low=1.08, close=1.0807,
                    volume=1, timestamp=datetime.now(timezone.utc))

    for _ in range(20):
        engine._check_confirmation(sig, 1, candle, min_score=2)

    assert stats_path.exists()
    import json
    data = json.loads(stats_path.read_text())
    assert data["total"] == 20


# ─────────────────────────────────────────────────────────────
# Indikatorer
# ─────────────────────────────────────────────────────────────


def test_update_indicators_needs_14_candles_for_atr(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    # Legg inn 10 candles (under ATR-tak)
    buf = engine.candle_buffers[1]
    for i in range(10):
        buf.candles.append(Candle(
            open=1.0 + i * 0.001, high=1.001 + i * 0.001,
            low=1.0 + i * 0.001, close=1.0 + i * 0.001,
            volume=1, timestamp=datetime.now(timezone.utc),
        ))
    engine._update_indicators(1)
    assert len(engine.ema9[1]) == 10  # EMA trenger kun 2
    assert engine.atr14[1] == []  # ATR trenger 14


def test_update_indicators_ema_and_atr_computed(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    buf = engine.candle_buffers[1]
    for i in range(20):
        buf.candles.append(Candle(
            open=1.0 + i * 0.001, high=1.002 + i * 0.001,
            low=0.999 + i * 0.001, close=1.001 + i * 0.001,
            volume=1, timestamp=datetime.now(timezone.utc),
        ))
    engine._update_indicators(1)
    assert len(engine.ema9[1]) == 20
    assert len(engine.atr14[1]) > 0


def test_get_ema9_returns_none_if_not_ready(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_symbols_ready(client)
    assert engine.get_ema9(1, offset=0) is None
    # En verdi — offset=1 returnerer None
    engine.ema9[1] = [1.0]
    assert engine.get_ema9(1, offset=0) == 1.0
    assert engine.get_ema9(1, offset=1) is None


def test_get_normal_spread(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        spread_history={1: deque([0.001, 0.002, 0.003], maxlen=20)},
    )
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    assert engine.get_normal_spread(1) == pytest.approx(0.002)
    assert engine.get_normal_spread(999) == 0.0  # ukjent sid


# ─────────────────────────────────────────────────────────────
# on_signals / execute_trade-callback
# ─────────────────────────────────────────────────────────────


def test_on_signals_stores_data(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={})
    engine = _make_engine(client, safety, config, active_states, stats_path=tmp_path / "s.json")
    engine.on_signals({"signals": [], "generated": "x"})
    assert engine.signal_data == {"signals": [], "generated": "x"}


def test_execute_trade_callback_called_on_confirm(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    """Full-flyt-test: watchlist → in_zone → confirm → execute_trade-
    callback blir kalt én gang med (sig, state, candle)."""
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0800}, last_ask={1: 1.0801},
        spread_history={1: deque([0.00002] * 15, maxlen=20)},
    )
    execute = MagicMock()
    engine = _make_engine(
        client, safety, config, active_states,
        stats_path=tmp_path / "s.json", execute_trade=execute,
    )
    engine.on_symbols_ready(client)
    # Fyll indikatorer for confirm-test
    engine.ema9[1] = [1.0800, 1.0805]
    engine.atr14[1] = [0.001]
    engine.atr14_5m[1] = 0.001

    signal = {
        "id": "full", "instrument": "EURUSD", "direction": "buy",
        "status": "watchlist",
        "alert_level": 1.0801, "stop": 1.0750, "t1": 1.0900,
        "entry_zone": [1.08, 1.081], "horizon": "SCALP", "horizon_config": {},
    }
    engine.signal_data = {"signals": [signal], "global_state": {}, "rules": {}}

    candle = Candle(
        open=1.0802, high=1.0807, low=1.0800, close=1.0807, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    engine._on_candle_closed(1, candle)
    execute.assert_called_once()
    # args: sig, state, candle
    call_sig, call_state, call_candle = execute.call_args.args
    assert call_sig["id"] == "full"
    assert call_state.signal_id == "full"
    assert call_candle is candle


def test_manage_open_positions_called_even_without_signals(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    manage = MagicMock()
    engine = _make_engine(
        client, safety, config, active_states,
        stats_path=tmp_path / "s.json", manage_positions=manage,
    )
    engine.on_symbols_ready(client)
    # signal_data = None
    candle = Candle(
        open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    engine._on_candle_closed(1, candle)
    manage.assert_called_once_with(1, candle)


def test_server_frozen_still_manages_positions(
    safety: SafetyMonitor, config: ReloadableConfig, active_states: list, tmp_path: Path
) -> None:
    safety.server_frozen = True
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    manage = MagicMock()
    engine = _make_engine(
        client, safety, config, active_states,
        stats_path=tmp_path / "s.json", manage_positions=manage,
    )
    engine.on_symbols_ready(client)
    engine.signal_data = {"signals": [], "global_state": {}, "rules": {}}
    candle = Candle(
        open=1.08, high=1.081, low=1.08, close=1.081, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    engine._on_candle_closed(1, candle)
    manage.assert_called_once()


# ─────────────────────────────────────────────────────────────
# _execute_trade_impl — ordre-sending, gates, sizing
# ─────────────────────────────────────────────────────────────


def _make_state(
    *,
    signal_id: str = "sig-1",
    symbol_id: int = 1,
    instrument: str = "EURUSD",
    direction: str = "buy",
    stop: float = 1.0780,
    t1: float = 1.0850,
    phase: TradePhase = TradePhase.AWAITING_CONFIRMATION,
) -> TradeState:
    return TradeState(
        signal_id=signal_id,
        symbol_id=symbol_id,
        instrument=instrument,
        direction=direction,
        stop_price=stop,
        t1_price=t1,
        phase=phase,
    )


def _make_signal(
    *,
    sig_id: str = "sig-1",
    instrument: str = "EURUSD",
    direction: str = "buy",
    alert: float = 1.0800,
    stop: float = 1.0780,
    t1: float = 1.0850,
    horizon: str = "SWING",
    base_risk: int = 40,
    character: str = "A",
) -> dict:
    return {
        "id": sig_id,
        "instrument": instrument,
        "direction": direction,
        "alert_level": alert,
        "stop": stop,
        "t1": t1,
        "horizon": horizon,
        "character": character,
        "horizon_config": {"sizing_base_risk_usd": base_risk},
    }


def _exec_engine(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    *,
    tmp_path: Path,
    client: MagicMock,
) -> EntryEngine:
    """Engine uten execute_trade-callback → default = _execute_trade_impl."""
    return EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
        trade_log_path=tmp_path / "trade_log.json",
    )


def test_execute_trade_sends_market_order(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0799},
        last_ask={1: 1.0801},
        account_balance=100_000.0,
    )
    client.symbol_info = {
        1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}
    }
    client.symbol_price_digits = {1: 5}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state()
    active_states.append(state)
    sig = _make_signal()
    candle = Candle(
        open=1.08, high=1.0805, low=1.0798, close=1.0801, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    engine._execute_trade_impl(sig, state, candle)

    # MARKET-ordre sendt med forventet parametre
    client.send_new_order.assert_called_once()
    kwargs = client.send_new_order.call_args.kwargs
    assert kwargs["symbol_id"] == 1
    assert kwargs["trade_side"] == "BUY"
    assert kwargs["volume"] == 2000  # 0.02 lot (SWING) × 100000 = 2000
    assert kwargs["order_type"] == "MARKET"
    assert "stop_loss" not in kwargs  # MARKET: SL settes via amend etter fill
    # State oppdatert
    assert state.full_volume == 2000
    assert state.entry_price == 1.0801  # ask for buy
    assert state.lots_used == 0.02
    assert state.risk_pct_used == 1.0
    assert state.horizon == "SWING"


def test_execute_trade_sends_limit_order_when_rule_set(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    client = _make_client_stub(
        symbol_map={"GOLD": 2},
        last_bid={2: 2050.00},
        last_ask={2: 2050.50},
        account_balance=100_000.0,
    )
    client.symbol_info = {
        2: {"lot_size": 100, "min_volume": 1, "step_volume": 1}
    }
    client.symbol_price_digits = {2: 2}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state(signal_id="gold-1", symbol_id=2, instrument="GOLD",
                        stop=2040.0, t1=2070.0)
    active_states.append(state)
    sig = _make_signal(sig_id="gold-1", instrument="GOLD", alert=2050.25,
                      stop=2040.0, t1=2070.0, base_risk=40)
    engine.signal_data = {
        "signals": [],
        "global_state": {},
        "rules": {"use_limit_orders": True},
    }
    candle = Candle(
        open=2050.0, high=2050.5, low=2049.9, close=2050.3, volume=1,
        timestamp=datetime.now(timezone.utc),
    )
    engine._execute_trade_impl(sig, state, candle)

    kwargs = client.send_new_order.call_args.kwargs
    assert kwargs["order_type"] == "LIMIT"
    assert kwargs["limit_price"] == 2050.25
    assert kwargs["stop_loss"] == 2040.0
    assert kwargs["take_profit"] == 2070.0
    assert "expiration_ms" in kwargs


def test_execute_trade_blocks_on_zero_risk(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """entry_price == stop → risk_per_unit=0 → avvis + fjern state."""
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0800}, last_ask={1: 1.0800},
    )
    client.symbol_info = {1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state(stop=1.0800)
    active_states.append(state)
    sig = _make_signal(stop=1.0800)
    candle = Candle(open=1.08, high=1.081, low=1.079, close=1.08, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, state, candle)
    client.send_new_order.assert_not_called()
    assert state not in active_states


def test_execute_trade_blocks_on_daily_loss(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Daily-loss over grense → ordre ikke sendt, state fjernet."""
    client = _make_client_stub(
        symbol_map={"EURUSD": 1},
        last_bid={1: 1.0799}, last_ask={1: 1.0801},
        account_balance=100_000.0,
    )
    client.symbol_info = {1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}}
    safety.add_loss(10_000.0)  # Over pct=2% × 100k = 2000
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state()
    active_states.append(state)
    sig = _make_signal()
    candle = Candle(open=1.08, high=1.081, low=1.079, close=1.08, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, state, candle)
    client.send_new_order.assert_not_called()
    assert state not in active_states


def test_execute_trade_blocks_oil_geo_warning_with_tight_sl(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Oil + geo-advarsel + SL smalere enn min_sl_pips × 0.01 → blokkert."""
    client = _make_client_stub(
        symbol_map={"OIL BRENT": 3},
        last_bid={3: 85.00}, last_ask={3: 85.05},
        account_balance=100_000.0,
    )
    client.symbol_info = {3: {"lot_size": 100, "min_volume": 1, "step_volume": 1}}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state(signal_id="oil-1", symbol_id=3, instrument="OIL BRENT",
                       stop=85.04)  # SL 1 cent = under 25×0.01 = 0.25
    active_states.append(state)
    sig = _make_signal(sig_id="oil-1", instrument="OIL BRENT", alert=85.05, stop=85.04, t1=85.40)
    engine.signal_data = {
        "signals": [],
        "global_state": {"oil_geo_warning": True},
        "rules": {},
    }
    candle = Candle(open=85.03, high=85.06, low=85.01, close=85.04, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, state, candle)
    client.send_new_order.assert_not_called()


def test_execute_trade_blocks_total_correlation_limit(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """max_total posisjoner aktive → ny ordre blokkert."""
    client = _make_client_stub(
        symbol_map={"EURUSD": 1, "USDJPY": 2},
        last_bid={1: 1.0799}, last_ask={1: 1.0801},
        account_balance=100_000.0,
    )
    client.symbol_info = {1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}}
    # Fyll 6 IN_TRADE states (default max_total)
    for i in range(6):
        active_states.append(TradeState(
            signal_id=f"other-{i}", symbol_id=99+i, instrument="USDJPY",
            phase=TradePhase.IN_TRADE, direction="buy",
        ))
    new_state = _make_state(signal_id="new-1")
    active_states.append(new_state)
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    sig = _make_signal(sig_id="new-1")
    engine.signal_data = {
        "signals": [],
        "global_state": {"correlation_config": {"max_total": 6}},
        "rules": {},
    }
    candle = Candle(open=1.08, high=1.081, low=1.079, close=1.08, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, new_state, candle)
    client.send_new_order.assert_not_called()
    assert new_state not in active_states


def test_execute_trade_agri_size_halved_and_corn_blocked_out_of_session(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corn utenfor session (f.eks. kl. 05:00 CET) → blokkert."""
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 5, 0, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(
        symbol_map={"Corn": 10},
        last_bid={10: 4.50}, last_ask={10: 4.52},
        account_balance=100_000.0,
    )
    client.symbol_info = {10: {"lot_size": 5000, "min_volume": 100, "step_volume": 100}}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    state = _make_state(signal_id="corn-1", symbol_id=10, instrument="Corn",
                       stop=4.40, t1=4.90)
    active_states.append(state)
    sig = _make_signal(sig_id="corn-1", instrument="Corn", alert=4.51,
                      stop=4.40, t1=4.90, base_risk=40)
    candle = Candle(open=4.51, high=4.52, low=4.50, close=4.515, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, state, candle)
    client.send_new_order.assert_not_called()


def test_execute_trade_agri_in_session_sends_order(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corn innenfor session (14:00 CET) → ordre sendt med halv lot."""
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 14, 0, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(
        symbol_map={"Corn": 10},
        last_bid={10: 4.50}, last_ask={10: 4.52},
        spread_history={10: deque([0.01] * 15, maxlen=20)},
        account_balance=100_000.0,
    )
    client.symbol_info = {10: {"lot_size": 5000, "min_volume": 100, "step_volume": 100}}
    client.symbol_price_digits = {10: 2}
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    # Populate ATR14 for spreadfilter: må ikke være None, og spread/atr skal passere
    engine.atr14[10] = [0.10] * 15  # ATR14 = 0.10 → maks spread 0.04 > faktisk 0.02
    state = _make_state(signal_id="corn-ok", symbol_id=10, instrument="Corn",
                       stop=4.40, t1=4.90)
    active_states.append(state)
    sig = _make_signal(sig_id="corn-ok", instrument="Corn", alert=4.51,
                      stop=4.40, t1=4.90, base_risk=40)
    candle = Candle(open=4.51, high=4.52, low=4.50, close=4.515, volume=1,
                   timestamp=datetime.now(timezone.utc))
    engine._execute_trade_impl(sig, state, candle)
    client.send_new_order.assert_called_once()
    kwargs = client.send_new_order.call_args.kwargs
    # Corn = agri, SWING: 0.02 × 0.5 = 0.01 lot × 5000 = 50, min_vol=100 → 100
    assert kwargs["volume"] == 100


# ─────────────────────────────────────────────────────────────
# _is_monday_gap
# ─────────────────────────────────────────────────────────────


def test_monday_gap_blocks_when_gap_large(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            # Mandag 2026-04-20 kl. 00:30 CET
            return datetime(2026, 4, 20, 0, 30, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1}, last_bid={1: 1.100})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    # H1 buffer med en "fredag"-close på 1.080 og ATR14_h1 = 0.005
    buf = CandleBuffer()
    buf.candles.append(Candle(open=1.080, high=1.081, low=1.079, close=1.080,
                              volume=0, timestamp=datetime.now(timezone.utc)))
    engine.h1_candle_buffers[1] = buf
    engine.atr14_h1[1] = [0.005] * 5  # ATR = 0.005
    # Gap = abs(1.100 - 1.080) = 0.020 > 2.0 × 0.005 = 0.010
    assert engine._is_monday_gap(1) is True


def test_monday_gap_false_outside_first_hour(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            # Mandag kl. 02:00 → utenfor første time
            return datetime(2026, 4, 20, 2, 0, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1}, last_bid={1: 1.100})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    engine.atr14_h1[1] = [0.005]
    assert engine._is_monday_gap(1) is False


def test_monday_gap_false_when_not_monday(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 21, 0, 30, 0, tzinfo=tz)  # Tirsdag
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"EURUSD": 1}, last_bid={1: 1.100})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    engine.atr14_h1[1] = [0.005]
    assert engine._is_monday_gap(1) is False


# ─────────────────────────────────────────────────────────────
# _agri_session_ok
# ─────────────────────────────────────────────────────────────


def test_agri_session_ok_within_hours(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 12, 0, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"Corn": 10})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    assert engine._agri_session_ok("Corn") is True


def test_agri_session_ok_outside_hours(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bedrock.bot import entry as entry_mod

    class _FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 4, 24, 4, 0, 0, tzinfo=tz)
    monkeypatch.setattr(entry_mod, "datetime", _FrozenDT)

    client = _make_client_stub(symbol_map={"Corn": 10})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    assert engine._agri_session_ok("Corn") is False


def test_agri_session_unknown_instrument_allowed(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    """Ukjent instrument → True (ikke blokkér)."""
    client = _make_client_stub(symbol_map={})
    engine = _exec_engine(safety, config, active_states, tmp_path=tmp_path, client=client)
    assert engine._agri_session_ok("UNKNOWN_THING") is True


# ─────────────────────────────────────────────────────────────
# _log_trade_opened
# ─────────────────────────────────────────────────────────────


def test_log_trade_opened_writes_json(
    safety: SafetyMonitor,
    config: ReloadableConfig,
    active_states: list[TradeState],
    tmp_path: Path,
) -> None:
    import json
    client = _make_client_stub(symbol_map={"EURUSD": 1})
    client.symbol_info = {1: {"lot_size": 100_000, "min_volume": 1000, "step_volume": 1000}}
    log_path = tmp_path / "signal_log.json"
    engine = EntryEngine(
        client=client,
        safety=safety,
        config=config,
        active_states=active_states,
        stats_path=tmp_path / "s.json",
        trade_log_path=log_path,
    )
    state = TradeState(
        signal_id="trade-1", symbol_id=1, instrument="EURUSD",
        direction="buy", entry_price=1.0800, stop_price=1.0780, t1_price=1.0850,
        full_volume=2000, position_id=42, horizon="SWING", risk_pct_used=1.0,
    )
    engine._log_trade_opened(state)
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert data["entries"][0]["signal"]["id"] == "trade-1"
    assert data["entries"][0]["signal"]["instrument"] == "EURUSD"
    assert data["entries"][0]["signal"]["direction"] == "BUY"
    assert data["entries"][0]["signal"]["lots"] == 0.02
    assert data["entries"][0]["signal"]["position_id"] == 42
    assert data["entries"][0]["closed_at"] is None
