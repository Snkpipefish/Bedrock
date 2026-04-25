"""Tester for `--instrument`-flagg og YAML-oppslag i `bedrock backfill *`.

Dekker:

- prices: --instrument gir yahoo_ticker + kanonisk DB-tag
- cot-disaggregated/cot-legacy: --instrument gir cot_contract
- weather: --instrument gir region/lat/lon
- fundamentals: --instrument itererer over fred_series_ids med per-serie
  resiliens + retry-oppsummering på feil
"""

from __future__ import annotations

import os
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


@pytest.fixture(autouse=True)
def _clean_fred_env():
    saved = os.environ.pop("FRED_API_KEY", None)
    yield
    if saved is not None:
        os.environ["FRED_API_KEY"] = saved


@pytest.fixture
def instruments_dir(tmp_path: Path) -> Path:
    d = tmp_path / "instruments"
    d.mkdir()
    (d / "gold.yaml").write_text(
        """\
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  yahoo_ticker: GC=F
  cot_contract: "GOLD - COMMODITY EXCHANGE INC."
  cot_report: disaggregated
  fred_series_ids:
    - DGS10
    - DTWEXBGS

aggregation: weighted_horizon
horizons:
  SWING:
    family_weights: {trend: 1.0}
    max_score: 5.0
    min_score_publish: 2.5
families:
  trend:
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_pct_of_max: 0.75, min_families: 4}
  A:      {min_pct_of_max: 0.55, min_families: 3}
  B:      {min_pct_of_max: 0.35, min_families: 2}
"""
    )
    (d / "corn.yaml").write_text(
        """\
instrument:
  id: Corn
  asset_class: grains
  ticker: ZC
  yahoo_ticker: ZC=F
  weather_region: us_cornbelt
  weather_lat: 40.75
  weather_lon: -96.75

aggregation: additive_sum
max_score: 18
min_score_publish: 7
families:
  outlook:
    weight: 5
    drivers:
      - {name: sma200_align, weight: 1.0, params: {tf: D1}}
grade_thresholds:
  A_plus: {min_score: 14, min_families_active: 4}
  A:      {min_score: 10, min_families_active: 3}
  B:      {min_score: 7,  min_families_active: 2}
"""
    )
    return d


def _sample_bars(n: int = 3) -> pd.DataFrame:
    ts = pd.date_range("2024-01-02", periods=n, freq="D")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


def _sample_fred(series_id: str, n: int = 2) -> pd.DataFrame:
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"][:n]
    return pd.DataFrame(
        {
            "series_id": [series_id] * n,
            "date": dates,
            "value": [1.0 + i for i in range(n)],
        }
    )


def _sample_cot_disagg() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "report_date": ["2024-01-02"],
            "contract": ["GOLD - COMMODITY EXCHANGE INC."],
            "mm_long": [100],
            "mm_short": [50],
            "other_long": [10],
            "other_short": [5],
            "comm_long": [80],
            "comm_short": [60],
            "nonrep_long": [3],
            "nonrep_short": [2],
            "open_interest": [1000],
        }
    )


def _sample_weather() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["us_cornbelt"],
            "date": ["2024-01-02"],
            "tmax": [10.0],
            "tmin": [-2.0],
            "precip": [0.0],
            "gdd": [None],
        }
    )


# ---------------------------------------------------------------------------
# prices --instrument
# ---------------------------------------------------------------------------


def test_prices_instrument_yaml_lookup(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    captured: dict[str, object] = {}

    def fake_fetch(ticker, from_date, to_date, interval="1d", timeout_sec=15.0):
        captured["ticker"] = ticker
        return _sample_bars(2)

    with patch("bedrock.cli.backfill.fetch_yahoo_prices", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--instrument",
                "gold",  # lowercase → case-insensitive YAML-lookup
                "--from",
                "2024-01-02",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["ticker"] == "GC=F"  # fra YAML yahoo_ticker
    # Kanonisk DB-tag fra YAML: "Gold" (ikke "gold")
    store = DataStore(db)
    assert store.has_prices("Gold", "D1")


def test_prices_explicit_ticker_bypasses_yaml(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """Eksplisitt --ticker vinner — ingen YAML-lookup, ingen krav til YAML-fil."""
    db = tmp_path / "bedrock.db"
    captured: dict[str, object] = {}

    def fake_fetch(ticker, from_date, to_date, interval="1d", timeout_sec=15.0):
        captured["ticker"] = ticker
        return _sample_bars(1)

    with patch("bedrock.cli.backfill.fetch_yahoo_prices", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "prices",
                "--instrument",
                "Silver",  # ikke i YAML, men --ticker bypasser lookup
                "--ticker",
                "SI=F",
                "--from",
                "2024-01-02",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["ticker"] == "SI=F"


def test_prices_unknown_instrument_without_ticker_errors(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "prices",
            "--instrument",
            "Platinum",
            "--from",
            "2024-01-02",
            "--db",
            str(db),
            "--instruments-dir",
            str(instruments_dir),
        ],
    )
    assert result.exit_code != 0
    assert "Platinum" in result.output or "Ukjent" in result.output


# ---------------------------------------------------------------------------
# cot-disaggregated --instrument
# ---------------------------------------------------------------------------


def test_cot_disagg_instrument_yaml_lookup(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    captured: dict[str, object] = {}

    def fake_fetch(contract, from_date, to_date):
        captured["contract"] = contract
        return _sample_cot_disagg()

    with patch("bedrock.cli.backfill.fetch_cot_disaggregated", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "cot-disaggregated",
                "--instrument",
                "Gold",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["contract"] == "GOLD - COMMODITY EXCHANGE INC."


def test_cot_disagg_instrument_without_cot_contract_errors(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """Corn.yaml har ikke cot_contract → tydelig feil når --instrument Corn brukes."""
    # Overskriv corn.yaml uten cot_contract
    (instruments_dir / "corn.yaml").write_text(
        (instruments_dir / "corn.yaml")
        .read_text()
        .replace(
            'cot_contract: "CORN - CHICAGO BOARD OF TRADE"\n  cot_report: disaggregated\n',
            "",
        )
    )
    # (corn.yaml har faktisk ikke cot_contract i fixture — bra)
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "cot-disaggregated",
            "--instrument",
            "Corn",
            "--from",
            "2024-01-01",
            "--db",
            str(db),
            "--instruments-dir",
            str(instruments_dir),
        ],
    )
    assert result.exit_code != 0
    assert "cot_contract" in result.output.lower()


def test_cot_without_contract_or_instrument_errors(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "cot-disaggregated",
            "--from",
            "2024-01-01",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# weather --instrument
# ---------------------------------------------------------------------------


def test_weather_instrument_yaml_lookup(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    captured: dict[str, object] = {}

    def fake_fetch(region, lat, lon, from_date, to_date):
        captured["region"] = region
        captured["lat"] = lat
        captured["lon"] = lon
        return _sample_weather()

    with patch("bedrock.cli.backfill.fetch_weather", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "weather",
                "--instrument",
                "Corn",
                "--from",
                "2024-01-02",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["region"] == "us_cornbelt"
    assert captured["lat"] == 40.75
    assert captured["lon"] == -96.75


def test_weather_instrument_without_weather_metadata_errors(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """Gold har ikke weather-felter → tydelig feil ved --instrument Gold."""
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "weather",
            "--instrument",
            "Gold",
            "--from",
            "2024-01-02",
            "--db",
            str(db),
            "--instruments-dir",
            str(instruments_dir),
        ],
    )
    assert result.exit_code != 0
    assert "weather" in result.output.lower()


def test_weather_without_instrument_or_coords_errors(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "weather",
            "--from",
            "2024-01-02",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fundamentals --instrument (iterasjon over fred_series_ids)
# ---------------------------------------------------------------------------


def test_fundamentals_instrument_iterates_all_series(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "ok"

    calls: list[str] = []

    def fake_fetch(series_id, api_key, from_date, to_date):
        calls.append(series_id)
        return _sample_fred(series_id, n=2)

    with patch("bedrock.cli.backfill.fetch_fred_series", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--instrument",
                "Gold",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert calls == ["DGS10", "DTWEXBGS"]
    assert "[1/2] series-id=DGS10" in result.output
    assert "[2/2] series-id=DTWEXBGS" in result.output
    assert "OK" in result.output
    # Summary for multi-item run
    assert "2/2 ok" in result.output


def test_fundamentals_instrument_one_failure_continues(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """En feil stopper ikke resten — og retry-kommandoen printes."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "ok"

    def fake_fetch(series_id, api_key, from_date, to_date):
        if series_id == "DTWEXBGS":
            raise RuntimeError("HTTP 429 Too Many Requests")
        return _sample_fred(series_id, n=2)

    with patch("bedrock.cli.backfill.fetch_fred_series", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--instrument",
                "Gold",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    # Exit-kode != 0 fordi én feil
    assert result.exit_code != 0

    # Første serie ok, DGS10 ble skrevet til DB
    store = DataStore(db)
    assert len(store.get_fundamentals("DGS10")) == 2

    # Summary synliggjør failure
    assert "1/2 ok" in result.output
    assert "1 failed" in result.output
    assert "DTWEXBGS" in result.output
    assert "HTTP 429" in result.output
    # Retry-kommando
    assert "--series-id DTWEXBGS" in result.output


def test_fundamentals_series_id_overrides_instrument(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """Eksplisitt --series-id vinner over --instrument (for retry/testing)."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "ok"

    calls: list[str] = []

    def fake_fetch(series_id, api_key, from_date, to_date):
        calls.append(series_id)
        return _sample_fred(series_id, n=1)

    with patch("bedrock.cli.backfill.fetch_fred_series", side_effect=fake_fetch):
        result = runner.invoke(
            cli,
            [
                "backfill",
                "fundamentals",
                "--instrument",
                "Gold",
                "--series-id",
                "DGS10",
                "--from",
                "2024-01-01",
                "--db",
                str(db),
                "--instruments-dir",
                str(instruments_dir),
            ],
        )

    assert result.exit_code == 0, result.output
    assert calls == ["DGS10"]  # KUN DGS10, ikke DTWEXBGS


def test_fundamentals_instrument_dry_run_shows_all_series(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "fundamentals",
            "--instrument",
            "Gold",
            "--from",
            "2024-01-01",
            "--db",
            str(db),
            "--instruments-dir",
            str(instruments_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "series_id=DGS10" in result.output
    assert "series_id=DTWEXBGS" in result.output
    assert not db.exists()


def test_fundamentals_instrument_empty_fred_list_errors(
    runner: CliRunner, tmp_path: Path, instruments_dir: Path
) -> None:
    """Corn har ingen fred_series_ids → tydelig feil."""
    db = tmp_path / "bedrock.db"
    os.environ["FRED_API_KEY"] = "ok"

    result = runner.invoke(
        cli,
        [
            "backfill",
            "fundamentals",
            "--instrument",
            "Corn",
            "--from",
            "2024-01-01",
            "--db",
            str(db),
            "--instruments-dir",
            str(instruments_dir),
        ],
    )
    assert result.exit_code != 0
    assert "fred_series_ids" in result.output


def test_fundamentals_without_instrument_or_series_errors(
    runner: CliRunner, tmp_path: Path
) -> None:
    db = tmp_path / "bedrock.db"
    result = runner.invoke(
        cli,
        [
            "backfill",
            "fundamentals",
            "--from",
            "2024-01-01",
            "--api-key",
            "k",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code != 0
