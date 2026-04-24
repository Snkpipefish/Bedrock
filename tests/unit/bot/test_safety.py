"""Tester for bot.safety — daily-loss persist + fetch-fail-eskalering.

Dekker:
- Round-trip: opprett → add_loss → ny instans → state lastes
- rollover ved ny dag + on_rollover-callback kalles med (prev, new)
- rollover gjør IKKE tilbakeholder tap før callback har kjørt
- daily_loss_limit matcher max(pct × balance, nok-gulv)
- daily_loss_exceeded-flagg
- fetch-fail eskalering: INFO → WARNING → ERROR
- record_fetch_success clearer telling og logger gjenoppretting
- _load_state ignorer state fra tidligere dag
- atomic write (temp-fil + replace)
- negativ add_loss ignoreres
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from bedrock.bot.config import DailyLossConfig
from bedrock.bot.safety import (
    DEFAULT_DAILY_LOSS_STATE_PATH,
    SafetyMonitor,
)


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "bot" / "daily_loss_state.json"


@pytest.fixture
def monitor(state_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=state_path)


@pytest.fixture
def default_cfg() -> DailyLossConfig:
    return DailyLossConfig()  # 2.0 pct, 500 nok


# ─────────────────────────────────────────────────────────────
# Basic state
# ─────────────────────────────────────────────────────────────


def test_default_state_is_zero_and_today(monitor: SafetyMonitor) -> None:
    today = datetime.now(timezone.utc).date()
    assert monitor.daily_loss == 0.0
    assert monitor.daily_loss_date == today


def test_initial_flags_are_safe(monitor: SafetyMonitor) -> None:
    assert monitor.server_frozen is False
    assert monitor.bot_locked is False
    assert monitor.bot_locked_until is None
    assert monitor.fetch_fail_count == 0
    assert monitor.fetch_frozen_since is None


def test_default_path_is_in_bedrock() -> None:
    assert "bedrock" in str(DEFAULT_DAILY_LOSS_STATE_PATH)
    assert "scalp_edge" not in str(DEFAULT_DAILY_LOSS_STATE_PATH)


# ─────────────────────────────────────────────────────────────
# add_loss + persist + roundtrip
# ─────────────────────────────────────────────────────────────


def test_add_loss_accumulates(monitor: SafetyMonitor) -> None:
    monitor.add_loss(100.0)
    monitor.add_loss(50.0)
    assert monitor.daily_loss == 150.0


def test_add_loss_persists_to_disk(
    monitor: SafetyMonitor, state_path: Path
) -> None:
    monitor.add_loss(42.5)
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["daily_loss"] == 42.5
    assert data["date"] == monitor.daily_loss_date.isoformat()


def test_roundtrip_new_instance_reads_same_day(state_path: Path) -> None:
    m1 = SafetyMonitor(state_path=state_path)
    m1.add_loss(300.0)
    # Ny instans — skal laste fra disk
    m2 = SafetyMonitor(state_path=state_path)
    assert m2.daily_loss == 300.0
    assert m2.daily_loss_date == m1.daily_loss_date


def test_negative_add_loss_ignored(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="bedrock.bot.safety"):
        monitor.add_loss(-5.0)
    assert monitor.daily_loss == 0.0
    assert any("negativ" in rec.message.lower() for rec in caplog.records)


def test_load_ignores_state_from_previous_day(
    state_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"date": yesterday.isoformat(), "daily_loss": 999.0})
    )
    with caplog.at_level("INFO", logger="bedrock.bot.safety"):
        m = SafetyMonitor(state_path=state_path)
    # State fra i går skal IKKE brukes — dagens tap er 0
    assert m.daily_loss == 0.0
    assert m.daily_loss_date == datetime.now(timezone.utc).date()


def test_load_recovers_same_day_state(state_path: Path) -> None:
    today = datetime.now(timezone.utc).date()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"date": today.isoformat(), "daily_loss": 250.0})
    )
    m = SafetyMonitor(state_path=state_path)
    assert m.daily_loss == 250.0


def test_corrupt_state_file_handled_gracefully(
    state_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("not-valid-json")
    with caplog.at_level("WARNING", logger="bedrock.bot.safety"):
        m = SafetyMonitor(state_path=state_path)
    assert m.daily_loss == 0.0


def test_save_uses_atomic_write(
    monitor: SafetyMonitor, state_path: Path
) -> None:
    """Atomic write bør gi en temp-fil som replaces — verifiser at
    endelig fil eksisterer og ingen temp-rester er igjen."""
    monitor.add_loss(10.0)
    files = list(state_path.parent.iterdir())
    # Kun hoved-fila, ingen temp-rester
    assert len(files) == 1
    assert files[0] == state_path


# ─────────────────────────────────────────────────────────────
# Rollover + callback
# ─────────────────────────────────────────────────────────────


def test_reset_same_day_returns_false(monitor: SafetyMonitor) -> None:
    monitor.add_loss(100.0)
    assert monitor.reset_daily_loss_if_new_day() is False
    assert monitor.daily_loss == 100.0


def test_reset_new_day_resets_and_returns_true(state_path: Path) -> None:
    # Simuler at state er fra i går
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"date": yesterday.isoformat(), "daily_loss": 500.0})
    )
    # _load_state ignorerer i-går-state (ser den som dead), men la oss sette
    # state manuelt til yesterday for å teste rollover-path
    m = SafetyMonitor(state_path=state_path)
    # Gjør state til "yesterday med tap" direkte for å simulere at bot
    # har kjørt over midnatt
    m._state.date = yesterday
    m._state.daily_loss = 500.0
    assert m.reset_daily_loss_if_new_day() is True
    assert m.daily_loss == 0.0
    assert m.daily_loss_date == datetime.now(timezone.utc).date()


def test_rollover_callback_called_with_dates(state_path: Path) -> None:
    captured: list[tuple[date, date]] = []

    def cb(prev: date, new: date) -> None:
        captured.append((prev, new))

    m = SafetyMonitor(state_path=state_path, on_rollover=cb)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    m._state.date = yesterday
    m._state.daily_loss = 500.0
    m.reset_daily_loss_if_new_day()
    assert len(captured) == 1
    prev, new = captured[0]
    assert prev == yesterday
    assert new == datetime.now(timezone.utc).date()


def test_rollover_callback_exception_does_not_block_reset(
    state_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(_a: date, _b: date) -> None:
        raise RuntimeError("git-commit feilet")

    m = SafetyMonitor(state_path=state_path, on_rollover=boom)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    m._state.date = yesterday
    m._state.daily_loss = 500.0
    with caplog.at_level("ERROR", logger="bedrock.bot.safety"):
        result = m.reset_daily_loss_if_new_day()
    # Reset skjedde selv om callback kastet
    assert result is True
    assert m.daily_loss == 0.0


def test_rollover_callback_sees_pre_reset_state(state_path: Path) -> None:
    """Callback må kjøre FØR state resettes slik at den kan bruke
    gårsdagens dato i commit-melding."""
    observed: list[date] = []

    def cb(prev: date, _new: date) -> None:
        observed.append(prev)

    m = SafetyMonitor(state_path=state_path, on_rollover=cb)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    m._state.date = yesterday
    m.reset_daily_loss_if_new_day()
    assert observed == [yesterday]


# ─────────────────────────────────────────────────────────────
# Daily-loss-limit
# ─────────────────────────────────────────────────────────────


def test_limit_pct_wins_for_large_account(default_cfg: DailyLossConfig) -> None:
    # 2% av 100000 = 2000 > 500 nok-gulv
    limit = SafetyMonitor.daily_loss_limit(100_000, default_cfg)
    assert limit == 2000.0


def test_limit_nok_floor_wins_for_small_account(default_cfg: DailyLossConfig) -> None:
    # 2% av 10000 = 200 < 500 nok-gulv
    limit = SafetyMonitor.daily_loss_limit(10_000, default_cfg)
    assert limit == 500.0


def test_limit_zero_balance_returns_nok_floor(default_cfg: DailyLossConfig) -> None:
    assert SafetyMonitor.daily_loss_limit(0, default_cfg) == 500.0


def test_exceeded_flag_flips_at_limit(
    monitor: SafetyMonitor, default_cfg: DailyLossConfig
) -> None:
    # Balance 100000 → limit = 2000
    assert not monitor.daily_loss_exceeded(100_000, default_cfg)
    monitor.add_loss(1999.0)
    assert not monitor.daily_loss_exceeded(100_000, default_cfg)
    monitor.add_loss(2.0)
    assert monitor.daily_loss_exceeded(100_000, default_cfg)


# ─────────────────────────────────────────────────────────────
# Fetch-fail-eskalering
# ─────────────────────────────────────────────────────────────


def test_record_fetch_failure_first_logs_info(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="bedrock.bot.safety"):
        monitor.record_fetch_failure("HTTP 500")
    assert monitor.server_frozen is True
    assert monitor.fetch_fail_count == 1
    assert monitor.fetch_frozen_since is not None
    assert any(
        rec.levelno == logging.INFO and "feilet" in rec.message.lower()
        for rec in caplog.records
    )


def test_fetch_failure_escalates_to_warning_at_three(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    monitor.record_fetch_failure("x")  # 1 INFO
    monitor.record_fetch_failure("x")  # 2 INFO
    with caplog.at_level("WARNING", logger="bedrock.bot.safety"):
        monitor.record_fetch_failure("x")  # 3 WARNING
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_fetch_failure_error_every_10th(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    for _ in range(9):
        monitor.record_fetch_failure("x")
    # 10. kall → ERROR
    with caplog.at_level("ERROR", logger="bedrock.bot.safety"):
        monitor.record_fetch_failure("x")
    assert monitor.fetch_fail_count == 10
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_fetch_failure_no_error_between_tens(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    for _ in range(10):
        monitor.record_fetch_failure("x")
    caplog.clear()
    # Kall 11-19 skal IKKE gi nye ERROR-linjer (anti-spam)
    with caplog.at_level("ERROR", logger="bedrock.bot.safety"):
        for _ in range(9):
            monitor.record_fetch_failure("x")
    assert not any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_fetch_success_clears_state(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    monitor.record_fetch_failure("x")
    monitor.record_fetch_failure("x")
    assert monitor.server_frozen is True
    with caplog.at_level("INFO", logger="bedrock.bot.safety"):
        monitor.record_fetch_success()
    assert monitor.server_frozen is False
    assert monitor.fetch_fail_count == 0
    assert monitor.fetch_frozen_since is None
    assert any("gjenoppretter" in rec.message.lower() or
               "gjenopprettet" in rec.message.lower()
               for rec in caplog.records)


def test_fetch_success_noop_when_already_healthy(
    monitor: SafetyMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    # Uten forutgående feil skal success være stille
    with caplog.at_level("INFO", logger="bedrock.bot.safety"):
        monitor.record_fetch_success()
    assert not any("gjenopprettet" in rec.message.lower() for rec in caplog.records)
