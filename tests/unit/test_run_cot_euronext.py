"""Tester for `cot_euronext`-runner + smart-skip + UI-gruppe (session 110)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import (
    _previous_wednesday,
    all_runner_names,
    run_fetcher_by_name,
)
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
    (insts / "wheat.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Wheat
              asset_class: grains
              ticker: ZWH
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.cot_euronext",
        cron="0 18 * * 3",
        stale_hours=168,
        table="cot_euronext",
        ts_column="report_date",
    )


def _sample_df(date_str: str = "2026-04-22") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "report_date": date_str,
                "contract": "euronext milling wheat",
                "mm_long": 80960,
                "mm_short": 110134,
                "open_interest": 475200,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_runner_registered() -> None:
    assert "cot_euronext" in all_runner_names()


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.cot_euronext.fetch_cot_euronext", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "cot_euronext",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_cot_euronext("euronext milling wheat")


def test_runner_handles_empty_df(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.cot_euronext.fetch_cot_euronext", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "cot_euronext",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 0


# ---------------------------------------------------------------------------
# Smart-skip (gjenbruker session 107s _previous_wednesday)
# ---------------------------------------------------------------------------


def test_runner_skips_when_db_has_latest_wednesday(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir

    target = _previous_wednesday()
    store.append_cot_euronext(_sample_df(date_str=target.isoformat()))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch(
        "bedrock.fetch.cot_euronext.fetch_cot_euronext",
        side_effect=_should_not_be_called,
    ):
        result = run_fetcher_by_name(
            "cot_euronext",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [], "fetcher må IKKE kalles når DB allerede er fersk"
    assert result.ok_count == 1
    assert result.total_rows == 0


def test_runner_runs_when_db_has_old_data(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    store.append_cot_euronext(_sample_df(date_str="2020-01-08"))

    fetcher_calls: list[int] = []

    def _fake(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df(date_str=_previous_wednesday().isoformat())

    with patch("bedrock.fetch.cot_euronext.fetch_cot_euronext", side_effect=_fake):
        result = run_fetcher_by_name(
            "cot_euronext",
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


def test_ui_group_ekstern_cot() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["cot_euronext"] == "Ekstern COT"
    assert "Ekstern COT" in _GROUP_ORDER


def test_fetch_yaml_has_cot_euronext_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "cot_euronext" in config.fetchers
    spec = config.fetchers["cot_euronext"]
    assert spec.cron == "0 18 * * 3"
    assert spec.stale_hours == 168
    assert spec.table == "cot_euronext"
    assert spec.ts_column == "report_date"
