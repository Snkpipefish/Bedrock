"""Tester for `cot_ice`-runner + smart-skip + UI-gruppe (sub-fase 12.5+ session 106)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.config.fetch import FetcherSpec
from bedrock.config.fetch_runner import (
    _previous_tuesday,
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
    (insts / "brent.yaml").write_text(
        dedent(
            """\
            inherits: family_financial
            instrument:
              id: Brent
              asset_class: energy
              ticker: XBRUSD
              cot_contract: "ice brent crude"
              cot_report: disaggregated
            """
        )
    )
    return defaults, insts


def _spec() -> FetcherSpec:
    return FetcherSpec(
        module="bedrock.fetch.cot_ice",
        cron="30 22 * * 5",
        stale_hours=168,
        table="cot_ice",
        ts_column="report_date",
    )


def _sample_df(report_date: str = "2024-01-16") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "report_date": [report_date],
            "contract": ["ice brent crude"],
            "mm_long": [100_000],
            "mm_short": [50_000],
            "other_long": [12_000],
            "other_short": [9_000],
            "comm_long": [400_000],
            "comm_short": [450_000],
            "nonrep_long": [4_000],
            "nonrep_short": [3_500],
            "open_interest": [1_000_000],
        }
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_cot_ice_runner_is_registered() -> None:
    assert "cot_ice" in all_runner_names()


# ---------------------------------------------------------------------------
# _previous_tuesday helper
# ---------------------------------------------------------------------------


def test_previous_tuesday_on_tuesday_returns_self() -> None:
    # 2026-04-21 var tirsdag
    tue = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    assert _previous_tuesday(tue) == date(2026, 4, 21)


def test_previous_tuesday_on_friday_returns_tuesday() -> None:
    # 2026-04-24 var fredag
    fri = datetime(2026, 4, 24, 23, 30, tzinfo=timezone.utc)
    assert _previous_tuesday(fri) == date(2026, 4, 21)


def test_previous_tuesday_on_monday_returns_last_tuesday() -> None:
    # 2026-04-27 var mandag
    mon = datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc)
    # Forrige tirsdag før mandag 27. = tirsdag 21.
    assert _previous_tuesday(mon) == date(2026, 4, 21)


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows_when_db_empty(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "cot_ice",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert result.ok_count == 1
    assert result.fail_count == 0
    assert result.total_rows == 1
    assert store.has_cot_ice("ice brent crude")


def test_runner_handles_empty_dataframe(store: DataStore, configs_dir) -> None:
    """Tom DataFrame fra fetcher → 0 rader, men ok=True (matcher andre runners)."""
    defaults, insts = configs_dir

    with patch(
        "bedrock.fetch.cot_ice.fetch_cot_ice",
        return_value=pd.DataFrame(),
    ):
        result = run_fetcher_by_name(
            "cot_ice",
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


def test_runner_skips_http_when_db_has_latest_tuesday(store: DataStore, configs_dir) -> None:
    """DB har siste tirsdag-rad → smart-skip aktiveres, fetcher kalles ALDRI."""
    defaults, insts = configs_dir

    # Pre-populer DB med rad for "i dag" (eller hvilken tirsdag _previous_tuesday gir nå)
    target = _previous_tuesday()
    store.append_cot_ice(_sample_df(report_date=target.isoformat()))

    fetcher_calls: list[int] = []

    def _should_not_be_called(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df()

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice", side_effect=_should_not_be_called):
        result = run_fetcher_by_name(
            "cot_ice",
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
    """DB har gamle rader (>1 uke siden) → smart-skip ikke aktivert, HTTP kjøres."""
    defaults, insts = configs_dir

    # Pre-populer DB med en gammel rad
    store.append_cot_ice(_sample_df(report_date="2020-01-07"))

    fetcher_calls: list[int] = []

    def _fake_fetch(*args, **kwargs):
        fetcher_calls.append(1)
        return _sample_df(report_date=_previous_tuesday().isoformat())

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice", side_effect=_fake_fetch):
        result = run_fetcher_by_name(
            "cot_ice",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    assert fetcher_calls == [1], "fetcher må kalles når DB-data er gammel"
    assert result.ok_count == 1
    assert result.total_rows == 1


# ---------------------------------------------------------------------------
# UI-grupperingen
# ---------------------------------------------------------------------------


def test_cot_ice_in_ui_group_ekstern_cot() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["cot_ice"] == "Ekstern COT"
    assert "Ekstern COT" in _GROUP_ORDER


# ---------------------------------------------------------------------------
# fetch.yaml-entry
# ---------------------------------------------------------------------------


def test_fetch_yaml_has_cot_ice_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "cot_ice" in config.fetchers
    spec = config.fetchers["cot_ice"]
    assert spec.cron == "30 22 * * 5"
    assert spec.stale_hours == 168
    assert spec.table == "cot_ice"
    assert spec.ts_column == "report_date"
