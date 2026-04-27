"""Tester for `eia_inventories`-runner + smart-skip + UI-gruppe (session 107)."""

from __future__ import annotations

from datetime import date, datetime, timezone
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
    (insts / "crudeoil.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: CrudeOil
              asset_class: energy
              ticker: XTIUSD
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.eia_inventories",
        cron="30 17 * * 3",
        stale_hours=200,
        table="eia_inventory",
        ts_column="date",
    )


def _sample_df(date_str: str = "2026-04-17") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["WCESTUS1"],
            "date": [date_str],
            "value": [465729.0],
            "units": ["MBBL"],
        }
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_eia_runner_is_registered() -> None:
    assert "eia_inventories" in all_runner_names()


# ---------------------------------------------------------------------------
# _previous_wednesday helper
# ---------------------------------------------------------------------------


def test_previous_wednesday_on_wednesday_returns_self() -> None:
    # 2026-04-22 var onsdag
    wed = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    assert _previous_wednesday(wed) == date(2026, 4, 22)


def test_previous_wednesday_on_friday_returns_wednesday() -> None:
    # 2026-04-24 fredag → forrige onsdag = 22.
    fri = datetime(2026, 4, 24, 23, 30, tzinfo=timezone.utc)
    assert _previous_wednesday(fri) == date(2026, 4, 22)


def test_previous_wednesday_on_tuesday_returns_last_wednesday() -> None:
    # 2026-04-21 tirsdag → siste onsdag før = 15.
    tue = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
    assert _previous_wednesday(tue) == date(2026, 4, 15)


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows_when_db_empty(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.eia_inventories.fetch_eia", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "eia_inventories",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_eia_inventory("WCESTUS1")


def test_runner_handles_empty_dataframe(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.eia_inventories.fetch_eia", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "eia_inventories",
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


def test_runner_skips_http_when_db_has_latest_wednesday(store: DataStore, configs_dir) -> None:
    """DB har siste onsdag-rad → fetcher kalles ALDRI."""
    defaults, insts = configs_dir

    target = _previous_wednesday()
    store.append_eia_inventory(_sample_df(date_str=target.isoformat()))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch("bedrock.fetch.eia_inventories.fetch_eia", side_effect=_should_not_be_called):
        result = run_fetcher_by_name(
            "eia_inventories",
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

    store.append_eia_inventory(_sample_df(date_str="2020-01-08"))

    fetcher_calls: list[int] = []

    def _fake(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df(date_str=_previous_wednesday().isoformat())

    with patch("bedrock.fetch.eia_inventories.fetch_eia", side_effect=_fake):
        result = run_fetcher_by_name(
            "eia_inventories",
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
# UI-grupperingen
# ---------------------------------------------------------------------------


def test_eia_in_ui_group_sektor() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["eia_inventories"] == "Sektor"
    assert "Sektor" in _GROUP_ORDER


# ---------------------------------------------------------------------------
# fetch.yaml-entry
# ---------------------------------------------------------------------------


def test_fetch_yaml_has_eia_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "eia_inventories" in config.fetchers
    spec = config.fetchers["eia_inventories"]
    assert spec.cron == "30 17 * * 3"
    assert spec.stale_hours == 200
    assert spec.table == "eia_inventory"
    assert spec.ts_column == "date"
