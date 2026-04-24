"""Tester for `bedrock.config.fetch_runner` + `bedrock fetch run` CLI."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli
from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import (
    all_runner_names,
    default_from_date,
    run_fetcher_by_name,
)
from bedrock.data.store import DataStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("FRED_API_KEY", None)
    yield
    if saved is not None:
        os.environ["FRED_API_KEY"] = saved


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


@pytest.fixture
def configs_dir(tmp_path: Path) -> tuple[Path, Path]:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "family_financial.yaml").write_text(
        dedent(
            """\
            aggregation: weighted_horizon
            horizons:
              SWING:
                family_weights: {trend: 1.0}
                max_score: 5.0
                min_score_publish: 0.5
            families:
              trend:
                drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.75, min_families: 1}
              A:      {min_pct_of_max: 0.55, min_families: 1}
              B:      {min_pct_of_max: 0.35, min_families: 1}
            """
        )
    )
    (defaults / "family_agri.yaml").write_text(
        dedent(
            """\
            aggregation: additive_sum
            max_score: 10
            min_score_publish: 3
            families:
              outlook:
                weight: 5
                drivers: [{name: sma200_align, weight: 1.0, params: {tf: D1}}]
            grade_thresholds:
              A_plus: {min_score: 8, min_families_active: 1}
              A:      {min_score: 5, min_families_active: 1}
              B:      {min_score: 3, min_families_active: 1}
            """
        )
    )
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "gold.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
              stooq_ticker: xauusd
              cot_contract: "GOLD - COMEX"
              cot_report: disaggregated
              fred_series_ids:
                - DGS10
            """
        )
    )
    (insts / "corn.yaml").write_text(
        dedent(
            """\
            inherits: family_agri
            instrument:
              id: Corn
              asset_class: grains
              ticker: ZC
              stooq_ticker: zc.f
              weather_region: us_cornbelt
              weather_lat: 40.75
              weather_lon: -96.75
            """
        )
    )
    return defaults, insts


def _spec(stale_hours: float = 24) -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.prices",
        cron="0 * * * *",
        stale_hours=stale_hours,
        table="prices",
        ts_column="ts",
    )


def _sample_bars(n: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-02", periods=n, freq="D"),
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [100.0] * n,
        }
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_all_registered_runners() -> None:
    names = all_runner_names()
    assert "prices" in names
    assert "cot_disaggregated" in names
    assert "cot_legacy" in names
    assert "fundamentals" in names
    assert "weather" in names


# ---------------------------------------------------------------------------
# Prices runner
# ---------------------------------------------------------------------------


def test_run_prices_iterates_all_instruments(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    calls: list[str] = []

    def fake_fetch(ticker, from_date, to_date, interval="d"):  # noqa: ARG001
        calls.append(ticker)
        return _sample_bars(2)

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "prices",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 5),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    # Både Gold og Corn har stooq_ticker
    assert set(calls) == {"xauusd", "zc.f"}
    assert result.ok_count == 2
    assert result.fail_count == 0
    assert result.total_rows == 4  # 2 instrumenter × 2 barer


def test_run_prices_instrument_filter(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    calls: list[str] = []

    def fake_fetch(ticker, from_date, to_date, interval="d"):  # noqa: ARG001
        calls.append(ticker)
        return _sample_bars(1)

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "prices",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
            instrument_filter="Gold",
        )

    assert calls == ["xauusd"]
    assert result.ok_count == 1


def test_run_prices_per_item_failure(store: DataStore, configs_dir) -> None:
    """Én feil skal ikke abortere resten."""
    defaults, insts = configs_dir

    def fake_fetch(ticker, from_date, to_date, interval="d"):  # noqa: ARG001
        if ticker == "xauusd":
            raise RuntimeError("HTTP 503")
        return _sample_bars(1)

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "prices",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert result.ok_count == 1
    assert result.fail_count == 1
    failed = next(i for i in result.items if not i.ok)
    assert failed.item_id == "Gold"
    assert "HTTP 503" in failed.error


# ---------------------------------------------------------------------------
# COT runner
# ---------------------------------------------------------------------------


def test_run_cot_disaggregated_only_matching_report(
    store: DataStore, configs_dir
) -> None:
    """Kun instrumenter med cot_report=disaggregated kalles."""
    defaults, insts = configs_dir
    calls: list[str] = []

    def fake_fetch(contract, from_date, to_date):  # noqa: ARG001
        calls.append(contract)
        return pd.DataFrame()  # tom → 0 rader skrevet

    with patch("bedrock.fetch.cot_cftc.fetch_cot_disaggregated", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "cot_disaggregated",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    # Kun Gold (Corn har ikke cot_contract i fixture)
    assert calls == ["GOLD - COMEX"]
    assert result.ok_count == 1


# ---------------------------------------------------------------------------
# Weather runner
# ---------------------------------------------------------------------------


def test_run_weather_only_agri_with_region(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    calls: list[tuple] = []

    def fake_fetch(region, lat, lon, from_date, to_date):  # noqa: ARG001
        calls.append((region, lat, lon))
        return pd.DataFrame(
            {
                "region": [region],
                "date": ["2024-01-02"],
                "tmax": [10.0],
                "tmin": [-2.0],
                "precip": [0.0],
                "gdd": [None],
            }
        )

    with patch("bedrock.fetch.weather.fetch_weather", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "weather",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    # Kun Corn har weather_region
    assert calls == [("us_cornbelt", 40.75, -96.75)]
    assert result.ok_count == 1


# ---------------------------------------------------------------------------
# Fundamentals runner
# ---------------------------------------------------------------------------


def test_run_fundamentals_without_key_fails_gracefully(
    store: DataStore, configs_dir
) -> None:
    defaults, insts = configs_dir
    # Ingen FRED_API_KEY satt, ingen secrets-fil
    with patch("bedrock.config.fetch_runner.get_secret", return_value=None):
        result = run_fetcher_by_name(
            "fundamentals",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert result.fail_count >= 1
    # Alle skal ha meldingen om manglende API-key
    for item in result.items:
        assert "FRED_API_KEY" in item.error


def test_run_fundamentals_with_key(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    os.environ["FRED_API_KEY"] = "test_key"

    def fake_fetch(series_id, api_key, from_date, to_date):  # noqa: ARG001
        return pd.DataFrame(
            {
                "series_id": [series_id],
                "date": ["2024-01-02"],
                "value": [3.95],
            }
        )

    with patch("bedrock.fetch.fred.fetch_fred_series", side_effect=fake_fetch):
        result = run_fetcher_by_name(
            "fundamentals",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert result.ok_count == 1
    assert result.total_rows == 1
    # Kun DGS10 siden kun Gold har fred_series_ids
    assert result.items[0].item_id == "DGS10"


# ---------------------------------------------------------------------------
# default_from_date
# ---------------------------------------------------------------------------


def test_default_from_date_with_stale_hours() -> None:
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    spec = _spec(stale_hours=24)
    result = default_from_date(spec, now=now, buffer_multiplier=2.0)
    # 24h × 2 = 48h bak → 30. mai
    assert result == date(2024, 5, 30)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_fetch_config(
    path: Path, *, include: list[str] | None = None
) -> None:
    fetchers = {
        "prices": {
            "module": "bedrock.fetch.prices",
            "cron": "40 * * * 1-5",
            "stale_hours": 24,
            "table": "prices",
            "ts_column": "ts",
        },
        "weather": {
            "module": "bedrock.fetch.weather",
            "cron": "0 3 * * *",
            "stale_hours": 30,
            "table": "weather",
            "ts_column": "date",
        },
    }
    if include:
        fetchers = {k: v for k, v in fetchers.items() if k in include}

    import yaml as pyyaml

    path.write_text(pyyaml.safe_dump({"fetchers": fetchers}))


def test_cli_fetch_run_single(runner: CliRunner, tmp_path: Path, configs_dir) -> None:
    defaults, insts = configs_dir
    config = tmp_path / "fetch.yaml"
    _write_fetch_config(config, include=["prices"])
    db = tmp_path / "bedrock.db"

    def fake_fetch(ticker, from_date, to_date, interval="d"):  # noqa: ARG001
        return _sample_bars(2)

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "fetch",
                "run",
                "prices",
                "--config",
                str(config),
                "--db",
                str(db),
                "--instruments-dir",
                str(insts),
                "--defaults-dir",
                str(defaults),
                "--from",
                "2024-01-01",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Running prices" in result.output
    assert "OK" in result.output
    assert "Summary" in result.output


def test_cli_fetch_run_all_fetchers(
    runner: CliRunner, tmp_path: Path, configs_dir
) -> None:
    defaults, insts = configs_dir
    config = tmp_path / "fetch.yaml"
    _write_fetch_config(config)
    db = tmp_path / "bedrock.db"

    def fake_prices(ticker, from_date, to_date, interval="d"):  # noqa: ARG001
        return _sample_bars(1)

    def fake_weather(region, lat, lon, from_date, to_date):  # noqa: ARG001
        return pd.DataFrame(
            {
                "region": [region],
                "date": ["2024-01-02"],
                "tmax": [10.0],
                "tmin": [-2.0],
                "precip": [0.0],
                "gdd": [None],
            }
        )

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_prices), patch(
        "bedrock.fetch.weather.fetch_weather", side_effect=fake_weather
    ):
        result = runner.invoke(
            cli,
            [
                "fetch",
                "run",
                "--config",
                str(config),
                "--db",
                str(db),
                "--instruments-dir",
                str(insts),
                "--defaults-dir",
                str(defaults),
                "--from",
                "2024-01-01",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Running prices" in result.output
    assert "Running weather" in result.output


def test_cli_fetch_run_unknown_fetcher(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "fetch.yaml"
    _write_fetch_config(config)
    result = runner.invoke(
        cli,
        ["fetch", "run", "ghost_fetcher", "--config", str(config)],
    )
    assert result.exit_code != 0
    assert "ghost_fetcher" in result.output


def test_cli_fetch_run_stale_only_skips_fresh(
    runner: CliRunner, tmp_path: Path, configs_dir
) -> None:
    """Hvis data er fresh → --stale-only hopper over fetcheren."""
    defaults, insts = configs_dir
    config = tmp_path / "fetch.yaml"
    _write_fetch_config(config, include=["prices"])
    db = tmp_path / "bedrock.db"
    # Skriv fersk data
    store = DataStore(db)
    df = _sample_bars(1)
    df["ts"] = pd.to_datetime([datetime.now(timezone.utc)])
    store.append_prices("Gold", "D1", df)

    mock_fetch_called = {"n": 0}

    def fake_fetch(*args, **kwargs):
        mock_fetch_called["n"] += 1
        return _sample_bars(1)

    with patch("bedrock.fetch.prices.fetch_prices", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "fetch",
                "run",
                "--config",
                str(config),
                "--db",
                str(db),
                "--instruments-dir",
                str(insts),
                "--defaults-dir",
                str(defaults),
                "--stale-only",
                "--from",
                "2024-01-01",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Ingen stale" in result.output
    assert mock_fetch_called["n"] == 0
