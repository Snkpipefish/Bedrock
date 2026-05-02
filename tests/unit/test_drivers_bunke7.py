"""Sub-fase 12.10 Bunke 7 driver-tester."""

from __future__ import annotations

import pytest

from bedrock.engine.drivers import get, is_registered


@pytest.mark.parametrize(
    "driver_name",
    [
        "agsi_germany_pct",
        "agsi_netherlands_pct",
        "agsi_italy_pct",
        "agsi_withdrawal_rate",
        "agsi_injection_rate",
        "cot_oi_change",
        "cot_commercial_extreme",
    ],
)
def test_driver_registered(driver_name: str) -> None:
    assert is_registered(driver_name)
    assert callable(get(driver_name))


def test_agsi_country_wrappers_propagate_country() -> None:
    """agsi_germany_pct → underliggende driver kalt med country='de'."""
    captured: dict = {}

    class _MockStore:
        def get_agsi_storage(self, country: str, last_n: int | None = None):
            captured["country"] = country
            import pandas as pd

            return pd.DataFrame()

    fn = get("agsi_germany_pct")
    fn(_MockStore(), "NaturalGas", {})
    assert captured["country"] == "de"


def test_cot_oi_change_requires_contract_param() -> None:
    """Uten contract-param → 0.0."""
    fn = get("cot_oi_change")

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return None

    assert fn(_MockStore(), "CrudeOil", {}) == 0.0


def test_cot_commercial_extreme_returns_neutral_when_sparse() -> None:
    fn = get("cot_commercial_extreme")
    import pandas as pd

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=10, freq="W"),
                    "comm_long": [1000] * 10,
                    "comm_short": [500] * 10,
                    "open_interest": [3000] * 10,
                }
            )

    assert fn(_MockStore(), "CrudeOil", {"contract": "X"}) == 0.5
