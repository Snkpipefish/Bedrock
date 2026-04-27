# pyright: reportArgumentType=false
"""Tester for `unica`-runner + smart-skip + UI-gruppe (session 112)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import all_runner_names, run_fetcher_by_name
from bedrock.data.schemas import UNICA_REPORTS_COLS
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
    (insts / "sugar.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Sugar
              asset_class: softs
              ticker: SB
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.unica",
        cron="0 21 1,16 * *",
        stale_hours=360,
        table="unica_reports",
        ts_column="report_date",
    )


def _sample_df(date_str: str = "2026-04-15") -> pd.DataFrame:
    row = dict.fromkeys(UNICA_REPORTS_COLS)
    row["report_date"] = date_str
    row["mix_sugar_pct"] = 50.61
    row["mix_sugar_pct_prev"] = 48.08
    row["crush_yoy_pct"] = -2.21
    return pd.DataFrame([row], columns=list(UNICA_REPORTS_COLS))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_runner_registered() -> None:
    assert "unica" in all_runner_names()


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.unica.fetch_unica", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "unica",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_unica_reports()


def test_runner_handles_empty_df(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.unica.fetch_unica", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "unica",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 0


# ---------------------------------------------------------------------------
# Smart-skip — halvmånedlig (13d threshold)
# ---------------------------------------------------------------------------


def test_runner_skips_when_db_has_recent_row(store: DataStore, configs_dir) -> None:
    """DB har rad innen siste 13 dager → fetcher kalles ALDRI."""
    defaults, insts = configs_dir

    today = datetime.now(timezone.utc).date()
    recent = (today - timedelta(days=5)).isoformat()
    store.append_unica_reports(_sample_df(date_str=recent))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch("bedrock.fetch.unica.fetch_unica", side_effect=_should_not_be_called):
        result = run_fetcher_by_name(
            "unica",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [], "fetcher må IKKE kalles innen smart-skip-vindu"
    assert result.ok_count == 1
    assert result.total_rows == 0


def test_runner_runs_when_db_has_old_row(store: DataStore, configs_dir) -> None:
    """DB med rad eldre enn 13 dager → fetcher kalles."""
    defaults, insts = configs_dir
    store.append_unica_reports(_sample_df(date_str="2020-01-15"))

    fetcher_calls: list[int] = []

    def _fake(*args, **kwargs):
        fetcher_calls.append(1)
        today = datetime.now(timezone.utc).date()
        return _sample_df(date_str=today.isoformat())

    with patch("bedrock.fetch.unica.fetch_unica", side_effect=_fake):
        result = run_fetcher_by_name(
            "unica",
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


def test_ui_group_sektor() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["unica"] == "Sektor"
    assert "Sektor" in _GROUP_ORDER


def test_fetch_yaml_has_unica_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "unica" in config.fetchers
    spec = config.fetchers["unica"]
    assert spec.cron == "0 21 1,16 * *"
    assert spec.stale_hours == 360
    assert spec.table == "unica_reports"
    assert spec.ts_column == "report_date"
