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
        "cot_concentration_top4",
        "cot_swap_dealer_skew",
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


# ---------------------------------------------------------------------------
# Spor F5: cot_concentration_top4 + cot_swap_dealer_skew
# ---------------------------------------------------------------------------


def test_cot_concentration_top4_no_contract_returns_zero() -> None:
    fn = get("cot_concentration_top4")

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return None

    assert fn(_MockStore(), "CrudeOil", {}) == 0.0


def test_cot_concentration_top4_missing_column_returns_zero() -> None:
    """Hvis Spor F5-backfill ikke er kjørt → conc_net_top4-kolonnen mangler."""
    fn = get("cot_concentration_top4")
    import pandas as pd

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=30, freq="W"),
                    "open_interest": [1000] * 30,
                }
            )

    assert fn(_MockStore(), "CrudeOil", {"contract": "X"}) == 0.0


def test_cot_concentration_top4_high_rank_returns_low_score_default() -> None:
    """Default bull_when='low': høy konsentrasjon = lav score."""
    fn = get("cot_concentration_top4")
    import pandas as pd

    # 30 rader, siste = max-verdi → percentile-rank ~1.0 → score ~0.0
    vals = list(range(30))
    vals[-1] = 100  # ekstrem siste-obs

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=30, freq="W"),
                    "open_interest": [1000] * 30,
                    "conc_net_top4": vals,
                }
            )

    score = fn(_MockStore(), "CrudeOil", {"contract": "X"})
    assert score < 0.1  # ekstrem-rank → bull_when=low → score nær 0


def test_cot_concentration_top4_supports_top8_param() -> None:
    fn = get("cot_concentration_top4")
    import pandas as pd

    captured = []

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            df = pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=30, freq="W"),
                    "open_interest": [1000] * 30,
                    "conc_net_top8": list(range(30)),
                }
            )
            captured.append(list(df.columns))
            return df

    score = fn(_MockStore(), "CrudeOil", {"contract": "X", "top": 8})
    assert 0.0 <= score <= 1.0
    assert "conc_net_top8" in captured[0]


def test_cot_swap_dealer_skew_missing_columns_returns_zero() -> None:
    fn = get("cot_swap_dealer_skew")
    import pandas as pd

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=30, freq="W"),
                    "open_interest": [1000] * 30,
                }
            )

    assert fn(_MockStore(), "CrudeOil", {"contract": "X"}) == 0.0


def test_cot_swap_dealer_skew_high_skew_returns_high_score_default() -> None:
    """Default bull_when='high': høy net-long skew = høy score."""
    fn = get("cot_swap_dealer_skew")
    import pandas as pd

    n = 30
    longs = list(range(100, 100 + n))
    shorts = [50] * n
    longs[-1] = 1000  # extreme net-long siste obs

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=n, freq="W"),
                    "open_interest": [10_000] * n,
                    "swap_long": longs,
                    "swap_short": shorts,
                }
            )

    score = fn(_MockStore(), "CrudeOil", {"contract": "X"})
    assert score > 0.9


def test_cot_swap_dealer_skew_returns_neutral_when_sparse() -> None:
    fn = get("cot_swap_dealer_skew")
    import pandas as pd

    class _MockStore:
        def get_cot(self, contract, report="disaggregated", last_n=None):
            return pd.DataFrame(
                {
                    "report_date": pd.date_range("2025-01-01", periods=10, freq="W"),
                    "open_interest": [1000] * 10,
                    "swap_long": [100] * 10,
                    "swap_short": [50] * 10,
                }
            )

    assert fn(_MockStore(), "CrudeOil", {"contract": "X"}) == 0.5
