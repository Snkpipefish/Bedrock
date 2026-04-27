"""Tester for `seismic`-runner + UI-gruppe (session 109)."""

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
        module="bedrock.fetch.seismic",
        cron="0 4 * * *",
        stale_hours=30,
        table="seismic_events",
        ts_column="event_ts",
    )


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "us_test_001",
                "event_ts": pd.Timestamp("2026-04-25T08:30:00Z"),
                "magnitude": 5.5,
                "latitude": -23.5,
                "longitude": -70.4,
                "depth_km": 30.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": "https://example.com/1",
            }
        ]
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_seismic_runner_registered() -> None:
    assert "seismic" in all_runner_names()


# ---------------------------------------------------------------------------
# Runner happy-path
# ---------------------------------------------------------------------------


def test_runner_writes_rows(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.seismic.fetch_seismic", return_value=_sample_df()):
        result = run_fetcher_by_name(
            "seismic",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 1
    assert store.has_seismic_events()


def test_runner_handles_empty_df(store: DataStore, configs_dir) -> None:
    defaults, insts = configs_dir
    with patch("bedrock.fetch.seismic.fetch_seismic", return_value=pd.DataFrame()):
        result = run_fetcher_by_name(
            "seismic",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )
    assert result.ok_count == 1
    assert result.total_rows == 0


def test_runner_idempotent_on_event_id(store: DataStore, configs_dir) -> None:
    """Samme event_id på flere kjøringer → INSERT OR REPLACE, ikke duplikater."""
    defaults, insts = configs_dir

    revised = pd.DataFrame(
        [
            {
                "event_id": "us_test_001",
                "event_ts": pd.Timestamp("2026-04-25T08:30:00Z"),
                "magnitude": 6.0,  # revidert opp
                "latitude": -23.5,
                "longitude": -70.4,
                "depth_km": 30.0,
                "place": "Chile",
                "region": "Chile / Peru",
                "url": "https://example.com/1",
            }
        ]
    )

    # Første kjøring
    with patch("bedrock.fetch.seismic.fetch_seismic", return_value=_sample_df()):
        run_fetcher_by_name(
            "seismic",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    # Andre kjøring med revidert magnitude
    with patch("bedrock.fetch.seismic.fetch_seismic", return_value=revised):
        run_fetcher_by_name(
            "seismic",
            store,
            _spec(),
            from_date=date(2024, 1, 1),
            instruments_dir=insts,
            defaults_dir=defaults,
        )

    df = store.get_seismic_events()
    assert len(df) == 1  # ikke 2 — INSERT OR REPLACE
    assert df["magnitude"].iloc[0] == 6.0  # revidert verdi


# ---------------------------------------------------------------------------
# UI-gruppen + fetch.yaml
# ---------------------------------------------------------------------------


def test_seismic_in_ui_group_sektor() -> None:
    from bedrock.signal_server.endpoints.ui import _FETCHER_GROUPS, _GROUP_ORDER

    assert _FETCHER_GROUPS["seismic"] == "Sektor"
    assert "Sektor" in _GROUP_ORDER


def test_fetch_yaml_has_seismic_entry() -> None:
    from bedrock.config.fetch import load_fetch_config

    config = load_fetch_config(Path("config/fetch.yaml"))
    assert "seismic" in config.fetchers
    spec = config.fetchers["seismic"]
    assert spec.cron == "0 4 * * *"
    assert spec.stale_hours == 30
    assert spec.table == "seismic_events"
    assert spec.ts_column == "event_ts"


# Suppress unused-import warning for fixture
_ = datetime, timezone
