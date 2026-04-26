"""Tester for systemd-generator + `bedrock systemd` CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bedrock.cli.__main__ import cli
from bedrock.config.fetch import FetchConfig, FetcherSpec
from bedrock.systemd.generator import (
    CronConversionError,
    cron_to_oncalendar,
    generate_service_unit,
    generate_timer_unit,
    generate_units,
    write_units,
)

# ---------------------------------------------------------------------------
# Cron-konverter
# ---------------------------------------------------------------------------


def test_cron_weekday_hourly_40() -> None:
    assert cron_to_oncalendar("40 * * * 1-5") == "Mon-Fri *-*-* *:40:00"


def test_cron_friday_2200() -> None:
    assert cron_to_oncalendar("0 22 * * 5") == "Fri *-*-* 22:00:00"


def test_cron_daily_0230() -> None:
    assert cron_to_oncalendar("30 2 * * *") == "*-*-* 02:30:00"


def test_cron_daily_0300() -> None:
    assert cron_to_oncalendar("0 3 * * *") == "*-*-* 03:00:00"


def test_cron_sunday_alias_zero() -> None:
    assert cron_to_oncalendar("0 0 * * 0") == "Sun *-*-* 00:00:00"


def test_cron_sunday_alias_seven() -> None:
    assert cron_to_oncalendar("0 0 * * 7") == "Sun *-*-* 00:00:00"


def test_cron_comma_dow() -> None:
    assert cron_to_oncalendar("0 12 * * 1,3,5") == "Mon,Wed,Fri *-*-* 12:00:00"


def test_cron_specific_date() -> None:
    assert cron_to_oncalendar("0 12 15 3 *") == "*-03-15 12:00:00"


def test_cron_month_range() -> None:
    # Mandager 21:30 UTC, kun april-november (NASS Crop Progress).
    assert cron_to_oncalendar("30 21 * 4-11 1") == "Mon *-04..11-* 21:30:00"


def test_cron_month_list() -> None:
    assert cron_to_oncalendar("0 12 * 3,6,9,12 *") == "*-03,06,09,12-* 12:00:00"


def test_cron_dom_range() -> None:
    assert cron_to_oncalendar("0 12 1-5 * *") == "*-*-1..5 12:00:00"


def test_cron_wrong_number_of_fields_raises() -> None:
    with pytest.raises(CronConversionError, match="5 felter"):
        cron_to_oncalendar("0 3 *")


def test_cron_step_rejected() -> None:
    with pytest.raises(CronConversionError, match="step"):
        cron_to_oncalendar("*/5 * * * *")


def test_cron_named_dow_rejected() -> None:
    with pytest.raises(CronConversionError, match="named"):
        cron_to_oncalendar("0 3 * * MON")


def test_cron_range_in_minute_rejected() -> None:
    with pytest.raises(CronConversionError, match="range/list"):
        cron_to_oncalendar("0-30 * * * *")


def test_cron_dow_out_of_range_raises() -> None:
    with pytest.raises(CronConversionError, match="utenfor"):
        cron_to_oncalendar("0 0 * * 8")


# ---------------------------------------------------------------------------
# Unit-fil-generering
# ---------------------------------------------------------------------------


def test_generate_service_unit_contains_required_fields() -> None:
    content = generate_service_unit(
        "prices",
        working_dir=Path("/home/pc/bedrock"),
        bedrock_executable="/home/pc/bedrock/.venv/bin/bedrock",
    )
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content
    assert "Description=Bedrock fetch: prices" in content
    assert "WorkingDirectory=/home/pc/bedrock" in content
    assert "ExecStart=/home/pc/bedrock/.venv/bin/bedrock fetch run prices" in content
    assert "Type=oneshot" in content
    assert "WantedBy=default.target" in content


def test_generate_service_with_module_hint() -> None:
    content = generate_service_unit(
        "prices",
        working_dir=Path("/repo"),
        bedrock_executable="/bin/bedrock",
        module_hint="bedrock.fetch.prices",
    )
    assert "Bedrock fetch: prices (bedrock.fetch.prices)" in content


def test_generate_timer_unit_contains_required_fields() -> None:
    content = generate_timer_unit("prices", "40 * * * 1-5")
    assert "[Timer]" in content
    assert "OnCalendar=Mon-Fri *-*-* *:40:00" in content
    assert "Persistent=true" in content
    assert "Requires=bedrock-fetch-prices.service" in content
    assert "WantedBy=timers.target" in content


def test_generate_units_produces_pair_per_fetcher() -> None:
    config = FetchConfig(
        fetchers={
            "prices": FetcherSpec(
                module="bedrock.fetch.prices",
                cron="40 * * * 1-5",
                stale_hours=24,
                table="prices",
            ),
            "weather": FetcherSpec(
                module="bedrock.fetch.weather",
                cron="0 3 * * *",
                stale_hours=30,
                table="weather",
                ts_column="date",
            ),
        }
    )
    units = generate_units(
        config,
        working_dir=Path("/repo"),
        bedrock_executable="/bin/bedrock",
    )

    expected_filenames = {
        "bedrock-fetch-prices.service",
        "bedrock-fetch-prices.timer",
        "bedrock-fetch-weather.service",
        "bedrock-fetch-weather.timer",
    }
    assert set(units.keys()) == expected_filenames

    # Sjekk at timers har riktig OnCalendar
    assert "Mon-Fri *-*-* *:40:00" in units["bedrock-fetch-prices.timer"]
    assert "*-*-* 03:00:00" in units["bedrock-fetch-weather.timer"]


def test_write_units_creates_files(tmp_path: Path) -> None:
    units = {
        "bedrock-fetch-x.service": "unit content\n",
        "bedrock-fetch-x.timer": "timer content\n",
    }
    written = write_units(units, tmp_path / "out")
    assert len(written) == 2
    for path in written:
        assert path.exists()
        assert path.read_text().endswith("\n")


def test_write_units_creates_missing_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    write_units({"x.service": "content"}, target)
    assert (target / "x.service").exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fetch_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "fetch.yaml"
    path.write_text(
        dedent(
            """\
            fetchers:
              prices:
                module: bedrock.fetch.prices
                cron: "40 * * * 1-5"
                stale_hours: 24
                table: prices
              weather:
                module: bedrock.fetch.weather
                cron: "0 3 * * *"
                stale_hours: 30
                table: weather
                ts_column: date
            """
        )
    )
    return path


def test_cli_generate_writes_all_files(
    runner: CliRunner, tmp_path: Path, fetch_config_file: Path
) -> None:
    output = tmp_path / "systemd"
    result = runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/home/pc/bedrock",
            "--executable",
            "/home/pc/bedrock/.venv/bin/bedrock",
        ],
    )

    assert result.exit_code == 0, result.output
    files = sorted(f.name for f in output.iterdir())
    assert files == [
        "bedrock-fetch-prices.service",
        "bedrock-fetch-prices.timer",
        "bedrock-fetch-weather.service",
        "bedrock-fetch-weather.timer",
    ]
    assert "Skrev 4 filer" in result.output


def test_cli_generate_unsupported_cron_errors(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "fetch.yaml"
    config.write_text(
        dedent(
            """\
            fetchers:
              odd:
                module: bedrock.fetch.prices
                cron: "*/5 * * * *"
                stale_hours: 1
                table: prices
            """
        )
    )
    result = runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(config),
            "--output",
            str(tmp_path / "systemd"),
        ],
    )
    assert result.exit_code != 0
    assert "step" in result.output


def test_cli_list_shows_generated(
    runner: CliRunner, tmp_path: Path, fetch_config_file: Path
) -> None:
    output = tmp_path / "systemd"
    runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/tmp",
            "--executable",
            "/usr/bin/bedrock",
        ],
    )

    result = runner.invoke(cli, ["systemd", "list", "--units-dir", str(output)])
    assert result.exit_code == 0
    assert "bedrock-fetch-prices.timer" in result.output
    assert "bedrock-fetch-weather.timer" in result.output
    assert "OnCalendar=" in result.output


def test_cli_list_missing_dir(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(cli, ["systemd", "list", "--units-dir", str(tmp_path / "nope")])
    assert result.exit_code == 0
    assert "mangler" in result.output


def test_cli_install_dry_run(runner: CliRunner, tmp_path: Path, fetch_config_file: Path) -> None:
    output = tmp_path / "systemd"
    runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/tmp",
            "--executable",
            "/usr/bin/bedrock",
        ],
    )

    result = runner.invoke(
        cli,
        ["systemd", "install", "--units-dir", str(output), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("DRY-RUN") == 4  # 2 services + 2 timere
    assert "systemctl --user link" in result.output


def test_cli_install_empty_dir(runner: CliRunner, tmp_path: Path) -> None:
    (tmp_path / "systemd").mkdir()
    result = runner.invoke(
        cli,
        ["systemd", "install", "--units-dir", str(tmp_path / "systemd")],
    )
    assert result.exit_code != 0
    assert "Fant ingen" in result.output


def test_cli_install_runs_systemctl(
    runner: CliRunner, tmp_path: Path, fetch_config_file: Path
) -> None:
    """Med mocked subprocess — verifiser at riktige kommandoer formatteres."""
    output = tmp_path / "systemd"
    runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/tmp",
            "--executable",
            "/usr/bin/bedrock",
        ],
    )

    successful = MagicMock(returncode=0, stdout="", stderr="")
    with (
        patch("bedrock.cli.systemd.subprocess.run", return_value=successful) as mock_run,
        patch("bedrock.cli.systemd.shutil.which", return_value="/usr/bin/systemctl"),
    ):
        result = runner.invoke(cli, ["systemd", "install", "--units-dir", str(output)])

    assert result.exit_code == 0, result.output
    assert mock_run.call_count == 4  # 2 .service + 2 .timer
    # Alle kalt med --user link
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert args[0] == "/usr/bin/systemctl"
        assert "--user" in args
        assert "link" in args


def test_cli_install_missing_systemctl_errors(
    runner: CliRunner, tmp_path: Path, fetch_config_file: Path
) -> None:
    output = tmp_path / "systemd"
    runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/tmp",
            "--executable",
            "/usr/bin/bedrock",
        ],
    )
    with patch("bedrock.cli.systemd.shutil.which", return_value=None):
        result = runner.invoke(cli, ["systemd", "install", "--units-dir", str(output)])
    assert result.exit_code != 0
    assert "systemctl" in result.output


def test_cli_install_propagates_systemctl_failure(
    runner: CliRunner, tmp_path: Path, fetch_config_file: Path
) -> None:
    output = tmp_path / "systemd"
    runner.invoke(
        cli,
        [
            "systemd",
            "generate",
            "--config",
            str(fetch_config_file),
            "--output",
            str(output),
            "--working-dir",
            "/tmp",
            "--executable",
            "/usr/bin/bedrock",
        ],
    )

    failing = subprocess.CompletedProcess(
        args=["systemctl"], returncode=1, stdout="", stderr="permission denied"
    )
    with (
        patch("bedrock.cli.systemd.subprocess.run", return_value=failing),
        patch("bedrock.cli.systemd.shutil.which", return_value="/usr/bin/systemctl"),
    ):
        result = runner.invoke(cli, ["systemd", "install", "--units-dir", str(output)])
    assert result.exit_code != 0
    assert "permission denied" in result.output
