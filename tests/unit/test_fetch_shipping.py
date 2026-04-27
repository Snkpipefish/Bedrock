# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Tester for ``bedrock.fetch.shipping`` (sub-fase 12.5+ session 113).

Verifiserer at BDI hentes via BDRY-ETF (Yahoo, mocket) og at manuell
CSV-fallback håndterer BCI/BPI/BSI. Ingen network-IO i tester.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.data.schemas import SHIPPING_INDICES_COLS
from bedrock.fetch.shipping import (
    fetch_bdi_via_bdry,
    fetch_shipping_indices,
    fetch_shipping_manual_csv,
)

# ---------------------------------------------------------------------------
# Yahoo BDRY → BDI
# ---------------------------------------------------------------------------


def _make_yahoo_df(n: int = 5) -> pd.DataFrame:
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


def test_fetch_bdi_via_bdry_returns_shipping_schema() -> None:
    fake = _make_yahoo_df(5)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake):
        df = fetch_bdi_via_bdry(start_date="2025-04-01")

    assert list(df.columns) == list(SHIPPING_INDICES_COLS)
    assert len(df) == 5
    assert (df["index_code"] == "BDI").all()
    assert (df["source"] == "BDRY").all()
    assert df["value"].iloc[0] == 10.0
    assert df["date"].iloc[0] == "2025-04-01"


def test_fetch_bdi_via_bdry_empty_returns_empty_with_correct_columns() -> None:
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=pd.DataFrame()):
        df = fetch_bdi_via_bdry()
    assert df.empty
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)


def test_fetch_bdi_via_bdry_yahoo_error_returns_empty() -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("yahoo down")

    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", side_effect=_raise):
        df = fetch_bdi_via_bdry()
    assert df.empty
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)


def test_fetch_bdi_via_bdry_default_end_date_is_today() -> None:
    fake = _make_yahoo_df(2)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake) as mock:
        fetch_bdi_via_bdry(start_date="2025-04-01")
    args = list(mock.call_args.args) + list(mock.call_args.kwargs.values())
    assert any(isinstance(a, date) and (date.today() - a).days < 2 for a in args)


# ---------------------------------------------------------------------------
# Manuell CSV
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[tuple[str, str, float, str]]) -> None:
    df = pd.DataFrame(rows, columns=list(SHIPPING_INDICES_COLS))
    df.to_csv(path, index=False)


def test_manual_csv_reads_all_indices(tmp_path: Path) -> None:
    csv = tmp_path / "shipping_indices.csv"
    _write_csv(
        csv,
        [
            ("BCI", "2026-04-22", 3850.0, "MANUAL"),
            ("BPI", "2026-04-22", 1620.0, "MANUAL"),
            ("BSI", "2026-04-22", 1150.0, "MANUAL"),
        ],
    )
    df = fetch_shipping_manual_csv(csv)
    assert len(df) == 3
    assert set(df["index_code"]) == {"BCI", "BPI", "BSI"}
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)


def test_manual_csv_uppercase_index_codes(tmp_path: Path) -> None:
    csv = tmp_path / "shipping_indices.csv"
    _write_csv(csv, [("bpi", "2026-04-22", 1620.0, "MANUAL")])
    df = fetch_shipping_manual_csv(csv)
    assert df["index_code"].iloc[0] == "BPI"


def test_manual_csv_filters_unknown_codes(tmp_path: Path) -> None:
    csv = tmp_path / "shipping_indices.csv"
    _write_csv(
        csv,
        [
            ("BPI", "2026-04-22", 1620.0, "MANUAL"),
            ("XYZ", "2026-04-22", 9999.0, "MANUAL"),
        ],
    )
    df = fetch_shipping_manual_csv(csv)
    assert len(df) == 1
    assert df["index_code"].iloc[0] == "BPI"


def test_manual_csv_missing_file_returns_empty(tmp_path: Path) -> None:
    df = fetch_shipping_manual_csv(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)


def test_manual_csv_missing_columns_raises(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    pd.DataFrame({"index_code": ["BPI"], "date": ["2026-04-22"]}).to_csv(csv, index=False)
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_shipping_manual_csv(csv)


# ---------------------------------------------------------------------------
# Orchestrator: fetch_shipping_indices
# ---------------------------------------------------------------------------


def test_fetch_shipping_indices_combines_bdi_and_manual(tmp_path: Path) -> None:
    csv = tmp_path / "shipping.csv"
    _write_csv(
        csv,
        [
            ("BCI", "2026-04-22", 3850.0, "MANUAL"),
            ("BPI", "2026-04-22", 1620.0, "MANUAL"),
        ],
    )
    fake = _make_yahoo_df(3)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake):
        df = fetch_shipping_indices(start_date="2025-04-01", csv_path=csv)

    assert len(df) == 5  # 3 BDI + 2 manual
    assert set(df["index_code"]) == {"BDI", "BCI", "BPI"}
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)


def test_fetch_shipping_indices_yahoo_only_when_csv_missing(tmp_path: Path) -> None:
    fake = _make_yahoo_df(2)
    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", return_value=fake):
        df = fetch_shipping_indices(start_date="2025-04-01", csv_path=tmp_path / "missing.csv")
    assert len(df) == 2
    assert (df["index_code"] == "BDI").all()


def test_fetch_shipping_indices_csv_only_when_yahoo_fails(tmp_path: Path) -> None:
    csv = tmp_path / "shipping.csv"
    _write_csv(csv, [("BPI", "2026-04-22", 1620.0, "MANUAL")])

    def _raise(*args, **kwargs):
        raise RuntimeError("yahoo down")

    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", side_effect=_raise):
        df = fetch_shipping_indices(start_date="2025-04-01", csv_path=csv)
    assert len(df) == 1
    assert df["index_code"].iloc[0] == "BPI"


def test_fetch_shipping_indices_empty_when_both_fail(tmp_path: Path) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("yahoo down")

    with patch("bedrock.fetch.yahoo.fetch_yahoo_prices", side_effect=_raise):
        df = fetch_shipping_indices(start_date="2025-04-01", csv_path=tmp_path / "missing.csv")
    assert df.empty
    assert list(df.columns) == list(SHIPPING_INDICES_COLS)
