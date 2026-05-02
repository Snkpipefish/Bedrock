"""Sub-fase 12.10 Bunke 6 #22 — EIA-utvidelse driver-tester.

Bunke 6-driverne er thin wrappers rundt eia_stock_change. Tester verifiserer
registry + at series_id propageres korrekt.
"""

from __future__ import annotations

import pytest

from bedrock.engine.drivers import get, is_registered


@pytest.mark.parametrize(
    "driver_name,expected_series_id",
    [
        ("eia_distillate_change", "WDISTUS1"),
        ("eia_propane_change", "WPRSTUS1"),
        ("eia_refinery_utilization_z", "WPULEUS3"),
        ("eia_petroleum_supplied", "WRPUPUS2"),
        ("eia_imports_crude", "WCRIMUS2"),
        ("eia_gasoline_demand", "WGFUPUS2"),
        ("eia_natgas_processing", "N9060US2"),  # Spor F8: monthly NGPL Production
    ],
)
def test_driver_registered_and_propagates_series_id(
    driver_name: str, expected_series_id: str
) -> None:
    assert is_registered(driver_name)
    fn = get(driver_name)
    assert callable(fn)

    # Bekreft series_id-propagering ved å fange call til underliggende driver
    captured: dict = {}

    class _MockStore:
        def get_eia_inventory(self, series_id: str, last_n: int | None = None):
            captured["series_id"] = series_id
            import pandas as pd

            # Tom DataFrame med riktig schema slik at eia_stock_change-flyten
            # kan probe lengde uten å kræsje
            return pd.DataFrame(columns=["series_id", "date", "value", "units"])

    store = _MockStore()
    score = fn(store, "CrudeOil", {})
    assert captured.get("series_id") == expected_series_id
    assert 0.0 <= score <= 1.0
