"""Tester for bot.comms — signal-fetch, push-prices, batch-commit, adaptive poll.

Dekker:
- adaptive_poll_interval: signals_data med/uten SCALP watchlist
- assemble_prices_from_state: trading + feed kombinert
- SignalComms.fetch_signals: HTTP 200, 500, network error, schema-warning
- SignalComms.fetch_kill_ids: liste, dict {signal_ids}, feil
- SignalComms.push_prices: tom dict, HTTP 200, nettverks-feil
- fetch_with_retry: 5xx retries, 4xx propagate, nettverk retry
- fetch_once returnerer FetchResult med begge delene
- commit_daily_trade_log: no-log, ikke-repo, utenfor-repo, add-fail,
  commit-uten-endringer, commit-suksess
- Schema-versjon warnes kun én gang per ukjent versjon
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from bedrock.bot.comms import (
    DEFAULT_TRADE_LOG_PATH,
    SUPPORTED_SCHEMA_VERSIONS,
    FetchResult,
    SignalComms,
    adaptive_poll_interval,
    assemble_prices_from_state,
    commit_daily_trade_log,
)
from bedrock.bot.config import PollingConfig, StartupOnlyConfig
from bedrock.bot.safety import SafetyMonitor


@pytest.fixture
def safety(tmp_path: Path) -> SafetyMonitor:
    return SafetyMonitor(state_path=tmp_path / "state.json")


@pytest.fixture
def startup_cfg() -> StartupOnlyConfig:
    return StartupOnlyConfig(signal_url="http://test.local:5100")


@pytest.fixture
def comms(safety: SafetyMonitor, startup_cfg: StartupOnlyConfig) -> SignalComms:
    session = MagicMock(spec=requests.Session)
    return SignalComms(
        startup_cfg=startup_cfg,
        api_key="test-key",
        safety=safety,
        session=session,
    )


# ─────────────────────────────────────────────────────────────
# Rene funksjoner
# ─────────────────────────────────────────────────────────────


def test_adaptive_interval_default_when_no_data() -> None:
    cfg = PollingConfig()
    assert adaptive_poll_interval(None, cfg) == cfg.default_seconds
    assert adaptive_poll_interval({}, cfg) == cfg.default_seconds


def test_adaptive_interval_returns_short_when_scalp_watchlist() -> None:
    cfg = PollingConfig()
    data = {
        "signals": [
            {"horizon": "SCALP", "status": "watchlist"},
            {"horizon": "SWING", "status": "active"},
        ]
    }
    assert adaptive_poll_interval(data, cfg) == cfg.scalp_active_seconds


def test_adaptive_interval_default_when_only_swing() -> None:
    cfg = PollingConfig()
    data = {"signals": [{"horizon": "SWING", "status": "watchlist"}]}
    assert adaptive_poll_interval(data, cfg) == cfg.default_seconds


def test_adaptive_interval_default_when_scalp_not_watchlist() -> None:
    cfg = PollingConfig()
    data = {"signals": [{"horizon": "SCALP", "status": "closed"}]}
    assert adaptive_poll_interval(data, cfg) == cfg.default_seconds


# ─────────────────────────────────────────────────────────────
# Prices assembler
# ─────────────────────────────────────────────────────────────


def test_assemble_prices_trading_only() -> None:
    sm = {"EURUSD": 1, "GOLD": 2}
    feed = {}
    bids = {1: 1.12345, 2: 2000.50}
    prices = assemble_prices_from_state(sm, feed, bids)
    assert prices["EURUSD"] == {"value": 1.12345}
    assert prices["Gold"] == {"value": 2000.5}


def test_assemble_prices_feed_only() -> None:
    sm = {}
    feed = {"BTC": 100, "NatGas": 101}
    bids = {100: 50000.0, 101: 3.25}
    prices = assemble_prices_from_state(sm, feed, bids)
    assert prices["BTC"] == {"value": 50000.0}
    assert prices["NatGas"] == {"value": 3.25}


def test_assemble_prices_combined() -> None:
    sm = {"EURUSD": 1}
    feed = {"BTC": 2}
    bids = {1: 1.12, 2: 50000.0}
    prices = assemble_prices_from_state(sm, feed, bids)
    assert "EURUSD" in prices
    assert "BTC" in prices


def test_assemble_skips_missing_bids() -> None:
    sm = {"EURUSD": 1, "GOLD": 2}
    # Kun sid 1 har bid
    bids = {1: 1.10}
    prices = assemble_prices_from_state(sm, {}, bids)
    assert "EURUSD" in prices
    assert "Gold" not in prices


# ─────────────────────────────────────────────────────────────
# SignalComms — fetch_signals
# ─────────────────────────────────────────────────────────────


def test_fetch_signals_200_returns_data_and_records_success(
    comms: SignalComms,
) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"signals": [], "schema_version": "2.1"}
    comms._session.get.return_value = mock_resp  # type: ignore[attr-defined]

    data = comms.fetch_signals()
    assert data == {"signals": [], "schema_version": "2.1"}
    assert comms.latest_signals == data
    assert comms._safety.server_frozen is False
    assert comms._safety.fetch_fail_count == 0


def test_fetch_signals_fires_on_signals_callback(
    safety: SafetyMonitor, startup_cfg: StartupOnlyConfig
) -> None:
    on_signals = MagicMock()
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"signals": []}
    session.get.return_value = mock_resp

    comms = SignalComms(
        startup_cfg=startup_cfg,
        api_key="k",
        safety=safety,
        on_signals=on_signals,
        session=session,
    )
    comms.fetch_signals()
    on_signals.assert_called_once_with({"signals": []})


def test_fetch_signals_500_records_failure(comms: SignalComms) -> None:
    # Alle retries får 500
    mock_resp = MagicMock(status_code=500)
    comms._session.get.return_value = mock_resp  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep"):
        data = comms.fetch_signals()
    assert data is None
    assert comms._safety.server_frozen is True
    assert comms._safety.fetch_fail_count == 1


def test_fetch_signals_network_error_records_failure(comms: SignalComms) -> None:
    comms._session.get.side_effect = requests.exceptions.ConnectionError("boom")  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep"):
        data = comms.fetch_signals()
    assert data is None
    assert comms._safety.server_frozen is True


def test_fetch_signals_warns_once_per_unknown_schema(
    comms: SignalComms, caplog: pytest.LogCaptureFixture
) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"signals": [], "schema_version": "99.9"}
    comms._session.get.return_value = mock_resp  # type: ignore[attr-defined]

    with caplog.at_level("WARNING", logger="bedrock.bot.comms"):
        comms.fetch_signals()
        comms.fetch_signals()  # andre gang skal IKKE warne igjen

    schema_warnings = [rec for rec in caplog.records if "SCHEMA" in rec.message]
    assert len(schema_warnings) == 1


def test_fetch_signals_known_schema_no_warning(
    comms: SignalComms, caplog: pytest.LogCaptureFixture
) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"signals": [], "schema_version": "2.1"}
    comms._session.get.return_value = mock_resp  # type: ignore[attr-defined]
    with caplog.at_level("WARNING", logger="bedrock.bot.comms"):
        comms.fetch_signals()
    assert not any("SCHEMA" in rec.message for rec in caplog.records)


def test_fetch_signals_bad_json_records_failure(comms: SignalComms) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.side_effect = ValueError("not json")
    comms._session.get.return_value = mock_resp  # type: ignore[attr-defined]
    data = comms.fetch_signals()
    assert data is None
    assert comms._safety.server_frozen is True


def test_supported_schema_versions_contains_core() -> None:
    assert "2.1" in SUPPORTED_SCHEMA_VERSIONS
    assert "2.0" in SUPPORTED_SCHEMA_VERSIONS
    assert "1.0" in SUPPORTED_SCHEMA_VERSIONS


# ─────────────────────────────────────────────────────────────
# Retry-logikk
# ─────────────────────────────────────────────────────────────


def test_retry_5xx_then_success(comms: SignalComms) -> None:
    resp500 = MagicMock(status_code=500)
    resp200 = MagicMock(status_code=200)
    resp200.json.return_value = {"signals": []}
    comms._session.get.side_effect = [resp500, resp200]  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep") as sleep_mock:
        data = comms.fetch_signals()
    assert data == {"signals": []}
    # sleep ble kalt én gang mellom retries
    assert sleep_mock.call_count >= 1


def test_retry_4xx_not_retried(comms: SignalComms) -> None:
    resp404 = MagicMock(status_code=404)
    comms._session.get.return_value = resp404  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep"):
        data = comms.fetch_signals()
    assert data is None
    # Skal KUN ha kalt én gang (ingen retry på 4xx)
    assert comms._session.get.call_count == 1  # type: ignore[attr-defined]


def test_retry_network_error_retries_up_to_3_times(comms: SignalComms) -> None:
    comms._session.get.side_effect = requests.exceptions.ConnectionError("x")  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep"):
        comms.fetch_signals()
    # 3 forsøk totalt
    assert comms._session.get.call_count == 3  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────
# fetch_kill_ids
# ─────────────────────────────────────────────────────────────


def test_fetch_kill_ids_list_response(comms: SignalComms) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = ["sig-1", "sig-2"]
    comms._session.get.return_value = resp  # type: ignore[attr-defined]
    ids = comms.fetch_kill_ids()
    assert ids == ["sig-1", "sig-2"]


def test_fetch_kill_ids_dict_response(comms: SignalComms) -> None:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"signal_ids": ["a", "b"]}
    comms._session.get.return_value = resp  # type: ignore[attr-defined]
    ids = comms.fetch_kill_ids()
    assert ids == ["a", "b"]


def test_fetch_kill_ids_fires_callback(
    safety: SafetyMonitor, startup_cfg: StartupOnlyConfig
) -> None:
    on_kill = MagicMock()
    session = MagicMock(spec=requests.Session)
    resp = MagicMock(status_code=200)
    resp.json.return_value = ["killme"]
    session.get.return_value = resp

    comms = SignalComms(
        startup_cfg=startup_cfg,
        api_key="k",
        safety=safety,
        on_kill_ids=on_kill,
        session=session,
    )
    comms.fetch_kill_ids()
    on_kill.assert_called_once_with(["killme"])


def test_fetch_kill_ids_empty_list_no_callback(
    safety: SafetyMonitor, startup_cfg: StartupOnlyConfig
) -> None:
    on_kill = MagicMock()
    session = MagicMock(spec=requests.Session)
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    session.get.return_value = resp

    comms = SignalComms(
        startup_cfg=startup_cfg,
        api_key="k",
        safety=safety,
        on_kill_ids=on_kill,
        session=session,
    )
    ids = comms.fetch_kill_ids()
    assert ids == []
    on_kill.assert_not_called()


def test_fetch_kill_ids_network_error_returns_empty(comms: SignalComms) -> None:
    comms._session.get.side_effect = requests.exceptions.ConnectionError("x")  # type: ignore[attr-defined]
    with patch("bedrock.bot.comms.time.sleep"):
        ids = comms.fetch_kill_ids()
    assert ids == []
    # Kill-fail fryser IKKE bot
    assert comms._safety.server_frozen is False


# ─────────────────────────────────────────────────────────────
# push_prices
# ─────────────────────────────────────────────────────────────


def test_push_prices_empty_returns_false(comms: SignalComms) -> None:
    assert comms.push_prices({}) is False


def test_push_prices_200_returns_true(comms: SignalComms) -> None:
    resp = MagicMock(status_code=200)
    comms._session.post.return_value = resp  # type: ignore[attr-defined]
    ok = comms.push_prices({"EURUSD": {"value": 1.1}})
    assert ok is True


def test_push_prices_500_returns_false(comms: SignalComms) -> None:
    resp = MagicMock(status_code=500)
    comms._session.post.return_value = resp  # type: ignore[attr-defined]
    assert comms.push_prices({"X": {"value": 1.0}}) is False


def test_push_prices_network_error_returns_false(comms: SignalComms) -> None:
    comms._session.post.side_effect = requests.exceptions.Timeout("x")  # type: ignore[attr-defined]
    assert comms.push_prices({"X": {"value": 1.0}}) is False


def test_push_prices_sends_auth_header(comms: SignalComms) -> None:
    resp = MagicMock(status_code=200)
    comms._session.post.return_value = resp  # type: ignore[attr-defined]
    comms.push_prices({"EURUSD": {"value": 1.1}})
    call = comms._session.post.call_args  # type: ignore[attr-defined]
    assert call.kwargs["headers"]["X-API-Key"] == "test-key"


# ─────────────────────────────────────────────────────────────
# fetch_once
# ─────────────────────────────────────────────────────────────


def test_fetch_once_returns_both_signals_and_kill_ids(comms: SignalComms) -> None:
    resp_sig = MagicMock(status_code=200)
    resp_sig.json.return_value = {"signals": []}
    resp_kill = MagicMock(status_code=200)
    resp_kill.json.return_value = ["kill1"]
    comms._session.get.side_effect = [resp_sig, resp_kill]  # type: ignore[attr-defined]
    result = comms.fetch_once()
    assert isinstance(result, FetchResult)
    assert result.signals_data == {"signals": []}
    assert result.kill_ids == ["kill1"]


# ─────────────────────────────────────────────────────────────
# commit_daily_trade_log
# ─────────────────────────────────────────────────────────────


def test_commit_no_log_file_returns_true(tmp_path: Path) -> None:
    missing_log = tmp_path / "nothing.jsonl"
    ok = commit_daily_trade_log(missing_log, date(2026, 4, 24), tmp_path)
    assert ok is True


def test_commit_not_a_repo_returns_false(tmp_path: Path) -> None:
    log_file = tmp_path / "log.jsonl"
    log_file.write_text("trade1\n")
    # tmp_path har ingen .git
    ok = commit_daily_trade_log(log_file, date(2026, 4, 24), tmp_path)
    assert ok is False


def test_commit_log_outside_repo_returns_false(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("x")
    ok = commit_daily_trade_log(outside, date(2026, 4, 24), repo)
    assert ok is False


def test_commit_success_calls_git_add_and_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    log_file = repo / "data" / "bot" / "log.jsonl"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("trade\n")

    add_result = MagicMock(returncode=0, stdout="", stderr="")
    commit_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=[add_result, commit_result]) as run_mock:
        ok = commit_daily_trade_log(log_file, date(2026, 4, 24), repo)

    assert ok is True
    assert run_mock.call_count == 2
    # Første kall = git add
    add_args = run_mock.call_args_list[0].args[0]
    assert add_args[:2] == ["git", "add"]
    # Andre kall = git commit -m ...
    commit_args = run_mock.call_args_list[1].args[0]
    assert commit_args[:3] == ["git", "commit", "-m"]
    assert "2026-04-24" in commit_args[3]


def test_commit_add_fail_returns_false(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    log_file = repo / "log.jsonl"
    log_file.write_text("x")

    add_fail = MagicMock(returncode=1, stdout="", stderr="permission denied")
    with patch("subprocess.run", return_value=add_fail):
        ok = commit_daily_trade_log(log_file, date(2026, 4, 24), repo)
    assert ok is False


def test_commit_no_changes_still_returns_true(tmp_path: Path) -> None:
    """Hvis git-commit sier 'nothing to commit' skal vi regne det som success
    (filen er allerede i siste commit)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    log_file = repo / "log.jsonl"
    log_file.write_text("x")

    add_ok = MagicMock(returncode=0, stdout="", stderr="")
    commit_nothing = MagicMock(
        returncode=1, stdout="nothing to commit, working tree clean", stderr=""
    )
    with patch("subprocess.run", side_effect=[add_ok, commit_nothing]):
        ok = commit_daily_trade_log(log_file, date(2026, 4, 24), repo)
    assert ok is True


def test_commit_real_failure_returns_false(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    log_file = repo / "log.jsonl"
    log_file.write_text("x")

    add_ok = MagicMock(returncode=0, stdout="", stderr="")
    commit_fail = MagicMock(returncode=128, stdout="", stderr="pre-commit hook failed")
    with patch("subprocess.run", side_effect=[add_ok, commit_fail]):
        ok = commit_daily_trade_log(log_file, date(2026, 4, 24), repo)
    assert ok is False


# ─────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────


def test_default_trade_log_path_in_bedrock() -> None:
    assert "bedrock" in str(DEFAULT_TRADE_LOG_PATH)
    assert "scalp_edge" not in str(DEFAULT_TRADE_LOG_PATH)
