"""Tester for `conab`-runner + smart-skip + UI-gruppe (session 111)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import all_runner_names, run_fetcher_by_name
from bedrock.data.store import DataStore


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
    insts = tmp_path / "insts"
    insts.mkdir()
    (insts / "soybean.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Soybean
              asset_class: grains
              ticker: ZS
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.conab",
        cron="0 20 15 * *",
        stale_hours=720,
        table="conab_estimates",
        ts_column="report_date",
    )


def _sample_df(date_str: str = "2026-04-15") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "report_date": date_str,
                "commodity": "soja",
                "levantamento": "7o",
                "safra": "2025/26",
                "production": 179151.6,
                "production_units": "kt",
                "area_kha": 48472.7,
                "yield_value": 3696,
                "yield_units": "kgha",
                "yoy_change_pct": 4.5,
                "mom_change_pct": None,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_runner_registered() -> None:
    assert "conab" in all_runner_names()


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.conab.fetch_conab", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "conab",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_conab_estimates("soja")


def test_runner_handles_empty_df(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.conab.fetch_conab", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "conab",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 0


# ---------------------------------------------------------------------------
# Smart-skip — månedlig
# ---------------------------------------------------------------------------


def test_runner_skips_when_db_has_current_month(store: DataStore, configs_dir) -> None:
    """DB har rad fra inneværende måned → fetcher kalles ALDRI."""
    defaults, insts = configs_dir

    today = datetime.now(timezone.utc).date()
    month_start_str = today.replace(day=1).isoformat()
    store.append_conab_estimates(_sample_df(date_str=month_start_str))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch("bedrock.fetch.conab.fetch_conab", side_effect=_should_not_be_called):
        result = run_fetcher_by_name(
            "conab",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [], "fetcher må IKKE kalles når DB allerede har siste måned"
    assert result.ok_count == 1
    assert result.total_rows == 0


def test_runner_runs_when_db_only_has_last_month(store: DataStore, configs_dir) -> None:
    """DB med rad fra forrige måned → smart-skip ikke aktivert."""
    defaults, insts = configs_dir

    # Sett en rad lenge før inneværende måned
    store.append_conab_estimates(_sample_df(date_str="2020-01-15"))

    fetcher_calls: list[int] = []

    def _fake(*args, **kwargs):
        fetcher_calls.append(1)
        today = datetime.now(timezone.utc).date()
        return _sample_df(date_str=today.replace(day=15).isoformat())

    with patch("bedrock.fetch.conab.fetch_conab", side_effect=_fake):
        result = run_fetcher_by_name(
            "conab",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [1]
    assert result.ok_count == 1
    assert result.total_rows == 1


# ---------------------------------------------------------------------------
# UI-gruppe + fetch.yaml
# ---------------------------------------------------------------------------


def test_ui_group_usda() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    # Conab plasseres i 'USDA'-gruppen (samme som wasde/crop_progress —
    # crop-estimate-data)
    assert _FETCHER_GROUPS["conab"] == "USDA"
    assert "USDA" in _GROUP_ORDER


def test_fetch_yaml_has_conab_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "conab" in config.fetchers
    spec = config.fetchers["conab"]
    assert spec.cron == "0 20 15 * *"
    assert spec.stale_hours == 720
    assert spec.table == "conab_estimates"
    assert spec.ts_column == "report_date"
