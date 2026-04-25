"""Tester for ASSET_CLASS_DIMS og DIM_EXTRACTORS (Fase 10 ADR-005, session 59).

Dekker:
- ASSET_CLASS_DIMS § 6.5-konformitet (alle 5 asset-klasser, 4 dim hver)
- DIM_EXTRACTORS — implementerte vs flagget-mangler
- get_extractor + MissingExtractorError for ikke-implementert dim
- Hver implementert extractor mot fixture-DB
- extract_query_from_latest med skip_missing
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from bedrock.config.instruments import InstrumentMetadata
from bedrock.data.analog import (
    ASSET_CLASS_DIMS,
    DIM_EXTRACTORS,
    MissingDataError,
    MissingExtractorError,
    _extract_cot_mm_pct,
    _extract_dxy_chg5d,
    _extract_enso_regime,
    _extract_real_yield_chg5d,
    _extract_term_spread,
    _extract_weather_stress,
    extract_query_from_latest,
    get_extractor,
)
from bedrock.data.store import DataStore

# ---------------------------------------------------------------------
# § 6.5-konformitet
# ---------------------------------------------------------------------


def test_asset_class_dims_has_all_five_classes() -> None:
    assert set(ASSET_CLASS_DIMS) == {"metals", "fx", "energy", "grains", "softs"}


def test_each_asset_class_has_four_dims() -> None:
    for asset_class, dims in ASSET_CLASS_DIMS.items():
        assert len(dims) == 4, f"{asset_class}: expected 4 dim per § 6.5, got {len(dims)}"


def test_metals_dims_match_plan_section_65() -> None:
    assert ASSET_CLASS_DIMS["metals"] == [
        "vix_regime",
        "real_yield_chg5d",
        "dxy_chg5d",
        "cot_mm_pct",
    ]


def test_fx_dims_match_plan_section_65() -> None:
    assert ASSET_CLASS_DIMS["fx"] == [
        "rate_differential_chg",
        "vix_regime",
        "dxy_chg5d",
        "term_spread",
    ]


def test_energy_dims_match_plan_section_65() -> None:
    assert ASSET_CLASS_DIMS["energy"] == [
        "backwardation",
        "supply_disruption_level",
        "dxy_chg5d",
        "cot_commercial_pct",
    ]


def test_grains_dims_match_plan_section_65() -> None:
    assert ASSET_CLASS_DIMS["grains"] == [
        "weather_stress_key_region",
        "enso_regime",
        "conab_yoy",
        "dxy_chg5d",
    ]


def test_softs_dims_match_plan_section_65() -> None:
    assert ASSET_CLASS_DIMS["softs"] == [
        "weather_stress",
        "enso_regime",
        "unica_mix_change",
        "brl_chg5d",
    ]


# ---------------------------------------------------------------------
# DIM_EXTRACTORS coverage
# ---------------------------------------------------------------------


def test_implemented_extractors() -> None:
    """De 6 dim som faktisk har data backfilt etter Fase 10 session 58."""
    expected = {
        "dxy_chg5d",
        "real_yield_chg5d",
        "term_spread",
        "cot_mm_pct",
        "enso_regime",
        "weather_stress_key_region",
        "weather_stress",  # softs-alias for samme extractor
    }
    assert set(DIM_EXTRACTORS) == expected


def test_get_extractor_for_known_dim() -> None:
    fn = get_extractor("dxy_chg5d")
    assert callable(fn)
    assert fn is _extract_dxy_chg5d


def test_get_extractor_for_unknown_dim_raises() -> None:
    with pytest.raises(MissingExtractorError, match="vix_regime"):
        get_extractor("vix_regime")


def test_weather_stress_aliases_share_extractor() -> None:
    """weather_stress (softs) og weather_stress_key_region (grains) skal
    bruke samme implementasjon — kun navne-konvensjon-forskjell per § 6.5."""
    assert get_extractor("weather_stress") is get_extractor("weather_stress_key_region")


# ---------------------------------------------------------------------
# Per-extractor smoke tests (mot fixture-DB)
# ---------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


@pytest.fixture
def gold_meta() -> InstrumentMetadata:
    return InstrumentMetadata(
        id="Gold",
        asset_class="metals",
        ticker="XAUUSD",
        cot_contract="GOLD - COMMODITY EXCHANGE INC.",
        cot_report="disaggregated",
    )


@pytest.fixture
def corn_meta() -> InstrumentMetadata:
    return InstrumentMetadata(
        id="Corn",
        asset_class="grains",
        ticker="ZC",
        cot_contract="CORN - CHICAGO BOARD OF TRADE",
        cot_report="disaggregated",
        weather_region="us_cornbelt",
    )


def _seed_fundamentals(
    store: DataStore, series_id: str, n: int, start_value: float = 100.0
) -> None:
    df = pd.DataFrame(
        {
            "series_id": [series_id] * n,
            "date": pd.date_range("2020-01-01", periods=n, freq="D"),
            "value": [start_value + i * 0.1 for i in range(n)],
        }
    )
    store.append_fundamentals(df)


def test_dxy_chg5d_basic(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    _seed_fundamentals(store, "DTWEXBGS", n=30, start_value=100.0)
    s = _extract_dxy_chg5d(store, gold_meta)
    assert not s.empty
    # Med 0.1-stigning per dag fra 100: 5d-pct ~= 0.5/100 * 100 = 0.5%
    assert s.iloc[0] == pytest.approx(0.5, abs=0.01)
    assert s.name == "dxy_chg5d"


def test_dxy_chg5d_missing_data(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    with pytest.raises(KeyError):  # get_fundamentals kaster KeyError ved tom serie
        _extract_dxy_chg5d(store, gold_meta)


def test_real_yield_chg5d(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    _seed_fundamentals(store, "DGS10", n=20, start_value=4.0)
    _seed_fundamentals(store, "T10YIE", n=20, start_value=2.0)
    s = _extract_real_yield_chg5d(store, gold_meta)
    assert not s.empty
    # real = DGS10 - T10YIE = (4 + i*0.1) - (2 + i*0.1) = 2.0 (konstant)
    # diff(5) av konstant = 0 (modulo floating-point)
    import numpy as np

    assert np.allclose(s.values, 0.0, atol=1e-10)


def test_term_spread(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    _seed_fundamentals(store, "DGS10", n=10, start_value=4.0)
    _seed_fundamentals(store, "DGS2", n=10, start_value=3.0)
    s = _extract_term_spread(store, gold_meta)
    # spread = (4+i*0.1) - (3+i*0.1) = 1.0 (modulo floating-point)
    import numpy as np

    assert np.allclose(s.values, 1.0, atol=1e-10)


def test_cot_mm_pct(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    df = pd.DataFrame(
        {
            "report_date": [date(2024, 1, 5), date(2024, 1, 12), date(2024, 1, 19)],
            "contract": [gold_meta.cot_contract] * 3,
            "mm_long": [80, 90, 70],
            "mm_short": [20, 10, 30],
            "other_long": [10, 10, 10],
            "other_short": [10, 10, 10],
            "comm_long": [10, 10, 10],
            "comm_short": [10, 10, 10],
            "nonrep_long": [5, 5, 5],
            "nonrep_short": [5, 5, 5],
            "open_interest": [100, 100, 100],
        }
    )
    store.append_cot_disaggregated(df)
    s = _extract_cot_mm_pct(store, gold_meta)
    # Etter forward-fill til daglig: jan 5 = 80%, jan 12 = 90%, jan 19 = 70%
    assert s.loc["2024-01-05"] == pytest.approx(80.0)
    assert s.loc["2024-01-12"] == pytest.approx(90.0)
    assert s.loc["2024-01-19"] == pytest.approx(70.0)
    # Forward-fill: jan 6-11 skal være 80%
    assert s.loc["2024-01-08"] == pytest.approx(80.0)


def test_cot_mm_pct_zero_total_handled(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    """Hvis (mm_long + mm_short) er 0, skal vi ikke krasje på 0-divisjon."""
    df = pd.DataFrame(
        {
            "report_date": [date(2024, 1, 5)],
            "contract": [gold_meta.cot_contract],
            "mm_long": [0],
            "mm_short": [0],
            "other_long": [0],
            "other_short": [0],
            "comm_long": [0],
            "comm_short": [0],
            "nonrep_long": [0],
            "nonrep_short": [0],
            "open_interest": [0],
        }
    )
    store.append_cot_disaggregated(df)
    s = _extract_cot_mm_pct(store, gold_meta)
    # 0/0 → NaN → fillna(50) — neutral
    assert s.iloc[0] == pytest.approx(50.0)


def test_cot_mm_pct_missing_contract_field(store: DataStore) -> None:
    meta = InstrumentMetadata(id="X", asset_class="metals", ticker="X")  # no cot_contract
    with pytest.raises(MissingDataError, match="cot_contract"):
        _extract_cot_mm_pct(store, meta)


def test_enso_regime(store: DataStore, corn_meta: InstrumentMetadata) -> None:
    _seed_fundamentals(store, "NOAA_ONI", n=10, start_value=-1.5)
    s = _extract_enso_regime(store, corn_meta)
    assert not s.empty
    assert s.iloc[0] == pytest.approx(-1.5)


def test_weather_stress(store: DataStore, corn_meta: InstrumentMetadata) -> None:
    df = pd.DataFrame(
        {
            "region": ["us_cornbelt"] * 3,
            "month": ["2024-05", "2024-06", "2024-07"],
            "temp_mean": [18.0, 22.0, 25.0],
            "temp_max": [None, None, None],
            "precip_mm": [None, None, None],
            "et0_mm": [None, None, None],
            "hot_days": [None, None, None],
            "dry_days": [None, None, None],
            "wet_days": [None, None, None],
            "water_bal": [10.0, -5.0, -20.0],  # mai positiv, juli stresset
        }
    )
    store.append_weather_monthly(df)
    s = _extract_weather_stress(store, corn_meta)
    # stress = -water_bal: mai = -10 (godt), juli = +20 (stresset)
    assert s.loc["2024-05-01"] == pytest.approx(-10.0)
    assert s.loc["2024-07-01"] == pytest.approx(20.0)


def test_weather_stress_missing_region(store: DataStore) -> None:
    meta = InstrumentMetadata(id="X", asset_class="grains", ticker="X")
    with pytest.raises(MissingDataError, match="weather_region"):
        _extract_weather_stress(store, meta)


# ---------------------------------------------------------------------
# extract_query_from_latest
# ---------------------------------------------------------------------


def test_extract_query_skip_missing(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    # Bare DTWEXBGS finnes — vix/real_yield/cot mangler
    _seed_fundamentals(store, "DTWEXBGS", n=20, start_value=100.0)
    q = extract_query_from_latest(store, gold_meta, "metals", skip_missing=True)
    assert set(q) == {"dxy_chg5d"}  # de andre droppet
    assert q["dxy_chg5d"] == pytest.approx(0.5, abs=0.01)


def test_extract_query_no_skip_raises(store: DataStore, gold_meta: InstrumentMetadata) -> None:
    """skip_missing=False kaster ved første manglende dim."""
    with pytest.raises((MissingExtractorError, MissingDataError, KeyError)):
        extract_query_from_latest(store, gold_meta, "metals", skip_missing=False)


def test_extract_query_unknown_asset_class_raises(
    store: DataStore, gold_meta: InstrumentMetadata
) -> None:
    with pytest.raises(KeyError, match="cryptos"):
        extract_query_from_latest(store, gold_meta, "cryptos")


def test_extract_query_explicit_dims_subset(
    store: DataStore, gold_meta: InstrumentMetadata
) -> None:
    """`dims=` overstyrer asset_class — kan be om bare ett dim."""
    _seed_fundamentals(store, "DTWEXBGS", n=20, start_value=100.0)
    q = extract_query_from_latest(
        store, gold_meta, "metals", dims=["dxy_chg5d"], skip_missing=False
    )
    assert set(q) == {"dxy_chg5d"}
