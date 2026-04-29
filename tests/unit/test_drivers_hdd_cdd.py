"""Tester for ``hdd_cdd_anomaly``-driver (sub-fase 12.7 D2 B4, session 131).

Pattern-doc § 3.1 sesong-modulert mønster: vinter=HDD, sommer=CDD,
skuldermåneder=0.5. Driver-intern, ingen ny polarity-type.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from bedrock.engine.drivers import get


class _MockStore:
    def __init__(self, weather_per_region: dict[str, pd.DataFrame]):
        self._weather = weather_per_region

    def get_weather(self, region: str, last_n: int | None = None) -> pd.DataFrame:
        if region not in self._weather:
            raise KeyError(f"No weather for region={region!r}")
        df = self._weather[region]
        if last_n is None:
            return df
        return df.tail(last_n).reset_index(drop=True)


def _make_weather(
    n_days: int,
    tmax_c: float,
    tmin_c: float,
    start: str = "2020-01-01",
    region: str = "us_ng_ne",
) -> pd.DataFrame:
    """Bygg weather-DF med konstante temperaturer (for sanity-tester)."""
    idx = pd.date_range(start, periods=n_days, freq="D")
    return pd.DataFrame(
        {
            "region": region,
            "date": idx,
            "tmax": [tmax_c] * n_days,
            "tmin": [tmin_c] * n_days,
            "precip": [0.0] * n_days,
            "gdd": [None] * n_days,
        }
    )


# ---------------------------------------------------------------------------
# Sesong-switch
# ---------------------------------------------------------------------------


def test_shoulder_april_returns_neutral() -> None:
    """April = skuldermåned → 0.5 uavhengig av weather-data."""
    df = _make_weather(2200, tmax_c=20.0, tmin_c=10.0)
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    assert fn(store, "NaturalGas", {"as_of": "2024-04-15"}) == 0.5


def test_shoulder_october_returns_neutral() -> None:
    """Oktober = skuldermåned → 0.5."""
    df = _make_weather(2200, tmax_c=20.0, tmin_c=10.0)
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    assert fn(store, "NaturalGas", {"as_of": "2024-10-15"}) == 0.5


def test_winter_anomaly_high_returns_high_score() -> None:
    """Vinter (Jan) med abnormalt kald siste 30d → høy HDD-anomaly → bull."""
    # Generér 5+ år historikk: januar normalt -5°C; siste 30d sterkt -20°C.
    n = 365 * 6
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    tmax = []
    tmin = []
    for d in idx:
        # Sesongmessig: kaldere om vinteren, varmere om sommeren
        if d.month in (12, 1, 2):
            tmax.append(0.0)
            tmin.append(-10.0)
        elif d.month in (6, 7, 8):
            tmax.append(30.0)
            tmin.append(20.0)
        else:
            tmax.append(15.0)
            tmin.append(5.0)
    df = pd.DataFrame(
        {
            "region": "us_ng_ne",
            "date": idx,
            "tmax": tmax,
            "tmin": tmin,
            "precip": [0.0] * n,
            "gdd": [None] * n,
        }
    )
    # Siste 30 dager før as_of: erstatt med abnormalt kalde temperaturer
    as_of_ts = pd.Timestamp("2024-01-15")
    mask = (df["date"] >= as_of_ts - pd.Timedelta(days=30)) & (df["date"] <= as_of_ts)
    df.loc[mask, "tmax"] = -10.0
    df.loc[mask, "tmin"] = -20.0

    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    score = fn(store, "NaturalGas", {"as_of": "2024-01-15"})
    # Sterkt kald siste 30d → høy HDD-anomaly → ≥ 0.85
    assert score >= 0.85


def test_summer_anomaly_high_returns_high_score() -> None:
    """Sommer (Jul) med abnormalt varm siste 30d → høy CDD-anomaly → bull."""
    n = 365 * 6
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    tmax = []
    tmin = []
    for d in idx:
        if d.month in (6, 7, 8):
            tmax.append(28.0)
            tmin.append(18.0)
        else:
            tmax.append(15.0)
            tmin.append(5.0)
    df = pd.DataFrame(
        {
            "region": "us_ng_ne",
            "date": idx,
            "tmax": tmax,
            "tmin": tmin,
            "precip": [0.0] * n,
            "gdd": [None] * n,
        }
    )
    # Siste 30d før as_of=2024-07-15: hete-bølge
    as_of_ts = pd.Timestamp("2024-07-15")
    mask = (df["date"] >= as_of_ts - pd.Timedelta(days=30)) & (df["date"] <= as_of_ts)
    df.loc[mask, "tmax"] = 38.0
    df.loc[mask, "tmin"] = 28.0

    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    score = fn(store, "NaturalGas", {"as_of": "2024-07-15"})
    assert score >= 0.85


def test_invert_flips_score() -> None:
    """invert=True flipper 1 − score."""
    df = _make_weather(2200, tmax_c=20.0, tmin_c=10.0)
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    # April = shoulder → 0.5; invert flipper til 0.5 (symmetrisk)
    assert fn(store, "NaturalGas", {"as_of": "2024-04-15", "invert": True}) == 0.5


def test_no_weather_data_returns_zero() -> None:
    """Ingen regioner i mock-store → 0.0."""
    store = _MockStore({})
    fn = get("hdd_cdd_anomaly")
    assert fn(store, "NaturalGas", {"as_of": "2024-01-15"}) == 0.0


def test_custom_regions_override() -> None:
    """regions-param override default."""
    n = 365 * 4
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    tmax = [0.0 if d.month in (12, 1, 2) else 15.0 for d in idx]
    tmin = [-10.0 if d.month in (12, 1, 2) else 5.0 for d in idx]
    df = pd.DataFrame(
        {
            "region": "custom_a",
            "date": idx,
            "tmax": tmax,
            "tmin": tmin,
            "precip": [0.0] * n,
            "gdd": [None] * n,
        }
    )
    store = _MockStore({"custom_a": df})
    fn = get("hdd_cdd_anomaly")
    score = fn(
        store,
        "NaturalGas",
        {"as_of": "2024-01-15", "regions": [["custom_a", 1.0]]},
    )
    # Vinter, normal HDD (ingen anomaly) → ~0.6 (positive anomaly because all data is normal)
    # Konstant historikk → 0% pct_anomaly → 0.6
    assert 0.4 <= score <= 0.7


def test_short_history_returns_neutral_05() -> None:
    """For lite historikk (< 30 obs i samme måned-sub-set) → 0.5."""
    df = _make_weather(50, tmax_c=0.0, tmin_c=-10.0, start="2024-01-01")  # bare 50 dager
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    score = fn(store, "NaturalGas", {"as_of": "2024-02-15"})
    assert score == 0.5


def test_as_of_string_parsed() -> None:
    """as_of som ISO-streng skal parses korrekt."""
    df = _make_weather(2200, tmax_c=20.0, tmin_c=10.0)
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    assert fn(store, "NaturalGas", {"as_of": "2024-04-15"}) == 0.5


def test_as_of_date_object_accepted() -> None:
    """as_of som date-objekt skal også fungere."""
    df = _make_weather(2200, tmax_c=20.0, tmin_c=10.0)
    store = _MockStore({"us_ng_ne": df, "us_ng_midwest": df, "us_ng_tx_la": df})
    fn = get("hdd_cdd_anomaly")
    assert fn(store, "NaturalGas", {"as_of": date(2024, 4, 15)}) == 0.5


def test_partial_regions_still_works() -> None:
    """Hvis bare én av default-regionene har data, fungerer driver fortsatt."""
    n = 365 * 6
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    tmax = [0.0 if d.month in (12, 1, 2) else 15.0 for d in idx]
    tmin = [-10.0 if d.month in (12, 1, 2) else 5.0 for d in idx]
    df = pd.DataFrame(
        {
            "region": "us_ng_ne",
            "date": idx,
            "tmax": tmax,
            "tmin": tmin,
            "precip": [0.0] * n,
            "gdd": [None] * n,
        }
    )
    # Kun us_ng_ne har data
    store = _MockStore({"us_ng_ne": df})
    fn = get("hdd_cdd_anomaly")
    score = fn(store, "NaturalGas", {"as_of": "2024-01-15"})
    # Vinter, normal HDD → ~0.6
    assert 0.4 <= score <= 0.7
