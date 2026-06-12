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
    business_hours_between,
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
    # Eldre fetchere
    assert "prices" in cfg.fetchers
    assert "cot_disaggregated" in cfg.fetchers
    assert "cot_legacy" in cfg.fetchers
    assert "fundamentals" in cfg.fetchers
    assert "weather" in cfg.fetchers
    assert "enso" in cfg.fetchers
    # Kartrommet-utvidelse
    assert "wasde" in cfg.fetchers
    assert "crop_progress" in cfg.fetchers
    assert "shipping" in cfg.fetchers  # session 113: bdi-rebrand
    assert "news_intel" in cfg.fetchers  # session 114: Google News RSS
    assert "crypto_sentiment" in cfg.fetchers  # session 115: F&G + CoinGecko
    # Smartere schedules — sanity-sjekker
    assert cfg.fetchers["wasde"].table == "wasde"
    assert cfg.fetchers["crop_progress"].cron == "0 23 * 4-11 1"  # apr-nov
    assert cfg.fetchers["shipping"].cron == "30 23 * * 1-5"  # mon-fri etter close
    assert cfg.fetchers["shipping"].table == "shipping_indices"
    assert cfg.fetchers["news_intel"].table == "news_intel"
    assert cfg.fetchers["news_intel"].cron == "30 6,18 * * *"  # 2× daglig
    assert cfg.fetchers["crypto_sentiment"].table == "crypto_sentiment"
    assert cfg.fetchers["crypto_sentiment"].cron == "0 7 * * *"  # daglig
    # Session 2026-06-12: daglige makro-fetchere + serie-filtrert staleness
    assert "fred_macro" in cfg.fetchers
    assert "yahoo_macro" in cfg.fetchers
    assert cfg.fetchers["fundamentals"].lookback_days == 150
    assert cfg.fetchers["fundamentals"].series_filter is not None
    assert cfg.fetchers["usda_psd_india_sugar"].series_prefix == "USDA_PSD_"
    assert cfg.fetchers["enso"].series_filter == ["NOAA_ONI"]


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


# ---------------------------------------------------------------------------
# Serie-filtrert staleness for delt fundamentals-tabell (2026-06-12)
# ---------------------------------------------------------------------------


def _fundamentals_spec(**overrides) -> FetcherSpec:
    base: dict = {
        "module": "bedrock.fetch.fred",
        "cron": "30 2 * * *",
        "stale_hours": 48,
        "table": "fundamentals",
        "ts_column": "date",
    }
    base.update(overrides)
    return FetcherSpec(**base)


def _write_fundamentals(store: DataStore, rows: list[tuple[str, str]]) -> None:
    df = pd.DataFrame(
        {
            "series_id": [r[0] for r in rows],
            "date": [r[1] for r in rows],
            "value": [1.0] * len(rows),
        }
    )
    store.append_fundamentals(df)


def test_fetcher_spec_rejects_filter_and_prefix_combo() -> None:
    with pytest.raises(Exception, match="series_filter og series_prefix"):
        _fundamentals_spec(series_filter=["DGS10"], series_prefix="USDA_")


def test_latest_observation_ts_series_filter(tmp_path: Path) -> None:
    """Filter måler kun egne serier — naboens ferske data maskerer ikke."""
    store = DataStore(tmp_path / "bedrock.db")
    _write_fundamentals(
        store,
        [("DGS10", "2024-06-01"), ("USDA_PSD_X", "2026-10-01")],
    )
    latest = latest_observation_ts(store, "fundamentals", "date", series_filter=["DGS10"])
    assert latest is not None
    assert latest.year == 2024


def test_latest_observation_ts_series_prefix(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "bedrock.db")
    _write_fundamentals(
        store,
        [("DGS10", "2026-01-01"), ("USDA_PSD_PROD", "2024-10-01"), ("USDA_PSD_EXP", "2024-09-01")],
    )
    latest = latest_observation_ts(store, "fundamentals", "date", series_prefix="USDA_PSD_")
    assert latest is not None
    assert (latest.year, latest.month) == (2024, 10)


def test_check_staleness_uses_spec_series_filter(tmp_path: Path) -> None:
    """Stale egen serie skal flagges selv om delt tabell har ferske rader."""
    store = DataStore(tmp_path / "bedrock.db")
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    _write_fundamentals(
        store,
        [("DGS10", "2024-05-31"), ("ANP_ETANOL", "2024-01-01")],
    )
    spec = _fundamentals_spec(series_prefix="ANP_", stale_hours=720)
    status = check_staleness("anp_ethanol", spec, store, now=now)
    assert status.is_stale is True  # 5 mnd > 720h — ikke maskert av DGS10


def test_check_staleness_future_dated_clamps_to_zero(tmp_path: Path) -> None:
    """USDA PSD marketing-year-rader er datert frem i tid → alder 0, ikke negativ."""
    store = DataStore(tmp_path / "bedrock.db")
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    _write_fundamentals(store, [("USDA_PSD_PROD", "2024-10-01")])
    spec = _fundamentals_spec(series_prefix="USDA_PSD_", stale_hours=720)
    status = check_staleness("usda_psd", spec, store, now=now)
    assert status.age_hours == 0.0
    assert status.is_stale is False


# ---------------------------------------------------------------------------
# US business-day calendar
# ---------------------------------------------------------------------------


def test_business_hours_weekend_excluded() -> None:
    # Fre 2026-05-22 12:00 UTC → Man 2026-05-25 12:00 UTC = 72 kalender-t
    # Med us_calendar: fre 12-23:59 (12t) + lør+søn 0 + man 00-12 (12t, men
    # 25.05 er Memorial Day → 0t) = 12.0 t
    start = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    assert business_hours_between(start, end) == pytest.approx(12.0, abs=0.01)


def test_business_hours_memorial_day_excluded() -> None:
    # 2026-05-25 (Memorial Day) er en mandag-holiday
    start = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc)
    assert business_hours_between(start, end) == pytest.approx(0.0, abs=0.01)


def test_business_hours_normal_weekday() -> None:
    # Tir 2026-05-19 00:00 → Ons 2026-05-20 06:00 = 30 timer business
    start = datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 20, 6, 0, tzinfo=timezone.utc)
    assert business_hours_between(start, end) == pytest.approx(30.0, abs=0.01)


def test_check_staleness_memorial_day_us_calendar(tmp_path: Path) -> None:
    """Regresjon for session 2026-05-26: FRED siste-data fredag 22.05,
    monitor kjørte tirsdag 26.05 04:30 UTC etter Memorial Day mandag.
    Med us_calendar=true skal status være fresh (business-hours < 48)."""
    store = DataStore(tmp_path / "bedrock.db")
    spec = FetcherSpec(
        module="bedrock.fetch.fred",
        cron="30 2 * * *",
        stale_hours=48,
        table="fundamentals",
        ts_column="date",
        us_calendar=True,
    )
    # Skriv én fundamentals-rad datert fredag 22.05
    fred_df = pd.DataFrame(
        {
            "date": ["2026-05-22"],
            "series_id": ["DGS10"],
            "value": [4.2],
        }
    )
    store.append_fundamentals(fred_df)

    now = datetime(2026, 5, 26, 4, 30, tzinfo=timezone.utc)
    status = check_staleness("fundamentals", spec, store, now=now)
    # Business-tid: fre 22 00:00-23:59 = 24t, lør+søn+man(holiday) = 0,
    # tir 26 00:00-04:30 = 4.5t → 28.5t ≪ 48t-stale_hours
    assert status.has_data is True
    assert status.is_stale is False
    assert status.age_hours is not None
    assert status.age_hours < 30.0


def test_check_staleness_us_calendar_still_stale_when_truly_old(tmp_path: Path) -> None:
    """us_calendar=true skal IKKE skjule reell staleness (data 2 uker gammel)."""
    store = DataStore(tmp_path / "bedrock.db")
    spec = FetcherSpec(
        module="bedrock.fetch.fred",
        cron="30 2 * * *",
        stale_hours=48,
        table="fundamentals",
        ts_column="date",
        us_calendar=True,
    )
    fred_df = pd.DataFrame({"date": ["2026-05-08"], "series_id": ["DGS10"], "value": [4.2]})
    store.append_fundamentals(fred_df)

    now = datetime(2026, 5, 26, 4, 30, tzinfo=timezone.utc)
    status = check_staleness("fundamentals", spec, store, now=now)
    assert status.is_stale is True
    assert status.age_hours is not None
    assert status.age_hours > 48.0


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
