"""Tester for ``bedrock.engine.drivers.agri``.

Verifiserer weather_stress + enso_regime mot in-memory mock-store +
monkey-patched ``find_instrument``. Dekker grenseverdier, invert-modus,
og defensive 0.0-fallbacks.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockStore:
    """Stub som returnerer pd.DataFrame for weather_monthly + pd.Series for fundamentals."""

    def __init__(
        self,
        weather: dict[str, pd.DataFrame] | None = None,
        fundamentals: dict[str, pd.Series] | None = None,
    ):
        self._weather = weather or {}
        self._fundamentals = fundamentals or {}

    def get_weather_monthly(self, region: str, last_n: int | None = None) -> pd.DataFrame:
        if region not in self._weather:
            raise KeyError(f"No monthly weather for region={region!r}")
        df = self._weather[region]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)

    def get_fundamentals(self, series_id: str, last_n: int | None = None) -> pd.Series:
        if series_id not in self._fundamentals:
            raise KeyError(f"No fundamentals for series_id={series_id!r}")
        s = self._fundamentals[series_id]
        if last_n is None:
            return s
        return s.tail(last_n)


def _weather_row(
    *,
    hot_days: int = 0,
    dry_days: int = 0,
    water_bal: float = 0.0,
    month: str = "2026-04",
    region: str = "us_cornbelt",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "region": region,
                "month": month,
                "temp_mean": 20.0,
                "temp_max": 30.0,
                "precip_mm": 50.0,
                "et0_mm": 60.0,
                "hot_days": hot_days,
                "dry_days": dry_days,
                "wet_days": 5,
                "water_bal": water_bal,
            }
        ]
    )


@pytest.fixture
def mock_corn_instrument(monkeypatch):
    """Monkey-patcher find_instrument til å returnere Corn med us_cornbelt."""

    class _Meta:
        weather_region = "us_cornbelt"

    class _Cfg:
        instrument = _Meta()

    def _fake(name, _dir):
        if name == "Unknown":
            raise FileNotFoundError(name)
        return _Cfg()

    monkeypatch.setattr("bedrock.cli._instrument_lookup.find_instrument", _fake)
    return _Cfg()


@pytest.fixture
def mock_no_region(monkeypatch):
    """Stub uten weather_region — driver skal returnere 0.0."""

    class _Meta:
        weather_region = None

    class _Cfg:
        instrument = _Meta()

    monkeypatch.setattr(
        "bedrock.cli._instrument_lookup.find_instrument",
        lambda name, _dir: _Cfg(),
    )
    return _Cfg()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_weather_stress_registered() -> None:
    assert get("weather_stress") is not None


def test_enso_regime_registered() -> None:
    assert get("enso_regime") is not None


# ---------------------------------------------------------------------------
# weather_stress
# ---------------------------------------------------------------------------


def test_weather_stress_zero_for_normal_month(mock_corn_instrument: Any) -> None:
    """Måned med null stress → score 0.0."""
    store = _MockStore(weather={"us_cornbelt": _weather_row()})
    fn = get("weather_stress")
    assert fn(store, "Corn", {}) == 0.0


def test_weather_stress_high_for_drought_month(mock_corn_instrument: Any) -> None:
    """Mange varme dager + tørke + vann-underskudd → høy score."""
    store = _MockStore(
        weather={"us_cornbelt": _weather_row(hot_days=25, dry_days=28, water_bal=-150.0)}
    )
    fn = get("weather_stress")
    score = fn(store, "Corn", {})
    # 0.4*0.83 + 0.4*0.90 + 0.2*1.0 ≈ 0.892
    assert score > 0.85


def test_weather_stress_invert_flips(mock_corn_instrument: Any) -> None:
    """``invert=True`` → høy stress gir lav score."""
    store = _MockStore(
        weather={"us_cornbelt": _weather_row(hot_days=20, dry_days=20, water_bal=-100.0)}
    )
    fn = get("weather_stress")
    score_default = fn(store, "Corn", {})
    score_invert = fn(store, "Corn", {"invert": True})
    assert score_default + score_invert == pytest.approx(1.0, abs=1e-3)


def test_weather_stress_water_surplus_doesnt_add_stress(
    mock_corn_instrument: Any,
) -> None:
    """Positiv water_bal (vått) → bidrar ikke til stress (klippet til 0)."""
    store = _MockStore(weather={"us_cornbelt": _weather_row(water_bal=100.0)})
    fn = get("weather_stress")
    # Bare water_bal = stress 0; hot_days=0, dry_days=0 → score 0
    assert fn(store, "Corn", {}) == 0.0


def test_weather_stress_missing_region_returns_zero(mock_no_region: Any) -> None:
    """Instrument uten weather_region → 0.0."""
    store = _MockStore(weather={})
    fn = get("weather_stress")
    assert fn(store, "Gold", {}) == 0.0


def test_weather_stress_no_data_returns_zero(mock_corn_instrument: Any) -> None:
    """Region uten data → 0.0."""
    store = _MockStore(weather={})
    fn = get("weather_stress")
    assert fn(store, "Corn", {}) == 0.0


def test_weather_stress_handles_none_water_bal(mock_corn_instrument: Any) -> None:
    """NULL water_bal i DB → behandles som 0 stress fra vann-komponent."""
    df = _weather_row(hot_days=10)
    df.loc[0, "water_bal"] = None
    store = _MockStore(weather={"us_cornbelt": df})
    fn = get("weather_stress")
    score = fn(store, "Corn", {})
    # Bare hot_days=10 bidrar: 0.4 * (10/30) ≈ 0.133
    assert 0.10 < score < 0.15


def test_weather_stress_custom_weights(mock_corn_instrument: Any) -> None:
    """Brukerstyrte vekter skal overstyre default."""
    store = _MockStore(weather={"us_cornbelt": _weather_row(hot_days=30, dry_days=0)})
    fn = get("weather_stress")
    # Custom: hot_days dominerer, dry_days/water ignoreres
    score = fn(
        store,
        "Corn",
        {"weights": {"hot_days": 1.0, "dry_days": 0.0, "water_bal": 0.0}},
    )
    assert score == 1.0


# ---------------------------------------------------------------------------
# enso_regime
# ---------------------------------------------------------------------------


def test_enso_regime_la_nina_strong_returns_max(mock_corn_instrument: Any) -> None:
    """ONI ≤ -1.0 (sterk La Niña) → 1.0 (Corn-bull-default)."""
    store = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([-1.5], index=pd.to_datetime(["2026-01-01"]))}
    )
    fn = get("enso_regime")
    assert fn(store, "Corn", {}) == 1.0


def test_enso_regime_el_nino_strong_returns_zero(mock_corn_instrument: Any) -> None:
    """ONI > +1.0 (sterk El Niño) → 0.0 (Corn-bull-default)."""
    store = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([1.8], index=pd.to_datetime(["2026-01-01"]))}
    )
    fn = get("enso_regime")
    assert fn(store, "Corn", {}) == 0.0


def test_enso_regime_neutral_returns_mid(mock_corn_instrument: Any) -> None:
    """|ONI| < 0.5 → 0.5 (nøytralsone)."""
    store = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([0.0], index=pd.to_datetime(["2026-01-01"]))}
    )
    fn = get("enso_regime")
    assert fn(store, "Corn", {}) == 0.5


def test_enso_regime_invert_flips(mock_corn_instrument: Any) -> None:
    """``invert=True`` → El Niño = bull, La Niña = bear."""
    store_la_nina = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([-1.5], index=pd.to_datetime(["2026-01-01"]))}
    )
    store_el_nino = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([1.5], index=pd.to_datetime(["2026-01-01"]))}
    )
    fn = get("enso_regime")
    assert fn(store_la_nina, "Corn", {"invert": True}) == 0.0
    assert fn(store_el_nino, "Corn", {"invert": True}) == 1.0


def test_enso_regime_missing_series_returns_zero(mock_corn_instrument: Any) -> None:
    store = _MockStore()
    fn = get("enso_regime")
    assert fn(store, "Corn", {}) == 0.0


def test_enso_regime_empty_series_returns_zero(mock_corn_instrument: Any) -> None:
    store = _MockStore(fundamentals={"NOAA_ONI": pd.Series([], dtype="float64")})
    fn = get("enso_regime")
    assert fn(store, "Corn", {}) == 0.0


def test_enso_regime_custom_thresholds(mock_corn_instrument: Any) -> None:
    """Brukerstyrte thresholds skal overstyre."""
    store = _MockStore(
        fundamentals={"NOAA_ONI": pd.Series([0.7], index=pd.to_datetime(["2026-01-01"]))}
    )
    fn = get("enso_regime")
    # Custom: ONI ≤ 1.0 → 0.9
    score = fn(
        store,
        "Corn",
        {"thresholds": [[1.0, 0.9], [2.0, 0.4]]},
    )
    assert score == 0.9
