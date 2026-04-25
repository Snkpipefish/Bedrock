"""Tester for `bedrock backfill weather` CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli
from bedrock.data.store import DataStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _sample_weather_df(region: str = "us_cornbelt", n: int = 3) -> pd.DataFrame:
    dates = pd.date_range("2024-07-01", periods=n, freq="D").strftime("%Y-%m-%d").tolist()
    return pd.DataFrame(
        {
            "region": [region] * n,
            "date": dates,
            "tmax": [30.0 + i for i in range(n)],
            "tmin": [18.0 + i for i in range(n)],
            "precip": [0.0, 2.5, 0.2][:n],
            "gdd": [None] * n,
        }
    )


def test_backfill_weather_writes_to_db(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_weather", return_value=_sample_weather_df(n=3)):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "weather",
                "--region",
                "us_cornbelt",
                "--lat",
                "40.75",
                "--lon",
                "-96.75",
                "--from",
                "2024-07-01",
                "--to",
                "2024-07-03",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Wrote 3" in result.output

    store = DataStore(db)
    out = store.get_weather("us_cornbelt")
    assert len(out) == 3
    assert out["tmax"].iloc[0] == 30.0


def test_backfill_weather_dry_run_shows_url_and_coords(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_weather") as mock_fetch:
        result = runner.invoke(
            cli,
            [
                "backfill",
                "weather",
                "--region",
                "us_cornbelt",
                "--lat",
                "40.75",
                "--lon",
                "-96.75",
                "--from",
                "2024-07-01",
                "--to",
                "2024-07-03",
                "--db",
                str(db),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "archive-api.open-meteo.com" in result.output
    assert "latitude=40.75" in result.output
    assert "longitude=-96.75" in result.output
    assert "us_cornbelt" in result.output
    mock_fetch.assert_not_called()
    assert not db.exists()


def test_backfill_weather_empty_result_is_not_error(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    empty_df = pd.DataFrame(columns=["region", "date", "tmax", "tmin", "precip", "gdd"])
    with patch("bedrock.cli.backfill.fetch_weather", return_value=empty_df):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "weather",
                "--region",
                "x",
                "--lat",
                "0",
                "--lon",
                "0",
                "--from",
                "2024-07-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "No rows to write" in result.output
    assert not db.exists()


def test_backfill_weather_defaults_to_today_when_to_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    from datetime import date as date_cls

    called = {}

    def capture(region, lat, lon, from_date, to_date):
        called["to"] = to_date
        return _sample_weather_df(n=1)

    db = tmp_path / "bedrock.db"
    with patch("bedrock.cli.backfill.fetch_weather", side_effect=capture):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "weather",
                "--region",
                "x",
                "--lat",
                "0",
                "--lon",
                "0",
                "--from",
                "2024-07-01",
                "--db",
                str(db),
            ],
        )

    assert result.exit_code == 0, result.output
    assert called["to"] == date_cls.today()


def test_backfill_weather_requires_region_lat_lon_from(runner: CliRunner) -> None:
    # Mangler --lat og --lon
    result = runner.invoke(
        cli,
        [
            "backfill",
            "weather",
            "--region",
            "x",
            "--from",
            "2024-01-01",
        ],
    )
    assert result.exit_code != 0


def test_backfill_weather_invalid_lat_type_errors(runner: CliRunner) -> None:
    """--lat må være float, ikke string."""
    result = runner.invoke(
        cli,
        [
            "backfill",
            "weather",
            "--region",
            "x",
            "--lat",
            "not-a-number",
            "--lon",
            "0",
            "--from",
            "2024-01-01",
        ],
    )
    assert result.exit_code != 0


def test_backfill_weather_help_visible(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "weather" in result.output
