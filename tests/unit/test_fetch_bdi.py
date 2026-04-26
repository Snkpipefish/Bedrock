"""Tester for ``bedrock.fetch.manual_events.fetch_bdi_via_bdry``.

Verifiserer at BDRY ETF (Yahoo) konverteres riktig til BDI_COLS-schema.
Yahoo-kallet mockes; ingen network-IO i tester.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from bedrock.data.schemas import BDI_COLS
from bedrock.fetch.manual_events import fetch_bdi_via_bdry


def _make_yahoo_df(n: int = 5) -> pd.DataFrame:
    """Bygg fake Yahoo-prices-output (samme format som fetch_yahoo_prices)."""
    return pd.DataFrame(
        {
            "ts": pd.to_datetime([f"2025-04-{i + 1:02d}" for i in range(n)]),
            "open": [10.0 + i for i in range(n)],
            "high": [10.5 + i for i in range(n)],
            "low": [9.5 + i for i in range(n)],
            "close": [10.0 + i * 0.5 for i in range(n)],
            "volume": [100000.0] * n,
        }
    )


def test_fetch_bdi_via_bdry_converts_to_bdi_schema() -> None:
    fake = _make_yahoo_df(5)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake):
        df = fetch_bdi_via_bdry(start_date="2025-04-01")

    assert list(df.columns) == list(BDI_COLS)
    assert len(df) == 5
    assert (df["source"] == "BDRY").all()
    # Verdier skal komme fra close
    assert df["value"].iloc[0] == 10.0
    assert df["value"].iloc[-1] == 12.0
    # Dato-format skal være ISO
    assert df["date"].iloc[0] == "2025-04-01"


def test_fetch_bdi_via_bdry_empty_returns_empty_df() -> None:
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=pd.DataFrame()):
        df = fetch_bdi_via_bdry()

    assert df.empty
    assert list(df.columns) == list(BDI_COLS)


def test_fetch_bdi_via_bdry_yahoo_error_returns_empty() -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("network down")

    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", side_effect=_raise):
        df = fetch_bdi_via_bdry()

    assert df.empty
    assert list(df.columns) == list(BDI_COLS)


def test_fetch_bdi_via_bdry_default_end_date_is_today() -> None:
    fake = _make_yahoo_df(2)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake) as mock:
        fetch_bdi_via_bdry(start_date="2025-04-01")

    # Verifiser at end-arg fra kall ikke er None
    call_kwargs = mock.call_args.kwargs
    call_args = mock.call_args.args
    # Yahoo fetcher tar start, end som positional eller keyword
    args_combined = list(call_args) + list(call_kwargs.values())
    has_today_or_close = any(
        isinstance(a, date) and (date.today() - a).days < 2 for a in args_combined
    )
    assert has_today_or_close
