"""Tester for `comex`-runner + smart-skip + UI-gruppe (session 108)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import (
    _previous_business_day,
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
    (insts / "gold.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Gold
              asset_class: metals
              ticker: XAUUSD
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.comex",
        cron="0 22 * * 1-5",
        stale_hours=30,
        table="comex_inventory",
        ts_column="date",
    )


def _sample_df(date_str: str = "2026-04-24") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "metal": "gold",
                "date": date_str,
                "registered": 15_000_000.0,
                "eligible": 13_000_000.0,
                "total": 28_000_000.0,
                "units": "oz",
            }
        ]
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_comex_runner_is_registered() -> None:
    assert "comex" in all_runner_names()


# ---------------------------------------------------------------------------
# _previous_business_day helper
# ---------------------------------------------------------------------------


def test_previous_business_day_on_tuesday_returns_monday() -> None:
    # 2026-04-21 var tirsdag
    tue = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    assert _previous_business_day(tue) == date(2026, 4, 20)


def test_previous_business_day_on_monday_returns_friday() -> None:
    # 2026-04-20 var mandag → forrige børsdag = fredag 17.
    mon = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    assert _previous_business_day(mon) == date(2026, 4, 17)


def test_previous_business_day_on_sunday_returns_friday() -> None:
    # 2026-04-19 var søndag → forrige børsdag = fredag 17.
    sun = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)
    assert _previous_business_day(sun) == date(2026, 4, 17)


def test_previous_business_day_on_saturday_returns_friday() -> None:
    sat = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    assert _previous_business_day(sat) == date(2026, 4, 17)


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows_when_db_empty(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.comex.fetch_comex", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "comex",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_comex_inventory("gold")


def test_runner_handles_empty_dataframe(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.comex.fetch_comex", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "comex",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 0


# ---------------------------------------------------------------------------
# Smart-skip
# ---------------------------------------------------------------------------


def test_runner_skips_http_when_db_has_latest_business_day(store: DataStore, configs_dir) -> None:
    """DB har siste børsdag-rad → fetcher kalles ALDRI."""
    defaults, insts = configs_dir

    target = _previous_business_day()
    store.append_comex_inventory(_sample_df(date_str=target.isoformat()))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch("bedrock.fetch.comex.fetch_comex", side_effect=_should_not_be_called):
        result = run_fetcher_by_name(
            "comex",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [], "fetcher må IKKE kalles når DB allerede er fersk"
    assert result.ok_count == 1
    assert result.total_rows == 0


def test_runner_runs_fetcher_when_db_only_has_old_data(store: DataStore, configs_dir) -> None:
    """DB med gammel rad → smart-skip ikke aktivert."""
    defaults, insts = configs_dir

    store.append_comex_inventory(_sample_df(date_str="2020-01-08"))

    fetcher_calls: list[int] = []

    def _fake(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df(date_str=_previous_business_day().isoformat())

    with patch("bedrock.fetch.comex.fetch_comex", side_effect=_fake):
        result = run_fetcher_by_name(
            "comex",
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
# UI-gruppen
# ---------------------------------------------------------------------------


def test_comex_in_ui_group_sektor() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["comex"] == "Sektor"
    assert "Sektor" in _GROUP_ORDER


# ---------------------------------------------------------------------------
# fetch.yaml-entry
# ---------------------------------------------------------------------------


def test_fetch_yaml_has_comex_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "comex" in config.fetchers
    spec = config.fetchers["comex"]
    assert spec.cron == "0 22 * * 1-5"
    assert spec.stale_hours == 30
    assert spec.table == "comex_inventory"
    assert spec.ts_column == "date"
