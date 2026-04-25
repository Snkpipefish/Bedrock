"""E2E-tester for `bedrock.orchestrator.generate_signals`.

Integrasjonsnivå: YAML + DataStore + Engine + setup-generator + hysterese
henger sammen. Bruker ekte drivere (sma200_align) og nok pris-data til
at build_setup faktisk kan finne nivåer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest

# Side-effekt: registrer drivere
import bedrock.engine.drivers  # noqa: F401
from bedrock.data.store import DataStore
from bedrock.orchestrator import generate_signals
from bedrock.orchestrator.score import OrchestratorError
from bedrock.setups.generator import Direction, Horizon

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wavy_series(n: int = 300, base: float = 100.0, amplitude: float = 20.0) -> np.ndarray:
    """Bølgete prisserie med lokale topper/bunner (gir swing-nivåer)."""
    t = np.arange(n)
    # Trend + sinus → oppadgående trend med volatilitet
    trend = base + t * 0.3
    oscillation = amplitude * np.sin(t / 8.0)
    return trend + oscillation


@pytest.fixture
def store_with_wavy_prices(tmp_path: Path) -> DataStore:
    """Nok data for SMA200 + swing-detektor."""
    store = DataStore(tmp_path / "bedrock.db")
    n = 300
    ts = pd.date_range("2020-01-01", periods=n, freq="D")
    close = _wavy_series(n)
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": [1000.0] * n,
        }
    )
    store.append_prices("Gold", "D1", df)
    store.append_prices("Corn", "D1", df)
    return store


@pytest.fixture
def minimal_defaults(tmp_path: Path) -> Path:
    d = tmp_path / "defaults"
    d.mkdir()
    (d / "family_financial.yaml").write_text(
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
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.75, min_families: 1}
              A:      {min_pct_of_max: 0.55, min_families: 1}
              B:      {min_pct_of_max: 0.35, min_families: 1}
            """
        )
    )
    (d / "family_agri.yaml").write_text(
        dedent(
            """\
            aggregation: additive_sum
            max_score: 10
            min_score_publish: 0.5
            families:
              outlook:
                weight: 5
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_score: 8, min_families_active: 1}
              A:      {min_score: 6, min_families_active: 1}
              B:      {min_score: 4, min_families_active: 1}
            """
        )
    )
    return d


@pytest.fixture
def instruments_dir(tmp_path: Path) -> Path:
    d = tmp_path / "instruments"
    d.mkdir()
    return d


def _write_gold(dir_: Path) -> None:
    (dir_ / "gold.yaml").write_text(
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


def _write_corn(dir_: Path) -> None:
    (dir_ / "corn.yaml").write_text(
        dedent(
            """\
            inherits: family_agri
            instrument:
              id: Corn
              asset_class: grains
              ticker: ZC
            """
        )
    )


# ---------------------------------------------------------------------------
# End-to-end financial
# ---------------------------------------------------------------------------


def test_generate_signals_financial_end_to_end(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    _write_gold(instruments_dir)
    now = datetime(2024, 1, 1, tzinfo=UTC)

    result = generate_signals(
        "Gold",
        store_with_wavy_prices,
        now=now,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )

    assert result.instrument == "Gold"
    assert result.run_ts == now
    # SWING × [BUY, SELL] = 2 entries
    assert len(result.entries) == 2
    directions = {e.direction for e in result.entries}
    assert directions == {Direction.BUY, Direction.SELL}
    horizons = {e.horizon for e in result.entries}
    assert horizons == {Horizon.SWING}
    # Alle entries har score
    for e in result.entries:
        assert e.score > 0
        assert e.grade in {"A_plus", "A", "B", "C"}
        assert e.max_score == 5.0


def test_generate_signals_with_snapshot_persists_stable_id(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
    tmp_path: Path,
) -> None:
    """To sekvensielle kjøringer → samme setup_id og first_seen uendret."""
    _write_gold(instruments_dir)
    snapshot = tmp_path / "last_run.json"

    first_ts = datetime(2024, 1, 1, tzinfo=UTC)
    first = generate_signals(
        "Gold",
        store_with_wavy_prices,
        now=first_ts,
        snapshot_path=snapshot,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert first.snapshot_written == snapshot
    assert snapshot.exists()

    second_ts = datetime(2024, 1, 2, tzinfo=UTC)
    second = generate_signals(
        "Gold",
        store_with_wavy_prices,
        now=second_ts,
        snapshot_path=snapshot,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )

    # For hvert matchende slot: setup_id og first_seen uendret, last_updated oppdatert
    first_buy = next(
        e for e in first.entries if e.direction == Direction.BUY and e.setup is not None
    )
    second_buy = next(
        e for e in second.entries if e.direction == Direction.BUY and e.setup is not None
    )
    assert first_buy.setup is not None
    assert second_buy.setup is not None
    assert first_buy.setup.setup_id == second_buy.setup.setup_id
    assert first_buy.setup.first_seen == second_buy.setup.first_seen
    assert second_buy.setup.last_updated == second_ts


def test_generate_signals_no_setup_found_keeps_entry_with_skip_reason(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    """Hvis build_setup returnerer None, skal entry finnes med
    skip_reason og setup=None. score fortsatt oppgis."""
    _write_gold(instruments_dir)

    # Kjør kun med SELL — på en stigende trend vil BUY finne nivå, SELL
    # trolig ikke (ingen sterk motstand bak pris). Ikke deterministisk,
    # men vi asserter mønsteret: hver entry har enten setup eller
    # skip_reason, aldri begge.
    result = generate_signals(
        "Gold",
        store_with_wavy_prices,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    for e in result.entries:
        if e.setup is None:
            assert e.skip_reason is not None
        else:
            assert e.skip_reason is None


# ---------------------------------------------------------------------------
# End-to-end agri
# ---------------------------------------------------------------------------


def test_generate_signals_agri_uses_three_horizons(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    _write_corn(instruments_dir)

    result = generate_signals(
        "Corn",
        store_with_wavy_prices,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )

    # Agri default: 3 horisonter × 2 retninger = 6 entries
    assert len(result.entries) == 6
    horizons = {e.horizon for e in result.entries}
    assert horizons == {Horizon.SCALP, Horizon.SWING, Horizon.MAKRO}


def test_generate_signals_agri_score_same_across_horizons(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    """Agri scorer én gang; samme score deles av alle horisonter."""
    _write_corn(instruments_dir)

    result = generate_signals(
        "Corn",
        store_with_wavy_prices,
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )

    # Grupper etter retning: alle 3 horisont-entries skal ha samme score
    buys = [e for e in result.entries if e.direction == Direction.BUY]
    sells = [e for e in result.entries if e.direction == Direction.SELL]
    assert len({e.score for e in buys}) == 1
    assert len({e.score for e in sells}) == 1


# ---------------------------------------------------------------------------
# Horisont- og retnings-filter
# ---------------------------------------------------------------------------


def test_generate_signals_filters_horizons(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    _write_corn(instruments_dir)
    result = generate_signals(
        "Corn",
        store_with_wavy_prices,
        horizons=["SWING"],
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert len(result.entries) == 2  # 1 horisont × 2 retninger
    assert all(e.horizon == Horizon.SWING for e in result.entries)


def test_generate_signals_filters_directions(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    _write_gold(instruments_dir)
    result = generate_signals(
        "Gold",
        store_with_wavy_prices,
        directions=[Direction.BUY],
        instruments_dir=instruments_dir,
        defaults_dir=minimal_defaults,
    )
    assert len(result.entries) == 1
    assert result.entries[0].direction == Direction.BUY


def test_generate_signals_unknown_horizon_errors(
    store_with_wavy_prices: DataStore,
    minimal_defaults: Path,
    instruments_dir: Path,
) -> None:
    _write_gold(instruments_dir)
    with pytest.raises(OrchestratorError, match="not defined"):
        generate_signals(
            "Gold",
            store_with_wavy_prices,
            horizons=["SCALP"],  # finnes ikke i minimal gold-YAML
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )


# ---------------------------------------------------------------------------
# Publisering
# ---------------------------------------------------------------------------


def test_published_flag_reflects_min_score_publish(
    store_with_wavy_prices: DataStore, instruments_dir: Path, tmp_path: Path
) -> None:
    """Høy publish-gulv → published=False selv når setup finnes."""
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
                min_score_publish: 999.0
            families:
              trend:
                drivers:
                  - {name: sma200_align, weight: 1.0, params: {tf: D1}}
            grade_thresholds:
              A_plus: {min_pct_of_max: 0.99, min_families: 1}
              A:      {min_pct_of_max: 0.98, min_families: 1}
              B:      {min_pct_of_max: 0.97, min_families: 1}
            """
        )
    )
    _write_gold(instruments_dir)

    result = generate_signals(
        "Gold",
        store_with_wavy_prices,
        instruments_dir=instruments_dir,
        defaults_dir=defaults,
    )
    assert all(not e.published for e in result.entries)


# ---------------------------------------------------------------------------
# Feil
# ---------------------------------------------------------------------------


def test_generate_signals_insufficient_prices_errors(
    tmp_path: Path, minimal_defaults: Path, instruments_dir: Path
) -> None:
    """Et DataStore med bare 1 bar → tydelig OrchestratorError."""
    store = DataStore(tmp_path / "empty.db")
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=1, freq="D"),
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1000.0],
        }
    )
    store.append_prices("Gold", "D1", df)

    _write_gold(instruments_dir)

    with pytest.raises(OrchestratorError, match="Ikke nok prisdata"):
        generate_signals(
            "Gold",
            store,
            instruments_dir=instruments_dir,
            defaults_dir=minimal_defaults,
        )
