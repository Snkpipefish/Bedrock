"""Tester for `bedrock.config.fetch` + `bedrock fetch status` CLI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli
from bedrock.config.fetch import (
    FetchConfig,
    FetchConfigError,
    FetcherSpec,
    check_staleness,
    latest_observation_ts,
    load_fetch_config,
    status_report,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_fetch_config_valid(tmp_path: Path) -> None:
    path = tmp_path / "fetch.yaml"
    path.write_text(
        dedent(
            """\
            fetchers:
              prices:
                module: bedrock.fetch.prices
                cron: "40 * * * 1-5"
                stale_hours: 2
                table: prices
                ts_column: ts
                on_failure: retry_with_backoff
            """
        )
    )
    cfg = load_fetch_config(path)
    assert isinstance(cfg, FetchConfig)
    assert "prices" in cfg.fetchers
    spec = cfg.fetchers["prices"]
    assert spec.module == "bedrock.fetch.prices"
    assert spec.stale_hours == 2.0
    assert spec.on_failure == "retry_with_backoff"


def test_load_fetch_config_default_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "fetch.yaml"
    path.write_text(
        dedent(
            """\
            fetchers:
              prices:
                module: bedrock.fetch.prices
                cron: "40 * * * 1-5"
                stale_hours: 2
                table: prices
            """
        )
    )
    cfg = load_fetch_config(path)
    assert cfg.fetchers["prices"].on_failure == "log_and_skip"
    assert cfg.fetchers["prices"].ts_column == "ts"


def test_load_fetch_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_fetch_config(Path("/tmp/does-not-exist-fetch.yaml"))


def test_load_fetch_config_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "fetch.yaml"
    path.write_text("")
    with pytest.raises(FetchConfigError, match="empty"):
        load_fetch_config(path)


def test_load_fetch_config_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "fetch.yaml"
    path.write_text(
        dedent(
            """\
            fetchers:
              prices:
                module: bedrock.fetch.prices
                cron: "40 * * * 1-5"
                stale_hours: 2
                table: prices
                unknown_field: bad
            """
        )
    )
    with pytest.raises(Exception):  # pydantic ValidationError
        load_fetch_config(path)


def test_load_fetch_config_on_checked_in_file() -> None:
    """Verifiser at repo-ens checked-in `config/fetch.yaml` parses."""
    repo_root = Path(__file__).resolve().parents[2]
    cfg = load_fetch_config(repo_root / "config" / "fetch.yaml")
    assert "prices" in cfg.fetchers
    assert "cot_disaggregated" in cfg.fetchers
    assert "fundamentals" in cfg.fetchers
    assert "weather" in cfg.fetchers


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def _price_spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.prices",
        cron="0 * * * *",
        stale_hours=24,
        table="prices",
        ts_column="ts",
    )


def test_latest_observation_ts_empty_table(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "empty.db")
    assert latest_observation_ts(store, "prices", "ts") is None


def test_latest_observation_ts_returns_most_recent(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-02"]),
            "open": [1.0, 1.0, 1.0],
            "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0],
            "close": [1.0, 1.0, 1.0],
            "volume": [100.0, 100.0, 100.0],
        }
    )
    store.append_prices("Gold", "D1", df)
    latest = latest_observation_ts(store, "prices", "ts")
    assert latest is not None
    assert latest.year == 2024
    assert latest.month == 1
    assert latest.day == 3
    assert latest.tzinfo is not None


def test_latest_observation_ts_unknown_table(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    assert latest_observation_ts(store, "does_not_exist", "ts") is None


def test_check_staleness_no_data(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "empty.db")
    status = check_staleness("prices", _price_spec(), store)
    assert status.has_data is False
    assert status.is_stale is True  # ingen data = stale per definisjon
    assert status.latest_observation is None
    assert status.age_hours is None


def test_check_staleness_fresh_data(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    # Hvis vi skriver data med ts "nå", burde status være fresh
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    df = pd.DataFrame(
        {
            "ts": [now - timedelta(hours=1)],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [100.0],
        }
    )
    store.append_prices("Gold", "D1", df)
    status = check_staleness("prices", _price_spec(), store, now=now)
    assert status.has_data is True
    assert status.is_stale is False
    assert status.age_hours == pytest.approx(1.0, abs=0.01)


def test_check_staleness_old_data(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    df = pd.DataFrame(
        {
            "ts": [now - timedelta(hours=50)],  # stale_hours=24
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [100.0],
        }
    )
    store.append_prices("Gold", "D1", df)
    status = check_staleness("prices", _price_spec(), store, now=now)
    assert status.has_data is True
    assert status.is_stale is True
    assert status.age_hours == pytest.approx(50.0, abs=0.1)


def test_status_report_iterates_all_fetchers(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    cfg = FetchConfig(
        fetchers={
            "prices": _price_spec(),
            "weather": FetcherSpec(
                module="bedrock.fetch.weather",
                cron="0 3 * * *",
                stale_hours=30,
                table="weather",
                ts_column="date",
            ),
        }
    )
    report = status_report(cfg, store)
    assert len(report) == 2
    names = {s.name for s in report}
    assert names == {"prices", "weather"}
    # Alle tomme (ingen data skrevet)
    assert all(not s.has_data for s in report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        dedent(
            """\
            fetchers:
              prices:
                module: bedrock.fetch.prices
                cron: "40 * * * 1-5"
                stale_hours: 24
                table: prices
            """
        )
    )


def test_cli_fetch_status_empty_db(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "fetch.yaml"
    _write_minimal_config(config)
    db = tmp_path / "bedrock.db"  # finnes ikke

    result = runner.invoke(cli, ["fetch", "status", "--config", str(config), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "prices" in result.output
    assert "NO_DATA" in result.output


def test_cli_fetch_status_with_fresh_data(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "fetch.yaml"
    _write_minimal_config(config)
    db = tmp_path / "bedrock.db"
    store = DataStore(db)
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime([datetime.now(timezone.utc)]),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [100.0],
        }
    )
    store.append_prices("Gold", "D1", df)

    result = runner.invoke(cli, ["fetch", "status", "--config", str(config), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "fresh" in result.output


def test_cli_fetch_status_json_output(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "fetch.yaml"
    _write_minimal_config(config)
    db = tmp_path / "bedrock.db"

    result = runner.invoke(
        cli,
        [
            "fetch",
            "status",
            "--config",
            str(config),
            "--db",
            str(db),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["name"] == "prices"
    assert payload[0]["has_data"] is False


def test_cli_fetch_status_missing_config(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        cli,
        [
            "fetch",
            "status",
            "--config",
            str(tmp_path / "nope.yaml"),
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_cli_fetch_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["fetch", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
