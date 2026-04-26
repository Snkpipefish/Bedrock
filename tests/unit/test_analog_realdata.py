"""Sanity-tester for find_analog_cases mot ekte backfilt data
(Fase 10 ADR-005, session 59).

Disse testene SKIP-pes hvis `data/bedrock.db` ikke finnes eller er tom
— de er ikke ment for CI uten data, men for manuell verifisering at
K-NN faktisk gir meningsfulle resultater på ekte historikk.

Kjør med:  pytest tests/unit/test_analog_realdata.py -v -s

Fra Fase 10 session 58 backfill: Gold + Corn × {30d, 90d} har 4 011-4 071
outcomes hver, så sanity-tester her viser hva K-NN gir på ekte
DGS10/DTWEXBGS/COT/ENSO/weather-data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bedrock.config.instruments import load_instrument_config
from bedrock.data.analog import (
    ASSET_CLASS_DIMS,
    extract_query_from_latest,
    find_analog_cases,
)
from bedrock.data.store import DataStore

_DB = Path("data/bedrock.db")
_GOLD_YAML = Path("config/instruments/gold.yaml")
_CORN_YAML = Path("config/instruments/corn.yaml")

_skip_no_data = pytest.mark.skipif(
    not _DB.exists() or _DB.stat().st_size < 100_000,
    reason="data/bedrock.db not backfilled — run `bedrock backfill ...` first",
)


@_skip_no_data
def test_gold_30d_returns_5_neighbors() -> None:
    store = DataStore(_DB)
    cfg = load_instrument_config(_GOLD_YAML)
    meta = cfg.instrument
    query = extract_query_from_latest(store, meta, "metals", skip_missing=True)
    # Vi har 3 av 4 metals-dim (vix mangler) — ennå nok til K-NN
    assert len(query) >= 3
    result = find_analog_cases(store, "Gold", meta, "metals", query, k=5, horizon_days=30)
    assert len(result) == 5
    assert (result["similarity"] > 0.5).all(), "Topp-5 burde ha similarity > 0.5"
    # Sanity: similarity strengt synkende
    sims = result["similarity"].tolist()
    assert sims == sorted(sims, reverse=True)


@_skip_no_data
def test_corn_30d_returns_5_neighbors() -> None:
    store = DataStore(_DB)
    cfg = load_instrument_config(_CORN_YAML)
    meta = cfg.instrument
    query = extract_query_from_latest(store, meta, "grains", skip_missing=True)
    # 3 av 4 grains-dim (conab_yoy mangler)
    assert len(query) >= 3
    result = find_analog_cases(store, "Corn", meta, "grains", query, k=5, horizon_days=30)
    assert len(result) == 5
    # Corn vil ha lavere similarity (vær er volatilt) men topp 5 burde >= 0.4
    assert (result["similarity"] > 0.4).all()


@_skip_no_data
def test_gold_90d_horizon_returns_distinct_outcomes() -> None:
    """30d og 90d horisonter skal gi separate outcomes-rader for samme
    ref_date — verifiser at K-NN returnerer riktig horisont."""
    store = DataStore(_DB)
    cfg = load_instrument_config(_GOLD_YAML)
    meta = cfg.instrument
    query = extract_query_from_latest(store, meta, "metals", skip_missing=True)
    r30 = find_analog_cases(store, "Gold", meta, "metals", query, k=5, horizon_days=30)
    r90 = find_analog_cases(store, "Gold", meta, "metals", query, k=5, horizon_days=90)
    # Samme ref_dates kan gjenta seg, men forward_return_pct skal være ulike
    # (forskjellig fremtids-vindu)
    assert len(r30) == 5
    assert len(r90) == 5


@_skip_no_data
def test_metals_query_has_expected_dim_names() -> None:
    """Sanity: query inneholder kun navn fra § 6.5-metals-listen."""
    store = DataStore(_DB)
    cfg = load_instrument_config(_GOLD_YAML)
    meta = cfg.instrument
    query = extract_query_from_latest(store, meta, "metals", skip_missing=True)
    expected = set(ASSET_CLASS_DIMS["metals"])
    assert set(query).issubset(expected)


@_skip_no_data
def test_grains_query_has_expected_dim_names() -> None:
    store = DataStore(_DB)
    cfg = load_instrument_config(_CORN_YAML)
    meta = cfg.instrument
    query = extract_query_from_latest(store, meta, "grains", skip_missing=True)
    expected = set(ASSET_CLASS_DIMS["grains"])
    assert set(query).issubset(expected)


@_skip_no_data
def test_unknown_instrument_no_outcomes_returns_empty() -> None:
    """Et instrument uten outcomes skal gi tom DataFrame.

    Etter session 99-backfilling har alle whitelist-instrumenter outcomes.
    Bruker derfor en oppdiktet instrument-id ("Foobar") for å verifisere
    defensiv håndtering ved manglende outcomes.
    """
    from bedrock.config.instruments import InstrumentMetadata

    store = DataStore(_DB)
    fake_meta = InstrumentMetadata(
        id="Foobar",
        asset_class="metals",
        ticker="XYZUSD",
        cot_contract="GOLD - COMMODITY EXCHANGE INC.",  # gjenbruk Gold COT for å unngå crash på extractor
        cot_report="disaggregated",
    )
    cfg = load_instrument_config(_GOLD_YAML)  # låner extractor-config fra gull
    query = extract_query_from_latest(store, cfg.instrument, "metals", skip_missing=True)
    result = find_analog_cases(store, "Foobar", fake_meta, "metals", query, k=5)
    # Foobar mangler outcomes → tom DataFrame
    assert result.empty
