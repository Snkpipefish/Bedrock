# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Tester for Euronext COT-fetcher (sub-fase 12.5+ session 110)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bedrock.data.schemas import COT_EURONEXT_COLS
from bedrock.fetch.cot_euronext import (
    DEFAULT_EURONEXT_PRODUCTS,
    fetch_cot_euronext,
    fetch_cot_euronext_manual,
    fetch_one_product,
    parse_html_report,
    recent_wednesdays,
    report_url,
)

# Sample HTML basert på faktisk Euronext-respons (forenklet).
_SAMPLE_HTML = """
<html><body>
<table>
<tr><td>NL</td><td>Notation</td><td></td>
    <td colspan="2">Investment Firms</td>
    <td colspan="2">Investment Funds</td>
    <td colspan="2">Other Financial</td>
    <td colspan="2">Commercial Undertakings</td></tr>
<tr><th></th><th>L</th><th>S</th><th>L</th><th>S</th><th>L</th><th>S</th><th>L</th><th>S</th></tr>
<tr><td>Number of positions</td></tr>
<tr><td>LOTS</td></tr>
<tr><td>Risk Reducing</td><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td></tr>
<tr><td>Other</td><td>10</td><td>20</td><td>30</td><td>40</td><td>50</td><td>60</td><td>70</td><td>80</td></tr>
<tr><td>Total</td><td>11</td><td>22</td><td>80960</td><td>110134</td><td>55</td><td>66</td><td>77</td><td>88</td></tr>
<tr><td>Changes since previous report</td></tr>
<tr><td>LOTS</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# recent_wednesdays
# ---------------------------------------------------------------------------


def test_recent_wednesdays_descending() -> None:
    # 2026-04-22 var onsdag
    days = recent_wednesdays(n=3, today=date(2026, 4, 22))
    assert days == [date(2026, 4, 22), date(2026, 4, 15), date(2026, 4, 8)]


def test_recent_wednesdays_from_thursday() -> None:
    """Torsdag → siste onsdag = forrige dag."""
    days = recent_wednesdays(n=2, today=date(2026, 4, 23))
    assert days[0] == date(2026, 4, 22)


def test_recent_wednesdays_from_tuesday() -> None:
    """Tirsdag → siste onsdag = uken før."""
    days = recent_wednesdays(n=2, today=date(2026, 4, 21))
    assert days[0] == date(2026, 4, 15)


# ---------------------------------------------------------------------------
# report_url
# ---------------------------------------------------------------------------


def test_report_url_format() -> None:
    url = report_url("EBM", date(2026, 4, 22))
    assert (
        url
        == "https://live.euronext.com/sites/default/files/commodities_reporting/2026/04/22/en/cdwpr_EBM_20260422.html"
    )


# ---------------------------------------------------------------------------
# parse_html_report
# ---------------------------------------------------------------------------


def test_parse_extracts_mm_totals() -> None:
    result = parse_html_report(_SAMPLE_HTML)
    assert result is not None
    assert result["mm_long"] == 80960
    assert result["mm_short"] == 110134
    # OI = sum av Long-kolonner i Total-raden = 11 + 80960 + 55 + 77 = 81103
    assert result["open_interest"] == 81103


def test_parse_returns_none_when_no_investment_funds_header() -> None:
    bad = "<html><body><table><tr><td>nope</td></tr></table></body></html>"
    assert parse_html_report(bad) is None


def test_parse_returns_none_for_short_table() -> None:
    short = """
    <html><body>
    <table>
    <tr><td>Investment Funds</td></tr>
    </table>
    </body></html>
    """
    assert parse_html_report(short) is None


def test_parse_handles_empty_html() -> None:
    assert parse_html_report("") is None


def test_parse_handles_no_total_row() -> None:
    """HTML uten Total-rad → None."""
    no_total = """
    <html><body>
    <table>
    <tr><td>NL</td><td>Notation</td><td></td>
        <td colspan="2">Investment Firms</td>
        <td colspan="2">Investment Funds</td></tr>
    <tr><th></th><th>L</th><th>S</th><th>L</th><th>S</th></tr>
    <tr><td>Number of positions</td></tr>
    <tr><td>LOTS</td></tr>
    <tr><td>Risk Reducing</td><td>1</td><td>2</td><td>3</td><td>4</td></tr>
    </table>
    </body></html>
    """
    assert parse_html_report(no_total) is None


# ---------------------------------------------------------------------------
# fetch_html_for_date / fetch_one_product
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, text: str = _SAMPLE_HTML):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def test_fetch_one_product_yields_dataframe() -> None:
    spec = DEFAULT_EURONEXT_PRODUCTS[0]  # EBM
    sess = MagicMock()
    sess.get.return_value = _mock_response()

    df = fetch_one_product(
        spec,
        n_wednesdays=2,
        session=sess,
        today=date(2026, 4, 22),
        pacing_sec=0,
    )
    assert len(df) == 2  # 2 onsdager
    assert df["contract"].iloc[0] == "euronext milling wheat"
    assert df["mm_long"].iloc[0] == 80960
    assert df["mm_short"].iloc[0] == 110134


def test_fetch_one_product_skips_404() -> None:
    """404-svar dropper raden men feiler ikke."""
    spec = DEFAULT_EURONEXT_PRODUCTS[0]

    call_count = {"n": 0}

    def _get(url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 1:
            return _mock_response(status_code=200)  # Cookie warm-up
        if "20260422" in url:
            return _mock_response(status_code=404, text="")
        return _mock_response()

    sess = MagicMock()
    sess.get.side_effect = _get

    df = fetch_one_product(
        spec, n_wednesdays=3, session=sess, today=date(2026, 4, 22), pacing_sec=0
    )
    # 2 av 3 onsdager skal lykkes
    assert len(df) == 2


def test_fetch_one_product_skips_response_without_table() -> None:
    spec = DEFAULT_EURONEXT_PRODUCTS[0]
    sess = MagicMock()
    sess.get.return_value = _mock_response(text="<html><body>no table</body></html>")
    df = fetch_one_product(
        spec, n_wednesdays=2, session=sess, today=date(2026, 4, 22), pacing_sec=0
    )
    assert df.empty


# ---------------------------------------------------------------------------
# fetch_cot_euronext (combined)
# ---------------------------------------------------------------------------


def test_combined_iterates_all_products(tmp_path: Path) -> None:
    """fetch_cot_euronext kaller fetch_one_product per spec."""
    call_log: list[str] = []

    def _fake(spec, **kwargs):
        call_log.append(spec.symbol)
        return pd.DataFrame(
            [
                {
                    "report_date": "2026-04-22",
                    "contract": spec.contract,
                    "mm_long": 100,
                    "mm_short": 50,
                    "open_interest": 1000,
                }
            ]
        )

    with patch("bedrock.fetch.cot_euronext.fetch_one_product", side_effect=_fake):
        df = fetch_cot_euronext(csv_path=tmp_path / "missing.csv", pacing_sec=0)

    assert call_log == [s.symbol for s in DEFAULT_EURONEXT_PRODUCTS]
    assert len(df) == 3


def test_combined_falls_back_to_csv(tmp_path: Path) -> None:
    csv = tmp_path / "cot_euronext.csv"
    pd.DataFrame(
        [
            {
                "report_date": "2026-04-22",
                "contract": "euronext milling wheat",
                "mm_long": 999,
                "mm_short": 888,
                "open_interest": 7777,
            }
        ]
    ).to_csv(csv, index=False)

    with patch(
        "bedrock.fetch.cot_euronext.fetch_one_product",
        side_effect=RuntimeError("HTML down"),
    ):
        df = fetch_cot_euronext(csv_path=csv, pacing_sec=0)

    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 999


def test_combined_returns_empty_when_both_fail(tmp_path: Path) -> None:
    with patch(
        "bedrock.fetch.cot_euronext.fetch_one_product",
        side_effect=RuntimeError("HTML down"),
    ):
        df = fetch_cot_euronext(csv_path=tmp_path / "missing.csv", pacing_sec=0)
    assert df.empty
    assert list(df.columns) == list(COT_EURONEXT_COLS)


# ---------------------------------------------------------------------------
# fetch_cot_euronext_manual
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_missing(tmp_path: Path) -> None:
    df = fetch_cot_euronext_manual(tmp_path / "nope.csv")
    assert df.empty


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv = tmp_path / "cot_euronext.csv"
    pd.DataFrame(
        [
            {
                "report_date": "2026-04-22",
                "contract": "euronext milling wheat",
                "mm_long": 80000,
                "mm_short": 110000,
                "open_interest": 475000,
            }
        ]
    ).to_csv(csv, index=False)

    df = fetch_cot_euronext_manual(csv)
    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 80000


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("report_date,contract\n2026-04-22,wheat\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_cot_euronext_manual(csv)


# ---------------------------------------------------------------------------
# Default-products
# ---------------------------------------------------------------------------


def test_default_products_includes_three() -> None:
    contracts = {p.contract for p in DEFAULT_EURONEXT_PRODUCTS}
    assert "euronext milling wheat" in contracts
    assert "euronext corn" in contracts
    assert "euronext canola" in contracts
